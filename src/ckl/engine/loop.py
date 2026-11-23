"""Render loop: composites the active profile at a fixed rate and streams frames to GameSense.

Two threads:
  * render thread - builds frames at ``fps`` (reads keys, lock state, CPU)
  * sender thread - pushes the *latest* frame to GG (a send takes ~35 ms, so stale
    frames are dropped instead of queueing up)
"""
from __future__ import annotations

import ctypes
import logging
import threading
import time

import numpy as np
import psutil

from ..gamesense import GameSenseClient
from ..input import KeyHook
from ..layout import Layout
from .effects import RenderContext
from .layer import Layer, LayerConfig, composite, to_u8

log = logging.getLogger(__name__)

VK_CAPITAL, VK_NUMLOCK, VK_SCROLL = 0x14, 0x90, 0x91
RESEND_INTERVAL = 3.0  # re-send unchanged frames so GG never times out


def _lock_states() -> dict[str, bool]:
    try:
        gks = ctypes.windll.user32.GetKeyState
        return {"caps": bool(gks(VK_CAPITAL) & 1), "num": bool(gks(VK_NUMLOCK) & 1), "scroll": bool(gks(VK_SCROLL) & 1)}
    except AttributeError:  # non-Windows (tests)
        return {}


class Engine:
    def __init__(self, layout: Layout, client: GameSenseClient, keyhook: KeyHook | None = None, fps: int = 30) -> None:
        self.layout = layout
        self.client = client
        self.keyhook = keyhook or KeyHook()
        self.fps = fps
        self.mouse_fps = 10.0  # cap wireless mouse lighting updates (battery)
        self.master = 1.0
        self.keyboard_level = 1.0
        self.mouse_level = 1.0
        self._levels = np.ones((layout.n, 1), dtype=np.float32)
        self._is_mouse = np.array([l.device == "mouse" for l in layout.leds])
        self._layers: list[Layer] = []
        self._layers_lock = threading.Lock()
        self._want_reactive = False
        self._paused = False
        self._running = False
        self._t0 = time.monotonic()
        self._preview = np.zeros((layout.n, 3), dtype=np.uint8)
        self._override: np.ndarray | None = None  # raw per-LED frame
        self._override_bitmap: list | None = None  # raw 132-cell bitmap (calibration)
        self._pending: tuple[list, list] | None = None
        self._cv = threading.Condition()
        self._threads: list[threading.Thread] = []
        self._cpu = 0.0
        self._cpu_at = 0.0
        self.frames_sent = 0
        psutil.cpu_percent(None)  # prime

    # ------------------------------------------------------------------ control
    def start(self) -> None:
        if self._running:
            return
        self._running = True
        for target, name in ((self._render_loop, "ckl-render"), (self._send_loop, "ckl-send")):
            t = threading.Thread(target=target, name=name, daemon=True)
            t.start()
            self._threads.append(t)

    def stop(self) -> None:
        self._running = False
        with self._cv:
            self._cv.notify_all()
        for t in self._threads:
            t.join(timeout=2)
        self._threads.clear()
        self.keyhook.stop()
        self.client.stop()

    @property
    def paused(self) -> bool:
        return self._paused

    def set_paused(self, paused: bool) -> None:
        self._paused = paused
        if paused:
            with self._cv:
                self._pending = None
            self.client.stop()  # hand lighting back to GG
        self._sync_keyhook()

    def set_levels(self, master: float | None = None, keyboard: float | None = None, mouse: float | None = None) -> None:
        """Brightness levels 0..1. Effective level = master x device level."""
        if master is not None:
            self.master = float(np.clip(master, 0.0, 1.0))
        if keyboard is not None:
            self.keyboard_level = float(np.clip(keyboard, 0.0, 1.0))
        if mouse is not None:
            self.mouse_level = float(np.clip(mouse, 0.0, 1.0))
        lv = np.where(self._is_mouse, self.mouse_level, self.keyboard_level) * self.master
        self._levels = lv.astype(np.float32)[:, None]

    def set_layers(self, configs: list[LayerConfig], reactive: bool = True) -> None:
        """Swap in a new layer stack (called from the UI thread)."""
        layers = []
        for cfg in configs:
            try:
                layers.append(Layer(cfg, self.layout))
            except Exception as exc:  # noqa: BLE001 - a broken layer must not kill lighting
                log.warning("skipping layer %s: %s", cfg.effect, exc)
        with self._layers_lock:
            self._layers = layers
        self._want_reactive = reactive and any(l.reactive for l in layers)
        self._sync_keyhook()

    def set_raw_override(self, colors_u8: np.ndarray | None) -> None:
        """Show a fixed per-LED frame instead of the profile (``None`` to resume)."""
        self._override = None if colors_u8 is None else colors_u8.copy()

    def set_raw_bitmap(self, bitmap: list | None) -> None:
        """Calibration helper: send an explicit 132-cell bitmap, bypassing the layout map."""
        self._override_bitmap = bitmap

    def add_key_subscriber(self, cb) -> None:
        """Receive raw scan codes on the hook thread (keeps the hook alive while subscribed)."""
        self.keyhook.subscribers.append(cb)
        self._sync_keyhook()

    def remove_key_subscriber(self, cb) -> None:
        if cb in self.keyhook.subscribers:
            self.keyhook.subscribers.remove(cb)
        self._sync_keyhook()

    def preview(self) -> np.ndarray:
        return self._preview

    @property
    def connected(self) -> bool:
        return self.client.connected

    def _sync_keyhook(self) -> None:
        need = (self._want_reactive and not self._paused) or bool(self.keyhook.subscribers)
        if need and not self.keyhook.running:
            self.keyhook.start()
        elif not need and self.keyhook.running:
            self.keyhook.stop()

    # ------------------------------------------------------------------ threads
    def _render_loop(self) -> None:
        last = time.monotonic()
        next_frame = last
        while self._running:
            now = time.monotonic()
            dt, last = now - last, now
            presses = []
            for scan, t in self.keyhook.drain():
                led = self.layout.by_scan.get(scan)
                if led is not None:
                    presses.append((led.index, t - self._t0))
            if now - self._cpu_at > 0.5:
                self._cpu = psutil.cpu_percent(None) / 100.0
                self._cpu_at = now
            held = {self.layout.by_scan[s].index for s in self.keyhook.snapshot_held() if s in self.layout.by_scan}
            ctx = RenderContext(t=now - self._t0, dt=min(dt, 0.25), layout=self.layout, presses=presses,
                                held=held, locks=_lock_states(), cpu=self._cpu)
            try:
                with self._layers_lock:
                    layers = self._layers
                    colors = composite(layers, ctx)
                frame = to_u8(colors, self._levels)
            except Exception:  # noqa: BLE001
                log.exception("render failed")
                frame = np.zeros((self.layout.n, 3), np.uint8)
            if self._override is not None:
                frame = self._override
            self._preview = frame
            bitmap = self._override_bitmap or self.layout.to_bitmap(frame)
            if not self._paused:
                with self._cv:
                    self._pending = (bitmap, self.layout.to_mouse(frame))
                    self._cv.notify()
            next_frame += 1.0 / max(1, self.fps)
            sleep = next_frame - time.monotonic()
            if sleep > 0:
                time.sleep(sleep)
            else:
                next_frame = time.monotonic()

    def _send_loop(self) -> None:
        state = SendState()
        while self._running:
            with self._cv:
                if self._pending is None:
                    self._cv.wait(timeout=1.0)
                item, self._pending = self._pending, None
            if self._paused or not self._running:
                state.reset()  # resend everything after resuming
                continue
            now = time.monotonic()
            kb, mouse = state.plan(item, now, self.mouse_fps)
            if kb is None and mouse is None:
                continue
            if self.client.send_frame(kb, mouse):
                state.sent(kb, mouse, now)
                self.frames_sent += 1
            else:
                state.reset()
                time.sleep(0.5)


MOUSE_REFRESH = 30.0  # re-assert mouse colors occasionally (e.g. after the mouse wakes up)


class SendState:
    """Decides what actually goes over the wire.

    * keyboard: whenever it changes, and re-sent every RESEND_INTERVAL as a keep-alive
    * mouse: only when its colors change, at most ``mouse_fps`` times a second, plus a slow
      refresh. A static or switched-off mouse therefore costs (almost) no wireless traffic.
    """

    def __init__(self) -> None:
        self.reset()

    def reset(self) -> None:
        self.kb = None
        self.mouse = None
        self.kb_time = float("-inf")  # never sent
        self.mouse_time = float("-inf")

    def plan(self, item, now: float, mouse_fps: float):
        kb_stale = now - self.kb_time > RESEND_INTERVAL
        if item is None:  # no new frame: keep-alive only
            return (self.kb if kb_stale and self.kb is not None else None), None
        kb, mouse = item
        if kb == self.kb and not kb_stale:
            kb = None
        mouse_due = now - self.mouse_time >= 1.0 / max(mouse_fps, 0.1)
        mouse_refresh = now - self.mouse_time > MOUSE_REFRESH
        if not ((mouse != self.mouse and mouse_due) or mouse_refresh):
            mouse = None
        return kb, mouse

    def sent(self, kb, mouse, now: float) -> None:
        if kb is not None:
            self.kb, self.kb_time = kb, now
        if mouse is not None:
            self.mouse, self.mouse_time = mouse, now

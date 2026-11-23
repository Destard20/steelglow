"""Global, read-only key listener (Windows low-level hook via pynput).

Never suppresses or alters input: events are only observed to drive reactive lighting.
Events are reported as scan codes (| 0xE000 for extended keys), which are independent of the
active keyboard language.
"""
from __future__ import annotations

import logging
import queue
import threading
import time

log = logging.getLogger(__name__)

WM_KEYDOWN, WM_KEYUP, WM_SYSKEYDOWN, WM_SYSKEYUP = 0x100, 0x101, 0x104, 0x105
LLKHF_EXTENDED = 0x01


class KeyHook:
    def __init__(self) -> None:
        self.events: "queue.SimpleQueue[tuple[int, float]]" = queue.SimpleQueue()
        self.held: set[int] = set()
        self._held_lock = threading.Lock()
        self._listener = None
        self.subscribers: list = []  # callables(scan) for calibration UI etc.

    @property
    def running(self) -> bool:
        return self._listener is not None

    def start(self) -> None:
        if self._listener is not None:
            return
        from pynput import keyboard

        self._listener = keyboard.Listener(win32_event_filter=self._filter)
        self._listener.daemon = True
        self._listener.start()
        log.info("key hook started")

    def stop(self) -> None:
        if self._listener is not None:
            self._listener.stop()
            self._listener = None
            with self._held_lock:
                self.held.clear()
            log.info("key hook stopped")

    def snapshot_held(self) -> set[int]:
        with self._held_lock:
            return set(self.held)

    def drain(self) -> list[tuple[int, float]]:
        out = []
        while True:
            try:
                out.append(self.events.get_nowait())
            except queue.Empty:
                return out

    # Runs on the hook thread: keep it fast.
    def _filter(self, msg, data) -> bool:
        sc = data.scanCode
        if sc == 0 or sc > 0xFF:  # synthetic events (e.g. fake LCtrl from AltGr)
            return False
        scan = sc | (0xE000 if data.flags & LLKHF_EXTENDED else 0)
        if msg in (WM_KEYDOWN, WM_SYSKEYDOWN):
            with self._held_lock:
                repeat = scan in self.held
                self.held.add(scan)
            if not repeat:
                self.events.put((scan, time.monotonic()))
                for cb in list(self.subscribers):
                    try:
                        cb(scan)
                    except Exception:  # noqa: BLE001 - never break the hook
                        log.exception("key subscriber failed")
        elif msg in (WM_KEYUP, WM_SYSKEYUP):
            with self._held_lock:
                self.held.discard(scan)
        return False  # don't run pynput's own (unused) callbacks; input is NOT suppressed

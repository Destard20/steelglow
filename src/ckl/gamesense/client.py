"""Minimal client for the SteelSeries GameSense local HTTP API (served by SteelSeries GG).

Only the pieces needed to stream per-key keyboard frames and 3-zone mouse colors are used:
  * ``bitmap`` mode on ``rgb-per-key-zones`` (132 = 22x6 grid of [r, g, b])
  * ``context-color`` mode on ``rgb-3-zone`` zones one/two/three
"""
from __future__ import annotations

import json
import logging
import os
import threading
import time
from pathlib import Path
from typing import Iterable, Sequence

import httpx

log = logging.getLogger(__name__)

GAME = "STEELGLOW"
LEGACY_GAMES = ("CUSTOM_KB_LIGHTS",)  # pre-rename ids; unregistered from GG once per run
KB_EVENT = "KB_FRAME"
MOUSE_EVENT = "MOUSE_FRAME"
GRID_ROWS, GRID_COLS = 6, 22
BITMAP_LEN = GRID_ROWS * GRID_COLS
MOUSE_ZONES = ("one", "two", "three")

CORE_PROPS_CANDIDATES = (
    Path(os.environ.get("PROGRAMDATA", r"C:\ProgramData")) / "SteelSeries" / "SteelSeries Engine 3" / "coreProps.json",
    Path(os.environ.get("PROGRAMDATA", r"C:\ProgramData")) / "SteelSeries" / "GG" / "coreProps.json",
)

Color = Sequence[int]


class GameSenseUnavailable(RuntimeError):
    """Raised when SteelSeries GG / GameSense cannot be reached."""


def read_address() -> str:
    """Return ``host:port`` of the GameSense server from coreProps.json."""
    for path in CORE_PROPS_CANDIDATES:
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if data.get("address"):
            return data["address"]
    raise GameSenseUnavailable("coreProps.json not found - is SteelSeries GG running?")


class GameSenseClient:
    """Thread-safe GameSense client with automatic re-registration after GG restarts."""

    def __init__(
        self,
        game: str = GAME,
        display_name: str = "SteelGlow",
        mouse_device_type: str = "rgb-3-zone",
        deinit_ms: int = 1000,
        reconnect_interval: float = 2.0,
    ) -> None:
        self.game = game
        self.display_name = display_name
        self.mouse_device_type = mouse_device_type
        self.deinit_ms = deinit_ms
        self.reconnect_interval = reconnect_interval
        self._http = httpx.Client(timeout=2.0)
        self._lock = threading.RLock()
        self._base: str | None = None
        self._multi = False
        self._last_attempt = 0.0
        self._counter = 0
        self._legacy_removed = False
        self.last_error: str | None = None

    # ------------------------------------------------------------------ connection
    @property
    def connected(self) -> bool:
        return self._base is not None

    def connect(self) -> None:
        """Register the game and bind the lighting handlers. Raises GameSenseUnavailable."""
        with self._lock:
            self._last_attempt = time.monotonic()
            base = "http://" + read_address()
            try:
                self._post(base, "game_metadata", {
                    "game": self.game,
                    "game_display_name": self.display_name,
                    "developer": "SteelGlow",
                    "deinitialize_timer_length_ms": self.deinit_ms,
                })
                self._post(base, "bind_game_event", {
                    "game": self.game,
                    "event": KB_EVENT,
                    "value_optional": True,
                    "handlers": [{"device-type": "rgb-per-key-zones", "mode": "bitmap"}],
                })
                self._post(base, "bind_game_event", {
                    "game": self.game,
                    "event": MOUSE_EVENT,
                    "value_optional": True,
                    "handlers": [
                        {
                            "device-type": self.mouse_device_type,
                            "zone": zone,
                            "mode": "context-color",
                            "context-frame-key": f"z{i + 1}",
                        }
                        for i, zone in enumerate(MOUSE_ZONES)
                    ],
                })
                try:
                    r = self._http.get(f"{base}/supports_multiple_game_events")
                    self._multi = r.status_code == 200
                except httpx.HTTPError:
                    self._multi = False
            except (httpx.HTTPError, GameSenseUnavailable) as exc:
                self._base = None
                self.last_error = str(exc)
                raise GameSenseUnavailable(str(exc)) from exc
            self._base = base
            self.last_error = None
            log.info("GameSense connected at %s (multiple_game_events=%s)", base, self._multi)
            self._remove_legacy_games(base)

    def _remove_legacy_games(self, base: str) -> None:
        """Drop pre-rename registrations so GG's Engine > Apps list shows only one entry."""
        if self._legacy_removed:
            return
        self._legacy_removed = True
        for old in LEGACY_GAMES:
            if old == self.game:
                continue
            try:
                self._post(base, "remove_game", {"game": old})
                log.info("removed legacy GameSense registration %s", old)
            except httpx.HTTPError:
                pass  # never registered (400) or GG busy: nothing to clean up

    def ensure_connected(self) -> bool:
        """Try to (re)connect, rate-limited. Returns True when connected."""
        if self._base:
            return True
        if time.monotonic() - self._last_attempt < self.reconnect_interval:
            return False
        try:
            self.connect()
        except GameSenseUnavailable as exc:
            log.debug("GameSense unavailable: %s", exc)
            return False
        return True

    def stop(self) -> None:
        """Stop our lighting so GG's own lighting comes back (client stays usable)."""
        with self._lock:
            if self._base:
                try:
                    self._post(self._base, "stop_game", {"game": self.game})
                except httpx.HTTPError:
                    pass
            self._base = None

    def close(self) -> None:
        self.stop()
        self._http.close()

    def remove_game(self) -> None:
        """Unregister completely (removes the app from GG's Engine apps list)."""
        with self._lock:
            if self.ensure_connected():
                try:
                    self._post(self._base, "remove_game", {"game": self.game})
                except httpx.HTTPError:
                    pass
                self._base = None

    # ------------------------------------------------------------------ sending
    def send_frame(self, bitmap: Iterable[Color] | None = None, mouse: Sequence[Color] | None = None) -> bool:
        """Push one lighting frame. ``bitmap`` = 132 RGB triples, ``mouse`` = 3 RGB triples.

        Returns False (without raising) when GG is not reachable; reconnects automatically.
        """
        with self._lock:
            if not self.ensure_connected():
                return False
            self._counter = (self._counter + 1) % 100
            events = []
            if bitmap is not None:
                bm = [[int(c[0]), int(c[1]), int(c[2])] for c in bitmap]
                if len(bm) != BITMAP_LEN:
                    raise ValueError(f"bitmap must have {BITMAP_LEN} entries, got {len(bm)}")
                events.append({"event": KB_EVENT, "data": {"value": self._counter, "frame": {"bitmap": bm}}})
            if mouse is not None:
                frame = {
                    f"z{i + 1}": {"red": int(c[0]), "green": int(c[1]), "blue": int(c[2])}
                    for i, c in enumerate(mouse[:3])
                }
                events.append({"event": MOUSE_EVENT, "data": {"value": self._counter, "frame": frame}})
            if not events:
                return True
            try:
                if self._multi and len(events) > 1:
                    self._post(self._base, "multiple_game_events", {"game": self.game, "events": events})
                else:
                    for ev in events:
                        self._post(self._base, "game_event", {"game": self.game, **ev})
            except httpx.HTTPStatusError as exc:
                # 400 "game not registered" happens after GG restarts on the same port.
                self._drop(f"GameSense rejected frame: {exc.response.text}")
                return False
            except httpx.HTTPError as exc:
                self._drop(f"GameSense connection lost: {exc}")
                return False
            return True

    def heartbeat(self) -> bool:
        with self._lock:
            if not self.ensure_connected():
                return False
            try:
                self._post(self._base, "game_heartbeat", {"game": self.game})
            except httpx.HTTPError as exc:
                self._drop(f"heartbeat failed: {exc}")
                return False
            return True

    # ------------------------------------------------------------------ internals
    def _drop(self, msg: str) -> None:
        log.warning(msg)
        self.last_error = msg
        self._base = None
        self._last_attempt = 0.0  # allow an immediate reconnect attempt on next call

    def _post(self, base: str, endpoint: str, payload: dict) -> httpx.Response:
        r = self._http.post(f"{base}/{endpoint}", json=payload)
        r.raise_for_status()
        return r

"""LED layout: every lightable thing (keyboard keys + mouse zones) is an "LED" with a position.

Effects render one color per LED. ``Layout.to_bitmap`` converts the keyboard LEDs into the
132-cell (22x6) GameSense bitmap using ``cell_to_led`` (default: nearest key in the same row,
overridable by the calibration wizard).
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from ..gamesense.client import BITMAP_LEN, GRID_COLS, GRID_ROWS
from ..paths import data_dir
from . import apex9_tkl

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class Led:
    index: int
    id: str
    label: str
    scan: int | None  # Windows scan code (| 0xE000 if extended); None for keys without one
    x: float  # left, in key units
    y: float  # top, in key units
    w: float
    h: float
    row: int  # keyboard row 0-5, or -1 for mouse zones
    device: str  # "keyboard" | "mouse"

    @property
    def cx(self) -> float:
        return self.x + self.w / 2

    @property
    def cy(self) -> float:
        return self.y + self.h / 2


def calibration_path() -> Path:
    return data_dir() / "calibration_apex9_tkl.json"


class Layout:
    def __init__(self, calibration_file: Path | None = None) -> None:
        leds: list[Led] = []
        for row_idx, (y, keys) in enumerate(apex9_tkl.ROWS):
            x = 0.0
            for kid, label, scan, w in keys:
                if kid is not None:
                    h = 2.0 if kid == "enter" else 1.0
                    leds.append(Led(len(leds), kid, label, scan, x, y, w, h, row_idx, "keyboard"))
                x += w
        for mid, label, mx, my in apex9_tkl.MOUSE_LEDS:
            leds.append(Led(len(leds), mid, label, None, mx, my, 1.0, 1.0, -1, "mouse"))
        self.leds = leds
        self.n = len(leds)
        self.by_id = {l.id: l for l in leds}
        self.by_scan = {l.scan: l for l in leds if l.scan is not None}
        self.keyboard = [l for l in leds if l.device == "keyboard"]
        self.mouse = [l for l in leds if l.device == "mouse"]
        self.mouse_idx = np.array([l.index for l in self.mouse], dtype=np.intp)
        # Centres (for spatial effects), plus normalised 0..1 versions.
        self.cx = np.array([l.cx for l in leds], dtype=np.float32)
        self.cy = np.array([l.cy for l in leds], dtype=np.float32)
        self.width = max(l.x + l.w for l in leds)
        self.height = apex9_tkl.KEYBOARD_HEIGHT
        self.nx = self.cx / self.width
        self.ny = self.cy / self.height

        self.default_cell_to_led = self._default_cells()
        self.cell_to_led = self.default_cell_to_led.copy()
        self.calibrated = False
        self.calibration_file = calibration_file or calibration_path()
        self.load_calibration()

    # ------------------------------------------------------------------ cells
    def _default_cells(self) -> np.ndarray:
        """Nearest key in the same row for each of the 22x6 grid cells."""
        out = np.full(BITMAP_LEN, -1, dtype=np.intp)
        kb_w = apex9_tkl.KEYBOARD_WIDTH
        for r in range(GRID_ROWS):
            row_keys = [l for l in self.keyboard if l.row == r or (l.id == "enter" and r == 3)]
            for c in range(GRID_COLS):
                x = (c + 0.5) / GRID_COLS * kb_w
                best = min(row_keys, key=lambda l: (0 if l.x <= x < l.x + l.w else 1, abs(l.cx - x)))
                out[r * GRID_COLS + c] = best.index
        return out

    def cell_center(self, cell: int) -> tuple[float, float]:
        r, c = divmod(cell, GRID_COLS)
        return (c + 0.5) / GRID_COLS * apex9_tkl.KEYBOARD_WIDTH, r + 0.5

    def load_calibration(self) -> None:
        path = self.calibration_file
        if not path.exists():
            return
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            mapping = data["cells"]  # {"cell": "key_id" | null}
        except (OSError, ValueError, KeyError) as exc:
            log.warning("ignoring bad calibration %s: %s", path, exc)
            return
        self.apply_calibration({int(k): v for k, v in mapping.items()})

    def apply_calibration(self, cells: dict[int, str | None]) -> None:
        """``cells`` maps grid cell -> key id that lit up (None = nothing lit)."""
        result = self.default_cell_to_led.copy()
        for cell, kid in cells.items():
            if 0 <= cell < BITMAP_LEN:
                result[cell] = self.by_id[kid].index if kid in self.by_id else -1
        self.cell_to_led = result
        self.calibrated = True

    def save_calibration(self, cells: dict[int, str | None]) -> None:
        self.calibration_file.parent.mkdir(parents=True, exist_ok=True)
        self.calibration_file.write_text(
            json.dumps({"device": "apex9_tkl", "cells": {str(k): v for k, v in sorted(cells.items())}}, indent=1),
            encoding="utf-8",
        )
        self.apply_calibration(cells)

    def reset_calibration(self) -> None:
        if self.calibration_file.exists():
            self.calibration_file.unlink()
        self.cell_to_led = self.default_cell_to_led.copy()
        self.calibrated = False

    # ------------------------------------------------------------------ conversion
    def to_bitmap(self, colors_u8: np.ndarray) -> list[list[int]]:
        """(n_leds, 3) uint8 -> 132 [r, g, b] lists for GameSense."""
        padded = np.vstack([colors_u8, np.zeros((1, 3), dtype=np.uint8)])  # index -1 -> black
        return padded[self.cell_to_led].tolist()

    def to_mouse(self, colors_u8: np.ndarray) -> list[list[int]]:
        return colors_u8[self.mouse_idx].tolist()

    def expand(self, ids, strict: bool = False) -> list[str]:
        """Expand ``@group`` entries (see ``layout.groups``) into key ids."""
        from .groups import expand

        return expand(ids, self, strict=strict)

    def ids_to_mask(self, ids: list[str] | None) -> np.ndarray:
        """Key-id list (``@group`` names allowed) -> boolean LED mask (None = every LED)."""
        if ids is None:
            return np.ones(self.n, dtype=bool)
        m = np.zeros(self.n, dtype=bool)
        for kid in self.expand(ids):
            led = self.by_id.get(kid)
            if led is not None:
                m[led.index] = True
        return m


_default: Layout | None = None


def get_layout() -> Layout:
    global _default
    if _default is None:
        _default = Layout()
    return _default

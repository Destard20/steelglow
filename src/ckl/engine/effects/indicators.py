"""Status indicators: lock keys and CPU load."""
from __future__ import annotations

import numpy as np

from .base import Effect, Param, RenderContext, hex_to_rgb, palette

FUNCTION_ROW = [f"f{i}" for i in range(1, 13)]


class LockKeys(Effect):
    id, name, category = "lock_keys", "Lock-key indicators", "Indicator"
    description = 'Shows Caps/Scroll/Num Lock state on keys. Transparent when locks are off; keep near the top.'
    params = [
        Param("caps_color", "Caps Lock color", "color", "#ff0000"),
        Param("caps_keys", "Caps Lock lights", "choice", "caps key", choices=["caps key", "all letters", "whole keyboard"]),
        Param("scroll_color", "Scroll Lock color", "color", "#ffa000"),
        Param("num_color", "Num Lock color", "color", "#00ff40"),
        Param("num_key", "Num Lock shown on key", "choice", "none", choices=["none", "ins", "pause", "ss"]),
    ]

    def setup(self) -> None:
        L = self.layout
        letters = [l.index for l in L.keyboard if len(l.id) == 1 and l.id.isalpha()]
        target = self.p["caps_keys"]
        if target == "all letters":
            self.caps_idx = np.array(letters, dtype=np.intp)
        elif target == "whole keyboard":
            self.caps_idx = np.array([l.index for l in L.keyboard], dtype=np.intp)
        else:
            self.caps_idx = np.array([L.by_id["caps"].index], dtype=np.intp)

    def render(self, ctx: RenderContext):
        L = self.layout
        colors = np.zeros((self.n, 3), dtype=np.float32)
        alpha = self.zeros()
        if ctx.locks.get("caps"):
            colors[self.caps_idx] = hex_to_rgb(self.p["caps_color"])
            alpha[self.caps_idx] = 1.0
        if ctx.locks.get("scroll"):
            i = L.by_id["scrlk"].index
            colors[i], alpha[i] = hex_to_rgb(self.p["scroll_color"]), 1.0
        if ctx.locks.get("num") and self.p["num_key"] in L.by_id:
            i = L.by_id[self.p["num_key"]].index
            colors[i], alpha[i] = hex_to_rgb(self.p["num_color"]), 1.0
        return colors, alpha


class CpuLoad(Effect):
    """Bar graph of CPU usage across the layer's keys (F1-F12 when the layer covers everything)."""

    id, name, category = "cpu_load", "CPU load bar", "Indicator"
    description = "Bar graph of CPU usage across the layer's keys (F1-F12 when the layer covers everything)."
    params = [
        Param("colors", "Low → high colors", "colors", ["#00ff40", "#ffe000", "#ff0000"]),
        Param("background", "Unlit keys color", "color", "#000000"),
        Param("background_alpha", "Unlit keys opacity", "float", 0.0, 0.0, 1.0, 0.05),
        Param("smoothing", "Smoothing (s)", "float", 1.0, 0.0, 10.0, 0.1),
    ]

    def setup(self) -> None:
        L = self.layout
        if self.mask.all():
            idx = [L.by_id[k].index for k in FUNCTION_ROW]
        else:
            idx = sorted(np.flatnonzero(self.mask), key=lambda i: (L.cx[i], L.cy[i]))
        self.bar = np.array(idx, dtype=np.intp)
        self.value = 0.0
        pos = np.linspace(0, 1, len(self.bar)) if len(self.bar) > 1 else np.zeros(1)
        self.bar_colors = palette(self.p["colors"], pos)

    def render(self, ctx: RenderContext):
        s = float(self.p["smoothing"])
        k = 1.0 if s <= 0 else min(1.0, ctx.dt / s)
        self.value += (ctx.cpu - self.value) * k
        colors = self.full(hex_to_rgb(self.p["background"]))
        alpha = self.zeros()
        alpha[self.bar] = float(self.p["background_alpha"])
        n = len(self.bar)
        lit = self.value * n
        for j, i in enumerate(self.bar):
            frac = float(np.clip(lit - j, 0.0, 1.0))
            if frac > 0:
                colors[i] = self.bar_colors[j]
                alpha[i] = max(alpha[i], frac)
        return colors, alpha

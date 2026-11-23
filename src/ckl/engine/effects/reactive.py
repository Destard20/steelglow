"""Effects driven by key presses."""
from __future__ import annotations

import numpy as np

from .base import Effect, Param, RenderContext, hex_to_rgb, hsv_array


class Ripple(Effect):
    id, name, category, reactive = "ripple", "Ripple", "Reactive", True
    description = 'Expanding rings from each pressed key. Transparent elsewhere; use blend screen/add over a base.'
    params = [
        Param("rainbow", "Rainbow rings", "bool", False),
        Param("color", "Color", "color", "#ffffff"),
        Param("speed", "Speed (keys/s)", "float", 14.0, 2.0, 60.0, 0.5),
        Param("width", "Ring width (keys)", "float", 1.0, 0.3, 4.0, 0.1),
        Param("lifetime", "Lifetime (s)", "float", 0.8, 0.1, 4.0, 0.05),
    ]

    def setup(self) -> None:
        self.rings: list[tuple[float, float, float, np.ndarray]] = []  # (x, y, t0, color)

    def render(self, ctx: RenderContext):
        L = self.layout
        for idx, t0 in ctx.presses:
            color = hsv_array(np.array([t0 * 0.37 % 1.0]))[0] if self.p["rainbow"] else hex_to_rgb(self.p["color"])
            self.rings.append((float(L.cx[idx]), float(L.cy[idx]), t0, color))
        life, speed, width = float(self.p["lifetime"]), float(self.p["speed"]), float(self.p["width"])
        self.rings = [r for r in self.rings if ctx.t - r[2] < life]
        alpha = self.zeros()
        colors = np.zeros((self.n, 3), dtype=np.float32)
        for x, y, t0, color in self.rings:
            age = max(ctx.t - t0, 0.0)
            d = np.hypot(L.cx - x, L.cy - y)
            a = np.exp(-(((d - age * speed) / width) ** 2)) * (1.0 - age / life)
            stronger = a > alpha
            colors[stronger] = color
            alpha = np.maximum(alpha, a)
        return colors, alpha.astype(np.float32)


class KeyFade(Effect):
    id, name, category, reactive = "key_fade", "Key fade", "Reactive", True
    description = 'Pressed keys light up then fade. Transparent elsewhere.'
    params = [
        Param("rainbow", "Random color per press", "bool", False),
        Param("color", "Color", "color", "#ff00ff"),
        Param("duration", "Fade time (s)", "float", 0.7, 0.05, 5.0, 0.05),
        Param("hold", "Stay lit while held", "bool", True),
    ]

    def setup(self) -> None:
        self.level = np.zeros(self.n, dtype=np.float32)
        self.colors = np.zeros((self.n, 3), dtype=np.float32)
        self.rng = np.random.default_rng()

    def render(self, ctx: RenderContext):
        self.level = np.maximum(self.level - ctx.dt / float(self.p["duration"]), 0.0)
        for idx, _ in ctx.presses:
            self.level[idx] = 1.0
            self.colors[idx] = (hsv_array(np.array([self.rng.random()]))[0] if self.p["rainbow"]
                                else hex_to_rgb(self.p["color"]))
        if self.p["hold"]:
            for idx in ctx.held:
                self.level[idx] = 1.0
        return self.colors, self.level


class Heatmap(Effect):
    id, name, category, reactive = "heatmap", "Heatmap", "Reactive", True
    description = 'Keys warm up the more they are pressed and slowly cool down.'
    params = [
        Param("cold", "Cold color", "color", "#0010ff"),
        Param("hot", "Hot color", "color", "#ff1000"),
        Param("per_press", "Heat per press", "float", 0.15, 0.01, 1.0, 0.01),
        Param("half_life", "Cool-down half-life (s)", "float", 20.0, 0.5, 600.0, 0.5),
        Param("transparent_cold", "Cold keys are transparent", "bool", True),
    ]

    def setup(self) -> None:
        self.heat = np.zeros(self.n, dtype=np.float32)

    def render(self, ctx: RenderContext):
        self.heat *= 0.5 ** (ctx.dt / float(self.p["half_life"]))
        for idx, _ in ctx.presses:
            self.heat[idx] = min(1.0, self.heat[idx] + float(self.p["per_press"]))
        cold, hot = hex_to_rgb(self.p["cold"]), hex_to_rgb(self.p["hot"])
        h = self.heat[:, None]
        cols = cold * (1 - h) + hot * h
        alpha = np.clip(self.heat * 3, 0, 1) if self.p["transparent_cold"] else self.ones()
        return cols.astype(np.float32), alpha.astype(np.float32)

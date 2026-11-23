"""Clouds: soft puffy clouds drifting slowly across the upper part of the layout."""
from __future__ import annotations

import numpy as np

from .base import Effect, Param, RenderContext, palette


class Clouds(Effect):
    id, name = "clouds", "Clouds"
    category = "Ambient"
    description = ("Soft clouds drifting sideways through a band near the top. Bright centres, shaded "
                   "edges; transparent elsewhere, so put it over a sky/base layer.")
    params = [
        Param("color", "Cloud color", "color", "#e8f8ff"),
        Param("shade", "Cloud edge color", "color", "#80c0e0"),
        Param("density", "Density (higher = more solid)", "float", 1.0, 0.3, 4.0, 0.1),
        Param("count","Number of clouds", "int", 3, 1, 8, 1),
        Param("size", "Cloud size (keys)", "float", 2.2, 0.8, 6.0, 0.1),
        Param("speed", "Drift speed (keys/s)", "float", 0.4, 0.0, 5.0, 0.05),
        Param("top", "Band top (0 = top edge)", "float", 0.05, 0.0, 1.0, 0.05),
        Param("bottom", "Band bottom", "float", 0.4, 0.0, 1.0, 0.05),
        Param("direction", "Direction", "choice", "right", choices=["right", "left"]),
        Param("seed", "Cloud shapes (seed)", "int", 7, 0, 999, 1),
    ]

    def setup(self) -> None:
        L = self.layout
        rng = np.random.default_rng(int(self.p["seed"]))
        size = float(self.p["size"])
        n = int(self.p["count"])
        self.span = float(L.width) + 6 * size  # clouds wrap around fully off-screen
        top, bottom = sorted((float(self.p["top"]), float(self.p["bottom"])))
        # Each cloud = 3 to 4 overlapping puffs (dx, dy, radius) around a centre.
        self.clouds = []
        for i in range(n):
            x0 = (i + rng.uniform(0.15, 0.85)) / n * self.span
            y = (top + rng.uniform(0, 1) * (bottom - top)) * float(L.height)
            puffs = [(0.0, 0.0, size * rng.uniform(0.9, 1.1))]
            for _ in range(rng.integers(2, 4)):
                puffs.append((rng.uniform(-1.3, 1.3) * size, rng.uniform(-0.25, 0.25) * size,
                              size * rng.uniform(0.55, 0.85)))
            self.clouds.append((x0, y, puffs))
        self.sign = 1.0 if self.p["direction"] == "right" else -1.0

    def render(self, ctx: RenderContext):
        L = self.layout
        size = float(self.p["size"])
        alpha = self.zeros()
        drift = float(self.p["speed"]) * ctx.t * self.sign
        for x0, y, puffs in self.clouds:
            cx = np.mod(x0 + drift, self.span) - 3 * size
            for dx, dy, r in puffs:
                d2 = ((L.cx - cx - dx) ** 2 + ((L.cy - y - dy) * 1.6) ** 2) / (r * r)
                alpha = np.maximum(alpha, np.clip(1.0 - d2, 0.0, 1.0) ** 1.2)
        alpha = np.clip(alpha * float(self.p["density"]), 0.0, 1.0)
        cols = palette([self.p["shade"], self.p["color"]], np.clip(alpha * 1.4, 0, 1))
        return cols, alpha.astype(np.float32)

"""Sea swell: a rolling water surface along the bottom of the layout."""
from __future__ import annotations

import numpy as np

from .base import Effect, Param, RenderContext, hex_to_rgb, palette


class SeaSwell(Effect):
    id, name = "sea_swell", "Sea swell"
    category = "Ambient"
    description = ("Water rising from the bottom with a rolling wavy surface and a foam crest. "
                   "Transparent above the water, so a base layer shows as the sky/shallows.")
    params = [
        Param("colors", "Water colors (surface → deep)", "colors", ["#0030ff", "#000a80"]),
        Param("foam", "Foam crest color", "color", "#a0f0ff"),
        Param("foam_strength", "Foam strength", "float", 0.5, 0.0, 1.0, 0.05),
        Param("foam_width", "Foam width (fraction of height)", "float", 0.06, 0.01, 0.3, 0.01),
        Param("level", "Water level (fraction of height)", "float", 0.3, 0.0, 1.0, 0.02),
        Param("amplitude", "Wave height (fraction of height)", "float", 0.12, 0.0, 0.5, 0.01),
        Param("wavelength", "Wavelength (fraction of width)", "float", 0.8, 0.1, 4.0, 0.05),
        Param("speed", "Speed (waves/s)", "float", 0.15, 0.0, 2.0, 0.01),
        Param("chop", "Chop (secondary ripples)", "float", 0.35, 0.0, 1.0, 0.05),
        Param("softness", "Surface edge softness", "float", 0.06, 0.01, 0.3, 0.01),
        Param("direction", "Direction", "choice", "right", choices=["right", "left"]),
    ]

    def setup(self) -> None:
        L = self.layout
        self.x = (L.nx if self.p["direction"] == "right" else 1.0 - L.nx).astype(np.float32)
        self.h = (1.0 - L.ny).astype(np.float32)  # height above the bottom edge, 0..1
        self.foam_rgb = hex_to_rgb(self.p["foam"])

    def surface(self, t: float) -> np.ndarray:
        """Water surface height at each LED's x position."""
        lam = float(self.p["wavelength"])
        spd = float(self.p["speed"])
        chop = float(self.p["chop"])
        main = np.sin(2 * np.pi * (self.x / lam - spd * t))
        small = np.sin(2 * np.pi * (self.x / (lam * 0.43) + spd * 1.7 * t) + 1.3)
        wave = (main + chop * 0.5 * small) / (1.0 + chop * 0.5)
        return float(self.p["level"]) + float(self.p["amplitude"]) * wave

    def render(self, ctx: RenderContext):
        depth = self.surface(ctx.t) - self.h  # > 0 under water
        soft = float(self.p["softness"])
        alpha = np.clip((depth + soft) / (2 * soft), 0.0, 1.0).astype(np.float32)
        max_depth = max(float(self.p["level"]) + float(self.p["amplitude"]), 1e-3)
        cols = palette(self.p["colors"], np.clip(depth, 0.0, None) / max_depth)
        fw = float(self.p["foam_width"])
        foam = (np.exp(-((depth / fw) ** 2)) * float(self.p["foam_strength"])).astype(np.float32)[:, None]
        cols = cols * (1.0 - foam) + self.foam_rgb[None, :] * foam
        return cols.astype(np.float32), alpha

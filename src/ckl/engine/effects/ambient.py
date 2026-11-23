"""Time-based (non-reactive) effects."""
from __future__ import annotations

import math

import numpy as np

from .base import Effect, Param, RenderContext, hex_to_rgb, hsv_array, palette

DIRECTIONS = ["right", "left", "down", "up", "radial out", "radial in"]


class Solid(Effect):
    id, name = "solid", "Solid color"
    description = 'One flat color on every LED of the layer.'
    params = [Param("color", "Color", "color", "#00a0ff")]

    def render(self, ctx: RenderContext):
        return self.full(hex_to_rgb(self.p["color"])), self.ones()


class Paint(Effect):
    """Per-key static colors painted in the editor. Unpainted keys are transparent."""

    id, name = "paint", "Per-key paint"
    description = 'Static per-key colors. params.keys maps key ids or @groups to hex colors; later entries win. Unlisted keys are transparent.'
    params = [Param("keys", "Painted keys", "keycolors", {})]

    def setup(self) -> None:
        self.colors = np.zeros((self.n, 3), dtype=np.float32)
        self.alpha = np.zeros(self.n, dtype=np.float32)
        # Entries apply in order, so "@letters" followed by "w" lets the single key win.
        for kid, hexcol in self.p["keys"].items():
            for k in self.layout.expand([kid]):
                led = self.layout.by_id.get(k)
                if led is not None:
                    self.colors[led.index] = hex_to_rgb(hexcol)
                    self.alpha[led.index] = 1.0

    def render(self, ctx: RenderContext):
        return self.colors, self.alpha


class Gradient(Effect):
    id, name = "gradient", "Static gradient"
    description = 'Static gradient across the layout in a direction, through the listed colors.'
    params = [
        Param("colors", "Colors", "colors", ["#ff0080", "#00c0ff"]),
        Param("direction", "Direction", "choice", "right", choices=DIRECTIONS),
    ]

    def setup(self) -> None:
        self.cols = palette(self.p["colors"], self.projection(self.p["direction"]))

    def render(self, ctx: RenderContext):
        return self.cols, self.ones()


class Spectrum(Effect):
    id, name = "spectrum", "Spectrum cycle"
    description = 'Whole layer cycles through the hue wheel together.'
    params = [
        Param("speed", "Speed (cycles/s)", "float", 0.1, 0.01, 2.0, 0.01),
        Param("saturation", "Saturation", "float", 1.0, 0.0, 1.0, 0.05),
    ]

    def render(self, ctx: RenderContext):
        h = np.full(self.n, ctx.t * self.p["speed"], dtype=np.float32)
        return hsv_array(h, float(self.p["saturation"])), self.ones()


class Wave(Effect):
    id, name = "wave", "Wave"
    description = 'Moving bands of color (rainbow or custom palette, looping) sweeping in a direction.'
    params = [
        Param("rainbow", "Rainbow", "bool", True),
        Param("colors", "Colors (if not rainbow)", "colors", ["#ff0040", "#2000ff", "#00ffc0"]),
        Param("direction", "Direction", "choice", "right", choices=DIRECTIONS),
        Param("speed", "Speed (waves/s)", "float", 0.4, 0.02, 4.0, 0.02),
        Param("wavelength", "Wavelength (fraction of width)", "float", 1.0, 0.1, 4.0, 0.05),
    ]

    def setup(self) -> None:
        self.proj = self.projection(self.p["direction"])

    def render(self, ctx: RenderContext):
        phase = self.proj / float(self.p["wavelength"]) - ctx.t * float(self.p["speed"])
        if self.p["rainbow"]:
            cols = hsv_array(phase)
        else:
            cols = palette(self.p["colors"], phase, cyclic=True)
        return cols, self.ones()


class Breathing(Effect):
    id, name = "breathing", "Breathing"
    description = 'Fades in and out; cycles through the color list once per breath. fade_layer=true fades to transparent so lower layers show.'
    params = [
        Param("colors", "Colors (cycled each breath)", "colors", ["#ff2000", "#0040ff"]),
        Param("period", "Breath length (s)", "float", 4.0, 0.5, 20.0, 0.1),
        Param("min_brightness", "Minimum brightness", "float", 0.0, 0.0, 1.0, 0.05),
        Param("fade_layer", "Fade to transparent instead of black", "bool", False),
    ]

    def render(self, ctx: RenderContext):
        period = float(self.p["period"])
        cycle = int(ctx.t // period)
        cols = self.p["colors"] or ["#ffffff"]
        color = hex_to_rgb(cols[cycle % len(cols)])
        level = math.sin(math.pi * (ctx.t % period) / period) ** 2
        lo = float(self.p["min_brightness"])
        level = lo + (1 - lo) * level
        if self.p["fade_layer"]:
            return self.full(color), np.full(self.n, level, dtype=np.float32)
        return self.full(color * level), self.ones()


class Starlight(Effect):
    id, name = "starlight", "Starlight"
    description = 'Random keys twinkle on and fade out. Transparent elsewhere, good overlay.'
    params = [
        Param("random_color", "Random colors", "bool", True),
        Param("color", "Color (if not random)", "color", "#ffffff"),
        Param("rate", "Stars per second", "float", 8.0, 0.5, 60.0, 0.5),
        Param("fade", "Fade time (s)", "float", 1.2, 0.1, 6.0, 0.1),
    ]

    def setup(self) -> None:
        self.level = np.zeros(self.n, dtype=np.float32)
        self.colors = np.zeros((self.n, 3), dtype=np.float32)
        self.rng = np.random.default_rng()
        self.candidates = np.flatnonzero(self.mask)

    def render(self, ctx: RenderContext):
        self.level = np.maximum(self.level - ctx.dt / float(self.p["fade"]), 0.0)
        if len(self.candidates):
            spawn = self.rng.poisson(float(self.p["rate"]) * ctx.dt)
            for idx in self.rng.choice(self.candidates, size=min(spawn, len(self.candidates)), replace=False):
                self.level[idx] = 1.0
                self.colors[idx] = (hsv_array(np.array([self.rng.random()]))[0] if self.p["random_color"]
                                    else hex_to_rgb(self.p["color"]))
        return self.colors, self.level

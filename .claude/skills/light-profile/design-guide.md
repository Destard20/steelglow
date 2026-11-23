# Lighting design guide

## How a profile renders
- A profile is a stack of **layers**, drawn **first → last (bottom → top)**.
- Each layer = one effect + `keys` scope (omit/null = every key **and** the 3 mouse zones; or a list of
  key ids / `@groups`) + `blend` + `opacity` (0–1) + `enabled`.
- Every effect outputs a color and an **alpha** per LED. Some effects are opaque (solid, gradient, wave,
  spectrum, breathing without `fade_layer`). Others are transparent except where they draw: paint (only
  painted keys), ripple, key_fade, starlight, heatmap (with `transparent_cold`), lock_keys and cpu_load.
- Result per LED: `out = out·(1−a) + blend(out, color)·a`, with `a = alpha · opacity · in_scope`.
- `keyboard_brightness` and `mouse_brightness` scale the final result. The user's master brightness
  (set in the tray) multiplies on top of both.

### Blend modes
| mode | use for |
|---|---|
| normal | replacing what's below (bases, painted keys) |
| screen | soft glowing overlays (ripples, starlight, key fade): brightens without clipping harshly |
| add | strong glows / heat, can saturate to white |
| multiply | tinting or darkening a region (e.g. a dark `solid` over `@frow` at 0.5 opacity dims it) |
| max | "brightest wins" when combining two animated layers |

### Standard stack
1. **Base / ambience**: gradient, wave, breathing, spectrum or a dim solid. Usually covers everything.
2. **Role highlights**: `paint` with `@groups` and keys, or a scoped solid/breathing layer.
3. **Reactive overlay**: ripple, key_fade or heatmap (blend screen or add).
4. **Indicators on top**: `lock_keys` (always worth including), `cpu_load` for work profiles.

An opaque full-coverage layer above other layers hides them; the validator warns about that.

## Readability rules
- Highlighted keys need contrast with the base. Keep the base **dim and dark** (value ≈ 5–25 %, e.g.
  `#100020`, `#0a1a2a`) when you're highlighting keys, and use saturated, bright highlight colors.
- Use at most 3–4 role colors, each with a clear meaning. Use hue for the role and brightness for
  importance.
- LEDs exaggerate saturation and make dark colors look darker than on screen. Very dark colors
  (< `#080808`) read as off, and pastels look washed out. Pure white is very bright, so prefer
  `#ffffff` only for brief reactive flashes.
- Yellow and orange stay distinguishable on LEDs, but similar blues and purples blur together.
  Mixed warm and cool palettes read best.
- Motion: calm is about 0.05–0.2 waves/s or a breathing period of 5–8 s. Gentle is 0.2–0.5 waves/s.
  Energetic is 0.6–1.5 waves/s with ripples. Fast full-keyboard motion is tiring in work profiles.

## Mouse (Aerox 9, 3 zones: mouse1 front → mouse3 back)
- It is wireless and the user cares about battery. Animated mouse lighting costs both radio updates
  (capped at 10/s by default) and LED power.
- Options:
  - Static colors on the mouse (very cheap: only re-sent when the color changes).
  - `mouse_brightness` 0.3–0.5 for dim.
  - `mouse_brightness` 0 for off.
- To give the mouse its own look, add a layer with `"keys": ["@mouse"]`, and keep the mouse out of
  busy keyboard layers by scoping those to `["@keyboard"]`.

## Recipes
**Vibe**
- Synthwave: gradient `#ff00aa → #6a00ff → #00e5ff` (direction right), slow wave overlay at opacity
  0.35 with blend screen, ripples `#ff66cc` on screen.
- Cozy fireplace: base `#2a0800`. A breathing layer `#ff4000, #ff7a00` (period 3–4, fade_layer) over
  `@row4 @row5`. Starlight `#ffb000` with rate 4–6 and fade 1.5 for embers.
- Ocean: gradient `#001a33 → #004466 → #00a0a0` going down, plus a slow wave of blues at opacity 0.4.
- Forest: gradient `#002200 → #0a4d00 → #3a7d00` with starlight `#ccff66` at a low rate.
- Night / low light: everything at `keyboard_brightness` 0.3–0.5, warm amber, no motion, mouse off.

**Game** (roles stay consistent across games so the user builds muscle memory)
- Base: a dim solid or very slow gradient in the game's identity color.
- Movement (WASD / ESDF / arrows): bright red or the game's signature color.
- Core abilities/skills (QWERT, 1–5 …): amber/orange.
- Consumables/potions/items: green.
- Utility/UI (Tab, M, I, Esc, map, inventory): cool blue/cyan, dimmer.
- Ping/communication (push-to-talk, chat): magenta.
- Add a reactive key_fade in a contrasting color (duration 0.3–0.5 s) so presses are visible on top.
- For competitive shooters, keep motion off the base so nothing distracts. Note that the profile's
  `reactive: false` setting turns off the keyboard hook if the user worries about anti-cheat.
- ARPGs such as PoE2 and Diablo: highlight skill keys and the potion row (1–5). The user's mouse side
  buttons send Q/2/3/E/5/6/R/8/9, so those keys matter.

**Task**
- Coding/writing: a calm gradient or static palette, a heatmap (half-life 30–60 s, blend add, opacity
  0.6–0.8), `cpu_load` on the F-row, and `lock_keys` lighting all letters for Caps Lock.
- Streaming: brand colors, a gentle wave, and specific hotkeys (F13+ don't exist here; use the F-row or
  nav cluster) painted in distinct colors.
- Video calls / focus: dim static, no reactive effects, mouse dim or off.
- Music: spectrum or a rainbow wave with a moderate speed, plus ripples.

## Writing a new effect
Create `src/ckl/engine/effects/<name>.py`. Any `Effect` subclass with an `id` registers itself
automatically and appears in the editor, in `ckl profile schema` and in the tests.

```python
"""<What it looks like>."""
from __future__ import annotations

import numpy as np

from .base import Effect, Param, RenderContext, hex_to_rgb, hsv_array, palette


class Fire(Effect):
    id, name = "fire", "Fire"          # id: unique snake_case, used in profile JSON
    category = "Ambient"               # Ambient | Reactive | Indicator (editor menu)
    reactive = False                   # True if it uses ctx.presses / ctx.held
    description = "Flickering flames rising from the bottom row."
    params = [                         # kinds: color, colors, float, int, choice, bool, keycolors
        Param("colors", "Flame colors (cool → hot)", "colors", ["#300000", "#ff3000", "#ffb000"]),
        Param("speed", "Flicker speed", "float", 1.0, 0.1, 5.0, 0.1),   # default, min, max, step
        Param("height", "Flame height", "float", 0.6, 0.1, 1.0, 0.05),
    ]

    def setup(self) -> None:           # precompute; self.p has params merged with defaults
        self.rng = np.random.default_rng()
        self.heat = np.zeros(self.n, dtype=np.float32)

    def render(self, ctx: RenderContext):
        L = self.layout                # L.nx / L.ny: 0..1 LED centres (y grows downward); L.n LEDs
        target = np.clip((L.ny - (1 - self.p["height"])) / self.p["height"], 0, 1)
        noise = self.rng.random(self.n).astype(np.float32)
        k = min(1.0, ctx.dt * 8 * self.p["speed"])
        self.heat += (target * (0.6 + 0.4 * noise) - self.heat) * k
        colors = palette(self.p["colors"], self.heat)      # (n, 3) float 0..1
        return colors, np.ones(self.n, dtype=np.float32)   # alpha (n,) 0..1
```

Rules:
- `render` must return `(colors (n,3) float32 0..1, alpha (n,) float32 0..1)` and stay fast, because it
  runs 30 times a second. Use numpy over all LEDs and avoid Python loops over keys where possible.
- Keep state in `setup()`. The layer is rebuilt whenever the profile changes.
- Useful context: `ctx.t` (seconds), `ctx.dt`, `ctx.presses` (list of `(led_index, t)` since the
  last frame), `ctx.held` (set of LED indices), `ctx.locks`, `ctx.cpu`. The layout provides
  `cx/cy` (key units), `nx/ny` (0..1), `by_id`, `keyboard`, `mouse` and `mouse_idx`.
- `self.mask` is the layer's key scope (bool per LED), if the effect needs it, as in `cpu_load`.
- Tests: `tests/test_engine.py::test_every_effect_renders_valid_output` checks every registered effect
  automatically. Add a focused test to `tests/test_engine.py` when the behavior matters (e.g. a
  reactive effect lights the pressed key). Run `.venv\Scripts\python -m pytest -q`.
- The running tray app loads effect code at startup. `ckl profile preview` notices when a profile
  uses an effect the running app doesn't know and restarts the app by itself. After *editing* an
  existing effect's code, run `ckl app restart` yourself.

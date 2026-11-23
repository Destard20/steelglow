"""Effect base class, parameter schema and color helpers."""
from __future__ import annotations

import colorsys
from dataclasses import dataclass, field
from typing import Any, ClassVar

import numpy as np

from ...layout import Layout


@dataclass
class Param:
    key: str
    label: str
    kind: str  # color | colors | float | int | choice | bool | keycolors
    default: Any
    min: float | None = None
    max: float | None = None
    step: float | None = None
    choices: list[str] = field(default_factory=list)


@dataclass
class RenderContext:
    t: float  # seconds since engine start
    dt: float  # seconds since previous frame
    layout: Layout
    presses: list[tuple[int, float]] = field(default_factory=list)  # (led index, time) since last frame
    held: set[int] = field(default_factory=set)
    locks: dict[str, bool] = field(default_factory=dict)  # caps / num / scroll
    cpu: float = 0.0  # 0..1


def hex_to_rgb(value: str | list | tuple) -> np.ndarray:
    if isinstance(value, (list, tuple)):
        return np.asarray(value[:3], dtype=np.float32) / (255.0 if max(value[:3]) > 1 else 1.0)
    s = value.lstrip("#")
    return np.array([int(s[i : i + 2], 16) for i in (0, 2, 4)], dtype=np.float32) / 255.0


def rgb_to_hex(rgb) -> str:
    r, g, b = (int(round(float(v) * 255)) for v in rgb[:3])
    return f"#{r:02x}{g:02x}{b:02x}"


def hsv_array(h: np.ndarray, s: float = 1.0, v: float = 1.0) -> np.ndarray:
    """Vectorised HSV -> RGB for an array of hues in [0, 1)."""
    h = np.mod(h, 1.0) * 6.0
    i = np.floor(h).astype(int) % 6
    f = h - np.floor(h)
    p = np.full_like(h, v * (1 - s))
    q = v * (1 - s * f)
    t = v * (1 - s * (1 - f))
    vv = np.full_like(h, v)
    r = np.choose(i, [vv, q, p, p, t, vv])
    g = np.choose(i, [t, vv, vv, q, p, p])
    b = np.choose(i, [p, p, t, vv, vv, q])
    return np.stack([r, g, b], axis=-1).astype(np.float32)


def hue_rgb(h: float) -> np.ndarray:
    return np.array(colorsys.hsv_to_rgb(h % 1.0, 1.0, 1.0), dtype=np.float32)


def palette(stops: list[str], pos: np.ndarray, cyclic: bool = False) -> np.ndarray:
    """Interpolate a list of hex colors at positions ``pos`` (0..1)."""
    cols = np.stack([hex_to_rgb(c) for c in stops]) if stops else np.ones((1, 3), np.float32)
    if cyclic:
        cols = np.vstack([cols, cols[:1]])
        pos = np.mod(pos, 1.0)
    else:
        pos = np.clip(pos, 0.0, 1.0)
    if len(cols) == 1:
        return np.repeat(cols, len(pos), axis=0)
    x = pos * (len(cols) - 1)
    i0 = np.clip(np.floor(x).astype(int), 0, len(cols) - 2)
    f = (x - i0)[:, None]
    return (cols[i0] * (1 - f) + cols[i0 + 1] * f).astype(np.float32)


EFFECTS: dict[str, type["Effect"]] = {}  # id -> class, filled automatically by subclassing


class Effect:
    """Base class. Subclasses with a non-empty ``id`` register themselves in ``EFFECTS``.

    To add an effect, drop a module into ``ckl/engine/effects/`` with a subclass: it is imported
    automatically and shows up in the editor, ``ckl profile schema`` and the test suite.
    """

    id: ClassVar[str] = ""
    name: ClassVar[str] = ""
    description: ClassVar[str] = ""
    category: ClassVar[str] = "Ambient"  # Ambient | Reactive | Indicator (editor menu grouping)
    reactive: ClassVar[bool] = False  # needs key presses
    params: ClassVar[list[Param]] = []

    def __init_subclass__(cls, **kwargs) -> None:
        super().__init_subclass__(**kwargs)
        if cls.id:
            if cls.id in EFFECTS and EFFECTS[cls.id].__qualname__ != cls.__qualname__:
                raise ValueError(f"duplicate effect id {cls.id!r}: {cls.__qualname__} vs {EFFECTS[cls.id].__qualname__}")
            EFFECTS[cls.id] = cls

    def __init__(self, layout: Layout, params: dict | None = None, mask: np.ndarray | None = None) -> None:
        self.layout = layout
        self.n = layout.n
        self.mask = mask if mask is not None else np.ones(layout.n, dtype=bool)
        self.p = self.defaults()
        if params:
            self.p.update({k: v for k, v in params.items() if k in self.p})
        self.setup()

    @classmethod
    def defaults(cls) -> dict:
        return {pr.key: (list(pr.default) if isinstance(pr.default, list) else
                         dict(pr.default) if isinstance(pr.default, dict) else pr.default) for pr in cls.params}

    def setup(self) -> None:
        """Hook for subclasses to precompute state."""

    def render(self, ctx: RenderContext) -> tuple[np.ndarray, np.ndarray]:
        """Return (colors (n, 3) float 0..1, alpha (n,) float 0..1)."""
        raise NotImplementedError

    # helpers
    def full(self, rgb) -> np.ndarray:
        return np.repeat(np.asarray(rgb, dtype=np.float32)[None, :], self.n, axis=0)

    def ones(self) -> np.ndarray:
        return np.ones(self.n, dtype=np.float32)

    def zeros(self) -> np.ndarray:
        return np.zeros(self.n, dtype=np.float32)

    def projection(self, direction: str) -> np.ndarray:
        """0..1 coordinate of each LED along a direction."""
        L = self.layout
        if direction == "left":
            return 1.0 - L.nx
        if direction == "down":
            return L.ny
        if direction == "up":
            return 1.0 - L.ny
        if direction in ("radial out", "radial in"):
            dx = (L.cx - L.width * 0.42) / L.width
            dy = (L.cy - L.height / 2) / L.width
            d = np.sqrt(dx * dx + dy * dy)
            d = d / max(float(d.max()), 1e-6)
            return d if direction == "radial out" else 1.0 - d
        return L.nx.copy()  # "right"

"""Layers and the compositor."""
from __future__ import annotations

import copy
from dataclasses import asdict, dataclass, field

import numpy as np

from ..layout import Layout
from .effects import EFFECTS, Effect, RenderContext

BLEND_MODES = ["normal", "add", "multiply", "screen", "max"]


@dataclass
class LayerConfig:
    """Serializable description of one layer."""

    effect: str
    params: dict = field(default_factory=dict)
    keys: list[str] | None = None  # None = every LED (keyboard + mouse)
    blend: str = "normal"
    opacity: float = 1.0
    enabled: bool = True
    name: str = ""

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "LayerConfig":
        return cls(
            effect=d["effect"],
            params=dict(d.get("params") or {}),
            keys=list(d["keys"]) if d.get("keys") is not None else None,
            blend=d.get("blend", "normal"),
            opacity=float(d.get("opacity", 1.0)),
            enabled=bool(d.get("enabled", True)),
            name=d.get("name", ""),
        )

    def display_name(self) -> str:
        if self.name:
            return self.name
        cls = EFFECTS.get(self.effect)
        return cls.name if cls else self.effect

    def clone(self) -> "LayerConfig":
        return copy.deepcopy(self)


class Layer:
    def __init__(self, cfg: LayerConfig, layout: Layout) -> None:
        self.cfg = cfg
        self.mask = layout.ids_to_mask(cfg.keys)
        cls = EFFECTS.get(cfg.effect)
        if cls is None:
            raise KeyError(f"unknown effect {cfg.effect!r}")
        self.effect: Effect = cls(layout, cfg.params, self.mask)

    @property
    def reactive(self) -> bool:
        return self.effect.reactive


def blend(base: np.ndarray, top: np.ndarray, mode: str) -> np.ndarray:
    if mode == "add":
        return np.minimum(base + top, 1.0)
    if mode == "multiply":
        return base * top
    if mode == "screen":
        return 1.0 - (1.0 - base) * (1.0 - top)
    if mode == "max":
        return np.maximum(base, top)
    return top


def composite(layers: list[Layer], ctx: RenderContext) -> np.ndarray:
    """Render layers bottom -> top. Returns (n, 3) float32 in 0..1."""
    out = np.zeros((ctx.layout.n, 3), dtype=np.float32)
    for layer in layers:
        if not layer.cfg.enabled or layer.cfg.opacity <= 0:
            continue
        colors, alpha = layer.effect.render(ctx)
        a = (np.clip(alpha, 0.0, 1.0) * layer.mask * float(layer.cfg.opacity))[:, None]
        out = out * (1.0 - a) + blend(out, np.clip(colors, 0.0, 1.0), layer.cfg.blend) * a
    return out.astype(np.float32)


def to_u8(colors: np.ndarray, brightness: float | np.ndarray = 1.0) -> np.ndarray:
    """``brightness`` is a scalar or an (n, 1) per-LED level array."""
    return np.clip(colors * (255.0 * np.asarray(brightness, dtype=np.float32)) + 0.5, 0, 255).astype(np.uint8)

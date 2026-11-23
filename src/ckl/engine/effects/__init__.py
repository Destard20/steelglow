"""Effect registry. Every module in this package is imported, and every ``Effect`` subclass with an
``id`` registers itself in ``EFFECTS`` (see ``base.Effect.__init_subclass__``)."""
import importlib
import pkgutil

from .base import EFFECTS, Effect, Param, RenderContext, hex_to_rgb, rgb_to_hex

for _mod in sorted(pkgutil.iter_modules(__path__), key=lambda m: m.name):
    if _mod.name != "base" and not _mod.name.startswith("_"):
        importlib.import_module(f"{__name__}.{_mod.name}")

__all__ = ["EFFECTS", "Effect", "Param", "RenderContext", "hex_to_rgb", "rgb_to_hex"]

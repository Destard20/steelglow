"""Validation for profile JSON (hand-written or generated). Errors break loading or rendering;
warnings flag things that load fine but probably aren't what the author meant."""
from __future__ import annotations

import re
from dataclasses import dataclass

from ..engine.effects import EFFECTS
from ..engine.layer import BLEND_MODES
from ..layout.groups import resolve_group

CATEGORIES = ["vibe", "game", "task", "other"]
HEX = re.compile(r"^#[0-9a-fA-F]{6}$")
TOP_KEYS = {"name", "description", "category", "tags", "keyboard_brightness", "mouse_brightness",
            "brightness", "reactive", "layers"}
LAYER_KEYS = {"effect", "params", "keys", "blend", "opacity", "enabled", "name"}
# Effects that paint every LED of their layer opaquely (so a full-coverage one hides what is below).
OPAQUE_EFFECTS = {"solid", "gradient", "wave", "spectrum"}


@dataclass
class Issue:
    level: str  # "error" | "warning"
    path: str
    message: str

    def __str__(self) -> str:
        return f"{self.level.upper():7} {self.path}: {self.message}"


def _is_num(v) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def _check_key(kid, layout, path, out: list[Issue]) -> None:
    if not isinstance(kid, str):
        out.append(Issue("error", path, f"key must be a string, got {kid!r}"))
    elif kid.startswith("@"):
        try:
            resolve_group(kid[1:], layout)
        except KeyError as exc:
            out.append(Issue("error", path, str(exc).strip("'\"")))
    elif kid not in layout.by_id:
        out.append(Issue("error", path, f"unknown key id {kid!r} (see `ckl profile schema`)"))


def _check_param(p, value, layout, path, out: list[Issue]) -> None:
    k = p.kind
    if k == "color":
        if not (isinstance(value, str) and HEX.match(value)):
            out.append(Issue("error", path, f"expected '#rrggbb' color, got {value!r}"))
    elif k == "colors":
        if not isinstance(value, list) or not value:
            out.append(Issue("error", path, "expected a non-empty list of '#rrggbb' colors"))
        else:
            for i, c in enumerate(value):
                if not (isinstance(c, str) and HEX.match(c)):
                    out.append(Issue("error", f"{path}[{i}]", f"expected '#rrggbb' color, got {c!r}"))
    elif k in ("float", "int"):
        if not _is_num(value):
            out.append(Issue("error", path, f"expected a number, got {value!r}"))
        elif (p.min is not None and value < p.min) or (p.max is not None and value > p.max):
            out.append(Issue("error", path, f"{value} is outside {p.min}..{p.max}"))
    elif k == "bool":
        if not isinstance(value, bool):
            out.append(Issue("error", path, f"expected true/false, got {value!r}"))
    elif k == "choice":
        if value not in p.choices:
            out.append(Issue("error", path, f"{value!r} is not one of {p.choices}"))
    elif k == "keycolors":
        if not isinstance(value, dict):
            out.append(Issue("error", path, "expected an object mapping key ids/@groups to '#rrggbb'"))
        else:
            for kid, c in value.items():
                _check_key(kid, layout, f"{path}.{kid}", out)
                if not (isinstance(c, str) and HEX.match(c)):
                    out.append(Issue("error", f"{path}.{kid}", f"expected '#rrggbb' color, got {c!r}"))


def validate(data, layout=None) -> list[Issue]:
    if layout is None:
        from ..layout import get_layout

        layout = get_layout()
    out: list[Issue] = []
    if not isinstance(data, dict):
        return [Issue("error", "$", "profile must be a JSON object")]
    name = data.get("name")
    if not isinstance(name, str) or not name.strip():
        out.append(Issue("error", "name", "profile needs a non-empty name"))
    for k in data:
        if k not in TOP_KEYS:
            out.append(Issue("warning", k, "unknown field (ignored)"))
    cat = data.get("category", "other")
    if cat not in CATEGORIES:
        out.append(Issue("warning", "category", f"{cat!r} is not one of {CATEGORIES}"))
    if "tags" in data and not (isinstance(data["tags"], list) and all(isinstance(t, str) for t in data["tags"])):
        out.append(Issue("error", "tags", "expected a list of strings"))
    for k in ("keyboard_brightness", "mouse_brightness", "brightness"):
        if k in data and not (_is_num(data[k]) and 0 <= data[k] <= 1):
            out.append(Issue("error", k, "expected a number between 0 and 1"))
    if "reactive" in data and not isinstance(data["reactive"], bool):
        out.append(Issue("error", "reactive", "expected true/false"))

    layers = data.get("layers")
    if not isinstance(layers, list) or not layers:
        out.append(Issue("error", "layers", "expected a non-empty list of layers"))
        return out

    any_reactive = False
    for i, layer in enumerate(layers):
        lp = f"layers[{i}]"
        if not isinstance(layer, dict):
            out.append(Issue("error", lp, "layer must be an object"))
            continue
        for k in layer:
            if k not in LAYER_KEYS:
                out.append(Issue("warning", f"{lp}.{k}", "unknown field (ignored)"))
        eid = layer.get("effect")
        cls = EFFECTS.get(eid)
        if cls is None:
            out.append(Issue("error", f"{lp}.effect", f"unknown effect {eid!r}; known: {sorted(EFFECTS)}"))
            continue
        any_reactive |= cls.reactive and layer.get("enabled", True)
        params = layer.get("params", {})
        if not isinstance(params, dict):
            out.append(Issue("error", f"{lp}.params", "expected an object"))
            params = {}
        schema = {p.key: p for p in cls.params}
        for k, v in params.items():
            if k not in schema:
                out.append(Issue("warning", f"{lp}.params.{k}", f"'{eid}' has no parameter {k!r} (ignored); "
                                                                f"valid: {sorted(schema)}"))
            else:
                _check_param(schema[k], v, layout, f"{lp}.params.{k}", out)
        keys = layer.get("keys")
        if keys is not None:
            if not isinstance(keys, list):
                out.append(Issue("error", f"{lp}.keys", "expected null (everything) or a list of key ids/@groups"))
            else:
                if not keys:
                    out.append(Issue("warning", f"{lp}.keys", "empty key list: this layer shows nothing"))
                for j, kid in enumerate(keys):
                    _check_key(kid, layout, f"{lp}.keys[{j}]", out)
        blend = layer.get("blend", "normal")
        if blend not in BLEND_MODES:
            out.append(Issue("error", f"{lp}.blend", f"{blend!r} is not one of {BLEND_MODES}"))
        op = layer.get("opacity", 1.0)
        if not (_is_num(op) and 0 <= op <= 1):
            out.append(Issue("error", f"{lp}.opacity", "expected a number between 0 and 1"))
        if "enabled" in layer and not isinstance(layer["enabled"], bool):
            out.append(Issue("error", f"{lp}.enabled", "expected true/false"))
        if (i > 0 and eid in OPAQUE_EFFECTS and keys is None and blend == "normal" and op == 1
                and layer.get("enabled", True)):
            out.append(Issue("warning", lp, f"'{eid}' covers every LED at full opacity with blend 'normal', "
                                            "so all layers below it are hidden"))
    if any_reactive and data.get("reactive") is False:
        out.append(Issue("warning", "reactive", "profile has reactive layers but reactive=false, so they never fire"))
    return out


def errors(issues: list[Issue]) -> list[Issue]:
    return [i for i in issues if i.level == "error"]

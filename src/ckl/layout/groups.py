"""Named key groups, usable in profiles as ``"@name"`` wherever a key id is accepted.

Static groups list key ids. Dynamic groups (``@all``, ``@keyboard``, ``@row0``…``@row5``) are
resolved against the layout.
"""
from __future__ import annotations

STATIC_GROUPS: dict[str, list[str]] = {
    "wasd": ["w", "a", "s", "d"],
    "letters": list("qwertyuiopasdfghjklzxcvbnm"),
    "numbers": [str(i) for i in range(1, 10)] + ["0"],
    "frow": [f"f{i}" for i in range(1, 13)],
    "arrows": ["up", "down", "left", "right"],
    "nav": ["ins", "home", "pgup", "del", "end", "pgdn", "prtsc", "scrlk", "pause"],
    "mods": ["lshift", "rshift", "lctrl", "rctrl", "lalt", "ralt", "lwin", "menu", "ss", "caps", "tab"],
    "punct": ["grave", "minus", "equal", "lbracket", "rbracket", "semicolon", "quote", "hash", "iso",
              "comma", "period", "slash"],
    "mouse": ["mouse1", "mouse2", "mouse3"],
}

DYNAMIC_GROUPS = ["all", "keyboard"] + [f"row{i}" for i in range(6)]

# Labels for the editor's quick-select buttons.
QUICK_SELECT = {
    "WASD": "wasd", "Letters": "letters", "Numbers": "numbers", "F-row": "frow", "Arrows": "arrows",
    "Nav": "nav", "Mods": "mods", "Mouse": "mouse",
}


def group_names() -> list[str]:
    return list(STATIC_GROUPS) + DYNAMIC_GROUPS


def resolve_group(name: str, layout) -> list[str]:
    """Key ids of group ``name`` (without the ``@``). Raises KeyError for unknown groups."""
    name = name.lower()
    if name in STATIC_GROUPS:
        return list(STATIC_GROUPS[name])
    if name == "all":
        return [l.id for l in layout.leds]
    if name == "keyboard":
        return [l.id for l in layout.keyboard]
    if name.startswith("row") and name[3:].isdigit():
        r = int(name[3:])
        if 0 <= r <= 5:
            return [l.id for l in layout.keyboard if l.row == r]
    raise KeyError(f"unknown key group '@{name}'")


def expand(ids, layout, strict: bool = False) -> list[str]:
    """Expand ``@group`` entries; keeps order, removes duplicates."""
    out: list[str] = []
    seen: set[str] = set()
    for kid in ids:
        if isinstance(kid, str) and kid.startswith("@"):
            try:
                members = resolve_group(kid[1:], layout)
            except KeyError:
                if strict:
                    raise
                continue
        else:
            members = [kid]
        for m in members:
            if m not in seen:
                seen.add(m)
                out.append(m)
    return out

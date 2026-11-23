"""Physical layout of the SteelSeries Apex 9 TKL (ISO, Italian legends) + Aerox 9 mouse zones.

Each row lists (id, label, scan_code, width_u). ``None`` as id inserts a horizontal gap of
``width_u`` units. Scan codes are Windows set-1 codes; extended keys carry 0xE000.
Positions are in key units (1u = one standard key).
"""
from __future__ import annotations

E = 0xE000  # extended-key flag

# fmt: off
ROWS: list[tuple[float, list[tuple]]] = [
    (0.0, [
        ("esc", "Esc", 0x01, 1), (None, "", None, 1),
        ("f1", "F1", 0x3B, 1), ("f2", "F2", 0x3C, 1), ("f3", "F3", 0x3D, 1), ("f4", "F4", 0x3E, 1), (None, "", None, 0.5),
        ("f5", "F5", 0x3F, 1), ("f6", "F6", 0x40, 1), ("f7", "F7", 0x41, 1), ("f8", "F8", 0x42, 1), (None, "", None, 0.5),
        ("f9", "F9", 0x43, 1), ("f10", "F10", 0x44, 1), ("f11", "F11", 0x57, 1), ("f12", "F12", 0x58, 1), (None, "", None, 0.25),
        ("prtsc", "Stamp", E | 0x37, 1), ("scrlk", "Bloc Scorr", 0x46, 1), ("pause", "Pausa", 0x45, 1),
    ]),
    (1.25, [
        ("grave", "\\", 0x29, 1), ("1", "1", 0x02, 1), ("2", "2", 0x03, 1), ("3", "3", 0x04, 1), ("4", "4", 0x05, 1),
        ("5", "5", 0x06, 1), ("6", "6", 0x07, 1), ("7", "7", 0x08, 1), ("8", "8", 0x09, 1), ("9", "9", 0x0A, 1),
        ("0", "0", 0x0B, 1), ("minus", "'", 0x0C, 1), ("equal", "ì", 0x0D, 1), ("backspace", "⟵", 0x0E, 2),
        (None, "", None, 0.25),
        ("ins", "Ins", E | 0x52, 1), ("home", "Home", E | 0x47, 1), ("pgup", "PgSu", E | 0x49, 1),
    ]),
    (2.25, [
        ("tab", "Tab", 0x0F, 1.5), ("q", "Q", 0x10, 1), ("w", "W", 0x11, 1), ("e", "E", 0x12, 1), ("r", "R", 0x13, 1),
        ("t", "T", 0x14, 1), ("y", "Y", 0x15, 1), ("u", "U", 0x16, 1), ("i", "I", 0x17, 1), ("o", "O", 0x18, 1),
        ("p", "P", 0x19, 1), ("lbracket", "è", 0x1A, 1), ("rbracket", "+", 0x1B, 1), ("enter", "Invio", 0x1C, 1.5),
        (None, "", None, 0.25),
        ("del", "Canc", E | 0x53, 1), ("end", "Fine", E | 0x4F, 1), ("pgdn", "PgGiù", E | 0x51, 1),
    ]),
    (3.25, [
        ("caps", "Bloc Maiusc", 0x3A, 1.75), ("a", "A", 0x1E, 1), ("s", "S", 0x1F, 1), ("d", "D", 0x20, 1),
        ("f", "F", 0x21, 1), ("g", "G", 0x22, 1), ("h", "H", 0x23, 1), ("j", "J", 0x24, 1), ("k", "K", 0x25, 1),
        ("l", "L", 0x26, 1), ("semicolon", "ò", 0x27, 1), ("quote", "à", 0x28, 1), ("hash", "ù", 0x2B, 1),
    ]),
    (4.25, [
        ("lshift", "Shift", 0x2A, 1.25), ("iso", "<", 0x56, 1), ("z", "Z", 0x2C, 1), ("x", "X", 0x2D, 1),
        ("c", "C", 0x2E, 1), ("v", "V", 0x2F, 1), ("b", "B", 0x30, 1), ("n", "N", 0x31, 1), ("m", "M", 0x32, 1),
        ("comma", ",", 0x33, 1), ("period", ".", 0x34, 1), ("slash", "-", 0x35, 1), ("rshift", "Shift", 0x36, 2.75),
        (None, "", None, 1.25), ("up", "↑", E | 0x48, 1),
    ]),
    (5.25, [
        ("lctrl", "Ctrl", 0x1D, 1.25), ("lwin", "Win", E | 0x5B, 1.25), ("lalt", "Alt", 0x38, 1.25),
        ("space", "", 0x39, 6.25), ("ralt", "AltGr", E | 0x38, 1.25), ("ss", "SS", None, 1.25),
        ("menu", "Menu", E | 0x5D, 1.25), ("rctrl", "Ctrl", E | 0x1D, 1.25), (None, "", None, 0.25),
        ("left", "←", E | 0x4B, 1), ("down", "↓", E | 0x50, 1), ("right", "→", E | 0x4D, 1),
    ]),
]
# fmt: on

KEYBOARD_WIDTH = 18.25

# ISO Enter is a "mirrored P": 1.5u wide on the Tab row (x 13.5-15), 1.25u wide on the
# Caps row, where it starts right after the ù key (Caps 1.75u + 12 keys = 13.75).
ISO_ENTER_LOWER_X = 13.75
KEYBOARD_HEIGHT = 6.25

# Aerox 9 Wireless RGB zones, drawn to the right of the keyboard (front -> back).
MOUSE_LEDS = [
    ("mouse1", "Mouse 1", 20.0, 2.25),
    ("mouse2", "Mouse 2", 20.0, 3.25),
    ("mouse3", "Mouse 3", 20.0, 4.25),
]

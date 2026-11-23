"""Profiles (stacks of layers) and app settings, stored as JSON under %APPDATA%."""
from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from pathlib import Path

from ..engine.layer import LayerConfig
from ..paths import data_dir, profiles_dir

log = logging.getLogger(__name__)


@dataclass
class Profile:
    name: str
    layers: list[LayerConfig] = field(default_factory=list)
    keyboard_brightness: float = 1.0
    mouse_brightness: float = 1.0  # 0 = mouse LEDs off (and no wireless lighting updates)
    reactive: bool = True  # listen to key presses (turn off for anti-cheat-sensitive games)
    description: str = ""
    category: str = "other"  # vibe | game | task | other
    tags: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        d = {
            "name": self.name,
            "description": self.description,
            "category": self.category,
            "tags": list(self.tags),
            "keyboard_brightness": self.keyboard_brightness,
            "mouse_brightness": self.mouse_brightness,
            "reactive": self.reactive,
            "layers": [l.to_dict() for l in self.layers],
        }
        return d

    @classmethod
    def from_dict(cls, d: dict) -> "Profile":
        legacy = float(d.get("brightness", 1.0))  # v0.1 had a single brightness value
        return cls(
            name=d["name"],
            layers=[LayerConfig.from_dict(x) for x in d.get("layers", [])],
            keyboard_brightness=float(d.get("keyboard_brightness", legacy)),
            mouse_brightness=float(d.get("mouse_brightness", legacy)),
            reactive=bool(d.get("reactive", True)),
            description=str(d.get("description", "")),
            category=str(d.get("category", "other")),
            tags=[str(t) for t in d.get("tags", [])],
        )


@dataclass
class AppRule:
    exe: str  # e.g. "cs2.exe" (case-insensitive)
    profile: str

    def matches(self, exe_name: str | None) -> bool:
        return bool(exe_name) and exe_name.lower() == self.exe.lower()


@dataclass
class Settings:
    default_profile: str = "Default"
    rules: list[AppRule] = field(default_factory=list)
    fps: int = 30
    mouse_device_type: str = "rgb-3-zone"
    auto_switch: bool = True
    master_brightness: float = 1.0  # global dimmer on top of every profile
    mouse_fps: float = 10.0  # max wireless mouse lighting updates per second

    def to_dict(self) -> dict:
        return {
            "default_profile": self.default_profile,
            "rules": [{"exe": r.exe, "profile": r.profile} for r in self.rules],
            "fps": self.fps,
            "mouse_device_type": self.mouse_device_type,
            "auto_switch": self.auto_switch,
            "master_brightness": self.master_brightness,
            "mouse_fps": self.mouse_fps,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "Settings":
        return cls(
            default_profile=d.get("default_profile", "Default"),
            rules=[AppRule(r["exe"], r["profile"]) for r in d.get("rules", [])],
            fps=int(d.get("fps", 30)),
            mouse_device_type=d.get("mouse_device_type", "rgb-3-zone"),
            auto_switch=bool(d.get("auto_switch", True)),
            master_brightness=float(d.get("master_brightness", 1.0)),
            mouse_fps=float(d.get("mouse_fps", 10.0)),
        )

    def profile_for(self, exe_name: str | None) -> str:
        for rule in self.rules:
            if rule.matches(exe_name):
                return rule.profile
        return self.default_profile


def _slug(name: str) -> str:
    return re.sub(r"[^A-Za-z0-9_-]+", "_", name).strip("_") or "profile"


class ProfileStore:
    def __init__(self, root: Path | None = None) -> None:
        self.dir = root / "profiles" if root else profiles_dir()
        self.dir.mkdir(parents=True, exist_ok=True)
        self.settings_path = (root or data_dir()) / "settings.json"
        self.profiles: dict[str, Profile] = {}
        self.settings = Settings()
        self.load()

    # ------------------------------------------------------------------ io
    def load(self) -> None:
        self.profiles.clear()
        for path in sorted(self.dir.glob("*.json")):
            try:
                p = Profile.from_dict(json.loads(path.read_text(encoding="utf-8")))
                self.profiles[p.name] = p
            except (OSError, ValueError, KeyError) as exc:
                log.warning("skipping bad profile %s: %s", path, exc)
        if self.settings_path.exists():
            try:
                self.settings = Settings.from_dict(json.loads(self.settings_path.read_text(encoding="utf-8")))
            except (OSError, ValueError, KeyError) as exc:
                log.warning("bad settings file, using defaults: %s", exc)
        if not self.profiles:
            for p in default_profiles():
                self.save_profile(p)
        if self.settings.default_profile not in self.profiles:
            self.settings.default_profile = next(iter(self.profiles))
        self.save_settings()

    def save_profile(self, profile: Profile, old_name: str | None = None) -> None:
        if old_name and old_name != profile.name:
            self.delete_profile(old_name, keep_rules=True)
            for r in self.settings.rules:
                if r.profile == old_name:
                    r.profile = profile.name
            if self.settings.default_profile == old_name:
                self.settings.default_profile = profile.name
            self.save_settings()
        self.profiles[profile.name] = profile
        (self.dir / f"{_slug(profile.name)}.json").write_text(json.dumps(profile.to_dict(), indent=2), encoding="utf-8")

    def delete_profile(self, name: str, keep_rules: bool = False) -> None:
        self.profiles.pop(name, None)
        path = self.dir / f"{_slug(name)}.json"
        if path.exists():
            path.unlink()
        if not keep_rules:
            self.settings.rules = [r for r in self.settings.rules if r.profile != name]
            if self.settings.default_profile == name and self.profiles:
                self.settings.default_profile = next(iter(self.profiles))
            self.save_settings()

    def save_settings(self) -> None:
        self.settings_path.write_text(json.dumps(self.settings.to_dict(), indent=2), encoding="utf-8")

    def get(self, name: str) -> Profile:
        return self.profiles.get(name) or self.profiles[self.settings.default_profile]


def default_profiles() -> list[Profile]:
    wasd = {k: "#ff1030" for k in ("w", "a", "s", "d")}
    wasd.update({k: "#ffb000" for k in ("lshift", "space", "lctrl", "e", "r", "q", "f")})
    return [
        Profile("Default", [
            LayerConfig("wave", {"rainbow": True, "speed": 0.25, "wavelength": 1.2}, name="Rainbow wave"),
            LayerConfig("ripple", {"color": "#ffffff"}, blend="screen", name="Ripples"),
            LayerConfig("lock_keys", {}, name="Caps / Scroll lock"),
        ]),
        Profile("Gaming", [
            LayerConfig("solid", {"color": "#100020"}, name="Dim base"),
            LayerConfig("breathing", {"colors": ["#4000ff"], "period": 5.0, "fade_layer": True},
                        keys=["mouse1", "mouse2", "mouse3"], name="Mouse breathing"),
            LayerConfig("paint", {"keys": wasd}, name="Game keys"),
            LayerConfig("key_fade", {"color": "#00e0ff", "duration": 0.4}, name="Key fade"),
            LayerConfig("lock_keys", {}, name="Caps / Scroll lock"),
        ]),
        Profile("Typing", [
            LayerConfig("gradient", {"colors": ["#ff6a00", "#ee0979"], "direction": "right"}, name="Sunset"),
            LayerConfig("heatmap", {"cold": "#000000", "hot": "#ffffff", "half_life": 30.0},
                        blend="add", opacity=0.8, name="Typing heatmap"),
            LayerConfig("cpu_load", {}, name="CPU on F-row"),
            LayerConfig("lock_keys", {"caps_keys": "all letters"}, name="Caps lock"),
        ]),
    ]

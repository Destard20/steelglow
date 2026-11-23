"""Glue between profiles, app rules, the render engine and the UI."""
from __future__ import annotations

import logging
import sys
from pathlib import Path

from PySide6.QtCore import QObject, QTimer, Signal

from ..engine.effects import EFFECTS
from ..engine.loop import Engine
from ..gamesense import GameSenseClient
from ..layout import get_layout
from ..profiles import ProfileStore
from ..profiles.app_rules import foreground_exe, is_own_process

log = logging.getLogger(__name__)

RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
RUN_NAME = "SteelGlow"
LEGACY_RUN_NAMES = ("CustomKeyboardLights",)  # pre-rename Run-key value names


class Controller(QObject):
    activeProfileChanged = Signal(str)
    statusChanged = Signal(bool, str)  # connected, message
    profilesChanged = Signal()
    masterBrightnessChanged = Signal(float)
    previewChanged = Signal(object)  # profile name or None

    def __init__(self) -> None:
        super().__init__()
        self.store = ProfileStore()
        self.layout = get_layout()
        s = self.store.settings
        self.client = GameSenseClient(mouse_device_type=s.mouse_device_type)
        self.engine = Engine(self.layout, self.client, fps=s.fps)
        self.engine.mouse_fps = s.mouse_fps
        self.engine.set_levels(master=s.master_brightness)
        self.active: str | None = None
        self.editor_profile: str | None = None  # shown while our own window has focus
        self.preview_profile: str | None = None  # forced from the CLI; beats editor and app rules
        self.foreground: str | None = None
        self._connected: bool | None = None
        self.timer = QTimer(self)
        self.timer.setInterval(500)
        self.timer.timeout.connect(self.tick)

    # ------------------------------------------------------------------ lifecycle
    def start(self) -> None:
        self.apply(self.store.settings.default_profile, force=True)
        self.engine.start()
        self.timer.start()
        self.tick()

    def shutdown(self) -> None:
        self.timer.stop()
        self.engine.stop()
        self.client.close()

    # ------------------------------------------------------------------ profile selection
    def target_profile(self) -> str:
        s = self.store.settings
        if self.preview_profile in self.store.profiles:
            return self.preview_profile
        if is_own_process(None) and self.editor_profile in self.store.profiles:
            return self.editor_profile
        if s.auto_switch:
            exe = foreground_exe()
            if exe and not is_own_process(exe):
                self.foreground = exe
            return s.profile_for(self.foreground)
        return s.default_profile

    def tick(self) -> None:
        try:
            target = self.target_profile()
        except Exception:  # noqa: BLE001
            log.exception("profile selection failed")
            target = self.store.settings.default_profile
        if target != self.active:
            self.apply(target)
        connected = self.client.connected
        if connected != self._connected:
            self._connected = connected
            msg = "Connected to SteelSeries GG" if connected else (
                "Waiting for SteelSeries GG… " + (self.client.last_error or ""))
            self.statusChanged.emit(connected, msg)

    def apply(self, name: str, force: bool = False) -> None:
        if name not in self.store.profiles:
            name = self.store.settings.default_profile
        if name == self.active and not force:
            return
        p = self.store.profiles[name]
        self.engine.set_layers(p.layers, reactive=p.reactive)
        self.engine.set_levels(keyboard=p.keyboard_brightness, mouse=p.mouse_brightness)
        self.active = name
        log.info("active profile: %s", name)
        self.activeProfileChanged.emit(name)

    def profile_edited(self, name: str) -> None:
        """Called by the editor after any change; persists and refreshes live lighting."""
        p = self.store.profiles.get(name)
        if p is None:
            return
        self.store.save_profile(p)
        if name == self.active:
            self.apply(name, force=True)

    # ------------------------------------------------------------------ preview / reload / IPC
    def set_preview(self, name: str | None) -> None:
        """Force ``name`` live regardless of focus/app rules (``None`` ends the preview)."""
        if name is not None and name not in self.store.profiles:
            raise KeyError(f"no profile named {name!r}")
        self.preview_profile = name
        self.previewChanged.emit(name)
        if name is not None:
            self.apply(name, force=True)
        self.tick()

    def reload_profiles(self) -> None:
        """Re-read profiles and settings from disk (after a CLI import/edit)."""
        self.store.load()
        s = self.store.settings
        self.engine.fps = s.fps
        self.engine.mouse_fps = s.mouse_fps
        self.engine.set_levels(master=s.master_brightness)
        if self.preview_profile not in self.store.profiles:
            self.preview_profile = None
            self.previewChanged.emit(None)
        self.profilesChanged.emit()
        self.masterBrightnessChanged.emit(s.master_brightness)
        target = self.target_profile()
        self.apply(target, force=True)

    def status(self) -> dict:
        return {
            "ok": True,
            "active": self.active,
            "preview": self.preview_profile,
            "default": self.store.settings.default_profile,
            "connected": self.client.connected,
            "gg_error": self.client.last_error,
            "paused": self.engine.paused,
            "profiles": list(self.store.profiles),
            "calibrated": self.layout.calibrated,
            "effects": sorted(EFFECTS),  # lets the CLI detect effects added since the app started
        }

    def handle_command(self, req: dict, on_show=None, on_quit=None) -> dict:
        cmd = req.get("cmd")
        if cmd == "status":
            return self.status()
        if cmd == "reload":
            self.reload_profiles()
            return self.status()
        if cmd == "preview":
            name = req.get("name")
            if req.get("reload", True):
                self.reload_profiles()
            if name not in self.store.profiles:
                return {"ok": False, "error": f"no profile named {name!r}", "profiles": list(self.store.profiles)}
            if req.get("unpause", True) and self.engine.paused:
                self.set_paused(False)
            self.set_preview(name)
            return self.status()
        if cmd == "end_preview":
            self.set_preview(None)
            return self.status()
        if cmd == "show":
            if on_show:
                on_show()
            return {"ok": True}
        if cmd == "quit":
            if on_quit:
                on_quit()
            return {"ok": True}
        return {"ok": False, "error": f"unknown command {cmd!r}"}

    def set_default_profile(self, name: str) -> None:
        self.store.settings.default_profile = name
        self.store.save_settings()
        self.tick()

    def set_auto_switch(self, on: bool) -> None:
        self.store.settings.auto_switch = on
        self.store.save_settings()
        self.tick()

    def set_master_brightness(self, level: float) -> None:
        level = max(0.0, min(1.0, float(level)))
        self.engine.set_levels(master=level)
        if abs(level - self.store.settings.master_brightness) > 1e-6:
            self.store.settings.master_brightness = level
            self.store.save_settings()
            self.masterBrightnessChanged.emit(level)

    def set_mouse_fps(self, fps: float) -> None:
        self.store.settings.mouse_fps = float(fps)
        self.engine.mouse_fps = float(fps)
        self.store.save_settings()

    pausedChanged = Signal(bool)

    def set_paused(self, paused: bool) -> None:
        if paused != self.engine.paused:
            self.engine.set_paused(paused)
            self.pausedChanged.emit(paused)

    def set_fps(self, fps: int) -> None:
        self.store.settings.fps = fps
        self.engine.fps = fps
        self.store.save_settings()

    def set_mouse_device_type(self, dtype: str) -> None:
        self.store.settings.mouse_device_type = dtype
        self.store.save_settings()
        self.client.mouse_device_type = dtype
        self.client.stop()  # re-registers handlers on next frame


# ---------------------------------------------------------------------- autostart
def _launch_command() -> str:
    exe = Path(sys.executable)
    pyw = exe.with_name("pythonw.exe")
    return f'"{pyw if pyw.exists() else exe}" -m ckl'


def _run_value_exists(name: str) -> bool:
    try:
        import winreg

        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as k:
            winreg.QueryValueEx(k, name)
            return True
    except OSError:
        return False


def autostart_enabled() -> bool:
    return any(_run_value_exists(n) for n in (RUN_NAME, *LEGACY_RUN_NAMES))


def set_autostart(enabled: bool) -> None:
    """Write (or remove) the HKCU Run entry. Always clears pre-rename entries."""
    import winreg

    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_SET_VALUE) as k:
        if enabled:
            winreg.SetValueEx(k, RUN_NAME, 0, winreg.REG_SZ, _launch_command())
        for name in ((*LEGACY_RUN_NAMES,) if enabled else (RUN_NAME, *LEGACY_RUN_NAMES)):
            try:
                winreg.DeleteValue(k, name)
            except FileNotFoundError:
                pass


def migrate_autostart() -> None:
    """Rename a pre-rename Run entry to the current name (keeps the user's choice)."""
    try:
        if any(_run_value_exists(n) for n in LEGACY_RUN_NAMES):
            set_autostart(True)
            log.info("migrated start-with-Windows entry to %r", RUN_NAME)
    except OSError as exc:
        log.warning("could not migrate autostart entry: %s", exc)

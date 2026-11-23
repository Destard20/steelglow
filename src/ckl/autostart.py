"""Start with Windows, via a "SteelGlow" shortcut in the user's Startup folder.

Why a shortcut and not an HKCU\\...\\Run value: a Run value launching ``pythonw.exe`` is listed as
"Python" in Task Manager / Settings > Apps > Startup, and on this machine Windows skipped such a
value at login because it had no entry in ``StartupApproved``. A Startup-folder shortcut is listed
under its own name and icon, and enabling it also writes the same "enabled" flag that the
Settings toggle writes, so the user can see and switch it there.
"""
from __future__ import annotations

import logging
import os
import sys
from pathlib import Path

log = logging.getLogger(__name__)

SHORTCUT_NAME = "SteelGlow.lnk"
RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
APPROVED_RUN = r"Software\Microsoft\Windows\CurrentVersion\Explorer\StartupApproved\Run"
APPROVED_FOLDER = r"Software\Microsoft\Windows\CurrentVersion\Explorer\StartupApproved\StartupFolder"
# Run-key value names used by earlier versions; removed whenever autostart is (re)configured.
LEGACY_RUN_NAMES = ("SteelGlow", "CustomKeyboardLights")
ENABLED_FLAG = b"\x02" + b"\x00" * 11  # what Settings > Apps > Startup writes for "On"


class _Registry:
    """Thin HKCU wrapper (swapped for a fake in tests)."""

    def get(self, key: str, name: str):
        import winreg

        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, key) as k:
                return winreg.QueryValueEx(k, name)[0]
        except OSError:
            return None

    def set_binary(self, key: str, name: str, data: bytes) -> None:
        import winreg

        with winreg.CreateKeyEx(winreg.HKEY_CURRENT_USER, key, 0, winreg.KEY_SET_VALUE) as k:
            winreg.SetValueEx(k, name, 0, winreg.REG_BINARY, data)

    def delete(self, key: str, name: str) -> None:
        import winreg

        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, key, 0, winreg.KEY_SET_VALUE) as k:
                winreg.DeleteValue(k, name)
        except OSError:
            pass


registry = _Registry()


# ---------------------------------------------------------------------- locations
def startup_dir() -> Path:
    return Path(os.environ.get("APPDATA", Path.home())) / "Microsoft" / "Windows" / "Start Menu" / "Programs" / "Startup"


def shortcut_path() -> Path:
    return startup_dir() / SHORTCUT_NAME


def project_root() -> Path:
    return Path(__file__).resolve().parents[2]  # src/ckl/autostart.py -> repo root


def launcher() -> tuple[str, str, str]:
    """(target exe, arguments, working dir) for starting the tray app without a console."""
    exe = Path(sys.executable)
    pyw = exe.with_name("pythonw.exe")
    return str(pyw if pyw.exists() else exe), "-m ckl", str(project_root())


# ---------------------------------------------------------------------- shortcut
def _icon_file() -> str | None:
    """Write the tray icon as .ico next to the settings (needs a running QApplication)."""
    try:
        from PySide6.QtGui import QGuiApplication

        if QGuiApplication.instance() is None:
            return None
        from .paths import data_dir
        from .ui.tray import make_icon

        path = data_dir() / "steelglow.ico"
        if make_icon().pixmap(64, 64).save(str(path), "ICO"):
            return str(path)
    except Exception as exc:  # noqa: BLE001 - an icon is nice to have, never required
        log.debug("no icon for shortcut: %s", exc)
    return None


def _write_shortcut(path: Path) -> None:
    import win32com.client

    target, args, workdir = launcher()
    path.parent.mkdir(parents=True, exist_ok=True)
    sc = win32com.client.Dispatch("WScript.Shell").CreateShortcut(str(path))
    sc.TargetPath = target
    sc.Arguments = args
    sc.WorkingDirectory = workdir
    sc.Description = "SteelGlow: layered RGB lighting for SteelSeries devices"
    icon = _icon_file()
    if icon:
        sc.IconLocation = icon
    sc.Save()


def _shortcut_target(path: Path) -> tuple[str, str] | None:
    info = _shortcut_info(path)
    return (info[0], info[1]) if info else None


def _shortcut_info(path: Path) -> tuple[str, str, str] | None:
    """(target, arguments, icon file) of an existing shortcut."""
    try:
        import win32com.client

        sc = win32com.client.Dispatch("WScript.Shell").CreateShortcut(str(path))
        return sc.TargetPath, sc.Arguments, sc.IconLocation.rsplit(",", 1)[0]
    except Exception:  # noqa: BLE001
        return None


def _icon_is_stale(icon: str) -> bool:
    """True when the shortcut's icon file isn't in the current settings folder (or is missing)."""
    if not icon:
        return False  # no custom icon: nothing to repair
    from .paths import data_dir

    p = Path(icon)
    return not p.exists() or p.parent.resolve() != data_dir().resolve()


# ---------------------------------------------------------------------- public api
def _remove_legacy_run_values() -> None:
    for name in LEGACY_RUN_NAMES:
        registry.delete(RUN_KEY, name)
        registry.delete(APPROVED_RUN, name)


def is_enabled() -> bool:
    return shortcut_path().exists()


def set_enabled(enabled: bool) -> None:
    path = shortcut_path()
    if enabled:
        _write_shortcut(path)
        registry.set_binary(APPROVED_FOLDER, SHORTCUT_NAME, ENABLED_FLAG)
    else:
        if path.exists():
            path.unlink()
        registry.delete(APPROVED_FOLDER, SHORTCUT_NAME)
    _remove_legacy_run_values()
    log.info("start with Windows: %s", "on" if enabled else "off")


def migrate() -> None:
    """Run at app start: turn old Run-key entries into the shortcut, and repoint a shortcut whose
    target no longer matches this install (e.g. after the project folder moved)."""
    try:
        legacy = any(registry.get(RUN_KEY, n) is not None for n in LEGACY_RUN_NAMES)
        path = shortcut_path()
        stale = False
        if path.exists():
            current = _shortcut_info(path)
            target, args, _ = launcher()
            stale = current is not None and (
                Path(current[0]) != Path(target) or current[1] != args or _icon_is_stale(current[2]))
        if legacy or stale:
            set_enabled(True)
            log.info("autostart migrated (legacy run entry=%s, stale shortcut=%s)", legacy, stale)
    except Exception as exc:  # noqa: BLE001 - never block startup over this
        log.warning("could not migrate autostart: %s", exc)

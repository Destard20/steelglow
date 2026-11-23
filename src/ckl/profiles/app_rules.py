"""Foreground-application detection for per-app profiles."""
from __future__ import annotations

import logging
import os

import psutil

log = logging.getLogger(__name__)

_cache: dict[int, str] = {}


def foreground_exe() -> str | None:
    """Executable name (e.g. ``cs2.exe``) of the focused window's process, or None."""
    try:
        import win32gui
        import win32process
    except ImportError:
        return None
    try:
        hwnd = win32gui.GetForegroundWindow()
        if not hwnd:
            return None
        _, pid = win32process.GetWindowThreadProcessId(hwnd)
    except Exception:  # noqa: BLE001
        return None
    if pid <= 0:
        return None
    name = _cache.get(pid)
    if name is None:
        try:
            name = psutil.Process(pid).name()
        except (psutil.Error, OSError):
            return None
        if len(_cache) > 512:
            _cache.clear()
        _cache[pid] = name
    return name


def is_own_process(exe: str | None) -> bool:
    """True when the focused window belongs to this app (editor/tray)."""
    try:
        import win32gui
        import win32process

        _, pid = win32process.GetWindowThreadProcessId(win32gui.GetForegroundWindow())
        return pid == os.getpid()
    except Exception:  # noqa: BLE001
        return False

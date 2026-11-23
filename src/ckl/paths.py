"""Per-user storage locations.

Data lives in ``%USERPROFILE%\\.steelglow``, deliberately *not* under AppData: packaged (MSIX) apps
such as the Claude desktop app get a private, redirected copy of AppData, and anything they launch
inherits it. A SteelGlow started from such an app and one started by Windows at login would then
see two different settings folders. A plain folder in the user profile is the same for both.
"""
from __future__ import annotations

import logging
import os
import shutil
from pathlib import Path

from . import APP_NAME, LEGACY_APP_NAME

log = logging.getLogger(__name__)
migration_note: str | None = None  # logged by the app once logging is set up

DATA_DIR_NAME = ".steelglow"


def _legacy_dirs() -> list[Path]:
    """Folders used by earlier versions, newest naming first."""
    appdata = os.environ.get("APPDATA")
    if not appdata:
        return []
    return [Path(appdata) / APP_NAME, Path(appdata) / LEGACY_APP_NAME]


def _newest(dirs: list[Path]) -> Path | None:
    """The legacy folder whose settings were saved most recently."""
    found = [d for d in dirs if (d / "settings.json").is_file() or (d / "profiles").is_dir()]

    def stamp(d: Path) -> float:
        files = [d / "settings.json", *d.glob("profiles/*.json")]
        return max((f.stat().st_mtime for f in files if f.exists()), default=0.0)

    return max(found, key=stamp, default=None)


def _migrate_legacy(legacy: Path, new: Path) -> None:
    """Copy (not move) an old settings folder, so the old one stays as a backup."""
    global migration_note
    shutil.copytree(legacy, new, ignore=shutil.ignore_patterns("ckl.log*"))
    migration_note = f"copied settings {legacy} -> {new} (the old folder is kept as a backup)"
    log.info(migration_note)


def data_dir() -> Path:
    override = os.environ.get("CKL_DATA_DIR")
    if override:
        base = Path(override)
    else:
        base = Path.home() / DATA_DIR_NAME
        if not base.exists():
            legacy = _newest(_legacy_dirs())
            if legacy is not None:
                _migrate_legacy(legacy, base)
    base.mkdir(parents=True, exist_ok=True)
    return base


def profiles_dir() -> Path:
    p = data_dir() / "profiles"
    p.mkdir(parents=True, exist_ok=True)
    return p

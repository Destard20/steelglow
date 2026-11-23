"""Per-user storage locations."""
from __future__ import annotations

import logging
import os
import shutil
from pathlib import Path

from . import APP_NAME, LEGACY_APP_NAME

log = logging.getLogger(__name__)
migration_note: str | None = None  # logged by the app once logging is set up


def _migrate_legacy(legacy: Path, new: Path) -> None:
    """One-time move of %APPDATA%\\CustomKeyboardLights -> %APPDATA%\\SteelGlow."""
    global migration_note
    try:
        legacy.rename(new)
        migration_note = f"moved settings {legacy} -> {new}"
    except OSError as exc:  # e.g. an old instance still has its log file open
        shutil.copytree(legacy, new)
        migration_note = f"copied settings {legacy} -> {new} (could not move: {exc}); the old folder can be deleted"
    log.info(migration_note)


def data_dir() -> Path:
    override = os.environ.get("CKL_DATA_DIR")
    if override:
        base = Path(override)
    else:
        root = Path(os.environ.get("APPDATA", Path.home()))
        base = root / APP_NAME
        legacy = root / LEGACY_APP_NAME
        if not base.exists() and legacy.is_dir():
            _migrate_legacy(legacy, base)
    base.mkdir(parents=True, exist_ok=True)
    return base


def profiles_dir() -> Path:
    p = data_dir() / "profiles"
    p.mkdir(parents=True, exist_ok=True)
    return p

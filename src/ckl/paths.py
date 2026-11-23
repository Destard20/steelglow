"""Per-user storage locations."""
from __future__ import annotations

import os
from pathlib import Path

from . import APP_NAME


def data_dir() -> Path:
    override = os.environ.get("CKL_DATA_DIR")
    base = Path(override) if override else Path(os.environ.get("APPDATA", Path.home())) / APP_NAME
    base.mkdir(parents=True, exist_ok=True)
    return base


def profiles_dir() -> Path:
    p = data_dir() / "profiles"
    p.mkdir(parents=True, exist_ok=True)
    return p

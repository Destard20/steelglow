import os
import time

from ckl import paths


def _isolate(monkeypatch, tmp_path):
    monkeypatch.delenv("CKL_DATA_DIR", raising=False)
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("USERPROFILE", str(home))
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("APPDATA", str(tmp_path / "appdata"))
    monkeypatch.setattr(paths, "migration_note", None)
    return home, tmp_path / "appdata"


def _make(folder, default):
    (folder / "profiles").mkdir(parents=True)
    (folder / "profiles" / f"{default}.json").write_text("{}", encoding="utf-8")
    (folder / "settings.json").write_text(f'{{"default_profile": "{default}"}}', encoding="utf-8")
    (folder / "ckl.log").write_text("old log", encoding="utf-8")


def test_data_lives_in_user_profile(monkeypatch, tmp_path):
    home, _ = _isolate(monkeypatch, tmp_path)
    assert paths.data_dir() == home / ".steelglow"
    assert paths.migration_note is None


def test_copies_newest_legacy_folder(monkeypatch, tmp_path):
    home, appdata = _isolate(monkeypatch, tmp_path)
    _make(appdata / "CustomKeyboardLights", "Old")
    _make(appdata / "SteelGlow", "Chill Ocean")
    later = time.time() + 60
    os.utime(appdata / "SteelGlow" / "settings.json", (later, later))

    d = paths.data_dir()
    assert '"Chill Ocean"' in (d / "settings.json").read_text(encoding="utf-8")
    assert (d / "profiles" / "Chill Ocean.json").exists()
    assert not (d / "ckl.log").exists()  # logs are not carried over
    assert (appdata / "SteelGlow").exists()  # kept as backup
    assert "copied" in paths.migration_note


def test_existing_data_dir_wins(monkeypatch, tmp_path):
    home, appdata = _isolate(monkeypatch, tmp_path)
    _make(appdata / "SteelGlow", "Legacy")
    (home / ".steelglow").mkdir()
    (home / ".steelglow" / "keep.txt").write_text("x", encoding="utf-8")
    d = paths.data_dir()
    assert (d / "keep.txt").exists() and not (d / "settings.json").exists()
    assert paths.migration_note is None


def test_override_skips_migration(monkeypatch, tmp_path):
    _, appdata = _isolate(monkeypatch, tmp_path)
    _make(appdata / "SteelGlow", "Legacy")
    monkeypatch.setenv("CKL_DATA_DIR", str(tmp_path / "custom"))
    assert paths.data_dir() == tmp_path / "custom"
    assert not (tmp_path / "custom" / "settings.json").exists()

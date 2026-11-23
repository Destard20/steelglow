from ckl import paths


def _isolate(monkeypatch, tmp_path):
    monkeypatch.delenv("CKL_DATA_DIR", raising=False)
    monkeypatch.setenv("APPDATA", str(tmp_path))
    monkeypatch.setattr(paths, "migration_note", None)


def test_legacy_folder_is_moved_once(monkeypatch, tmp_path):
    _isolate(monkeypatch, tmp_path)
    legacy = tmp_path / "CustomKeyboardLights"
    (legacy / "profiles").mkdir(parents=True)
    (legacy / "profiles" / "Mine.json").write_text("{}", encoding="utf-8")
    (legacy / "settings.json").write_text('{"default_profile": "Mine"}', encoding="utf-8")

    d = paths.data_dir()
    assert d == tmp_path / "SteelGlow"
    assert (d / "profiles" / "Mine.json").exists() and (d / "settings.json").exists()
    assert not legacy.exists()
    assert "moved" in paths.migration_note


def test_existing_new_folder_wins(monkeypatch, tmp_path):
    _isolate(monkeypatch, tmp_path)
    (tmp_path / "CustomKeyboardLights").mkdir()
    (tmp_path / "SteelGlow").mkdir()
    (tmp_path / "SteelGlow" / "keep.txt").write_text("x", encoding="utf-8")
    d = paths.data_dir()
    assert (d / "keep.txt").exists()
    assert (tmp_path / "CustomKeyboardLights").exists()  # untouched
    assert paths.migration_note is None


def test_fresh_install(monkeypatch, tmp_path):
    _isolate(monkeypatch, tmp_path)
    assert paths.data_dir() == tmp_path / "SteelGlow"
    assert paths.migration_note is None


def test_override_skips_migration(monkeypatch, tmp_path):
    _isolate(monkeypatch, tmp_path)
    (tmp_path / "CustomKeyboardLights").mkdir()
    monkeypatch.setenv("CKL_DATA_DIR", str(tmp_path / "custom"))
    assert paths.data_dir() == tmp_path / "custom"
    assert (tmp_path / "CustomKeyboardLights").exists()

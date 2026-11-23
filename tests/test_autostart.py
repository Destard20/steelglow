"""Start-with-Windows: shortcut + StartupApproved flag, with a fake registry."""
import pytest

from ckl import autostart


class FakeRegistry:
    def __init__(self):
        self.values: dict[tuple[str, str], object] = {}

    def get(self, key, name):
        return self.values.get((key, name))

    def set_binary(self, key, name, data):
        self.values[(key, name)] = data

    def delete(self, key, name):
        self.values.pop((key, name), None)


@pytest.fixture
def env(monkeypatch, tmp_path):
    reg = FakeRegistry()
    monkeypatch.setattr(autostart, "registry", reg)
    monkeypatch.setenv("APPDATA", str(tmp_path))
    monkeypatch.setenv("CKL_DATA_DIR", str(tmp_path / "data"))
    return reg


def test_enable_creates_shortcut_and_approval(env):
    autostart.set_enabled(True)
    assert autostart.is_enabled()
    assert autostart.shortcut_path().parent == autostart.startup_dir()
    target, args = autostart._shortcut_target(autostart.shortcut_path())
    assert target.lower().endswith("pythonw.exe") and args == "-m ckl"
    assert env.get(autostart.APPROVED_FOLDER, autostart.SHORTCUT_NAME) == autostart.ENABLED_FLAG


def test_disable_removes_everything(env):
    autostart.set_enabled(True)
    autostart.set_enabled(False)
    assert not autostart.is_enabled()
    assert env.get(autostart.APPROVED_FOLDER, autostart.SHORTCUT_NAME) is None


def test_migrate_replaces_legacy_run_entries(env):
    for name in autostart.LEGACY_RUN_NAMES:
        env.values[(autostart.RUN_KEY, name)] = '"old\\pythonw.exe" -m ckl'
    env.values[(autostart.APPROVED_RUN, "SteelGlow")] = b"\x03" + b"\x00" * 11
    autostart.migrate()
    assert autostart.is_enabled()
    assert not any(k[0] in (autostart.RUN_KEY, autostart.APPROVED_RUN) for k in env.values)


def test_migrate_repoints_stale_shortcut(env, monkeypatch):
    """A shortcut left pointing at an old project folder is rewritten on the next start."""
    real = autostart.launcher
    monkeypatch.setattr(autostart, "launcher", lambda: (r"C:\old\place\pythonw.exe", "-m ckl", r"C:\old\place"))
    autostart.set_enabled(True)
    assert autostart._shortcut_target(autostart.shortcut_path())[0].lower() == r"c:\old\place\pythonw.exe"
    monkeypatch.setattr(autostart, "launcher", real)
    autostart.migrate()
    assert autostart._shortcut_target(autostart.shortcut_path())[0].lower() == real()[0].lower()


def test_migrate_noop_when_nothing_to_do(env):
    autostart.migrate()
    assert not autostart.is_enabled()
    assert env.values == {}

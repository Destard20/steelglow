from ckl.engine.layer import LayerConfig
from ckl.profiles import AppRule, Profile, ProfileStore


def test_first_run_creates_defaults(tmp_path):
    store = ProfileStore(tmp_path)
    assert {"Default", "Gaming", "Typing"} <= set(store.profiles)
    assert (tmp_path / "settings.json").exists()


def test_round_trip(tmp_path):
    store = ProfileStore(tmp_path)
    p = Profile("My FPS", [LayerConfig("paint", {"keys": {"w": "#ff0000"}}, keys=None, blend="add", opacity=0.5)],
                keyboard_brightness=0.7, mouse_brightness=0.0, reactive=False)
    store.save_profile(p)
    store.settings.rules.append(AppRule("CS2.exe", "My FPS"))
    store.save_settings()
    again = ProfileStore(tmp_path)
    q = again.profiles["My FPS"]
    assert q.to_dict() == p.to_dict()
    assert again.settings.profile_for("cs2.EXE") == "My FPS"
    assert again.settings.profile_for("notepad.exe") == again.settings.default_profile
    assert again.settings.profile_for(None) == again.settings.default_profile


def test_legacy_single_brightness_migrates():
    p = Profile.from_dict({"name": "Old", "brightness": 0.4, "layers": []})
    assert p.keyboard_brightness == 0.4 and p.mouse_brightness == 0.4
    assert "brightness" not in p.to_dict()


def test_master_brightness_persists(tmp_path):
    store = ProfileStore(tmp_path)
    store.settings.master_brightness = 0.25
    store.settings.mouse_fps = 4
    store.save_settings()
    again = ProfileStore(tmp_path).settings
    assert again.master_brightness == 0.25 and again.mouse_fps == 4


def test_rename_updates_rules(tmp_path):
    store = ProfileStore(tmp_path)
    store.settings.rules.append(AppRule("game.exe", "Gaming"))
    p = store.profiles["Gaming"]
    p.name = "Gaming 2"
    store.save_profile(p, old_name="Gaming")
    again = ProfileStore(tmp_path)
    assert "Gaming" not in again.profiles and "Gaming 2" in again.profiles
    assert again.settings.profile_for("game.exe") == "Gaming 2"


def test_delete_removes_rules(tmp_path):
    store = ProfileStore(tmp_path)
    store.settings.rules.append(AppRule("x.exe", "Typing"))
    store.delete_profile("Typing")
    assert ProfileStore(tmp_path).settings.rules == []

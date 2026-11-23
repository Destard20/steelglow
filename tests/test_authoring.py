"""Tests for the profile-authoring toolchain: groups, effect registry, validator, preview IPC, CLI."""
import json
from pathlib import Path

import numpy as np
import pytest

from ckl.engine.effects import EFFECTS, Effect, Param, RenderContext
from ckl.engine.layer import Layer, LayerConfig, composite, to_u8
from ckl.layout import Layout
from ckl.profiles.validate import errors, validate

LIBRARY = sorted((Path(__file__).resolve().parents[1] / "profile_library").glob("*.json"))


@pytest.fixture(scope="module")
def layout(tmp_path_factory):
    return Layout(calibration_file=tmp_path_factory.mktemp("cal") / "none.json")


# ---------------------------------------------------------------- groups
def test_group_expansion(layout):
    ids = layout.expand(["@wasd", "w", "@row0"])
    assert ids[:4] == ["w", "a", "s", "d"]
    assert ids.count("w") == 1
    assert "esc" in ids and "f12" in ids and "pause" in ids
    assert set(layout.expand(["@mouse"])) == {"mouse1", "mouse2", "mouse3"}
    assert len(layout.expand(["@keyboard"])) == len(layout.keyboard)
    assert len(layout.expand(["@all"])) == layout.n
    with pytest.raises(KeyError):
        layout.expand(["@nope"], strict=True)
    assert layout.expand(["@nope", "q"]) == ["q"]


def test_group_mask_and_paint(layout):
    mask = layout.ids_to_mask(["@arrows"])
    assert mask.sum() == 4 and mask[layout.by_id["up"].index]
    paint = Layer(LayerConfig("paint", {"keys": {"@letters": "#0000ff", "w": "#ff0000"}}), layout)
    out = to_u8(composite([paint], RenderContext(t=0, dt=0.03, layout=layout)))
    assert tuple(out[layout.by_id["w"].index]) == (255, 0, 0)  # later entry wins
    assert tuple(out[layout.by_id["q"].index]) == (0, 0, 255)
    assert tuple(out[layout.by_id["1"].index]) == (0, 0, 0)


# ---------------------------------------------------------------- registry
def test_effect_auto_registration(layout):
    class Dummy(Effect):
        id, name = "zz_test_dummy", "Dummy"
        params = [Param("color", "Color", "color", "#123456")]

        def render(self, ctx):
            return self.full(np.array([1, 0, 0], np.float32)), self.ones()

    try:
        assert EFFECTS["zz_test_dummy"] is Dummy
        assert Layer(LayerConfig("zz_test_dummy"), layout).effect.p["color"] == "#123456"
    finally:
        EFFECTS.pop("zz_test_dummy", None)


def test_mutable_defaults_not_shared(layout):
    a = Layer(LayerConfig("wave"), layout).effect
    a.p["colors"].append("#ffffff")
    assert "#ffffff" not in Layer(LayerConfig("wave"), layout).effect.p["colors"]


def test_every_effect_has_description():
    assert all(cls.description for cls in EFFECTS.values())


# ---------------------------------------------------------------- validator
GOOD = {
    "name": "Test", "category": "game", "tags": ["x"], "keyboard_brightness": 0.8, "mouse_brightness": 0,
    "layers": [
        {"effect": "solid", "params": {"color": "#101010"}},
        {"effect": "paint", "params": {"keys": {"@wasd": "#ff0000", "space": "#00ff00"}}},
        {"effect": "ripple", "blend": "screen", "opacity": 0.7, "keys": ["@keyboard"]},
    ],
}


def test_validator_accepts_good_profile(layout):
    assert validate(GOOD, layout) == []


@pytest.mark.parametrize("mutate, path", [
    (lambda d: d["layers"][0].update(effect="nope"), "layers[0].effect"),
    (lambda d: d["layers"][0]["params"].update(color="red"), "layers[0].params.color"),
    (lambda d: d["layers"][2].update(params={"speed": 999}), "layers[2].params.speed"),
    (lambda d: d["layers"][2].update(keys=["@wasd", "nokey"]), "layers[2].keys[1]"),
    (lambda d: d["layers"][2].update(keys=["@bogus"]), "layers[2].keys[0]"),
    (lambda d: d["layers"][1]["params"]["keys"].update({"zz": "#ffffff"}), "layers[1].params.keys.zz"),
    (lambda d: d["layers"][2].update(blend="overlay"), "layers[2].blend"),
    (lambda d: d["layers"][2].update(opacity=2), "layers[2].opacity"),
    (lambda d: d.update(mouse_brightness=1.5), "mouse_brightness"),
    (lambda d: d.update(layers=[]), "layers"),
    (lambda d: d.update(name=""), "name"),
])
def test_validator_errors(layout, mutate, path):
    data = json.loads(json.dumps(GOOD))
    mutate(data)
    errs = errors(validate(data, layout))
    assert any(e.path == path for e in errs), [str(e) for e in errs]


def test_validator_warnings(layout):
    data = json.loads(json.dumps(GOOD))
    data["layers"].append({"effect": "wave", "params": {"speedy": 1}})
    data["reactive"] = False
    issues = validate(data, layout)
    assert not errors(issues)
    msgs = " | ".join(str(i) for i in issues)
    assert "speedy" in msgs and "hidden" in msgs and "reactive" in msgs


@pytest.mark.parametrize("path", LIBRARY, ids=lambda p: p.name)
def test_library_profiles_are_valid(layout, path):
    issues = validate(json.loads(path.read_text(encoding="utf-8")), layout)
    assert not errors(issues), [str(i) for i in issues]


# ---------------------------------------------------------------- controller preview / IPC commands
@pytest.fixture
def qapp():
    from PySide6.QtWidgets import QApplication

    return QApplication.instance() or QApplication([])


@pytest.fixture
def ctrl(qapp, tmp_path, monkeypatch):
    monkeypatch.setenv("CKL_DATA_DIR", str(tmp_path))
    from ckl.ui.controller import Controller

    c = Controller()
    c.store.settings.auto_switch = False
    c.store.settings.default_profile = "Default"
    c.apply("Default", force=True)
    yield c
    c.engine.keyhook.stop()


def test_preview_overrides_and_ends(ctrl):
    st = ctrl.handle_command({"cmd": "preview", "name": "Gaming"})
    assert st["ok"] and st["active"] == "Gaming" and st["preview"] == "Gaming"
    ctrl.tick()  # normal selection must not take it away
    assert ctrl.active == "Gaming"
    st = ctrl.handle_command({"cmd": "end_preview"})
    assert st["preview"] is None and ctrl.active == "Default"


def test_preview_unknown_profile(ctrl):
    st = ctrl.handle_command({"cmd": "preview", "name": "Nope"})
    assert not st["ok"] and "Nope" in st["error"]


def test_reload_picks_up_new_files(ctrl, tmp_path):
    (tmp_path / "profiles" / "New.json").write_text(json.dumps(GOOD | {"name": "New One"}), encoding="utf-8")
    st = ctrl.handle_command({"cmd": "reload"})
    assert "New One" in st["profiles"]
    assert "effects" in st and "wave" in st["effects"]
    assert ctrl.handle_command({"cmd": "bogus"})["ok"] is False


# ---------------------------------------------------------------- CLI
def test_cli_validate_import_render(qapp, tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("CKL_DATA_DIR", str(tmp_path))
    from ckl.cli import main

    src = tmp_path / "p.json"
    src.write_text(json.dumps(GOOD | {"name": "CLI Test"}), encoding="utf-8")
    assert main(["profile", "validate", str(src)]) == 0
    assert main(["profile", "import", str(src), "--no-reload"]) == 0
    assert (tmp_path / "profiles" / "CLI_Test.json").exists()
    assert main(["profile", "import", str(src), "--no-reload"]) == 1  # exists, no --replace
    assert main(["profile", "import", str(src), "--no-reload", "--replace"]) == 0
    png = tmp_path / "out.png"
    assert main(["profile", "render", str(src), "--out", str(png), "--press", "@wasd"]) == 0
    assert png.stat().st_size > 10_000
    bad = tmp_path / "bad.json"
    bad.write_text(json.dumps({"name": "Bad", "layers": [{"effect": "nope"}]}), encoding="utf-8")
    assert main(["profile", "validate", str(bad)]) == 1


def test_cli_schema_json(capsys):
    from ckl.cli import main

    assert main(["profile", "schema", "--json"]) == 0
    data = json.loads(capsys.readouterr().out)
    assert "wave" in data["effects"] and "@wasd" in data["key_groups"]
    assert data["keys_by_row"]["mouse"] == ["mouse1", "mouse2", "mouse3"]


def test_render_frames_reactive_press():
    from ckl.cli import render_frames

    frames = render_frames(GOOD, [0.0, 0.3], press=["space"])
    (_, f0), (_, f1) = frames
    assert len(frames) == 2 and f0.shape == f1.shape

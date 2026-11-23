import numpy as np
import pytest

from ckl.engine.effects import EFFECTS, RenderContext
from ckl.engine.layer import Layer, LayerConfig, blend, composite, to_u8
from ckl.gamesense.client import BITMAP_LEN
from ckl.layout import Layout


@pytest.fixture(scope="module")
def layout(tmp_path_factory):
    return Layout(calibration_file=tmp_path_factory.mktemp("cal") / "none.json")


def ctx(layout, t=1.0, dt=1 / 30, **kw):
    return RenderContext(t=t, dt=dt, layout=layout, **kw)


def test_layout_basics(layout):
    assert len(layout.keyboard) == 88  # ISO TKL incl. SteelSeries key
    assert len(layout.mouse) == 3
    assert layout.by_scan[0x11].id == "w"
    assert layout.by_scan[0xE000 | 0x48].id == "up"
    # Every grid cell maps to a keyboard key by default, and every key is reachable.
    assert (layout.default_cell_to_led >= 0).all()
    reached = set(layout.default_cell_to_led.tolist())
    missing = [l.id for l in layout.keyboard if l.index not in reached]
    assert len(missing) <= 6, missing


def test_bitmap_and_mouse_conversion(layout):
    colors = np.zeros((layout.n, 3), np.uint8)
    colors[layout.by_id["esc"].index] = (255, 0, 0)
    colors[layout.mouse_idx[1]] = (0, 0, 255)
    bm = layout.to_bitmap(colors)
    assert len(bm) == BITMAP_LEN
    assert bm[0] == [255, 0, 0]  # top-left cell is Esc
    assert layout.to_mouse(colors) == [[0, 0, 0], [0, 0, 255], [0, 0, 0]]


def test_calibration_overrides(layout, tmp_path):
    lay = Layout(calibration_file=tmp_path / "cal.json")
    lay.save_calibration({0: "f1", 1: None})
    again = Layout(calibration_file=tmp_path / "cal.json")
    assert again.calibrated
    assert again.cell_to_led[0] == again.by_id["f1"].index
    assert again.cell_to_led[1] == -1
    colors = np.full((again.n, 3), 200, np.uint8)
    assert again.to_bitmap(colors)[1] == [0, 0, 0]


@pytest.mark.parametrize("eid", sorted(EFFECTS))
def test_every_effect_renders_valid_output(layout, eid):
    layer = Layer(LayerConfig(eid, EFFECTS[eid].defaults()), layout)
    w = layout.by_id["w"].index
    for i in range(5):
        c = ctx(layout, t=i * 0.1, presses=[(w, i * 0.1)], held={w}, locks={"caps": True, "scroll": True}, cpu=0.5)
        colors, alpha = layer.effect.render(c)
        assert colors.shape == (layout.n, 3)
        assert alpha.shape == (layout.n,)
        assert np.isfinite(colors).all() and np.isfinite(alpha).all()
        assert (alpha >= 0).all() and (alpha <= 1.0001).all()


def test_blend_modes():
    a = np.array([[0.5, 0.5, 0.5]], np.float32)
    b = np.array([[0.4, 1.0, 0.0]], np.float32)
    np.testing.assert_allclose(blend(a, b, "normal"), b)
    np.testing.assert_allclose(blend(a, b, "add"), [[0.9, 1.0, 0.5]])
    np.testing.assert_allclose(blend(a, b, "multiply"), [[0.2, 0.5, 0.0]])
    np.testing.assert_allclose(blend(a, b, "max"), [[0.5, 1.0, 0.5]])


def test_layer_stacking_and_masks(layout):
    base = Layer(LayerConfig("solid", {"color": "#0000ff"}), layout)
    wasd = Layer(LayerConfig("solid", {"color": "#ff0000"}, keys=["w", "a", "s", "d"]), layout)
    half = Layer(LayerConfig("solid", {"color": "#00ff00"}, keys=["esc"], opacity=0.5), layout)
    out = to_u8(composite([base, wasd, half], ctx(layout)))
    L = layout.by_id
    assert tuple(out[L["w"].index]) == (255, 0, 0)
    assert tuple(out[L["q"].index]) == (0, 0, 255)
    assert tuple(out[L["esc"].index]) == (0, 128, 128)
    assert tuple(out[layout.mouse_idx[0]]) == (0, 0, 255)


def test_paint_transparent_elsewhere(layout):
    base = Layer(LayerConfig("solid", {"color": "#202020"}), layout)
    paint = Layer(LayerConfig("paint", {"keys": {"space": "#ffffff"}}), layout)
    out = to_u8(composite([base, paint], ctx(layout)))
    assert tuple(out[layout.by_id["space"].index]) == (255, 255, 255)
    assert tuple(out[layout.by_id["a"].index]) == (32, 32, 32)


def test_disabled_layer_is_skipped(layout):
    cfg = LayerConfig("solid", {"color": "#ffffff"}, enabled=False)
    out = composite([Layer(cfg, layout)], ctx(layout))
    assert out.max() == 0


def test_ripple_spreads_and_expires(layout):
    eff = Layer(LayerConfig("ripple", {"lifetime": 0.5, "speed": 10}), layout).effect
    g = layout.by_id["g"].index
    _, a0 = eff.render(ctx(layout, t=0.0, presses=[(g, 0.0)]))
    assert a0[g] > 0.9
    _, a1 = eff.render(ctx(layout, t=0.2))
    assert a1[g] < 0.2 and a1.max() > 0.3  # ring moved away from origin
    _, a2 = eff.render(ctx(layout, t=0.6))
    assert a2.max() == 0


def test_lock_keys_follow_state(layout):
    eff = Layer(LayerConfig("lock_keys", {}), layout).effect
    caps = layout.by_id["caps"].index
    _, off = eff.render(ctx(layout, locks={"caps": False}))
    _, on = eff.render(ctx(layout, locks={"caps": True}))
    assert off[caps] == 0 and on[caps] == 1


def test_cpu_bar_fills_function_row(layout):
    eff = Layer(LayerConfig("cpu_load", {"smoothing": 0}), layout).effect
    _, a = eff.render(ctx(layout, cpu=0.5))
    f = [a[layout.by_id[f"f{i}"].index] for i in range(1, 13)]
    assert f[:6] == [1.0] * 6 and f[6:] == [0.0] * 6

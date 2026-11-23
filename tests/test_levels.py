import numpy as np
import pytest

from ckl.engine.effects import RenderContext
from ckl.engine.layer import Layer, LayerConfig, composite
from ckl.engine.loop import MOUSE_REFRESH, RESEND_INTERVAL, Engine, SendState
from ckl.layout import Layout


class FakeClient:
    connected = True

    def stop(self):
        pass


@pytest.fixture(scope="module")
def layout(tmp_path_factory):
    return Layout(calibration_file=tmp_path_factory.mktemp("cal") / "none.json")


def render(engine, layout):
    from ckl.engine.layer import to_u8

    layers = [Layer(LayerConfig("solid", {"color": "#ffffff"}), layout)]
    return to_u8(composite(layers, RenderContext(t=0, dt=0.03, layout=layout)), engine._levels)


def test_device_levels_and_master(layout):
    eng = Engine(layout, FakeClient())
    eng.set_levels(keyboard=0.5, mouse=0.0)
    out = render(eng, layout)
    assert tuple(out[layout.by_id["a"].index]) == (128, 128, 128)
    assert out[layout.mouse_idx].max() == 0
    eng.set_levels(master=0.5)  # keeps device levels, scales on top
    out = render(eng, layout)
    assert tuple(out[layout.by_id["a"].index]) == (64, 64, 64)
    eng.set_levels(master=0.0)
    assert render(eng, layout).max() == 0


def test_static_mouse_is_sent_once():
    s = SendState()
    kb, mouse = [[1, 1, 1]], [[0, 0, 0]] * 3
    assert s.plan((kb, mouse), 0.0, 10) == (kb, mouse)
    s.sent(kb, mouse, 0.0)
    # same frame shortly after: nothing at all
    assert s.plan((kb, mouse), 0.5, 10) == (None, None)
    # keyboard changes, mouse doesn't -> keyboard only
    kb2 = [[2, 2, 2]]
    assert s.plan((kb2, mouse), 0.6, 10) == (kb2, None)
    s.sent(kb2, None, 0.6)
    # keep-alive re-sends keyboard only
    assert s.plan(None, 0.6 + RESEND_INTERVAL + 0.1, 10) == (kb2, None)
    # slow refresh eventually re-asserts the mouse
    assert s.plan((kb2, mouse), MOUSE_REFRESH + 1, 10)[1] == mouse


def test_animated_mouse_is_rate_limited():
    s = SendState()
    s.sent([[0, 0, 0]], [[0, 0, 0]] * 3, 0.0)
    sent = 0
    for i in range(1, 61):  # one second of 60 fps animation
        t = i / 60
        _, m = s.plan(([[i, 0, 0]], [[i, 0, 0]] * 3), t, 5)
        if m is not None:
            s.sent(None, m, t)
            sent += 1
    assert 4 <= sent <= 5

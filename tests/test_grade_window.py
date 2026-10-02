"""Window timing for the semantic grade, and that old presets are untouched."""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import grade  # noqa: E402


def test_weight_is_zero_outside_and_one_inside():
    assert grade.window_weight(0.99, 1.0, 2.0, 0.1) == 0.0
    assert grade.window_weight(2.01, 1.0, 2.0, 0.1) == 0.0
    assert grade.window_weight(1.5, 1.0, 2.0, 0.1) == 1.0


def test_weight_eases_in_and_out_symmetrically():
    assert grade.window_weight(1.05, 1.0, 2.0, 0.1) == pytest.approx(0.5)
    assert grade.window_weight(1.95, 1.0, 2.0, 0.1) == pytest.approx(0.5)
    ramp = [grade.window_weight(1.0 + i * 0.01, 1.0, 2.0, 0.1) for i in range(11)]
    assert ramp == sorted(ramp)


def test_short_window_still_reaches_full_strength():
    t0, t1, ease = grade.parse_window("1.0:1.1", 0.1)
    assert ease == pytest.approx(0.05)
    assert grade.window_weight(1.05, t0, t1, ease) == pytest.approx(1.0)


@pytest.mark.parametrize("bad", ["1.0", "a:b", "2:1", "-1:2", "1:1"])
def test_bad_windows_are_rejected(bad):
    with pytest.raises(ValueError):
        grade.parse_window(bad)


def test_window_filter_blends_source_with_graded_copy():
    vf = grade.apply_window(grade.LOSS_RED, 1.0, 2.0, 0.1)
    assert vf.startswith("split[a][b];[b]colorbalance")
    assert "blend=all_expr=" in vf and "T-1.0000" in vf and "2.0000-T" in vf


def test_existing_presets_are_unchanged():
    assert grade.build_filter("warm_lift", "normal") == (
        "curves=all='0/0.040 0.5/0.580 1/0.99',"
        "eq=brightness=0.040:contrast=1.080:saturation=1.080:gamma=1.060,"
        "colortemperature=temperature=5200,unsharp=5:5:0.3")
    assert grade.build_filter("none", "normal") is None
    assert grade.build_filter("eq=contrast=1.2", "normal") == "eq=contrast=1.2"

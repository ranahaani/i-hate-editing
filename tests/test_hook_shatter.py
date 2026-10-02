"""Shatter geometry: timing, determinism, and flight paths clear of the face."""

import math
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "templates" / "hook"))

import shatter  # noqa: E402

ZONE = {"x": 90, "y": 330, "w": 900, "h": 260}
FACE = {"x": 250, "y": 640, "w": 580, "h": 600}


def test_timing_gives_a_legible_lead_and_a_0_4s_shatter():
    t_in, t_end = shatter.timing(1.8)
    assert t_in == pytest.approx(0.7)
    assert t_end - 1.8 >= shatter.SHATTER_SECONDS


def test_early_hit_never_starts_before_zero():
    assert shatter.timing(0.5)[0] == 0.0


def test_geometry_is_deterministic():
    a = shatter.build_shards(ZONE, FACE, seed=3)
    b = shatter.build_shards(ZONE, FACE, seed=3)
    assert a == b


def test_zone_over_face_is_refused():
    with pytest.raises(ValueError, match="overlaps the face"):
        shatter.validate({"x": 300, "y": 700, "w": 400, "h": 200}, FACE)


def test_zone_outside_frame_is_refused():
    with pytest.raises(ValueError, match="leaves the frame"):
        shatter.validate({"x": 900, "y": 100, "w": 400, "h": 200}, None)


@pytest.mark.parametrize("zone,face", [
    (ZONE, FACE),
    ({"x": 90, "y": 330, "w": 900, "h": 300}, {"x": 250, "y": 640, "w": 580, "h": 600}),
    ({"x": 40, "y": 700, "w": 220, "h": 500}, {"x": 400, "y": 600, "w": 500, "h": 700}),
])
def test_every_flight_stays_clear_of_the_face(zone, face):
    for s in shatter.build_shards(zone, face, seed=11):
        assert shatter.path_clear(s["box"], s["dx"], s["dy"], face), s


def test_shards_tile_the_word_box():
    shards = shatter.build_shards(ZONE, None)
    assert len(shards) == 24                 # stays under hyperframes' heavy-overlay warning
    area = 0.0
    for s in shards:
        p = s["poly"]
        area += abs(sum(p[i][0] * p[(i + 1) % 3][1] - p[(i + 1) % 3][0] * p[i][1]
                        for i in range(3))) / 2
    assert area == pytest.approx(100 * 100, rel=1e-3)


def test_build_emits_one_hit_tween_per_shard_at_t_hit():
    out = shatter.build("never", 1.8, ZONE, FACE)
    hits = [a for a in out["anims"] if ", 1.8" in a and "rotation" in a]
    assert len(hits) == out["shards"]
    assert 'data-track-index="55"' in out["clips"][0]
    assert math.isclose(out["t_in"], 0.7)

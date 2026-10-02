"""Zone-ranking and geometry tests for safe_zone.py. No video, no OpenCV."""

import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import safe_zone as sz  # noqa: E402


def overlaps(a, b):
    ax, ay, aw, ah = a
    bx, by, bw, bh = b
    return ax < bx + bw and bx < ax + aw and ay < by + bh and by < ay + ah


def zone_box(z):
    return (z["x"], z["y"], z["w"], z["h"])


def test_safe_rect_uses_studio_margins():
    # header 15% (288), text above 27% from bottom (1402), right 15% (918),
    # side margin 5% (54); the 4:5 crop (285..1635) is looser than all of them.
    assert sz.safe_rect() == (54, 288, 918, 1402)


def test_chest_up_face_picks_below():
    head = (300, 400, 480, 780)
    zones, chosen, shrink = sz.rank_zones(head)
    assert chosen["zone"] == "below"
    assert shrink is None
    assert chosen["y"] >= head[1] + head[3] + sz.FACE_PAD


def test_zones_ranked_widest_gap_first():
    head = (100, 300, 300, 700)  # tall, off-centre left: right gap 518 > below 402
    zones, chosen, _ = sz.rank_zones(head, need_w=200, need_h=100)
    gaps = [z["gap"] for z in zones]
    assert gaps == sorted(gaps, reverse=True)
    assert zones[0]["zone"] == "right"
    assert chosen["zone"] == "right"


def test_chosen_is_best_ranked_zone_that_fits():
    head = (100, 300, 300, 700)
    zones, chosen, _ = sz.rank_zones(head, need_w=600, need_h=100)
    first_fit = next(z for z in zones if z["fits"])
    assert chosen == first_fit
    assert chosen["zone"] != "right"  # right column too narrow for 600px


def test_never_overlaps_head_for_any_box():
    rng = random.Random(7)
    for _ in range(500):
        w, h = rng.randint(100, 800), rng.randint(100, 1200)
        head = (rng.randint(-50, 1000), rng.randint(0, 1500), w, h)
        zones, chosen, _ = sz.rank_zones(head, need_w=150, need_h=80)
        for z in zones:
            assert not overlaps(zone_box(z), head), (head, z)
        if chosen:
            assert chosen["fits"]


def test_zones_stay_inside_safe_area():
    sx0, sy0, sx1, sy1 = sz.safe_rect()
    zones, _, _ = sz.rank_zones((400, 600, 300, 400))
    for z in zones:
        assert z["x"] >= sx0 and z["y"] >= sy0
        assert z["x"] + z["w"] <= sx1 and z["y"] + z["h"] <= sy1


def test_no_clear_zone_returns_shrink_not_overlap():
    # Head fills most of the safe area; only a narrow left column remains.
    head = (330, 250, 600, 1250)
    zones, chosen, shrink = sz.rank_zones(head, need_w=360, need_h=140)
    assert chosen is None
    assert shrink is not None and 0 < shrink < 1
    for z in zones:
        assert not overlaps(zone_box(z), head)


def test_shrink_is_none_when_even_shrunk_text_cannot_fit():
    head = (60, 250, 860, 1250)  # head spans the whole safe width
    zones, chosen, shrink = sz.rank_zones(head, need_w=360, need_h=140)
    assert chosen is None
    assert shrink is None


def test_transform_identity_without_zoom():
    box = (400, 600, 300, 400)
    out = sz.transform_box(box, 1080, 1920, zoom=1.0)
    assert [round(v, 3) for v in out] == list(box)


def test_transform_matches_render_crop_math():
    # render.py: crop=iw/z:ih/z:(iw-iw/z)/2:(ih-ih/z)*zoom_y, then scale to fit.
    z, zy = 1.55, 0.30
    cw, ch = 1080 / z, 1920 / z
    cx, cy = (1080 - cw) / 2, (1920 - ch) * zy
    box = (400, 600, 300, 400)
    x, y, w, h = sz.transform_box(box, 1080, 1920, z, zy)
    assert abs(x - (400 - cx) * z) < 1e-6
    assert abs(y - (600 - cy) * z) < 1e-6
    assert abs(w - 300 * z) < 1e-6 and abs(h - 400 * z) < 1e-6


def test_transform_letterboxes_landscape_source():
    # 1920x1080 source fits to width 1080 (scale 0.5625), padded top/bottom.
    x, y, w, h = sz.transform_box((0, 0, 1920, 1080), 1920, 1080)
    assert round(x) == 0 and round(w) == 1080 and round(h) == 608
    assert round(y) == (1920 - 608) // 2


def test_zoom_pushes_face_into_a_smaller_clear_zone():
    face = (400, 600, 280, 380)
    before = sz.rank_zones(sz.expand_head(face))[1]
    zoomed = sz.transform_box(face, 1080, 1920, 1.55, 0.30)
    after = sz.rank_zones(sz.expand_head(zoomed))[1]
    assert before is not None
    assert after is None or after["h"] < before["h"] or after["zone"] != "below"

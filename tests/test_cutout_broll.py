"""Gate math for cutout_broll on synthetic arrays — no media, no model.

Run with the virtual-bg venv: ~/.cache/virtual-bg/venv/bin/python -m pytest
"""

import sys
from pathlib import Path

import cv2
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import cutout_broll as cb  # noqa: E402

RNG = np.random.default_rng(7)


def textured(h=200, w=200):
    return RNG.integers(0, 256, (h, w), dtype=np.uint8)


def test_blur_loses_detail_and_ratio_reflects_it():
    sharp = textured()
    soft = cv2.GaussianBlur(sharp, (0, 0), 2)
    mask = np.ones(sharp.shape, bool)
    s, o = cb.laplacian_variance(sharp, mask), cb.laplacian_variance(soft, mask)
    ratio, worst, n = cb.detail_ratio([s], [o])
    assert o < s and ratio < 0.3 and worst == ratio and n == 1


def test_identical_pixels_measure_exactly_one():
    img = textured()
    mask = np.ones(img.shape, bool)
    v = cb.laplacian_variance(img, mask)
    assert cb.detail_ratio([v, v], [v, v])[0] == 1.0


def test_tiny_region_is_not_measurable():
    img = textured()
    mask = np.zeros(img.shape, bool)
    mask[:5, :5] = True
    assert cb.laplacian_variance(img, mask) is None
    assert cb.detail_ratio([None], [None]) == (None, None, 0)


def test_detail_ratio_skips_unmeasured_frames_and_reports_worst():
    ratio, worst, n = cb.detail_ratio([100, None, 100], [90, 50, 70])
    assert n == 2 and abs(ratio - 0.8) < 1e-9 and abs(worst - 0.7) < 1e-9


def test_verdict_threshold_is_inclusive_at_085():
    assert cb.verdict(0.85, 0.85)
    assert not cb.verdict(0.8499, 0.95)
    assert not cb.verdict(0.95, 0.8499)


def test_verdict_fails_when_a_region_was_not_measured():
    assert not cb.verdict(None, 0.99)
    assert not cb.verdict(0.99, None)


def test_verdict_fails_on_see_through_matte_even_with_perfect_detail():
    assert cb.verdict(1.0, 1.0, translucent=cb.TRANSLUCENT_MAX)
    assert not cb.verdict(1.0, 1.0, translucent=cb.TRANSLUCENT_MAX + 0.01)


def test_motion_mask_finds_moved_pixels_only_inside_the_subject():
    prev = np.zeros((120, 120), np.uint8)
    cur = prev.copy()
    cur[40:60, 40:60] = 200      # moved, inside subject
    cur[90:110, 90:110] = 200    # moved, outside subject
    subject = np.zeros(prev.shape, bool)
    subject[:80, :80] = True
    m = cb.motion_mask(prev, cur, subject)
    assert m[50, 50] and not m[100, 100] and not m[5, 5]


def test_composite_keeps_source_bit_exact_where_solid_and_blends_at_edge():
    src = RNG.integers(0, 256, (20, 20, 3), dtype=np.uint8)
    plate = np.full((20, 20, 3), 255, np.uint8)
    alpha = np.full((20, 20), 255, np.uint8)
    alpha[:, :5] = 0
    alpha[:, 5:8] = 128
    out = cb.composite(src, plate, alpha)
    assert np.array_equal(out[:, 8:], src[:, 8:])
    assert np.array_equal(out[:, :5], plate[:, :5])
    expected = (src[:, 5:8].astype(float) * 128 / 255 + 255 * (1 - 128 / 255)).round()
    assert np.abs(out[:, 5:8].astype(float) - expected).max() <= 1


def test_translucent_share_is_zero_for_a_solid_subject_and_catches_a_hole():
    solid = np.zeros((200, 200), np.uint8)
    solid[40:180, 40:160] = 255
    assert cb.translucent_interior_share(solid) == 0.0
    holed = solid.copy()
    holed[90:110, 90:110] = 0   # a held object the matte dropped
    assert cb.translucent_interior_share(holed) > 0.01


def test_translucent_share_ignores_soft_edges():
    a = np.zeros((200, 200), np.uint8)
    a[40:180, 40:160] = 255
    a = cv2.GaussianBlur(a, (0, 0), 2)  # honest soft edge
    assert cb.translucent_interior_share(a) < 0.01


def test_translucent_share_counts_a_half_transparent_hand():
    a = np.zeros((200, 200), np.uint8)
    a[40:180, 40:160] = 255
    a[80:140, 80:140] = 140
    assert cb.translucent_interior_share(a) > 0.1


def test_halo_detects_a_bright_fringe_and_not_a_clean_edge():
    h, w = 120, 120
    alpha = np.zeros((h, w), np.uint8)
    alpha[:, 60:] = 255
    alpha[:, 56:60] = 128                      # edge band
    dark_subject = np.full((h, w, 3), 60, np.uint8)
    dark_plate = np.full((h, w, 3), 70, np.uint8)
    clean = cb.composite(dark_subject, dark_plate, alpha)
    assert cb.halo_fraction(clean, dark_subject, dark_plate, alpha) == 0.0
    fringe_src = dark_subject.copy()
    fringe_src[:, 56:60] = 240                 # old bright room bleeding into the edge
    fringed = cb.composite(fringe_src, dark_plate, alpha)
    assert cb.halo_fraction(fringed, fringe_src, dark_plate, alpha) > 0.5


def test_band_visibility_reports_empty_top_and_covered_bottom():
    union = np.zeros((100, 60), np.uint8)
    union[55:, :] = 255
    union[22:55, 20:40] = 255
    bands = cb.band_visibility(union)
    assert bands["0-22%"] == 1.0 and bands["55-100%"] == 0.0 and 0.0 < bands["22-55%"] < 1.0


def test_plate_crop_slides_to_detail_in_the_visible_region():
    plate = np.zeros((100, 300, 3), np.uint8)
    plate[:, 200:300] = RNG.integers(0, 256, (100, 100, 3), dtype=np.uint8)  # detail only on the right
    visible = np.ones((100, 100), bool)
    crop, offset = cb.pick_plate_crop(plate, 100, 100, visible)
    assert crop.shape == (100, 100, 3) and offset >= 150
    assert cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY).std() > 40

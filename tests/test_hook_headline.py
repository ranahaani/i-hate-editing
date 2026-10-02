"""Headline rules: word count, orphan words, line breaks, placement, mark crop."""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "templates" / "hook"))

import headline  # noqa: E402

ZONE = {"x": 54, "y": 288, "w": 864, "h": 166}
FACE = {"x": 389, "y": 695, "w": 452, "h": 575}
SHATTER_ZONE = {"x": 90, "y": 1300, "w": 900, "h": 230}
MARK = {"mode": "logo", "src": None}


# --------------------------------------------------------- word count guard

@pytest.mark.parametrize("lines", [["LIMIT HIT?"], ["ONE", "TWO"]])
def test_fewer_than_three_words_is_an_error(lines):
    with pytest.raises(ValueError, match="word"):
        headline.check_word_count(lines)


@pytest.mark.parametrize("n", [3, 4, 5])
def test_three_to_five_words_pass_clean(n):
    lines = [" ".join(["WORD"] * n)]
    assert headline.check_word_count(lines) == []


def test_six_words_pass_with_a_warning():
    warnings = headline.check_word_count(["ONE TWO THREE", "FOUR FIVE SIX"])
    assert len(warnings) == 1 and "6 words" in warnings[0]


def test_seven_words_is_an_error():
    with pytest.raises(ValueError, match="ceiling"):
        headline.check_word_count(["ONE TWO THREE FOUR", "FIVE SIX SEVEN"])


# ------------------------------------------------------------ orphan words

def test_the_old_defect_is_refused():
    with pytest.raises(ValueError, match="orphan"):
        headline.check_layout(["WHEN YOUR LIMIT RUNS", "OUT"])


def test_single_word_last_line_in_three_lines_is_refused():
    with pytest.raises(ValueError, match="orphan"):
        headline.check_layout(["SAVE", "THE", "SESSION"])


def test_line_ending_on_a_connector_is_refused():
    with pytest.raises(ValueError, match="connector"):
        headline.check_layout(["SAVE THE", "SESSION NOW"])


def test_good_stack_passes():
    headline.check_layout(["LIMIT HIT?", "SAVE THE SESSION"])
    headline.check_layout(["FREE", "LLM API"])


@pytest.mark.parametrize("n", [1, 4])
def test_line_count_must_be_two_or_three(n):
    with pytest.raises(ValueError, match="line"):
        headline.check_layout(["WORD WORD"] * n)


def test_empty_line_is_refused():
    with pytest.raises(ValueError, match="empty"):
        headline.check_layout(["ONE TWO", "  "])


# ------------------------------------------------------------ auto breaking

def test_auto_break_never_strands_a_word():
    cases = ["WHEN YOUR LIMIT RUNS OUT", "LIMIT HIT? SAVE THE SESSION",
             "FREE LLM API", "STOP PAYING FOR AI", "THIS PROMPT SAVES HOURS"]
    for text in cases:
        lines = headline.break_lines(text)
        assert len(lines[-1].split()) >= 2, lines
        headline.check_layout(lines)
        assert " ".join(lines) == text


def test_auto_break_prefers_the_punctuation_break():
    assert headline.break_lines("LIMIT HIT? SAVE THE SESSION") == [
        "LIMIT HIT?", "SAVE THE SESSION"]


def test_auto_break_keeps_connector_with_its_noun():
    lines = headline.break_lines("SAVE THE SESSION NOW")
    assert not lines[0].endswith("THE")


def test_auto_break_is_deterministic():
    text = "STOP PAYING FOR AI"
    assert headline.break_lines(text) == headline.break_lines(text)


def test_auto_break_checks_the_word_guard_first():
    with pytest.raises(ValueError, match="word"):
        headline.break_lines("TOO SHORT")
    with pytest.raises(ValueError, match="ceiling"):
        headline.break_lines("ONE TWO THREE FOUR FIVE SIX SEVEN")


def test_resolve_lines_validates_a_given_list():
    with pytest.raises(ValueError, match="orphan"):
        headline.resolve_lines(["WHEN YOUR LIMIT RUNS", "OUT"])
    lines, warnings = headline.resolve_lines(["LIMIT HIT?", "SAVE THE SESSION"])
    assert lines == ["LIMIT HIT?", "SAVE THE SESSION"] and warnings == []


# ------------------------------------------------------------- claim word

def test_claim_word_is_found_ignoring_case_and_punctuation():
    assert headline.pick_claim(["LIMIT HIT?", "SAVE THE SESSION"], "save") == 2
    assert headline.pick_claim(["LIMIT HIT?", "SAVE THE SESSION"], "hit") == 1


def test_unknown_claim_word_is_refused():
    with pytest.raises(ValueError, match="not in the headline"):
        headline.pick_claim(["LIMIT HIT?", "SAVE THE SESSION"], "NEVER")


def test_default_claim_skips_connectors():
    lines = ["STOP PAYING", "FOR AI"]
    assert headline.pick_claim(lines) == 1


# ---------------------------------------------------------------- placement

def test_zone_over_the_face_is_refused():
    with pytest.raises(ValueError, match="overlaps the face"):
        headline.validate_placement({"x": 54, "y": 600, "w": 864, "h": 200}, FACE, [])


def test_zone_over_the_shatter_zone_is_refused():
    with pytest.raises(ValueError, match="another zone"):
        headline.validate_placement(ZONE, FACE, [{"x": 100, "y": 300, "w": 500, "h": 200}])


def test_clear_zone_is_accepted():
    headline.validate_placement(ZONE, FACE, [SHATTER_ZONE])


def test_zone_outside_the_frame_is_refused():
    with pytest.raises(ValueError, match="leaves the frame"):
        headline.validate_placement({"x": 900, "y": 100, "w": 400, "h": 160}, None, [])


def test_hold_shorter_than_the_dwell_floor_is_refused():
    with pytest.raises(ValueError, match="hold it"):
        headline.validate_timing(0.1, 1.0)
    headline.validate_timing(0.1, 3.2)


def test_mark_is_sized_from_the_cap_height_and_never_under_a_readable_face():
    cap = headline.cap_height_px(150)
    assert headline.mark_for_font(150) == round(cap * headline.MARK_CAP_RATIO)
    assert headline.mark_for_font(40) == headline.MIN_MARK_PX


# ---------------------------------------------------------------- the crop

def test_crop_is_square_centred_and_inside_the_image():
    left, top, side = headline.crop_square(1200, 1200, (360, 3, 370, 648))
    assert side == pytest.approx(648 * headline.CHIP_CROP_MARGIN)
    assert 0 <= left and left + side <= 1200
    assert 0 <= top and top + side <= 1200
    assert left + side / 2 == pytest.approx(360 + 185)   # head centre kept on x


def test_crop_slides_back_inside_rather_than_padding():
    left, top, side = headline.crop_square(1200, 1200, (0, 0, 300, 300))
    assert (left, top) == (0, 0)


def test_crop_shrinks_to_a_small_image():
    _, _, side = headline.crop_square(500, 400, (50, 50, 380, 380))
    assert side == 400


# ----------------------------------------------------------------- the build

def test_build_refuses_without_an_assets_dir(tmp_path):
    svg = tmp_path / "m.svg"
    svg.write_text("<svg xmlns='http://www.w3.org/2000/svg'/>")
    with pytest.raises(ValueError, match="assets_dir"):
        headline.build("LIMIT HIT? SAVE THE SESSION", "#D97757",
                       {"mode": "logo", "src": str(svg)}, 0.08, 3.2, ZONE)


def test_build_returns_the_shatter_shape_and_track_50(tmp_path):
    svg = tmp_path / "m.svg"
    svg.write_text("<svg xmlns='http://www.w3.org/2000/svg'/>")
    font = tmp_path / "f.ttf"
    font.write_bytes(b"\0")
    frag = headline.build(["LIMIT HIT?", "SAVE THE SESSION"], "#D97757",
                          {"mode": "logo", "src": str(svg)}, 0.08, 3.2, ZONE, FACE,
                          avoid=[SHATTER_ZONE], accent_word="SAVE",
                          assets_dir=tmp_path / "a", font_file=font)
    assert {"css", "clips", "anims"} <= set(frag)
    assert 'data-track-index="50"' in frag["clips"][0]
    css = frag["css"]
    assert "#D97757" in css and "@font-face" in css
    assert css.count("hl-claim") >= 1 and "SAVE" in frag["clips"][0]
    anims = "\n".join(frag["anims"])
    assert "opacity" not in anims                      # never a fade
    assert "back.out" in anims                         # overshoot snap
    assert f"{0.08:.3f}" in anims                      # entrance starts at t_in


def test_splice_inserts_everywhere_and_survives_a_second_fragment():
    html = ("<style>\n    </style>\n<div>\n    </div>\n\n    <script>\n"
            '      window.__timelines["main"] = tl;\n')
    frag = {"css": "A", "clips": ["B"], "anims": ["C"]}
    out = headline.splice(html, frag)
    out = headline.splice(out, {"css": "D", "clips": ["E"], "anims": ["F"]})
    for token in "ABCDEF":
        assert token in out

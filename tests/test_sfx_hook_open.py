"""Placement and budget logic for the hook-open hit — no media required."""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import sfx  # noqa: E402

TAXONOMY = Path(__file__).resolve().parents[1] / "assets" / "sfx-taxonomy.json"


def ev(at, category, mandatory=True):
    return {"at": at, "category": category, "why": "t", "mandatory": mandatory}


def test_earliest_visual_event_inside_window_wins():
    assert sfx.first_visual_event([4.0, 1.1, 0.7, 1.4]) == 0.7


def test_visual_event_outside_window_is_ignored():
    assert sfx.first_visual_event([1.6, 3.0]) is None
    assert sfx.first_visual_event([]) is None


def test_window_edge_is_inclusive():
    assert sfx.first_visual_event([sfx.HOOK_WINDOW]) == sfx.HOOK_WINDOW


def test_anchors_to_visual_event_not_to_word():
    hook, why = sfx.hook_open_event([0.9], post_hook_at=6.0, word_onset=0.2)
    assert why is None
    assert hook["at"] == 0.9
    assert hook["category"] == "hook_open"
    assert hook["mandatory"] is True


def test_falls_back_to_word_onset_when_no_visual_event():
    hook, _ = sfx.hook_open_event([3.0], post_hook_at=6.0, word_onset=0.3)
    assert hook["at"] == 0.3 + sfx.HOOK_ONSET_LAG
    assert "no visual event" in hook["why"]


def test_no_anchor_means_no_hook_open():
    hook, reason = sfx.hook_open_event([3.0], post_hook_at=6.0, word_onset=None)
    assert hook is None and reason


def test_late_word_onset_is_not_a_hook_open():
    hook, _ = sfx.hook_open_event([], post_hook_at=None, word_onset=1.5)
    assert hook is None


def test_hit_never_lands_before_minimum():
    hook, _ = sfx.hook_open_event([0.0], post_hook_at=6.0)
    assert hook["at"] == sfx.HOOK_MIN_AT


def test_skipped_when_post_hook_impact_is_the_same_moment():
    hook, reason = sfx.hook_open_event([1.0], post_hook_at=1.0)
    assert hook is None
    assert "post-hook" in reason


def test_skipped_when_post_hook_impact_is_inside_clear_zone():
    hook, _ = sfx.hook_open_event([0.8], post_hook_at=0.8 + sfx.HOOK_CLEAR - 0.01)
    assert hook is None


def test_kept_when_post_hook_impact_is_clear():
    hook, _ = sfx.hook_open_event([0.8], post_hook_at=0.8 + sfx.HOOK_CLEAR + 0.01)
    assert hook is not None


def test_replaces_whoosh_on_same_cut_and_card():
    hook = ev(1.0, "hook_open")
    events = [ev(1.0, "whoosh_light"), ev(1.12, "whoosh_deep"), ev(1.3, "pop", False),
              ev(4.0, "whoosh_light")]
    out = sfx.apply_hook_open(events, hook)
    assert [e["category"] for e in out] == ["hook_open", "whoosh_light"]
    assert out[1]["at"] == 4.0


def test_exactly_one_sound_in_the_hook_clear_zone():
    hook = ev(0.7, "hook_open")
    events = [ev(0.7, "whoosh_light"), ev(0.9, "glitch"), ev(1.2, "click", False)]
    out = sfx.apply_hook_open(events, hook)
    zone = [e for e in out if abs(e["at"] - 0.7) < sfx.HOOK_CLEAR]
    assert [e["category"] for e in zone] == ["hook_open"]


def test_no_hook_leaves_events_untouched_and_does_not_mutate():
    events = [ev(1.0, "whoosh_light")]
    out = sfx.apply_hook_open(events, None)
    assert out == events and out is not events


def test_apply_does_not_mutate_input():
    events = [ev(1.0, "whoosh_light")]
    sfx.apply_hook_open(events, ev(1.0, "hook_open"))
    assert [e["category"] for e in events] == ["whoosh_light"]


def test_output_is_time_sorted():
    out = sfx.apply_hook_open([ev(5.0, "pop"), ev(0.1, "click")], ev(1.0, "hook_open"))
    assert [e["at"] for e in out] == sorted(e["at"] for e in out)


def test_hook_open_is_mandatory_so_it_counts_against_the_budget():
    hook, _ = sfx.hook_open_event([1.0], post_hook_at=6.0)
    assert hook["mandatory"] is True


def test_taxonomy_entry_follows_calibration_style():
    spec = sfx.taxonomy_spec("hook_open")
    assert spec["mixkit"] == "impact"
    assert -18 <= spec["peak_db"] <= -10
    assert 0 < spec["volume"] <= 1.0
    import compose
    assert spec["track"] <= compose.AUDIO_TRACK_CEILING


def test_taxonomy_track_is_unique():
    cats = [c for g in json.loads(TAXONOMY.read_text())["groups"].values()
            for c in g["categories"].values()]
    hook_track = sfx.taxonomy_spec("hook_open")["track"]
    assert sum(1 for c in cats if c["track"] == hook_track) == 1


def test_trimmed_hit_fits_placement_window():
    assert sfx.HOOK_HIT_LEN == sfx.HOOK_HIT_PRE + 0.45
    assert sfx.HOOK_HIT_FADE < sfx.HOOK_HIT_LEN

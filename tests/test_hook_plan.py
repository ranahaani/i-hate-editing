"""hook_plan decisions: mark ladder, concept map, accent, treatment, sizing."""

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "templates" / "hook"))

import headline  # noqa: E402
import hook_plan as hp  # noqa: E402

MANIFEST = {"entities": {"anthropic": {"file": "anthropic.png", "stands_for": "Anthropic / Claude",
                                       "registered_by": "user", "licence": "unknown", "use": "chip"}}}
OK = {"ok": True, "failed": [], "metrics": {"sharpness": 500}}
BAD = {"ok": False, "failed": ["sharpness"], "metrics": {"sharpness": 20}}
LOGO = {"mode": "logo", "src": "x.svg", "name": "NVIDIA", "aspect": 1.5, "aspect_check": "rendered"}
ICON = lambda name, _w: ({"mode": "icon", "name": name, "set": "lucide", "src": f"{name}.svg"}, None)  # noqa: E731
NO_LOGO = lambda c, w: (None, "no exact Simple Icons entry")  # noqa: E731
YES_LOGO = lambda c, w: (LOGO, None)  # noqa: E731


def ladder(entity, text="", words=(), photo=lambda p: OK, logo=NO_LOGO, icon=ICON):
    return hp.choose_mark(entity, text, list(words), "/tmp/x", MANIFEST, photo, logo, icon)


# ------------------------------------------------------------- mark ladder

def test_suitable_face_wins_rung_one():
    r = ladder("Claude/Anthropic", "your Claude limit", ["LIMIT"])
    assert r["rung"] == 1 and r["mark"]["mode"] == "face" and r["rejected"] == []
    assert r["mark"]["src"].endswith("anthropic.png")


def test_unsuitable_face_falls_to_logo_and_records_why():
    r = ladder("Claude/Anthropic", photo=lambda p: BAD, logo=YES_LOGO)
    assert r["rung"] == 2
    assert r["rejected"][0]["rung"] == 1 and "sharpness" in r["rejected"][0]["reason"]


def test_entity_without_face_skips_rung_one():
    r = ladder("NVIDIA", logo=YES_LOGO)
    assert r["rung"] == 2
    assert "no face registered" in r["rejected"][0]["reason"]


def test_logo_rejected_falls_to_icon_by_keyword():
    r = ladder("NVIDIA", "the limit is gone", ["LIMIT"], logo=NO_LOGO)
    assert r["rung"] == 3 and r["mark"]["name"] == "clock"
    assert [x["rung"] for x in r["rejected"]] == [1, 2]


def test_no_entity_goes_straight_to_icon():
    r = ladder(None, "free api key", ["FREE", "API", "KEY"])
    assert r["rung"] == 3 and r["mark"]["name"] == "key"
    assert all("no entity" in x["reason"] for x in r["rejected"])


def test_icon_fetch_failure_is_an_error():
    with pytest.raises(hp.PlanError):
        ladder(None, "limit", ["LIMIT"], icon=lambda n, w: (None, "404"))


def test_manifest_matches_either_name_and_never_a_stranger():
    assert hp.manifest_entry(MANIFEST, ["Claude"])[0] == "anthropic"
    assert hp.manifest_entry(MANIFEST, ["Anthropic"])[0] == "anthropic"
    assert hp.manifest_entry(MANIFEST, ["OpenAI"]) == (None, None)


def test_entity_candidates():
    assert hp.entity_candidates("Claude/Anthropic") == ["Claude", "Anthropic"]
    assert hp.entity_candidates(None) == [] and hp.entity_candidates("none") == []


# ------------------------------------------------------------- concept map

@pytest.mark.parametrize("text,icon", [
    ("you hit the limit", "clock"), ("get a free api key", "key"),
    ("so much faster", "zap"), ("saves money", "coins"), ("no unlimited plan", "infinity")])
def test_concept_map(text, icon):
    assert hp.pick_concept([], text)[0] == icon


def test_concept_map_misses_cleanly_and_stays_small():
    assert hp.pick_concept(["HELLO", "WORLD"], "hello world") == (None, None)
    assert len(hp.CONCEPTS) <= 12


def test_headline_words_beat_the_rest_of_the_hook():
    assert hp.pick_concept(["MONEY"], "the limit is real")[0] == "coins"


# ------------------------------------------------------- lines and accent

def test_short_hook_is_used_as_spoken():
    c = hp.headline_candidates("Free LLM API")
    assert len(c) == 1 and c[0]["words"] == ["FREE", "LLM", "API"]


def test_long_hook_is_distilled_to_four_then_three_words():
    c = hp.headline_candidates("Imagine you hit your Claude limit mid-work and your session is gone",
                               frozenset({"claude"}))
    assert [len(x["words"]) for x in c[:1]] == [4]
    assert {len(x["words"]) for x in c} == {3, 4}
    assert c[0]["words"] == ["HIT", "CLAUDE", "LIMIT", "GONE"]   # entity and loss word kept
    assert {"Imagine", "you", "your", "and"} <= set(c[0]["dropped"])
    assert c[0]["dropped_why"]["Imagine"] == "filler, connector or pronoun"


def test_condenser_is_deterministic_and_never_invents_words():
    text = "Imagine you hit your Claude limit mid-work and your session is gone"
    a = hp.headline_candidates(text, frozenset({"claude"}))
    assert a == hp.headline_candidates(text, frozenset({"claude"}))
    spoken = {w.upper() for w in text.split()}
    assert all(set(c["words"]) <= spoken and len(c["words"]) <= 5 for c in a)


def test_headline_override_is_validated():
    assert hp.headline_candidates("x", override="LIMIT HIT NOW")[0]["words"] == ["LIMIT", "HIT", "NOW"]
    with pytest.raises(hp.PlanError):
        hp.headline_candidates("x", override="TOO SHORT")


def test_too_few_meaning_words_is_an_error():
    with pytest.raises(hp.PlanError):
        hp.headline_candidates("and you are the one to be")


def test_accent_prefers_loss_then_skips_connectors_and_entity():
    words = ["CLAUDE", "LIMIT", "SESSION", "GONE"]
    assert words[hp.claim_order(words, frozenset({"claude"}))[0]] == "GONE"
    free = ["FREE", "LLM", "API"]
    assert free[hp.claim_order(free, frozenset())[0]] == "FREE"
    order = hp.claim_order(["SAVE", "THE", "CLAUDE"], frozenset({"claude"}))
    assert order[0] == 0 and order[-1] in (1, 2)


def test_forced_accent_word():
    assert hp.claim_order(["A1", "LIMIT", "HIT"], frozenset(), "hit") == [2]
    with pytest.raises(hp.PlanError):
        hp.claim_order(["A", "B", "C"], frozenset(), "zzz")


# -------------------------------------------------------------- treatment

def W(*pairs):
    return [{"word": w, "start": s, "end": s + 0.3} for w, s in pairs]


ZONES = [{"name": "below", "tier": "safe", "x": 54, "y": 1250, "w": 864, "h": 300, "gap": 100}]
HEAD_ZONE = {"x": 54, "y": 182, "w": 864, "h": 313}
FACE = {"x": 437, "y": 745, "w": 368, "h": 427}


def test_loss_word_gets_grade_and_shatter_when_a_zone_is_clear():
    t = hp.choose_treatment(W(("it", 0.1), ("is", 0.3), ("gone", 0.8)), "GONE", HEAD_ZONE, ZONES, FACE)
    assert t["kind"] == "loss_red+shatter" and t["word"] == "GONE"
    assert t["grade"]["preset"] == "loss_red" and t["grade"]["window"] == "0.80:1.35"
    assert t["shatter"]["t_hit"] == 0.8


def test_loss_word_grade_only_without_a_shatter_zone():
    t = hp.choose_treatment(W(("never", 0.2)), "NEVER", HEAD_ZONE, [], FACE)
    assert t["kind"] == "loss_red" and "shatter" not in t


def test_shatter_zone_must_not_touch_the_headline():
    zones = [{"name": "above", "tier": "safe", "x": 54, "y": 288, "w": 864, "h": 200, "gap": 1}]
    assert hp.pick_shatter_zone(zones, HEAD_ZONE, FACE) is None


def test_number_gets_held_zoom_and_no_grade():
    t = hp.choose_treatment(W(("save", 0.1), ("10x", 0.5)), "SAVE", HEAD_ZONE, ZONES, FACE)
    assert t["kind"] == "held_zoom" and t["word"] == "10X" and "grade" not in t


def test_neutral_hook_has_no_treatment_and_loss_beats_number():
    assert hp.choose_treatment(W(("hello", 0.1), ("world", 0.4)), "HELLO", HEAD_ZONE, ZONES, FACE)["kind"] == "none"
    t = hp.choose_treatment(W(("10x", 0.1), ("never", 0.5)), "10X", HEAD_ZONE, [], FACE)
    assert t["kind"] == "loss_red"


def test_strong_loss_word_beats_soft_when_not_in_headline():
    t = hp.choose_treatment(W(("limit", 0.2), ("gone", 0.9)), "SESSION", HEAD_ZONE, [], FACE)
    assert t["word"] == "GONE"


def test_word_timing_uses_chunks_else_spreads_by_letters():
    spread = hp.timed_words("aa bbbb", None, 0.0, 3.0)
    assert spread[0]["start"] == 0.0 and spread[-1]["end"] == pytest.approx(3.0)
    chunks = [{"text": "one two", "start": 1.0, "end": 2.0}]
    assert hp.timed_words("", chunks, 0, 3)[0]["start"] == 1.0
    exact = [{"text": "a b", "start": 0, "end": 1, "words": [{"word": "a", "start": 0.4, "end": 0.5}]}]
    assert hp.timed_words("", exact, 0, 3)[0]["start"] == 0.4


def test_hook_open_anchors_on_the_headline_entrance():
    r = hp.hook_open_anchor(0.08, [], 0.0, 3.2)
    assert not r["skipped"] and r["at"] == pytest.approx(0.15)       # clamped to HOOK_MIN_AT
    r = hp.hook_open_anchor(2.0, [], 0.0, 3.2)
    assert not r["skipped"] and "first word" in r["why"]


# ----------------------------------------------------- size and reflow

def zone(name, h, y=100, w=864, tier="safe"):
    return {"name": name, "tier": tier, "x": 54, "y": y, "w": w, "h": h, "gap": 0,
            "intrudes_header": tier == "header"}


def test_min_cap_is_about_110_and_font_follows_cap_height():
    m = headline.font_metrics()
    assert headline.cap_height_px(160, m) == pytest.approx(110, abs=1)
    assert hp.MIN_CAP_PX == 110 and hp.ACCEPT_CAP_PX < hp.MIN_CAP_PX


def test_largest_font_is_the_boundary_of_fit():
    z = {"x": 54, "y": 100, "w": 864, "h": 313}
    lines, claim = ["LIMIT", "HIT NOW"], 0
    f = headline.largest_font_px(lines, claim, z, 120)
    aw, ah = headline.text_box(z, 120)
    w, h = headline.stack_size(lines, claim, f)
    w2, h2 = headline.stack_size(lines, claim, f + 1)
    assert w <= aw * headline.FIT_SLACK and h <= ah
    assert w2 > aw * headline.FIT_SLACK or h2 > ah


def test_taller_zone_gets_the_larger_type_and_a_cramped_one_gets_none():
    big = hp.search_design(hp.headline_candidates("x", override="LIMIT HIT NOW"),
                           [zone("above", 239)], frozenset(), headline.font_metrics())[0]
    assert big["cap_px"] >= hp.ACCEPT_CAP_PX
    none, trace = hp.search_design(hp.headline_candidates("x", override="LIMIT HIT NOW"),
                                   [zone("above", 173)], frozenset(), headline.font_metrics())
    assert none is None and trace[-1]["best_seen"]["cap_px"] < hp.ACCEPT_CAP_PX


def test_next_zone_is_tried_when_the_first_cannot_hold_the_minimum():
    cands = hp.headline_candidates("x", override="LIMIT HIT NOW")
    d, trace = hp.search_design(cands, [zone("above", 173), zone("above_header", 313, tier="header")],
                                frozenset(), headline.font_metrics())
    assert d["zone"]["name"] == "above_header"
    assert trace[0]["result"] == "rejected" and trace[0]["zone"] == "above"


def test_reflow_to_fewer_words_when_four_words_cannot_reach_the_minimum():
    cands = hp.headline_candidates("Imagine you hit your Claude limit mid-work and your session is gone",
                                   frozenset({"claude"}))
    ents = frozenset({"claude"})
    d, _ = hp.search_design(cands, [zone("above_header", 313, tier="header")], ents,
                            headline.font_metrics(), thresholds=(hp.ACCEPT_CAP_PX,))
    assert d is not None and len(d["words"]) == 3          # 4 words cannot reach the floor here
    four = [c for c in cands if len(c["words"]) == 4]
    assert hp.search_design(four, [zone("z", 313)], ents, headline.font_metrics(),
                            thresholds=(hp.ACCEPT_CAP_PX,))[0] is None


def test_min_floor_is_enforced_never_returns_small_type():
    cands = hp.headline_candidates("x", override="SESSION IS GONE")
    d, _ = hp.search_design(cands, [zone("z", 120)], frozenset(), headline.font_metrics())
    assert d is None or d["cap_px"] >= hp.ACCEPT_CAP_PX


def test_tighten_recomputes_the_font_on_the_final_box():
    m = headline.font_metrics()
    d, _ = hp.search_design(hp.headline_candidates("x", override="LIMIT HIT NOW"),
                            [zone("z", 400)], frozenset(), m)
    final, font, mark = hp.tighten(d, m)
    assert final["h"] <= 400 and font >= d["font_px"] and mark == d["mark_px"]
    ink = headline.stack_ink_height(d["lines"], d["claim_index"], font, m)
    assert ink + 2 * headline.CONTENT_PAD <= final["h"]


def test_no_backing_by_default_and_the_gradient_stays_soft():
    assert hp.FEATHER_STEPS[0] == 0.0
    assert max(hp.FEATHER_STEPS) == hp.MAX_FEATHER <= 0.35


def test_union_box():
    u = hp.union_box([{"x": 0, "y": 10, "w": 5, "h": 5}, {"x": 20, "y": 0, "w": 5, "h": 5}])
    assert u == {"x": 0, "y": 0, "w": 25, "h": 15}


# ------------------------------------------- entrance geometry (headline.py)

def test_entrance_never_crosses_the_mark_and_overshoot_is_clamped(tmp_path):
    svg = tmp_path / "m.svg"
    svg.write_text("<svg xmlns='http://www.w3.org/2000/svg'/>")
    frag = headline.build(["LIMIT", "HIT NOW"], "#D97757", {"mode": "logo", "src": str(svg)}, 0.08, 3.2,
                          {"x": 54, "y": 182, "w": 864, "h": 313}, assets_dir=tmp_path / "a",
                          mark_px=120)
    anims = "\n".join(frag["anims"])
    assert "x: 1" in anims.split("hl-line")[1] or "x: 9" in anims   # slides in from the right
    assert headline.CLAIM_EASE in anims and headline.MARK_EASE in anims
    assert "back.out(3)" not in anims and "back.out(2.6)" not in anims
    assert frag["mark"]["diameter"] == 120


def test_font_metrics_read_real_widths():
    m = headline.font_metrics()
    assert m.cap_em == pytest.approx(0.688)
    assert m.advance_em("LLM API") == pytest.approx(4.5, abs=0.1)


# --------------------------------------------- photo suitability (needs cv2)

PHOTO = ROOT / "assets" / "people" / "anthropic.png"


@pytest.fixture
def cv2():
    if not PHOTO.exists():
        pytest.skip("assets/people/ holds the user's own face photos and is not in the repo")
    return pytest.importorskip("cv2")


def test_registered_photo_passes_with_numbers(cv2):
    v = hp.photo_suitability(PHOTO)
    assert v["ok"], v
    mt = v["metrics"]
    assert mt["faces_found"] == 1 and mt["sharpness"] > hp.MIN_SHARPNESS and mt["faces_at_120px"] == 1


def test_blurred_photo_fails_sharpness(tmp_path, cv2):
    img = cv2.imread(str(PHOTO), cv2.IMREAD_UNCHANGED)
    cv2.imwrite(str(tmp_path / "b.png"), cv2.GaussianBlur(img, (0, 0), 2))
    v = hp.photo_suitability(tmp_path / "b.png")
    assert not v["ok"] and "sharpness" in v["failed"]


def test_photo_with_transparency_fails(tmp_path, cv2):
    img = cv2.imread(str(PHOTO), cv2.IMREAD_UNCHANGED)
    img[:50, :50, 3] = 0
    cv2.imwrite(str(tmp_path / "a.png"), img)
    assert "alpha" in hp.photo_suitability(tmp_path / "a.png")["failed"]


def test_non_face_image_fails_single_face(tmp_path, cv2):
    import numpy as np
    cv2.imwrite(str(tmp_path / "n.png"), np.full((400, 400, 3), 128, np.uint8))
    assert "single_face" in hp.photo_suitability(tmp_path / "n.png")["failed"]

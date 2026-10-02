import hook_storyboard as sb

WORDS = [{"word": "Now", "start": 0.08}, {"word": "projects", "start": 0.58},
         {"word": "FREE", "start": 1.04}, {"word": "AI", "start": 1.30}]


def test_no_proof_means_no_split():
    s = sb.storyboard(WORDS, "FREE")
    assert s["layout"] == "overlay" and s["beats"] == []


def test_split_from_frame_zero_with_proof():
    s = sb.storyboard(WORDS, "FREE", proof=["models.png"], mark={"mode": "logo"})
    assert s["layout"] == "split_proof"
    assert s["beats"][0]["t"] == 0.0 and s["beats"][0]["card"] is True


def test_swap_lands_on_the_claim_word_inside_the_window():
    assert sb.swap_time(WORDS, "FREE")[0] == 1.04


def test_swap_falls_back_when_the_claim_word_is_late():
    late = [{"word": "FREE", "start": 2.4}]
    assert sb.swap_time(late, "FREE")[0] == sb.SWAP_DEFAULT


def test_sting_starts_early_so_its_peak_hits_the_moment():
    s = sb.sting("click", 1.32, "x")
    assert s["start"] == round(1.32 - sb.STING_PEAKS["click"], 3) and s["hit_at"] == 1.32


def test_frame_one_impact_never_starts_before_zero():
    assert sb.sting("impact", 0.0, "x")["start"] == 0.0


def test_sounds_follow_the_beats():
    s = sb.storyboard(WORDS, "FREE", proof=["models.png"])
    cats = [x["category"] for x in s["sounds"]]
    assert cats == ["impact", "swoosh", "click"]
    assert s["sounds"][1]["hit_at"] == 1.04 and s["sounds"][2]["hit_at"] == s["highlight_at"]

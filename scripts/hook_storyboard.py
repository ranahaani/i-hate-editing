"""Storyboard for the first ~2 seconds: layout, beat timings and sounds.

Measured on five reference reels (reel-refs/hooks-2026-10-02, rules/hooks.md
"The split-proof hook"): every one opens split from frame 0 with real proof on
top and the speaker below, changes the top panel once at 1.10-1.30s, and keeps
a music bed about 20-25 dB under the voice. This module turns those numbers
into decisions; hook_plan.py still owns the headline words, size and mark.
"""

SWAP_WINDOW = (1.0, 1.4)      # first top-panel change; refs measured 1.10-1.30s
SWAP_DEFAULT = 1.2
SWAP_TRANSITION = 0.32        # zoom/push into the second state
RING_DELAY = 0.30             # highlight lands after the zoom settles
CARD_EXIT = 0.18
SPLIT_FACE_Y = 40             # objectPosition % for the face in the bottom half
SEAM_TOP_FRAC = 0.34          # headline block top, as a share of frame height
BED_UNDER_VOICE_DB = -22      # refs: floor -31..-37 dBFS against voice peaks -9..-14

STING_PEAKS = {"impact": 0.178, "swoosh": 0.107, "click": 0.202, "pop": 0.13}


def swap_time(words, claim_word, hook_start=0.0):
    """When the top panel changes: on the claim word's onset if it falls in the
    window, else the window default. Returns (t, why)."""
    lo, hi = hook_start + SWAP_WINDOW[0], hook_start + SWAP_WINDOW[1]
    target = (claim_word or "").strip(".,!?").upper()
    for w in words:
        if w["word"].strip(".,!?").upper() == target and lo <= w["start"] <= hi:
            return round(w["start"], 3), f"on the claim word {target!r} at {w['start']:.2f}s"
    return round(hook_start + SWAP_DEFAULT, 3), (
        f"claim word not spoken inside {SWAP_WINDOW[0]}-{SWAP_WINDOW[1]}s; "
        f"default {SWAP_DEFAULT}s (refs swap at 1.10-1.30s)")


def sting(category, hit_at, why):
    start = max(0.0, round(hit_at - STING_PEAKS[category], 3))
    return {"category": category, "hit_at": round(start + STING_PEAKS[category], 3),
            "start": start, "why": why}


def storyboard(words, claim_word, proof=(), mark=None, hook_start=0.0, hook_end=3.2,
               kicker=None):
    """Layout + beats + sounds. `proof` is a list of real captures (paths);
    without one the hook stays an overlay on the full frame, because a split
    with nothing real on top is a designed card, which rules/proof.md forbids."""
    if not proof:
        return {"layout": "overlay", "beats": [], "sounds": [
                    sting("impact", hook_start, "frame-1 hit under the headline entrance")],
                "why": "no real capture to put on top, so no split; headline over the full frame"}

    t_swap, swap_why = swap_time(words, claim_word, hook_start)
    second = proof[1] if len(proof) > 1 else proof[0]
    beats = [
        {"t": hook_start, "top": proof[0], "card": (mark or {}).get("mode") in ("logo", "icon"),
         "move": "push-in 1.00->1.04, dimmed so the card reads",
         "why": "frame 0 is already split: proof on top, face below (all 5 refs)"},
        {"t": t_swap, "top": second,
         "move": ("zoom onto the highlight target" if second == proof[0] else "cut to the second capture"),
         "card_exit": CARD_EXIT, "transition": SWAP_TRANSITION, "why": swap_why},
    ]
    ring_at = round(t_swap + RING_DELAY, 3)
    sounds = [
        sting("impact", hook_start, "frame-1 thud as the split lands"),
        sting("swoosh", t_swap, "card leaves / top panel changes"),
        sting("click", ring_at, "highlight lands on the proof"),
    ]
    return {
        "layout": "split_proof",
        "face": {"top_frac": 0.5, "object_position_y": SPLIT_FACE_Y},
        "headline": {"position": "seam", "top_frac": SEAM_TOP_FRAC,
                     "kicker": kicker, "kicker_style": "serif italic, white, ~0.7x the claim line",
                     "claim_style": "Archivo Black, outline + shadow, accent on the claim word",
                     "exit": round(hook_end - 0.24, 3)},
        "captions": "split class: just under the seam, never on the face",
        "beats": beats,
        "highlight_at": ring_at,
        "sounds": sounds,
        "bed": {"under_voice_db": BED_UNDER_VOICE_DB,
                "why": "refs keep a music floor at -31..-37 dBFS under voice peaks of -9..-14"},
        "why": "real proof exists, so the hook opens split like every reference reel",
    }

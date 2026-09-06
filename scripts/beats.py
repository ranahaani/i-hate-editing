#!/usr/bin/env python3
"""Audit the beat map for stretches where nothing changes.

The most-reported defect in short-form is a shot that sits still. The rule is
something new every three seconds — a card, a cutaway, a logo, a layout change
— and it is easy to satisfy at the start of a piece and quietly break in the
middle, because nothing errors when a face holds for ten seconds.

Counts every visible event across the composition and reports the gaps.

    python3 scripts/beats.py --studio <footage>/studio
    python3 scripts/beats.py --studio ... --max-gap 4
"""

import argparse
import json
import re
import sys
from pathlib import Path

DEFAULT_MAX_GAP = 3.0
# rules/motion.md: a beat longer than about four seconds needs another event
# inside it. Below that a single held element still reads as alive.
PACING_GAP = {"punchy": 4.0, "balanced": 5.0, "restrained": 6.5}

sys.path.insert(0, str(Path(__file__).resolve().parent))
from transcribe import read_profile  # noqa: E402


def load(path, key):
    p = Path(path)
    if not p.is_file():
        return []
    try:
        return json.loads(p.read_text()).get(key, [])
    except Exception:
        return []


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--studio", default="studio")
    ap.add_argument("--max-gap", type=float, default=None)
    args = ap.parse_args()

    studio = Path(args.studio)
    tl_path = studio / "timeline.json"
    if not tl_path.is_file():
        print("error: no timeline.json — render the cut first", file=sys.stderr)
        return 1
    tl = json.loads(tl_path.read_text())
    duration = float(tl.get("predicted_duration", 0))

    profile = read_profile(studio)
    pacing = str(profile.get("pacing", "punchy")).lower()
    max_gap = args.max_gap or PACING_GAP.get(pacing, DEFAULT_MAX_GAP)

    events = []
    for s in tl.get("segments", []):
        if s["out_start"] > 0.01:
            events.append((s["out_start"], "cut", s.get("beat") or "segment"))
    for c in load(studio / "cards.json", "cards"):
        kind = "band" if c.get("style") == "band" else "card"
        label = c.get("big", "").replace("*", "")[:28]
        start, dur = float(c["start"]), float(c["duration"])
        events.append((start, kind, label))
        # The headline's held zoom is real motion inside the card, so it counts
        # as an event — ignoring it reports dead time where the screen moves.
        if kind == "card" and dur > 1.2:
            events.append((start + 0.45, "zoom", f"{label} held zoom"))
    for b in load(studio / "proof.json", "beats"):
        events.append((float(b["start"]), "proof",
                       f"{b.get('action')} {b.get('target') or ''}".strip()))

    # --- gate: the frame must be disrupted inside the first two seconds
    opening = [e for e in events if e[0] <= 2.0]

    # --- gate: captions must have been proofread
    raw_caption_flags = []
    capf = studio / "captions.json"
    if capf.is_file():
        try:
            cd = json.loads(capf.read_text())
        except Exception:
            cd = {}
        chunks = cd.get("chunks", [])
        if chunks and not cd.get("proofread"):
            raw_caption_flags.append("captions.json has no proofread flag")
        # Shapes that only appear in an untouched machine pass.
        for c in chunks:
            t = c.get("text", "")
            if re.search(r'["""]|\s[,.]|\.\s*\w+,\s*$', t) or len(t.split()) > 4:
                raw_caption_flags.append(f'"{t[:38]}"')
        raw_caption_flags = raw_caption_flags[:4]

    # --- gate: if the piece names a real artifact, proof must exist
    named, proof_count = [], len([e for e in events if e[1] == "proof"])
    caps = studio / "captions.json"
    if caps.is_file():
        try:
            text = " ".join(c["text"] for c in
                            json.loads(caps.read_text()).get("chunks", [])).lower()
        except Exception:
            text = ""
        for cue in ("repo", "github", "link in", "comment ", "tool called",
                    "install", "open source", "npm", "pip install"):
            if cue in text:
                named.append(cue)

    events.sort()
    if not events:
        print("no visual events at all — the whole piece is one static shot")
        return 2

    print(f"{len(events)} visual events over {duration:.1f}s · "
          f"pacing '{pacing}' allows {max_gap:.1f}s\n")

    gaps, prev, prev_label = [], 0.0, "start"
    for t, kind, label in events + [(duration, "end", "end")]:
        gap = t - prev
        flag = "  ← DEAD" if gap > max_gap else ""
        if gap > max_gap:
            gaps.append((prev, t, gap, prev_label))
        if kind != "end":
            print(f"  {t:6.2f}s  {kind:<6} {label:<30} (+{gap:5.2f}s){flag}")
        elif flag:
            print(f"  {t:6.2f}s  {'end':<6} {'':<30} (+{gap:5.2f}s){flag}")
        prev, prev_label = t, f"{kind} {label}"

    print()
    failures = []
    if not opening:
        failures.append(
            "nothing happens in the first 2s — the frame must be disrupted by a "
            "micro-zoom, a cut, or a graphic sliding in (rules/hooks.md)")
    if raw_caption_flags:
        failures.append(
            "captions look unproofread — " + "; ".join(raw_caption_flags) +
            ". Machine translation is a draft, not caption copy; rewrite it and "
            "set proofread: true (rules/captions.md)")
    if named and not proof_count:
        failures.append(
            f"the piece names something real ({', '.join(sorted(set(named))[:3])}) "
            f"but shows no proof shot. Capture the page and zoom onto the words "
            f"being said — a card is a claim, the page is evidence "
            f"(rules/proof.md)")

    for f in failures:
        print(f"  FAIL  {f}\n")

    if not gaps and not failures:
        print(f"no stretch longer than {max_gap:.1f}s without something new")
        return 0
    if failures and not gaps:
        return 2

    print(f"{len(gaps)} stretch(es) with nothing new:")
    for a, b, g, after in gaps:
        print(f"  · {a:.2f}s → {b:.2f}s  ({g:.1f}s) after {after}")
    print("\nFill these with a card, a cutaway, a logo, or a layout change.")
    print("A held zoom on the key word counts; a caption changing does not.")
    return 2


if __name__ == "__main__":
    sys.exit(main())

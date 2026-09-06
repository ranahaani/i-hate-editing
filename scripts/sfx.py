#!/usr/bin/env python3
"""Place sound effects so their PEAK lands on the beat.

The rule that matters here is frame-perfect timing: what the ear registers is
the loud transient, not the moment the file started playing. Since library
files rarely have their peak at the start, a sound placed by its start time
lands late by however long its lead-in is — and a window too short to reach
the peak is simply silent (rules/sound.md).

So every placement is computed backwards from the peak: the file is started
early enough that its loudest moment coincides with the picture.

    python3 scripts/sfx.py plan --studio <dir> --library ~/sfx
    python3 scripts/sfx.py plan --studio <dir> --dry-run
"""

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from sound import find_peak, levels  # noqa: E402

DENSITY_PER_15S = 5          # ceiling from rules/sound.md
MIN_GAP = 0.25               # two stings closer than this mush together

# The sound should arrive a frame or two ahead of the picture. Landing exactly
# on it reads fractionally late, and landing after reads laggy.
LEAD = 0.05                  # ~1.5 frames at 30fps

DEFAULT_LIB = Path.home() / ".i-hate-editing" / "sfx"

# A transient whose loud moment sits seconds into the file cannot mark a beat:
# aligning its peak would start it far earlier than the cut, so it plays a long
# lead-in over the previous shot. Beds and risers are allowed to build.
MAX_PEAK_OFFSET = {"riser": 3.0, "heartbeat": 3.0, "clock": 3.0,
                   "paper": 3.0, "crowd": 6.0, "hiss": 6.0}
DEFAULT_MAX_PEAK = 1.6

# Fallback placement when the library index is missing its metadata.
TRACKS = {"whoosh": 12, "pop": 24, "impact": 34, "riser": 36,
          "notification": 38, "click": 26, "keyboard": 30}
GAIN = {"whoosh": 0.75, "pop": 0.55, "impact": 0.80, "riser": 0.85,
        "notification": 0.60, "click": 0.45, "keyboard": 0.30}


def load_index(library):
    """The installed library, if sfx_library.py has been run."""
    idx = Path(library).expanduser() / "index.json"
    if idx.is_file():
        try:
            return json.loads(idx.read_text())
        except Exception:
            pass
    return {}


def pick(library, category, index, used):
    """A file for this category, rotating so one sound is not the whole reel.

    An indexed library carries per-category volume and track from the taxonomy;
    a bare directory of mp3s still works, just without that metadata."""
    entry = index.get(category)
    if entry and entry.get("files"):
        limit = MAX_PEAK_OFFSET.get(category, DEFAULT_MAX_PEAK)
        usable = [f for f in entry["files"]
                  if Path(f["file"]).is_file()
                  and float(f.get("peak_at", 0)) <= limit]
        if not usable:
            # Better a late-peaking file than none, but take the earliest.
            usable = sorted((f for f in entry["files"] if Path(f["file"]).is_file()),
                            key=lambda f: float(f.get("peak_at", 0)))[:1]
        if usable:
            f = usable[used.get(category, 0) % len(usable)]
            used[category] = used.get(category, 0) + 1
            return Path(f["file"]), entry.get("volume"), entry.get("track")

    root = Path(library).expanduser()
    for sub in (root / category, root):
        if not sub.is_dir():
            continue
        files = sorted(f for f in sub.glob("*.mp3") if category in f.name.lower()) \
            or sorted(sub.glob("*.mp3"))
        if files:
            boosted = [f for f in files if "boost" in f.name or "swell" in f.name]
            return (boosted or files)[0], None, None
    return None, None, None


def analyse(path, cache):
    """(peak_offset, duration) — where the loud moment actually is."""
    key = str(path)
    if key not in cache:
        pk, t, total = find_peak(path, step=0.05)
        _, full = levels(path)
        cache[key] = {"peak_at": t or 0.0, "duration": total,
                      "peak_db": pk, "file_peak_db": full}
    c = cache[key]
    return c["peak_at"], c["duration"], c


def place(hit_at, path, cache):
    """Start the file so its peak lands just before hit_at."""
    peak_at, total, info = analyse(path, cache)
    start = hit_at - LEAD - peak_at
    lead_trimmed = 0.0
    if start < 0:                       # cannot start before the timeline
        lead_trimmed = -start
        start = 0.0
    # Play through the peak plus a short tail so it is never truncated.
    duration = min(total, peak_at + 0.45) - lead_trimmed
    return round(start, 3), round(max(0.15, duration), 3), info


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    pl = sub.add_parser("plan", help="generate sfx.json from the edit")
    pl.add_argument("--studio", default="studio")
    pl.add_argument("--library", default=str(DEFAULT_LIB),
                    help="root of the sound library")
    pl.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    studio = Path(args.studio)
    tl = json.loads((studio / "timeline.json").read_text()) \
        if (studio / "timeline.json").is_file() else {}
    beats = json.loads((studio / "proof.json").read_text()).get("beats", []) \
        if (studio / "proof.json").is_file() else []

    duration = tl.get("predicted_duration", 0)
    events = []

    # Post-hook sting: riser building into an impact at the first seam. This is
    # the one mandatory moment — a hook that hard-cuts into the body with no
    # sound reads as unfinished.
    seams = tl.get("seams") or []
    if seams:
        events.append({"at": seams[0], "category": "riser",
                       "why": "post-hook riser", "mandatory": True})
        events.append({"at": seams[0], "category": "impact",
                       "why": "post-hook impact", "mandatory": True})

    # Remaining cut transitions get a whoosh. No pop where an impact already
    # lands — stacked transients mush into one distorted blob.
    for s in seams[1:]:
        events.append({"at": s, "category": "whoosh_light", "mandatory": True,
                       "why": "cut transition"})

    # Cards are layout changes too. Missing these left more than half the
    # reel with graphics arriving in silence, which reads as unfinished.
    for c in (json.loads((studio / "cards.json").read_text()).get("cards", [])
              if (studio / "cards.json").is_file() else []):
        start, dur = float(c["start"]), float(c["duration"])
        # Match the sound to what the card actually is. A full-frame card
        # taking over the screen is a bigger move than a half-split arriving,
        # and a band is a small element popping in.
        if c.get("style") == "band":
            kind, why = "pop", "band in"
        elif c.get("full"):
            kind, why = "whoosh_deep", "full-frame card"
        else:
            kind, why = "whoosh_light", "card in"
        events.append({"at": start, "category": kind, "mandatory": True,
                       "why": why})

        # Each list row lands with a click, staggered with the row animation.
        items = c.get("items") or []
        for n in range(len(items)):
            events.append({"at": start + 0.40 + n * 0.30, "category": "click",
                           "mandatory": True, "why": f"list row {n + 1}"})

        # The headline's held zoom gets an accent — a ding when the card is a
        # result or metric, a pop otherwise.
        if c.get("style") != "band" and dur > 1.6 and not items:
            big = (c.get("big") or "").lower()
            metric = any(w in big for w in ("result", "%", "x ", "faster",
                                            "hours", "mins", "free"))
            events.append({"at": start + 0.45,
                           "category": "ding" if metric else "pop",
                           "why": "headline lands"})

    # Proof shots slide in and out; both movements are layout changes.
    for b in beats:
        start, dur = float(b["start"]), float(b["duration"])
        # Cutting from a face to a screen is a change of medium, so it gets a
        # glitch rather than a plain whoosh; the return is a light swoosh.
        events.append({"at": start, "category": "glitch", "mandatory": True,
                       "why": "cut to screen"})
        events.append({"at": start + dur - 0.2, "category": "swoosh",
                       "mandatory": True, "why": "back to face"})
        if b.get("action") == "zoom":
            events.append({"at": start + 0.1, "category": "shutter",
                           "why": "screenshot lands"})
        if b.get("highlight"):
            events.append({"at": start + float(b.get("highlight_at", 0.7)),
                           "category": "click", "why": "highlight sweep"})

    events.sort(key=lambda e: e["at"])

    # Resolve collisions. The forbidden stack is pop+impact — they mush into
    # one distorted blob. Riser+impact is the opposite: the riser is *meant* to
    # resolve into the impact, so that pair is always allowed to share a moment.
    # One dominant sound per visual cue. Stacking a whoosh, a pop and a ding on
    # one frame reads as chaos, not emphasis. The single exception is a riser
    # resolving into an impact, which is one gesture in two parts.
    ALLOWED_PAIR = {frozenset({"riser", "impact"})}
    DOMINANCE = ["impact", "riser", "whoosh_deep", "glitch", "notification",
                 "ding", "whoosh_light", "swoosh", "rewind", "record_scratch",
                 "shutter", "pop", "click", "keyboard"]
    kept = []
    for e in events:
        clash = [k for k in kept if abs(k["at"] - e["at"]) < MIN_GAP]
        clash = [c for c in clash
                 if frozenset({c["category"], e["category"]}) not in ALLOWED_PAIR]
        if clash:
            if e["category"] == "impact" and any(c["category"] == "pop" for c in clash):
                # The impact carries the transient; drop the pop under it.
                kept = [k for k in kept if not (k["category"] == "pop"
                                                and abs(k["at"] - e["at"]) < MIN_GAP)]
            elif not e.get("mandatory"):
                continue
        kept.append(e)

    # The ceiling is a budget on optional accents. Mandatory stings are never
    # thinned — the rule caps total moments, it does not license skipping the
    # ones that must fire.
    # The ceiling governs optional accents only. Every layout change gets a
    # sound — that is the floor, and a graphic arriving in silence reads as an
    # unfinished edit (rules/sound.md). A piece with a card every few seconds
    # legitimately carries more sounds than a face-only one.
    ceiling = max(3, int(DENSITY_PER_15S * (duration / 15.0))) if duration else len(kept)
    must = [e for e in kept if e.get("mandatory")]
    optional = [e for e in kept if not e.get("mandatory")]
    room = max(0, ceiling - len(must))
    if len(optional) > room:
        priority = {"whoosh": 0, "pop": 1, "click": 2, "keyboard": 3}
        optional.sort(key=lambda e: (priority.get(e["category"], 4), e["at"]))
        dropped = len(optional) - room
        optional = optional[:room]
        print(f"  density ceiling {ceiling} for {duration:.0f}s — "
              f"dropped {dropped} optional accent(s), kept {len(must)} mandatory")
    kept = sorted(must + optional, key=lambda e: e["at"])

    index = load_index(args.library)
    cache, out, missing, used = {}, [], set(), {}
    for e in kept:
        f, vol, track = pick(args.library, e["category"], index, used)
        if not f:
            missing.add(e["category"])
            continue
        start, dur, info = place(e["at"], f, cache)
        out.append({
            "file": str(f), "category": e["category"], "why": e["why"],
            "hit_at": round(e["at"], 3),
            "start": start, "duration": dur,
            "track": track if track is not None else TRACKS.get(e["category"], 20),
            "volume": vol if vol is not None else GAIN.get(e["category"], 0.6),
            "peak_offset": round(info["peak_at"], 3),
        })

    print(f"{len(out)} sound(s) over {duration:.1f}s")
    for s in out:
        shift = s["hit_at"] - s["start"]
        print(f"  {s['hit_at']:6.2f}s  {s['category']:<12} {s['why']:<18} "
              f"start {s['start']:6.2f} (peak +{shift:.2f}s in)  {Path(s['file']).name}")
    if missing:
        print(f"  missing categories in the library: {', '.join(sorted(missing))}")

    if not args.dry_run:
        (studio / "sfx.json").write_text(json.dumps({"sounds": out}, indent=2))
        print(f"-> {studio / 'sfx.json'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

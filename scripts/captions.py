#!/usr/bin/env python3
"""Build caption chunks on the OUTPUT timeline.

Source timestamps are meaningless after segments are concatenated (hard rule
5), so every token is remapped through the timeline before chunking. Chunks
start 0.08s *after* the word onset — a caption that appears before the word is
spoken is the most-reported caption defect, and late is invisible where early
is a bug (rules/captions.md).

    python3 scripts/captions.py --studio <footage>/studio
    python3 scripts/captions.py --studio ... --max-words 4
"""

import argparse
import glob
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from transcribe import read_profile  # noqa: E402

LATE_BIAS = 0.08       # never early
GAP_BREAK = 0.35       # a pause this long starts a new chunk
MAX_WORDS = 3          # four only when a split would break a phrase
MIN_ON_SCREEN = 0.40   # shorter than this cannot be read; merge instead

STOP = {
    "a", "an", "the", "and", "or", "but", "if", "so", "to", "of", "in", "on",
    "at", "by", "for", "with", "is", "are", "was", "were", "be", "been", "am",
    "it", "its", "this", "that", "these", "those", "you", "your", "i", "we",
    "he", "she", "they", "them", "my", "me", "will", "can", "do", "does",
    "did", "have", "has", "had", "not", "no", "as", "from", "then", "than",
    "what", "when", "which", "who", "how", "why", "there", "here", "all",
}


def load_transcript(studio, source_path, prefer_translate):
    """Resolve by the source path each transcript recorded, not by filename.

    Matching on stem alone silently picks the wrong transcript whenever the
    EDL points at a different file that happens to share a name, and finds
    nothing when the EDL path differs from what was transcribed."""
    want = str(Path(source_path).resolve())
    by_mode = {"translate": [], "verbatim": []}
    for f in sorted(glob.glob(str(Path(studio) / "transcripts" / "*.json"))):
        try:
            doc = json.loads(Path(f).read_text())
        except Exception:
            continue
        if doc.get("source") != want:
            continue
        by_mode.setdefault(doc.get("mode", "verbatim"), []).append(doc)

    order = ["translate", "verbatim"] if prefer_translate else ["verbatim"]
    for mode in order:
        if by_mode.get(mode):
            return by_mode[mode][-1]
    return None


def to_words(doc):
    """Normalise to word tokens. Segment-level input is split and interpolated,
    which is approximate — flagged so downstream can say so."""
    out = []
    approx = doc.get("granularity") != "word"
    for tok in doc["words"]:
        text = tok["text"].strip()
        if not text:
            continue
        if not approx:
            out.append({"start": tok["start"], "end": tok["end"], "text": text, "approx": False})
            continue
        parts = text.split()
        if not parts:
            continue
        span = max(0.001, tok["end"] - tok["start"]) / len(parts)
        for i, w in enumerate(parts):
            out.append({
                "start": tok["start"] + i * span,
                "end": tok["start"] + (i + 1) * span,
                "text": w, "approx": True,
            })
    return out


def remap(words, segments, source_key, speed=1.0):
    """Source time -> output time, dropping anything not kept in the cut.

    The offset within a segment is divided by the playback speed. Adding a
    source-seconds offset to an output-timeline anchor drifts progressively
    through every segment, and a word near the end lands past the segment
    entirely."""
    kept = []
    for seg in segments:
        if seg["source"] != source_key:
            continue
        s0, s1, o0 = seg["source_start"], seg["source_end"], seg["out_start"]
        for w in words:
            if w["start"] >= s0 and w["start"] < s1:
                kept.append({
                    "start": (w["start"] - s0) / speed + o0,
                    "end": (min(w["end"], s1) - s0) / speed + o0,
                    "text": w["text"], "approx": w["approx"],
                })
    return sorted(kept, key=lambda w: w["start"])


def chunk(words, max_words):
    chunks, cur = [], []
    for w in words:
        if cur:
            gap = w["start"] - cur[-1]["end"]
            ends_clause = bool(re.search(r"[.?!,;:]$", cur[-1]["text"]))
            if ends_clause or gap >= GAP_BREAK or len(cur) >= max_words:
                chunks.append(cur)
                cur = []
        cur.append(w)
    if cur:
        chunks.append(cur)

    # Merge anything too brief to read into its neighbour.
    merged = []
    for c in chunks:
        dur = c[-1]["end"] - c[0]["start"]
        if merged and dur < MIN_ON_SCREEN and len(merged[-1]) + len(c) <= max_words + 2:
            merged[-1] += c
        else:
            merged.append(c)
    return merged


def emphasis(words, keywords):
    """Index of the one or two words carrying the meaning."""
    scored = []
    for i, w in enumerate(words):
        t = re.sub(r"[^\w'-]", "", w["text"])
        low = t.lower()
        if not t:
            continue
        s = 0
        if re.search(r"\d", t):
            s += 10                                  # numbers carry claims
        if low in keywords:
            s += 9
        if t[:1].isupper() and i > 0:
            s += 4                                   # product / tool names
        if low not in STOP:
            s += min(len(t), 8) / 4
        else:
            s -= 5
        scored.append((s, i))
    scored.sort(key=lambda x: (-x[0], x[1]))
    picks = [i for s, i in scored[:2] if s > 2]
    return sorted(picks[:1] if len(words) <= 2 else picks)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--studio", default="studio")
    ap.add_argument("--max-words", type=int, default=MAX_WORDS)
    ap.add_argument("--keywords", default="", help="comma-separated words to always emphasise")
    ap.add_argument("--fix", action="append", default=[],
                    help="wrong=right, repeatable; ASR reliably mangles product names")
    ap.add_argument("-o", "--out", default=None)
    args = ap.parse_args()

    studio = Path(args.studio)
    tl_path, edl_path = studio / "timeline.json", studio / "edl.json"
    if not tl_path.is_file():
        print("error: no timeline.json — run render.py first", file=sys.stderr)
        return 1
    tl = json.loads(tl_path.read_text())
    edl = json.loads(edl_path.read_text()) if edl_path.is_file() else {}
    sources = edl.get("sources", {})

    prof = read_profile(studio)
    prefer_translate = prof.get("translate_captions") is True
    keywords = {k.strip().lower() for k in args.keywords.split(",") if k.strip()}
    fixes = {}
    for f in args.fix:
        if "=" in f:
            a, b = f.split("=", 1)
            fixes[a.strip().lower()] = b.strip()

    segments = tl["segments"]
    speed = float(tl.get("speed", 1.0))
    all_words, approx_any, missing = [], False, []
    for key in sorted({s["source"] for s in segments}):
        path = sources.get(key, key)
        doc = load_transcript(studio, path, prefer_translate)
        if not doc:
            missing.append(key)
            continue
        words = to_words(doc)
        approx_any = approx_any or any(w["approx"] for w in words)
        all_words += remap(words, segments, key, speed)

    if missing:
        print(f"error: no transcript for {', '.join(missing)} — run transcribe.py",
              file=sys.stderr)
        return 1
    if not all_words:
        print("error: no words fell inside the kept ranges", file=sys.stderr)
        return 1

    all_words.sort(key=lambda w: w["start"])
    groups = chunk(all_words, args.max_words)

    out_chunks, prev_end = [], 0.0
    for g in groups:
        start = max(g[0]["start"] + LATE_BIAS, prev_end + 0.01)
        end = max(g[-1]["end"], start + MIN_ON_SCREEN)
        if start >= end:
            continue
        for w in g:
            bare = re.sub(r"[^\w']", "", w["text"]).lower()
            if bare in fixes:
                w["text"] = w["text"].replace(
                    re.sub(r"[^\w']", "", w["text"]), fixes[bare])
        em = emphasis(g, keywords)
        out_chunks.append({
            "start": round(start, 3),
            "end": round(end, 3),
            "duration": round(end - start, 3),
            "text": " ".join(w["text"] for w in g),
            "words": [{"text": w["text"], "emphasis": i in em} for i, w in enumerate(g)],
            "approx_timing": any(w["approx"] for w in g),
        })
        prev_end = end

    out = Path(args.out) if args.out else studio / "captions.json"
    out.write_text(json.dumps({
        "language": prof.get("language"),
        "translated": prefer_translate,
        "late_bias": LATE_BIAS,
        "chunks": out_chunks,
    }, indent=2, ensure_ascii=False))

    dur = tl.get("predicted_duration", 0)
    covered = sum(c["duration"] for c in out_chunks)
    print(f"{len(out_chunks)} chunks · {covered:.1f}s of {dur:.1f}s covered "
          f"({covered / dur * 100:.0f}%)" if dur else f"{len(out_chunks)} chunks")
    if approx_any:
        print("  note: segment-level source — word timing is interpolated and")
        print("        approximate. Check a few chunks against the video.")
    for c in out_chunks[:6]:
        marked = " ".join(f"[{w['text']}]" if w["emphasis"] else w["text"] for w in c["words"])
        print(f"  [{c['start']:6.2f}-{c['end']:6.2f}] {marked}")
    if len(out_chunks) > 6:
        print(f"  … {len(out_chunks) - 6} more")
    print(f"-> {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

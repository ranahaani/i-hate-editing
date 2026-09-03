#!/usr/bin/env python3
"""Pack cached transcripts into takes.md — the reading view for cut decisions.

You make cut decisions by reading this file, not by watching the video and not
by paging through raw JSON. Phrases break on silence or on a long gap between
tokens, and every line carries its time range so a decision can be written
straight into an EDL.

    python3 scripts/pack.py --studio <footage>/studio
"""

import argparse
import glob
import json
import os
from pathlib import Path

PHRASE_GAP = 0.50      # a pause this long starts a new phrase
MAX_WORDS = 14         # keep lines readable even in continuous speech


def load(studio):
    out = []
    for f in sorted(glob.glob(str(Path(studio) / "transcripts" / "*.verbatim.json"))):
        d = json.loads(Path(f).read_text())
        out.append(d)
    return out


def phrases(words, granularity):
    """Group tokens into phrase lines. Segment-level input is already phrased."""
    if granularity == "segment":
        return [{"start": w["start"], "end": w["end"], "text": w["text"]} for w in words]

    lines, cur = [], []
    for w in words:
        if cur:
            gap = w["start"] - cur[-1]["end"]
            if gap >= PHRASE_GAP or len(cur) >= MAX_WORDS:
                lines.append(cur)
                cur = []
        cur.append(w)
    if cur:
        lines.append(cur)

    out = []
    for group in lines:
        text = ""
        for w in group:
            t = w["text"]
            if t in ",.?!;:" or t.startswith("'"):
                text += t
            else:
                text += (" " if text else "") + t
        out.append({"start": group[0]["start"], "end": group[-1]["end"], "text": text.strip()})
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--studio", default="studio")
    ap.add_argument("-o", "--out", default=None)
    args = ap.parse_args()

    docs = load(args.studio)
    if not docs:
        print("no transcripts found — run scripts/transcribe.py first")
        return 1

    md = ["# Takes", "",
          "Phrase-level reading view. Times are seconds within each source.",
          "Cut edges must land on a word boundary and be cross-checked against",
          "`scripts/silences.py` — never trusted from these timestamps alone.", ""]

    for d in docs:
        name = Path(d["source"]).name
        lines = phrases(d["words"], d.get("granularity", "word"))
        dur = lines[-1]["end"] if lines else 0
        md.append(f"## {name}")
        md.append(f"_{dur:.1f}s · {len(lines)} phrases · {d['language']} · "
                  f"{d.get('granularity', 'word')}-level_")
        md.append("")
        for p in lines:
            md.append(f"  [{p['start']:07.2f}-{p['end']:07.2f}] {p['text']}")
        md.append("")

    out = Path(args.out) if args.out else Path(args.studio) / "takes.md"
    out.write_text("\n".join(md))
    total = sum(len(phrases(d["words"], d.get("granularity", "word"))) for d in docs)
    print(f"{len(docs)} source(s), {total} phrases -> {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

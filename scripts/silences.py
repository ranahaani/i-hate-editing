#!/usr/bin/env python3
"""Silence detection — the authority on cut timing.

Transcript timestamps drift, especially on non-Latin scripts where tokens are
segment-level. Silence boundaries come straight from the waveform, so every cut
edge should be cross-checked against this rather than trusted from the
transcript alone.

    python3 scripts/silences.py take1.mp4
    python3 scripts/silences.py take1.mp4 --noise -32dB --min 0.35 --json
"""

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

# Silence gaps and what they mean for cutting. Values in seconds.
CLEAN = 0.40      # >= this is a safe cut point
USABLE = 0.15     # between USABLE and CLEAN: check a frame before cutting
                  # < USABLE is mid-phrase and unsafe


def detect(src, noise="-32dB", min_dur=0.30):
    proc = subprocess.run(
        ["ffmpeg", "-hide_banner", "-nostats", "-i", str(src),
         "-af", f"silencedetect=noise={noise}:d={min_dur}", "-f", "null", "-"],
        capture_output=True, text=True, errors="replace")
    log = proc.stderr

    starts = [float(m) for m in re.findall(r"silence_start:\s*(-?[\d.]+)", log)]
    ends = [float(m) for m in re.findall(r"silence_end:\s*(-?[\d.]+)", log)]

    gaps = []
    for i, s in enumerate(starts):
        e = ends[i] if i < len(ends) else None
        if e is None:                      # trailing silence to end of file
            e = duration(src)
        if e <= s:
            continue
        gaps.append({
            "start": round(s, 3),
            "end": round(e, 3),
            "duration": round(e - s, 3),
            "quality": "clean" if (e - s) >= CLEAN else
                       ("usable" if (e - s) >= USABLE else "unsafe"),
        })
    return gaps


def duration(src):
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=nw=1:nk=1", str(src)],
        capture_output=True, text=True, errors="replace").stdout.strip()
    try:
        return float(out)
    except ValueError:
        return 0.0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("source")
    ap.add_argument("--noise", default="-32dB")
    ap.add_argument("--min", dest="min_dur", type=float, default=0.30)
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    if not Path(args.source).is_file():
        print(f"error: no such file: {args.source}", file=sys.stderr)
        return 1

    total = duration(args.source)
    gaps = detect(args.source, args.noise, args.min_dur)
    speech = round(total - sum(g["duration"] for g in gaps), 2)

    if args.json:
        print(json.dumps({
            "source": str(Path(args.source).resolve()),
            "duration": round(total, 2),
            "speech_time": speech,
            "silence_time": round(total - speech, 2),
            "gaps": gaps,
        }, indent=2))
        return 0

    print(f"{Path(args.source).name}  {total:.1f}s total · {speech:.1f}s speech "
          f"· {total - speech:.1f}s silence · {len(gaps)} gaps")
    for g in gaps:
        mark = {"clean": "cut here", "usable": "check a frame first", "unsafe": "mid-phrase"}[g["quality"]]
        print(f"  [{g['start']:7.2f}-{g['end']:7.2f}]  {g['duration']:5.2f}s  {g['quality']:<7} {mark}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

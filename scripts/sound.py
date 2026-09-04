#!/usr/bin/env python3
"""Sound effect placement, and the audibility check that catches silent stings.

A sound effect can play, not clip, and still be inaudible: if its loud
transient falls outside the window you play, the mix contains only the quiet
lead-in. Every level check passes and the render completes. Nobody hears it.

`inspect` sweeps a source file to find where its peak actually is.
`check` measures the rendered output against a voice-only baseline, which is
the only measurement that proves a human would hear it.

    python3 scripts/sound.py inspect assets/sfx/riser/riser.mp3
    python3 scripts/sound.py inspect assets/sfx/ --window 0.6
    python3 scripts/sound.py check cut.mp4 --at 5.0 21.0 30.6
"""

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

STEP = 0.10            # sweep resolution
MISS_MARGIN = 3.0      # window peak this far below true peak => window misses it
STING_TARGET = 3.0     # a transient should read this many dB over the voice
AUDIO_EXT = {".mp3", ".wav", ".m4a", ".aac", ".ogg", ".flac"}


def sh(cmd):
    return subprocess.run(cmd, capture_output=True, text=True, errors="replace")


def duration(path):
    out = sh(["ffprobe", "-v", "error", "-show_entries", "format=duration",
              "-of", "default=nw=1:nk=1", str(path)]).stdout.strip()
    try:
        return float(out)
    except ValueError:
        return 0.0


def levels(path, start=None, dur=None):
    """(mean_db, max_db) over a window, or the whole file."""
    cmd = ["ffmpeg", "-hide_banner", "-nostats"]
    if start is not None:
        cmd += ["-ss", f"{max(0, start):.3f}"]
    cmd += ["-i", str(path)]
    if dur is not None:
        cmd += ["-t", f"{dur:.3f}"]
    cmd += ["-af", "volumedetect", "-f", "null", "-"]
    err = sh(cmd).stderr
    mean = re.search(r"mean_volume:\s*(-?[\d.]+) dB", err)
    peak = re.search(r"max_volume:\s*(-?[\d.]+) dB", err)
    return (float(mean.group(1)) if mean else None,
            float(peak.group(1)) if peak else None)


def find_peak(path, step=STEP):
    """Sweep the file and return (peak_db, peak_time, total_duration)."""
    total = duration(path)
    if total <= 0:
        return None, None, 0.0
    best_db, best_t = -999.0, 0.0
    t = 0.0
    while t < total:
        _, pk = levels(path, t, min(step, total - t))
        if pk is not None and pk > best_db:
            best_db, best_t = pk, t
        t += step
    return best_db, best_t, total


def cmd_inspect(args):
    targets = []
    for raw in args.paths:
        p = Path(raw)
        if p.is_dir():
            targets += sorted(f for f in p.rglob("*") if f.suffix.lower() in AUDIO_EXT)
        elif p.is_file():
            targets.append(p)
    if not targets:
        print("no audio files found", file=sys.stderr)
        return 1

    problems = []
    for f in targets:
        _, file_peak = levels(f)
        peak_db, peak_t, total = find_peak(f)
        if file_peak is None or total <= 0:
            print(f"{f.name}: unreadable")
            continue

        win = min(args.window, total)
        _, win_peak = levels(f, 0.0, win)
        win_peak = win_peak if win_peak is not None else -999.0
        misses = (file_peak - win_peak) > MISS_MARGIN

        print(f"\n{f.name}  ({total:.2f}s)")
        print(f"  true peak      {file_peak:6.1f} dB at {peak_t:.2f}s")
        print(f"  first {win:.2f}s     {win_peak:6.1f} dB")
        if misses:
            tail = max(0.05, total - peak_t + 0.15)
            print(f"  ⚠ a {win:.2f}s window from the start misses the peak by "
                  f"{file_peak - win_peak:.1f} dB — it will be inaudible.")
            print(f"    extend the window to {peak_t + 0.25:.2f}s, or trim the tail:")
            print(f"    ffmpeg -sseof -{tail:.2f} -i {f.name} "
                  f'-af "afade=t=in:st=0:d=0.1" {f.stem}-swell{f.suffix}')
            problems.append(f.name)
        elif file_peak < -12.0:
            print(f"  ⚠ quiet throughout ({file_peak:.1f} dB) — not truncated, "
                  f"just weak. Pre-amplify:")
            print(f'    ffmpeg -i {f.name} -af "volume=+10dB,alimiter=limit=0.95" '
                  f"{f.stem}-boosted{f.suffix}")
            problems.append(f.name)
        else:
            print(f"  ok — peak lands inside a {win:.2f}s window")

    print(f"\n{len(problems)} of {len(targets)} file(s) need attention"
          + (": " + ", ".join(problems) if problems else ""))
    return 2 if problems else 0


def cmd_check(args):
    video = Path(args.video)
    if not video.is_file():
        print(f"error: no such file: {video}", file=sys.stderr)
        return 1

    times = list(args.at or [])
    if not times:
        tl = video.parent / "timeline.json"
        if tl.is_file():
            times = json.loads(tl.read_text()).get("seams", [])
        if not times:
            print("nothing to check — pass --at, or render first so seams exist")
            return 1

    base_mean, base_peak = baseline(video, times, args.window)
    if base_mean is None:
        print("error: could not measure a voice-only baseline", file=sys.stderr)
        return 1

    print(f"voice baseline: {base_mean:.1f} dB typical, {base_peak:.1f} dB peaks\n")
    weak = []
    for t in times:
        _, pk = levels(video, t - 0.05, args.window)
        if pk is None:
            continue
        delta = pk - base_mean
        verdict = "audible" if delta >= STING_TARGET else (
            "MARGINAL" if delta >= 1.0 else "INAUDIBLE")
        if delta < STING_TARGET:
            weak.append((t, delta))
        print(f"  {t:7.2f}s  {pk:6.1f} dB  {delta:+5.1f} vs voice   {verdict}")

    print()
    if weak:
        print(f"{len(weak)} sting(s) below the +{STING_TARGET:.0f} dB target:")
        for t, d in weak:
            print(f"  · {t:.2f}s is only {d:+.1f} dB over the voice")
        print("\nCheck the source file's peak placement before raising gain —")
        print("a truncated window cannot be fixed with volume:")
        print("  python3 scripts/sound.py inspect <the sfx file>")
        return 2
    print("all stings read clearly above the voice")
    return 0


def baseline(video, times, window):
    """Typical speech level away from any sting.

    Sampled across several windows and averaged, because a single window is
    unreliable: speech peaks are spiky, so one plosive can sit as high as a
    sting and hide a real difference. The comparison that matters is whether
    the transient rises above *typical* speech, not above its loudest instant."""
    total = duration(video)
    span = max(window, 1.0)
    means, peaks = [], []
    for f in (0.10, 0.22, 0.34, 0.46, 0.58, 0.70, 0.82, 0.94):
        probe = total * f
        if probe + span >= total:
            continue
        if any(abs(probe - t) < 1.5 for t in times):
            continue
        m, p = levels(video, probe, span)
        if m is not None and m > -50:
            means.append(m)
            peaks.append(p)
    if not means:
        m, p = levels(video, 0, min(2.0, total))
        return m, p
    return sum(means) / len(means), sum(peaks) / len(peaks)


def main():
    ap = argparse.ArgumentParser(description="sound placement and audibility")
    sub = ap.add_subparsers(dest="cmd", required=True)

    i = sub.add_parser("inspect", help="find where a file's peak really is")
    i.add_argument("paths", nargs="+", help="audio files or a directory")
    i.add_argument("--window", type=float, default=0.6,
                   help="the window length you intend to play (default 0.6s)")
    i.set_defaults(func=cmd_inspect)

    c = sub.add_parser("check", help="verify stings are audible in a render")
    c.add_argument("video")
    c.add_argument("--at", nargs="*", type=float, help="timestamps to check")
    c.add_argument("--window", type=float, default=0.30)
    c.set_defaults(func=cmd_check)

    args = ap.parse_args()
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())

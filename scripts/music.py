#!/usr/bin/env python3
"""Lay a music bed under the master, ducked beneath the voice.

Muxed onto the finished video rather than baked into the composition, so
changing the music or its level never costs a full re-render.

Ducking is sidechain-driven by default: the bed drops when the speaker talks
and recovers in the gaps. That keeps a bed audible in the pauses without it
ever competing with speech — a static level has to be set so low to stay clear
of the voice that nobody notices it at all.

    python3 scripts/music.py master.mp4 bed.mp3 -o final.mp4
    python3 scripts/music.py master.mp4 bed.mp3 --level 0.18 --no-duck
"""

import argparse
import re
import subprocess
import sys
from pathlib import Path


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
    cmd = ["ffmpeg", "-hide_banner", "-nostats"]
    if start is not None:
        cmd += ["-ss", f"{max(0, start):.3f}"]
    cmd += ["-i", str(path)]
    if dur is not None:
        cmd += ["-t", f"{dur:.3f}"]
    cmd += ["-af", "volumedetect", "-f", "null", "-"]
    err = sh(cmd).stderr
    m = re.search(r"mean_volume:\s*(-?[\d.]+) dB", err)
    p = re.search(r"max_volume:\s*(-?[\d.]+) dB", err)
    return (float(m.group(1)) if m else None, float(p.group(1)) if p else None)


def has_audio(path):
    out = sh(["ffprobe", "-v", "error", "-select_streams", "a",
              "-show_entries", "stream=index", "-of", "csv=p=0", str(path)]).stdout
    return bool(out.strip())


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("video")
    ap.add_argument("music")
    ap.add_argument("-o", "--out", default=None)
    ap.add_argument("--level", type=float, default=0.15,
                    help="bed gain before ducking (default 0.15)")
    ap.add_argument("--no-duck", action="store_true", help="static level instead")
    ap.add_argument("--fade", type=float, default=0.8, help="tail fade seconds")
    args = ap.parse_args()

    video, music = Path(args.video), Path(args.music)
    for f in (video, music):
        if not f.is_file():
            print(f"error: no such file: {f}", file=sys.stderr)
            return 1
    if not has_audio(video):
        print("error: the video has no audio track to mix under", file=sys.stderr)
        return 1

    dur = duration(video)
    if dur <= 0:
        print("error: could not read the video duration", file=sys.stderr)
        return 1
    fade_at = max(0.0, dur - args.fade)

    bed = (f"[1:a]aloop=loop=-1:size=2e9,atrim=0:{dur:.3f},"
           f"afade=t=out:st={fade_at:.3f}:d={args.fade},volume={args.level}[bed]")

    if args.no_duck:
        graph = f"{bed};[0:a][bed]amix=inputs=2:duration=first:normalize=0[a]"
    else:
        # Voice drives the compressor's sidechain; the bed is what gets pushed
        # down. normalize=0 keeps the voice at unity through the mix.
        graph = (f"{bed};[0:a]asplit=2[v1][v2];"
                 f"[bed][v1]sidechaincompress=threshold=0.05:ratio=8:attack=15:"
                 f"release=380[duck];"
                 f"[v2][duck]amix=inputs=2:duration=first:normalize=0[a]")

    out = Path(args.out) if args.out else video.with_name(f"{video.stem}_music.mp4")
    print(f"{'static' if args.no_duck else 'sidechain-ducked'} bed at {args.level:g} "
          f"· {dur:.1f}s · fade {args.fade:g}s")

    r = sh(["ffmpeg", "-y", "-loglevel", "error", "-i", str(video), "-i", str(music),
            "-filter_complex", graph, "-map", "0:v", "-map", "[a]",
            "-c:v", "copy", "-c:a", "aac", "-b:a", "192k", "-shortest", str(out)])
    if r.returncode != 0:
        print(f"error: mux failed:\n{r.stderr[-800:]}", file=sys.stderr)
        return 1

    # The bed must not have buried the speaker. Compare a speech moment before
    # and after; more than ~1.5 dB of loss means the level is too high.
    probe_at = dur * 0.4
    before, _ = levels(video, probe_at, 1.5)
    after, _ = levels(out, probe_at, 1.5)
    print(f"\n-> {out}")
    if before is not None and after is not None:
        delta = after - before
        print(f"   speech at {probe_at:.1f}s: {before:.1f} -> {after:.1f} dB ({delta:+.1f})")
        if delta < -1.5:
            print("   ⚠ the voice dropped — lower --level or keep ducking on")
        elif delta > 3.0:
            print("   ⚠ the mix got much louder; check for clipping")
        else:
            print("   voice preserved")
    print("\nListen before shipping. A bed nobody notices is doing nothing;")
    print("one that competes with the speaker is worse than none.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

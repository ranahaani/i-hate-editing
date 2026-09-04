#!/usr/bin/env python3
"""Lighting correction and colour grade.

Always emits a before/after comparison frame. A grade you have not looked at is
not a grade — and the common failure is not an ugly result, it is a correction
so subtle it does nothing while appearing to have worked.

    python3 scripts/grade.py cut.mp4 -o cut_lit.mp4
    python3 scripts/grade.py cut.mp4 --preset warm_lift --strength strong
    python3 scripts/grade.py cut.mp4 --compare-only     # frames, no render
"""

import argparse
import re
import subprocess
import sys
from pathlib import Path

# strength -> (shadow lift, contrast, saturation, gamma, brightness, temperature)
STRENGTH = {
    "subtle": (0.02, 1.04, 1.03, 1.03, 0.02, 5600),
    "normal": (0.04, 1.08, 1.08, 1.06, 0.04, 5200),
    "strong": (0.06, 1.12, 1.16, 1.10, 0.06, 4400),
}


def sh(cmd):
    return subprocess.run(cmd, capture_output=True, text=True, errors="replace")


def build_filter(preset, strength):
    if preset == "none":
        return None
    if preset not in ("warm_lift", "neutral_punch", "cool_clean"):
        return preset                      # raw ffmpeg filter string
    lift, con, sat, gam, bri, temp = STRENGTH[strength]
    if preset == "neutral_punch":
        sat, temp = 1.0 + (sat - 1.0) * 0.4, None
    if preset == "cool_clean":
        temp = 7200
    chain = [
        f"curves=all='0/{lift:.3f} 0.5/{0.5 + lift * 2:.3f} 1/0.99'",
        f"eq=brightness={bri:.3f}:contrast={con:.3f}:saturation={sat:.3f}:gamma={gam:.3f}",
    ]
    if temp:
        chain.append(f"colortemperature=temperature={temp}")
    chain.append("unsharp=5:5:0.3")
    return ",".join(chain)


def frame_stats(path):
    """Mean luma and saturation, for proving the grade actually did something."""
    err = sh(["ffmpeg", "-hide_banner", "-nostats", "-i", str(path),
              "-vf", "signalstats,metadata=print:key=lavfi.signalstats.YAVG",
              "-frames:v", "1", "-f", "null", "-"]).stderr
    m = re.search(r"YAVG=([\d.]+)", err)
    return float(m.group(1)) if m else None


def grab(video, t, dst, vf=None):
    cmd = ["ffmpeg", "-y", "-loglevel", "error", "-ss", f"{t:.2f}", "-i", str(video)]
    if vf:
        cmd += ["-vf", vf]
    cmd += ["-frames:v", "1", str(dst)]
    sh(cmd)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("video")
    ap.add_argument("-o", "--out", default=None)
    ap.add_argument("--preset", default="warm_lift",
                    choices=["warm_lift", "neutral_punch", "cool_clean", "none"],
                    help="or pass a raw ffmpeg filter string")
    ap.add_argument("--filter", dest="raw", help="raw ffmpeg filter chain")
    ap.add_argument("--strength", default="normal", choices=list(STRENGTH))
    ap.add_argument("--at", type=float, default=None, help="comparison frame time")
    ap.add_argument("--compare-only", action="store_true")
    args = ap.parse_args()

    src = Path(args.video)
    if not src.is_file():
        print(f"error: no such file: {src}", file=sys.stderr)
        return 1

    vf = build_filter(args.raw or args.preset, args.strength)
    if vf is None:
        print("preset 'none' — nothing to do")
        return 0

    dur = float(sh(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                    "-of", "default=nw=1:nk=1", str(src)]).stdout.strip() or 0)
    t = args.at if args.at is not None else max(0.5, dur * 0.35)

    outdir = src.parent / "verify"
    outdir.mkdir(parents=True, exist_ok=True)
    before, after = outdir / "grade_before.png", outdir / "grade_after.png"
    grab(src, t, before)
    grab(src, t, after, vf)

    y0, y1 = frame_stats(before), frame_stats(after)
    side = outdir / "grade_compare.png"
    sh(["ffmpeg", "-y", "-loglevel", "error", "-i", str(before), "-i", str(after),
        "-filter_complex", "hstack=inputs=2", str(side)])

    print(f"{args.raw or args.preset} · {args.strength}")
    print(f"  {vf}")
    print(f"\ncomparison at {t:.2f}s -> {side}")
    if y0 and y1:
        delta = y1 - y0
        print(f"  mean luma {y0:.1f} -> {y1:.1f}  ({delta:+.1f})")
        if abs(delta) < 2.0:
            print("  ⚠ barely changed. A grade that measures this close to the")
            print("    original is doing nothing — go up a strength, or the")
            print("    footage may need a different correction than exposure.")
    print("\nLook at the comparison before rendering. Check: skin natural, no")
    print("blown highlights, background not muddy.")

    if args.compare_only:
        return 0

    out = Path(args.out) if args.out else src.with_name(f"{src.stem}_graded.mp4")
    print(f"\nrendering -> {out}")
    proc = sh(["ffmpeg", "-y", "-loglevel", "error", "-i", str(src),
               "-vf", vf, "-c:v", "libx264", "-crf", "18", "-preset", "medium",
               "-pix_fmt", "yuv420p", "-c:a", "copy", str(out)])
    if proc.returncode != 0:
        print(f"error: grade failed:\n{proc.stderr[-600:]}", file=sys.stderr)
        return 1
    print("done")
    return 0


if __name__ == "__main__":
    sys.exit(main())

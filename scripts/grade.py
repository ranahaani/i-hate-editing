#!/usr/bin/env python3
"""Lighting correction and colour grade.

Always emits a before/after comparison frame. A grade you have not looked at is
not a grade — and the common failure is not an ugly result, it is a correction
so subtle it does nothing while appearing to have worked.

    python3 scripts/grade.py cut.mp4 -o cut_lit.mp4
    python3 scripts/grade.py cut.mp4 --preset warm_lift --strength strong
    python3 scripts/grade.py cut.mp4 --compare-only     # frames, no render
    python3 scripts/grade.py cut.mp4 --preset loss_red --window 1.2:1.9

`--window t0:t1` applies the grade between those output-timeline seconds only,
easing in and out over `--ease` (default 0.1s) and returning to the untouched
source outside it. `loss_red` is the semantic warm-red grade for a negation or
a loss (rules/hooks.md) and requires a window: red for the length of one word,
never the whole cut.
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


LOSS_RED = ("colorbalance=rs=0.22:gs=-0.14:bs=-0.18:rm=0.30:gm=-0.22:bm=-0.24:"
            "rh=0.14:gh=-0.10:bh=-0.10,eq=contrast=1.06:saturation=1.12")
DEFAULT_EASE = 0.1


def sh(cmd):
    return subprocess.run(cmd, capture_output=True, text=True, errors="replace")


def build_filter(preset, strength):
    if preset == "none":
        return None
    if preset == "loss_red":
        return LOSS_RED
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


def parse_window(text, ease=DEFAULT_EASE):
    """'t0:t1' -> (t0, t1, ease). The ease is shortened for a window under
    twice its length, so the grade still reaches full strength at the midpoint."""
    try:
        t0, t1 = (float(p) for p in text.split(":"))
    except ValueError:
        raise ValueError(f"window must be t0:t1 in seconds, got {text!r}")
    if t0 < 0 or t1 <= t0:
        raise ValueError(f"window needs 0 <= t0 < t1, got {t0}:{t1}")
    if ease <= 0:
        raise ValueError("ease must be positive")
    return t0, t1, min(ease, (t1 - t0) / 2)


def window_weight(t, t0, t1, ease):
    """Grade strength at time t: 0 outside, 1 inside, smoothstep over the
    ease. Mirrors the ffmpeg expression in apply_window."""
    w = max(0.0, min(1.0, min((t - t0) / ease, (t1 - t) / ease)))
    return w * w * (3 - 2 * w)


def apply_window(vf, t0, t1, ease):
    """Wrap a filter chain so it applies inside [t0, t1] only.

    The graded copy is blended with the untouched one by `window_weight`.
    Outside the window the weight is exactly 0, so A + (B - A) * 0 returns the
    source pixel unchanged."""
    w = f"clip(min((T-{t0:.4f})/{ease:.4f},({t1:.4f}-T)/{ease:.4f}),0,1)"
    mix = f"st(0,{w});A+(B-A)*ld(0)*ld(0)*(3-2*ld(0))"
    return f"split[a][b];[b]{vf}[g];[a][g]blend=all_expr='{mix}'"


def frame_stats(path):
    """Mean luma and saturation, for proving the grade actually did something."""
    err = sh(["ffmpeg", "-hide_banner", "-nostats", "-i", str(path),
              "-vf", "signalstats,metadata=print:key=lavfi.signalstats.YAVG",
              "-frames:v", "1", "-f", "null", "-"]).stderr
    m = re.search(r"YAVG=([\d.]+)", err)
    return float(m.group(1)) if m else None


def frame_red(path):
    """Mean V (red-difference) chroma. A red grade moves this, not luma."""
    err = sh(["ffmpeg", "-hide_banner", "-nostats", "-i", str(path),
              "-vf", "signalstats,metadata=print:key=lavfi.signalstats.VAVG",
              "-frames:v", "1", "-f", "null", "-"]).stderr
    m = re.search(r"VAVG=([\d.]+)", err)
    return float(m.group(1)) if m else None


def grab(video, t, dst, vf=None):
    # -copyts keeps the source timeline after the seek, so a windowed grade
    # sees the real time and not a clock restarted at zero.
    cmd = ["ffmpeg", "-y", "-loglevel", "error", "-ss", f"{t:.2f}", "-copyts",
           "-i", str(video)]
    if vf:
        cmd += ["-vf", vf]
    cmd += ["-frames:v", "1", str(dst)]
    sh(cmd)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("video")
    ap.add_argument("-o", "--out", default=None)
    ap.add_argument("--preset", default="warm_lift",
                    choices=["warm_lift", "neutral_punch", "cool_clean", "loss_red", "none"],
                    help="or pass a raw ffmpeg filter string")
    ap.add_argument("--filter", dest="raw", help="raw ffmpeg filter chain")
    ap.add_argument("--strength", default="normal", choices=list(STRENGTH))
    ap.add_argument("--window", default=None, metavar="T0:T1",
                    help="apply the grade between these seconds only (required for loss_red)")
    ap.add_argument("--ease", type=float, default=DEFAULT_EASE,
                    help="seconds to ease the window in and out")
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
    window = None
    if args.preset == "loss_red" and not args.raw and not args.window:
        print("error: loss_red needs --window t0:t1 (red for one word, not the cut)",
              file=sys.stderr)
        return 1
    if args.window:
        try:
            window = parse_window(args.window, args.ease)
        except ValueError as err:
            print(f"error: {err}", file=sys.stderr)
            return 1
        vf = apply_window(vf, *window)

    dur = float(sh(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                    "-of", "default=nw=1:nk=1", str(src)]).stdout.strip() or 0)
    if args.at is not None:
        t = args.at
    elif window:
        t = (window[0] + window[1]) / 2        # the default frame must be graded
    else:
        t = max(0.5, dur * 0.35)
    if window and window[1] > dur + 0.05:
        print(f"error: window ends at {window[1]:.2f}s, past the {dur:.2f}s cut",
              file=sys.stderr)
        return 1

    outdir = src.parent / "verify"
    outdir.mkdir(parents=True, exist_ok=True)
    before, after = outdir / "grade_before.png", outdir / "grade_after.png"
    grab(src, t, before)
    grab(src, t, after, vf)

    y0, y1 = frame_stats(before), frame_stats(after)
    side = outdir / "grade_compare.png"
    sh(["ffmpeg", "-y", "-loglevel", "error", "-i", str(before), "-i", str(after),
        "-filter_complex", "hstack=inputs=2", str(side)])

    label = args.raw or args.preset
    if window:
        label += f" · window {window[0]:.2f}-{window[1]:.2f}s, ease {window[2]:.2f}s"
    print(f"{label} · {args.strength}")
    print(f"  {vf}")
    print(f"\ncomparison at {t:.2f}s -> {side}")
    if args.preset == "loss_red" and not args.raw:
        v0, v1 = frame_red(before), frame_red(after)
        if v0 and v1:
            print(f"  mean red chroma (V) {v0:.1f} -> {v1:.1f}  ({v1 - v0:+.1f})")
            if v1 - v0 < 3.0:
                print("  ⚠ red barely moved: at this frame the window is not at full")
                print("    strength, or the grade is too weak to read as red.")
    elif y0 and y1:
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

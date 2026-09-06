#!/usr/bin/env python3
"""Render an EDL into a cut.

Per hard rule 2 the pipeline is extract-per-segment then lossless concat: each
range is encoded exactly once (with its edge fades and any grade), then the
segments are joined with stream copy. A single-pass filtergraph would re-encode
everything again as soon as overlays are added.

    python3 scripts/render.py --studio <footage>/studio
    python3 scripts/render.py --studio ... --preview      # fast 720p draft
    python3 scripts/render.py --edl path/to/edl.json -o out.mp4

EDL:
{
  "sources": {"take1": "/abs/take1.mp4"},
  "ranges": [{"source":"take1","start":2.42,"end":6.85,"beat":"HOOK","reason":"..."}],
  "pad":    {"in": 0.05, "out": 0.08},
  "grade":  null
}
"""

import argparse
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from media import probe  # noqa: E402  (rotation-aware)

FADE = 0.030          # hard rule 3 — 30ms audio fade at every boundary
PAD_MIN, PAD_MAX = 0.030, 0.200   # hard rule 7 working window

GRADES = {
    "none": None,
    "neutral_punch": "eq=contrast=1.06:saturation=1.04,curves=all='0/0.02 0.5/0.53 1/0.99'",
    "warm_lift": ("curves=all='0/0.04 0.5/0.58 1/0.99',"
                  "eq=brightness=0.04:contrast=1.08:saturation=1.10:gamma=1.06,"
                  "colortemperature=temperature=5000,unsharp=5:5:0.3"),
}


def die(msg):
    print(f"error: {msg}", file=sys.stderr)
    sys.exit(1)


def clamp_pad(v):
    return max(PAD_MIN, min(PAD_MAX, float(v)))


def extract(src, start, end, dst, target, grade, preview, speed=1.0,
            zoom=1.0, zoom_y=0.42):
    """Encode one segment: normalised geometry, graded, with edge fades.

    Speed is applied here rather than to the finished cut so that the timeline
    records sped durations. Captions and sound are timed from that timeline, so
    speeding up afterwards would drift every one of them."""
    dur = end - start
    if dur <= 0:
        die(f"non-positive range on {Path(src).name}: {start}->{end}")

    w, h, fps = target
    if preview:
        w, h = (w // 2 // 2) * 2, (h // 2 // 2) * 2

    vf = []
    if zoom > 1.001:
        # Reframe by cropping in. rules/proof.md calls for changing the shot
        # scale when there is no B-roll — cutting chest-up to a tighter crop is
        # a real cut. zoom_y biases the crop upward because faces sit high.
        vf.append(f"crop=iw/{zoom:.4f}:ih/{zoom:.4f}:"
                  f"(iw-iw/{zoom:.4f})/2:(ih-ih/{zoom:.4f})*{zoom_y:.3f}")
    vf += [f"scale={w}:{h}:force_original_aspect_ratio=decrease",
           f"pad={w}:{h}:(ow-iw)/2:(oh-ih)/2",
           f"fps={fps}", "setsar=1"]
    if grade:
        vf.insert(0, grade)

    af_parts = []
    if abs(speed - 1.0) > 0.001:
        vf.append(f"setpts=PTS/{speed:.4f}")
        # atempo is only valid 0.5-2.0; chain it for anything outside that.
        remaining, tempo = speed, []
        while remaining > 2.0:
            tempo.append(2.0)
            remaining /= 2.0
        while remaining < 0.5:
            tempo.append(0.5)
            remaining /= 0.5
        tempo.append(remaining)
        af_parts += [f"atempo={t:.4f}" for t in tempo]
        dur = dur / speed

    out_fade = max(0.0, dur - FADE)
    af_parts += [f"afade=t=in:st=0:d={FADE}",
                 f"afade=t=out:st={out_fade:.3f}:d={FADE}"]
    af = ",".join(af_parts)

    # -ss and -t must BOTH precede -i. After -i, -t is an output-side limit
    # measured on the sped timeline, which pulls extra source and cancels the
    # speed change entirely. Only visible when speed != 1.
    src_dur = (end - start)
    cmd = ["ffmpeg", "-y", "-loglevel", "error",
           "-ss", f"{start:.3f}", "-t", f"{src_dur:.3f}", "-i", str(src),
           "-vf", ",".join(vf), "-af", af,
           "-c:v", "libx264", "-preset", "veryfast" if preview else "medium",
           "-crf", "26" if preview else "18", "-pix_fmt", "yuv420p",
           "-c:a", "aac", "-b:a", "192k", "-ar", "48000", "-ac", "2",
           "-video_track_timescale", "90000",
           str(dst)]
    proc = subprocess.run(cmd, capture_output=True, text=True, errors="replace")
    if proc.returncode != 0:
        die(f"segment encode failed ({Path(src).name} {start:.2f}-{end:.2f}):\n{proc.stderr[-800:]}")


def concat(parts, out):
    with tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False) as f:
        for p in parts:
            f.write(f"file '{Path(p).resolve()}'\n")
        listfile = f.name
    try:
        proc = subprocess.run(
            ["ffmpeg", "-y", "-loglevel", "error", "-f", "concat", "-safe", "0",
             "-i", listfile, "-c", "copy", "-movflags", "+faststart", str(out)],
            capture_output=True, text=True, errors="replace")
        if proc.returncode != 0:
            die(f"concat failed:\n{proc.stderr[-800:]}")
    finally:
        Path(listfile).unlink(missing_ok=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--studio", default="studio")
    ap.add_argument("--edl", default=None)
    ap.add_argument("-o", "--out", default=None)
    ap.add_argument("--speed", type=float, default=None,
                    help="playback speed; 1.2 is the short-form default")
    ap.add_argument("--preview", action="store_true", help="fast half-size draft")
    ap.add_argument("--keep-segments", action="store_true")
    args = ap.parse_args()

    studio = Path(args.studio)
    edl_path = Path(args.edl) if args.edl else studio / "edl.json"
    if not edl_path.is_file():
        die(f"no EDL at {edl_path}")
    edl = json.loads(edl_path.read_text())

    ranges = edl.get("ranges") or []
    if not ranges:
        die("EDL has no ranges")
    sources = edl.get("sources") or {}

    pad = edl.get("pad") or {}
    pad_in, pad_out = clamp_pad(pad.get("in", 0.05)), clamp_pad(pad.get("out", 0.08))

    speed = args.speed if args.speed else float(edl.get("speed", 1.0))
    grade_key = edl.get("grade") or "none"
    grade = GRADES.get(grade_key, grade_key if grade_key not in GRADES else None)
    if grade_key not in GRADES and grade_key != "none":
        grade = grade_key            # raw ffmpeg filter string

    # Normalise every segment to the first source's geometry.
    first = sources.get(ranges[0]["source"]) or ranges[0]["source"]
    iw, ih, _ = probe(first)
    info = {"w": iw, "h": ih}
    if not info["w"]:
        die(f"could not probe {first}")
    target = (info["w"], info["h"], 30)

    work = studio / "segments"
    if work.exists():
        shutil.rmtree(work)
    work.mkdir(parents=True)

    parts, timeline, cursor = [], [], 0.0
    print(f"{len(ranges)} ranges · {target[0]}x{target[1]}@{target[2]}"
          f"{f' · {speed:g}x' if abs(speed - 1.0) > 0.001 else ''}"
          f"{' · preview' if args.preview else ''}")

    for i, r in enumerate(ranges):
        src = sources.get(r["source"], r["source"])
        if not Path(src).is_file():
            die(f"source not found: {src}")
        _, _, src_dur = probe(src)
        sinfo = {"duration": src_dur}
        start = max(0.0, float(r["start"]) - pad_in)
        end = min(sinfo["duration"], float(r["end"]) + pad_out)
        dst = work / f"seg_{i:03d}.mp4"
        extract(src, start, end, dst, target, grade, args.preview, speed,
                float(r.get("zoom", 1.0)), float(r.get("zoom_y", 0.42)))
        d = probe(dst)[2]
        timeline.append({
            "index": i,
            "beat": r.get("beat"),
            "source": r["source"],
            "source_start": round(start, 3),
            "source_end": round(end, 3),
            "out_start": round(cursor, 3),
            "out_end": round(cursor + d, 3),
        })
        cursor += d
        parts.append(dst)
        zl = f"  {float(r.get('zoom', 1.0)):.2f}x" if float(r.get("zoom", 1.0)) > 1.001 else ""
        print(f"  [{i:02d}] {r.get('beat') or '-':<12} {r['source']} "
              f"{start:7.2f}-{end:7.2f}  ->  {timeline[-1]['out_start']:7.2f}{zl}")

    out = Path(args.out) if args.out else studio / ("preview.mp4" if args.preview else "cut.mp4")
    out.parent.mkdir(parents=True, exist_ok=True)
    concat(parts, out)

    # Seam positions are what the verify pass needs; write them next to the cut.
    seams = [t["out_start"] for t in timeline[1:]]
    (studio / "timeline.json").write_text(json.dumps({
        "output": str(out.resolve()),
        "speed": speed,
        "predicted_duration": round(cursor, 3),
        "segments": timeline,
        "seams": seams,
    }, indent=2))

    if not args.keep_segments:
        shutil.rmtree(work, ignore_errors=True)

    actual = probe(out)[2]
    drift = abs(actual - cursor)
    print(f"\n{out}  {actual:.2f}s (predicted {cursor:.2f}s, drift {drift:.3f}s)")
    if drift > 0.15:
        print("  warning: duration drift over 150ms — check for variable frame rate sources")
    print(f"{len(seams)} seam(s) -> {studio / 'timeline.json'}")
    print("\nNext: python3 scripts/verify.py --studio", args.studio)
    return 0


if __name__ == "__main__":
    sys.exit(main())

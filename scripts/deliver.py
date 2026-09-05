#!/usr/bin/env python3
"""Assemble the delivery package.

An editor hands back more than a file. This produces the master's platform
variants, thumbnail candidates, and the raw material for the post copy, so
nothing is left for the user to assemble.

Wording is not generated here. Titles and captions are judgement, and a
generated one reads like it — this surfaces the strongest lines the speaker
actually said, for the agent to write from.

    python3 scripts/deliver.py --studio <footage>/studio
    python3 scripts/deliver.py --studio ... --aspects 9:16 1:1 16:9
"""

import argparse
import glob
import json
import re
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from media import probe  # noqa: E402  (rotation-aware)
from transcribe import read_profile  # noqa: E402

ASPECTS = {
    "9:16": (1080, 1920),
    "1:1": (1080, 1080),
    "16:9": (1920, 1080),
    "4:5": (1080, 1350),
}
THUMB_CANDIDATES = 6


def sh(cmd):
    return subprocess.run(cmd, capture_output=True, text=True, errors="replace")


def dst_ar_wider(src_w, src_h, tw, th):
    return (tw / th) > (src_w / src_h)


def has_captions(studio):
    c = Path(studio) / "captions.json"
    if not c.is_file():
        return False
    try:
        return bool(json.loads(c.read_text()).get("chunks"))
    except Exception:
        return False


def sharpness(path):
    """Laplacian-ish variance: a sharp frame beats a motion-blurred one."""
    try:
        from PIL import Image, ImageFilter, ImageStat
    except ImportError:
        return 0.0
    im = Image.open(path).convert("L").resize((320, 568))
    edges = im.filter(ImageFilter.FIND_EDGES)
    return ImageStat.Stat(edges).stddev[0]


def brightness(path):
    try:
        from PIL import Image, ImageStat
    except ImportError:
        return 0.0
    return ImageStat.Stat(Image.open(path).convert("L")).mean[0]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--studio", default="studio")
    ap.add_argument("--master", default=None)
    ap.add_argument("--aspects", nargs="*", default=None)
    ap.add_argument("--focus", type=float, default=0.35,
                    help="vertical crop bias, 0=top 1=bottom (faces sit high)")
    args = ap.parse_args()

    studio = Path(args.studio)
    out = studio / "out"
    out.mkdir(parents=True, exist_ok=True)

    master = Path(args.master) if args.master else None
    if not master:
        for cand in (out / "final.mp4", out / "master.mp4"):
            if cand.is_file():
                master = cand
                break
    if not master or not master.is_file():
        print("error: no master found — run compose.py --render first", file=sys.stderr)
        return 1

    profile = read_profile(studio)
    aspects = args.aspects or profile.get("aspects") or ["9:16"]
    if isinstance(aspects, str):
        aspects = [aspects]

    sw, sh_, dur = probe(master)
    print(f"master {master.name} · {sw}x{sh_} · {dur:.1f}s")

    manifest = {"master": str(master), "duration": round(dur, 2), "variants": {}}

    for a in aspects:
        if a not in ASPECTS:
            print(f"  skip unknown aspect {a}")
            continue
        tw, th = ASPECTS[a]
        dst = out / f"{master.stem}_{a.replace(':', 'x')}.mp4"
        if (tw, th) == (sw, sh_):
            manifest["variants"][a] = str(master)
            print(f"  {a:<5} native")
            continue
        vf, style = variant_filter(sw, sh_, tw, th, args.focus)
        flag = "-filter_complex" if "split=2" in vf else "-vf"
        r = sh(["ffmpeg", "-y", "-loglevel", "error", "-i", str(master),
                flag, vf, "-c:v", "libx264", "-crf", "19", "-preset", "medium",
                "-pix_fmt", "yuv420p", "-c:a", "copy", str(dst)])
        if r.returncode != 0:
            print(f"  {a:<5} FAILED: {r.stderr[-200:]}")
            continue
        manifest["variants"][a] = str(dst)
        note = ""
        if style == "cropped" and dst_ar_wider(sw, sh_, tw, th) and has_captions(studio):
            # Captions live in the lower part of the frame, which is exactly
            # what a vertical-to-square crop removes.
            note = "  ⚠ captions fall outside this crop"
            manifest.setdefault("warnings", []).append(
                f"{a}: captions are cropped out; re-render the composition at "
                f"{tw}x{th} if this variant needs them")
        print(f"  {a:<5} {tw}x{th} ({style}) -> {dst.name}{note}")

    # Thumbnail candidates. Sampled away from cuts, ranked by sharpness — the
    # agent picks, because "face visible, not mid-blink" is a judgement a
    # metric cannot make.
    thumbs = out / "thumbnails"
    thumbs.mkdir(exist_ok=True)
    for old in thumbs.glob("*.png"):
        old.unlink()
    tl_path = studio / "timeline.json"
    seams = json.loads(tl_path.read_text()).get("seams", []) if tl_path.is_file() else []
    scored = []
    for i in range(THUMB_CANDIDATES):
        t = dur * (i + 0.5) / THUMB_CANDIDATES
        if any(abs(t - s) < 0.4 for s in seams):
            t += 0.5
        t = min(t, max(0.0, dur - 0.1))
        p = thumbs / f"t{i}_{t:.1f}s.png"
        sh(["ffmpeg", "-y", "-loglevel", "error", "-ss", f"{t:.2f}",
            "-i", str(master), "-frames:v", "1", str(p)])
        if p.is_file():
            scored.append((sharpness(p), brightness(p), t, p))
    scored.sort(reverse=True)
    manifest["thumbnails"] = [str(p) for _, _, _, p in scored]
    if scored:
        print(f"\n{len(scored)} thumbnail candidates (sharpest first):")
        for s_, b_, t, p in scored[:3]:
            print(f"  {p.name}  sharpness {s_:.1f}  brightness {b_:.0f}")
        print("  Look at these — pick one with the face clear and eyes open.")

    # Raw material for the post copy: the strongest complete lines spoken.
    lines = []
    caps = studio / "captions.json"
    if caps.is_file():
        text = " ".join(c["text"] for c in json.loads(caps.read_text())["chunks"])
        for s_ in re.split(r"(?<=[.?!])\s+", text):
            s_ = s_.strip()
            if 25 <= len(s_) <= 170:
                lines.append(s_)
    manifest["spoken_lines"] = lines[:8]

    copy_path = out / "post.md"
    if not copy_path.is_file():
        copy_path.write_text(
            "# Post copy\n\n"
            "Write these from the lines below. Do not paste them verbatim —\n"
            "they are transcription, not copy.\n\n"
            "## Caption\n\n_hook line_\n\n_two lines of substance_\n\n_hashtags_\n\n"
            "## Titles\n\n- \n- \n- \n\n"
            "## Lines actually spoken\n\n"
            + ("\n".join(f"- {l}" for l in lines[:8]) or "_(no captions found)_")
            + "\n")
        print(f"\ncopy scaffold -> {copy_path}")
    else:
        print(f"\ncopy already written -> {copy_path}")

    (out / "manifest.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False))
    print(f"manifest -> {out / 'manifest.json'}")
    if manifest.get("warnings"):
        print("\nwarnings:")
        for w in manifest["warnings"]:
            print(f"  · {w}")
    print("\nPackage is not done until the copy is written and a thumbnail chosen.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

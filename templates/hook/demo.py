#!/usr/bin/env python3
"""Render a shatter over a real clip through the real compose.py skeleton.

    python3 demo.py clip.mp4 --word NEVER --t-hit 1.8 \
        --zone 90,380,900,230 --face 300,640,480,560 --out /path/to/workdir

Proves the fragment splices into compose.build_html output and renders. Writes
the composition and master.mp4 under --out, never into the skill directory
(hard rule 14).
"""

import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parents[1] / "scripts"))

import compose  # noqa: E402
import shatter  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("clip")
    ap.add_argument("--word", required=True)
    ap.add_argument("--t-hit", type=float, required=True)
    ap.add_argument("--zone", required=True)
    ap.add_argument("--face")
    ap.add_argument("--out", required=True)
    ap.add_argument("--render", action="store_true")
    args = ap.parse_args()

    clip = Path(args.clip)
    width, height, duration = compose.probe(clip)
    comp = Path(args.out) / "composition"
    comp.mkdir(parents=True, exist_ok=True)
    shutil.copy2(clip, comp / clip.name)
    (comp / "hyperframes.json").write_text(
        json.dumps(compose.HYPERFRAMES_JSON, indent=2))
    (comp / "package.json").write_text(
        json.dumps(compose.PACKAGE_JSON, indent=2))

    fragment = shatter.build(
        args.word, args.t_hit, shatter.parse_box(args.zone),
        shatter.parse_box(args.face) if args.face else None,
        frame=(width, height))
    html = compose.build_html(clip.name, width, height, duration, [], {})
    (comp / "index.html").write_text(shatter.splice(html, fragment))
    print(f"-> {comp / 'index.html'}  ({fragment['shards']} shards)")

    for sub in ("check", "render"):
        if sub == "render" and not args.render:
            break
        cmd = ["npx", "--yes", compose.HYPERFRAMES_PKG, sub]
        if sub == "render":
            cmd += [".", "-q", "high", "--crf", "16", "--video-frame-format", "png",
                    "-o", str((Path(args.out) / "master.mp4").resolve())]
        r = subprocess.run(cmd, cwd=comp, capture_output=True, text=True, errors="replace")
        print((r.stdout or r.stderr)[-1200:])
        if r.returncode != 0:
            return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
"""Generate a HyperFrames composition from the cut and its captions.

Captions are rendered as HTML text over the video rather than burned in with
ffmpeg, which is both better looking and necessary: many ffmpeg builds ship
without libass, so the subtitles filter simply is not available.

    python3 scripts/compose.py --studio <footage>/studio
    python3 scripts/compose.py --studio ... --render

Styling comes entirely from profile.yml. There are no brand values in here.
"""

import argparse
import html
import json
import shutil
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from transcribe import read_profile  # noqa: E402

# Visual clips can sit on any track. AUDIO must stay low — HyperFrames drops
# or attenuates audio on high track indices without raising an error, so a
# sting placed up here plays silently in the render.
TRACK_VIDEO = 1
TRACK_CAPTION = 60
AUDIO_TRACK_CEILING = 40

HYPERFRAMES_JSON = {
    "$schema": "https://hyperframes.heygen.com/schema/hyperframes.json",
    "registry": "https://raw.githubusercontent.com/heygen-com/hyperframes/main/registry",
    "paths": {"blocks": "compositions", "components": "compositions/components",
              "assets": "assets"},
    "media": {"autoProxy": True},
}

PACKAGE_JSON = {
    "name": "editkit-composition", "private": True, "version": "1.0.0",
    "scripts": {
        "dev": "npx --yes hyperframes preview",
        "check": "npx --yes hyperframes check",
        "render": "npx --yes hyperframes render",
    },
}


def probe(path):
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "v:0",
         "-show_entries", "stream=width,height", "-show_entries", "format=duration",
         "-of", "json", str(path)],
        capture_output=True, text=True, errors="replace").stdout
    d = json.loads(out or "{}")
    st = (d.get("streams") or [{}])[0]
    return (st.get("width") or 1080, st.get("height") or 1920,
            float((d.get("format") or {}).get("duration") or 0))


def caption_css(profile, width):
    accent = (profile.get("brand") or {}).get("accent", "#FFE300")
    # Named fallbacks like Impact are not in the renderer's auto-resolved font
    # list, so they fail the font_family_without_font_face check and would
    # silently render with wrong typography. Only a generic family follows.
    font = (profile.get("brand") or {}).get("font", "Archivo Black")
    big = round(width * 0.070)
    small = round(width * 0.044)
    # No background box. Legibility comes from a multi-directional outline so
    # the video stays visible underneath (rules/captions.md).
    shadow = ("0 0 9px #000, 3px 3px 0 #000, -3px -3px 0 #000, "
              "3px -3px 0 #000, -3px 3px 0 #000, 5px 6px 0 rgba(0,0,0,0.55)")
    return f"""
      .caption {{
        position: absolute;
        left: 5%; width: 90%;
        bottom: 16%;
        text-align: center;
        font-family: "{font}", sans-serif;
        line-height: 1.12;
        text-shadow: {shadow};
        text-transform: uppercase;
      }}
      .caption .w {{
        display: inline-block;
        margin: 0 0.12em;
        font-size: {small}px;
        color: #fff;
        vertical-align: baseline;
      }}
      .caption .w.em {{
        font-size: {big}px;
        color: {accent};
      }}
"""


def build_html(video_name, width, height, duration, chunks, profile):
    esc = html.escape
    clips, anims = [], []

    # No `muted` attribute. It is a boolean attribute, so even muted="false"
    # mutes the element and the whole edit renders silent.
    # Never add a `muted` attribute here. It is a boolean HTML attribute, so
    # even muted="false" mutes the element — and the entire edit then renders
    # with no voice at all, silently, with every check still passing.
    clips.append(
        f'      <video id="face" class="clip" src="{esc(video_name)}" data-has-audio="true"\n'
        f'             data-start="0" data-duration="{duration:.2f}" '
        f'data-track-index="{TRACK_VIDEO}"\n'
        f'             style="position:absolute;top:0;left:0;width:100%;height:100%;'
        f'object-fit:cover;"></video>')

    for i, c in enumerate(chunks):
        cid = f"cap{i}"
        words = "".join(
            f'<span class="w{" em" if w["emphasis"] else ""}">{esc(w["text"])}</span>'
            for w in c["words"])
        clips.append(
            f'      <div id="{cid}" class="clip" data-start="{c["start"]:.2f}" '
            f'data-duration="{c["duration"]:.2f}" data-track-index="{TRACK_CAPTION}">\n'
            f'        <div class="inner caption">{words}</div>\n'
            f'      </div>')
        t = c["start"]
        # Whole chunk lifts in; the emphasis word overshoots on top of it. The
        # pop is what makes captions read as authored rather than burned in.
        anims.append(
            f'      tl.from("#{cid} .inner", {{ opacity: 0, y: 18, duration: 0.14, '
            f'ease: "power2.out" }}, {t:.2f});')
        # Only when the chunk actually has an emphasis word — a tween aimed at
        # a selector that matches nothing is a silent no-op and warns at render.
        if any(w["emphasis"] for w in c["words"]):
            anims.append(
                f'      tl.from("#{cid} .inner .em", {{ scale: 0.72, duration: 0.22, '
                f'ease: "back.out(2.4)", transformOrigin: "50% 60%" }}, {t:.2f});')

    return f"""<!doctype html>
<html lang="en">
  <head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width={width}, height={height}" />
    <script src="https://cdn.jsdelivr.net/npm/gsap@3.14.2/dist/gsap.min.js"></script>
    <style>
      * {{ margin: 0; padding: 0; box-sizing: border-box; }}
      html, body {{
        margin: 0; width: {width}px; height: {height}px;
        overflow: hidden; background: #000;
      }}
{caption_css(profile, width)}
    </style>
  </head>
  <body>
    <div id="root" data-composition-id="main"
         data-start="0" data-duration="{duration:.2f}"
         data-width="{width}" data-height="{height}">
{chr(10).join(clips)}
    </div>

    <script>
      window.__timelines = window.__timelines || {{}};
      const tl = gsap.timeline({{ paused: true }});
{chr(10).join(anims)}
      window.__timelines["main"] = tl;
    </script>
  </body>
</html>
"""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--studio", default="studio")
    ap.add_argument("--video", default=None, help="defaults to the graded cut, else cut.mp4")
    ap.add_argument("--render", action="store_true")
    ap.add_argument("--check", action="store_true", default=True)
    args = ap.parse_args()

    studio = Path(args.studio)
    caps_path = studio / "captions.json"
    if not caps_path.is_file():
        print("error: no captions.json — run captions.py first", file=sys.stderr)
        return 1
    chunks = json.loads(caps_path.read_text())["chunks"]

    if args.video:
        video = Path(args.video)
    else:
        graded = studio / "cut_graded.mp4"
        video = graded if graded.is_file() else studio / "cut.mp4"
    if not video.is_file():
        print(f"error: no video at {video}", file=sys.stderr)
        return 1

    profile = read_profile(studio)
    width, height, duration = probe(video)

    comp = studio / "composition"
    comp.mkdir(parents=True, exist_ok=True)
    (comp / "hyperframes.json").write_text(json.dumps(HYPERFRAMES_JSON, indent=2))
    (comp / "package.json").write_text(json.dumps(PACKAGE_JSON, indent=2))
    shutil.copy2(video, comp / video.name)

    trailing = [c for c in chunks if c["end"] > duration + 0.05]
    if trailing:
        print(f"  note: {len(trailing)} caption(s) run past the video end; trimming")
        for c in trailing:
            c["end"] = min(c["end"], duration)
            c["duration"] = max(0.1, c["end"] - c["start"])

    (comp / "index.html").write_text(
        build_html(video.name, width, height, duration, chunks, profile))

    print(f"{len(chunks)} captions over {duration:.1f}s · {width}x{height}")
    print(f"-> {comp / 'index.html'}")

    if args.check:
        print("\nchecking…")
        r = subprocess.run(["npx", "--yes", "hyperframes", "check"], cwd=comp,
                           capture_output=True, text=True, errors="replace")
        tail = (r.stdout or "")[-1500:]
        print(tail.strip() or (r.stderr or "")[-800:])
        if r.returncode != 0:
            print("\ncheck failed — fix before rendering", file=sys.stderr)
            return 1

    if args.render:
        print("\nrendering…")
        out = studio / "out"
        out.mkdir(parents=True, exist_ok=True)
        r = subprocess.run(["npx", "--yes", "hyperframes", "render", ".",
                            "-o", str((out / "master.mp4").resolve())],
                           cwd=comp, capture_output=True, text=True, errors="replace")
        print((r.stdout or "")[-800:].strip() or (r.stderr or "")[-800:])
        if r.returncode != 0:
            return 1
        print(f"\n-> {out / 'master.mp4'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

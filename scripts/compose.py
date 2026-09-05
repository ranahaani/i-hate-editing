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
TRACK_PROOF = 20
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


def proof_css(profile):
    accent = (profile.get("brand") or {}).get("accent", "#FFE300")
    return f"""
      .proofwin {{
        position: absolute; top: 0; left: 0;
        width: 100%; height: 100%;
        overflow: hidden; background: #0d0d10;
      }}
      .proofpan {{ position: absolute; top: 0; left: 0; will-change: transform; }}
      .proofpan img {{ display: block; width: 100%; }}
      .hl {{
        position: absolute;
        background: {accent};
        /* multiply keeps the text legible through the highlight, the way a
           real marker works — an opaque box would cover the words. */
        mix-blend-mode: multiply;
        border-radius: 3px;
        transform-origin: 0 50%;
      }}
"""


def build_proof(beats, width, height):
    """Scroll / zoom / highlight over a captured page image.

    The page is one tall still, so every move is authored here rather than
    baked into a recording: it can be re-timed when the cut changes and can
    slow down on the line that matters."""
    clips, anims = [], []
    for i, b in enumerate(beats):
        meta = json.loads(Path(b["meta"]).read_text())
        img = meta["image"]
        dpr = meta.get("dpr", 3)
        img_w, img_h = meta["image_size"]
        fit = width / img_w                      # image is displayed at frame width
        shown_h = img_h * fit                    # displayed height of the whole page

        def px(css_v):
            return css_v * dpr * fit

        def clamp_pan(y):
            """Keep the image covering the frame.

            Centring a target near the top or bottom of the page otherwise
            leaves a black band where there is no image, which reads as a
            broken shot."""
            return max(min(y, 0.0), min(0.0, height - shown_h))

        start, dur = float(b["start"]), float(b["duration"])
        bid = f"proof{i}"
        end = start + dur

        tgt = None
        if b.get("target"):
            tgt = meta["targets"].get(b["target"])
            if tgt is None:
                raise SystemExit(f"error: target {b['target']!r} not in {b['meta']}")

        # Where the pan sits so the point of interest is frame-centred.
        if tgt:
            cx, cy = px(tgt["centre"][0]), px(tgt["centre"][1])
        else:
            cx, cy = width / 2, px(float(b.get("from_y", 0))) + height / 2

        hl = ""
        if tgt and b.get("highlight"):
            hl = (f'<div class="hl" id="{bid}hl" style="left:{px(tgt["x"]) - 6:.0f}px;'
                  f'top:{px(tgt["y"]) - 4:.0f}px;height:{px(tgt["h"]) + 8:.0f}px;'
                  f'width:{px(tgt["w"]) + 12:.0f}px;"></div>')

        clips.append(
            f'      <div id="{bid}" class="clip" data-start="{start:.2f}" '
            f'data-duration="{dur:.2f}" data-track-index="{TRACK_PROOF + i}">\n'
            f'        <div class="inner proofwin">\n'
            f'          <div class="proofpan" id="{bid}pan">'
            f'<img src="{html.escape(Path(img).name)}" alt="">{hl}</div>\n'
            f'        </div>\n'
            f'      </div>')

        # Cutaway: the proof owns the frame, then hands it back.
        anims.append(f'      tl.fromTo("#{bid} .inner", {{ yPercent: -100 }}, '
                     f'{{ yPercent: 0, duration: 0.24, ease: "power3.out" }}, {start:.2f});')
        anims.append(f'      tl.to("#{bid} .inner", {{ yPercent: -100, duration: 0.2, '
                     f'ease: "power3.in" }}, {end - 0.2:.2f});')
        anims.append(f'      tl.set("#{bid} .inner", {{ yPercent: -100 }}, {end:.2f});')

        if b.get("action") == "scroll":
            y0 = clamp_pan(-px(float(b.get("from_y", 0))))
            y1 = clamp_pan(-px(float(b.get("to_y", 0))))
            anims.append(
                f'      tl.fromTo("#{bid}pan", {{ y: {y0:.0f} }}, '
                f'{{ y: {y1:.0f}, duration: {dur:.2f}, ease: "none" }}, {start:.2f});')
        else:
            scale = float(b.get("scale", 2.0))
            hold = max(0.3, dur - 0.9)
            pan_y = clamp_pan(height / 2 - cy)
            anims.append(
                f'      tl.set("#{bid}pan", {{ y: {pan_y:.0f}, '
                f'transformOrigin: "{cx:.0f}px {cy:.0f}px" }}, {start:.2f});')
            anims.append(
                f'      tl.fromTo("#{bid}pan", {{ scale: 1 }}, {{ scale: {scale:.2f}, '
                f'duration: 0.55, ease: "power2.inOut" }}, {start:.2f});')
            anims.append(
                f'      tl.to("#{bid}pan", {{ scale: 1, duration: 0.35, '
                f'ease: "power2.in" }}, {start + 0.55 + hold:.2f});')

        if hl:
            # Sweep left to right, like a marker drawn across the line.
            anims.append(
                f'      tl.fromTo("#{bid}hl", {{ scaleX: 0 }}, {{ scaleX: 1, '
                f'duration: 0.42, ease: "power2.out" }}, '
                f'{start + float(b.get("highlight_at", 0.7)):.2f});')
    return clips, anims


def build_sfx(sounds):
    """<audio> clips, peak-aligned by sfx.py.

    Track indices stay low deliberately: HyperFrames drops or attenuates audio
    on high tracks with no error at all, so a sting placed up with the visual
    layers plays silently in the render."""
    clips = []
    for i, s in enumerate(sounds):
        track = int(s.get("track", 20))
        if track > AUDIO_TRACK_CEILING:
            raise SystemExit(
                f"error: audio track {track} exceeds the ceiling of "
                f"{AUDIO_TRACK_CEILING}; it would render silently")
        clips.append(
            f'      <audio id="sfx{i}" class="clip" '
            f'src="{html.escape(Path(s["file"]).name)}"\n'
            f'             data-start="{float(s["start"]):.2f}" '
            f'data-duration="{float(s["duration"]):.2f}"\n'
            f'             data-track-index="{track}" '
            f'data-volume="{float(s.get("volume", 0.6)):.2f}"></audio>')
    return clips


def build_html(video_name, width, height, duration, chunks, profile, beats=None,
               sounds=None):
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

    proof_clips, proof_anims = build_proof(beats or [], width, height)
    clips += proof_clips
    anims += proof_anims
    clips += build_sfx(sounds or [])

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
{caption_css(profile, width)}{proof_css(profile)}
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
    ap.add_argument("--proof", default=None,
                    help="proof.json: scroll / zoom / highlight beats over captured pages")
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

    beats = []
    proof_path = Path(args.proof) if args.proof else studio / "proof.json"
    if proof_path.is_file():
        beats = json.loads(proof_path.read_text()).get("beats", [])
        for b in beats:
            b["meta"] = str((studio / "assets" / "proof" / f"{b['asset']}.json")
                            if "meta" not in b else b["meta"])

    sounds = []
    sfx_path = studio / "sfx.json"
    if sfx_path.is_file():
        sounds = json.loads(sfx_path.read_text()).get("sounds", [])

    profile = read_profile(studio)
    width, height, duration = probe(video)

    comp = studio / "composition"
    comp.mkdir(parents=True, exist_ok=True)
    (comp / "hyperframes.json").write_text(json.dumps(HYPERFRAMES_JSON, indent=2))
    (comp / "package.json").write_text(json.dumps(PACKAGE_JSON, indent=2))
    shutil.copy2(video, comp / video.name)
    for b in beats:
        img = Path(json.loads(Path(b["meta"]).read_text())["image"])
        if img.is_file():
            shutil.copy2(img, comp / img.name)
    for s_ in sounds:
        f = Path(s_["file"])
        if f.is_file():
            shutil.copy2(f, comp / f.name)

    trailing = [c for c in chunks if c["end"] > duration + 0.05]
    if trailing:
        print(f"  note: {len(trailing)} caption(s) run past the video end; trimming")
        for c in trailing:
            c["end"] = min(c["end"], duration)
            c["duration"] = max(0.1, c["end"] - c["start"])

    (comp / "index.html").write_text(
        build_html(video.name, width, height, duration, chunks, profile, beats, sounds))

    print(f"{len(chunks)} captions · {len(beats)} proof beat(s) · "
          f"{len(sounds)} sound(s) over {duration:.1f}s · {width}x{height}")
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

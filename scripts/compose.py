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
from media import probe  # noqa: E402  (rotation-aware)
from transcribe import read_profile  # noqa: E402

# Visual clips can sit on any track. AUDIO must stay low — HyperFrames drops
# or attenuates audio on high track indices without raising an error, so a
# sting placed up here plays silently in the render.
TRACK_VIDEO = 1
BIG_ZOOM = 1.18          # held zoom on a card headline
TRACK_CARD = 15
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
    "name": "i-hate-editing-composition", "private": True, "version": "1.0.0",
    "scripts": {
        "dev": "npx --yes hyperframes preview",
        "check": "npx --yes hyperframes check",
        "render": "npx --yes hyperframes render",
    },
}


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
        /* Clear of Instagram's own UI, which covers the bottom ~25% with the
           caption and audio name. 16% put text underneath it. */
        bottom: 27%;
        text-align: center;
        font-family: "{font}", sans-serif;
        line-height: 1.12;
        text-shadow: {shadow};
        text-transform: uppercase;
      }}
      /* During a half-split the face occupies the bottom half, so a caption in
         its usual place lands on the speaker's eyes. It moves into the card's
         empty lower region instead (rules/framing.md). */
      .caption.split {{ bottom: 52%; }}
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


def card_css(profile, width):
    accent = (profile.get("brand") or {}).get("accent", "#FFE300")
    font = (profile.get("brand") or {}).get("font", "Archivo Black")
    return f"""
      .card {{
        position: absolute; top: 0; left: 0;
        width: 100%; height: 50%;
        background: #0d0d10;
        display: flex; flex-direction: column;
        align-items: center; justify-content: center;
        padding: 0 {round(width * 0.075)}px;
        font-family: "{font}", sans-serif;
        text-align: center;
      }}
      .card .kicker {{
        font-size: {round(width * 0.032)}px;
        letter-spacing: 0.18em;
        color: {accent};
        text-transform: uppercase;
        margin-bottom: {round(width * 0.028)}px;
      }}
      .card .big {{
        line-height: 1.04;
        color: #fff;
        text-transform: uppercase;
        white-space: nowrap;
      }}
      .card .big em {{ color: {accent}; font-style: normal; }}
      .band {{
        position: absolute; top: 5.5%; left: 5%;
        width: 90%;
        background: {accent};
        color: #0d0d10;
        font-family: "{font}", sans-serif;
        font-size: {round(width * 0.062)}px;
        line-height: 1.06;
        text-align: center;
        text-transform: uppercase;
        padding: {round(width * 0.022)}px {round(width * 0.02)}px;
        box-shadow: 10px 10px 0 rgba(0,0,0,0.35);
      }}
      .card.full {{ height: 100%; justify-content: center; }}
      .card .rows {{
        display: flex; flex-direction: column; gap: {round(width * 0.016)}px;
        width: 100%; margin-top: {round(width * 0.026)}px;
      }}
      .card .row {{
        display: flex; align-items: baseline; gap: {round(width * 0.018)}px;
        background: #f4f6f8; color: #10131a;
        border-radius: {round(width * 0.012)}px;
        padding: {round(width * 0.020)}px {round(width * 0.022)}px;
        text-align: left;
      }}
      .card .row .n {{
        font-size: {round(width * 0.026)}px; color: #6b7686;
        min-width: {round(width * 0.030)}px;
      }}
      .card .row .t {{ font-size: {round(width * 0.046)}px; line-height: 1.1; }}
      .card .row .d {{
        font-size: {round(width * 0.030)}px; color: #5c6472;
        font-weight: 400; margin-left: auto; text-align: right;
      }}
      .card .sub {{
        font-size: {round(width * 0.040)}px;
        line-height: 1.35;
        color: #b9c0cc;
        margin-top: {round(width * 0.030)}px;
        max-width: 86%;
      }}
"""


def build_cards(cards, width, height, face_half_y):
    """Half-screen split: designed card on top, face below.

    The face is repositioned rather than scaled — scaling it while it is also
    being moved into a half produces glitches that only show in motion
    (rules/framing.md)."""
    clips, anims = [], []
    card_index = 0
    prev_card_end = None
    FULL = 'top: "0px", height: "100%", objectPosition: "50% 50%"'
    HALF = (f'top: "50%", height: "50%", '
            f'objectPosition: "50% {face_half_y:.0f}%"')

    for i, c in enumerate(cards):
        start, dur = float(c["start"]), float(c["duration"])
        end = start + dur
        cid = f"card{i}"

        # A band sits over the top of a full frame and leaves the face alone —
        # the hook headline lives in the empty space above the head, and the
        # face must stay full-frame there (rules/hooks.md).
        if c.get("style") == "band":
            txt = html.escape(c["big"]).replace("*", "")
            clips.append(
                f'      <div id="{cid}" class="clip" data-start="{start:.2f}" '
                f'data-duration="{dur:.2f}" data-track-index="{TRACK_CARD + i}">\n'
                f'        <div class="inner band">{txt}</div>\n'
                f'      </div>')
            anims.append(
                f'      tl.from("#{cid} .inner", {{ yPercent: -160, opacity: 0, '
                f'duration: 0.32, ease: "back.out(1.7)" }}, {start:.2f});')
            anims.append(
                f'      tl.to("#{cid} .inner", {{ yPercent: -160, opacity: 0, '
                f'duration: 0.22, ease: "power3.in" }}, {end - 0.22:.2f});')
            anims.append(
                f'      tl.set("#{cid} .inner", {{ opacity: 0 }}, {end:.2f});')
            continue
        big = c["big"]
        if "*" in big:                      # *word* marks the accent word
            parts = big.split("*")
            big = "".join(f"<em>{p}</em>" if n % 2 else p for n, p in enumerate(parts))
        # Size the headline so the whole line fits inside the padding. A fixed
        # size clips long phrases at both edges, which rules/framing.md forbids
        # and which is only visible after rendering.
        plain = big.replace("<em>", "").replace("</em>", "")
        avail = width * (1 - 2 * 0.075) * 0.97
        # Heavy uppercase sans averages ~0.62 em per glyph, and the headline is
        # zoomed to BIG_ZOOM during its hold — sizing to fit at rest still
        # clips once the zoom lands.
        fitted = avail / max(1, len(plain) * 0.62 * BIG_ZOOM)
        size = int(min(width * 0.105, fitted))

        inner = ""
        if c.get("kicker"):
            inner += f'<div class="kicker">{html.escape(c["kicker"])}</div>'
        inner += (f'<div class="big" id="{cid}big" '
                  f'style="font-size:{size}px">{big}</div>')
        if c.get("items"):
            rows = "".join(
                f'<div class="row" id="{cid}r{n}">'
                f'<span class="n">{n + 1}</span>'
                f'<span class="t">{html.escape(it.get("title", ""))}</span>'
                + (f'<span class="d">{html.escape(it["note"])}</span>'
                   if it.get("note") else "")
                + "</div>"
                for n, it in enumerate(c["items"]))
            inner += f'<div class="rows">{rows}</div>'
        if c.get("sub"):
            inner += f'<div class="sub">{html.escape(c["sub"])}</div>'

        full = " full" if c.get("full") else ""
        clips.append(
            f'      <div id="{cid}" class="clip" data-start="{start:.2f}" '
            f'data-duration="{dur:.2f}" data-track-index="{TRACK_CARD + i}">\n'
            f'        <div class="inner card{full}">{inner}</div>\n'
            f'      </div>')

        if not c.get("full"):
            anims.append(f'      tl.set("#face", {{ {HALF} }}, {start:.2f});')
            anims.append(f'      tl.set("#face", {{ {FULL} }}, {end:.2f});')

        # Choose the arrival from what the element is, not from variety alone
        # (rules/motion.md). Variety only breaks ties between equals.
        prev_end = prev_card_end
        follows_card = prev_end is not None and (start - prev_end) < 1.0

        if c.get("full"):
            # A payoff owns the frame. No animation is the strongest arrival
            # when the moment earns it; the impact carries the transition.
            enter, leave, dur_in = "{ opacity: 0 }", "{ opacity: 0 }", 0.04
        elif follows_card:
            # One card pushing the last out reads as a sequence.
            side = 110 if (card_index % 2 == 0) else -110
            enter, leave, dur_in = (f"{{ xPercent: {side} }}",
                                    f"{{ xPercent: {-side} }}", 0.28)
        else:
            # Coming in over the speaker: from outside the frame, so the face
            # is handed off rather than replaced.
            enter, leave, dur_in = ("{ yPercent: -110 }", "{ yPercent: -110 }", 0.30)
        card_index += 1
        prev_card_end = end
        anims.append(
            f'      tl.from("#{cid} .inner", {{ ...{enter}, duration: {dur_in}, '
            f'ease: "power3.out" }}, {start:.2f});')
        anims.append(
            f'      tl.to("#{cid} .inner", {{ ...{leave}, duration: 0.22, '
            f'ease: "power3.in" }}, {end - 0.22:.2f});')
        anims.append(f'      tl.set("#{cid} .inner", {{ opacity: 0 }}, {end:.2f});')

        # List rows arrive one at a time — the eye cannot track two new things
        # at once (rules/motion.md).
        for n in range(len(c.get("items") or [])):
            anims.append(
                f'      tl.from("#{cid}r{n}", {{ opacity: 0, y: 26, '
                f'duration: 0.22, ease: "power2.out" }}, '
                f'{start + 0.34 + n * 0.16:.2f});')
        # A held zoom on the key word, err large (rules/motion.md).
        hold_at = start + 0.45
        anims.append(
            f'      tl.to("#{cid}big", {{ scale: 1.18, duration: 0.28, '
            f'ease: "power2.out" }}, {hold_at:.2f});')
        anims.append(
            f'      tl.to("#{cid}big", {{ scale: 1.0, duration: 0.30, '
            f'ease: "power2.inOut" }}, {min(hold_at + 1.5, end - 0.3):.2f});')
    return clips, anims


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

        def clamp_x(x):
            """Keep the image covering the frame horizontally."""
            return max(min(x, 0.0), min(0.0, width - width))  # image is frame-wide

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
            # Translate is computed directly from the scale with the origin
            # at 0,0 rather than scaling about the target and translating
            # separately — the two-step version leaves the target off-frame
            # because the origin and the translate compose in a way that is
            # easy to get subtly wrong. This form is exact:
            #   x = frame_centre - target_centre * scale
            requested = float(b.get("scale", 2.0))
            scale = requested
            if tgt:
                tw = max(1.0, px(tgt["w"]))
                fit_scale = (width * 0.86) / tw
                scale = max(1.05, min(requested, fit_scale))
                if scale < requested - 0.01:
                    print(f"  beat {i}: scale {requested:.2f} -> {scale:.2f} so "
                          f"{b.get('target')!r} stays inside the frame")
            hold = max(0.3, dur - 0.9)

            def place(sc):
                x = width / 2 - cx * sc
                y = height / 2 - cy * sc
                # Keep the image covering the frame at this scale.
                x = max(min(x, 0.0), min(0.0, width - width * sc))
                y = max(min(y, 0.0), min(0.0, height - shown_h * sc))
                return x, y

            x0, y0 = place(1.0)
            x1, y1 = place(scale)
            anims.append(
                f'      tl.set("#{bid}pan", {{ transformOrigin: "0px 0px" }}, {start:.2f});')
            anims.append(
                f'      tl.fromTo("#{bid}pan", '
                f'{{ scale: 1, x: {x0:.0f}, y: {y0:.0f} }}, '
                f'{{ scale: {scale:.3f}, x: {x1:.0f}, y: {y1:.0f}, '
                f'duration: 0.55, ease: "power2.inOut" }}, {start:.2f});')
            anims.append(
                f'      tl.to("#{bid}pan", {{ scale: 1, x: {x0:.0f}, y: {y0:.0f}, '
                f'duration: 0.35, ease: "power2.in" }}, {start + 0.55 + hold:.2f});')

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


def split_windows(cards):
    """Times when a half-screen card is on screen."""
    return [(float(c["start"]), float(c["start"]) + float(c["duration"]))
            for c in (cards or [])
            if c.get("style") != "band" and not c.get("full")]


def full_windows(cards):
    """Times a full-screen card owns the frame.

    Captions are suppressed here rather than repositioned: the card is the
    message, and two text blocks competing for one frame is worse than either
    alone (rules/framing.md)."""
    return [(float(c["start"]), float(c["start"]) + float(c["duration"]))
            for c in (cards or []) if c.get("full")]


def build_html(video_name, width, height, duration, chunks, profile, beats=None,
               sounds=None, cards=None, face_half_y=30.0):
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

    card_clips, card_anims = build_cards(cards or [], width, height, face_half_y)
    clips += card_clips
    anims += card_anims

    proof_clips, proof_anims = build_proof(beats or [], width, height)
    clips += proof_clips
    anims += proof_anims
    clips += build_sfx(sounds or [])

    splits = split_windows(cards)
    fulls = full_windows(cards)
    for i, c in enumerate(chunks):
        cid = f"cap{i}"
        mid = (c["start"] + c["end"]) / 2
        if any(a - 0.15 <= mid < b + 0.15 for a, b in fulls):
            continue                      # the card speaks for this beat
        in_split = any(a <= mid < b for a, b in splits)
        cls = "caption split" if in_split else "caption"
        words = "".join(
            f'<span class="w{" em" if w["emphasis"] else ""}">{esc(w["text"])}</span>'
            for w in c["words"])
        clips.append(
            f'      <div id="{cid}" class="clip" data-start="{c["start"]:.2f}" '
            f'data-duration="{c["duration"]:.2f}" data-track-index="{TRACK_CAPTION}">\n'
            f'        <div class="inner {cls}">{words}</div>\n'
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
{caption_css(profile, width)}{proof_css(profile)}{card_css(profile, width)}
    </style>
  </head>
  <body>
    <div id="root" data-composition-id="main"
         data-start="0" data-duration="{duration:.2f}"
         data-width="{width}" data-height="{height}">
{chr(10).join(clips)}
    </div>

    <script>
      // Fit every card headline to its box, measured in the browser rather
      // than estimated from character counts — glyph widths depend on the font
      // that actually resolves, and an estimate clips the text at both edges.
      // The zoom factor is included, since the headline is scaled during hold.
      (function fitHeadlines() {{
        const ZOOM = {BIG_ZOOM};
        document.querySelectorAll(".card .big").forEach((el) => {{
          // clientWidth includes the card's horizontal padding, so measuring
          // it directly allows more width than actually exists and the
          // headline still clips.
          const par = el.parentElement;
          const cs = getComputedStyle(par);
          const box = (par.clientWidth
                       - parseFloat(cs.paddingLeft)
                       - parseFloat(cs.paddingRight)) * 0.98;
          let size = parseFloat(getComputedStyle(el).fontSize);
          let guard = 0;
          while (el.scrollWidth * ZOOM > box && size > 24 && guard < 80) {{
            size -= 2;
            el.style.fontSize = size + "px";
            guard++;
          }}
        }});
      }})();

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

    cards = []
    cards_path = studio / "cards.json"
    if cards_path.is_file():
        cards = json.loads(cards_path.read_text()).get("cards", [])

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
        build_html(video.name, width, height, duration, chunks, profile, beats,
                   sounds, cards, float(profile.get("face_half_y", 30))))

    print(f"{len(chunks)} captions · {len(cards)} card(s) · {len(beats)} proof · "
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

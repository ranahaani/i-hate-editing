#!/usr/bin/env python3
"""Shatter text: one word that breaks into shards on the beat of an impact.

Written for this project (see NOTICE.md). Output follows the conventions of
`scripts/compose.py`: a CSS block, a list of `<div class="clip">` elements and
a list of GSAP statements appended to the composition's `tl`. Composing the
word inside the HyperFrames composition keeps the caption layer on top
(hard rule 20).

Geometry is generated here, not in the browser, so it is deterministic and
testable. The browser only measures the font and runs the tweens.

    python3 shatter.py --word NEVER --t-hit 1.9 \
        --zone 90,380,900,230 --face 300,640,480,560

The zone is the box `safe_zone.py` picks (x, y, w, h in frame pixels). The face
box is optional but strongly advised: when given, every shard's flight path is
kept clear of it, so the debris never crosses the speaker.
"""

import argparse
import json
import math
import random
import sys

FRAME_W, FRAME_H = 1080, 1920
TRACK_HOOK = 55            # above cards (15) and proof (45), under captions (60)
SHATTER_SECONDS = 0.40     # rules/hooks.md: fragments fly for about 0.4s
FADE_SECONDS = 0.14
STAGGER_SECONDS = 0.05     # centre shards leave first; reads as a wave
DEFAULT_LEAD = 1.1         # on screen at least 1.5s in total (rules/motion.md)
PATH_STEPS = 24


def parse_box(text):
    x, y, w, h = (float(p) for p in text.split(","))
    return {"x": x, "y": y, "w": w, "h": h}


def rects_intersect(a, b):
    return not (a["x"] + a["w"] <= b["x"] or b["x"] + b["w"] <= a["x"]
                or a["y"] + a["h"] <= b["y"] or b["y"] + b["h"] <= a["y"])


def inflate(box, m):
    return {"x": box["x"] - m, "y": box["y"] - m,
            "w": box["w"] + 2 * m, "h": box["h"] + 2 * m}


def translate(box, dx, dy):
    return {"x": box["x"] + dx, "y": box["y"] + dy, "w": box["w"], "h": box["h"]}


def shard_box(zone, poly, origin):
    """Bounding square of a shard in frame pixels, grown to the circle it
    sweeps while rotating about its centroid."""
    cx = zone["x"] + origin[0] / 100 * zone["w"]
    cy = zone["y"] + origin[1] / 100 * zone["h"]
    r = max(math.hypot((px - origin[0]) / 100 * zone["w"],
                       (py - origin[1]) / 100 * zone["h"]) for px, py in poly)
    return {"x": cx - r, "y": cy - r, "w": 2 * r, "h": 2 * r}


def tight_box(zone, poly):
    """Unrotated bounding box of a shard in frame pixels."""
    xs = [zone["x"] + px / 100 * zone["w"] for px, _ in poly]
    ys = [zone["y"] + py / 100 * zone["h"] for _, py in poly]
    return {"x": min(xs), "y": min(ys), "w": max(xs) - min(xs), "h": max(ys) - min(ys)}


def path_clear(box, dx, dy, face):
    """True when `box`, swept along (dx, dy), never touches the face."""
    for i in range(PATH_STEPS + 1):
        t = i / PATH_STEPS
        if rects_intersect(translate(box, dx * t, dy * t), face):
            return False
    return True


def clear_scale(box, dx, dy, face):
    """Largest s in [0, 1] such that travelling s*(dx, dy) stays clear."""
    if face is None or path_clear(box, dx, dy, face):
        return 1.0
    lo, hi = 0.0, 1.0
    for _ in range(12):
        mid = (lo + hi) / 2
        if path_clear(box, dx * mid, dy * mid, face):
            lo = mid
        else:
            hi = mid
    return lo


def validate(zone, face, frame_w=FRAME_W, frame_h=FRAME_H):
    if zone["w"] <= 0 or zone["h"] <= 0:
        raise ValueError("zone has no area")
    if (zone["x"] < 0 or zone["y"] < 0
            or zone["x"] + zone["w"] > frame_w or zone["y"] + zone["h"] > frame_h):
        raise ValueError("zone leaves the frame")
    if face is not None and rects_intersect(zone, face):
        raise ValueError("zone overlaps the face: shrink or move the text, "
                         "never overlap (rules/hooks.md)")


def timing(t_hit, lead=DEFAULT_LEAD):
    """(t_in, t_end): the word is whole from t_in until t_hit, in pieces until
    t_end. t_in never goes negative, so a hit at 0.5s still lands."""
    t_in = max(0.0, t_hit - lead)
    return t_in, t_hit + SHATTER_SECONDS + 0.05


def build_shards(zone, face, cols=6, rows=2, seed=7, spread=320.0):
    """Triangular shards over a jittered grid, with a flight for each.

    Polygons are percentages of the word box. Flights are pixels: outward from
    the box centre, mirrored away from the face when they would head toward
    it, then shortened until the shard's own sweep is clear. The word box is
    the zone, so a shard's pixels are known exactly."""
    rng = random.Random(seed)
    pts = []
    for r in range(rows + 1):
        row = []
        for c in range(cols + 1):
            u, v = c / cols, r / rows
            if 0 < c < cols:
                u += rng.uniform(-0.35, 0.35) / cols
            if 0 < r < rows:
                v += rng.uniform(-0.35, 0.35) / rows
            row.append((u, v))
        pts.append(row)

    zone_c = (zone["x"] + zone["w"] / 2, zone["y"] + zone["h"] / 2)
    away = None
    if face is not None:
        fx, fy = face["x"] + face["w"] / 2 - zone_c[0], face["y"] + face["h"] / 2 - zone_c[1]
        norm = math.hypot(fx, fy) or 1.0
        away = (fx / norm, fy / norm)    # unit vector pointing at the face

    shards = []
    for r in range(rows):
        for c in range(cols):
            a, b = pts[r][c], pts[r][c + 1]
            d, e = pts[r + 1][c], pts[r + 1][c + 1]
            tris = ([a, b, e], [a, e, d]) if rng.random() < 0.5 else ([a, b, d], [b, e, d])
            for tri in tris:
                cu = sum(p[0] for p in tri) / 3
                cv = sum(p[1] for p in tri) / 3
                vx, vy = (cu - 0.5) * zone["w"], (cv - 0.5) * zone["h"]
                norm = math.hypot(vx, vy)
                if norm < 1e-6:
                    vx, vy, norm = 0.0, -1.0, 1.0
                ang = math.atan2(vy, vx) + rng.uniform(-0.45, 0.45)
                ux, uy = math.cos(ang), math.sin(ang)
                if away is not None:
                    dot = ux * away[0] + uy * away[1]
                    if dot > 0:          # heading at the face: mirror it away
                        ux, uy = ux - 2 * dot * away[0], uy - 2 * dot * away[1]
                dist = spread * rng.uniform(0.6, 1.4)
                dx, dy = ux * dist, uy * dist
                poly = [(round(p[0] * 100, 2), round(p[1] * 100, 2)) for p in tri]
                origin = (round(cu * 100, 2), round(cv * 100, 2))
                rot = round(rng.uniform(-200, 200), 1)
                box = shard_box(zone, poly, origin)
                if face is not None and rects_intersect(box, face):
                    # Spinning here would swing a corner onto the face, so
                    # this shard flies without rotation, on its tight box.
                    box, rot = tight_box(zone, poly), 0.0
                s = clear_scale(box, dx, dy, face)
                dx, dy = dx * s, dy * s
                shards.append({
                    "poly": poly, "origin": origin,
                    "dx": round(dx, 1), "dy": round(dy, 1),
                    "rot": rot, "box": box,
                    "scale": round(rng.uniform(0.35, 0.8), 2),
                    "delay": round(math.hypot(cu - 0.5, cv - 0.5) * 2 * STAGGER_SECONDS, 3),
                })
    return shards


def estimate_font_px(word, zone, pad):
    return int(min(zone["h"] - 2 * pad, (zone["w"] - 2 * pad) / (0.78 * max(1, len(word)))))


def build(word, t_hit, zone, face=None, uid="hookshatter", font="Archivo Black",
          color="#76B900", lead=DEFAULT_LEAD, seed=7, scrim=0.62, track=TRACK_HOOK,
          frame=(FRAME_W, FRAME_H)):
    """Return {"css", "clips", "anims"} ready to splice into compose.build_html."""
    validate(zone, face, *frame)
    t_in, t_end = timing(t_hit, lead)
    pad = max(18, round(zone["h"] * 0.12))
    shards = build_shards(zone, face, seed=seed)
    fs = estimate_font_px(word, zone, pad)
    text = word.upper()
    outline = ("0 0 9px #000, 3px 3px 0 #000, -3px -3px 0 #000, "
               "3px -3px 0 #000, -3px 3px 0 #000, 5px 6px 0 rgba(0,0,0,0.55)")

    css = f"""
      #{uid} {{
        position: absolute; left: {zone['x']:.0f}px; top: {zone['y']:.0f}px;
        width: {zone['w']:.0f}px; height: {zone['h']:.0f}px;
        display: flex; align-items: center; justify-content: center;
      }}
      #{uid} .hs-word {{
        position: relative; width: 100%; height: 100%; font-size: {fs}px;
        font-family: "{font}", sans-serif; line-height: 1; white-space: nowrap;
        text-transform: uppercase; color: {color}; text-shadow: {outline};
      }}
      /* hyperframes check samples the pixels behind the text; a light wall
         under yellow fails WCAG. The scrim buys the contrast and leaves with
         the shards. */
      #{uid} .hs-scrim {{
        position: absolute; inset: 0; border-radius: {round(zone['h'] * 0.18)}px;
        background: rgba(0, 0, 0, {scrim}); box-shadow: 0 0 36px 18px rgba(0, 0, 0, {scrim * 0.6:.2f});
      }}
      #{uid} .hs-sizer {{
        position: absolute; left: 0; top: 0; visibility: hidden; display: inline-block;
      }}
      #{uid} .hs-shard {{
        position: absolute; inset: 0;
        display: flex; align-items: center; justify-content: center;
      }}
"""
    shard_html, anims = [], []
    for i, s in enumerate(shards):
        poly = ", ".join(f"{x}% {y}%" for x, y in s["poly"])
        sid = f"{uid}s{i}"
        shard_html.append(
            f'<div id="{sid}" class="hs-shard" data-layout-allow-overlap '
            f'data-layout-allow-overflow style="clip-path: polygon({poly}); '
            f'transform-origin: {s["origin"][0]}% {s["origin"][1]}%;">{text}</div>')
        t0 = t_hit + s["delay"]
        move = SHATTER_SECONDS - STAGGER_SECONDS
        anims.append(
            f'      tl.to("#{sid}", {{ x: {s["dx"]}, y: {s["dy"]}, rotation: {s["rot"]}, '
            f'scale: {s["scale"]}, duration: {move:.2f}, ease: "power3.out" }}, {t0:.3f});')
        anims.append(
            f'      tl.to("#{sid}", {{ opacity: 0, duration: {FADE_SECONDS}, '
            f'ease: "power1.in" }}, {t0 + move - FADE_SECONDS:.3f});')

    fit = f"""      // Fit the word to its zone after the webfont resolves, as fitHeadlines does.
      (function () {{
        const fit = () => {{
          const word = document.querySelector("#{uid} .hs-word");
          const sizer = word.querySelector(".hs-sizer");
          let size = parseFloat(getComputedStyle(word).fontSize), guard = 0;
          while (sizer.offsetWidth > {zone['w'] - 2 * pad:.0f} && size > 24 && guard < 80) {{
            size -= 2; word.style.fontSize = size + "px"; guard++;
          }}
        }};
        fit();
        if (document.fonts && document.fonts.ready) document.fonts.ready.then(fit);
      }})();"""
    anims.append(
        f'      tl.to("#{uid} .hs-scrim", {{ opacity: 0, duration: {FADE_SECONDS}, '
        f'ease: "power1.in" }}, {t_hit + 0.08:.3f});')
    entrance = (f'      tl.from("#{uid} .hs-word", {{ scale: 0.6, opacity: 0, duration: 0.22, '
                f'ease: "back.out(2.2)", transformOrigin: "50% 50%" }}, {t_in:.3f});')
    clip = (f'      <div id="{uid}" class="clip" data-start="{t_in:.3f}" '
            f'data-duration="{t_end - t_in:.3f}" data-track-index="{track}">\n'
            f'        <div class="hs-scrim"></div>\n'
            f'        <div class="hs-word"><span class="hs-sizer">{text}</span>'
            f'{"".join(shard_html)}</div>\n'
            f'      </div>')
    return {"css": css, "clips": [clip], "anims": [fit, entrance] + anims,
            "t_in": t_in, "t_end": t_end, "shards": len(shards)}


def splice(html, fragment):
    """Insert a fragment into the output of compose.build_html."""
    html = html.replace("    </style>", fragment["css"] + "    </style>", 1)
    html = html.replace("    </div>\n\n    <script>",
                        "\n".join(fragment["clips"]) + "\n    </div>\n\n    <script>", 1)
    return html.replace('      window.__timelines["main"] = tl;',
                        "\n".join(fragment["anims"]) + '\n      window.__timelines["main"] = tl;', 1)


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--word", required=True)
    ap.add_argument("--t-hit", type=float, required=True, help="impact time, output timeline")
    ap.add_argument("--zone", required=True, help="x,y,w,h in frame pixels")
    ap.add_argument("--face", help="x,y,w,h face box, keeps debris clear of it")
    ap.add_argument("--color", default="#76B900")
    ap.add_argument("--lead", type=float, default=DEFAULT_LEAD)
    args = ap.parse_args()
    try:
        out = build(args.word, args.t_hit, parse_box(args.zone),
                    parse_box(args.face) if args.face else None,
                    color=args.color, lead=args.lead)
    except ValueError as err:
        print(f"error: {err}", file=sys.stderr)
        return 1
    print(json.dumps(out, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())

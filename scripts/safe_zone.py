#!/usr/bin/env python3
"""Pick where hook text goes so it never overlaps the face (rules/hooks.md,
"Place hook text where the face is not").

    safe_zone.py VIDEO --at 3.2 [--zoom 1.55 --zoom-y 0.30] [--debug-png out.png]

Prints JSON: the measured face box, every candidate zone ranked widest-gap
first, the chosen zone, and (when nothing clears the face) a shrink factor.
All geometry is in the 1080x1920 output frame.

Run it with the venv that has OpenCV (system python has no cv2):

    ~/.cache/i-hate-editing/venv/bin/python scripts/safe_zone.py ...

Setup, once:  uv venv --python 3.12 ~/.cache/i-hate-editing/venv
              uv pip install --python ~/.cache/i-hate-editing/venv/bin/python \\
                  "opencv-python-headless<5" numpy
(opencv 5.x dropped the Haar cascade fallback; the same recipe family is in
~/.claude/skills/virtual-bg/SKILL.md:127-128.)

Platform safe-area numbers, all reused from the studio, none invented:
  * Top ~15% platform header, bottom ~25% caption/controls, right ~15% buttons:
    rules/framing.md:59-61.
  * Burned-in text stays above ~27% from the bottom: rules/framing.md:64.
  * 4:5 feed crop of a 9:16 frame: rules/framing.md:53 ("the feed crops to
    4:5"). 1080x1350 centred in 1080x1920 is arithmetic, not a measurement.
  * Side margin 5%: scripts/compose.py:77 and :198 (`left: 5%; width: 90%`).
  * Zoom/crop transform copied from scripts/render.py:70-75 and the scale+pad
    on render.py:76-77; zoom_y default 0.42 from render.py:55.

Working defaults, UNVERIFIED (no studio source), kept as constants below:
  HEAD_EXPAND_*, FACE_PAD, MIN_TEXT_W, MIN_TEXT_H, MIN_SHRINK, MIN_CONFIDENCE.
HEAD_EXPAND_* were measured by eye on one subject (take_02.mp4 of
2026-09-02-prompt-master): the YuNet box stops at the brow and the chin, so the
hair and beard sit outside it. Check the debug PNG on a new speaker.
"""

import argparse
import json
import sys
import urllib.request
from pathlib import Path

W, H = 1080, 1920

# Studio numbers (see module docstring for file:line).
HEADER_FRAC = 0.15
BOTTOM_TEXT_FRAC = 0.27
RIGHT_FRAC = 0.15
SIDE_MARGIN_FRAC = 0.05
FEED_ASPECT = (4, 5)
DEFAULT_ZOOM_Y = 0.42

# Working defaults, unverified.
HEAD_EXPAND_TOP = 0.40     # of face-box height: hair above the detected brow
HEAD_EXPAND_BOTTOM = 0.15  # of face-box height: beard/chin below the box
HEAD_EXPAND_SIDE = 0.12    # of face-box width, each side: ears and hair
FACE_PAD = 40              # px of clear air between head and any text
MIN_TEXT_W = 360           # smallest text block a zone must hold, px
MIN_TEXT_H = 140
MIN_SHRINK = 0.5           # below this, shrinking would not read: report none
MIN_CONFIDENCE = 0.7

YUNET_URL = ("https://github.com/opencv/opencv_zoo/raw/main/models/"
             "face_detection_yunet/face_detection_yunet_2023mar.onnx")
YUNET_PATH = Path.home() / ".cache" / "i-hate-editing" / "yunet.onnx"


# ---------------------------------------------------------------- geometry

def safe_rect():
    """Interface-safe area inside the 4:5 feed crop: (x0, y0, x1, y1)."""
    feed_h = W * FEED_ASPECT[1] / FEED_ASPECT[0]
    feed_top = (H - feed_h) / 2
    feed_bottom = feed_top + feed_h
    x0 = W * SIDE_MARGIN_FRAC
    x1 = W * (1 - RIGHT_FRAC)
    y0 = max(H * HEADER_FRAC, feed_top)
    y1 = min(H * (1 - BOTTOM_TEXT_FRAC), feed_bottom)
    return (round(x0), round(y0), round(x1), round(y1))


def expand_head(face):
    """Grow the detector box to cover hair and beard. face = (x, y, w, h)."""
    x, y, w, h = face
    return (x - w * HEAD_EXPAND_SIDE, y - h * HEAD_EXPAND_TOP,
            w * (1 + 2 * HEAD_EXPAND_SIDE),
            h * (1 + HEAD_EXPAND_TOP + HEAD_EXPAND_BOTTOM))


def transform_box(box, src_w, src_h, zoom=1.0, zoom_y=DEFAULT_ZOOM_Y):
    """Map a source-frame box into the 1080x1920 output exactly as render.py
    does: crop in by `zoom` (offset biased by zoom_y), scale to fit, pad."""
    x, y, w, h = box
    cw, ch = src_w / zoom, src_h / zoom
    cx = (src_w - cw) / 2
    cy = (src_h - ch) * zoom_y
    s = min(W / cw, H / ch)
    ox, oy = (W - cw * s) / 2, (H - ch * s) / 2
    return ((x - cx) * s + ox, (y - cy) * s + oy, w * s, h * s)


def clip_box(box):
    x, y, w, h = box
    x0, y0 = max(0, x), max(0, y)
    x1, y1 = min(W, x + w), min(H, y + h)
    return (x0, y0, max(0, x1 - x0), max(0, y1 - y0))


def rank_zones(head, safe=None, pad=FACE_PAD, need_w=MIN_TEXT_W,
               need_h=MIN_TEXT_H):
    """Candidate zones around `head` (x, y, w, h), clipped to `safe`.

    A zone never touches the head: it starts `pad` px clear of it. `gap` is
    the free room between the head edge and the safe-area edge in that
    direction; zones are ranked widest gap first. Zones too small for a
    need_w x need_h text block are listed with fits=False and never chosen.
    Returns (ranked_zones, chosen_or_None, shrink_or_None)."""
    sx0, sy0, sx1, sy1 = safe or safe_rect()
    hx, hy, hw, hh = head
    hx1, hy1 = hx + hw, hy + hh

    raw = {
        "below": (sx0, hy1 + pad, sx1, sy1),
        "above": (sx0, sy0, sx1, hy - pad),
        "left": (sx0, sy0, hx - pad, sy1),
        "right": (hx1 + pad, sy0, sx1, sy1),
    }
    gaps = {"below": sy1 - hy1, "above": hy - sy0,
            "left": hx - sx0, "right": sx1 - hx1}

    zones = []
    for name, (x0, y0, x1, y1) in raw.items():
        x0, y0 = max(x0, sx0), max(y0, sy0)
        x1, y1 = min(x1, sx1), min(y1, sy1)
        w, h = max(0, x1 - x0), max(0, y1 - y0)
        if w <= 0 or h <= 0:
            continue
        zones.append({
            "zone": name, "x": round(x0), "y": round(y0),
            "w": round(w), "h": round(h),
            "gap": round(gaps[name]),
            "fits": w >= need_w and h >= need_h,
            "fit_ratio": round(min(w / need_w, h / need_h), 3),
        })
    zones.sort(key=lambda z: z["gap"], reverse=True)

    chosen = next((z for z in zones if z["fits"]), None)
    shrink = None
    if chosen is None and zones:
        best = max(z["fit_ratio"] for z in zones)
        shrink = best if best >= MIN_SHRINK else None
    return zones, chosen, shrink


# --------------------------------------------------------------- detection

def _yunet_model():
    if YUNET_PATH.exists():
        return YUNET_PATH
    YUNET_PATH.parent.mkdir(parents=True, exist_ok=True)
    try:
        urllib.request.urlretrieve(YUNET_URL, YUNET_PATH)
        return YUNET_PATH
    except OSError:
        YUNET_PATH.unlink(missing_ok=True)
        return None


def detect_faces(frame):
    """Return (detector_name, [(x, y, w, h, score), ...]) on the source frame.
    YuNet first, Haar fallback when the model cannot be fetched. Measured on
    3 clips x 40 frames: both found the face in 120/120; YuNet's box is
    tighter and scored, and it raised fewer extra detections than Haar
    (2 vs 4 frames with more than one hit, at confidence 0.7). Its one
    false positive seen (a hand, score 0.62) is below MIN_CONFIDENCE."""
    import cv2
    model = _yunet_model()
    if model is not None:
        det = cv2.FaceDetectorYN.create(str(model), "", (frame.shape[1],
                                        frame.shape[0]), MIN_CONFIDENCE)
        _, rows = det.detect(frame)
        faces = [] if rows is None else [
            (float(r[0]), float(r[1]), float(r[2]), float(r[3]), float(r[-1]))
            for r in rows]
        return "yunet", faces
    haar = cv2.CascadeClassifier(
        cv2.data.haarcascades + "haarcascade_frontalface_default.xml")
    rects = haar.detectMultiScale(cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY),
                                  1.1, 5, minSize=(120, 120))
    return "haar", [(float(x), float(y), float(w), float(h), 1.0)
                    for x, y, w, h in rects]


def read_frame(video, at):
    import cv2
    cap = cv2.VideoCapture(str(video))
    if not cap.isOpened():
        sys.exit(f"cannot open {video}")
    cap.set(cv2.CAP_PROP_POS_MSEC, at * 1000)
    ok, frame = cap.read()
    cap.release()
    if not ok:
        sys.exit(f"cannot read a frame at {at}s from {video}")
    return frame


def render_view(frame, zoom, zoom_y):
    """The frame as the render pipeline would present it (crop, fit, pad)."""
    import cv2
    import numpy as np
    sh, sw = frame.shape[:2]
    cw, ch = sw / zoom, sh / zoom
    cx, cy = (sw - cw) / 2, (sh - ch) * zoom_y
    crop = frame[int(round(cy)):int(round(cy + ch)),
                 int(round(cx)):int(round(cx + cw))]
    s = min(W / cw, H / ch)
    nw, nh = int(round(cw * s)), int(round(ch * s))
    crop = cv2.resize(crop, (nw, nh), interpolation=cv2.INTER_AREA)
    canvas = np.zeros((H, W, 3), dtype=np.uint8)
    ox, oy = (W - nw) // 2, (H - nh) // 2
    canvas[oy:oy + nh, ox:ox + nw] = crop
    return canvas


def draw_debug(path, frame, zoom, zoom_y, face, head, safe, zones, chosen):
    import cv2
    img = render_view(frame, zoom, zoom_y)

    def rect(box, color, thick=3):
        x, y, w, h = (int(round(v)) for v in box)
        cv2.rectangle(img, (x, y), (x + w, y + h), color, thick)

    sx0, sy0, sx1, sy1 = safe
    rect((sx0, sy0, sx1 - sx0, sy1 - sy0), (0, 255, 255), 2)
    feed_h = int(W * FEED_ASPECT[1] / FEED_ASPECT[0])
    top = (H - feed_h) // 2
    cv2.line(img, (0, top), (W, top), (255, 0, 255), 2)
    cv2.line(img, (0, top + feed_h), (W, top + feed_h), (255, 0, 255), 2)
    for z in zones:
        color = (0, 200, 0) if z["fits"] else (128, 128, 128)
        rect((z["x"], z["y"], z["w"], z["h"]), color,
             8 if chosen and z is chosen else 2)
        cv2.putText(img, z["zone"], (z["x"] + 10, z["y"] + 40),
                    cv2.FONT_HERSHEY_SIMPLEX, 1.1, color, 3)
    rect(head, (0, 165, 255), 3)
    rect(face, (0, 0, 255), 4)
    cv2.imwrite(str(path), img)


# --------------------------------------------------------------------- cli

def analyse(video, at, zoom=1.0, zoom_y=DEFAULT_ZOOM_Y, debug_png=None,
            need_w=MIN_TEXT_W, need_h=MIN_TEXT_H):
    frame = read_frame(video, at)
    sh, sw = frame.shape[:2]
    detector, faces = detect_faces(frame)
    result = {"video": str(video), "at": at, "zoom": zoom, "zoom_y": zoom_y,
              "frame": [W, H], "detector": detector, "faces_found": len(faces)}
    if not faces:
        result.update(face=None, chosen=None, zones=[],
                      error=f"no face found at {at}s; position not guessed")
        return result, 2

    x, y, w, h, score = max(faces, key=lambda f: f[2] * f[3])
    face = clip_box(transform_box((x, y, w, h), sw, sh, zoom, zoom_y))
    head = clip_box(expand_head(face))
    safe = safe_rect()
    zones, chosen, shrink = rank_zones(head, safe, need_w=need_w,
                                       need_h=need_h)
    shrink_zone = (max(zones, key=lambda z: z["fit_ratio"])["zone"]
                   if shrink else None)
    result.update(
        face={"x": round(face[0]), "y": round(face[1]),
              "w": round(face[2]), "h": round(face[3]),
              "score": round(score, 3)},
        head={"x": round(head[0]), "y": round(head[1]),
              "w": round(head[2]), "h": round(head[3])},
        safe_area=dict(zip(("x0", "y0", "x1", "y1"), safe)),
        zones=zones, chosen=chosen,
        need={"w": need_w, "h": need_h}, shrink=shrink,
        shrink_zone=shrink_zone)
    if chosen is None:
        result["note"] = (
            "no zone clears the face at full size; scale the text by "
            f"`shrink` into zone `{shrink_zone}`" if shrink else
            "no zone clears the face even shrunk; move the text or reframe")
    if debug_png:
        draw_debug(debug_png, frame, zoom, zoom_y, face, head, safe, zones,
                   chosen)
        result["debug_png"] = str(debug_png)
    return result, 0 if chosen else 3


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("video")
    ap.add_argument("--at", type=float, required=True, help="seconds")
    ap.add_argument("--zoom", type=float, default=1.0,
                    help="EDL zoom on this range (rules/proof.md)")
    ap.add_argument("--zoom-y", type=float, default=DEFAULT_ZOOM_Y,
                    help="EDL zoom_y vertical bias (render.py default 0.42)")
    ap.add_argument("--need-w", type=float, default=MIN_TEXT_W)
    ap.add_argument("--need-h", type=float, default=MIN_TEXT_H)
    ap.add_argument("--debug-png")
    a = ap.parse_args()
    result, code = analyse(a.video, a.at, a.zoom, a.zoom_y, a.debug_png,
                           a.need_w, a.need_h)
    print(json.dumps(result, indent=2))
    sys.exit(code)


if __name__ == "__main__":
    main()

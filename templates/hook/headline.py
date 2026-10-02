#!/usr/bin/env python3
"""Hook headline: stacked type with an entity mark, replacing the flat slab.

Written for this project (see NOTICE.md). Same integration pattern as
`shatter.py`: `build()` returns {"css", "clips", "anims"} for the composition
that `scripts/compose.py` writes, and `splice()` inserts it. The clip sits on
track 50, above cards (15) and proof (45), under shatter (55) and captions (60).

Rules it enforces (rules/hooks.md, "The headline"):
  * 3 to 5 words, 6 is the ceiling and carries a warning, 7+ is an error;
  * 2 or 3 stacked lines, left-aligned, broken by meaning: a layout whose last
    line is a single word, or whose line ends on a connector, is refused;
  * one claim word in the accent colour, the rest white and slightly smaller;
  * an entity mark to the left: `face` (circular crop tight on the detected
    face, the face filling ~70% of the circle), `logo` (an SVG/PNG of the real
    mark) or `icon` (scripts/icons.py), sized ~1.25x the claim cap height;
  * no slab: contrast comes from a thick dark outline and a layered drop
    shadow; only when that is not enough a soft feathered gradient (max 0.35)
    darkens the wall behind the type. Never a box;
  * a scale-snap / slide entrance inside ~0.3s (never a fade), a hold, then a
    slide-out at `t_out`;
  * every pixel of content inside the zone, and the zone must clear the face
    and any other zone passed in `avoid` (the shatter zone).

    python3 headline.py --text "LIMIT HIT? SAVE THE SESSION" --accent-word SAVE \
        --accent "#D97757" --mark face --mark-src assets/people/anthropic.png \
        --t-in 0.08 --t-out 3.2 --zone 54,288,864,166 --assets-dir out/

`--text` breaks lines for you; `--lines "A B|C D E"` takes your own breaks.
Face mode needs OpenCV (the i-hate-editing venv); everything else is stdlib.
`preview` mode renders over a real clip, as `demo.py` does for shatter.
"""

import argparse
import itertools
import json
import math
import re
import shutil
import struct
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parents[1] / "scripts"))

import shatter  # noqa: E402  (parse_box, validate, rects_intersect)

FRAME_W, FRAME_H = 1080, 1920
TRACK_HEADLINE = 50
MIN_WORDS, MAX_WORDS, SOFT_MAX_WORDS = 3, 6, 5
MIN_LINES, MAX_LINES = 2, 3
MIN_HOLD_SECONDS = 1.5
MIN_MARK_PX = 120            # rules/assets.md: a face must read at 120 px
ENTRANCE_SECONDS = 0.26
EXIT_SECONDS = 0.22
SMALL_WORD_EM = 0.86         # non-claim words, relative to the claim word
WORD_GAP_EM = 0.36           # space after a word, in that word's own em
LINE_HEIGHT = 0.94
MARK_CAP_RATIO = 1.25        # mark diameter / claim cap height
OUTLINE_EM = 0.09            # dark outline thickness outside the glyph, in em
MAX_FEATHER = 0.35           # darkest point of the feathered gradient; no box
FEATHER_PAD = (24, 90)       # px the gradient extends past the zone (y, x)
MARK_GAP = 26
FIT_SLACK = 0.97             # kerning is not measured; leave 3% of the width
# Entrance overshoot is clamped so neighbours never touch mid-snap: a
# back-ease overshoots about 6% at s=1.2 and 10% at s=1.7, and the gap after a
# word (WORD_GAP_EM) is wider than the claim word's growth at that overshoot.
CLAIM_EASE = "back.out(1.2)"
MARK_EASE = "back.out(1.4)"
CONTENT_PAD = 6              # px of the zone kept free for the outline
FACE_FILL = 0.70             # share of the chip circle the face box fills
CHIP_CROP_MARGIN = 1 / FACE_FILL   # crop side / face box longer edge
CHIP_PX = 360
DEFAULT_FONT_FILE = Path.home() / "Library" / "Fonts" / "ArchivoBlack-Regular.ttf"
CONNECTORS = frozenset(
    "A AN THE TO OF IN ON AT FOR AND OR BUT WITH FROM BY AS IS ARE YOUR YOU".split())


# ------------------------------------------------------------- text rules

def split_words(line):
    return line.split()


def bare(word):
    return re.sub(r"[^\w]", "", word).upper()


def count_words(lines):
    return sum(len(split_words(l)) for l in lines)


def check_word_count(lines):
    """Return a list of warnings; raise ValueError outside 3..6 words."""
    n = count_words(lines)
    if n < MIN_WORDS:
        raise ValueError(f"headline has {n} word(s); rules/hooks.md asks for "
                         f"{MIN_WORDS} to {SOFT_MAX_WORDS}")
    if n > MAX_WORDS:
        raise ValueError(f"headline has {n} words; {MAX_WORDS} is the ceiling "
                         f"(rules/hooks.md)")
    if n > SOFT_MAX_WORDS:
        return [f"{n} words: the ceiling, not the target; cut one if you can"]
    return []


def check_layout(lines):
    """Raise ValueError for a layout that strands a word or splits a phrase.

    The defect this exists for: "WHEN YOUR LIMIT RUNS / OUT"."""
    if not MIN_LINES <= len(lines) <= MAX_LINES:
        raise ValueError(f"headline has {len(lines)} line(s); stack "
                         f"{MIN_LINES} or {MAX_LINES}")
    for line in lines:
        if not split_words(line):
            raise ValueError("headline has an empty line")
    last = split_words(lines[-1])
    if len(last) == 1:
        raise ValueError(f"orphan word {last[0]!r} alone on the last line: "
                         f"re-break by meaning (rules/hooks.md)")
    for line in lines[:-1]:
        tail = split_words(line)[-1]
        if bare(tail) in CONNECTORS:
            raise ValueError(f"line ends on the connector {tail!r}, which "
                             f"belongs with the word after it")


def _line_cost(line):
    return len(line)


def legal_layouts(text, line_counts=(2, 3)):
    """Every stacked layout of `text` with no orphan and no dangling
    connector, in a stable order. Raises ValueError for a bad word count."""
    words = text.split()
    check_word_count([text])
    found = []
    for n in line_counts:
        for cuts in itertools.combinations(range(1, len(words)), n - 1):
            edges = (0, *cuts, len(words))
            lines = [" ".join(words[a:b]) for a, b in zip(edges, edges[1:])]
            try:
                check_layout(lines)
            except ValueError:
                continue
            found.append(lines)
    return found


def layout_score(lines):
    """Lower is better: lines ending on punctuation, then fewer lines, then
    the narrowest widest line."""
    punct = sum(1 for l in lines[:-1] if l[-1] in "?!:,.-")
    return (-punct, len(lines), max(_line_cost(l) for l in lines))


def break_lines(text, line_counts=(2, 3)):
    """Break `text` into stacked lines by meaning.

    Every legal layout (no orphan, no dangling connector) is scored: lines
    that end on punctuation are preferred, then the narrowest widest line, so
    the type can be set larger. Raises ValueError when no layout is legal."""
    layouts = legal_layouts(text, line_counts)
    if not layouts:
        raise ValueError(f"no legal stacked layout for {text!r}: every break "
                         f"strands a word or splits a phrase")
    return min(layouts, key=layout_score)


def resolve_lines(lines_or_text):
    """Accept a string (auto break) or a list of lines (validated as given)."""
    lines = (break_lines(lines_or_text) if isinstance(lines_or_text, str)
             else [l.strip() for l in lines_or_text])
    warnings = check_word_count(lines)
    check_layout(lines)
    return lines, warnings


def pick_claim(lines, accent_word=None):
    """The word that takes the accent colour. Defaults to the longest word
    that is not a connector; ties go to the first."""
    flat = [w for l in lines for w in split_words(l)]
    if accent_word:
        hits = [i for i, w in enumerate(flat) if bare(w) == bare(accent_word)]
        if not hits:
            raise ValueError(f"accent word {accent_word!r} is not in the headline")
        return hits[0]
    pool = [(len(bare(w)), -i) for i, w in enumerate(flat) if bare(w) not in CONNECTORS]
    return -max(pool)[1] if pool else 0


# ------------------------------------------------------------ type metrics

class FontMetrics:
    """Advance widths and cap height read straight from a TrueType file
    (cmap format 4, hmtx, OS/2), so the largest size that fits a zone is
    computed, not guessed. Stdlib only. Kerning (GPOS) is not applied; the
    FIT_SLACK margin and the browser-side fit absorb the difference."""

    def __init__(self, path=DEFAULT_FONT_FILE):
        data = Path(path).read_bytes()
        count = struct.unpack(">H", data[4:6])[0]
        tabs = {}
        for i in range(count):
            tag, _, off, _ = struct.unpack(">4sIII", data[12 + 16 * i:28 + 16 * i])
            tabs[tag.decode()] = off
        self.upem = struct.unpack(">H", data[tabs["head"] + 18:tabs["head"] + 20])[0]
        os2 = tabs["OS/2"]
        self.cap_em = struct.unpack(">h", data[os2 + 88:os2 + 90])[0] / self.upem
        self.ascent_em = struct.unpack(">h", data[tabs["hhea"] + 4:tabs["hhea"] + 6])[0] / self.upem
        self.descent_em = -struct.unpack(">h", data[tabs["hhea"] + 6:tabs["hhea"] + 8])[0] / self.upem
        n_metrics = struct.unpack(">H", data[tabs["hhea"] + 34:tabs["hhea"] + 36])[0]
        hmtx = tabs["hmtx"]
        self._adv = [struct.unpack(">H", data[hmtx + 4 * i:hmtx + 4 * i + 2])[0]
                     for i in range(n_metrics)]
        self._cmap = self._read_cmap(data, tabs["cmap"])

    @staticmethod
    def _read_cmap(data, base):
        n = struct.unpack(">H", data[base + 2:base + 4])[0]
        for i in range(n):
            plat, enc, off = struct.unpack(">HHI", data[base + 4 + 8 * i:base + 12 + 8 * i])
            if (plat, enc) not in ((3, 1), (0, 3), (0, 4)):
                continue
            t = base + off
            if struct.unpack(">H", data[t:t + 2])[0] != 4:
                continue
            segx2 = struct.unpack(">H", data[t + 6:t + 8])[0]
            seg = segx2 // 2
            ends = struct.unpack(f">{seg}H", data[t + 14:t + 14 + segx2])
            starts = struct.unpack(f">{seg}H", data[t + 16 + segx2:t + 16 + 2 * segx2])
            deltas = struct.unpack(f">{seg}h", data[t + 16 + 2 * segx2:t + 16 + 3 * segx2])
            ro_at = t + 16 + 3 * segx2
            ranges = struct.unpack(f">{seg}H", data[ro_at:ro_at + segx2])
            cmap = {}
            for k in range(seg):
                for code in range(starts[k], ends[k] + 1):
                    if code == 0xFFFF:
                        continue
                    if ranges[k] == 0:
                        gid = (code + deltas[k]) & 0xFFFF
                    else:
                        at = ro_at + 2 * k + ranges[k] + 2 * (code - starts[k])
                        gid = struct.unpack(">H", data[at:at + 2])[0]
                        gid = (gid + deltas[k]) & 0xFFFF if gid else 0
                    cmap[code] = gid
            return cmap
        raise ValueError("font has no format-4 unicode cmap")

    def advance_em(self, text):
        total = 0
        for ch in text:
            gid = self._cmap.get(ord(ch), 0)
            total += self._adv[min(gid, len(self._adv) - 1)]
        return total / self.upem


_METRICS = {}


def font_metrics(path=DEFAULT_FONT_FILE):
    key = str(path)
    if key not in _METRICS:
        _METRICS[key] = FontMetrics(path)
    return _METRICS[key]


def cap_height_px(font_px, metrics=None):
    """Cap height of the claim word (set at the full font size)."""
    return (metrics or font_metrics()).cap_em * font_px


def line_em(line_index, lines, claim_index):
    """Font size of a line in em of the headline font: the line holding the
    claim is set at 1em, every other line at SMALL_WORD_EM, so its box is as
    short as its words (a small line does not pay for the claim's height)."""
    flat = sum(len(split_words(l)) for l in lines[:line_index])
    holds_claim = flat <= claim_index < flat + len(split_words(lines[line_index]))
    return 1.0 if holds_claim else SMALL_WORD_EM


def stack_size(lines, claim_index, font_px, metrics=None):
    """(width, box height) of the stacked text in px, as the CSS lays it out:
    the claim at 1em, every other word at SMALL_WORD_EM, WORD_GAP_EM after each
    word but the last on a line, LINE_HEIGHT per line of that line's own size."""
    m = metrics or font_metrics()
    widest, flat, height = 0.0, 0, 0.0
    for i, line in enumerate(lines):
        words = split_words(line)
        w = 0.0
        for k, x in enumerate(words):
            em = 1.0 if flat == claim_index else SMALL_WORD_EM
            w += m.advance_em(x.upper()) * em
            if k < len(words) - 1:
                w += WORD_GAP_EM * em
            flat += 1
        widest = max(widest, w)
        height += LINE_HEIGHT * line_em(i, lines, claim_index) * font_px
    return widest * font_px, height


def ink_insets(lines, claim_index, font_px, metrics=None):
    """(top, bottom) px between the stack's box and its ink: the first line's
    cap top and the last line's baseline, from the font's ascent and descent
    (CSS centres the content area in the line box)."""
    m = metrics or font_metrics()
    half_lead = (LINE_HEIGHT - m.ascent_em - m.descent_em) / 2
    first = line_em(0, lines, claim_index) * font_px
    last = line_em(len(lines) - 1, lines, claim_index) * font_px
    return ((half_lead + m.ascent_em - m.cap_em) * first,
            (half_lead + m.descent_em) * last)


def stack_ink_height(lines, claim_index, font_px, metrics=None):
    """Height of the visible capitals: cap top of line one to baseline of the
    last line. This, not the line boxes, is what must clear the face."""
    _w, box = stack_size(lines, claim_index, font_px, metrics)
    top, bottom = ink_insets(lines, claim_index, font_px, metrics)
    return box - top - bottom


def mark_for_font(font_px, metrics=None):
    """Mark diameter: MARK_CAP_RATIO x the claim cap height, never under the
    120 px a face needs to read."""
    return max(MIN_MARK_PX, round(MARK_CAP_RATIO * cap_height_px(font_px, metrics)))


def text_box(zone, mark_px):
    """(width, height) the stacked text may use inside `zone`."""
    return (zone["w"] - mark_px - MARK_GAP - 2 * CONTENT_PAD,
            zone["h"] - 2 * CONTENT_PAD)


def largest_font_px(lines, claim_index, zone, mark_px, metrics=None, ceiling=400):
    """The largest integer font size whose stack fits the zone beside a mark
    of `mark_px`, found by binary search on the measured layout. 0 when even
    24px does not fit."""
    avail_w, avail_h = text_box(zone, mark_px)
    avail_w *= FIT_SLACK
    return _search(lambda px: _fits(lines, claim_index, px, avail_w, avail_h, metrics), ceiling)


def largest_font_with_mark(lines, claim_index, zone, metrics=None, ceiling=400):
    """(font_px, mark_px): the largest font whose mark, sized from that same
    font by MARK_CAP_RATIO, still leaves room for the text and fits the zone
    height. (0, None) when nothing fits."""
    def fits(px):
        mark = mark_for_font(px, metrics)
        avail_w, avail_h = text_box(zone, mark)
        return (mark <= zone["h"] - 2 * CONTENT_PAD
                and _fits(lines, claim_index, px, avail_w * FIT_SLACK, avail_h, metrics))
    font = _search(fits, ceiling)
    return (font, mark_for_font(font, metrics)) if font else (0, None)


def _fits(lines, claim_index, px, avail_w, avail_h, metrics):
    w, _box = stack_size(lines, claim_index, px, metrics)
    return w <= avail_w and stack_ink_height(lines, claim_index, px, metrics) <= avail_h


def _search(fits, ceiling, floor=24):
    lo, hi = floor, ceiling
    if not fits(lo):
        return 0
    while lo < hi:
        mid = (lo + hi + 1) // 2
        lo, hi = (mid, hi) if fits(mid) else (lo, mid - 1)
    return lo


# ------------------------------------------------------------- the mark

def crop_square(image_w, image_h, head, margin=CHIP_CROP_MARGIN):
    """Square (x, y, side) centred on `head` (x, y, w, h), inside the image.
    The chip passes the detector's face box, so the face fills 1/margin of it.

    Pure geometry so it is testable without OpenCV. The side is the head's
    longer edge times `margin`, shrunk to the image if needed, and slid back
    inside rather than padded: no pixel is invented."""
    x, y, w, h = head
    side = min(max(w, h) * margin, image_w, image_h)
    cx, cy = x + w / 2, y + h / 2
    left = min(max(cx - side / 2, 0), image_w - side)
    top = min(max(cy - side / 2, 0), image_h - side)
    return left, top, side


def detect_head(image_bgr):
    """Largest face in the image, grown to the head as safe_zone does.
    Detection only: nothing here tries to say who the face belongs to."""
    import safe_zone
    _, faces = safe_zone.detect_faces(image_bgr)
    if not faces:
        raise ValueError("no face detected: centre is not guessed; use the "
                         "logo rung (rules/assets.md)")
    x, y, w, h, score = max(faces, key=lambda f: f[2] * f[3])
    head = safe_zone.expand_head((x, y, w, h))
    return (x, y, w, h), head, score


def make_face_chip(src, dest, size=CHIP_PX):
    """Circular crop tight on the detected face box (the face fills FACE_FILL
    of the circle, so hair and a held mic fall outside it). Crop and resize
    only; the alpha mask is the circle, no retouching, no generated pixels."""
    import cv2
    import numpy as np
    img = cv2.imread(str(src), cv2.IMREAD_UNCHANGED)
    if img is None:
        raise ValueError(f"cannot read {src}")
    if img.ndim == 3 and img.shape[2] == 4 and img[..., 3].min() < 255:
        raise ValueError("photo has transparency: not a plain photograph")
    bgr = img[..., :3].copy()
    face, _head, score = detect_head(bgr)
    ih, iw = bgr.shape[:2]
    left, top, side = crop_square(iw, ih, face)
    l, t, s = int(round(left)), int(round(top)), int(round(side))
    chip = cv2.resize(bgr[t:t + s, l:l + s], (size, size), interpolation=cv2.INTER_AREA)
    mask = np.zeros((size, size), np.uint8)
    cv2.circle(mask, (size // 2, size // 2), size // 2, 255, -1, cv2.LINE_AA)
    cv2.imwrite(str(dest), np.dstack([chip, mask]))
    return {"face": [round(v, 1) for v in face], "crop": [l, t, s],
            "score": round(float(score), 3), "image": [iw, ih]}


def _icon_svg(spec, accent, assets_dir):
    """Fetch through scripts/icons.py (exact match or nothing) unless a file
    is given. Lucide strokes take `currentColor`; set it to the accent."""
    if spec.get("src"):
        return Path(spec["src"]), None
    import icons
    which = spec.get("set", "lucide")
    index = icons.brand_index() if which == "simple-icons" else []
    entry, err = icons.fetch_one(spec["name"], which, Path(assets_dir) / "icons", index)
    if err:
        raise ValueError(err)
    path = Path(entry["file"])
    svg = path.read_text().replace("currentColor", accent)
    path.write_text(svg)
    return path, entry


def prepare_mark(mark, accent, assets_dir):
    """Return (relative_file, kind, info). Writes into assets_dir."""
    mode = mark.get("mode")
    out = Path(assets_dir)
    out.mkdir(parents=True, exist_ok=True)
    if mode == "face":
        dest = out / "mark_face.png"
        info = make_face_chip(mark["src"], dest)
        return dest.name, "face", info
    if mode == "logo":
        src = Path(mark["src"])
        dest = out / f"mark_logo{src.suffix}"
        shutil.copy2(src, dest)
        return dest.name, "logo", {"src": str(src)}
    if mode == "icon":
        path, entry = _icon_svg(mark, accent, out)
        dest = out / f"mark_icon{path.suffix}"
        if path.resolve() != dest.resolve():
            shutil.copy2(path, dest)
        return dest.name, "icon", entry or {"src": str(path)}
    raise ValueError(f"mark mode must be face, logo or icon, got {mode!r}")


def dominant_accent(image_path):
    """Modal non-neutral colour of a brand image (the favicon, the app icon).
    Exact pixel value, so the accent is read from the mark, not remembered."""
    import collections
    import colorsys
    import cv2
    img = cv2.imread(str(image_path), cv2.IMREAD_UNCHANGED)
    if img is None:
        raise ValueError(f"cannot read {image_path}")
    if img.shape[2] == 3:
        import numpy as np
        img = np.dstack([img, np.full(img.shape[:2], 255, np.uint8)])
    counts = collections.Counter()
    for b, g, r, a in img.reshape(-1, 4):
        if a < 255:
            continue
        _, s, v = colorsys.rgb_to_hsv(r / 255, g / 255, b / 255)
        if s > 0.35 and 0.25 < v < 0.98:
            counts[(int(r), int(g), int(b))] += 1
    if not counts:
        raise ValueError("no non-neutral colour in the image")
    r, g, b = counts.most_common(1)[0][0]
    return f"#{r:02X}{g:02X}{b:02X}"


# --------------------------------------------------------------- the build

def validate_placement(zone, face, avoid, frame=(FRAME_W, FRAME_H)):
    shatter.validate(zone, face, *frame)
    for other in avoid:
        if shatter.rects_intersect(zone, other):
            raise ValueError("headline zone overlaps another zone (the shatter "
                             "zone): move one of them")


def validate_timing(t_in, t_out):
    if t_in < 0:
        raise ValueError("t_in is before the first frame")
    if t_out - t_in < MIN_HOLD_SECONDS:
        raise ValueError(f"headline is on screen {t_out - t_in:.2f}s; hold it "
                         f"at least {MIN_HOLD_SECONDS}s")


def build(lines, accent, mark, t_in, t_out, zone, face=None, avoid=(),
          accent_word=None, uid="hookheadline", font="Archivo Black",
          font_file=DEFAULT_FONT_FILE, assets_dir=None, feather=0.0,
          track=TRACK_HEADLINE, frame=(FRAME_W, FRAME_H), mark_px=None):
    """Return {"css", "clips", "anims", ...} ready to splice into build_html.

    `lines` is a string (broken for you) or a list of lines (validated).
    `mark_px` pins the mark diameter (default: MARK_CAP_RATIO x the claim cap
    height, so the mark grows with the type).
    `feather` (0 to MAX_FEATHER) adds a soft gradient behind the type; the
    default is none, because outline and shadow carry the contrast.
    `mark` is {"mode": "face", "src": png} | {"mode": "logo", "src": svg} |
    {"mode": "icon", "name": "clock", "set": "lucide"} (or "src" for a file).
    The processed mark and the font are written under `assets_dir`; copy that
    folder beside the composition's index.html."""
    lines, warnings = resolve_lines(lines)
    claim = pick_claim(lines, accent_word)
    validate_timing(t_in, t_out)
    validate_placement(zone, face, avoid, frame)
    if not 0 <= feather <= MAX_FEATHER:
        raise ValueError(f"feather {feather} is outside 0..{MAX_FEATHER}: a "
                         f"darker backing is a box, which hooks.md rules out")
    if mark_px is not None and mark_px < MIN_MARK_PX:
        warnings.append(f"mark is {mark_px}px, under the {MIN_MARK_PX}px a "
                        f"face needs to read: give the zone more height")
    if assets_dir is None:
        raise ValueError("assets_dir is required: the mark image and the font "
                         "are files the composition loads")
    assets_dir = Path(assets_dir)
    mark_file, mark_kind, mark_info = prepare_mark(mark, accent, assets_dir)
    fonts = assets_dir / "fonts"
    fonts.mkdir(parents=True, exist_ok=True)
    font_name = Path(font_file).name
    shutil.copy2(font_file, fonts / font_name)
    try:
        metrics = font_metrics(font_file)
    except (struct.error, KeyError, ValueError, IndexError):
        metrics = font_metrics(DEFAULT_FONT_FILE)   # an unparsable file: same family assumed
    if mark_px is None:
        fs, mark_px = largest_font_with_mark(lines, claim, zone, metrics)
    else:
        fs = largest_font_px(lines, claim, zone, mark_px, metrics)
    if fs == 0:
        raise ValueError("headline does not fit the zone even at 24px: give "
                         "the zone more room or use fewer words")
    outline = outline_shadow(fs)
    _top_inset, _bottom_inset = ink_insets(lines, claim, fs, metrics)
    ink_shift = round((_bottom_inset - _top_inset) / 2, 1)
    _w, box_h = stack_size(lines, claim, fs, metrics)
    ring = max(6, round(mark_px * 0.045))
    disc = "#0d0d10" if mark_kind != "face" else "#000"
    inset = 0 if mark_kind == "face" else 17
    fit_mode = "cover" if mark_kind == "face" else "contain"

    css = f"""
      @font-face {{
        font-family: "{font}"; src: url("{assets_dir.name}/fonts/{font_name}") format("truetype");
        font-weight: 400; font-style: normal;
      }}
      #{uid} {{
        position: absolute; left: {zone['x']:.0f}px; top: {zone['y']:.0f}px;
        width: {zone['w']:.0f}px; height: {zone['h']:.0f}px;
        display: flex; align-items: center; justify-content: center;
        gap: {MARK_GAP}px; padding: 0 {CONTENT_PAD}px;
      }}
      #{uid} .hl-feather {{
        position: absolute; inset: -{FEATHER_PAD[0]}px -{FEATHER_PAD[1]}px; pointer-events: none;
        background: radial-gradient(ellipse 50% 50% at 50% 50%,
          rgba(0, 0, 0, {feather:.2f}) 0%, rgba(0, 0, 0, {feather * 0.85:.2f}) 38%,
          rgba(0, 0, 0, {feather * 0.4:.2f}) 68%, rgba(0, 0, 0, 0) 100%);
      }}
      #{uid} .hl-mark {{
        position: relative; z-index: 2; flex: none; width: {mark_px}px; height: {mark_px}px;
        border-radius: 50%; background: {disc};
        border: {ring}px solid {accent};
        box-shadow: 0 6px 18px rgba(0, 0, 0, 0.6);
        overflow: hidden;
      }}
      #{uid} .hl-mark img {{
        position: absolute; left: {inset}%; top: {inset}%;
        width: {100 - 2 * inset}%; height: {100 - 2 * inset}%; object-fit: {fit_mode};
      }}
      #{uid} .hl-textwrap {{ position: relative; top: {ink_shift}px; flex: 0 1 auto; min-width: 0; }}
      #{uid} .hl-text {{
        display: inline-block; white-space: nowrap; text-align: left;
        font-family: "{font}", sans-serif; font-size: {fs}px; line-height: {LINE_HEIGHT};
        text-transform: uppercase; color: #fff; text-shadow: {outline};
      }}
      #{uid} .hl-line {{ display: block; transform-origin: 0% 50%; }}
      #{uid} .hl-small {{ font-size: {SMALL_WORD_EM}em; }}
      #{uid} .hl-w {{ display: inline-block; font-size: {SMALL_WORD_EM}em; margin-right: {WORD_GAP_EM}em; transform-origin: 0% 60%; }}
      #{uid} .hl-small .hl-w {{ font-size: 1em; }}
      #{uid} .hl-w:last-child {{ margin-right: 0; }}
      #{uid} .hl-claim {{ font-size: 1em; color: {accent}; }}
"""
    flat = 0
    line_html = []
    for i, l in enumerate(lines):
        spans = []
        for w in split_words(l):
            cls = "hl-w hl-claim" if flat == claim else "hl-w"
            spans.append(f'<span class="{cls}">{w}</span>')
            flat += 1
        small = " hl-small" if line_em(i, lines, claim) < 1 else ""
        line_html.append(f'<span class="hl-line{small}">{"".join(spans)}</span>')

    t_end = t_out
    off = round(zone["x"] + zone["w"] + 80)
    anims = [f"""      // Fit the stack to its zone after the webfont resolves.
      (function () {{
        const fit = () => {{
          const box = document.querySelector("#{uid}");
          const text = box.querySelector(".hl-text");
          const maxW = box.clientWidth - {mark_px + MARK_GAP + 2 * CONTENT_PAD}, maxH = {math.ceil(box_h) + 4};
          let size = parseFloat(getComputedStyle(text).fontSize), guard = 0;
          while ((text.offsetWidth > maxW || text.offsetHeight > maxH) && size > 24 && guard < 120) {{
            size -= 1; text.style.fontSize = size + "px"; guard++;
          }}
        }};
        fit();
        if (document.fonts && document.fonts.ready) document.fonts.ready.then(fit);
      }})();""",
        # Entrance: lines slide in from the right, so they never cross the mark,
        # and the scale-snap overshoot is clamped (CLAIM_EASE, MARK_EASE).
        f'      tl.from("#{uid} .hl-mark", {{ scale: 0.15, duration: {ENTRANCE_SECONDS}, '
        f'ease: "{MARK_EASE}" }}, {t_in:.3f});',
        f'      tl.from("#{uid} .hl-line", {{ x: {off}, duration: {ENTRANCE_SECONDS}, '
        f'ease: "power3.out", stagger: 0.05 }}, {t_in + 0.02:.3f});',
        f'      tl.from("#{uid} .hl-claim", {{ scale: 0.55, transformOrigin: "50% 60%", '
        f'duration: {ENTRANCE_SECONDS}, ease: "{CLAIM_EASE}" }}, {t_in + 0.08:.3f});',
        # Exit: everything leaves left, ending as the clip ends.
        f'      tl.to("#{uid} .hl-line", {{ x: -{off}, duration: {EXIT_SECONDS}, '
        f'ease: "power3.in", stagger: 0.04 }}, {t_out - EXIT_SECONDS - 0.04:.3f});',
        f'      tl.to("#{uid} .hl-mark", {{ scale: 0, duration: {EXIT_SECONDS}, '
        f'ease: "back.in(2)" }}, {t_out - EXIT_SECONDS:.3f});',
    ]
    if feather:
        anims += [
            f'      tl.from("#{uid} .hl-feather", {{ scaleX: 0.2, transformOrigin: "0% 50%", '
            f'duration: {ENTRANCE_SECONDS}, ease: "power3.out" }}, {t_in:.3f});',
            f'      tl.to("#{uid} .hl-feather", {{ scaleX: 0.2, transformOrigin: "0% 50%", '
            f'duration: {EXIT_SECONDS}, ease: "power3.in" }}, {t_out - EXIT_SECONDS:.3f});',
        ]
    clip = (f'      <div id="{uid}" class="clip" data-start="{t_in:.3f}" '
            f'data-duration="{t_end - t_in:.3f}" data-track-index="{track}" '
            f'data-layout-allow-overflow>\n'
            + (f'        <div class="hl-feather"></div>\n' if feather else "") +
            f'        <div class="hl-mark"><img src="{assets_dir.name}/{mark_file}" alt=""></div>\n'
            f'        <div class="hl-textwrap"><div class="hl-text">{"".join(line_html)}</div></div>\n'
            f'      </div>')
    return {"css": css, "clips": [clip], "anims": anims, "t_in": t_in,
            "t_end": t_end, "lines": lines, "claim_index": claim,
            "warnings": warnings, "mark": {"kind": mark_kind, "file": mark_file,
                                           "diameter": mark_px, **mark_info},
            "uid": uid}


def outline_shadow(font_px):
    """text-shadow for the type: a round dark outline OUTLINE_EM thick (16
    hard-edged copies on a circle, so no mitred spikes on A or M), then a
    layered drop shadow. Contrast comes from this, not from a box."""
    r = OUTLINE_EM * font_px
    ring = [f"{r * math.cos(a * math.pi / 8):.1f}px {r * math.sin(a * math.pi / 8):.1f}px 0 #000"
            for a in range(16)]
    drop = [f"0 {0.05 * font_px:.1f}px {0.03 * font_px:.1f}px rgba(0,0,0,0.65)",
            f"0 {0.10 * font_px:.1f}px {0.26 * font_px:.1f}px rgba(0,0,0,0.5)",
            f"0 0 {0.55 * font_px:.1f}px rgba(0,0,0,0.3)"]
    return ", ".join(ring + drop)


def splice(html, fragment):
    """Insert a fragment into the output of compose.build_html."""
    return shatter.splice(html, fragment)


# -------------------------------------------------------------------- cli

def preview(clip, out, lines, accent, mark, t_in, t_out, zone, face=None,
            duration=None, render=False, **kw):
    """Composite the headline over a real clip through compose.build_html,
    as demo.py does for shatter. Writes under `out`, never the skill dir."""
    import json as _json
    import subprocess
    import compose
    clip = Path(clip)
    width, height, full = compose.probe(clip)
    duration = min(duration or full, full)
    comp = Path(out) / "composition"
    comp.mkdir(parents=True, exist_ok=True)
    shutil.copy2(clip, comp / clip.name)
    (comp / "hyperframes.json").write_text(_json.dumps(compose.HYPERFRAMES_JSON, indent=2))
    (comp / "package.json").write_text(_json.dumps(compose.PACKAGE_JSON, indent=2))
    fragment = build(lines, accent, mark, t_in, t_out, zone, face,
                     assets_dir=comp / "hl_assets", frame=(width, height), **kw)
    html = compose.build_html(clip.name, width, height, duration, [], {})
    (comp / "index.html").write_text(splice(html, fragment))
    print(f"-> {comp / 'index.html'}  lines={fragment['lines']}")
    for sub in ("check", "render"):
        if sub == "render" and not render:
            break
        cmd = ["npx", "--yes", compose.HYPERFRAMES_PKG, sub]
        if sub == "render":
            cmd += [".", "-q", "high", "--crf", "16", "--video-frame-format", "png",
                    "-o", str((Path(out) / "master.mp4").resolve())]
        r = subprocess.run(cmd, cwd=comp, capture_output=True, text=True, errors="replace")
        print((r.stdout or r.stderr)[-1800:])
        if r.returncode != 0:
            return 1
    return 0


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    src = ap.add_mutually_exclusive_group(required=True)
    src.add_argument("--text", help="headline text; lines are broken for you")
    src.add_argument("--lines", help='your own breaks, separated by "|"')
    ap.add_argument("--accent-word")
    ap.add_argument("--accent", help="hex colour of the mark/brand")
    ap.add_argument("--accent-from", help="brand image to read the accent from")
    ap.add_argument("--mark", required=True, choices=["face", "logo", "icon"])
    ap.add_argument("--mark-src", help="image/SVG file (face, logo, or icon)")
    ap.add_argument("--icon", help="icon name for icons.py (icon mode)")
    ap.add_argument("--icon-set", default="lucide", choices=["lucide", "simple-icons"])
    ap.add_argument("--t-in", type=float, required=True)
    ap.add_argument("--t-out", type=float, required=True)
    ap.add_argument("--zone", required=True, help="x,y,w,h in frame pixels")
    ap.add_argument("--face", help="x,y,w,h face box: the zone must clear it")
    ap.add_argument("--avoid", action="append", default=[],
                    help="x,y,w,h of another zone (shatter); repeatable")
    ap.add_argument("--mark-px", type=int, help="pin the mark diameter in px")
    ap.add_argument("--feather", type=float, default=0.0,
                    help=f"0 to {MAX_FEATHER}: soft gradient behind the type, only if "
                         f"outline and shadow fail the contrast check")
    ap.add_argument("--assets-dir", help="where the mark and font are written")
    ap.add_argument("--clip", help="preview over this clip (needs --out)")
    ap.add_argument("--out")
    ap.add_argument("--duration", type=float)
    ap.add_argument("--render", action="store_true")
    a = ap.parse_args()
    try:
        accent = a.accent or (dominant_accent(a.accent_from) if a.accent_from else "#76B900")
        lines = a.text if a.text else a.lines.split("|")
        mark = {"mode": a.mark}
        if a.mark_src:
            mark["src"] = a.mark_src
        if a.icon:
            mark.update(name=a.icon, set=a.icon_set)
        kw = dict(accent_word=a.accent_word, feather=a.feather, mark_px=a.mark_px,
                  avoid=[shatter.parse_box(b) for b in a.avoid])
        zone = shatter.parse_box(a.zone)
        face = shatter.parse_box(a.face) if a.face else None
        if a.clip:
            return preview(a.clip, a.out, lines, accent, mark, a.t_in, a.t_out,
                           zone, face, a.duration, a.render, **kw)
        out = build(lines, accent, mark, a.t_in, a.t_out, zone, face,
                    assets_dir=a.assets_dir, **kw)
    except ValueError as err:
        print(f"error: {err}", file=sys.stderr)
        return 1
    print(json.dumps(out, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())

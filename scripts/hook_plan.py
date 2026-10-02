#!/usr/bin/env python3
"""Decide the hook design with no questions (rules/hooks.md, "The studio
decides the design"). Writes hook_plan.json: every decision plus a `why`.

    hook_plan.py cut.mp4 --text "Imagine you hit your Claude limit mid-work and \\
        your session is gone" --entity "Claude/Anthropic" --out hook_plan.json
    hook_plan.py cut.mp4 --chunks chunks.json --entity NVIDIA --zoom 1.2:1.9:1.25

Decisions, in order:
  1. MARK ladder (rules/assets.md): a registered face if the photo passes the
     suitability checks, else the exact logo if it renders at 120 px, else a
     concept icon from a small keyword map. Rejected rungs are recorded.
     A face is only ever looked up in assets/people/manifest.json. Detection
     here finds a face; nothing identifies one.
  2. LINES + ACCENT: the studio WRITES the headline. `condense()` scores the
     spoken words (entity, loss/win, number, pain verb, punchline position),
     drops fillers/connectors/pronouns, and ranks 3-5 word candidates made
     only of words the speaker said, in spoken order. `--headline` overrides.
     Candidates are broken into stacked lines and one claim word takes the
     accent colour, read from the winning mark's brand. Dropped words are
     logged with the reason.
  3. SIZE + PLACEMENT: the face is measured at the first frame and at every
     zoom bell (safe_zone.py); the zone must stay clear of all of them. Safe-
     area zones are exhausted (both size thresholds) before the header band is
     touched; header intrusion is a flagged last resort. The largest type that
     fits is chosen. Claim cap height must reach MIN_CAP_PX; when a zone cannot
     hold it the plan tries the next candidate (fewer/shorter words), then the
     next zone, and says so.
  4. CONTRAST: outline + layered shadow alone. A soft feathered gradient
     (<= 0.35, no edges, never a box) is added only if the measured wall is too
     bright for that to pass the check.
  5. TREATMENT: at most one. Loss/negation word -> loss_red grade (+ shatter
     when a clear shatter zone exists); number/win -> held-zoom hint; else none.
     hook_open is anchored with sfx.hook_open_event.

Exit codes: 0 plan written; 2 input or detection failure (no face, bad
words); 3 no legal design exists (nothing is placed over the face instead).

Run with the studio venv (OpenCV):
    ~/.cache/i-hate-editing/venv/bin/python scripts/hook_plan.py ...
"""

import argparse
import colorsys
import itertools
import json
import math
import re
import shlex
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
SKILL = HERE.parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(SKILL / "templates" / "hook"))

import headline  # noqa: E402
import hook_storyboard  # noqa: E402
import safe_zone  # noqa: E402
import shatter  # noqa: E402

PEOPLE_DIR = SKILL / "assets" / "people"
MANIFEST = PEOPLE_DIR / "manifest.json"

# ---- studio numbers (sources in the comments) ------------------------------
MIN_CAP_PX = 110           # claim cap height at 1080x1920: ~2x the first preview
ACCEPT_CAP_PX = 100        # measured on final-v6 "FREE" (y 95..195); below this: error
HOOK_SECONDS = 3.2         # headline README preview window
HEADLINE_IN = 0.08         # headline README example --t-in
PROFILE_ACCENT = "#76B900"  # profile.yml brand.accent default (compose.py)
HELD_ZOOM_HINT = 1.18      # compose.BIG_ZOOM
# ---- working defaults, UNVERIFIED (no studio source) -----------------------
HEADLINE_TOP_FLOOR = round(safe_zone.H * safe_zone.HEADER_FRAC / 2)
MIN_SHARPNESS = 100.0      # Laplacian variance of the face at 200px; see photo_suitability
MAX_YAW_RATIO = 0.30       # nose offset from eye midline / eye distance
MAX_ROLL_DEG = 15.0
MIN_FACE_SCORE = 0.8
MAX_LOGO_ASPECT = 2.0      # rules/assets.md rung 3: wordmarks wider than 2:1 are out
MIN_LOGO_LUMINANCE = 0.12  # the chip is near-black; a darker logo vanishes on it
MAX_FEATHER = headline.MAX_FEATHER   # soft gradient ceiling; never a box
FEATHER_STEPS = (0.0, 0.2, MAX_FEATHER)   # backing escalation, tried only when the check fails
SHATTER_MIN_W, SHATTER_MIN_H, SHATTER_MAX_H = 400, 200, 260
TARGET_WORDS = (4, 3)      # distilled headline sizes, in order of preference
WORDSETS_PER_SIZE = 60
ADJACENT_BONUS = 0.4       # per pair of kept words that were neighbours in the speech
ENTITY_BONUS = 1.0         # a candidate that keeps the entity word
PUNCHLINE_BONUS = 0.4      # at most, for words late in the sentence

STOP = frozenset("""a an the to of in on at for and or but with from by as is are was
were be been am it its this that these those so just really very actually
imagine then than if when while you your yours i me my we our us he she they
them their do does did have has had will would can could should
suppose picture basically literally honestly hey okay ok well like gonna wanna
what why how who which where there here about into also too still even ever
im ive youre youve thats theres hes shes""".split())
LOSS_STRONG = frozenset("""not never no nahi khatam dead wrong gone lost stuck broken fail
failed cant dont without banned blocked expired crash crashed wasted""".split())
LOSS_SOFT = frozenset("limit limits limited error errors slow stop".split())
GLUE = frozenset("is are was were to for of in on at with from by as".split())  # kept only between two kept words that were neighbours
PAIN = frozenset("hit hits lose lost ran runs burn burned waste miss missed wipe wiped reset".split())
WIN = frozenset("free unlimited win won best faster instantly double triple".split())
NUMBER_RE = re.compile(r"^\$?\d[\d,.]*[kmxb%]?$", re.I)

# keyword -> lucide icon, kept small on purpose. First matching row wins.
CONCEPTS = (
    (("api key", "key", "token", "password"), "key"),
    (("limit", "limits", "quota", "rate"), "clock"),
    (("speed", "fast", "faster", "slow", "instant", "instantly"), "zap"),
    (("money", "cash", "pay", "paid", "price", "cost", "dollar", "dollars", "$"), "coins"),
    (("free", "gift"), "gift"),
    (("unlimited", "infinite"), "infinity"),
    (("hack", "leak", "secure", "security", "safe"), "shield"),
    (("bug", "error", "crash", "broken"), "bug"),
    (("deadline", "hours", "minutes", "time", "timer"), "timer"),
)
DEFAULT_ICON = "zap"


class PlanError(Exception):
    """A decision that cannot be made legally. `code` is the exit status."""

    def __init__(self, message, code=3):
        super().__init__(message)
        self.code = code


# ------------------------------------------------------------- word helpers

def bare(word):
    return re.sub(r"[^\w$%-]", "", word).strip("-")


def norm(text):
    return re.sub(r"[^a-z0-9]", "", text.lower())


def entity_candidates(entity):
    """'Claude/Anthropic' -> ['Claude', 'Anthropic']. Empty for none."""
    if not entity or not entity.strip() or entity.strip().lower() == "none":
        return []
    parts = re.split(r"\s*(?:/|,|\||&|\band\b)\s*", entity.strip())
    return [p for p in parts if p]


def classify(word):
    w = bare(word).lower()
    if w in LOSS_STRONG:
        return "loss_strong"
    if w in LOSS_SOFT:
        return "loss_soft"
    if NUMBER_RE.match(w):
        return "number"
    if w in WIN:
        return "win"
    return None


# ----------------------------------------------------------- 1. mark ladder

def manifest_entry(manifest, candidates):
    """(key, entry) when any candidate names a registered entity. The mapping
    is the user's (rules/assets.md); nothing is inferred from a face."""
    wanted = {norm(c) for c in candidates}
    for key, entry in (manifest.get("entities") or {}).items():
        names = {norm(key)} | {norm(t) for t in re.split(r"[/,]", entry.get("stands_for", ""))}
        if wanted & names:
            return key, entry
    return None, None


def _yunet_rows(image_bgr):
    import cv2
    model = safe_zone._yunet_model()
    if model is None:
        return None
    det = cv2.FaceDetectorYN.create(str(model), "", (image_bgr.shape[1], image_bgr.shape[0]),
                                    safe_zone.MIN_CONFIDENCE)
    _, rows = det.detect(image_bgr)
    return [] if rows is None else [[float(v) for v in r] for r in rows]


def photo_suitability(path):
    """Checks a registered photo before it becomes a face chip. Returns
    {"ok", "failed": [names], "metrics": {...}}. Thresholds are working
    defaults; sharpness was calibrated on one photo and synthetic blur
    (original 861, sigma 1 -> 260, sigma 2 -> 63, 8x downscale -> 20)."""
    import cv2
    import numpy as np
    failed, metrics = [], {}
    img = cv2.imread(str(path), cv2.IMREAD_UNCHANGED)
    if img is None:
        return {"ok": False, "failed": ["readable"], "metrics": {"readable": False}}
    ih, iw = img.shape[:2]
    metrics["image_px"] = [iw, ih]
    alpha_min = int(img[..., 3].min()) if img.ndim == 3 and img.shape[2] == 4 else 255
    metrics["alpha_min"] = alpha_min
    if alpha_min < 255:
        failed.append("alpha")
    bgr = img[..., :3].copy() if img.ndim == 3 else cv2.cvtColor(img, cv2.COLOR_GRAY2BGR)
    rows = _yunet_rows(bgr)
    if rows is None:
        return {"ok": False, "failed": ["detector"],
                "metrics": {**metrics, "detector": "YuNet model unavailable"}}
    metrics["faces_found"] = len(rows)
    if len(rows) != 1:
        failed.append("single_face")
        return {"ok": False, "failed": failed, "metrics": metrics}
    r = rows[0]
    x, y, w, h, score = r[0], r[1], r[2], r[3], r[-1]
    metrics.update(face_px=[round(w), round(h)], face_score=round(score, 3))
    # Front-facing: nose centred between the eyes, eyes level.
    (rex, rey), (lex, ley), (nx, _) = (r[4], r[5]), (r[6], r[7]), (r[8], r[9])
    eye_dist = math.hypot(lex - rex, ley - rey) or 1.0
    metrics["yaw_ratio"] = round(abs(nx - (rex + lex) / 2) / eye_dist, 3)
    metrics["roll_deg"] = round(abs(math.degrees(math.atan2(ley - rey, lex - rex))), 1)
    if metrics["yaw_ratio"] > MAX_YAW_RATIO or metrics["roll_deg"] > MAX_ROLL_DEG:
        failed.append("front_facing")
    # Covered / cut off: landmarks inside the box, box inside the image, and a
    # confident detection. A hand or mask over the face lowers the score or
    # moves landmarks; sunglasses are not detected (limit of this check).
    inside = all(x - 0.05 * w <= r[i] <= x + 1.05 * w and y - 0.05 * h <= r[i + 1] <= y + 1.05 * h
                 for i in range(4, 14, 2))
    clipped = x < 0 or y < 0 or x + w > iw or y + h > ih
    metrics["landmarks_inside"], metrics["clipped_at_edge"] = inside, clipped
    if score < MIN_FACE_SCORE or not inside or clipped:
        failed.append("not_covered")
    # Sharpness on the face box, normalised to 200 px so size does not skew it.
    x0, y0 = max(0, int(x)), max(0, int(y))
    face_gray = cv2.cvtColor(bgr[y0:int(y + h), x0:int(x + w)], cv2.COLOR_BGR2GRAY)
    face_gray = cv2.resize(face_gray, (200, 200), interpolation=cv2.INTER_AREA)
    metrics["sharpness"] = round(float(cv2.Laplacian(face_gray, cv2.CV_64F).var()), 1)
    if metrics["sharpness"] < MIN_SHARPNESS:
        failed.append("sharpness")
    # Reads at 120 px: the circular crop must hold >=120 source px, and YuNet
    # must still find exactly one face on the 120 px circle.
    left, top, side = headline.crop_square(iw, ih, safe_zone.expand_head((x, y, w, h)))
    metrics["crop_source_px"] = round(side)
    chip = cv2.resize(bgr[int(round(top)):int(round(top + side)), int(round(left)):int(round(left + side))],
                      (headline.MIN_MARK_PX, headline.MIN_MARK_PX), interpolation=cv2.INTER_AREA)
    mask = np.zeros(chip.shape[:2], np.uint8)
    cv2.circle(mask, (60, 60), 60, 255, -1)
    chip[mask == 0] = 0
    chip_rows = _yunet_rows(chip) or []
    metrics["faces_at_120px"] = len(chip_rows)
    if side < headline.MIN_MARK_PX or len(chip_rows) != 1:
        failed.append("reads_at_120px")
    return {"ok": not failed, "failed": failed, "metrics": metrics}


def logo_ink_aspect(svg_path):
    """(aspect, how): ink bounding box of the logo rendered at 120 px, as the
    larger side over the smaller. rsvg-convert when present, else the SVG
    viewBox (which cannot see a wide wordmark inside a square box)."""
    import cv2
    import numpy as np
    exe = shutil.which("rsvg-convert")
    if exe:
        with tempfile.TemporaryDirectory() as tmp:
            png = Path(tmp) / "logo.png"
            subprocess.run([exe, "-w", "240", "-h", "240", "--keep-aspect-ratio",
                            str(svg_path), "-o", str(png)], check=True, capture_output=True)
            img = cv2.imread(str(png), cv2.IMREAD_UNCHANGED)
        ys, xs = np.where(img[..., 3] > 16)
        if len(xs):
            w, h = xs.max() - xs.min() + 1, ys.max() - ys.min() + 1
            return max(w / h, h / w), "rendered with rsvg-convert"
    m = re.search(r'viewBox="[\d.\-]+ [\d.\-]+ ([\d.]+) ([\d.]+)"', Path(svg_path).read_text())
    if m:
        w, h = float(m.group(1)), float(m.group(2))
        return max(w / h, h / w), "viewBox only (rsvg-convert missing: wordmark width not measured)"
    return None, "no viewBox and no renderer"


def luminance(hex_colour):
    r, g, b = (int(hex_colour.lstrip("#")[i:i + 2], 16) / 255 for i in (0, 2, 4))
    lin = [c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4 for c in (r, g, b)]
    return 0.2126 * lin[0] + 0.7152 * lin[1] + 0.0722 * lin[2]


def logo_lookup(candidates, workdir):
    """Exact Simple Icons match that renders at 120 px. -> (mark, None) or
    (None, reason). Never a near match (icons.find exact_only)."""
    import icons
    index = icons.brand_index()
    reasons = []
    for cand in candidates:
        if not icons.find(index, cand, exact_only=True):
            reasons.append(f"no exact Simple Icons entry for {cand!r}")
            continue
        entry, err = icons.fetch_one(cand, "simple-icons", Path(workdir) / "icons", index)
        if err:
            reasons.append(err)
            continue
        aspect, how = logo_ink_aspect(entry["file"])
        if aspect is None or aspect > MAX_LOGO_ASPECT:
            reasons.append(f"{entry['name']} logo aspect {aspect and round(aspect, 2)}:1 "
                           f"exceeds {MAX_LOGO_ASPECT:.0f}:1 ({how}): too wide to read at 120px")
            continue
        hexc = entry.get("hex")
        if hexc and luminance(hexc) < MIN_LOGO_LUMINANCE:
            reasons.append(f"{entry['name']} logo colour {hexc} is too dark for the dark chip")
            continue
        return ({"mode": "logo", "src": entry["file"], "name": entry["name"],
                 "aspect": round(aspect, 2), "aspect_check": how, "hex": hexc,
                 "licence": entry.get("licence")}, None)
    return None, "; ".join(reasons) or "no candidate"


def icon_lookup(name, workdir):
    import icons
    entry, err = icons.fetch_one(name, "lucide", Path(workdir) / "icons", [])
    if err:
        return None, err
    return {"mode": "icon", "name": name, "set": "lucide", "src": entry["file"],
            "licence": entry.get("licence")}, None


def pick_concept(words, hook_text):
    """(icon, matched_keyword) from the small map; headline words first, then
    the whole hook. (None, None) when nothing matches."""
    for source in (words, hook_text.split()):
        tokens = [bare(w).lower() for w in source]
        joined = " ".join(tokens)
        for keys, icon in CONCEPTS:
            for key in keys:
                hit = (f" {key} " in f" {joined} ") if " " in key else (key in tokens)
                if hit:
                    return icon, key
    return None, None


def choose_mark(entity, hook_text, headline_words, workdir, manifest=None,
                photo_check=photo_suitability, logo_check=logo_lookup,
                icon_check=icon_lookup):
    """Walk the ladder. Returns {"mark": {...}, "rung", "why", "rejected": [...]}.
    The three checks are injectable so the decisions are testable offline."""
    if manifest is None:
        manifest = json.loads(MANIFEST.read_text()) if MANIFEST.exists() else {"entities": {}}
    cands = entity_candidates(entity)
    rejected = []
    if not cands:
        rejected.append({"rung": 1, "kind": "face", "reason": "no entity named in the hook"})
        rejected.append({"rung": 2, "kind": "logo", "reason": "no entity named in the hook"})
    else:
        key, entry = manifest_entry(manifest, cands)
        if entry is None:
            rejected.append({"rung": 1, "kind": "face",
                             "reason": f"no face registered for {'/'.join(cands)} in assets/people/manifest.json"})
        else:
            photo = PEOPLE_DIR / entry["file"]
            verdict = photo_check(photo)
            if verdict["ok"]:
                return {"mark": {"mode": "face", "src": str(photo), "entity_key": key,
                                 "registered_by": entry.get("registered_by"),
                                 "licence": entry.get("licence"), "use": entry.get("use")},
                        "rung": 1, "suitability": verdict,
                        "why": f"face registered for {key!r} passes every suitability check; "
                               f"kept as a small chip, never as the speaker of the line",
                        "rejected": rejected}
            rejected.append({"rung": 1, "kind": "face", "suitability": verdict,
                             "reason": f"photo for {key!r} failed: {', '.join(verdict['failed'])}"})
        logo, reason = logo_check(cands, workdir)
        if logo:
            return {"mark": logo, "rung": 2,
                    "why": f"exact logo for {logo['name']}, {logo['aspect_check']}, "
                           f"aspect {logo['aspect']}:1",
                    "rejected": rejected}
        rejected.append({"rung": 2, "kind": "logo", "reason": reason})
    icon, key = pick_concept(headline_words, hook_text)
    if icon is None:
        icon, why = DEFAULT_ICON, "no concept keyword in the hook; neutral default icon"
    else:
        why = f"concept icon {icon!r} for the keyword {key!r}"
    mark, err = icon_check(icon, workdir)
    if mark is None:
        raise PlanError(f"icon {icon!r} could not be fetched: {err}", code=2)
    return {"mark": mark, "rung": 3, "why": why, "rejected": rejected}


def pick_accent(candidates, index, fallback=PROFILE_ACCENT):
    """Accent from the entity's live brand colour (Simple Icons hex through
    icons.py), skipping near-neutral brand colours; else the profile palette."""
    import icons
    for cand in candidates:
        for title, _slug, hexc in icons.find(index, cand, exact_only=True):
            if not hexc:
                continue
            r, g, b = (int(hexc[i:i + 2], 16) / 255 for i in (0, 2, 4))
            _, s, v = colorsys.rgb_to_hsv(r, g, b)
            if s > 0.35 and 0.25 < v < 0.98:
                return {"hex": f"#{hexc.upper()}", "source": f"simple-icons brand colour of {title}",
                        "why": f"accent read live from the {title} brand colour"}
    return {"hex": fallback, "source": "profile palette",
            "why": "no saturated brand colour for the entity; profile accent"}


# --------------------------------------------------- 2. lines + accent word

def word_weights(words, entity_words, positions=None):
    """Meaning weight per word: loss/number/win lead, then the entity and pain
    verbs, then plain words; hyphenated qualifiers trail; words late in the
    sentence get a small bonus because the punchline lands last."""
    out = []
    n = len(positions) if positions else 0
    for k, w in enumerate(words):
        b = bare(w)
        kind = classify(w)
        weight = {"loss_strong": 3.0, "number": 3.0, "loss_soft": 2.5, "win": 2.5}.get(kind)
        if weight is None:
            weight = 1.0 + min(len(b), 8) / 16
            if norm(b) in entity_words:
                weight = 2.0
            elif b.lower() in PAIN:
                weight = 1.8
            elif "-" in b:
                weight -= 0.5
        if n > 1:
            weight += PUNCHLINE_BONUS * k / (n - 1)
        out.append(weight)
    return out


def condense(text, entity_words=frozenset()):
    """Deterministic headline writer, no LLM. Returns candidates ranked best
    first: [{"words", "dropped", "dropped_why", "score", "why"}].

    Only words the speaker said are used, in spoken order. Fillers, connectors
    and pronouns go first (STOP); of the rest, the combination with the highest
    meaning weight wins, plus a bonus for words that were neighbours in the
    speech (so the result reads as a phrase) and for keeping the entity.
    Candidates are 4 then 3 words; the caller tries them in order until one
    fits the minimum type size. A hook with fewer than 3 meaning words raises
    PlanError."""
    raw = text.split()
    keep = [i for i, w in enumerate(raw) if bare(w).lower() not in STOP and bare(w)]
    if len(keep) < 3:
        raise PlanError(f"only {len(keep)} meaning-bearing word(s) in {text!r}; pass --headline "
                        f"with 3-5 words", code=2)
    weights = word_weights([raw[i] for i in keep], entity_words, keep)
    has_entity = {k for k, i in enumerate(keep) if norm(bare(raw[i])) in entity_words}
    by_size = {size: [] for size in TARGET_WORDS}
    for k in range(2, max(TARGET_WORDS) + 1):
        for combo in itertools.combinations(range(len(keep)), k):
            chosen = _with_glue(raw, keep, combo)
            if len(chosen) not in by_size:
                continue
            score = sum(weights[c] for c in combo)
            score += ADJACENT_BONUS * sum(1 for a, b in zip(combo, combo[1:]) if b == a + 1)
            if has_entity & set(combo):
                score += ENTITY_BONUS
            by_size[len(chosen)].append((-round(score, 6), combo, chosen))
    out, seen = [], set()
    for size in TARGET_WORDS:
        for neg, _combo, chosen in sorted(by_size[size])[:WORDSETS_PER_SIZE]:
            words = tuple(raw[i].strip(".,;:!?").upper() for i in chosen)
            if words in seen:
                continue
            seen.add(words)
            why = {}
            for i, w in enumerate(raw):
                if i not in chosen:
                    why[w.strip(".,;:!?")] = ("filler, connector or pronoun" if i not in keep
                                              else "lower meaning weight than the words kept")
            glued = [raw[i].strip(".,;:!?") for i in chosen if i not in keep]
            out.append({"words": list(words), "dropped": list(why), "dropped_why": why,
                        "score": -neg, "glue": glued,
                        "why": f"condensed to {size} spoken words by meaning weight "
                               f"({-neg:.2f}); fillers and the lowest-weight words dropped"
                               + (f"; kept {', '.join(glued)} to join neighbouring words" if glued else "")})
    return out


def _with_glue(raw, keep, combo):
    """Raw indexes of a combination, plus the GLUE words spoken directly
    between two chosen words that were neighbours among the meaning words
    ("session [is] gone"), so the headline reads as the speaker's phrase."""
    chosen = []
    for n, c in enumerate(combo):
        if n and c == combo[n - 1] + 1:
            between = list(range(keep[combo[n - 1]] + 1, keep[c]))
            if between and all(bare(raw[i]).lower() in GLUE for i in between):
                chosen += between
        chosen.append(keep[c])
    return chosen


def headline_candidates(text, entity_words=frozenset(), override=None):
    """Ordered candidate headlines. `--headline` wins as written. A hook that
    is already 3-5 words is tried as spoken first, then its condensed
    alternatives (shorter, so the type can grow); a longer hook is condensed."""
    def clean(ws):
        return [w.strip(".,;:").upper() for w in ws]

    raw = (override or text).split()
    if override:
        if not 3 <= len(raw) <= headline.MAX_WORDS:
            raise PlanError(f"--headline has {len(raw)} words; need 3 to {headline.MAX_WORDS}", code=2)
        return [{"words": clean(raw), "dropped": [], "dropped_why": {}, "why": "headline given as written"}]
    if 3 <= len(raw) <= headline.SOFT_MAX_WORDS:
        spoken = {"words": clean(raw), "dropped": [], "dropped_why": {},
                  "why": "hook is already 3-5 words; used as spoken"}
        try:
            alts = [c for c in condense(text, entity_words) if c["words"] != spoken["words"]]
        except PlanError:
            alts = []
        return [spoken] + alts
    return condense(text, entity_words)


def claim_order(words, entity_words, accent_word=None):
    """Flat word indexes in preference order for the accent: loss/negation,
    number, win, soft loss, then longer words; connectors and the entity name
    (the mark already carries it) come last."""
    if accent_word:
        hits = [i for i, w in enumerate(words) if bare(w).upper() == bare(accent_word).upper()]
        if not hits:
            raise PlanError(f"accent word {accent_word!r} is not in the headline {words}", code=2)
        return hits[:1]
    rank = {"loss_strong": 0, "number": 1, "win": 2, "loss_soft": 3, None: 4}

    def key(i):
        w = words[i]
        demote = bare(w).upper() in headline.CONNECTORS or norm(bare(w)) in entity_words
        return (demote, rank[classify(w)], -len(bare(w)), i)

    return sorted(range(len(words)), key=key)


# ------------------------------------------------ 3. size + placement search

def best_layout(words, claim, zone, metrics):
    """(font_px, lines, mark_px) with the largest font over every legal line
    layout; the mark is sized from the font (headline.MARK_CAP_RATIO x cap).
    None when nothing fits."""
    best = None
    for lines in headline.legal_layouts(" ".join(words)):
        f, mp = headline.largest_font_with_mark(lines, claim, zone, metrics)
        if f == 0:
            continue
        score = headline.layout_score(lines)
        key = (f, -score[0], -score[1], -score[2])
        if best is None or key > best[0]:
            best = (key, f, lines, mp)
    return None if best is None else (best[1], best[2], best[3])


def search_design(candidates, zones, entity_words, metrics, accent_word=None,
                  thresholds=(MIN_CAP_PX, ACCEPT_CAP_PX)):
    """The first design that reaches a cap-height threshold. Safe-area zones
    are exhausted at every threshold before a header-band zone is looked at:
    the higher threshold is tried in every zone of a tier before the lower one
    is accepted, but a header zone never beats a safe zone that reaches the
    floor. Within a zone the candidates are tried in rank order (meaning
    first, then fewer/shorter words); the layout and mark are the ones that
    give the largest type. Returns (design_or_None, trace)."""
    trace = []
    best_seen = {"cap_px": 0}
    tiers = [[z for z in zones if z["tier"] == t] for t in ("safe", "header")]
    for tier_zones in tiers:
        for threshold in thresholds:
            for zone in tier_zones:
                zbox = {k: zone[k] for k in ("x", "y", "w", "h")}
                reached = 0
                for rank, cand in enumerate(candidates):
                    for crank, claim in enumerate(claim_order(cand["words"], entity_words, accent_word)):
                        found = best_layout(cand["words"], claim, zbox, metrics)
                        if found is None:
                            continue
                        font, lines, mp = found
                        cap = headline.cap_height_px(font, metrics)
                        reached = max(reached, cap)
                        if cap > best_seen["cap_px"]:
                            best_seen = {"cap_px": round(cap), "zone": zone["name"],
                                         "lines": lines, "claim_word": cand["words"][claim]}
                        if cap >= threshold:
                            trace.append({"zone": zone["name"], "tier": zone["tier"],
                                          "threshold": threshold, "result": "accepted",
                                          "cap_px": round(cap)})
                            return ({"zone": zone, "words": cand["words"], "lines": lines,
                                     "claim_index": claim, "claim_word": cand["words"][claim],
                                     "claim_rank": crank, "wordset_rank": rank,
                                     "dropped": cand["dropped"],
                                     "dropped_why": cand.get("dropped_why", {}),
                                     "candidate_why": cand["why"],
                                     "font_px": font, "cap_px": round(cap), "mark_px": mp,
                                     "meets_target": cap >= MIN_CAP_PX}, trace)
                trace.append({"zone": zone["name"], "tier": zone["tier"], "threshold": threshold,
                              "result": "rejected", "best_cap_px": round(reached)})
    trace.append({"result": "none", "best_seen": best_seen})
    return None, trace


def tighten(design, metrics):
    """Shrink the zone to the ink actually placed (centred in the free space)
    so a shatter zone can use the rest, and recompute the font on the final
    box with the same functions headline.build uses. Returns (zone, font, mark)."""
    zone, lines = design["zone"], design["lines"]
    claim, mp = design["claim_index"], design["mark_px"]
    ink = headline.stack_ink_height(lines, claim, design["font_px"], metrics)
    h = min(zone["h"], math.ceil(max(ink, mp) + 2 * headline.CONTENT_PAD))
    final = {"x": zone["x"], "y": zone["y"] + round((zone["h"] - h) / 2), "w": zone["w"], "h": h}
    font = headline.largest_font_px(lines, claim, final, mp, metrics)
    return final, font, mp


def union_box(boxes):
    x0 = min(b["x"] for b in boxes)
    y0 = min(b["y"] for b in boxes)
    x1 = max(b["x"] + b["w"] for b in boxes)
    y1 = max(b["y"] + b["h"] for b in boxes)
    return {"x": x0, "y": y0, "w": x1 - x0, "h": y1 - y0}


def measure_moments(clip, hook_start, hook_end, bells):
    """Face + head at the first frame and at the peak of every zoom bell
    inside the hook window (safe_zone.analyse, one call per moment)."""
    moments = [{"at": hook_start, "zoom": 1.0, "zoom_y": safe_zone.DEFAULT_ZOOM_Y,
                "why": "hook first frame"}]
    for b in bells:
        peak = round((b["start"] + b["end"]) / 2, 3)
        if hook_start <= peak <= hook_end:
            moments.append({"at": peak, "zoom": b["zoom"],
                            "zoom_y": b.get("zoom_y", safe_zone.DEFAULT_ZOOM_Y),
                            "why": f"zoom bell {b['start']}-{b['end']} at its peak"})
    for m in moments:
        result, code = safe_zone.analyse(clip, m["at"], m["zoom"], m["zoom_y"], need_w=1, need_h=1)
        if result.get("face") is None:
            raise PlanError(f"no face found at {m['at']}s ({m['why']}); position is not guessed",
                            code=2)
        m.update(face=result["face"], head=result["head"], detector=result["detector"])
    return moments


def build_zones(head, strict_safe=False):
    """Candidate zones around the union head: safe-area zones ranked widest
    gap first, then (unless strict) a taller 'above' zone that reaches up into
    the header band. Header intrusion is the last resort and is flagged."""
    h = (head["x"], head["y"], head["w"], head["h"])
    zones, _chosen, _shrink = safe_zone.rank_zones(h, safe_zone.safe_rect(), need_w=1, need_h=1)
    out = [dict(z, name=z["zone"], tier="safe", intrudes_header=False) for z in zones]
    sx0, sy0, sx1, _sy1 = safe_zone.safe_rect()
    bottom = head["y"] - safe_zone.FACE_PAD
    if not strict_safe and HEADLINE_TOP_FLOOR < sy0 and bottom - HEADLINE_TOP_FLOOR > 0:
        out.append({"zone": "above_header", "name": "above_header", "tier": "header",
                    "intrudes_header": True, "x": sx0, "y": HEADLINE_TOP_FLOOR,
                    "w": sx1 - sx0, "h": bottom - HEADLINE_TOP_FLOOR,
                    "gap": head["y"] - HEADLINE_TOP_FLOOR, "fits": True, "fit_ratio": 1.0})
    return out


# --------------------------------------------------------- 4. treatment

def timed_words(text, chunks, hook_start, hook_end):
    """[{"word", "start", "end"}] from per-word timings, else chunk timings
    spread by letter count, else the hook window spread by letter count."""
    def spread(tokens, t0, t1):
        weights = [len(bare(t)) + 1 for t in tokens]
        total, at, out = sum(weights), t0, []
        for t, wt in zip(tokens, weights):
            d = (t1 - t0) * wt / total
            out.append({"word": t, "start": round(at, 3), "end": round(at + d, 3)})
            at += d
        return out

    if not chunks:
        return spread(text.split(), hook_start, hook_end)
    out = []
    for c in chunks:
        words = c.get("words")
        if words:
            out += [{"word": w.get("word") or w.get("text"), "start": w["start"], "end": w["end"]}
                    for w in words]
        else:
            out += spread(c["text"].split(), c["start"], c["end"])
    return out


def choose_treatment(words, claim_word, headline_zone, zones, face, measured=False):
    """One treatment at most. Loss/negation wins over number/win. Shatter is
    added only when a clear zone (not the headline's, clear of the face)
    exists; otherwise the grade runs alone."""
    loss = [w for w in words if classify(w["word"]) in ("loss_strong", "loss_soft")]
    if loss:
        strong = [w for w in loss if classify(w["word"]) == "loss_strong"]
        in_headline = [w for w in loss if bare(w["word"]).upper() == bare(claim_word).upper()]
        target = (in_headline or strong or loss)[-1]
        t0, t1 = target["start"], target["end"] + 0.25
        out = {"kind": "loss_red", "word_timing": "measured" if measured else "estimated from letter counts",
               "word": bare(target["word"]).upper(),
               "grade": {"preset": "loss_red", "window": f"{t0:.2f}:{t1:.2f}", "ease": 0.1},
               "why": f"{bare(target['word'])!r} is a negation/loss word: warm-red grade for the "
                      f"word plus a 0.25s tail"}
        zone = pick_shatter_zone(zones, headline_zone, face)
        if zone:
            out.update(kind="loss_red+shatter",
                       shatter={"word": out["word"], "t_hit": round(target["start"], 3), "zone": zone})
            out["why"] += (f"; shatter on the same word in a clear {zone['from_zone']} zone "
                           f"(counts as one treatment)")
        else:
            out["why"] += "; no clear shatter zone around the face, so the grade runs alone"
        return out
    num = [w for w in words if classify(w["word"]) in ("number", "win")]
    if num:
        target = num[0]
        return {"kind": "held_zoom", "word": bare(target["word"]).upper(),
                "zoom": HELD_ZOOM_HINT, "at": round(target["start"], 3),
                "why": f"{bare(target['word'])!r} is a number/win word: held zoom hint, no grade"}
    return {"kind": "none", "why": "no negation, loss, number or win word: no treatment"}


def pick_shatter_zone(zones, headline_zone, face):
    """First zone (widest gap) big enough for a word, disjoint from the
    headline and the face. Sized to at most SHATTER_MAX_H and centred."""
    keep = shatter.inflate(headline_zone, 20)
    for z in zones:
        if z["tier"] != "safe" or z["w"] < SHATTER_MIN_W or z["h"] < SHATTER_MIN_H:
            continue
        h = min(z["h"], SHATTER_MAX_H)
        box = {"x": z["x"], "y": z["y"] + round((z["h"] - h) / 2), "w": min(z["w"], 900), "h": h}
        try:
            shatter.validate(box, face)
        except ValueError:
            continue
        if shatter.rects_intersect(box, keep):
            continue
        return dict(box, from_zone=z["name"])
    return None


def zone_luminance(clip, moments, zone):
    """95th-percentile relative luminance (0..1, linear) of the clip under `zone`,
    worst over the measured moments, as the render would present it. The
    contrast audit trips on bright patches, not on the mean."""
    import cv2
    import numpy as np
    worst = 0.0
    for m in moments:
        view = safe_zone.render_view(safe_zone.read_frame(clip, m["at"]), m["zoom"], m["zoom_y"])
        x, y, w, h = (int(zone[k]) for k in ("x", "y", "w", "h"))
        rgb = cv2.cvtColor(view[y:y + h, x:x + w], cv2.COLOR_BGR2RGB).astype(np.float64) / 255
        lin = np.where(rgb <= 0.03928, rgb / 12.92, ((rgb + 0.055) / 1.055) ** 2.4)
        worst = max(worst, float(np.percentile(lin @ np.array([0.2126, 0.7152, 0.0722]), 95)))
    return worst


def check_contrast(plan, clip, workdir):
    """Run `hyperframes check` on the planned headline over the real clip and
    escalate only on failure: outline and layered shadow first, then a soft
    feathered gradient at FEATHER_STEPS. Returns the verdict and writes the
    winning feather into the plan. Measured on the bright wall of the
    nvidia-nim cut (luminance 0.71): the outline alone passed AA 11/11, and
    the same type with no outline failed at 1.5:1 to 1.9:1."""
    import contextlib
    import io
    z, h, m = plan["placement"]["zone"], plan["headline"], plan["mark"]
    face = plan["placement"]["face"]
    tried = []
    for feather in FEATHER_STEPS:
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = headline.preview(
                clip, Path(workdir), h["lines"], plan["accent"]["hex"],
                {k: m[k] for k in ("mode", "src", "name", "set") if k in m},
                plan["timing"]["t_in"], plan["timing"]["t_out"], z, face,
                duration=plan["timing"]["t_out"] + 0.2, accent_word=h["claim_word"],
                mark_px=plan["size"]["mark_px"], feather=feather)
        tail = [l.strip() for l in out.getvalue().splitlines() if "text checks" in l or "Check" in l]
        tried.append({"feather": feather, "passed": code == 0, "report": tail})
        if code == 0:
            plan["contrast"].update(feather=feather, verified=True, tried=tried)
            return plan["contrast"]
    plan["contrast"].update(verified=False, tried=tried)
    return plan["contrast"]


def hook_open_anchor(t_in, bells, first_word_start, hook_end, extra_visual=()):
    """Anchor via sfx.hook_open_event: the headline entrance is a visual
    event, so are bell starts and the shatter hit."""
    import sfx
    visual = [t_in, *(b["start"] for b in bells), *extra_visual]
    hit, reason = sfx.hook_open_event(visual, post_hook_at=hook_end, word_onset=first_word_start)
    if hit is None:
        return {"skipped": True, "why": reason}
    return {"at": hit["at"], "category": hit["category"], "why": hit["why"], "skipped": False}


# -------------------------------------------------------------- the plan

def plan_hook(clip, text, entity=None, hook_start=0.0, hook_end=HOOK_SECONDS, bells=(),
              chunks=None, override=None, accent_word=None, workdir=None,
              strict_safe=False, manifest=None):
    workdir = Path(workdir or tempfile.mkdtemp(prefix="hook_plan_"))
    workdir.mkdir(parents=True, exist_ok=True)
    cands = entity_candidates(entity)
    entity_words = frozenset(norm(t) for c in cands for t in c.split())
    metrics = headline.font_metrics()

    # 1+2: words first (the ladder may need them for the concept map).
    candidates = headline_candidates(text, entity_words, override)

    # 3a: where the face is.
    moments = measure_moments(clip, hook_start, hook_end, bells)
    head = union_box([m["head"] for m in moments])
    face = union_box([m["face"] for m in moments])
    zones = build_zones(head, strict_safe)

    # 3b: largest legal type.
    design, trace = search_design(candidates, zones, entity_words, metrics, accent_word)
    if design is None:
        detail = "; ".join(f"{t['zone']} best {t['best_cap_px']}px" for t in trace
                           if t["result"] == "rejected" and t["threshold"] == ACCEPT_CAP_PX)
        seen = trace[-1]["best_seen"]
        raise PlanError(
            f"no legal hook design: the claim word cannot reach {ACCEPT_CAP_PX}px cap height in any "
            f"zone clear of the face ({detail}). Best seen: {' / '.join(seen.get('lines', []))} "
            f"at {seen['cap_px']}px in {seen.get('zone')}. Reframe wider, shorten the hook, or pass "
            f"a shorter --headline (short words: about 5 letters per line fit at this size). "
            f"Nothing was placed over the face.")
    final_zone, font_px, mark_px = tighten(design, metrics)
    if shatter.rects_intersect(final_zone, head):
        raise PlanError("internal check failed: the chosen zone overlaps the head", code=3)

    # 1: mark ladder on the chosen words.
    ladder = choose_mark(entity, text, design["words"], workdir, manifest)
    index = None
    if cands:
        import icons
        index = icons.brand_index()
    accent = pick_accent(cands, index or [])

    luminance = zone_luminance(clip, moments, final_zone)
    feather = 0.0   # outline + layered shadow first; check_contrast escalates on failure

    # 4: treatment and hook_open.
    t_in = round(hook_start + HEADLINE_IN, 3)
    t_out = round(hook_end, 3)
    headline.validate_timing(t_in, t_out)
    words = timed_words(text, chunks, hook_start, hook_end)
    treatment = choose_treatment(words, design["claim_word"], final_zone, zones, face,
                                 measured=bool(chunks))
    extra = [treatment["shatter"]["t_hit"]] if "shatter" in treatment else []
    first_word = words[0]["start"] if words else hook_start
    hook_open = hook_open_anchor(t_in, list(bells), first_word, hook_end, extra)

    warnings = list(headline.check_word_count([" ".join(design["words"])]))
    if not design["meets_target"]:
        warnings.append(f"claim cap height {design['cap_px']}px is under the {MIN_CAP_PX}px target "
                        f"but at or above the {ACCEPT_CAP_PX}px floor (final-v6 measured about 100px)")
    safe_top = safe_zone.safe_rect()[1]
    intrudes = final_zone["y"] < safe_top
    if intrudes:
        safe_best = max([t.get("best_cap_px", 0) for t in trace
                         if t.get("tier") == "safe" and t["result"] == "rejected"] or [0])
        warnings.append(f"HEADER INTRUSION (last resort): ink starts at y={final_zone['y']}, above the safe "
                        f"top y={safe_top}, into the platform header band; no safe-area zone reached the "
                        f"{ACCEPT_CAP_PX}px floor (best {safe_best}px)")
    mark = ladder["mark"]
    plan = {
        "version": 1,
        "clip": str(clip),
        "hook": {"text": text, "start": hook_start, "end": hook_end, "bells": list(bells)},
        "entity": {"raw": entity, "candidates": cands},
        "mark": {**mark, "rung": ladder["rung"], "why": ladder["why"],
                 "rejected": ladder["rejected"],
                 **({"suitability": ladder["suitability"]} if "suitability" in ladder else {})},
        "accent": accent,
        "headline": {"lines": design["lines"], "words": [w for l in design["lines"] for w in l.split()],
                     "claim_index": design["claim_index"], "claim_word": design["claim_word"],
                     "dropped": design["dropped"], "dropped_why": design["dropped_why"],
                     "why": f"{design['candidate_why']}; accent on {design['claim_word']!r}: "
                            f"claim order is loss/number/win, then longer words, never the entity "
                            f"name the mark already shows; lines broken by meaning, no orphan",
                     "candidates_ranked": [c["words"] for c in candidates[:8]]},
        "placement": {
            "zone": final_zone, "available_zone": {k: design["zone"][k] for k in ("x", "y", "w", "h")},
            "zone_name": design["zone"]["name"], "tier": design["zone"]["tier"],
            "intrudes_header": intrudes,
            "face": face, "head": head, "moments": moments,
            "zones_considered": [{k: z[k] for k in ("name", "tier", "x", "y", "w", "h", "gap")} for z in zones],
            "trace": trace,
            "why": f"zone {design['zone']['name']!r} ({design['zone']['tier']}) is clear of the head at "
                   f"{len(moments)} measured moment(s); zones are ranked widest gap first and the "
                   f"first one that can hold the minimum type wins",
        },
        "size": {"font_px": font_px, "claim_cap_px": round(headline.cap_height_px(font_px, metrics)),
                 "min_cap_px": MIN_CAP_PX, "accept_cap_px": ACCEPT_CAP_PX,
                 "meets_target": design["meets_target"], "mark_px": mark_px,
                 "why": f"largest font whose ink fits the zone beside a {mark_px}px mark "
                        f"({headline.MARK_CAP_RATIO}x the claim cap height), by binary search on "
                        f"measured Archivo Black widths; claim cap height "
                        f"{round(headline.cap_height_px(font_px, metrics))}px"},
        "timing": {"t_in": t_in, "t_out": t_out,
                   "why": "enters 0.08s into the hook (scale-snap), holds to the end of the hook"},
        "contrast": {"outline_em": headline.OUTLINE_EM, "feather": feather, "verified": None,
                     "zone_luminance": round(luminance, 3),
                     "why": f"zone luminance {luminance:.2f}: contrast from a {headline.OUTLINE_EM}em dark "
                            f"outline and layered drop shadow, no slab; run with --verify-contrast to "
                            f"check it with hyperframes and add a feathered gradient (<= {MAX_FEATHER}) "
                            f"only on failure"},
        "treatment": treatment,
        "hook_open": hook_open,
        "warnings": warnings,
    }
    plan["headline_cmd"] = headline_command(plan)
    return plan


def headline_command(plan):
    z, h, m = plan["placement"]["zone"], plan["headline"], plan["mark"]
    box = lambda b: f"{b['x']:.0f},{b['y']:.0f},{b['w']:.0f},{b['h']:.0f}"  # noqa: E731
    args = ["~/.cache/i-hate-editing/venv/bin/python", "templates/hook/headline.py",
            "--lines", "|".join(h["lines"]), "--accent-word", h["claim_word"],
            "--accent", plan["accent"]["hex"], "--mark", m["mode"], "--mark-px", str(plan["size"]["mark_px"]),
            "--t-in", str(plan["timing"]["t_in"]), "--t-out", str(plan["timing"]["t_out"]),
            "--zone", box(z), "--face", box(plan["placement"]["face"])]
    if m["mode"] in ("face", "logo", "icon") and m.get("src"):
        args += ["--mark-src", m["src"]]
    if plan["contrast"]["feather"]:
        args += ["--feather", str(plan["contrast"]["feather"])]
    if "shatter" in plan["treatment"]:
        args += ["--avoid", box(plan["treatment"]["shatter"]["zone"])]
    return " ".join(a if a.startswith("~") else shlex.quote(a) for a in args)


def summary(plan):
    h, s, p, m, t = plan["headline"], plan["size"], plan["placement"], plan["mark"], plan["treatment"]
    z = p["zone"]
    lines = [
        f"MARK     rung {m['rung']} {m['mode']}: {m.get('name') or m.get('entity_key') or ''} - {m['why']}",
    ]
    for r in m["rejected"]:
        lines.append(f"           rejected rung {r['rung']} ({r['kind']}): {r['reason']}")
    if "suitability" in m:
        lines.append(f"           suitability {json.dumps(m['suitability']['metrics'])}")
    lines += [
        f"ACCENT   {plan['accent']['hex']} on {h['claim_word']} - {plan['accent']['source']}",
        f"LINES    {' / '.join(h['lines'])}" + (f"   (dropped: {', '.join(f'{w} [{r}]' for w, r in h['dropped_why'].items())})"
                                                         if h["dropped"] else ""),
        f"SIZE     font {s['font_px']}px, claim cap {s['claim_cap_px']}px (target {s['min_cap_px']}, floor "
        f"{s['accept_cap_px']}), mark {s['mark_px']}px",
        f"PLACE    zone {p['zone_name']} {z['x']},{z['y']},{z['w']},{z['h']}  "
        f"face {p['face']['x']:.0f},{p['face']['y']:.0f},{p['face']['w']:.0f},{p['face']['h']:.0f}  "
        f"gap to head {p['head']['y'] - (z['y'] + z['h']):.0f}px",
        f"CONTRAST feather {plan['contrast']['feather']} verified={plan['contrast']['verified']} - "
        f"{plan['contrast']['why']}",
        f"TREAT    {t['kind']}" + (f" on {t['word']}" if "word" in t else "") + f" - {t['why']}",
        "OPEN     " + (f"hook_open at {plan['hook_open']['at']:.2f}s ({plan['hook_open']['why']})"
                       if not plan["hook_open"]["skipped"] else f"skipped: {plan['hook_open']['why']}"),
    ]
    sb = plan.get("storyboard")
    if sb:
        beats = ", ".join(f"{b['t']:.2f}s {b['move']}" for b in sb["beats"])
        stings = ", ".join(f"{x['category']}@{x['hit_at']:.2f}" for x in sb["sounds"])
        lines.append(f"STORY    {sb['layout']} - {sb['why']}" + (f"; beats: {beats}" if beats else ""))
        lines.append(f"SOUND    {stings}")
    lines += [f"WARN     {w}" for w in plan["warnings"]]
    return "\n".join(lines)


def parse_bell(text):
    parts = [float(p) for p in text.split(":")]
    if len(parts) not in (3, 4) or parts[1] <= parts[0]:
        raise argparse.ArgumentTypeError("zoom bell is start:end:zoom[:zoom_y] with end > start")
    bell = {"start": parts[0], "end": parts[1], "zoom": parts[2]}
    if len(parts) == 4:
        bell["zoom_y"] = parts[3]
    return bell


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("clip")
    ap.add_argument("--text", help="the spoken hook")
    ap.add_argument("--chunks", help="JSON list of {text,start,end[,words]}; gives word timing")
    ap.add_argument("--headline", help="3-5 word headline to use as written")
    ap.add_argument("--entity", help='entity named in the hook, e.g. "Claude/Anthropic"; omit for none')
    ap.add_argument("--accent-word")
    ap.add_argument("--hook-start", type=float, default=0.0)
    ap.add_argument("--hook-end", type=float)
    ap.add_argument("--zoom", action="append", default=[], type=parse_bell,
                    metavar="START:END:ZOOM[:ZOOM_Y]", help="zoom bell window; repeatable")
    ap.add_argument("--strict-safe", action="store_true",
                    help="never reach into the header band; fail instead")
    ap.add_argument("--verify-contrast", action="store_true",
                    help="run hyperframes check on the planned headline; add a feathered "
                         "gradient only if outline + shadow fail (slow: one npx run per step)")
    ap.add_argument("--out", default="hook_plan.json")
    ap.add_argument("--workdir", help="where fetched icons/logos are written")
    ap.add_argument("--proof", action="append", default=[],
                    help="real capture for the top panel (repeatable); any proof makes the hook split")
    ap.add_argument("--kicker", help="small serif line above the headline, in the speaker's words")
    a = ap.parse_args()
    chunks = json.loads(Path(a.chunks).read_text()) if a.chunks else None
    text = a.text or (" ".join(c["text"] for c in chunks) if chunks else None)
    if not text:
        print("error: give --text or --chunks", file=sys.stderr)
        return 2
    hook_end = a.hook_end or (max(c["end"] for c in chunks) if chunks else HOOK_SECONDS)
    out = Path(a.out)
    try:
        plan = plan_hook(a.clip, text, a.entity, a.hook_start, hook_end, a.zoom, chunks,
                         a.headline, a.accent_word, a.workdir or out.parent / "hook_plan_assets",
                         a.strict_safe)
    except PlanError as err:
        print(f"error: {err}", file=sys.stderr)
        return err.code
    except ValueError as err:
        print(f"error: {err}", file=sys.stderr)
        return 2
    words = timed_words(text, chunks, a.hook_start, hook_end)
    plan["storyboard"] = hook_storyboard.storyboard(
        words, plan["headline"]["claim_word"], a.proof, plan["mark"], a.hook_start, hook_end, a.kicker)
    if a.verify_contrast:
        check_contrast(plan, a.clip, (a.workdir and Path(a.workdir) or out.parent) / "contrast_check")
        plan["headline_cmd"] = headline_command(plan)
    out.write_text(json.dumps(plan, indent=2))
    print(summary(plan))
    print(f"\n-> {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

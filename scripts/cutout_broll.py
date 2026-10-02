#!/usr/bin/env python3
"""Put b-roll BEHIND a cut-out speaker for one short window, behind a hard gate.

An earlier background replace measured 31% of source detail on a moving hand and
19% on the face, so this refuses to claim success unless the written file keeps
at least GATE (85%) of the source's Laplacian variance on a moving region and on
the face, measured across every frame of the window and never from stills.

Run it with the virtual-bg venv (system Python has no onnxruntime/cv2 wheels):

    ~/.cache/virtual-bg/venv/bin/python cutout_broll.py SRC PLATE OUT \\
        --start 4.0 --end 6.0 [--blur-plate [SIGMA]]

Exit 0 = gate passed. Exit 2 = GATE FAILED: the file is written as
`<out>_FAILED.<ext>` and the caller must use a card above the head instead.
`<out>.gate.json` is written either way. Exit 1 = could not run.

How it keeps detail
  * Subject pixels are the SOURCE pixels, copied bit-exact wherever alpha >= 0.98.
    Only the matte edge blends. The matte's foreground estimate (fgr) is never used.
  * No temporal smoothing of the matte (EMA cost ~75% of detail before). Recurrent
    RVM state is warmed up on frames before the window so the first frame is stable.
  * Frames outside the window are the source frames, unmodified, re-encoded at
    CRF 12 with the audio stream copied. Matting happens before any zoom/overlay:
    run this on the graded cut, then zoom/captions/headline on its output.

Plate placement (the plate is the whole backdrop; the subject covers most of it)
  The visible region V is every pixel where the union of the window's alphas stays
  below 0.1. For a seated chest-up shot that is the top ~22% full width and the
  outer columns. A plate wider than the frame is cover-fit and slid horizontally
  to the offset that puts the most plate edge energy inside V; a plate narrower
  than the frame is slid vertically the same way. The report prints the plate's
  visible fraction per height band so a plate with its detail under the chest can
  be rejected by eye before it is used.

Licences: RobustVideoMatting is GPL-3 (rendered video is fine). BiRefNet (MIT) is
an acceptable alternative. NEVER RMBG-2.0 (CC BY-NC).
"""
import argparse
import ast
import json
import os
import subprocess
import sys
from pathlib import Path

import cv2
import numpy as np

GATE = 0.85
SOLID_ALPHA = 250  # uint8; source pixels copied bit-exact at or above this
WARMUP_FRAMES = 15
MIN_REGION_PIXELS = 400
MOTION_THRESHOLD = 12
HALO_MARGIN = 20
HALO_WARN_FRACTION = 0.05
INTERIOR_ERODE_PX = 8
TRANSLUCENT_MAX = 0.01  # share of the subject interior allowed to be see-through
VIRTUAL_BG_MATTE = Path.home() / ".claude" / "skills" / "virtual-bg" / "scripts" / "matte_full.py"
FAIL_MESSAGE = "GATE FAILED: use a card above the head instead"


# ---------------------------------------------------------------- gate math --

def laplacian_variance(gray, mask):
    """Variance of the Laplacian over the masked pixels; None if the region is tiny."""
    if int(mask.sum()) < MIN_REGION_PIXELS:
        return None
    lap = cv2.Laplacian(gray.astype(np.float64), cv2.CV_64F)
    return float(lap[mask].var())


def detail_ratio(source_vars, output_vars):
    """Output detail as a share of source detail, over frames with a measurable region.

    Returns (ratio of means, worst single-frame ratio, frames used)."""
    pairs = [(s, o) for s, o in zip(source_vars, output_vars) if s is not None and o is not None and s > 0]
    if not pairs:
        return None, None, 0
    s = np.array([p[0] for p in pairs])
    o = np.array([p[1] for p in pairs])
    return float(o.mean() / s.mean()), float((o / s).min()), len(pairs)


def motion_mask(prev_gray, cur_gray, subject_mask, threshold=MOTION_THRESHOLD):
    """Pixels of the subject that moved between two source frames (hands, mostly)."""
    a = cv2.GaussianBlur(prev_gray, (0, 0), 2)
    b = cv2.GaussianBlur(cur_gray, (0, 0), 2)
    moved = cv2.absdiff(a, b) > threshold
    moved = cv2.dilate(moved.astype(np.uint8), np.ones((7, 7), np.uint8)) > 0
    return moved & subject_mask


def halo_fraction(output_bgr, source_bgr, plate_bgr, alpha_u8, margin=HALO_MARGIN):
    """Share of matte-edge pixels brighter than BOTH the subject and the plate beside them.

    A fringe of old-room pixels shows up as a bright rim that neither side owns.
    Subject brightness is a normalised blur of the solid-alpha source pixels."""
    edge = (alpha_u8 > 5) & (alpha_u8 < SOLID_ALPHA)
    if int(edge.sum()) < MIN_REGION_PIXELS:
        return 0.0
    luma = lambda x: cv2.cvtColor(x, cv2.COLOR_BGR2GRAY).astype(np.float32)
    solid = (alpha_u8 >= SOLID_ALPHA).astype(np.float32)
    num = cv2.GaussianBlur(luma(source_bgr) * solid, (0, 0), 6)
    den = cv2.GaussianBlur(solid, (0, 0), 6) + 1e-6
    subject_luma = num / den
    plate_luma = cv2.GaussianBlur(luma(plate_bgr), (0, 0), 3)
    out_luma = luma(output_bgr)
    bright = out_luma > np.maximum(subject_luma, plate_luma) + margin
    return float((bright & edge).sum() / edge.sum())


def translucent_interior_share(alpha_u8):
    """Share of the subject's interior where the matte lets the plate show through.

    Detail ratios are blind to this: a held microphone or a motion-blurred hand that
    the matte dissolves keeps its sharp pixels but shows the plate through them.
    Outside = low-alpha area connected to the frame border; everything else, holes
    included, is subject. The subject is eroded so honest edge blending is not counted."""
    low = (alpha_u8 < 128).astype(np.uint8)
    _, labels = cv2.connectedComponents(low, connectivity=4)
    border = np.unique(np.concatenate([labels[0], labels[-1], labels[:, 0], labels[:, -1]]))
    outside = np.isin(labels, border[border != 0]) & (low > 0)
    filled = (~outside).astype(np.uint8)
    k = np.ones((2 * INTERIOR_ERODE_PX + 1,) * 2, np.uint8)
    interior = cv2.erode(filled, k) > 0
    if not interior.any():
        return 0.0
    return float(((alpha_u8 < SOLID_ALPHA) & interior).sum() / interior.sum())


def verdict(hand_ratio, face_ratio, translucent=0.0, gate=GATE, translucent_max=TRANSLUCENT_MAX):
    """Pass only when both regions were measurable, both clear the detail gate, and the
    matte is not see-through inside the subject."""
    if hand_ratio is None or face_ratio is None:
        return False
    return hand_ratio >= gate and face_ratio >= gate and translucent <= translucent_max


def band_visibility(union_alpha_u8, bands=(0, 22, 55, 100)):
    """Fraction of each height band that stays visible (alpha < 0.1 in every frame)."""
    visible = union_alpha_u8 < 26
    h = visible.shape[0]
    return {f"{lo}-{hi}%": float(visible[int(h * lo / 100):int(h * hi / 100)].mean())
            for lo, hi in zip(bands[:-1], bands[1:])}


def pick_plate_crop(plate_bgr, frame_w, frame_h, visible_mask):
    """Cover-fit the plate to the frame, sliding along the overflow axis to the offset
    that puts the most edge energy inside the visible region. Returns (crop, offset_px)."""
    ph, pw = plate_bgr.shape[:2]
    scale = max(frame_w / pw, frame_h / ph)
    fitted = cv2.resize(plate_bgr, (max(frame_w, round(pw * scale)), max(frame_h, round(ph * scale))),
                        interpolation=cv2.INTER_AREA if scale < 1 else cv2.INTER_CUBIC)
    fh, fw = fitted.shape[:2]
    gray = cv2.cvtColor(fitted, cv2.COLOR_BGR2GRAY).astype(np.float32)
    energy = np.abs(cv2.Laplacian(gray, cv2.CV_32F))
    horizontal = fw > frame_w
    span = (fw - frame_w) if horizontal else (fh - frame_h)
    best, best_off = -1.0, 0
    for off in range(0, span + 1, max(1, span // 40)):
        window = energy[:, off:off + frame_w] if horizontal else energy[off:off + frame_h, :]
        score = float(window[visible_mask].sum())
        if score > best:
            best, best_off = score, off
    crop = fitted[:, best_off:best_off + frame_w] if horizontal else fitted[best_off:best_off + frame_h, :]
    return crop, best_off


def composite(source_bgr, plate_bgr, alpha_u8):
    """Source pixels where the matte is solid; straight alpha blend only at the edge."""
    a = (alpha_u8.astype(np.float32) / 255.0)[..., None]
    blended = source_bgr.astype(np.float32) * a + plate_bgr.astype(np.float32) * (1 - a)
    out = np.clip(blended + 0.5, 0, 255).astype(np.uint8)
    solid = alpha_u8 >= SOLID_ALPHA
    out[solid] = source_bgr[solid]
    return out


# ------------------------------------------------------------- media + model --

def load_rvm_model_path():
    """Reuse virtual-bg's model cache/download by lifting rvm_model() out of matte_full.py.

    matte_full.py runs a whole-clip job at import time, so it cannot be imported;
    the function is extracted from its AST and executed in isolation."""
    if not VIRTUAL_BG_MATTE.is_file():
        sys.exit(f"missing {VIRTUAL_BG_MATTE}; cannot reuse its RVM model setup")
    tree = ast.parse(VIRTUAL_BG_MATTE.read_text())
    wanted = [n for n in tree.body if isinstance(n, (ast.Import, ast.ImportFrom))
              or (isinstance(n, ast.FunctionDef) and n.name == "rvm_model")]
    scope = {}
    exec(compile(ast.Module(body=wanted, type_ignores=[]), str(VIRTUAL_BG_MATTE), "exec"), scope)
    return scope["rvm_model"]()


def probe(path):
    cap = cv2.VideoCapture(str(path))
    if not cap.isOpened():
        sys.exit(f"cannot open {path}")
    info = dict(fps=cap.get(cv2.CAP_PROP_FPS), w=int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)),
                h=int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT)), frames=int(cap.get(cv2.CAP_PROP_FRAME_COUNT)))
    cap.release()
    return info


def read_frames(path, first, last):
    """Yield (index, frame) for first <= index < last."""
    cap = cv2.VideoCapture(str(path))
    cap.set(cv2.CAP_PROP_POS_FRAMES, first)
    for i in range(first, last):
        ok, frame = cap.read()
        if not ok:
            break
        yield i, frame
    cap.release()


def matte_window(src, first, last, warmup, downsample):
    """Alpha (uint8) for each frame in [first, last), RVM state warmed on earlier frames."""
    import onnxruntime as ort
    sess = ort.InferenceSession(load_rvm_model_path(), providers=["CPUExecutionProvider"])
    rec = [np.zeros((1, 1, 1, 1), np.float32)] * 4
    dsr = np.array([downsample], np.float32)
    alphas = []
    for i, frame in read_frames(src, max(0, first - warmup), last):
        s = (cv2.cvtColor(frame, cv2.COLOR_BGR2RGB).astype(np.float32) / 255.0).transpose(2, 0, 1)[None]
        _, pha, *rec = sess.run([], {"src": s, "r1i": rec[0], "r2i": rec[1], "r3i": rec[2],
                                     "r4i": rec[3], "downsample_ratio": dsr})
        if i >= first:
            alphas.append((np.clip(pha[0, 0], 0, 1) * 255 + 0.5).astype(np.uint8))
    return alphas


class PlateSource:
    """A still image or a looping video, cropped to one fixed offset for the whole window."""

    def __init__(self, path, w, h, visible_mask, blur_sigma):
        self.w, self.h, self.blur = w, h, blur_sigma
        img = cv2.imread(str(path))
        self.video = None
        if img is None:
            self.video = cv2.VideoCapture(str(path))
            ok, img = self.video.read()
            if not ok:
                sys.exit(f"cannot read plate {path}")
        self.still, self.offset = pick_plate_crop(img, w, h, visible_mask)
        self.offset_axis = "x" if img.shape[1] / img.shape[0] > w / h else "y"

    def frame(self):
        if self.video is None:
            frame = self.still
        else:
            ok, raw = self.video.read()
            if not ok:
                self.video.set(cv2.CAP_PROP_POS_FRAMES, 0)
                ok, raw = self.video.read()
            frame = self._slide(raw)
        return cv2.GaussianBlur(frame, (0, 0), self.blur) if self.blur else frame

    def _slide(self, raw):
        ph, pw = raw.shape[:2]
        scale = max(self.w / pw, self.h / ph)
        fitted = cv2.resize(raw, (max(self.w, round(pw * scale)), max(self.h, round(ph * scale))))
        return (fitted[:, self.offset:self.offset + self.w] if self.offset_axis == "x"
                else fitted[self.offset:self.offset + self.h, :])


def start_encoder(out_tmp, w, h, fps):
    return subprocess.Popen(
        ["ffmpeg", "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "bgr24", "-s", f"{w}x{h}",
         "-r", f"{fps:.6f}", "-i", "-", "-c:v", "libx264", "-preset", "medium", "-crf", "12",
         "-pix_fmt", "yuv420p", str(out_tmp)], stdin=subprocess.PIPE)


def render(src, plate_arg, out_path, info, first, last, alphas, blur_sigma, visible_mask):
    plate = PlateSource(plate_arg, info["w"], info["h"], visible_mask, blur_sigma)
    video_tmp = Path(str(out_path) + ".video.mp4")
    enc = start_encoder(video_tmp, info["w"], info["h"], info["fps"])
    plates_seen = {}
    for i, frame in read_frames(src, 0, info["frames"]):
        if first <= i < last:
            bg = plate.frame()
            plates_seen[i] = bg
            frame = composite(frame, bg, alphas[i - first])
        enc.stdin.write(frame.tobytes())
    enc.stdin.close()
    if enc.wait() != 0:
        sys.exit("ffmpeg video encode failed")
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(video_tmp), "-i", str(src),
                    "-map", "0:v:0", "-map", "1:a:0?", "-c:v", "copy", "-c:a", "copy",
                    "-movflags", "+faststart", str(out_path)], check=True)
    video_tmp.unlink()
    return plate, plates_seen


# ------------------------------------------------------------------ the gate --

def detect_face(gray_full, cascade, last_box):
    small = cv2.resize(gray_full, None, fx=0.5, fy=0.5)
    faces = cascade.detectMultiScale(small, scaleFactor=1.1, minNeighbors=5, minSize=(80, 80))
    if len(faces) == 0:
        return last_box
    x, y, w, h = max(faces, key=lambda f: f[2] * f[3]) * 2
    return (x, y, w, h)


def face_region_mask(shape, box, subject_mask):
    """Interior of the detected face box (central 70%), restricted to the subject."""
    m = np.zeros(shape, bool)
    x, y, w, h = box
    m[y + int(h * .15):y + int(h * .85), x + int(w * .15):x + int(w * .85)] = True
    return m & subject_mask


def run_gate(src, out_path, first, last, alphas, plates_seen):
    cascade = cv2.CascadeClassifier(str(Path(cv2.data.haarcascades) / "haarcascade_frontalface_default.xml"))
    series = {(n, k): ([], []) for n in ('hand', 'face') for k in ('incl', 'solid')}
    halos, solid_share, translucent = [], [], []
    last_face, face_found, prev_gray = None, 0, None
    src_frames = read_frames(src, max(0, first - 1), last)
    out_frames = read_frames(out_path, max(0, first - 1), last)
    for (i, s), (j, o) in zip(src_frames, out_frames):
        gs = cv2.cvtColor(s, cv2.COLOR_BGR2GRAY)
        if i < first:
            prev_gray = gs
            continue
        alpha = alphas[i - first]
        subject = alpha >= 128
        go = cv2.cvtColor(o, cv2.COLOR_BGR2GRAY)
        box = detect_face(gs, cascade, last_face)
        face_found += box is not None and box is not last_face
        last_face = box
        face_mask = face_region_mask(gs.shape, box, subject) if box else np.zeros_like(subject)
        hands = motion_mask(prev_gray, gs, subject) & ~cv2.dilate(face_mask.astype(np.uint8), np.ones((41, 41))).astype(bool)
        solid = alpha >= SOLID_ALPHA
        for name, region in (("hand", hands), ("face", face_mask)):
            for kind, mask in (("incl", region), ("solid", region & solid)):
                series[(name, kind)][0].append(laplacian_variance(gs, mask))
                series[(name, kind)][1].append(laplacian_variance(go, mask))
        solid_share.append(float((hands & solid).sum() / max(1, hands.sum())))
        translucent.append(translucent_interior_share(alpha))
        halos.append(halo_fraction(o, s, plates_seen[i], alpha))
        prev_gray = gs
    def summarise(name):
        incl = detail_ratio(*series[(name, "incl")])
        solid = detail_ratio(*series[(name, "solid")])
        gated = [r for r in (incl[0], solid[0]) if r is not None]
        return dict(detail_ratio=min(gated) if gated else None,
                    worst_frame_ratio=min([r for r in (incl[1], solid[1]) if r is not None], default=None),
                    frames_measured=incl[2],
                    detail_ratio_all_region_pixels=incl[0], detail_ratio_solid_pixels_only=solid[0])
    moving, face = summarise("hand"), summarise("face")
    face["face_detected"] = face_found > 0
    moving["solid_alpha_share_of_moving_pixels"] = float(np.mean(solid_share))
    return dict(
        moving_region=moving, face_region=face,
        halo=dict(mean_fringe_fraction=float(np.mean(halos)), max_fringe_fraction=float(np.max(halos)),
                  warn=bool(np.mean(halos) > HALO_WARN_FRACTION), note="informational, not part of pass/fail"),
        matte_integrity=dict(mean_translucent_interior_share=float(np.mean(translucent)),
                             max_translucent_interior_share=float(np.max(translucent)),
                             limit=TRANSLUCENT_MAX),
        frames_in_window=last - first)


def fmt(r):
    return "n/a (region not measurable)" if r is None else f"{r * 100:.1f}%"


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("source"); ap.add_argument("plate"); ap.add_argument("out")
    ap.add_argument("--start", type=float, required=True)
    ap.add_argument("--end", type=float, required=True)
    ap.add_argument("--blur-plate", nargs="?", const=14.0, type=float, default=0.0, metavar="SIGMA",
                    help="Gaussian-blur the plate (default sigma 14 when the flag is given)")
    ap.add_argument("--downsample", type=float, default=0.25,
                    help="RVM downsample_ratio; raise before reaching for any smoothing")
    a = ap.parse_args(argv)
    if not 0 <= a.start < a.end:
        sys.exit("need 0 <= --start < --end")

    info = probe(a.source)
    first, last = int(round(a.start * info["fps"])), min(info["frames"], int(round(a.end * info["fps"])))
    if last <= first:
        sys.exit("window is empty for this clip")
    print(f"source {info['w']}x{info['h']} {info['fps']:.3f}fps, window frames {first}-{last} ({a.start}s-{a.end}s)")

    print("matting window (RVM, no temporal smoothing)...", flush=True)
    alphas = matte_window(a.source, first, last, WARMUP_FRAMES, a.downsample)
    union = np.max(np.stack(alphas), axis=0)
    visible = union < 26
    print("plate visibility by height band (share of band the plate can show):")
    for band, share in band_visibility(union).items():
        print(f"  {band:>8}  {share:5.0%}")

    out = Path(a.out)
    work = out.with_name(out.stem + "_WORKING" + out.suffix)
    plate, plates_seen = render(a.source, a.plate, work, info, first, last, alphas, a.blur_plate, visible)
    print(f"plate offset {plate.offset}px along {plate.offset_axis}")

    print("measuring the written file against the source...", flush=True)
    res = run_gate(a.source, work, first, last, alphas, plates_seen)
    hand, face = res["moving_region"]["detail_ratio"], res["face_region"]["detail_ratio"]
    passed = verdict(hand, face, res["matte_integrity"]["max_translucent_interior_share"])
    final = out if passed else out.with_name(out.stem + "_FAILED" + out.suffix)
    work.replace(final)

    res.update(gate=GATE, passed=passed, output=str(final), source=a.source, plate=a.plate,
               window=[a.start, a.end], downsample_ratio=a.downsample, blur_plate=a.blur_plate,
               temporal_smoothing="none",
               measurement="Laplacian variance of the decoded output vs the source, same pixels, every window frame")
    Path(str(out) + ".gate.json").write_text(json.dumps(res, indent=2))

    print(f"moving region (hands): {fmt(hand)} of source detail (worst frame {fmt(res['moving_region']['worst_frame_ratio'])}, "
          f"{res['moving_region']['frames_measured']} frames)\n"
          f"   all region pixels {fmt(res['moving_region']['detail_ratio_all_region_pixels'])}, solid-alpha pixels only "
          f"{fmt(res['moving_region']['detail_ratio_solid_pixels_only'])}, solid share of moving pixels "
          f"{res['moving_region']['solid_alpha_share_of_moving_pixels']:.0%}")
    print(f"face region:           {fmt(face)} of source detail (worst frame {fmt(res['face_region']['worst_frame_ratio'])}, "
          f"{res['face_region']['frames_measured']} frames, face detected: {res['face_region']['face_detected']})\n"
          f"   all region pixels {fmt(res['face_region']['detail_ratio_all_region_pixels'])}, solid-alpha pixels only "
          f"{fmt(res['face_region']['detail_ratio_solid_pixels_only'])}")
    h = res["halo"]
    print(f"halo fringe at matte edge: mean {h['mean_fringe_fraction']:.1%}, max {h['max_fringe_fraction']:.1%}"
          f"{'  WARN: bright rim' if h['warn'] else ''}")
    m = res["matte_integrity"]
    print(f"matte integrity: see-through share of subject interior mean {m['mean_translucent_interior_share']:.2%}, "
          f"worst frame {m['max_translucent_interior_share']:.2%} (limit {m['limit']:.0%})")
    if passed:
        print(f"GATE PASSED (>= {GATE:.0%} on both, matte solid) -> {final}")
        return 0
    print(f"{FAIL_MESSAGE}\n(file kept for inspection only: {final})")
    return 2


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
"""Verify a rendered cut before anyone sees it.

Two defects survive every automated pipeline and both get flagged by viewers:
a word repeated across a join, and a clause that starts or ends mid-thought.
A whole-file transcript hides both — it condenses and smooths exactly the
region you need to inspect. So this transcribes short windows aligned to each
seam instead.

What is mechanical is decided here. Clause completeness needs judgement, so the
seam text is surfaced for the agent to read rather than guessed at.

    python3 scripts/verify.py --studio <footage>/studio
    python3 scripts/verify.py --studio ... --window 3.0
"""

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from transcribe import (NON_LATIN, extract_audio, find_model, normalize,  # noqa: E402
                        read_profile, run_whisper)

POP_MARGIN_DB = 3.0        # seam louder than both neighbours by this => suspect
DRIFT_LIMIT = 0.15         # seconds


def sh(cmd):
    return subprocess.run(cmd, capture_output=True, text=True, errors="replace")


def probe_duration(path):
    out = sh(["ffprobe", "-v", "error", "-show_entries", "format=duration",
              "-of", "default=nw=1:nk=1", str(path)]).stdout.strip()
    try:
        return float(out)
    except ValueError:
        return 0.0


def peak_db(path, start, dur):
    """max_volume in a window, in dBFS. Returns None when silent/unmeasurable."""
    r = sh(["ffmpeg", "-hide_banner", "-nostats", "-ss", f"{max(0, start):.3f}",
            "-t", f"{dur:.3f}", "-i", str(path), "-af", "volumedetect",
            "-f", "null", "-"])
    m = re.search(r"max_volume:\s*(-?[\d.]+) dB", r.stderr)
    return float(m.group(1)) if m else None


def norm_token(t):
    return re.sub(r"[^\w؀-ۿऀ-ॿ]+", "", t.lower())


def repeated_runs(tokens, max_n=None):
    """Find adjacent duplicated n-grams: 'so so', 'this tool this tool'.

    Tokens may be single words (Latin scripts) or whole phrases (segment-level
    output), so split on whitespace first — otherwise a phrase collapses into
    one opaque string and only exact whole-phrase repeats are ever found."""
    words = []
    for t in tokens:
        for part in str(t).split():
            n = norm_token(part)
            if n:
                words.append(n)
    # A repeated span can be a whole sentence, not just a stutter, so the
    # n-gram width has to scale with the window rather than sit at a fixed 4.
    if max_n is None:
        max_n = max(1, min(15, len(words) // 2))

    hits = []
    for n in range(1, max_n + 1):
        i = 0
        while i + 2 * n <= len(words):
            a, b = words[i:i + n], words[i + n:i + 2 * n]
            if a == b and all(len(x) > 1 for x in a):
                hits.append(" ".join(a))
                i += n
            else:
                i += 1
    hits = sorted(set(hits), key=lambda h: -len(h.split()))
    kept = []
    for h in hits:
        if not any(h in k for k in kept):
            kept.append(h)
    return kept


def transcribe_window(video, start, dur, model, lang, workdir, idx):
    workdir.mkdir(parents=True, exist_ok=True)
    clip = workdir / f"seam_{idx:03d}.mp4"
    wav = workdir / f"seam_{idx:03d}.wav"
    sh(["ffmpeg", "-y", "-loglevel", "error", "-ss", f"{max(0, start):.3f}",
        "-t", f"{dur:.3f}", "-i", str(video), "-c", "copy", str(clip)])
    if not clip.is_file() or clip.stat().st_size == 0:
        sh(["ffmpeg", "-y", "-loglevel", "error", "-ss", f"{max(0, start):.3f}",
            "-t", f"{dur:.3f}", "-i", str(video), str(clip)])
    extract_audio(clip, wav)
    word_level = lang.lower().split("-")[0] not in NON_LATIN
    raw = run_whisper(wav, model, lang, workdir / f"seam_{idx:03d}",
                      translate=False, word_level=word_level)
    return normalize(raw)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--studio", default="studio")
    ap.add_argument("--video", default=None, help="defaults to the rendered cut")
    ap.add_argument("--window", type=float, default=3.0,
                    help="seconds either side of each seam")
    ap.add_argument("--frames", action="store_true", default=True)
    args = ap.parse_args()

    studio = Path(args.studio)
    tl_path = studio / "timeline.json"
    if not tl_path.is_file():
        print(f"error: no timeline.json in {studio} — run render.py first", file=sys.stderr)
        return 1
    tl = json.loads(tl_path.read_text())

    video = Path(args.video) if args.video else Path(tl["output"])
    if not video.is_file():
        print(f"error: rendered video not found: {video}", file=sys.stderr)
        return 1

    # Seam positions only describe the render that produced them. Verifying a
    # different file against them silently checks the wrong timestamps and
    # invents problems that are not there.
    recorded = Path(tl.get("output", "")).resolve()
    if recorded and video.resolve() != recorded:
        print(f"error: {video.name} does not match the timeline, which describes "
              f"{recorded.name}.\n"
              f"       Re-run render.py for this video, or pass its own studio dir.",
              file=sys.stderr)
        return 1

    prof = read_profile(studio)
    lang = prof.get("language") or "en"
    model = find_model((prof.get("transcription") or {}).get("model") or "large-v3-turbo")
    if not model:
        print("error: whisper model not found — run scripts/scan.py", file=sys.stderr)
        return 1

    vdir = studio / "verify"
    vdir.mkdir(parents=True, exist_ok=True)
    work = vdir / ".work"

    problems, notes, seam_reports = [], [], []

    # ---- duration ----
    actual = probe_duration(video)
    predicted = tl.get("predicted_duration", 0)
    drift = abs(actual - predicted)
    if drift > DRIFT_LIMIT:
        problems.append(f"duration drift {drift:.3f}s (actual {actual:.2f}s vs predicted {predicted:.2f}s)")

    seams = tl.get("seams") or []
    print(f"verifying {video.name} — {actual:.1f}s, {len(seams)} seam(s), language {lang}\n")

    for i, t in enumerate(seams):
        start = max(0.0, t - args.window)
        dur = min(args.window * 2, actual - start)
        words = transcribe_window(video, start, dur, model, lang, work, i)
        text = " ".join(w["text"] for w in words).strip()
        dupes = repeated_runs([w["text"] for w in words])

        # audio discontinuity right at the join
        seam_pk = peak_db(video, t - 0.03, 0.06)
        pre_pk = peak_db(video, t - 0.25, 0.20)
        post_pk = peak_db(video, t + 0.05, 0.20)
        pop = (seam_pk is not None and pre_pk is not None and post_pk is not None
               and seam_pk > pre_pk + POP_MARGIN_DB and seam_pk > post_pk + POP_MARGIN_DB)

        frame = None
        if args.frames:
            frame = vdir / f"seam_{i:03d}_{t:.2f}s.png"
            sh(["ffmpeg", "-y", "-loglevel", "error", "-ss", f"{t:.3f}",
                "-i", str(video), "-frames:v", "1", str(frame)])

        rep = {
            "seam": i, "at": round(t, 3),
            "text": text,
            "repeated": dupes,
            "audio": {"seam_db": seam_pk, "before_db": pre_pk, "after_db": post_pk, "pop": pop},
            "frame": str(frame) if frame and frame.is_file() else None,
        }
        seam_reports.append(rep)

        flag = []
        if dupes:
            flag.append(f"REPEATED: {', '.join(dupes)}")
            problems.append(f"seam {i} at {t:.2f}s repeats: {', '.join(dupes)}")
        if pop:
            flag.append(f"POSSIBLE POP ({seam_pk:.1f} vs {pre_pk:.1f}/{post_pk:.1f} dB)")
            problems.append(f"seam {i} at {t:.2f}s may pop")

        print(f"seam {i} @ {t:7.2f}s   {'  '.join(flag) if flag else 'clean'}")
        print(f"  {text[:150]}")
        print()

    report = {
        "video": str(video), "duration": round(actual, 2),
        "predicted_duration": predicted, "drift": round(drift, 3),
        "seams": seam_reports, "problems": problems,
    }
    (vdir / "report.json").write_text(json.dumps(report, indent=2, ensure_ascii=False))

    if work.exists():
        import shutil
        shutil.rmtree(work, ignore_errors=True)

    print("─" * 60)
    if problems:
        print(f"{len(problems)} mechanical problem(s):")
        for p in problems:
            print(f"  · {p}")
    else:
        print("no mechanical problems found")

    print("\nStill needs your judgement — read each seam's text above and check:")
    print("  · does every block start and end on a complete thought?")
    print("  · did dropping an item leave a stale reference (\"fourth\" on item three)?")
    print("  · look at the seam frames in", vdir)
    print(f"\nreport -> {vdir / 'report.json'}")
    return 2 if problems else 0


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
"""Word-level transcription via whisper.cpp, cached per source.

Language is always pinned explicitly. Auto-detect silently *translates* some
languages instead of transcribing them, which corrupts every downstream
timestamp — that failure is why this script refuses to run without a language.

    python3 scripts/transcribe.py take1.mp4 take2.mp4 --studio <footage>/studio
    python3 scripts/transcribe.py take1.mp4 --lang ur --translate
"""

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

# whisper.cpp's -ml 1 (one token per segment) splits multi-byte UTF-8
# characters mid-sequence on non-Latin scripts, producing corrupt JSON and
# unusable subword fragments. For these languages we take segment-level
# output and derive cut boundaries from silence detection instead, which is
# the more reliable clock anyway.
NON_LATIN = {"ur", "hi", "bn", "pa", "ta", "te", "mr", "gu", "kn", "ml",
             "fa", "ar", "he", "ru", "uk", "el", "zh", "ja", "ko", "th", "my", "am"}

# Turbo models are distilled for transcription and have no translation
# capability at all — asking one to translate silently returns the SOURCE
# language, which then flows into captions as untranslated text. Verified
# against large-v3-turbo: -tr returned Urdu, medium returned English.
TRANSLATION_CAPABLE = ("large-v3", "large-v2", "large", "medium", "small", "base")

MODEL_DIRS = [
    Path.home() / ".cache/whisper",
    Path.home() / ".cache/hyperframes/whisper/models",
    Path.home() / ".local/share/whisper",
    Path("/opt/homebrew/share/whisper-cpp"),
]


def die(msg, code=1):
    print(f"error: {msg}", file=sys.stderr)
    sys.exit(code)


def translation_model(preferred):
    """Best available model that can actually translate."""
    for key in ("large-v3", "medium", "small", "base"):
        if key in str(preferred) and "turbo" not in str(preferred):
            return find_model(preferred)
    for key in ("large-v3", "medium", "small", "base"):
        m = find_model(key)
        if m:
            return m
    return None


def find_model(name):
    """Accept a bare key (large-v3-turbo), a filename, or an absolute path."""
    p = Path(name).expanduser()
    if p.is_file():
        return p
    fname = name if name.startswith("ggml-") else f"ggml-{name}.bin"
    if not fname.endswith(".bin"):
        fname += ".bin"
    for d in MODEL_DIRS:
        cand = d / fname
        if cand.is_file():
            return cand
    return None


def read_profile(studio):
    """Tiny YAML reader for the flat subset scan.py writes."""
    f = Path(studio) / "profile.yml"
    if not f.is_file():
        return {}
    prof = {}
    stack = [(0, prof)]
    for raw in f.read_text().splitlines():
        if not raw.strip() or raw.lstrip().startswith("#"):
            continue
        indent = len(raw) - len(raw.lstrip())
        line = raw.strip()
        if line.startswith("- "):
            continue
        if ":" not in line:
            continue
        key, _, val = line.partition(":")
        key, val = key.strip(), val.strip().strip('"')
        while stack and indent < stack[-1][0]:
            stack.pop()
        target = stack[-1][1]
        if val == "":
            child = {}
            target[key] = child
            stack.append((indent + 2, child))
        else:
            if val in ("true", "false"):
                val = val == "true"
            target[key] = val
    return prof


def source_key(path):
    st = Path(path).stat()
    h = hashlib.sha1(f"{Path(path).resolve()}|{st.st_size}|{int(st.st_mtime)}".encode())
    return h.hexdigest()[:12]


def extract_audio(src, wav):
    subprocess.run(
        ["ffmpeg", "-y", "-loglevel", "error", "-i", str(src),
         "-ar", "16000", "-ac", "1", "-vn", str(wav)],
        check=True)


def run_whisper(wav, model, lang, out_stem, translate=False, word_level=True,
                max_len=None):
    cmd = ["whisper-cli", "-m", str(model), "-f", str(wav),
           "-l", lang, "-oj", "-of", str(out_stem)]
    if word_level:
        cmd += ["-ml", "1"]          # one token per segment => word-level timing
    elif max_len:
        # Phrase-level. Safe on Latin output: the -ml corruption is a
        # multi-byte splitting problem, and a translate pass from a
        # translation-capable model emits English.
        cmd += ["-ml", str(int(max_len))]
    if translate:
        cmd += ["-tr"]
    proc = subprocess.run(cmd, capture_output=True, text=True, errors="replace")
    if proc.returncode != 0:
        die(f"whisper-cli failed:\n{proc.stderr[-1500:]}")
    produced = Path(f"{out_stem}.json")
    if not produced.is_file():
        die(f"whisper produced no JSON at {produced}")
    return produced


def to_sec(ts):
    h, m, rest = ts.split(":")
    s, ms = rest.split(",")
    return int(h) * 3600 + int(m) * 60 + int(s) + int(ms) / 1000


def normalize(raw_json):
    """whisper.cpp JSON -> [{start, end, text}] on a plain seconds timeline.

    Decoded defensively: whisper.cpp can emit invalid UTF-8 when it splits a
    multi-byte character, so a strict read would crash on perfectly usable
    output."""
    data = json.loads(Path(raw_json).read_bytes().decode("utf-8", errors="replace"))
    items = []
    for seg in data.get("transcription", []):
        text = (seg.get("text") or "").strip()
        if not text:
            continue
        ts = seg.get("timestamps") or {}
        try:
            items.append({"start": to_sec(ts["from"]), "end": to_sec(ts["to"]), "text": text})
        except Exception:
            off = seg.get("offsets") or {}
            if "from" in off:
                items.append({"start": off["from"] / 1000, "end": off["to"] / 1000, "text": text})
    return items


# Whisper falls into repetition loops on long audio — it will emit the same
# phrase every two seconds to the end of the file. Translate passes are the
# most susceptible. Windowing avoids it because each pass is short enough to
# stay inside the model's context.
WINDOW = 25.0
OVERLAP = 1.0


def windowed(wav, model, lang, workdir, translate, total):
    """Run whisper in windows and stitch, offsetting each window's times."""
    items, cursor, idx = [], 0.0, 0
    while cursor < total:
        span = min(WINDOW, total - cursor)
        if span < 0.4:
            break
        piece = workdir / f"w{idx:03d}.wav"
        subprocess.run(
            ["ffmpeg", "-y", "-loglevel", "error", "-ss", f"{cursor:.3f}",
             "-t", f"{span:.3f}", "-i", str(wav), str(piece)], check=True)
        raw = run_whisper(piece, model, lang, workdir / f"w{idx:03d}",
                          translate=translate, word_level=False,
                          max_len=48 if translate else None)
        for it in normalize(raw):
            # Whisper can report times past the clip it was given; clamp them
            # or one bad segment swallows the next window through the dedup.
            it["start"] = min(it["start"], span) + cursor
            it["end"] = min(it["end"], span) + cursor
            if it["end"] <= it["start"]:
                continue
            if items and it["start"] < items[-1]["end"] - 0.05:
                continue
            items.append(it)
        piece.unlink(missing_ok=True)
        cursor += WINDOW - OVERLAP
        idx += 1
    return items


def looped(items, threshold=4):
    """True when one phrase repeats far more than speech plausibly would."""
    from collections import Counter
    if len(items) < 8:
        return False
    counts = Counter(i["text"].strip() for i in items if len(i["text"].strip()) > 12)
    if not counts:
        return False
    top, n = counts.most_common(1)[0]
    return n >= threshold and n / len(items) > 0.15


def transcribe_one(src, studio, model, lang, translate, force):
    # Keyed on the SOURCE language, including for translate passes. Assuming a
    # translate pass emits Latin text and can therefore take -ml 1 is wrong in
    # practice: it still returns fragmented, corrupted tokens of the source
    # script. Verified, not assumed.
    word_level = lang.lower().split("-")[0] not in NON_LATIN
    studio = Path(studio)
    cache = studio / "transcripts"
    cache.mkdir(parents=True, exist_ok=True)

    key = source_key(src)
    tag = "translate" if translate else "verbatim"
    out = cache / f"{Path(src).stem}.{key}.{tag}.json"

    if out.is_file() and not force:
        print(f"  cached   {Path(src).name} -> {out.name}")
        return out

    work = cache / f".work-{key}"
    work.mkdir(exist_ok=True)
    wav = work / "audio.wav"
    try:
        if not wav.is_file():
            extract_audio(src, wav)
        use = model
        if translate and "turbo" in Path(model).name:
            alt = translation_model(model)
            if not alt:
                die("translation needs a non-turbo model (large-v3, medium…);\n"
                    "       turbo models cannot translate and silently return the\n"
                    "       source language. None found in the model cache.")
            print(f"  note     {Path(model).name} cannot translate — "
                  f"using {Path(alt).name} for this pass")
            use = alt
        raw = run_whisper(wav, use, lang, work / tag,
                          translate=translate, word_level=word_level)
        words = normalize(raw)

        # A whole-file pass can loop; if it did, redo it in windows. Checked
        # rather than assumed, because windowing costs time and most passes
        # are fine.
        if looped(words):
            total = float(subprocess.run(
                ["ffprobe", "-v", "error", "-show_entries", "format=duration",
                 "-of", "default=nw=1:nk=1", str(wav)],
                capture_output=True, text=True, errors="replace").stdout.strip() or 0)
            print(f"  note     whole-file pass looped — re-running in "
                  f"{WINDOW:.0f}s windows")
            words = windowed(wav, use, lang, work, translate, total)
            word_level = False
        out.write_text(json.dumps({
            "source": str(Path(src).resolve()),
            "language": lang,
            "mode": tag,
            "model": Path(use).name,
            "granularity": "word" if word_level else "segment",
            "words": words,
        }, indent=2))
        gran = "word" if word_level else "segment"
        print(f"  ok       {Path(src).name} -> {out.name}  ({len(words)} {gran}s)")
    finally:
        shutil.rmtree(work, ignore_errors=True)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("sources", nargs="+")
    ap.add_argument("--studio", default="studio", help="studio directory")
    ap.add_argument("--lang", help="ISO language code; overrides profile.yml")
    ap.add_argument("--model", help="model key, filename or path; overrides profile.yml")
    ap.add_argument("--translate", action="store_true",
                    help="additionally produce an English translation pass for captions")
    ap.add_argument("--force", action="store_true", help="ignore cache")
    args = ap.parse_args()

    if not shutil.which("whisper-cli"):
        die("whisper-cli not found — brew install whisper-cpp")
    if not shutil.which("ffmpeg"):
        die("ffmpeg not found — brew install ffmpeg")

    prof = read_profile(args.studio)
    lang = args.lang or prof.get("language")
    if not lang:
        die("no language set. Pass --lang or run scripts/scan.py first.\n"
            "       Auto-detect is deliberately unsupported: it silently translates\n"
            "       some languages, which corrupts every downstream timestamp.")

    model_key = args.model or (prof.get("transcription") or {}).get("model") or "large-v3-turbo"
    model = find_model(model_key)
    if not model:
        die(f"model {model_key!r} not found in any known cache directory.\n"
            f"       Looked in: {', '.join(str(d) for d in MODEL_DIRS)}")

    print(f"language {lang} · model {model.name}")
    for src in args.sources:
        if not Path(src).is_file():
            die(f"no such file: {src}")
        transcribe_one(src, args.studio, model, lang, translate=False, force=args.force)
        if args.translate or prof.get("translate_captions") is True:
            transcribe_one(src, args.studio, model, lang, translate=True, force=args.force)
    return 0


if __name__ == "__main__":
    sys.exit(main())

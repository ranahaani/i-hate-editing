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

MODEL_DIRS = [
    Path.home() / ".cache/whisper",
    Path.home() / ".cache/hyperframes/whisper/models",
    Path.home() / ".local/share/whisper",
    Path("/opt/homebrew/share/whisper-cpp"),
]


def die(msg, code=1):
    print(f"error: {msg}", file=sys.stderr)
    sys.exit(code)


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


def run_whisper(wav, model, lang, out_stem, translate=False, word_level=True):
    cmd = ["whisper-cli", "-m", str(model), "-f", str(wav),
           "-l", lang, "-oj", "-of", str(out_stem)]
    if word_level:
        cmd += ["-ml", "1"]          # one token per segment => word-level timing
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


def transcribe_one(src, studio, model, lang, translate, force):
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
        raw = run_whisper(wav, model, lang, work / tag,
                          translate=translate, word_level=word_level)
        words = normalize(raw)
        out.write_text(json.dumps({
            "source": str(Path(src).resolve()),
            "language": lang,
            "mode": tag,
            "model": Path(model).name,
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

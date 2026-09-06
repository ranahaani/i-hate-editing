#!/usr/bin/env python3
"""Capability scan + first-run setup for i-hate-editing.

Detects what the machine already has, picks a Whisper model from language and
hardware, and writes profile.yml. Standard library only — this runs before
anything is installed.

    python3 scripts/scan.py                  # interactive setup
    python3 scripts/scan.py --json           # machine-readable scan, no prompts
    python3 scripts/scan.py --footage <dir>  # scaffold alongside this footage
"""

import argparse
import json
import os
import platform
import shutil
import subprocess
import sys
from pathlib import Path

# Language groups drive model choice. Low-resource languages need the full
# large model; anything smaller drifts badly enough to break cut timing.
MAJOR = {"en", "es", "fr", "de", "it", "pt", "nl", "ru", "ja", "zh", "ko"}
LOW_RESOURCE = {"ur", "hi", "bn", "pa", "ta", "te", "mr", "fa", "ar", "sw", "vi", "th", "id"}

MODELS = {
    "large-v3":       ("ggml-large-v3.bin",       "3.1 GB"),
    "large-v3-turbo": ("ggml-large-v3-turbo.bin", "1.6 GB"),
    "medium":         ("ggml-medium.bin",         "1.5 GB"),
    "medium.en":      ("ggml-medium.en.bin",      "1.5 GB"),
    "small":          ("ggml-small.bin",          "488 MB"),
    "small.en":       ("ggml-small.en.bin",       "488 MB"),
}

TOOLS = [
    ("ffmpeg",      "brew install ffmpeg",       True),
    ("ffprobe",     "brew install ffmpeg",       True),
    ("whisper-cli", "brew install whisper-cpp",  True),
    ("node",        "brew install node",         True),
    ("npm",         "brew install node",         True),
    ("yt-dlp",      "brew install yt-dlp",       False),
]


def which(name):
    return shutil.which(name)


def version_of(tool):
    try:
        out = subprocess.run([tool, "-version"], capture_output=True, text=True, errors="replace", timeout=8)
        first = (out.stdout or out.stderr).splitlines()[0]
        for token in first.split():
            if token[:1].isdigit():
                return token
        return first[:40]
    except Exception:
        return ""


def node_version():
    try:
        v = subprocess.run(["node", "-v"], capture_output=True, text=True, errors="replace", timeout=8).stdout.strip()
        return v.lstrip("v")
    except Exception:
        return ""


def ffmpeg_has_text_filters():
    """Many Homebrew ffmpeg builds ship without libass/libfreetype, so the
    subtitles and drawtext filters are unavailable. I Hate Editing renders text
    through HyperFrames instead, so this is informational, not a blocker."""
    if not which("ffmpeg"):
        return None
    try:
        out = subprocess.run(["ffmpeg", "-hide_banner", "-filters"],
                             capture_output=True, text=True, errors="replace", timeout=15).stdout
        return ("subtitles" in out) or ("drawtext" in out)
    except Exception:
        return None


def detect_accel():
    sysname = platform.system()
    if sysname == "Darwin" and platform.machine() == "arm64":
        return "metal"
    if which("nvidia-smi"):
        return "cuda"
    return "cpu"


def disk_free_gb(path="."):
    try:
        return shutil.disk_usage(path).free / 1e9
    except Exception:
        return 0.0


def pick_model(lang, accel, translate=False):
    """Return (model_key, reason).

    Turbo models cannot translate — they return the source language instead —
    so a project that needs English captions from non-English speech must not
    be given one."""
    lang = (lang or "en").lower().split("-")[0]
    gpu = accel in ("metal", "cuda")

    if translate:
        if gpu:
            return "large-v3", "translation needed — turbo models cannot translate"
        return "medium", "translation needed on CPU — turbo cannot translate"

    if lang in LOW_RESOURCE:
        return "large-v3", (
            "low-resource language — smaller models drift enough to break cut "
            "timing; consider a hosted ASR key if timing still slips")
    if lang == "en":
        if gpu:
            return "large-v3-turbo", "English on GPU — best quality-to-speed"
        return "small.en", "English on CPU — fast enough to stay interactive"
    if lang in MAJOR:
        if gpu:
            return "large-v3-turbo", "major language on GPU"
        return "medium", "major language on CPU — expect slow passes on long takes"
    return "large-v3", "uncommon language — use the strongest model available"


def scan():
    found, missing = {}, []
    for tool, install, required in TOOLS:
        p = which(tool)
        if p:
            v = node_version() if tool == "node" else (version_of(tool) if tool in ("ffmpeg", "ffprobe") else "")
            found[tool] = {"path": p, "version": v}
        else:
            missing.append({"tool": tool, "install": install, "required": required})

    accel = detect_accel()
    report = {
        "os": f"{platform.system()} {platform.release()}",
        "arch": platform.machine(),
        "accel": accel,
        "python": platform.python_version(),
        "disk_free_gb": round(disk_free_gb(), 1),
        "found": found,
        "missing": missing,
        "ffmpeg_text_filters": ffmpeg_has_text_filters(),
        "whisper_models_present": find_models(),
    }
    node_v = found.get("node", {}).get("version", "")
    report["node_ok"] = bool(node_v) and int(node_v.split(".")[0] or 0) >= 22
    return report


def find_models():
    roots = [
        Path.home() / ".cache/whisper",
        Path.home() / ".cache/hyperframes/whisper/models",
        Path.home() / ".local/share/whisper",
        Path("/opt/homebrew/share/whisper-cpp"),
    ]
    out = []
    for r in roots:
        if r.is_dir():
            out += [str(p) for p in r.glob("ggml-*.bin")]
    return out


def print_scan(r):
    print("\nScanning…")
    for tool, _, required in TOOLS:
        if tool in r["found"]:
            v = r["found"][tool]["version"]
            print(f"  {tool:<13} found   {v}")
        else:
            tag = "missing" if required else "missing (optional)"
            print(f"  {tool:<13} {tag}")
    if r["ffmpeg_text_filters"] is False:
        print("  note          ffmpeg has no libass — text renders via HyperFrames")
    if not r["node_ok"] and "node" in r["found"]:
        print("  warning       node 22+ required for HyperFrames")
    print(f"  hardware      {r['arch']} · {r['accel']}")
    print(f"  disk free     {r['disk_free_gb']} GB")
    if r["whisper_models_present"]:
        print(f"  whisper       {len(r['whisper_models_present'])} model(s) already cached")


def ask(prompt, options=None, default=None):
    if options:
        print(f"\n{prompt}")
        for i, o in enumerate(options, 1):
            mark = " (default)" if o == default else ""
            print(f"  {i}. {o}{mark}")
        raw = input("> ").strip()
        if not raw:
            return default
        if raw.isdigit() and 1 <= int(raw) <= len(options):
            return options[int(raw) - 1]
        return raw
    raw = input(f"\n{prompt}\n> ").strip()
    return raw or default


def yaml_dump(profile):
    """Minimal YAML writer — avoids requiring PyYAML before install."""
    lines = ["# i-hate-editing profile — the only configuration in this studio.",
             "# Everything else is a craft decision the studio makes for you.", ""]

    def emit(d, indent=0):
        pad = "  " * indent
        for k, v in d.items():
            if isinstance(v, dict):
                lines.append(f"{pad}{k}:")
                emit(v, indent + 1)
            elif isinstance(v, list):
                lines.append(f"{pad}{k}:")
                for item in v:
                    lines.append(f"{pad}  - {item}")
            elif isinstance(v, bool):
                lines.append(f"{pad}{k}: {'true' if v else 'false'}")
            elif v is None:
                lines.append(f"{pad}{k}:")
            else:
                s = str(v)
                if any(c in s for c in ":#") and not s.startswith('"'):
                    s = f'"{s}"'
                lines.append(f"{pad}{k}: {s}")

    emit(profile)
    return "\n".join(lines) + "\n"


def setup(report, footage_dir):
    print("\n" + "─" * 58)
    print("Setup — answer five questions, then nothing else is asked of you.")
    print("─" * 58)

    lang = ask("What language do you record in? (ISO code, e.g. en, ur, es)", default="en") or "en"
    lang = lang.lower().split("-")[0]

    fmt = ask("What are you making?",
              ["Short-form vertical (reels, shorts, TikTok)",
               "YouTube talking-head",
               "Both"],
              default="Short-form vertical (reels, shorts, TikTok)")

    style = ask("Editing style?",
                ["Punchy — fast cuts, dense motion, heavy sound design",
                 "Balanced — measured pacing, motion where it earns it",
                 "Restrained — minimal motion, let the talking carry it"],
                default="Punchy — fast cuts, dense motion, heavy sound design")

    brand = ask("Brand look?",
                ["Pick for me",
                 "I'll supply colours and a font"],
                default="Pick for me")

    accent, font = "#FFE300", "Archivo Black"
    if brand.startswith("I'll"):
        accent = ask("Accent colour (hex)", default="#FFE300") or "#FFE300"
        font = ask("Display font", default="Archivo Black") or "Archivo Black"

    sounds = (ask("Install the sound library? (~60 free-licensed effects) (y/n)",
                  default="y") or "y").lower().startswith("y")
    gallery = (ask("Install the local review gallery? (y/n)", default="y") or "y").lower().startswith("y")
    growth = (ask("Install comment-to-DM automation? (y/n)", default="n") or "n").lower().startswith("y")

    model, reason = pick_model(lang, report["accel"], translate=(lang != "en"))
    fname, size = MODELS[model]

    aspects = {"Short-form vertical (reels, shorts, TikTok)": ["9:16"],
               "YouTube talking-head": ["16:9"],
               "Both": ["9:16", "16:9"]}[fmt]

    profile = {
        "language": lang,
        "translate_captions": lang != "en",
        "format": fmt.split(" —")[0].split(" (")[0],
        "aspects": aspects,
        "pacing": style.split(" —")[0].lower(),
        "brand": {"accent": accent, "font": font, "caption_style": "big-keyword"},
        "transcription": {"model": model, "accel": report["accel"]},
        "optional": {"sound_library": sounds, "review_gallery": gallery,
                     "comment_to_dm": growth},
    }

    studio = Path(footage_dir) / "studio"
    for sub in ("transcripts", "composition", "assets", "verify", "out"):
        (studio / sub).mkdir(parents=True, exist_ok=True)

    (studio / "profile.yml").write_text(yaml_dump(profile))
    taste = studio / "taste.md"
    if not taste.exists():
        taste.write_text(
            "# Taste\n\n"
            "Durable feedback. Read before every edit; appended after every review.\n"
            "One dated rule per line, phrased as an instruction for next time.\n\n")

    print("\n" + "─" * 58)
    print("Plan")
    print("─" * 58)
    for m in report["missing"]:
        if m["required"] or m["tool"] == "yt-dlp":
            print(f"  install  {m['tool']:<12} {m['install']}")
    if not any(fname in p for p in report["whisper_models_present"]):
        print(f"  download {model:<12} {size} — {reason}")
    else:
        print(f"  model    {model:<12} already cached")
    print(f"  scaffold {studio}")
    if sounds:
        print("  install  sound library   python3 scripts/sfx_library.py install")
    if gallery:
        print("  install  review gallery")
    if growth:
        print("  install  comment-to-DM (Meta Graph API)")

    print(f"\nWrote {studio / 'profile.yml'}")
    print(f"Drop your takes in {footage_dir} and say \"edit these\".\n")
    return profile


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", action="store_true", help="scan only, machine-readable")
    ap.add_argument("--footage", default=".", help="footage directory to scaffold beside")
    args = ap.parse_args()

    report = scan()

    if args.json:
        print(json.dumps(report, indent=2))
        return 0

    print_scan(report)

    blocking = [m for m in report["missing"] if m["required"]]
    if blocking:
        print("\nMissing required tools — install these first:")
        for m in blocking:
            print(f"  {m['install']}")
        print("\nContinuing setup anyway; nothing runs until they exist.")

    if not sys.stdin.isatty():
        print("\nNot a terminal — run without --json in an interactive shell to set up.")
        return 0

    setup(report, args.footage)
    return 0


if __name__ == "__main__":
    sys.exit(main())

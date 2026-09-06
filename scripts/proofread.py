#!/usr/bin/env python3
"""Turn a raw caption pass into caption copy.

A machine transcription is a draft. Left alone it ships merged sentences,
stray punctuation, fragments cut mid-clause, and — most damagingly — mangled
product names, which are exactly the words the audience is watching for.

Two passes:

**Deterministic** always runs and needs nothing installed: known names are
restored, punctuation artefacts stripped, over-long chunks flagged, unreadably
short ones merged. It cannot fix meaning, so on its own it does not mark the
captions proofread.

**Model** is optional and provider-agnostic: give it any command that reads a
prompt on stdin and writes text on stdout. No API key lives in this skill, and
nothing is sent anywhere unless you ask for it.

    python3 scripts/proofread.py check  --studio <studio>
    python3 scripts/proofread.py fix    --studio <studio> --name "Claude" --name "gnhf"
    python3 scripts/proofread.py fix    --studio <studio> --llm "ollama run llama3.2"
    python3 scripts/proofread.py fix    --studio <studio> --accept   # I rewrote it myself
"""

import argparse
import json
import difflib
import re
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from transcribe import read_profile  # noqa: E402

MAX_WORDS = 4
MIN_ON_SCREEN = 0.40

# Shapes that only survive from an untouched machine pass.
ARTEFACTS = [
    (re.compile(r'["""»«]'), "stray quotation mark"),
    (re.compile(r"\s+[,.;:]"), "space before punctuation"),
    (re.compile(r"[.!?]\s*\w"), "two sentences in one chunk"),
    (re.compile(r"^\s*[,.;:]"), "leading punctuation"),
    (re.compile(r"\b(\w+)\s+\1\b", re.I), "word repeated"),
]

PROMPT = """You are proofreading burned-in captions for a short vertical video.

The speaker's words, transcribed and machine-translated, are below as numbered
chunks. Each chunk appears on screen for the duration shown.

Rewrite each chunk as caption copy:
- Keep the speaker's meaning and their voice. Do not add claims.
- Two to three words per chunk, four at the absolute most.
- No stray punctuation. No chunk containing two sentences.
- Fix product and tool names exactly: {names}
- Plain uppercase text only. No quotes around chunks.
- Return EXACTLY {n} lines, numbered the same way, nothing else.

{chunks}"""


def load(studio):
    p = Path(studio) / "captions.json"
    if not p.is_file():
        print("error: no captions.json — run captions.py first", file=sys.stderr)
        sys.exit(1)
    return p, json.loads(p.read_text())


def known_names(profile, extra):
    names = list(extra or [])
    for n in (profile.get("names") or []):
        names.append(str(n))
    return names


SIMILAR = 0.72          # below this it is a different word, not a mis-hearing


def _close(a, b):
    """Is `a` a plausible mis-hearing of `b`?

    Fuzzy, because ASR substitutes sounds rather than dropping characters:
    'cloud' for 'claude', 'curser' for 'cursor'. Guarded on the first two
    letters and on length, or ordinary words get swallowed — 'could' scores
    just as highly against 'claude' as 'cloud' does."""
    if a == b:
        return False
    if abs(len(a) - len(b)) > 2 or a[:2] != b[:2]:
        return False
    return difflib.SequenceMatcher(None, a, b).ratio() >= SIMILAR


def fix_names(text, names):
    """Restore product names ASR mangled.

    A listed name is also capitalised where it already appears correctly, so
    "the cursor blinked" becomes "the Cursor blinked" if Cursor is on the list.
    That is deliberate — you control the list, and in a video about a product
    the capitalised reading is right far more often than not."""
    out = text
    for name in names:
        squashed = re.sub(r"[^a-z0-9]", "", name.lower())
        if len(squashed) < 3:
            continue
        # letters spelled out or hyphenated: "g n h f" -> "gnhf"
        loose = r"\b" + r"[\s\-]?".join(re.escape(c) for c in squashed) + r"\b"
        out = re.sub(loose, name, out, flags=re.I)

        # phonetic near-misses, matched over the same number of words
        span = len(name.split())
        words = out.split()
        for i in range(len(words) - span + 1):
            window = " ".join(words[i:i + span])
            bare = re.sub(r"[^a-z0-9]", "", window.lower())
            if _close(bare, squashed):
                keep = re.sub(r"^[\w\s-]+", "", window)   # trailing punctuation
                words[i:i + span] = [name + keep]
                out = " ".join(words)
                words = out.split()
    return out


def tidy(text):
    t = re.sub(r'["""»«]', "", text)
    t = re.sub(r"\s+([,.;:!?])", r"\1", t)
    t = re.sub(r"^\s*[,.;:]\s*", "", t)
    t = re.sub(r"\s{2,}", " ", t)
    return t.strip()


def issues(chunks):
    found = []
    for i, c in enumerate(chunks):
        t = c.get("text", "")
        for pat, label in ARTEFACTS:
            if pat.search(t):
                found.append((i, label, t))
                break
        else:
            if len(t.split()) > MAX_WORDS:
                found.append((i, f"{len(t.split())} words (ceiling {MAX_WORDS})", t))
            elif c.get("duration", 1) < MIN_ON_SCREEN:
                found.append((i, "too brief to read", t))
    return found


def run_model(cmd, chunks, names):
    body = "\n".join(f"{i + 1}. {c['text']}" for i, c in enumerate(chunks))
    prompt = PROMPT.format(names=", ".join(names) or "(none given)",
                           n=len(chunks), chunks=body)
    try:
        r = subprocess.run(cmd, shell=True, input=prompt, capture_output=True,
                           text=True, errors="replace", timeout=300)
    except subprocess.TimeoutExpired:
        print("  model timed out; keeping the deterministic pass", file=sys.stderr)
        return None
    if r.returncode != 0:
        print(f"  model failed: {r.stderr[-200:].strip()}", file=sys.stderr)
        return None

    lines = {}
    for line in (r.stdout or "").splitlines():
        m = re.match(r"\s*(\d+)[.)]\s*(.+?)\s*$", line)
        if m:
            lines[int(m.group(1))] = m.group(2).strip().strip('"')
    if len(lines) < len(chunks) * 0.8:
        print(f"  model returned {len(lines)} of {len(chunks)} lines — ignoring it",
              file=sys.stderr)
        return None
    return lines


def cmd_check(args):
    _, d = load(args.studio)
    chunks = d.get("chunks", [])
    found = issues(chunks)
    print(f"{len(chunks)} chunks · proofread flag: {d.get('proofread', False)}")
    if not found and d.get("proofread"):
        print("no artefacts; captions are marked proofread")
        return 0
    for i, label, t in found[:12]:
        print(f"  {i:3d}  {label:<28} {t[:44]!r}")
    if len(found) > 12:
        print(f"  … {len(found) - 12} more")
    print(f"\n{len(found)} chunk(s) need attention")
    if not d.get("proofread"):
        print("Captions are not marked proofread, so verification will fail.")
    return 2 if (found or not d.get("proofread")) else 0


def cmd_fix(args):
    path, d = load(args.studio)
    chunks = d.get("chunks", [])
    if not chunks:
        print("error: captions.json has no chunks", file=sys.stderr)
        return 1
    profile = read_profile(args.studio)
    names = known_names(profile, args.name)

    before = sum(1 for _ in issues(chunks))
    for c in chunks:
        c["text"] = tidy(fix_names(c["text"], names))
        for w in c.get("words", []):
            w["text"] = tidy(fix_names(w["text"], names))
    print(f"deterministic pass: {before} issue(s) -> {len(issues(chunks))}")

    used_model = False
    if args.llm:
        print(f"model pass: {args.llm}")
        rewritten = run_model(args.llm, chunks, names)
        if rewritten:
            for i, c in enumerate(chunks, start=1):
                if i in rewritten:
                    c["text"] = rewritten[i]
                    c["words"] = [{"text": w, "emphasis": False}
                                  for w in rewritten[i].split()]
            # keep one emphasis word per chunk
            for c in chunks:
                if c["words"] and not any(w["emphasis"] for w in c["words"]):
                    j = max(range(len(c["words"])),
                            key=lambda k: len(c["words"][k]["text"]))
                    c["words"][j]["emphasis"] = True
            used_model = True
            print(f"  rewrote {len(rewritten)} chunk(s)")

    remaining = issues(chunks)
    d["chunks"] = chunks
    # Only a model pass or an explicit human sign-off counts as proofread. The
    # deterministic pass cannot fix meaning, and meaning is what breaks.
    if used_model or args.accept:
        d["proofread"] = True
    path.write_text(json.dumps(d, indent=2, ensure_ascii=False))

    print(f"\n-> {path}")
    print(f"proofread: {d.get('proofread', False)}")
    if remaining:
        print(f"{len(remaining)} chunk(s) still flagged:")
        for i, label, t in remaining[:6]:
            print(f"  {i:3d}  {label:<28} {t[:44]!r}")
    if not d.get("proofread"):
        print("\nNot marked proofread. Rewrite the copy yourself and re-run with")
        print("--accept, or pass --llm to have a model do it. A machine pass is a")
        print("draft; the captions are the most-read thing on screen.")
        return 2
    return 0


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("check", help="report artefacts without changing anything")
    c.add_argument("--studio", default="studio")
    c.set_defaults(func=cmd_check)
    f = sub.add_parser("fix", help="clean up, optionally with a model")
    f.add_argument("--studio", default="studio")
    f.add_argument("--name", action="append", help="product name to restore; repeatable")
    f.add_argument("--llm", help="command reading a prompt on stdin, writing text out")
    f.add_argument("--accept", action="store_true",
                   help="you rewrote the copy yourself; mark it proofread")
    f.set_defaults(func=cmd_fix)
    args = ap.parse_args()
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())

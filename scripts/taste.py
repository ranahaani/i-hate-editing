#!/usr/bin/env python3
"""Taste memory — the loop that makes the studio better than last time.

Every correction becomes a durable instruction, grouped by area and dated, read
before every subsequent edit. This is the difference between a tool that
repeats itself and one that learns a person's preferences.

Two things are stored per entry: the **instruction** for next time, and the
**raw words** the user actually said. The instruction is a reading of the
feedback and can be wrong; keeping the original means a bad reading can be
corrected later instead of quietly hardening into a rule.

    python3 scripts/taste.py add captions "Start captions 0.08s after the word." \\
        --said "captions show early for a sec then I start speaking"
    python3 scripts/taste.py show
    python3 scripts/taste.py show --area sound
    python3 scripts/taste.py retire captions 2
"""

import argparse
import datetime as dt
import re
import sys
from pathlib import Path

AREAS = ["cutting", "pacing", "hooks", "captions", "sound", "motion",
         "framing", "proof", "delivery", "general"]

HEADER = """# Taste

Durable feedback for this project. Read before every edit; appended after every
review. Newer entries win when two rules conflict.

Each line is an instruction for next time, not a description of what happened.
Retired entries are kept, struck through, so a reversal stays visible.
"""

ENTRY = re.compile(r"^- (?P<date>\d{4}-\d{2}-\d{2}) — (?P<body>.*)$")
RETIRED = re.compile(r"^- ~~(?P<date>\d{4}-\d{2}-\d{2}) — (?P<body>.*)~~.*$")


def taste_path(studio):
    return Path(studio) / "taste.md"


def load(path):
    """-> (preamble_lines, {area: [raw_line, ...]}) preserving order."""
    if not path.is_file():
        return HEADER.strip().splitlines(), {}
    lines = path.read_text().splitlines()
    preamble, sections, cur = [], {}, None
    for ln in lines:
        if ln.startswith("## "):
            cur = ln[3:].strip().lower()
            sections.setdefault(cur, [])
            continue
        if cur is None:
            preamble.append(ln)
        elif ln.strip():
            sections[cur].append(ln)
    while preamble and not preamble[-1].strip():
        preamble.pop()
    return preamble, sections


def save(path, preamble, sections):
    out = list(preamble) + [""]
    for area in AREAS:
        entries = sections.get(area)
        if not entries:
            continue
        out += [f"## {area}", ""] + entries + [""]
    for area, entries in sections.items():          # any custom areas
        if area not in AREAS and entries:
            out += [f"## {area}", ""] + entries + [""]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(out).rstrip() + "\n")


def cmd_add(args):
    path = taste_path(args.studio)
    preamble, sections = load(path)
    area = args.area.lower()
    if area not in AREAS:
        print(f"note: '{area}' is not a standard area ({', '.join(AREAS)}) — adding anyway")
    date = args.date or dt.date.today().isoformat()

    instruction = args.instruction.strip().rstrip(".") + "."
    line = f"- {date} — {instruction}"
    if args.said:
        line += f' _("{args.said.strip()}")_'

    entries = sections.setdefault(area, [])
    if any(instruction.lower() in e.lower() for e in entries):
        print("already recorded — nothing added")
        return 0
    entries.append(line)
    save(path, preamble, sections)
    print(f"{area}: {instruction}")
    print(f"-> {path}")
    return 0


def cmd_show(args):
    path = taste_path(args.studio)
    if not path.is_file():
        print("no taste memory yet")
        return 0
    _, sections = load(path)
    areas = [args.area.lower()] if args.area else list(sections)
    shown = 0
    for area in areas:
        entries = [e for e in sections.get(area, []) if args.all or not e.startswith("- ~~")]
        if not entries:
            continue
        print(f"\n{area}")
        for i, e in enumerate(entries, 1):
            print(f"  {i:>2}. {e[2:]}")
            shown += 1
    if not shown:
        print("nothing recorded" + (f" for {args.area}" if args.area else ""))
    else:
        print()
    return 0


def cmd_retire(args):
    path = taste_path(args.studio)
    preamble, sections = load(path)
    area = args.area.lower()
    entries = sections.get(area) or []
    live = [i for i, e in enumerate(entries) if not e.startswith("- ~~")]
    if not (1 <= args.index <= len(live)):
        print(f"error: {area} has {len(live)} live entr(ies)", file=sys.stderr)
        return 1
    idx = live[args.index - 1]
    body = entries[idx][2:]
    today = dt.date.today().isoformat()
    entries[idx] = f"- ~~{body}~~ _(retired {today})_"
    save(path, preamble, sections)
    print(f"retired {area} #{args.index}: {body[:70]}")
    return 0


def cmd_brief(args):
    """Compact form for loading into context at the start of an edit."""
    path = taste_path(args.studio)
    if not path.is_file():
        print("(no taste memory)")
        return 0
    _, sections = load(path)
    any_out = False
    for area in AREAS + [a for a in sections if a not in AREAS]:
        entries = [e for e in sections.get(area, []) if not e.startswith("- ~~")]
        if not entries:
            continue
        any_out = True
        print(f"{area}:")
        for e in entries:
            m = ENTRY.match(e)
            body = m.group("body") if m else e[2:]
            body = re.sub(r'\s*_\(".*?"\)_\s*$', "", body)
            print(f"  - {body}")
    if not any_out:
        print("(no taste memory)")
    return 0


def main():
    ap = argparse.ArgumentParser(description="taste memory")
    ap.add_argument("--studio", default="studio")
    sub = ap.add_subparsers(dest="cmd", required=True)

    a = sub.add_parser("add", help="record a correction as an instruction")
    a.add_argument("area", help=f"one of: {', '.join(AREAS)}")
    a.add_argument("instruction", help="what to do next time, imperative")
    a.add_argument("--said", help="the user's own words, kept verbatim")
    a.add_argument("--date", help="override the date (YYYY-MM-DD)")
    a.set_defaults(func=cmd_add)

    s = sub.add_parser("show", help="read the memory")
    s.add_argument("--area")
    s.add_argument("--all", action="store_true", help="include retired entries")
    s.set_defaults(func=cmd_show)

    b = sub.add_parser("brief", help="compact instructions for context loading")
    b.set_defaults(func=cmd_brief)

    r = sub.add_parser("retire", help="reverse a rule that no longer applies")
    r.add_argument("area")
    r.add_argument("index", type=int)
    r.set_defaults(func=cmd_retire)

    args = ap.parse_args()
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
"""Install the sound library described by assets/sfx-taxonomy.json.

Sounds are fetched rather than bundled: shipping audio inside the repository
would redistribute it, and that is a licence question for every single file.
Fetching records the licence per file instead.

Every downloaded file is analysed at install time, so a sound whose loud
transient sits late — and which would therefore be silent in a short window —
is known before it is ever placed in an edit.

    python3 scripts/sfx_library.py install
    python3 scripts/sfx_library.py install --library ~/.i-hate-editing/sfx
    python3 scripts/sfx_library.py status
"""

import argparse
import json
import re
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from sound import find_peak, levels  # noqa: E402

HERE = Path(__file__).resolve().parent.parent
TAXONOMY = HERE / "assets" / "sfx-taxonomy.json"
DEFAULT_LIB = Path.home() / ".i-hate-editing" / "sfx"
PER_CATEGORY = 3
UA = {"User-Agent": "Mozilla/5.0 (i-hate-editing sound library installer)"}
LICENCE = ("Mixkit Free Sound Effects Licence — free for commercial and "
           "non-commercial video, no attribution required. "
           "https://mixkit.co/license/#sfxFree")


def load_taxonomy():
    return json.loads(TAXONOMY.read_text())


def each_category(tax):
    for gname, g in tax["groups"].items():
        for cname, c in g["categories"].items():
            yield gname, cname, c


def fetch(url, timeout=30):
    return urllib.request.urlopen(
        urllib.request.Request(url, headers=UA), timeout=timeout).read()


def discover(slug):
    """Preview URLs on a Mixkit category page."""
    try:
        html = fetch(f"https://mixkit.co/free-sound-effects/{slug}/").decode(
            "utf-8", errors="replace")
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError):
        return []
    urls = re.findall(
        r'https://assets\.mixkit\.co/active_storage/sfx/\d+/[\w\-.]+\.mp3', html)
    seen, out = set(), []
    for u in urls:
        if u not in seen:
            seen.add(u)
            out.append(u)
    return out


def analyse(path):
    """Peak level and where it sits — the audibility check, at install time."""
    peak_db, peak_at, total = find_peak(path, step=0.05)
    _, full = levels(path)
    early = levels(path, 0.0, min(0.6, total))[1]
    truncating = full is not None and early is not None and (full - early) > 3.0
    return {
        "duration": round(total, 3),
        "peak_db": round(full, 1) if full is not None else None,
        "peak_at": round(peak_at or 0.0, 3),
        "peak_after_600ms": bool(truncating),
    }


def cmd_install(args):
    tax = load_taxonomy()
    lib = Path(args.library).expanduser()
    lib.mkdir(parents=True, exist_ok=True)
    index_path = lib / "index.json"
    index = json.loads(index_path.read_text()) if index_path.is_file() else {}

    wanted = list(each_category(tax))
    if args.only:
        wanted = [w for w in wanted if w[1] in args.only]

    added = skipped = failed = 0
    for group, cat, spec in wanted:
        have = index.get(cat, {}).get("files", [])
        if have and not args.force:
            print(f"  {cat:<15} have {len(have)}")
            skipped += 1
            continue

        urls = discover(spec["mixkit"])
        if not urls:
            print(f"  {cat:<15} no sources found for '{spec['mixkit']}'")
            failed += 1
            continue

        out_dir = lib / cat
        out_dir.mkdir(exist_ok=True)
        files = []
        for url in urls[:PER_CATEGORY]:
            name = re.sub(r"[^\w.-]+", "-", url.rsplit("/", 1)[-1])
            dest = out_dir / name
            if not dest.is_file():
                try:
                    dest.write_bytes(fetch(url))
                except Exception as exc:
                    print(f"  {cat:<15} download failed: {str(exc)[:50]}")
                    continue
            info = analyse(dest)
            info.update({"file": str(dest), "source": url, "licence": LICENCE})
            files.append(info)

        if not files:
            failed += 1
            continue

        index[cat] = {"group": group, "when": spec["when"],
                      "volume": spec["volume"], "track": spec["track"],
                      "peak_db_target": spec["peak_db"], "files": files}
        late = sum(1 for f in files if f["peak_after_600ms"])
        note = f"  ({late} with a late peak — handled by peak alignment)" if late else ""
        print(f"  {cat:<15} {len(files)} file(s){note}")
        added += 1

    index_path.write_text(json.dumps(index, indent=2))
    print(f"\n{added} installed, {skipped} already present, {failed} unavailable")
    print(f"library: {lib}")
    if failed:
        print("Missing categories degrade gracefully — placement skips them.")
    return 0


def cmd_status(args):
    lib = Path(args.library).expanduser()
    index_path = lib / "index.json"
    if not index_path.is_file():
        print(f"no library at {lib} — run: python3 scripts/sfx_library.py install")
        return 1
    index = json.loads(index_path.read_text())
    tax = load_taxonomy()
    all_cats = [c for _, c, _ in each_category(tax)]

    print(f"{lib}\n")
    for group, g in tax["groups"].items():
        print(f"{g['title']}")
        for cat in g["categories"]:
            entry = index.get(cat)
            if entry:
                print(f"  {cat:<15} {len(entry['files'])} file(s)  · {entry['when']}")
            else:
                print(f"  {cat:<15} MISSING       · {g['categories'][cat]['when']}")
        print()
    missing = [c for c in all_cats if c not in index]
    print(f"{len(all_cats) - len(missing)}/{len(all_cats)} categories present")
    return 2 if missing else 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--library", default=str(DEFAULT_LIB))
    sub = ap.add_subparsers(dest="cmd", required=True)
    i = sub.add_parser("install")
    i.add_argument("--only", nargs="*", help="specific categories")
    i.add_argument("--force", action="store_true")
    i.set_defaults(func=cmd_install)
    st = sub.add_parser("status")
    st.set_defaults(func=cmd_status)
    args = ap.parse_args()
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())

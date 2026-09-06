#!/usr/bin/env python3
"""Fetch brand logos and interface icons for cards and proof frames.

A card that names a tool reads better with that tool's mark on it, and a brand
frame in the brand's own colour reads as designed rather than templated. Both
were previously impossible: there was no icon source at all.

Two sources, both free to use commercially:

- **Simple Icons** (CC0, public domain) — brand marks, and each one carries its
  official hex colour, so a card can theme itself to whatever it names.
- **Lucide** (ISC) — interface icons for concepts with no brand: a clock, a
  moon, a checkmark.

Fetched on demand and cached, never bundled, so the licence stays traceable.

    python3 scripts/icons.py search claude
    python3 scripts/icons.py fetch claude github cursor --studio <studio>
    python3 scripts/icons.py fetch moon --set lucide --studio <studio>
"""

import argparse
import json
import re
import sys
import urllib.error
import urllib.request
from pathlib import Path

BRAND_INDEX = "https://cdn.jsdelivr.net/npm/simple-icons@latest/data/simple-icons.json"
BRAND_SVG = "https://cdn.jsdelivr.net/npm/simple-icons@latest/icons/{slug}.svg"
LUCIDE_SVG = "https://cdn.jsdelivr.net/npm/lucide-static@latest/icons/{slug}.svg"
CACHE = Path.home() / ".i-hate-editing" / "icons"
UA = {"User-Agent": "Mozilla/5.0 (i-hate-editing icons)"}

LICENCES = {
    "simple-icons": "CC0-1.0 (public domain) — https://github.com/simple-icons/simple-icons",
    "lucide": "ISC — https://github.com/lucide-icons/lucide",
}


def get(url, timeout=25):
    return urllib.request.urlopen(
        urllib.request.Request(url, headers=UA), timeout=timeout).read()


def brand_index():
    CACHE.mkdir(parents=True, exist_ok=True)
    cached = CACHE / "simple-icons.json"
    if cached.is_file():
        try:
            return json.loads(cached.read_text())
        except Exception:
            pass
    try:
        raw = get(BRAND_INDEX).decode("utf-8", errors="replace")
    except Exception as exc:
        print(f"error: could not fetch the brand index ({str(exc)[:60]})",
              file=sys.stderr)
        return []
    cached.write_text(raw)
    return json.loads(raw)


def slugify(title):
    """Simple Icons' own slug rule, close enough for lookup."""
    s = title.lower()
    s = s.replace("+", "plus").replace(".", "dot").replace("&", "and")
    s = re.sub(r"[^a-z0-9]", "", s)
    return s


def find(index, query, exact_only=False):
    """Matches, exact first.

    `exact_only` exists because a near-match is worse than nothing: asking for
    OpenAI and silently getting OpenAI Gym puts the wrong company's mark on a
    card. Simple Icons genuinely has no plain OpenAI entry, so the honest
    answer is to say so."""
    q = query.lower().strip()
    exact, partial = [], []
    for e in index:
        title = e["title"]
        slug = e.get("slug") or slugify(title)
        names = [title.lower(), slug] + [
            a.lower() for a in (e.get("aliases", {}).get("aka") or [])]
        if q in names:
            exact.append((title, slug, e.get("hex", "")))
        elif any(q in n for n in names):
            partial.append((title, slug, e.get("hex", "")))
    return exact if exact_only else exact + partial


def cmd_search(args):
    index = brand_index()
    hits = find(index, args.query)
    if not hits:
        print(f"no brand mark for {args.query!r}")
        print("For a concept rather than a brand, try the interface set:")
        print(f"  python3 scripts/icons.py fetch {args.query} --set lucide")
        return 1
    for title, slug, hex_ in hits[:12]:
        print(f"  {title:<28} slug {slug:<24} #{hex_}")
    if len(hits) > 12:
        print(f"  … {len(hits) - 12} more")
    return 0


def fetch_one(name, which, outdir, index):
    if which == "lucide":
        slug = re.sub(r"[^a-z0-9-]", "-", name.lower())
        url, hex_, title = LUCIDE_SVG.format(slug=slug), "", name
    else:
        hits = find(index, name, exact_only=True)
        if not hits:
            near = [t for t, _, _ in find(index, name)[:3]]
            hint = f" Did you mean: {', '.join(near)}?" if near else ""
            return None, (f"no exact brand mark for {name!r}.{hint} "
                          f"Use the exact name, or --set lucide for a concept.")
        title, slug, hex_ = hits[0]
        url = BRAND_SVG.format(slug=slug)
    try:
        svg = get(url).decode("utf-8", errors="replace")
    except urllib.error.HTTPError:
        return None, f"{name!r} not found in the {which} set"
    except Exception as exc:
        return None, f"{name!r}: {str(exc)[:50]}"

    # Simple Icons ships monochrome paths; colour it so a card can use it
    # directly rather than needing a CSS filter.
    if hex_ and "fill=" not in svg.split(">")[0]:
        svg = svg.replace("<svg", f'<svg fill="#{hex_}"', 1)

    outdir.mkdir(parents=True, exist_ok=True)
    dest = outdir / f"{slug}.svg"
    dest.write_text(svg)
    return {"name": title, "slug": slug, "hex": f"#{hex_}" if hex_ else None,
            "file": str(dest), "set": which, "licence": LICENCES[which]}, None


def cmd_fetch(args):
    outdir = Path(args.studio) / "assets" / "icons"
    index = brand_index() if args.set == "simple-icons" else []
    manifest_path = outdir / "index.json"
    manifest = {}
    if manifest_path.is_file():
        try:
            manifest = json.loads(manifest_path.read_text())
        except Exception:
            pass

    ok = 0
    for name in args.names:
        entry, err = fetch_one(name, args.set, outdir, index)
        if err:
            print(f"  {err}")
            continue
        manifest[entry["slug"]] = entry
        colour = f" · {entry['hex']}" if entry["hex"] else ""
        print(f"  {entry['name']:<24} {Path(entry['file']).name}{colour}")
        ok += 1

    if ok:
        outdir.mkdir(parents=True, exist_ok=True)
        manifest_path.write_text(json.dumps(manifest, indent=2))
        print(f"\n{ok} icon(s) -> {outdir}")
        print(f"licence: {LICENCES[args.set]}")
    return 0 if ok else 1


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("search", help="look for a brand mark")
    s.add_argument("query")
    s.set_defaults(func=cmd_search)
    f = sub.add_parser("fetch", help="download marks into the studio")
    f.add_argument("names", nargs="+")
    f.add_argument("--studio", default="studio")
    f.add_argument("--set", default="simple-icons",
                   choices=["simple-icons", "lucide"],
                   help="brand marks, or interface icons for concepts")
    f.set_defaults(func=cmd_fetch)
    args = ap.parse_args()
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())

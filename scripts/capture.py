#!/usr/bin/env python3
"""Capture a real page as proof B-roll: one tall image plus target coordinates.

Deliberately *not* a scroll recording. A recorded scroll bakes in its speed and
timing permanently — it cannot be re-synced when the cut changes, cannot slow
down on the important line, and cannot be zoomed mid-scroll. Capturing the page
as a single tall image and animating it in the composition keeps scroll, zoom
and highlight frame-accurate and re-editable, in the same timeline as the face,
captions and sound.

Targets are found by TEXT, not CSS selectors. Selectors are per-site and
brittle — a mobile layout hides half of them — while text is how the beat is
actually described: "zoom to the 100k stars".

    python3 scripts/capture.py https://github.com/org/repo --studio <dir> \\
        --name repo --find "100k" --find "MIT license"
"""

import argparse
import json
import re
import sys
from pathlib import Path

VIEWPORT = (390, 844)      # vertical: reels and shorts
DPR = 3


def rank_js():
    """Score candidate elements for a text needle.

    An unranked "smallest element containing the text" picks the wrong thing —
    on a repo page it matched a code sample containing the word rather than the
    counter. Exactness, brevity and position all matter."""
    return """(needles) => {
      const out = {};
      const nodes = Array.from(document.querySelectorAll('body *'));
      const inCode = (el) => !!el.closest('pre, code, textarea, script, style');
      for (const needle of needles) {
        const low = needle.toLowerCase();
        let re; try { re = new RegExp(needle, 'i'); } catch (e) { re = null; }
        const cands = [];
        for (const el of nodes) {
          if (el.children.length > 3) continue;
          const t = (el.innerText || '').trim();
          if (!t || t.length > 160) continue;
          const hit = re ? re.test(t) : t.toLowerCase().includes(low);
          if (!hit) continue;
          const r = el.getBoundingClientRect();
          if (r.width < 6 || r.height < 6) continue;
          const tl = t.toLowerCase();
          let score = 0;
          if (tl === low) score += 100;
          else if (tl.startsWith(low) || tl.endsWith(low)) score += 40;
          score += Math.max(0, 40 - t.length);
          score -= (r.top + scrollY) / 400;
          if (inCode(el)) score -= 60;
          if (el.tagName === 'A' || el.tagName === 'STRONG') score += 8;
          cands.push({ text: t, score,
            x: r.left + scrollX, y: r.top + scrollY, w: r.width, h: r.height });
        }
        cands.sort((a, b) => b.score - a.score);
        if (cands.length) { out[needle] = cands[0]; out[needle].alternates = cands.slice(1, 4); }
      }
      return out;
    }"""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("url")
    ap.add_argument("--studio", default="studio")
    ap.add_argument("--name", default=None, help="asset basename")
    ap.add_argument("--find", action="append", default=[],
                    help="text to locate; repeatable")
    ap.add_argument("--width", type=int, default=VIEWPORT[0])
    ap.add_argument("--height", type=int, default=VIEWPORT[1])
    ap.add_argument("--dpr", type=int, default=DPR)
    ap.add_argument("--wait", type=float, default=3.0)
    ap.add_argument("--keep-overlays", action="store_true",
                    help="keep sticky/fixed elements (cookie bars, nav)")
    args = ap.parse_args()

    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("error: playwright not installed.\n"
              "       uv pip install --python .venv playwright && "
              ".venv/bin/playwright install chromium", file=sys.stderr)
        return 1

    name = args.name or re.sub(r"[^\w.-]+", "-", args.url.split("//")[-1])[:48].strip("-")
    outdir = Path(args.studio) / "assets" / "proof"
    outdir.mkdir(parents=True, exist_ok=True)
    png, meta = outdir / f"{name}.png", outdir / f"{name}.json"

    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": args.width, "height": args.height},
                                device_scale_factor=args.dpr)
        try:
            page.goto(args.url, wait_until="domcontentloaded", timeout=60000)
        except Exception as e:
            print(f"error: could not load {args.url}: {str(e)[:120]}", file=sys.stderr)
            browser.close()
            return 1
        page.wait_for_timeout(int(args.wait * 1000))

        if not args.keep_overlays:
            # Sticky headers and cookie bars repeat down the whole tall capture,
            # which looks broken once it scrolls.
            page.evaluate("""() => {
              for (const el of document.querySelectorAll('body *')) {
                const s = getComputedStyle(el);
                if (s.position === 'fixed' || s.position === 'sticky') {
                  el.style.setProperty('position', 'static', 'important');
                }
              }
            }""")
            page.wait_for_timeout(300)

        targets = page.evaluate(rank_js(), args.find) if args.find else {}
        page_w = page.evaluate("document.documentElement.scrollWidth")
        page_h = page.evaluate("document.body.scrollHeight")
        title = page.title()
        page.screenshot(path=str(png), full_page=True)
        browser.close()

    clean = {}
    for needle, t in targets.items():
        clean[needle] = {
            "text": t["text"],
            # CSS px on the page; multiply by dpr for pixels in the image.
            "x": round(t["x"], 1), "y": round(t["y"], 1),
            "w": round(t["w"], 1), "h": round(t["h"], 1),
            "centre": [round(t["x"] + t["w"] / 2, 1), round(t["y"] + t["h"] / 2, 1)],
            "alternates": [a["text"] for a in t.get("alternates", [])],
        }

    meta.write_text(json.dumps({
        "url": args.url, "title": title,
        "image": str(png.resolve()),
        "viewport": [args.width, args.height], "dpr": args.dpr,
        "page_size": [page_w, page_h],
        "image_size": [page_w * args.dpr, page_h * args.dpr],
        "targets": clean,
    }, indent=2, ensure_ascii=False))

    print(f"{title[:60]}")
    print(f"  {page_w}x{page_h} css · {page_w * args.dpr}x{page_h * args.dpr} px -> {png.name}")
    for needle, t in clean.items():
        print(f"  found {needle!r}: {t['text'][:48]!r} at y={t['y']:.0f}")
        if t["alternates"]:
            print(f"        other matches: {', '.join(a[:28] for a in t['alternates'][:2])}")
    for needle in args.find:
        if needle not in clean:
            print(f"  MISSING {needle!r} — not on the page at this viewport width")
    print(f"-> {meta}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

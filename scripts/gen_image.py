#!/usr/bin/env python3
"""Generate a still for the edit via the local Gemini proxy.

For beats where there is nothing real to show — an abstract claim, a payoff, a
transition. Real material always beats a generated still (rules/proof.md), so
reach for this only after checking there is no repo, page or dashboard to
capture. A generated image must never imply a screenshot of something real.

    python3 scripts/gen_image.py "<prompt>" --studio <studio> --name payoff
    python3 scripts/gen_image.py "<prompt>" -o out.jpg --animate 3.0

The proxy is OpenAI-compatible but image generation is a ROUTE, not a model:
nothing in /v1/models generates images, `n` must be 1, and size/quality/style
are rejected. Ask for the aspect in the prompt text instead.
"""
import argparse, base64, json, os, subprocess, sys, urllib.request
from pathlib import Path

BASE = os.environ.get("GEMINI_WEB2API_BASE", "http://127.0.0.1:8081/v1")
KEY = os.environ.get("GEMINI_WEB2API_KEY", "sk-gemini")

# The aspect is the only thing the model needs every time — a landscape still
# is unusable in a 9:16 edit. The old blanket ban on text, logos, screens and
# UI came off permanently on 2026-09-16: it locked out the literal subject
# whenever the beat was about a screen, which is most of them here. Put any
# bans the individual beat actually needs at the end of its own prompt.
REQUIRED = "Vertical 9:16 portrait orientation, tall not wide. "


def generate(prompt, out):
    body = json.dumps({"prompt": REQUIRED + prompt, "n": 1,
                       "response_format": "b64_json"}).encode()
    req = urllib.request.Request(f"{BASE}/images/generations", data=body, method="POST",
                                 headers={"Authorization": f"Bearer {KEY}",
                                          "Content-Type": "application/json"})
    try:
        d = json.loads(urllib.request.urlopen(req, timeout=180).read())
    except Exception as e:
        sys.exit(f"error: image generation failed ({str(e)[:120]}).\n"
                 f"       check the proxy is up:  curl -s -o /dev/null -w '%{{http_code}}' "
                 f"-H 'Authorization: Bearer {KEY}' {BASE}/models")
    Path(out).write_bytes(base64.b64decode(d["data"][0]["b64_json"]))
    return out


def probe(path):
    r = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "stream=width,height",
                        "-of", "csv=p=0", path], capture_output=True, text=True)
    w, h = (int(x) for x in r.stdout.strip().split(",")[:2])
    return w, h


def animate(img, out, seconds, width=1080, height=1920):
    """A still that sits there is a dead frame. Give it a slow push-in."""
    frames = int(seconds * 30)
    subprocess.run(
        ["ffmpeg", "-v", "error", "-loop", "1", "-i", img, "-t", f"{seconds:.2f}",
         "-vf", (f"scale={width*2}:-1,"
                 f"zoompan=z='1+0.12*(in/{frames})':x='iw/2-(iw/zoom/2)':"
                 f"y='ih/2-(ih/zoom/2)':d=1:s={width}x{height}:fps=30,format=yuv420p"),
         "-c:v", "libx264", "-preset", "medium", "-crf", "18", "-an", "-y", out],
        check=True)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("prompt")
    ap.add_argument("--studio")
    ap.add_argument("--name", default="image")
    ap.add_argument("-o", "--out")
    ap.add_argument("--animate", type=float, default=0.0,
                    help="also render an N-second push-in clip")
    args = ap.parse_args()

    if args.out:
        img = args.out
    else:
        d = Path(args.studio or ".") / "assets" / "generated"
        d.mkdir(parents=True, exist_ok=True)
        img = str(d / f"{args.name}.jpg")

    generate(args.prompt, img)
    w, h = probe(img)
    print(f"{img}  {w}x{h}" + ("  WARNING: landscape, re-prompt for vertical" if w > h else ""))

    if args.animate:
        clip = str(Path(img).with_suffix(".mp4"))
        animate(img, clip, args.animate)
        print(f"{clip}  {args.animate:.1f}s push-in — add to broll.json as an overlay")


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""Serve the finished video and open it in a browser.

Self-contained: no configuration, no remembered address. It picks a free port,
prints both the local and LAN URLs, and opens the local one. The LAN URL is
printed fresh every run because a machine's IP changes with the network, and a
remembered one silently stops working.

    python3 scripts/review.py --studio <footage>/studio
    python3 scripts/review.py --studio ... --no-open
"""

import argparse
import http.server
import json
import socket
import socketserver
import subprocess
import sys
import threading
import webbrowser
from pathlib import Path

PAGE = """<!doctype html>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title}</title>
<style>
  :root {{ color-scheme: dark; }}
  * {{ box-sizing: border-box; }}
  body {{
    margin: 0; background: #0d0f13; color: #e8ecf2;
    font: 15px/1.6 ui-sans-serif, -apple-system, "Segoe UI", sans-serif;
    display: flex; flex-direction: column; align-items: center;
    padding: 24px 16px 64px;
  }}
  h1 {{ font-size: 17px; font-weight: 650; margin: 0 0 4px; letter-spacing: -.01em; }}
  .meta {{
    font: 12px ui-monospace, SFMono-Regular, Menlo, monospace;
    color: #8a94a6; letter-spacing: .05em; margin-bottom: 18px;
  }}
  video {{
    max-height: 78vh; max-width: 100%; border-radius: 10px;
    background: #000; box-shadow: 0 18px 50px rgba(0,0,0,.55);
  }}
  .bar {{
    display: flex; gap: 8px; flex-wrap: wrap;
    align-items: center; margin-top: 14px;
  }}
  button {{
    background: #1b202a; color: #e8ecf2; border: 1px solid #2c3341;
    border-radius: 7px; padding: 7px 12px; cursor: pointer;
    font: 13px ui-monospace, SFMono-Regular, Menlo, monospace;
  }}
  button:hover {{ background: #232a36; }}
  button:focus-visible {{ outline: 2px solid #f0a93b; outline-offset: 2px; }}
  #t {{
    font: 13px ui-monospace, SFMono-Regular, Menlo, monospace;
    color: #f0a93b; min-width: 148px; text-align: center;
  }}
  .versions {{ margin-top: 22px; font-size: 13px; }}
  .versions a {{ color: #f0a93b; margin-right: 14px; }}
  pre {{
    margin-top: 22px; max-width: 640px; width: 100%;
    background: #12161d; border: 1px solid #232a36; border-radius: 8px;
    padding: 14px 16px; white-space: pre-wrap; font-size: 13px; color: #b9c2d0;
  }}
</style>
<h1>{title}</h1>
<div class="meta">{meta}</div>
<video id="v" src="{src}" controls autoplay playsinline></video>
<div class="bar">
  <button onclick="step(-1/30)">◀ frame</button>
  <button onclick="step(1/30)">frame ▶</button>
  <button onclick="v.currentTime=0">restart</button>
  <button onclick="v.playbackRate = v.playbackRate===1?0.5:1">½ speed</button>
  <span id="t">0.000s · f0</span>
</div>
<div class="versions">{versions}</div>
{copy}
<script>
  const v = document.getElementById("v"), t = document.getElementById("t");
  const step = (d) => {{ v.pause(); v.currentTime = Math.max(0, v.currentTime + d); }};
  const tick = () => {{
    t.textContent = v.currentTime.toFixed(3) + "s · f" + Math.round(v.currentTime * 30);
    requestAnimationFrame(tick);
  }};
  tick();
  addEventListener("keydown", (e) => {{
    if (e.key === ",") step(-1/30);
    if (e.key === ".") step(1/30);
    if (e.key === " ") {{ e.preventDefault(); v.paused ? v.play() : v.pause(); }}
  }});
</script>
"""


def lan_ip():
    """Best-guess outward-facing address, without needing a network call."""
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("8.8.8.8", 80))          # no packets are sent
        return s.getsockname()[0]
    except Exception:
        return None
    finally:
        s.close()


def free_port(preferred=8777):
    for port in (preferred, 0):
        try:
            s = socket.socket()
            s.bind(("", port))
            p = s.getsockname()[1]
            s.close()
            return p
        except OSError:
            continue
    return 8777


def probe(path):
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration,size",
         "-select_streams", "v:0", "-show_entries", "stream=width,height",
         "-of", "json", str(path)],
        capture_output=True, text=True, errors="replace").stdout
    try:
        d = json.loads(out or "{}")
    except json.JSONDecodeError:
        return ""
    st = (d.get("streams") or [{}])[0]
    fmt = d.get("format") or {}
    dur = float(fmt.get("duration") or 0)
    mb = int(fmt.get("size") or 0) / 1e6
    return f"{st.get('width')}x{st.get('height')} · {dur:.1f}s · {mb:.0f} MB"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--studio", default="studio")
    ap.add_argument("--file", default=None, help="specific video to review")
    ap.add_argument("--port", type=int, default=None)
    ap.add_argument("--no-open", action="store_true")
    args = ap.parse_args()

    studio = Path(args.studio).resolve()
    out = studio / "out"

    if args.file:
        video = Path(args.file).resolve()
    else:
        video = next((p for p in (out / "final.mp4", out / "master.mp4")
                      if p.is_file()), None)
    if not video or not video.is_file():
        print(f"error: nothing to review in {out} — render first", file=sys.stderr)
        return 1

    root = video.parent
    others = sorted(p for p in root.glob("*.mp4") if p != video)
    versions = "".join(f'<a href="?v={p.name}">{p.name}</a>' for p in others)
    if versions:
        versions = "also: " + versions

    post = root / "post.md"
    copy_html = ""
    if post.is_file():
        import html as _h
        copy_html = f"<pre>{_h.escape(post.read_text()[:4000])}</pre>"

    page = PAGE.format(title=video.stem, meta=probe(video), src=video.name,
                       versions=versions, copy=copy_html)
    (root / "_review.html").write_text(page)

    port = args.port or free_port()

    class Handler(http.server.SimpleHTTPRequestHandler):
        def __init__(self, *a, **kw):
            super().__init__(*a, directory=str(root), **kw)

        def do_GET(self):
            if self.path in ("/", "/index.html") or self.path.startswith("/?"):
                self.path = "/_review.html"
            return super().do_GET()

        def log_message(self, *a):
            pass

    socketserver.TCPServer.allow_reuse_address = True
    server = socketserver.TCPServer(("", port), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()

    local = f"http://localhost:{port}/"
    ip = lan_ip()
    print(f"reviewing {video.name}  ({probe(video)})", flush=True)
    print(f"\n  this machine   {local}", flush=True)
    if ip:
        print(f"  phone / LAN    http://{ip}:{port}/", flush=True)
    print("\n  , and . step one frame · space toggles play", flush=True)
    print("  ctrl-c to stop\n", flush=True)

    if not args.no_open:
        webbrowser.open(local)

    try:
        threading.Event().wait()
    except KeyboardInterrupt:
        print("stopped")
        server.shutdown()
    return 0


if __name__ == "__main__":
    sys.exit(main())

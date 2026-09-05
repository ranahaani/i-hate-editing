#!/usr/bin/env python3
"""Media probing that respects rotation.

Phone footage carries a rotation matrix rather than rotated pixels: ffprobe
reports the stream as 1920x1080 while ffmpeg decodes 1080x1920. Reading the raw
stream dimensions therefore sizes a vertical video as landscape and letterboxes
the whole edit — silently, since nothing errors.

Always use display_size() rather than reading width/height directly.
"""

import json
import subprocess
from pathlib import Path


def _sh(cmd):
    return subprocess.run(cmd, capture_output=True, text=True, errors="replace")


def rotation(path):
    """Degrees of rotation the container asks for, normalised to 0/90/180/270."""
    out = _sh(["ffprobe", "-v", "error", "-select_streams", "v:0",
               "-show_entries", "stream_side_data=rotation",
               "-show_entries", "stream_tags=rotate",
               "-of", "json", str(path)]).stdout
    try:
        d = json.loads(out or "{}")
    except json.JSONDecodeError:
        return 0
    st = (d.get("streams") or [{}])[0]
    val = None
    for sd in st.get("side_data_list") or []:
        if "rotation" in sd:
            val = sd["rotation"]
            break
    if val is None:
        val = (st.get("tags") or {}).get("rotate")
    try:
        return int(abs(float(val))) % 360 if val is not None else 0
    except (TypeError, ValueError):
        return 0


def probe(path):
    """(display_width, display_height, duration_seconds)."""
    out = _sh(["ffprobe", "-v", "error", "-select_streams", "v:0",
               "-show_entries", "stream=width,height",
               "-show_entries", "format=duration",
               "-of", "json", str(path)]).stdout
    try:
        d = json.loads(out or "{}")
    except json.JSONDecodeError:
        d = {}
    st = (d.get("streams") or [{}])[0]
    w = st.get("width") or 0
    h = st.get("height") or 0
    if rotation(path) in (90, 270):
        w, h = h, w
    try:
        dur = float((d.get("format") or {}).get("duration") or 0)
    except (TypeError, ValueError):
        dur = 0.0
    return w, h, dur


def display_size(path):
    w, h, _ = probe(path)
    return w, h


def duration(path):
    return probe(path)[2]


def has_audio(path):
    out = _sh(["ffprobe", "-v", "error", "-select_streams", "a",
               "-show_entries", "stream=index", "-of", "csv=p=0", str(path)]).stdout
    return bool(out.strip())


if __name__ == "__main__":
    import sys
    for f in sys.argv[1:]:
        w, h, d = probe(f)
        r = rotation(f)
        print(f"{Path(f).name}: {w}x{h} · {d:.2f}s"
              + (f" · rotation {r}° applied" if r else ""))

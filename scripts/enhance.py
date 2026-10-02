#!/usr/bin/env python3
"""Enhance the cut's voice with Adobe Podcast Enhance Speech (v2).

    python3 scripts/enhance.py <studio>/cut.wav -o <studio>/voice_enhanced.wav [--mix site|full]

Uploads through the signed-in ego-browser session (adobe_enhance.mjs), downloads
the 8-channel stem FLAC and mixes it down locally:

  site  the website's default download, "Speech 50%, Background 10%, Music 10%".
        Fitted against the site's own file on 2026-10-02 to a residual of
        -101 dB: 0.354 x enhanced speech + 0.353 x original speech
        + 0.017 x each music/background channel.
  full  enhanced speech only (100%). Sounds processed on most takes.

Stem layout of merged_media, measured: c0/c1 original, c2 enhanced speech,
c3 original speech, c4/c5 music, c6/c7 background.

Needs `ego-browser` and an Adobe account signed in to podcast.adobe.com inside
it. An agent cannot type the password; when the script reports NOT_SIGNED_IN,
ask the user to sign in and rerun.
"""
import argparse
import json
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
MIXES = {
    "site": "mono|c0=0.354*c2+0.353*c3+0.017*c4+0.017*c5+0.017*c6+0.017*c7",
    "full": "mono|c0=c2",
}


def run_enhance(src, flac, model):
    job = json.dumps({"input": str(src), "output": str(flac), "model": model})
    script = f"const JOB = {job};\n" + (HERE / "adobe_enhance.mjs").read_text()
    r = subprocess.run(["ego-browser", "nodejs"], input=script, text=True, capture_output=True)
    out = (r.stdout + r.stderr).strip()
    result = next((json.loads(l) for l in out.splitlines() if l.startswith('{"ok"')), None)
    if r.returncode or not result:
        raise SystemExit(f"error: adobe enhance failed\n{out[-1500:]}")
    return result


def mixdown(flac, dst, mix):
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(flac), "-af", f"pan={MIXES[mix]}",
                    "-ar", "48000", "-c:a", "pcm_s16le", str(dst)], check=True)


def duration(path):
    out = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0",
                          str(path)], capture_output=True, text=True, check=True).stdout
    return float(out)


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("input", help="voice track (wav); 16-bit PCM is what the site accepts most reliably")
    ap.add_argument("-o", "--output", required=True)
    ap.add_argument("--mix", choices=sorted(MIXES), default="site")
    ap.add_argument("--model", default="v2")
    a = ap.parse_args()
    src, dst = Path(a.input).resolve(), Path(a.output).resolve()
    with tempfile.TemporaryDirectory(prefix="adobe_enhance_") as tmp:
        wav = Path(tmp) / f"{src.stem}.wav"
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(src), "-ac", "1", "-ar", "48000",
                        "-c:a", "pcm_s16le", str(wav)], check=True)
        flac = Path(tmp) / "merged.flac"
        result = run_enhance(wav, flac, a.model)
        mixdown(flac, dst, a.mix)
    drift = abs(duration(dst) - duration(src))
    if drift > 0.05:
        raise SystemExit(f"error: enhanced file is {drift:.3f}s off the input; timings would break")
    print(f"enhanced ({a.mix} mix, model {result['model']}, {result['seconds']:.0f}s on Adobe) -> {dst}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

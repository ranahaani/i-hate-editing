#!/usr/bin/env python3
"""Designed motion-graphics scenes, built in Remotion and composited as clips.

HyperFrames cards are text on a ground: a headline, a sub-line, a list. That
is the right form for most beats and stays where it is. A beat that needs a
*built* visual — a product card, a counter, a diagram assembling itself, a
simulated UI — is not a card, and forcing it into one is how a piece ends up
looking like a slideshow with a face attached (rules/motion.md).

Those beats are built as Remotion components: real React, frame-driven motion,
previewed in Studio. Each approved scene renders to its own MP4, and the MP4 is
composited by compose.py through the same overlay path B-roll uses, so
captions still draw on top and the face still repositions under a half-panel.

    python3 scripts/scenes.py init    --studio <footage>/studio
    python3 scripts/scenes.py sync    --studio <footage>/studio
    python3 scripts/scenes.py check   --studio <footage>/studio
    python3 scripts/scenes.py render  --studio <footage>/studio [--only <id>]
    python3 scripts/scenes.py studio  --studio <footage>/studio

The approach, the per-scene composition rule and the spec-before-build gate are
adapted from Creatorberry's flick (MIT), which does this end to end:
https://github.com/Creatorberry/flick
"""

import argparse
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from media import probe  # noqa: E402  (rotation-aware)

TEMPLATE = Path(__file__).resolve().parent.parent / "templates" / "remotion"
ID_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
# rules/motion.md: a shot that holds for more than about three seconds loses
# attention. A scene longer than this needs a second event inside it.
LONG_SCENE = 4.0


def fail(msg):
    print(f"error: {msg}", file=sys.stderr)
    raise SystemExit(1)


def cut_video(studio):
    graded = studio / "cut_graded.mp4"
    video = graded if graded.is_file() else studio / "cut.mp4"
    if not video.is_file():
        fail(f"no cut at {video} — render the cut first")
    return video


def probe_fps(video):
    """Frame rate of the cut, as an exact ratio.

    A scene rendered at a different rate than the cut is resampled on
    composite: every few frames one is dropped or doubled, which reads as
    judder on exactly the moves that are supposed to look designed. Nothing
    errors, so it has to be checked here.
    """
    r = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "v:0",
         "-show_entries", "stream=r_frame_rate", "-of", "csv=p=0", str(video)],
        capture_output=True, text=True)
    if r.returncode != 0:
        fail(f"ffprobe failed on {video}: {(r.stderr or '').strip()}")
    num, _, den = r.stdout.strip().partition("/")
    fps = float(num) / float(den or 1)
    rounded = round(fps)
    if abs(fps - rounded) > 0.02:
        fail(f"the cut is {fps:.3f} fps; Remotion needs a whole-number rate. "
             f"Re-render the cut at {rounded} fps before building scenes")
    return rounded


def component_name(scene):
    if scene.get("component"):
        return scene["component"]
    return "".join(p.capitalize() for p in scene["id"].split("-"))


def read_scenes(studio):
    path = studio / "scenes.json"
    if not path.is_file():
        fail(f"no {path} — author it before building scenes (rules/scenes.md)")
    scenes = json.loads(path.read_text()).get("scenes", [])
    if not scenes:
        fail(f"{path} has no scenes")
    return scenes


def validate(scenes, fps, duration):
    seen, windows, warnings = set(), [], []
    for s in scenes:
        sid = s.get("id", "")
        if not ID_RE.match(sid):
            fail(f"scene id {sid!r} must be lowercase kebab-case")
        if sid in seen:
            fail(f"duplicate scene id {sid!r}")
        seen.add(sid)
        start, dur = float(s["start"]), float(s["duration"])
        if dur <= 0:
            fail(f"{sid}: duration must be positive")
        if start < 0 or start + dur > duration + 0.05:
            fail(f"{sid}: {start:.2f}–{start + dur:.2f}s falls outside the "
                 f"{duration:.2f}s cut")
        if round(dur * fps) < 1:
            fail(f"{sid}: {dur:.3f}s is shorter than one frame at {fps} fps")
        windows.append((start, start + dur, sid))
        if dur > LONG_SCENE:
            warnings.append(f"{sid} runs {dur:.1f}s — plan a second event "
                            f"inside it (rules/motion.md)")
    windows.sort()
    for (a_start, a_end, a_id), (b_start, _, b_id) in zip(windows, windows[1:]):
        if b_start < a_end - 0.01:
            fail(f"{a_id} and {b_id} overlap; one scene owns the frame at a "
                 f"time")
    return warnings


def spec(scenes, width, height, fps):
    return {
        "width": width, "height": height, "fps": fps,
        "scenes": [{
            "id": s["id"],
            "component": component_name(s),
            "start": round(float(s["start"]), 3),
            "duration": round(float(s["duration"]), 3),
            "durationInFrames": max(1, round(float(s["duration"]) * fps)),
            "full": bool(s.get("full")),
            "line": s.get("line", ""),
            "visual": s.get("visual", ""),
            "assets": s.get("assets", []),
        } for s in scenes],
    }


def root_tsx(scene_spec):
    """One Composition per scene, generated — never hand-maintained.

    Hand-registering compositions is where a scene drifts from its spec: the
    component gets a new duration in the plan and Root.tsx keeps the old frame
    count, so the scene renders truncated and the render still succeeds.
    """
    imports = "\n".join(
        f"import {{{s['component']}}} from './scenes/{s['component']}';"
        for s in scene_spec["scenes"])
    comps = "\n".join(
        f"""      <Composition
        id="{s['id']}"
        component={{{s['component']}}}
        durationInFrames={{{s['durationInFrames']}}}
        fps={{{scene_spec['fps']}}}
        width={{{scene_spec['width']}}}
        height={{{scene_spec['height']}}}
      />""" for s in scene_spec["scenes"])
    return f"""// Generated by scripts/scenes.py — do not edit.
// Edit studio/scenes.json and re-run `scenes.py sync`.
import type {{FC}} from 'react';
import {{Composition}} from 'remotion';
{imports}

export const RemotionRoot: FC = () => {{
  return (
    <>
{comps}
    </>
  );
}};
"""


def workspace(studio):
    return studio / "scenes"


def do_init(studio, install=True):
    ws = workspace(studio)
    if (ws / "package.json").is_file():
        print(f"workspace already at {ws}")
    else:
        if not TEMPLATE.is_dir():
            fail(f"missing template at {TEMPLATE}")
        ws.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(TEMPLATE, ws, dirs_exist_ok=True)
        print(f"-> {ws}")
    scenes_json = studio / "scenes.json"
    if not scenes_json.is_file():
        scenes_json.write_text(json.dumps({"scenes": []}, indent=2) + "\n")
        print(f"-> {scenes_json} (author it, then run sync)")
    if install and not (ws / "node_modules").is_dir():
        print("installing Remotion…")
        r = subprocess.run(["npm", "install"], cwd=ws)
        if r.returncode != 0:
            fail("npm install failed")
    return 0


def do_sync(studio, quiet=False):
    ws = workspace(studio)
    if not (ws / "package.json").is_file():
        fail(f"no workspace at {ws} — run `scenes.py init` first")
    video = cut_video(studio)
    width, height, duration = probe(video)
    fps = probe_fps(video)
    scenes = read_scenes(studio)
    warnings = validate(scenes, fps, duration)
    s = spec(scenes, width, height, fps)
    (ws / "src" / "data").mkdir(parents=True, exist_ok=True)
    (ws / "src" / "data" / "scene-spec.json").write_text(
        json.dumps(s, indent=2) + "\n")
    (ws / "src" / "Root.tsx").write_text(root_tsx(s))
    missing = [x["component"] for x in s["scenes"]
               if not (ws / "src" / "scenes" / f"{x['component']}.tsx").is_file()]
    if not quiet:
        for w in warnings:
            print(f"  note: {w}")
        print(f"{len(s['scenes'])} scene(s) at {width}x{height} {fps}fps")
        for x in s["scenes"]:
            print(f"  {x['id']:<24} {x['start']:6.2f}s  "
                  f"{x['durationInFrames']:>4}f  "
                  f"{'full' if x['full'] else 'panel'}")
    if missing:
        print("\nno component yet for: " + ", ".join(missing))
        print(f"write them in {ws / 'src' / 'scenes'} (see rules/scenes.md)")
    return s, missing


def do_check(studio):
    s, missing = do_sync(studio)
    if missing:
        fail("every scene needs its component before check can pass")
    ws = workspace(studio)
    print("\ntype-checking…")
    r = subprocess.run(["npx", "--yes", "tsc", "--noEmit"], cwd=ws,
                       capture_output=True, text=True, errors="replace")
    print((r.stdout or "")[-1500:].strip() or (r.stderr or "")[-800:].strip()
          or "clean")
    return 0 if r.returncode == 0 else 1


def has_audio(path):
    r = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "a", "-show_entries",
         "stream=index", "-of", "csv=p=0", str(path)],
        capture_output=True, text=True)
    return bool(r.stdout.strip())


def merge_overlays(studio, rendered):
    """Hand the rendered scenes to compose.py through broll.json.

    Overlays authored by broll-gen are kept; only entries this script wrote
    before (source: "scene") are replaced, so re-rendering one scene does not
    drop the B-roll plan.
    """
    path = studio / "broll.json"
    data = json.loads(path.read_text()) if path.is_file() else {}
    existing = data.get("overlays", [])
    kept = [o for o in existing if o.get("source") != "scene"]
    mine = {o["id"]: o for o in existing if o.get("source") == "scene"}
    mine.update(rendered)
    data["overlays"] = sorted(kept + list(mine.values()),
                              key=lambda o: float(o["start"]))
    path.write_text(json.dumps(data, indent=2) + "\n")
    print(f"-> {path} ({len(data['overlays'])} overlay(s))")


def do_render(studio, only=None):
    s, missing = do_sync(studio, quiet=True)
    if missing:
        fail("missing component(s): " + ", ".join(missing))
    ws = workspace(studio)
    out_dir = studio / "assets" / "scenes"
    out_dir.mkdir(parents=True, exist_ok=True)
    targets = [x for x in s["scenes"] if only is None or x["id"] == only]
    if not targets:
        fail(f"no scene with id {only!r}")
    rendered = {}
    for x in targets:
        out = out_dir / f"{x['id']}.mp4"
        print(f"rendering {x['id']}…")
        r = subprocess.run(
            ["npx", "--yes", "remotion", "render", "src/index.tsx", x["id"],
             str(out.resolve()), "--codec", "h264", "--crf", "16"],
            cwd=ws)
        if r.returncode != 0:
            fail(f"{x['id']} failed to render")
        if has_audio(out):
            # compose.py mounts every overlay with the `muted` attribute, so
            # audio baked into a scene is dropped without a warning and the
            # sting the scene was cut against is simply absent from the mix.
            fail(f"{x['id']}.mp4 carries an audio stream; scene audio is "
                 f"dropped on composite — plan the sting in sfx.json instead "
                 f"(HARD-RULES.md)")
        rendered[x["id"]] = {
            "id": x["id"], "source": "scene",
            "file": str(Path("assets") / "scenes" / f"{x['id']}.mp4"),
            "start": x["start"], "end": round(x["start"] + x["duration"], 3),
            "full": x["full"],
        }
        print(f"  -> {out}")
    merge_overlays(studio, rendered)
    print("\nnow run compose.py — the scenes composite under the captions")
    return 0


def do_studio(studio):
    ws = workspace(studio)
    do_sync(studio, quiet=True)
    print("opening Remotion Studio (ctrl-c to stop)…")
    return subprocess.run(["npx", "--yes", "remotion", "studio",
                           "src/index.tsx"], cwd=ws).returncode


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("command",
                    choices=["init", "sync", "check", "render", "studio"])
    ap.add_argument("--studio", default="studio")
    ap.add_argument("--only", default=None, help="render a single scene id")
    ap.add_argument("--no-install", action="store_true",
                    help="init without running npm install")
    args = ap.parse_args()
    studio = Path(args.studio)

    if args.command == "init":
        return do_init(studio, install=not args.no_install)
    if args.command == "sync":
        do_sync(studio)
        return 0
    if args.command == "check":
        return do_check(studio)
    if args.command == "render":
        return do_render(studio, args.only)
    return do_studio(studio)


if __name__ == "__main__":
    sys.exit(main())

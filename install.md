# Install

Read this once. Daily usage is in [`SKILL.md`](./SKILL.md).

## Prerequisites

| Tool | Purpose | Install |
|---|---|---|
| `ffmpeg` + `ffprobe` | All media processing | `brew install ffmpeg` |
| `whisper.cpp` | Local transcription | `brew install whisper-cpp` |
| Node 22+ | HyperFrames compositions | `brew install node` |
| Python 3.10+ | The scripts | usually present |
| `uv` | Python environment | `brew install uv` |
| `yt-dlp` | Reference footage (optional) | `brew install yt-dlp` |

On Linux, substitute your package manager. Nothing here is macOS-specific
except the Homebrew commands.

**Your ffmpeg does not need libass.** Many builds ship without it, so the
`subtitles` and `drawtext` filters are unavailable. i-hate-editing renders all text
through HyperFrames instead, which is both better looking and immune to this.
The scan reports it as a note, not a problem.

## Install the skill

```bash
git clone https://github.com/ranahaani/i-hate-editing ~/Developer/i-hate-editing
cd ~/Developer/i-hate-editing
```

Register it with your agent:

```bash
ln -sfn ~/Developer/i-hate-editing ~/.claude/skills/i-hate-editing      # Claude Code
# ln -sfn ~/Developer/i-hate-editing ~/.codex/skills/i-hate-editing     # Codex
```

## Python environment

Only needed for proof B-roll (page capture). Everything else is standard
library plus ffmpeg.

```bash
uv venv .venv
uv pip install --python .venv playwright
.venv/bin/playwright install chromium
```

If your system Python refuses a direct `pip install` with an
"externally managed environment" error, that is expected — use the venv above
rather than `--break-system-packages`.

## Whisper models

The setup scan picks a model from your language and hardware and downloads it.
You do not normally choose one yourself.

| Language | Acceleration | Model | Size |
|---|---|---|---|
| English | Metal / CUDA | `large-v3-turbo` | 1.6 GB |
| English | CPU | `small.en` | 488 MB |
| Major non-English | Metal / CUDA | `large-v3-turbo` | 1.6 GB |
| Major non-English | CPU | `medium` | 1.5 GB |
| Low-resource (Urdu, Hindi, Arabic…) | any | `large-v3` | 3.1 GB |
| Any, when captions need translating | any | `large-v3` or `medium` | — |

**Turbo models cannot translate.** Asked to, they return the source language
without any error, which would flow into your captions as untranslated text.
If your captions need translating, i-hate-editing substitutes a translation-capable
model automatically and says so.

Models are looked for in `~/.cache/whisper`,
`~/.cache/hyperframes/whisper/models`, `~/.local/share/whisper`, and
`/opt/homebrew/share/whisper-cpp`.

## Sound library

```bash
python3 scripts/sfx_library.py install
python3 scripts/sfx_library.py status
```

Installs roughly sixty effects into `~/.i-hate-editing/sfx`, organised by what
each one is *for* rather than by what it sounds like — see
`assets/sfx-taxonomy.json`. Placement reads that vocabulary, so a list row gets
a click, a cut to a screen gets a glitch, and a full-frame card gets a deep
whoosh, without anyone choosing files by hand.

Sounds are fetched rather than bundled. Shipping audio inside the repository
would redistribute it, and that is a licence question for every file; fetching
records the licence per file instead. The default source is Mixkit, whose free
licence permits commercial use without attribution.

Every file is analysed on install. Roughly **40% of library effects have their
loud moment well after the file starts** — played in a short window those are
silent while every level check passes. The installer records where each peak
sits so placement can start the file early enough to land it on the beat, and
skips files whose peak is too late to be usable as a transient.

To add your own, drop files into a category directory and re-run `status`.
Check the licence of anything you add: an unlicensed effect in a monetised
video is a real problem.

## First run

```bash
cd /path/to/your/footage
python3 ~/.claude/skills/i-hate-editing/scripts/scan.py --footage .
```

It reports what it found, asks five questions, and writes `studio/profile.yml`
next to your footage. Then start your agent in that directory and ask it to
edit.

To check the environment without setting anything up:

```bash
python3 scripts/scan.py --json
```

## Verify the install

```bash
python3 scripts/scan.py --json | grep -E '"node_ok"|whisper|ffmpeg'
python3 scripts/sound.py inspect <any mp3>
.venv/bin/python scripts/capture.py https://example.com --studio /tmp/t --find "Example"
```

If all three work, the pipeline will run.

## Reviewing

```bash
python3 scripts/review.py --studio <footage>/studio
```

Serves the finished video, opens it in your browser, and prints a LAN address
for watching on a phone. `,` and `.` step a frame; space toggles play. The
address is printed fresh each run rather than remembered, because it changes
with the network.

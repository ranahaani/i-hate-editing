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
`subtitles` and `drawtext` filters are unavailable. editkit renders all text
through HyperFrames instead, which is both better looking and immune to this.
The scan reports it as a note, not a problem.

## Install the skill

```bash
git clone https://github.com/ranahaani/editkit ~/Developer/editkit
cd ~/Developer/editkit
```

Register it with your agent:

```bash
ln -sfn ~/Developer/editkit ~/.claude/skills/editkit      # Claude Code
# ln -sfn ~/Developer/editkit ~/.codex/skills/editkit     # Codex
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
If your captions need translating, editkit substitutes a translation-capable
model automatically and says so.

Models are looked for in `~/.cache/whisper`,
`~/.cache/hyperframes/whisper/models`, `~/.local/share/whisper`, and
`/opt/homebrew/share/whisper-cpp`.

## Sound library

editkit places sounds from a library you point it at, organised by category:

```
sfx/
├── whoosh/
├── pop/
├── impact/
├── riser/
└── notification/
```

Free, permissively licensed effects are available from
[Mixkit](https://mixkit.co/free-sound-effects/). Check the licence of anything
you add — audio scraped from aggregator sites generally cannot be redistributed
or used commercially.

Before using a new file, inspect it:

```bash
python3 scripts/sound.py inspect sfx/riser/riser.mp3
```

Many library files have their loud transient well after the file start. Played
in a short window they are silent while every level check passes. `inspect`
finds this and prints the fix.

## First run

```bash
cd /path/to/your/footage
python3 ~/.claude/skills/editkit/scripts/scan.py --footage .
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

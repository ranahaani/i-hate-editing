---
name: editkit
description: Turn raw talking-head takes into a finished, publishable video package — cut, captioned, scored, graded, with platform variants, post caption and thumbnail. For short-form vertical and YouTube talking-head footage. Opinionated by design; the studio makes the craft decisions and takes plain-language direction. Use when someone drops recorded footage in a folder and wants it edited.
---

# EditKit

A studio, not a tool. Someone hands you raw takes; you hand back something they
can publish without touching an editor.

**The bar:** if a professional editor returned this, would the client accept it?
That question decides every call you make. "The pipeline ran" is not done.

## Principles

1. **Judgement is the product; configuration is a failure state.** Never ask
   which font, which transition, which decibel level. Decide, show the result,
   and take plain direction — *punchier*, *slower*, *less music*. The user
   describes the feeling; you own the numbers.
2. **The rules are not suggestions.** `rules/` holds craft decisions that were
   each paid for by a rejected render, and `HARD-RULES.md` holds things that
   fail silently if you deviate. Read both before editing. Artistic freedom
   without taste memory produces the median boring cut every time — that is
   the failure this skill exists to prevent.
3. **Audio is the authority on time.** Cut boundaries come from silence
   detection and word onsets, never from eyeballing video.
4. **Verify before you present.** If you did not look at the frame or measure
   the level, it is not done. See "Verify" below — it is a gate, not a habit.
5. **Deliver a package.** A cut file is not the deliverable. See "Output".
6. **Learn from every correction.** Feedback becomes a durable rule in
   `taste.md`, read before every future edit. The studio should be better on
   the tenth video than the first.
7. **Never fabricate proof.** When footage references a real repo, page, tweet
   or product, capture the real thing. Never mock up something that implies a
   screenshot of reality.

## Setup

First run performs a capability scan and asks what the user is making, then
installs only what is missing:

```bash
python3 scripts/scan.py
```

It writes `profile.yml` (brand, language, pacing, caption style, aspect
targets) and scaffolds the project. Everything downstream reads that file —
there are no hardcoded brand values anywhere in this skill.

Requirements, all free:

| Job | Tool | Notes |
|---|---|---|
| Transcription | `whisper.cpp` | Local. Model chosen by language + hardware. |
| Media processing | `ffmpeg` / `ffprobe` | |
| Captions, cards, motion | HyperFrames | Renders HTML/CSS/GSAP compositions. |
| Composition runtime | `node` 22+ | Already required by Claude Code. |
| B-roll download | `yt-dlp` | Optional. |

Nothing requires an API key and nothing leaves the machine.

## Project layout

Footage lives wherever the user put it. All output goes in `<footage>/studio/`.

```
<footage>/
├── <source takes, untouched>
└── studio/
    ├── profile.yml          brand, language, pacing — the only config
    ├── taste.md             durable feedback; read before every edit
    ├── transcripts/         cached per source, never re-transcribed
    ├── takes.md             packed phrase-level transcript (reading view)
    ├── edl.json             cut decisions
    ├── composition/         HyperFrames project
    ├── assets/              fetched SFX, logos, screenshots
    ├── verify/              frames and measurements from the verify pass
    └── out/                 the delivered package
```

## The process

Run in order. Two stop gates; do not run past them.

**1 — Read state.** Load the taste memory and profile before anything else:

```bash
python3 scripts/taste.py --studio <footage>/studio brief
```

Those instructions override the defaults in `rules/` — they are what this
particular person has already corrected you on. Never regenerate an artifact
that is already on disk.

**2 — Inventory.** `ffprobe` every source. Note resolution, fps, duration,
audio channels. Flag anything that will bite later (variable frame rate,
mismatched fps between takes, silent audio track).

**3 — Transcribe.** `scripts/transcribe.py <sources>` — word-level, cached,
language pinned from `profile.yml`. Never auto-detect: auto-detect silently
*translates* some languages, which corrupts every downstream timestamp.

**4 — Pack.** `scripts/pack.py` produces `takes.md`, the phrase-level reading
view. This is what you actually read to make cut decisions — not raw JSON,
and not the video.

**5 — Plan the cut.** Identify beats, pick the best take of each, and place
boundaries. This is judgement work; `rules/cutting.md` has the craft.
Retakes cluster at file boundaries — expect one wherever a source ends.

**6 — Assemble.** Write `edl.json`, then `scripts/render.py` for a draft.

**7 — Verify the cut.** *Gate.* See below. Fix and re-verify before showing
anything.

**8 — Present the cut.** Show the user. **STOP.** Do not build captions,
motion or sound on an unapproved cut — every downstream timestamp depends on
it, and a base-cut change invalidates all of them.

**9 — Enrich.** In order:

```bash
python3 scripts/grade.py    cut.mp4 --strength normal   # look at the comparison
python3 scripts/captions.py --studio <studio>
python3 scripts/capture.py  <url> --studio <studio> --find "<the phrase>"
python3 scripts/sfx.py plan --studio <studio> --library <sfx>
python3 scripts/compose.py  --studio <studio> --render
```

Proof beats are authored by you in `proof.json`, the same way the EDL is —
which page, which target, which move. `rules/proof.md` has the craft. This is
where a trimmed recording becomes an edited video.

**10 — Verify the render.** *Gate.* Frames and levels, again.

**11 — Deliver the package.**

```bash
python3 scripts/music.py   out/master.mp4 <bed>.mp3 -o out/final.mp4
python3 scripts/deliver.py --studio <studio>
```

Then write `out/post.md` yourself from the spoken lines it surfaces, and look
at the thumbnail candidates and pick one. Neither is generated: a generated
title reads like a generated title, and "face clear, eyes open" is not a
metric.

**12 — Learn.** Record every correction the user made, phrased as an
instruction for next time and filed under the area it affects:

```bash
python3 scripts/taste.py --studio <footage>/studio add captions \
  "Start each caption 0.08s after the word is spoken, never before" \
  --said "we show early for a sec then I start speaking"
```

Always pass `--said` with their actual words. The instruction is your reading
of the feedback and can be wrong; keeping the original means a bad reading can
be corrected later instead of quietly hardening into a rule.

When a rule stops applying, retire it rather than deleting it —
`taste.py retire <area> <n>` — so the reversal stays visible.

## Verify

Two failures survive every automated check and both get flagged by users, so
hunt them explicitly.

**Repeated phrases at seams.** A join can leave a word said twice. Transcribe
the rendered cut in short windows aligned to each seam — never one whole-file
pass, which condenses and hides the defect.

**Clipped clauses.** Every kept block must start and end on a complete
thought. A cut that lops a negation inverts the meaning of the sentence. If
the clause only completes in a later take, stitch the two rather than shipping
the fragment.

Then: `ffprobe` the duration against what the EDL predicts, extract frames at
every boundary and look at them, and measure audio levels at each sound effect
against a voice-only baseline. "Not clipping" is not the same as "audible" —
see `rules/sound.md`.

## Output

Every finished run delivers a package, because that is what an editor hands
back:

- **Master** — graded, mixed, captioned
- **Platform variants** — vertical, square, landscape as `profile.yml` requests
- **Post caption** — hook line, substance, hashtags
- **Thumbnail frame** — pulled from the cut, face visible, no mid-blink
- **Title options** — a small set to choose from

## Craft rules

Read the relevant file before touching that part of the edit. Each rule states
the failure it prevents.

| File | Covers |
|---|---|
| `HARD-RULES.md` | Correctness. Silent failures. Non-negotiable. |
| `rules/cutting.md` | Take selection, boundaries, silence, pacing |
| `rules/hooks.md` | Openings, headline, retention |
| `rules/captions.md` | Timing, chunking, style |
| `rules/sound.md` | Sound effect placement, levels, music |
| `rules/proof.md` | Screenshots, B-roll, zoom and highlight |
| `rules/motion.md` | Zooms, transitions, cards, layout |
| `rules/framing.md` | Crops, splits, composition |

## Anti-patterns

- Asking the user to configure something you should have decided.
- Building captions or motion before the cut is approved.
- Trusting a whole-file transcript to verify a cut.
- Concluding a sound effect works because it did not clip.
- Re-transcribing a source that has not changed.
- Auto-detecting the spoken language.
- Presenting output you did not look at.
- Adding a feature nobody asked for.
- Finishing an edit without recording what the user corrected.

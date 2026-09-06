# Security Policy

## Reporting a vulnerability

Open a [private security advisory](https://github.com/ranahaani/i-hate-editing/security/advisories/new)
on this repository, or email the maintainer listed on the GitHub profile.
Please include steps to reproduce and impact. Do not open a public issue for
exploitable findings until a fix is available.

## What this project does (and does not) do

i-hate-editing is a **local** agent skill. Footage, transcripts, and renders
stay on the machine that runs it. There is no hosted backend and no required
cloud transcription API.

That does not mean every script is safe to expose to an untrusted network or
untrusted input.

## Surfaces to be aware of

### Review server (`scripts/review.py`)

By default the review UI binds **localhost only** (`127.0.0.1`).

`--lan` binds `0.0.0.0` and prints a phone/LAN URL so you can preview on
another device. That server has **no authentication** and serves files from
the output directory (renders, `post.md`, etc.). Only use `--lan` on a
trusted network. Prefer a USB/cable preview or localhost when on public Wi‑Fi.

### Optional LLM shell (`scripts/proofread.py --llm`)

`--llm` runs the string you pass through the shell (`shell=True`) with the
caption prompt on stdin. Treat that argument as a shell command: only pass
commands you trust (for example an agent-owned wrapper). Do not interpolate
untrusted user text into `--llm`.

### Proof capture (`scripts/capture.py`)

Playwright navigates to whatever URL you pass. Pointing it at internal hosts
(`http://127.0.0.1`, `file://`, cloud metadata IPs, etc.) is possible. Only
capture pages you intend to open.

### Sound library installer (`scripts/sfx_library.py`)

Downloads free Mixkit preview MP3s over HTTPS and records the licence per
file. Network failures degrade gracefully; treat the remote host as an
untrusted content source and keep the library path under your home directory.

### Composition render (`npx hyperframes@…`)

Renders pull a **pinned** HyperFrames package via `npx`. Pinning reduces
supply-chain drift; still review upstream releases before bumping the pin in
`scripts/compose.py`.

## Out of scope for this policy

Misuse of `yt-dlp`, copyrighted music beds, or filming people without consent
is the operator's responsibility. See the README disclaimers.

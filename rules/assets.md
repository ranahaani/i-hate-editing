# Assets

Where the picture comes from when the speaker's line needs one. The order below
is the order to try. Stop at the first rung that gives a real answer; do not
generate what already exists.

Never ship a placeholder. A missing asset costs a few seconds; a fake one costs
trust (`rules/proof.md`).

---

## The order

| # | Source | Use it when |
|---|---|---|
| 1 | **Real proof**: capture the actual page | The line names a repo, product, page, number or tweet. Always first. 9:16 pieces are captured in mobile view (`rules/proof.md`). |
| 2 | **Reference clips**: `~/ai-me/reel-refs/media/` | A reference reel already shows the screen you need. Screens only, never the other creator's face (`rules/proof.md`, "Borrowed B-roll"). |
| 3 | **Designed scenes**: flick (Remotion) first, HyperFrames second | The line describes structure with no real artefact: a mechanism, a comparison, a counter, a payoff. `rules/scenes.md`. |
| 4 | **Generated stills, then animated** | Nothing real and nothing designed fits. Gemini image via the local proxy, then a held push-in. |
| 5 | **Generated video**: Google Flow | A still cannot carry the beat. Optional, only when content is genuinely lacking. |

Rungs 4 and 5 are **optional and fallback only.** Reaching for them to avoid
looking something up breaks rung 1.

---

## 2. Reference clips

`reel-refs/INDEX.md` lists every reference reel with its media directory. Before
building a beat that wants a screen, check whether a reference already has it.

- Use only windows where the other creator is **not** in frame. Map their
  presence across the whole clip first; the head arrives in the last frames,
  which a spot check at t=0.5 misses. The method is in `rules/proof.md`.
- Crop out any watermark or handle.
- If no clean window exists, the clip is not usable. Move down a rung.

## 3. Designed scenes

**Flick first.** Built-in Remotion templates beat hand-built HyperFrames cards
on this material, and they carry the real vendor logo with a palette taken from
it. HyperFrames renders the composition, captions and the simple band and hook
cards.

- Flick lives at `~/ai-me/research/flick`. Read
  `skills/flick/saved-animations/README.md` before writing a new scene.
- Panels render to `studio/assets/panels/*.mp4`: 1080×960 half panel,
  1080×1920 full frame.
- A card naming a product carries that product's real logo. No logo and no
  site: the profile palette, never an invented one.
- Hook effects live in `templates/hook/` (shatter text) and `scripts/grade.py`
  (`loss_red` window). Shatter text is a HyperFrames overlay on purpose: it is
  text over the face inside the composition (hard rule 20), not a designed
  scene, so flick-first does not apply to it.
- **brag** (`latent-spaces/brag`, MIT) was mined for hook effects and had no
  shatter, glitch or kinetic-type code, so nothing was copied
  (`templates/hook/NOTICE.md`). Its other motion work was not reviewed.

## 4. Generated stills

`scripts/gen_image.py "<full prompt>" --studio <studio> --name <beat> --animate 3`
generates through the local Gemini proxy (`/free-gemini`) and renders the
push-in in one call.

- **Prompt the literal object in the line**, never a metaphor. "Student" is a
  student at a desk. Three variants, under 1400 characters.
- Write the whole prompt: subject, setting, camera, light, composition with the
  empty regions named, mood, ban list. A short prompt returns stock-photo
  cliché.
- It must not imply a screenshot of something real.
- Reject any output with visible text artefacts or a watermark.

## 5. Generated video

`~/.claude/skills/google-flow/scripts/flow generate --aspect-ratio 9:16`.

- **Flow first.** Verified on 2026-09-15 (`google-flow/references/provider-matrix.md`):
  Veo 3.1 Lite on the default ego profile returned a clean 720×1280, 6s clip
  with no watermark. The three pooled accounts were **not** signed in then
  (`cookiesSaved: false`). Run `flow doctor` and `flow accounts status` first;
  if nothing is signed in, this rung is closed. Say so and use rung 4.
- **Plan for the wait.** The matrix measured over 10 minutes per clip
  (`--timeout 1800`) and rate-limits on high traffic. Start it early or skip it.
- **PixVerse is a last resort and usually not usable.** `broll-gen` falls
  through to the PixVerse browser backend, which returned watermarked
  landscape clips. The google-flow provider matrix records that no PixVerse
  clip was validated. Run the skill's validator before using any of it.
- **Never ship a watermarked or landscape clip.** Run
  `google-flow/scripts/validate-media.mjs` on every generated clip. A failure
  means regenerate, crop, or move to rung 4.
- Generated people and places must read as clearly generated, not as footage of
  something real.

---

## Naming an entity: face, then logo, then icon

When a hook, headline or card is about a named company, product or person, the
visual for it comes from this ladder. Take the first rung that is suitable.

| # | Visual | Suitable when |
|---|---|---|
| 1 | **A person's face**: the recognised public face of that entity | A clear, front-facing, well-lit photo exists, it reads at 120 px, and the person is genuinely the face of the thing (founder, spokesperson). |
| 2 | **The logo** | No suitable face, or the face would imply the person said or endorsed something. The real vendor mark, never a redraw. |
| 3 | **An icon** | The logo is unusable (a wordmark too wide for the slot, an unreadable mark at small size). A neutral concept icon from `scripts/icons.py`: a key for API keys, a clock for a limit. |

Used on the last reel: nvidia-nim final-v6 took rung 3 (a key icon) for "free
LLM API". For Anthropic, rung 1 is the photo registered in
`assets/people/` (see below).

**Rules for rung 1, because a real person's face is the riskiest asset here:**

- **The mapping is the user's call, never inferred.** Do not work out who is in
  a photo from the face. A face is registered for an entity only when the user
  has said which entity it stands for, in `assets/people/manifest.json`, along
  with where the photo came from.
- **Source and licence are recorded**, or recorded as unknown. Unknown is
  allowed to be used only because the user supplied it; it is never presented
  as cleared.
- **It must not imply the person said the line.** A face beside a headline
  reads as an endorsement or a quote. Keep it as a small chip next to the
  entity name, never a full-frame portrait under their own words, and never
  with text that reads as theirs.
- **Crop, do not alter.** No generated, retouched or composited faces. A
  generated face standing in for a real person is fabrication
  (`rules/proof.md`).
- **If the photo is poor, drop to rung 2.** Low resolution, a hand or object
  covering the face, a profile angle, or a background too busy to crop to a
  circle all count.

The headline chip, entity beats and logo cards all take their accent colour
from the mark that won the ladder.

---

## Standing constraints

- **Memes are desi only**: memes.co.in (Paresh Rawal, Amrish Puri), never US
  meme culture. Crop the bottom-left watermark.
- **Dwell time**: nothing on screen under 1.5s or over 3s.
- **Nothing is added unprompted**: no captions, GIFs or cards the user did not
  ask for.
- **Sound mixes in ffmpeg**, never inside HyperFrames (`rules/sound.md`).

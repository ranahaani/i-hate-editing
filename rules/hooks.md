# Hooks

The first three seconds decide whether the rest of the edit is ever seen. No
amount of craft later recovers a hook that lost the viewer.

---

## The studio decides the design. It does not ask.

Which mark to use, how big the headline is, where it sits, which word takes
the accent, and which semantic treatment fires are the studio's calls, made
from the footage and the script. Asking the user "face or logo?" or "where
should the text go?" is a failure of this skill.

`scripts/hook_plan.py` makes those calls and writes `hook_plan.json`:

- **Mark:** walk the ladder in `rules/assets.md` (face, then logo, then icon)
  and take the first suitable rung. The plan records why a rung was rejected.
- **Size:** the largest type that fits the clear zone, within the 3–5 word
  rule. Small type is a defect; the plan must not return text under the
  minimum height.
- **Placement:** from the measured face box after zoom (`safe_zone.py`).
- **Accent:** from the mark that won the ladder.
- **Treatment:** at most one semantic treatment, from the word's meaning.

The user corrects the result in plain language ("bigger", "use the logo") and
that goes to `taste.md`. They are never asked to configure it up front.

---

## Three hooks run at once — all three, every time

Never lean on one. The first frame must hit from three angles at once, and all
three must make the *same* promise. Conflicting cues cause an immediate skip.

- **Visual** — sudden movement, a change in lighting, an unusual angle, an
  expressive reaction, or a pattern interrupt: something unexpected. A static
  frame is the weakest possible opening.
- **Verbal** — the very first words heard: a bold claim, a relatable pain, or
  a tease. Under about ten words so it completes inside the window.
- **Text** — large, high-contrast, and it must make sense **with the sound
  off**. Most viewers are muted, so text that only works alongside the audio is
  text that does not work.

**Place hook text where the face is not.** Never over the eyes, nose or mouth,
and never over the face at any moment of any word. The position is chosen per
hook from the measured frame, not from a fixed line:

1. **Measure the face box** at the hook's first frame and again after every
   zoom. A punch-in moves the face; text placed before the zoom lands on it
   after. Do not eyeball it.
2. **Keep only zones that are clear of the interface and inside the 4:5 crop.**
   The header covers the top band; the caption, buttons and progress bar cover
   the bottom and right edge. `scripts/safe_zone.py` holds the numbers.
3. **Rank the clear zones by gap from the face**, widest first. Chest-up
   framing usually wins below the chin; a wide frame with headroom may win
   above the head; a face framed off-centre leaves a side column.
4. **If no zone clears the face, shrink or move the text. Never overlap.**
   `safe_zone.py` returns a shrink factor, or none. A 1.55 close-up of a
   chest-up face usually leaves no room at all (on 3 test clips, 2 returned a
   shrink of 0.50–0.62 and 1 returned none). Then the text goes to the headline
   band, a card, or waits for a wider shot. It does not go on the face.
5. **Keep the zone for the whole phrase.** Moving text between words reads as
   jitter. Re-pick only at a cut.

High contrast, with a drop shadow or outline, always.

### Rank the words, do not set them all equal

Only the one word carrying the claim is large and carries the accent colour.
Connectors stay small and white. A hook where every word is the same size has
no entry point. Observed in reference reel `DZwy1E7pEoR`: the key word
("Student", "Country") is oversized and gradient-filled while "har" and "ke
liye" are small and plain.

**Disrupt the frame inside the first two seconds.** The brain needs a sensory
reset: a micro-zoom, a jump cut, or a graphic sliding in. Two seconds of an
unchanging frame is already too long, whatever is being said over it.

**Kill the intro.** No dead air, no slow build, no logo. Open on the claim.

## Frame one is a face

Open on the speaker, never on a design card, a logo, or a title screen. A
designed opening frame reads as an advert and gets swiped past; a face reads as
a person about to tell you something.

This also decides the thumbnail, since most platforms take an early frame by
default.

## The split-proof hook (default when there is something real to show)

Measured on five tech reels on 2026-10-02 (`reel-refs/hooks-2026-10-02`:
Ddstvr2vZQM, DdriJi7gDwp, Ddk71qSSNMx, DdgwI6voxz6, DcBs-YVhYy8) with 10 fps
contact sheets, `scdet` cuts, word-level whisper and a spectral-flux pass.
All five use the same structure; `scripts/hook_storyboard.py` encodes it and
`hook_plan.py --proof <capture>` turns it on.

- **Split from frame 0.** Top half: the real thing (repo page, product page,
  the person named, an animated UI of the tool). Bottom half: the speaker. The
  face is still on frame 1, so "frame one is a face" holds.
- **A brand card on the proof.** A white rounded card with the logo sits on
  the dimmed capture (the GitHub card in Ddstvr2vZQM, the app icon in
  DdriJi7gDwp). It is readable on frame 0, not animated in.
- **Text on the seam.** Either a two-tier headline at the bottom of the top
  panel (serif italic kicker plus a bold sans line, DcBs-YVhYy8 "Elon Musk Just
  Open-Sourced / X'S ALGORITHM") or a short caption pill right on the seam
  (Ddstvr2vZQM, Ddk71qSSNMx). Never on the face.
- **The top panel changes once at 1.10-1.30s** (first `scdet` cut: 1.10,
  1.28, 1.30, 1.27; Ddk71qSSNMx scrolls the page instead and cuts at 2.17).
  The second change lands at 2.2-3.0s. The face half does not cut.
- **The verbal hook is one sentence of 9-13 words, finished by 3.5-4.2s.** It
  opens with a news verb or a "this" pointer: "Someone just open sourced",
  "This GitHub repo will give you", "Apparently this repo", "If you're
  building AI agents", "Elon Musk just open-sourced". All in the first 0.1s.
- **Sound is quiet and continuous.** Every reel keeps a bed under the voice
  (10th-percentile floor -31 to -37 dBFS against voice peaks of -9 to -14).
  Stings are sparse: at most one or two in the first 4s, and they sit on a
  panel change, not on every word (DdriJi7gDwp 1.44s after the 1.30s cut,
  Ddk71qSSNMx 4.06s after the 3.90s cut).
- **Captions are small.** One to three words in a pill or plain white with a
  shadow, at the seam. The headline carries the size, the caption does not.

How this studio builds it (NVIDIA reel final-v7, 2026-10-02):

| Time | Top panel | Text | Sound |
|---|---|---|---|
| 0.00 | Real capture, dimmed, slow push-in; white logo card on it | Kicker + claim line on the seam | Impact, peak about 0.18s |
| claim word, or 1.2s | Card leaves; zoom onto a real highlight target | unchanged | Swoosh on the swap |
| +0.30s | Accent ring lands on the target | unchanged | Click |
| about 1.9s | Next proof panel | Headline slides out | Existing beat stings |

When there is no real capture, do not fake one: the hook stays an overlay
(headline above the head, the rest of this file). A split with a designed card
on top is the thing `rules/proof.md` forbids.

**When the hook states a problem and nothing real shows it** (promptive
final-v5: "your limit runs out", and no capture of a limit message exists),
the top half is an HD motion graphic built at frame resolution. The named
tools' marks pop on their spoken names, a usage meter fills to 100%, and the
loss word turns the whole frame red. Never mock up the error message itself.

**The first-frame text is 2-3 familiar words plus one emoji** ("CLAUDE / LIMIT
ISSUE 😕"), not the whole sentence and not a kicker line. The speaker says the
sentence; the text names the topic the viewer already recognises.

**The top panel in the first 3 seconds must be HD.** Use a motion graphic
rendered at 1080 wide, an HD image or HD video, or a Flick/Remotion scene. An
upscaled or dimmed screenshot reads as blurry: a 1280x800 capture scaled into
the 1080x960 half was rejected on 2026-10-02.

### Pick the hook type before designing it

From swngproductions.com/crafting-video-openings and
opus.pro/blog/instagram-reels-hook-formulas (read 2026-10-02):

- **Problem then solution:** state the pain, show the fix by about 2s. This
  is the default for tool reels ("limit runs out" then "this one extension").
- **Contrarian:** "Everyone says X, but Y" or "Stop X, do this instead". Only
  when the claim can be backed up in the reel.
- **Mistake:** "I lost X because I Y". Needs a real loss.
- **Numbered list:** "N things that Z", N between 3 and 7, one beat per second,
  and the reel must deliver exactly N.
- **Time-based:** "How I got X in Y days".
- **Question:** never an easy yes/no question. It must challenge what the
  viewer thinks they know.
- **Sound break:** a distinct tap, switch or sting before the first word.

Timing and craft numbers from the same sources:

- About **1.7s** to win attention. Interrupt for 1-2s, then 2-3s of context.
- **Say or show the benefit by second 2.** Brand or product name inside 2-3s.
- **One hook, one idea.** Do not stack features in the opening.
- **1-2 short caption lines,** high contrast. Calm the background motion while
  text is on screen.
- **Trim every micro-pause** in the first 3s.
- **Vague lines fail:** "This changed everything" and "You need to see this"
  promise nothing specific.
- **The hook's promise must match the content.** A mismatch costs retention
  later in the reel.
- 3-second hold: above 60% is strong, 70-80% is excellent. Test variants by
  changing only the opening seconds.

The loss-red grade (semantic treatment below) still applies inside a split
hook when the claim is a loss word. It is the one treatment; do not add it on a
win word like "free".

---

## Three tests every hook must pass

Standing advice from the short-form guides, kept as a checklist because each
item maps to something this studio can verify in a frame:

1. **Something unexpected moves at the start**: a sudden zoom-in, an object
   dropping, someone entering frame. The headline's own entrance counts.
2. **The result, or the core prop, is visible early.** Show what the viewer
   gets before explaining it. If the result cannot go in the first frame
   (frame one is the face), it goes inside the first three seconds.
3. **A bold title of three to five words** states the promise.

Fail any of the three and the hook is not done, however clean the rest is.

## Build the hook in layers

A raw take becomes a premium hook by adding one new sense per layer, in this
order, with nothing repeated. Source: a layer-by-layer breakdown reel
(`DZwy1E7pEoR`) that replays one 3-second line six times with one more layer
each time. The order below is what it shows; the thresholds are working
defaults to test against Skip Rate, not measured facts.

| # | Layer | What it adds |
|---|---|---|
| 1 | Raw | Baseline. Usually flat, wide, face small. |
| 2 | Grade | Contrast and warmth; `scripts/grade.py`. |
| 3 | Track + zoom | Face fills about two thirds of the frame and the frame is never static. |
| 4 | Text | Ranked words, placed by the zone rule above. |
| 5 | Keyword animation | The claim word gets its own entrance and a literal picture. |
| 6 | World + sound | Semantic grade, b-roll behind the subject, and the designed sound. |

**Do not skip to layer 6.** A hook with effects and no framing is noisier, not
better. Each layer must be visible in the frame on its own.

**Every picture is the literal object in the line.** "Student" gets a student,
"country" gets a map. Never a metaphor. See `rules/scenes.md`.

## Semantic treatment

Style follows meaning. Pick it from what the word *is*, once per hook, on the
single word that carries it.

| The word is… | Treatment |
|---|---|
| A negation or a loss ("not", "never", "dead", "wrong") | Warm-red grade for the length of the word, text **shatters** on it |
| A number or a win | Held zoom and a bright accent on the figure; no grade change |
| A named thing (a country, a tool, a person) | Literal b-roll for that thing, see below |
| Everything else | No treatment |

**Budget: one treatment per hook.** Two in 3 seconds reads as a preset. A
shatter and a red grade together count as one — they are the same beat.

**Shatter text** breaks the word into pieces that fly outward over about
0.4 seconds, timed to the impact sound. It is a payoff device, so it fires
once, on the word that negates or breaks something, and never on a neutral
word. Specification and render code: `templates/hook/`.

**The grade shifts the whole frame for the word, then returns.** Hold the red
for the word plus a short tail; staying red past the word makes the next
sentence read as angry. Never use it on a word that is not negative.

## The world behind the speaker

b-roll can sit **behind** the speaker, with their body cut out over it: a map
behind "country", a classroom behind "student". It reads as a composited shot,
where a card over the face reads as a pasted one.

**This is gated, because it has failed before.** An earlier background replace
measured 31% of source detail on a moving hand and 19% on the face
(`reference_virtual_bg_skill` in memory). The rule is therefore:

- Never ship it without a measured detail check on a moving region, 85% or
  better against the source. Measured, not looked at.
- **The detail ratio alone is not enough.** The first real test passed it
  (hands 108%, face 106%) and still had a visible defect: the held mic was
  matted out, leaving a hole showing the map, and a motion-blurred hand went
  semi-transparent. Sharp pixels that the plate shows through still score as
  sharp. The script therefore also gates matte integrity, the share of the
  speaker's interior with alpha under 250. Its 1% limit was chosen after seeing
  the defect, so treat it as unvalidated.
- **Anything held in hand is a risk.** Mics, phones and pens get matted out.
  Look at every frame of the window for what the speaker holds.
- Keep it to the one keyword window (1.5–3 seconds), not the whole hook.
- Take the subject's pixels from the source; blend only at the matte edge.
- If the check fails, fall back to a card above the head. Do not ship the
  composite "because it looks fine on three frames".

Implementation and the gate: `scripts/cutout_broll.py`.

---

## The headline

Every short-form piece carries a headline across the **top** of the frame
during the hook — the promise of what the viewer is about to get. It is not the
caption of what is being said. It is the reason to keep watching.

- **Three to five words.** One idea. Benefit or curiosity, not description.
  Six is the ceiling.
- **Stacked type, not a slab.** Two or three short lines, left-aligned, heavy
  weight, with the one claim word in the accent colour. A flat coloured box
  with a sentence in it reads as a banner ad, and it wraps badly: a line
  break that strands one word ("…RUNS / OUT") is a defect. Break by meaning.
  Reference: the nvidia-nim reel, final-v6 (a key icon beside stacked
  "FREE / LLM API" in yellow, white and green) against the promptive-sentry
  v2 hook (a yellow box wrapping "WHEN YOUR LIMIT RUNS / OUT"), which was
  redesigned for exactly this.
- **A mark sits beside it.** The entity the headline is about gets a visual
  from the ladder in `rules/assets.md`: a person's face, else the logo, else
  an icon. The accent colour comes from that mark.
- **It arrives with motion**, inside the first 0.3 seconds: a scale-snap or a
  slide, never a fade. A headline that appears without movement is not a
  pattern interrupt.
- **Top band, never over the face.** It lives in the empty space above the
  head. Covering the face with text defeats the point of opening on one.
- **Holds for the whole hook**, then leaves when the body starts.
- **Doubles as the thumbnail line**, so write it to work as a still.

"Free AI models, unlimited tokens" is a promise. "About prompt engineering" is
a description. Only one of them earns the next three seconds.

---

## What the hook says

**Open on the first complete thought.** If the speaker restarted, keep the last
attempt. A hook that begins mid-throat-clear has already lost.

**Lead with the claim, not the preamble.** "Here's a thing I found interesting"
is preamble. The claim is the thing.

**A personal anecdote beats a scripted line.** When the speaker improvises an
opening from their own experience it consistently outperforms the written one.
If there is a take where they went off-script and it works, use it.

---

## The beat after the hook

Hold roughly half a second of real footage with no speech between the hook and
the body, and put the sound sting there — a riser resolving into an impact.

The rhythm is **claim → [hit, no voice] → body**. Without the beat the hook
runs into the explanation and neither lands. Do not trim that pause away; the
cutting rules preserve it deliberately.

---

## Proof early

If there is a number, a screenshot, or a real page that backs the claim, show
it inside the first three seconds — it doubles as the visual hook, and a real
page appearing under a spoken claim is a stronger interrupt than any designed
card. A claim with a receipt attached is a different
proposition from a claim alone, and this is the moment the viewer is deciding
whether the speaker actually knows anything.

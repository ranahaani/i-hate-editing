# Sound

Sound design is what separates an edit from a trimmed recording. It is also
where the most expensive silent failure in this whole pipeline lives — see
"Audibility" below, and hard rule 11.

---

## Audibility — the failure that passes every check

**A sound effect can play, not clip, and still be inaudible.**

Many library files do not have their loud transient at the start. If the window
you play is shorter than the file, or starts before the peak, the mix contains
only the quiet lead-in. Every level check passes. The render completes. The
sound is simply not there.

Verify by sweeping the source file, not by measuring the window you chose:

```bash
python3 scripts/sound.py inspect assets/sfx/riser/riser.mp3
```

If the peak inside your window is more than 3 dB quieter than the file's true
peak, the window is missing it. Two fixes:

- **Extend** the window so it reaches the existing peak, or
- **Trim** the loud tail into its own short asset so the peak lands exactly on
  the beat:
  `ffmpeg -sseof -<N> -i in.mp3 -af "afade=t=in:st=0:d=0.1" out.mp3`

A file that is quiet *throughout* is a different problem — that one needs
pre-amplification, not trimming.

**Confirm on the rendered output, never on the composition.** A structural
check validates that the audio element exists. It cannot tell you whether a
human would hear it. Measure the final file.

**Measure by differencing, not by reading the master.** Hard rule 11. Wherever
a sting sits under speech, the loudest thing in that window is the voice, so a
level taken from the master describes the voice and not the sting.
`scripts/sound.py check` works this way: on a talking-head mix it reports every
sting as TOO LOUD, and following it once cut 26 stings by ~6 dB into silence
while its own arithmetic said they were too loud.

The honest measurement is the master **minus** the voice-only cut:

1. `compose.py` attenuates the video's own audio by 2–3 dB when other tracks
   are present. Measure that first: `mean_volume` over three or four sting-free
   speech windows in both files, averaged.
2. Per sting: `lift = (master_peak + attenuation) - cut_peak`, over a 0.25s
   window starting 0.05s before the hit.
3. Target a **+2 to +4 dB mean lift (centre +3.1)**, with nothing below +1 or
   above +8. On 2026-10-02 every sting was cut by 10% in amplitude (-0.9 dB)
   because the old +3 to +5 band read as too loud next to the enhanced voice.

A negative lift is physically impossible from addition. Seeing one means step 1
was skipped.

**Do not aim at a `data-volume` number.** It is not comparable across assets
with different normalisation — a 0.65 on a pre-boosted file and a 0.65 on a raw
one deliver very different levels. Measure the lift instead.

**Master the finished mix to −15 LUFS** with linear `loudnorm`. The render
lands 2–3 dB under the cut, which reads quiet next to other reels.

---

## Levels

Absolute targets, measured on the finished mix:

| Element | Peak | Note |
|---|---|---|
| Voice | −3 to −6 dBFS | Loud and clear; it is the whole point |
| Transient SFX | −10 to −18 dBFS | Felt, not heard. Never louder than the voice's peak |
| Music bed | −18 to −22 dBFS | Under everything, ducked further under speech |
| Textural bed | −20 to −30 dBFS | Should register only if removed |

These sit alongside the relative rule below, they do not replace it: a
transient at −12 dBFS still reads 3–5 dB above *typical* speech, because
typical speech sits well under its own peaks.

**Measure that baseline on a voice-only moment, not on the file mean.**
`volumedetect`'s `mean_volume` averages in every silence and every gap, so it
reads several dB below actual speech. Calibrating "+4 dB over typical voice"
against the file mean puts the stings *under* real speech, which is how the
2026-09-09 google-ai-tools mix passed its own arithmetic and still came back
from the creator as flat. Take a 1–2s window of continuous speech, measure
that, and size the transients off it.

**Transients ride above the voice. Beds sit under it.**

| Kind | Duration | Level |
|---|---|---|
| Transient — whoosh, pop, impact, riser resolve | under ~1s | peak **3–5 dB above** a voice-only moment |
| Bed — texture held under a scene, music | over ~1s | clearly **under** the voice throughout |

These are not in conflict. A transient is punctuation; burying it defeats the
point. A bed that rides above the voice competes with the speaker.

Library files are usually quiet — commonly 23 to 32 dB under the voice — so
nominal volumes bury them. Pre-amplify into a louder set rather than pushing
per-clip gain to extremes:
`volume=+7..13dB,alimiter=limit=0.95`

**Music sits well under everything** and ducks further under speech. Err
toward audible rather than tasteful-but-inaudible; a bed nobody notices is
doing nothing.

---

## Placement

**Every layout change gets a sound — including every card.** This is the
floor, and it outranks the density ceiling below. More than half of one edit
shipped with graphics arriving in silence because the ceiling was thinning
them; a card that appears without a sound reads as unfinished. The ceiling
governs optional accents only.

 A visual transition in silence reads as a
missing asset. Whoosh on the movement, pop on the element that lands.

**Anything that pops off makes a sound.** A celebration, flash, or hero stat
landing in silence reads as a bug.

**Never stack a pop and an impact on the same frame.** They mush into one
distorted blob. Where an impact lands, drop the pop — the impact already
carries the transient. Put any notification 0.2–0.3s *after* the impact, never
on it.

**Frame-perfect or it feels disconnected.** The sound's *peak* — not its start
— lands within about two frames of the visual it marks. Back-shift the start so
the loud part, not the silent lead-in, coincides with the picture.

---

## Reference mix

When in doubt, match a reel that landed rather than an abstract target.

**gnhf / "good night, have fun" (2026-09-06) — judged good by the creator:**

| | gnhf (good) | google-ai-tools v10 (flat) |
|---|---|---|
| stings | 26 in 36.1s (0.72/s) | 27 in 47.8s (0.56/s) |
| `data-volume` | 0.45–0.85, mean **0.65** | 0.25–0.37, mean **0.33** |
| distinct categories | 8 | 4 |
| programme loudness | −15.2 LUFS | −11.7 LUFS |

Roughly 6 dB less sting against a 3.5 dB louder voice: a ~9.5 dB worse
sting-to-voice ratio. That gap, not absolute level, is what gets heard as "the
old one sounded better". Start at mean `data-volume` ≈ 0.65 and keep programme
loudness nearer −15 LUFS than −12.

gnhf also spent eight roles from the table in "Semantics" below, where v10 used
four and never touched `glitch` or `click`, the two that mark screen cuts and
list rows. **Range of roles is what to copy from it — not its sting count.**

**Do not sting a hard cut that a card already covers.** `sfx.py` fires a whoosh
on the cut *and* another on the card arriving 0.12s later, so a reel with six
card beats ends up with twelve near-identical whooshes and a creator asking why
it is all whoosh. Drop the cut's, keep the card's. Reported on 2026-09-14:
26 sounds → 21, whoosh+swoosh 15 → 6, and the piece got *more* varied, not less
paced.

Give each sting a job instead: pop for text or a keyword arriving, whoosh for
something sliding in, swoosh for a graphic leaving, glitch for cutting to a
screen, click for interface rows, sparkle for a creative reveal, impact for the
single biggest payoff.

---

## Density

**Floor:** at least one sound per layout change.
**Ceiling:** roughly three to five distinct sound moments per 15 seconds.

Above that it reads as auditory fatigue and people leave. The ceiling is a
budget on total moments, not permission to skip the mandatory ones — thin out
optional accents first.

---

## Under the voice

**Duck the music, do not just set it low.** A static level has to sit so far
down to stay clear of speech that nobody notices it. Sidechain it to the voice
so it recovers in the gaps.

**Dip further before the most important line.** Dropping the bed an extra few
dB just ahead of the payoff makes it land, and costs nothing.

**Layer a transition rather than reaching for one whoosh.** A low whoosh under
a short metallic hit reads as designed; the same whoosh on every cut reads as a
preset.

## The hook opener — sound inside the first 1.5 seconds

The first seconds are what Instagram's Skip Rate measures (the share of
viewers who leave within 3 seconds), and until now nothing in them was
designed: the first sound was the voice, and the first sting came after the
claim.

Anchor the hook with one low **hook opener** — a single hit, not a whoosh
stack — on the first visual change of the hook. Role `hook_open` in
`assets/sfx-taxonomy.json`, placed by `hook_open_event` in `scripts/sfx.py`.

- **Anchor:** the earliest seam, card, b-roll overlay or proof beat inside the
  opening 1.5 seconds. A per-range micro-zoom is not written to
  `timeline.json`, so it cannot anchor a hit.
- **Fallback:** with no visual event, it lands 0.15s after the first caption
  chunk's start (less the 0.08s caption bias), labelled "first word, no visual
  event" in the plan. This fallback is unverified; judge it by ear.
- **Never before 0.15s.** No anchor at all means no opener.
- **One hit.** It removes every other sound within 0.6s of itself, including the
  cut's and the card's whoosh, so the first 1.5s carries one sound.
- **Skipped when the post-hook riser/impact lands within 0.6s of the anchor**
  (an early first seam). The post-hook impact then stands alone.
- **It is mandatory, so it counts against the density ceiling and is never
  thinned.** It obeys "one role per sting".
- **Measure it like every other sting**: master minus voice-only, +2 to +4 dB.
  Measured on three clips with a plain ffmpeg sum: +3.0, +4.0, +6.5 (mean
  +4.5). Not measured through compose or the −15 LUFS pass, so the delivered
  mix gets the final say.
- It is **additional to** the post-hook sting below, not a replacement for it.

Status: a working default taken from creator-side sources, not a platform fact.
Retention effect is untested. Check it against Skip Rate on posted reels before
treating it as settled.

Known issue, not fixed: when the first seam is early, the post-hook riser can
start at 0.00 and play under the opener, with its peak not landing on its
impact. Inspect that mix by ear.

## The post-hook sting

After the opening claim, before the body begins, place a riser resolving into
an impact. This is separate from, and additional to, the transition whoosh and
pop.

It fires even when the cut has no pause there — but it lands far better when it
does, which is why `rules/cutting.md` says to preserve roughly half a second of
real footage at that point. The rhythm is: **claim → [hit, no voice] → body.**

Never hard-cut from a hook straight into the body with no sound at all.

---

## Semantics

Sound should mean something, not just fill space.

| Trigger | Sound |
|---|---|
| Layout transition | whoosh + pop |
| Text or element appears | pop |
| Screen recording underneath | keyboard, low |
| Something selected or circled | click |
| The single biggest reveal in the piece | notification, once only |
| The hook's first visual change (first 1.5s) | `hook_open`, one low hit |
| Building into a hero reveal | riser |
| The reveal itself | impact |
| Cutting to paper, receipt, document | paper tear |
| Cutting to a screen, retro filter, glitch | glitch |
| A key metric or tip landing | chime, paired with a held zoom |

## Defaults locked 2026-10-02

- **Voice first.** Run `scripts/enhance.py` (Adobe Podcast Enhance v2, site
  mix) on the cut before placing any sting. Level the result to about
  -18.4 LUFS with compression, then measure every sting against the enhanced
  voice-only file.
- **Pop sting:** `assets/sfx/pop_dragon.mp3`. Its peak is at 0.197s, so start
  it 0.197s before the word onset it marks.

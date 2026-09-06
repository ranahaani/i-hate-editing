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

---

## Levels

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
| Building into a hero reveal | riser |
| The reveal itself | impact |
| Cutting to paper, receipt, document | paper tear |
| Cutting to a screen, retro filter, glitch | glitch |
| A key metric or tip landing | chime, paired with a held zoom |

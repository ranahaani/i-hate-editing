# Motion

Motion is what separates an edit from a recording playing. The failure mode is
not too little movement — it is movement that is timid, constant, or unrelated
to what is being said.

---

## Err large

Timid zooms read as a mistake rather than a choice. A move the viewer is not
sure happened is worse than no move.

| Move | Scale |
|---|---|
| Punch on the face at a layout change | ~1.10 |
| Held zoom on a card's key word | 1.18–1.20 |
| Held zoom on the face | 1.24–1.30 |
| Slow drift across a still | 1.00 → 1.05 |

When in doubt, go bigger. The consistent correction on this material is *more*
zoom, never less.

---

## Hold the zoom, do not ride it

A **held** zoom punches in, stays at a constant scale for 1.3–1.6 seconds, then
eases back. Scale is fixed during the hold.

**Never continuously scale a detailed screenshot across a whole beat.** Every
frame gets resampled at a slightly different size and the result looks like the
image is vibrating. This reads as a rendering bug, and it was rejected on
sight. A held zoom has no shimmer because the scale does not change during the
hold.

---

## Something new every three seconds

A shot that holds still for more than about three seconds loses attention, and
this applies **inside** a single card's duration, not just between cards. A
panel that arrives once and then sits there for eight seconds is a defect even
though something did technically change at its start.

If a beat runs longer than four seconds, plan another event inside it: a card
swap, a logo, a cutaway, a held zoom on the key word, or a sound accent. Split
a two-sentence beat into two cards rather than stretching one across both.

The pacing default is the user's to override. If they say it feels too fast,
go to fewer, longer-held beats and keep the face on screen between them.

---

## Vary the entrance

No two consecutive elements arrive the same way. Slide, wipe, whip, scale —
rotate them. Repetition of a single entrance makes an edit feel automated,
which it is, and the point is that it should not look it.

---

## One thing at a time

**Never reveal two independent elements simultaneously.** The eye cannot track
both, so it tracks neither. One thing, a pause, then the next.

Applies to bullet reveals, to a card arriving while a logo pops, and to any
moment where two animations were placed at the same timestamp because they were
both "at that beat."

---

## Vary the shape, not just the timing

Repeating one card layout is the same defect as repeating one entrance. If
three consecutive beats are a headline with a sub-line, the piece reads as a
template even when the words differ. Rotate the *form*:

- A statement — kicker, headline, supporting line
- A numbered list, rows arriving one at a time
- A full-frame card where the graphic owns the screen and the face steps away
- A real screenshot with a zoom onto the thing being said

Pick the form from what the sentence is doing. A list of three things wants a
list; a single claim wants a statement; a payoff wants the full frame.

## Choosing the entrance

The arrival should mean something. Pick from what the element *is*, not from
variety alone — variety is the tiebreaker between equals, not the reason.

| Element | Arrival | Why |
|---|---|---|
| A card replacing the previous one | Slide from the side | Reads as a sequence: one thing pushes the last out |
| The first card after the speaker | Slide down from the top | Comes from outside the frame, so the face is not "replaced" |
| A single word, number or badge | Scale pop with a slight overshoot | Weight without travel; travel on a small object looks fussy |
| A logo or emoji | Scale pop, faster and smaller | It is an accent, not a statement |
| A screenshot or real page | Push in from the edge, then hold | Physical, like paper being placed down |
| Rows in a list | Slide in from the left, ~0.3s apart | One at a time, far enough apart to read as separate events. A tight stagger looks like one block fading in |
| A payoff or punchline | Hard cut in, masked by an impact | No animation at all is the strongest arrival when the moment earns it |
| Returning to the face | Slide the graphic away, do not fade | A fade reads as an ending; a slide reads as a handoff |

**Zoom is not an entrance.** Zoom emphasises something already on screen. If a
card zooms as it arrives, the viewer sees two moves competing and reads
neither.

## Cards are the fallback, not the goal

Real material always beats a designed card. When the speaker names a repo, a
page, a product or a number, show that thing. Reach for a card when there is
genuinely nothing real to show — an abstract claim, a summary, a transition of
topic — and for the call to action.

An edit where every beat is a card is a slideshow with a face attached.

## Easing

Never `linear` — it reads as robotic in every context.

- `power2.out` / `power3.out` for arrivals: fast in, slow landing.
- `back.out` for a pop that should overshoot slightly.
- `power2.inOut` for a continuous move like a scroll or a drift.

Add motion blur to anything that slides on quickly. Without it fast movement
looks choppy, which is one of the clearest amateur tells.

---

## Sync to the word

A move that lands on the word it illustrates feels authored. The same move
half a second early or late feels accidental.

Get the onset of the payoff word and start the animation early enough that its
*landing frame* coincides with the word being spoken. The default failure is
arriving late — the move begins on the word and completes after it.

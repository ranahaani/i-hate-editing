# Proof

When the speaker names a repo, article, product or number, show the real thing.
Proof shots are what make a talking-head video feel researched rather than just
talked, and they are the highest-value B-roll available because the material
already exists — it does not have to be designed.

---

## Never fabricate

Capture the actual page. Never mock up something that implies a screenshot of
reality, never retype a statistic into a designed card and present it as the
source, and never reuse a capture of a *different* subject because it looks
similar. A repo scroll from another project is fabricated evidence.

If the real thing cannot be captured, say so and cut the beat. A missing proof
shot costs a few seconds; a fabricated one costs trust.

---

## Capture a still, not a recording

`scripts/capture.py` takes one tall image of the whole page plus the
coordinates of the things worth pointing at.

This is deliberate. A screen recording bakes in its scroll speed permanently:
it cannot be re-synced when the cut changes, cannot slow down on the line that
matters, and cannot be zoomed mid-scroll. A still plus authored motion stays
frame-accurate and re-editable, and composites in the same timeline as the
face, captions and sound.

**Capture in the delivery aspect.** Vertical viewport for reels and shorts —
the desktop layout of most sites wastes two thirds of a 9:16 frame.

**Targets are found by text, not CSS selectors.** Selectors are per-site and
break the moment a layout changes; mobile layouts hide half of them outright.
Text is also how the beat is actually described: *zoom to the 100k stars*.

**Found in the DOM is not the same as visible on screen.** A narrow viewport
can truncate text with an ellipsis while the element's text content, and its
reported coordinates, stay complete. A repo name matched and returned a box,
but only its first letter actually drew — a highlight over it would have swept
across nothing. Check the captured image at the target's coordinates before
building a zoom or highlight on it, and if the text is not legible there, use
a different target or a different move.

**A missing target is a real answer.** If the text is not on the page at that
viewport, the capture says so. Do not substitute a near-match — check whether
the element is desktop-only, or point at something that is genuinely there.

---

## The three moves

**Scroll** — establish that the page is real and has substance. Keep it short;
this is context, not reading time. Scroll through content, never through
whitespace or a footer.

**Zoom** — land on the exact thing being said as it is said. The zoom target is
the word in the speech, not a general area of the page. A zoom that lands
somewhere near the subject reads as sloppier than no zoom at all.

**Highlight** — a marker sweeping left to right across the line, timed to the
phrase. Use `mix-blend-mode: multiply` so the text stays readable through the
colour; an opaque box covers the words it is meant to emphasise.

Reserve highlight for the single most important line in the shot. Highlighting
three things in one beat emphasises nothing.

---

## Timing

**The zoom lands on the spoken word.** Start the move early enough that it
*arrives* as the phrase is said — the payoff frame and the payoff word coincide.
Arriving late is the most common version of this mistake.

**Give a proof shot 2.5–4 seconds.** Under two seconds it flies past before the
viewer has parsed what they are looking at, which is worse than not showing it.
Longer than four and the face has been gone too long.

**The face returns.** A proof shot is a cutaway, not a new scene. Slide the
page in, hold, slide it out, and the speaker is back.

---

## Verify

Every proof beat, before shipping:

- **Content fills the frame.** No black band where the image ran out. Centring
  a target near the top or bottom of a page will do this unless the pan is
  clamped.
- **The scroll passes over real content**, not a dead stretch. Check frames
  across the whole beat, not just its first one.
- **The zoom target is the thing being said**, and it is legible at that scale.
- **The highlight covers the phrase**, not half of it and not the whole
  paragraph.

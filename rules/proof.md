# Proof

When the speaker names a repo, article, product or number, show the real thing.
Proof shots are what make a talking-head video feel researched rather than just
talked, and they are the highest-value B-roll available because the material
already exists — it does not have to be designed.

---

## If the piece names a real thing, show it

This is not optional and it is not a nice-to-have. When the speaker names a
repo, a product, a page or a number, the edit shows that thing — captured,
scrolled, zoomed onto the words being said, with the marker sweeping the line
that matters.

**A designed card is not a substitute.** A card saying "MEET PROMPT MASTER" is
a claim; the repo page is evidence. An edit that talks about a real artifact
for forty seconds and never shows it looks like the editor could not be
bothered to look it up.

**Not knowing the URL is not a reason to skip it.** Search for it. Ask. The
only acceptable reason to omit proof is that the thing genuinely does not exist
publicly — and then say so rather than quietly filling the beat with cards.

## Never fabricate

Capture the actual page. Never mock up something that implies a screenshot of
reality, never retype a statistic into a designed card and present it as the
source, and never reuse a capture of a *different* subject because it looks
similar. A repo scroll from another project is fabricated evidence.

If the real thing cannot be captured, say so and cut the beat. A missing proof
shot costs a few seconds; a fabricated one costs trust.

### Borrowed B-roll: screens only, never the other creator

Clips lifted from a reference reel are usable when they show a **screen** — a
product UI, a diagram, a dashboard. They are never usable when the other
creator is in frame. Their face is the visual signature viewers tie to that
account, and it reads as a stolen clip the moment it appears.

Cropping the top band is not enough on its own: the creator's head enters that
band whenever a graphic slides away. Before cutting any window, map where they
are on camera across the whole reference, then pick windows strictly inside the
graphic-only stretches:

```bash
ffmpeg -v error -i ref.mp4 -vf "crop=<top band>,fps=5,format=gray,signalstats,\
metadata=print:key=lavfi.signalstats.YAVG:file=-" -f null - 2>/dev/null \
  | grep -o "YAVG=[0-9.]*" | cut -d= -f2
```

Their room is lit differently from the graphics, so the per-frame average
luminance separates the two cleanly: sustained runs on the graphic side of the
threshold are the safe windows. Leave 0.2s of margin at each edge, and check a
frame from the start AND the end of every clip you cut — the head usually
arrives in the last few frames, which is exactly where a spot check at t=0.5
misses it.

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

## Marks and icons

A card naming a tool should carry that tool's mark, and a brand beat should use
that brand's colour. `scripts/icons.py` fetches both — Simple Icons is public
domain and ships each brand's official hex, so the card themes itself.

Use the interface set for concepts with no brand — a clock for urgency, a moon
for overnight — rather than writing the word.

**An exact match or nothing.** Asking for "OpenAI" and silently getting
"OpenAI Gym" puts the wrong company's mark on screen. The fetcher refuses
near-matches and names the alternatives.

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

## Match the meaning, and change the framing

**The insert must match the words being spoken**, not the topic in general. If
the sentence is about a specific number, show that number — not a generic shot
of the page it lives on.

**Match the feeling, not just the noun.** "I was stuck for three days" is not
illustrated by a neutral screenshot of the tool; it is illustrated by the error,
the failing run, the thing that was actually stuck.

**Never cut from a medium shot to another medium shot.** If the speaker is
framed chest-up, the insert should be a tight detail or a wide view. Matching
scales across a cut makes the change invisible and the edit feel flat — the
brain needs to re-adjust for the cut to register as a cut.

When there is no B-roll, change the framing of the face instead: cut from
chest-up to a tighter crop on a key line. That is a real cut, and it costs
nothing but a crop. Put `"zoom": 1.25` on an EDL range for a medium, `1.55`
with `"zoom_y": 0.30` for a close-up — the vertical bias exists because faces
sit high in frame.

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

## A screenshot is not a thumbnail

Ranking frames by sharpness puts a page of text first every time — text has far
more edge contrast than a face. Sample thumbnail candidates only from moments
the speaker is actually on screen, skipping proof shots and full-frame cards,
or the best-scoring frame will be a screenshot nobody would click.

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

---

## The marker disappears on a dark page

`highlight: true` draws the accent bar with `mix-blend-mode: multiply`, which
is what makes it read as a real marker: the words stay legible through it
instead of being covered. Multiply over a near-black capture multiplies to
black, so the highlight renders perfectly and is invisible.

On a dark page set `"highlight_style": "dark"` on the beat. That screens the
bar instead, so it lights up and light text stays light.

Check the frame. A highlight you did not look at is a highlight you do not
have.

## A wrapped headline needs `highlight_rect`

A multi-line headline is a single element, so its bounding box covers every
line. A marker drawn on that box is a slab across the whole paragraph, not a
stroke under a phrase.

Put `"highlight_rect": {"x":…, "y":…, "w":…, "h":…}` (css units, same space as
`from_y`) on the beat and place the marker on the one line carrying the claim.
Measure it: crop the capture at the element's box, look at it, and read the
line's coordinates off the crop.

# Framing

Where the speaker sits in the frame, and what shares it with them.

---

## Judge every crop from a real frame

Never compute a crop from arithmetic alone. Extract an actual frame from the
actual footage, look at it, and decide from what you see.

The method that works: render the same frame at three candidate positions —
say 20%, 30% and 40% — put them side by side, and pick. It takes seconds and
settles the question that arithmetic cannot, because where a person sits in
frame differs with every recording setup.

Crops derived from assumptions about where a person sits put the forehead at
the top of frame or cut off the chin, and the error is invisible until someone
watches it. One extracted frame costs seconds and settles it.

---

## The split

When a designed card shares the frame with the speaker, the card takes the top
half and the face fills the bottom half. Not a quarter, not a strip — half.

The face half is a **centre crop** of the source: the box is positioned so that
the upper and lower parts of the recorded frame are cut away and what remains
is a tight, centred portrait. The speaker must not be pushed to the bottom edge
of their half; that reads as them disappearing out of frame.

**Anything positioned against the full-height frame must move when the split
happens.** Elements anchored for a full frame now fall outside the card and get
clipped, or land on the speaker's face. Re-anchor them to the layout they are
actually in.

---

## Never scale the face during a split

Zoom on the face belongs to the full-frame state. Scaling the face element
while it is also being repositioned into a half produces glitches that static
frame checks do not catch — they only appear in motion, which is exactly where
they get noticed.

If a punch is wanted at that moment, put it on the card's content instead.

---

## The platform covers part of your frame

Reels are shot 9:16 but the feed crops to 4:5, and the app's own interface sits
on top of what remains. Anything essential outside these bounds is either cut
off or covered:

| Zone | Reserved for |
|---|---|
| Top ~15% | Platform header |
| Bottom ~25% | Caption, audio name, controls |
| Right ~15% | Like, comment, share buttons |

Captions placed at 16% from the bottom sit underneath the app's own caption —
readable in your render, obscured in the feed. Keep burned-in text above ~27%.

Position the speaker's eyes on the upper third. It reads as eye contact and
leaves the space below for text.

## Nothing lands on the face

No overlay, popup, logo, badge, or caption sits over the face. Full-frame
overlays go in the lower third or the empty space above the head.

Popups and product images live between the chest and the caption zone. If a
popup is large enough to collide with a caption, hide that caption for its
duration — the image replaces it. Two elements fighting for one region is worse
than either alone.

---

## Text never touches an edge

Give every text block real horizontal padding, and size the largest word so the
**longest** word fits inside that padding without wrapping. A headline that
kisses the frame edge or wraps mid-phrase looks broken.

Leave vertical breathing room between stacked elements — a divider, a big word
and a sub-line need space between them, not just sequence.

**Never estimate text width — measure it where it renders.** This was got
wrong three times in a row on one card: sizing from character count clipped
the headline, accounting for the held zoom still clipped it, and measuring
`clientWidth` *still* clipped it because that property includes the container's
padding and permitted 1015px where only 918px existed. Glyph widths depend on
the font that actually resolves, which is not knowable ahead of the render.
Fit the text in the browser, against the true content box, and include any
scale the element is animated to.

After rendering, verify mechanically rather than by eye: sample the outermost
dozen pixel columns of the frame for ink. Text touching an edge is a recurring
defect and easy to miss in a thumbnail-sized check.

---

## Every layout has its own caption position

A caption position tuned for a full frame will sit on the speaker's forehead
once the layout becomes a split. Each layout state gets its own caption
placement, and switching layouts must switch it.

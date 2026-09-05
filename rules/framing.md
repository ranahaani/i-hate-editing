# Framing

Where the speaker sits in the frame, and what shares it with them.

---

## Judge every crop from a real frame

Never compute a crop from arithmetic alone. Extract an actual frame from the
actual footage, look at it, and decide from what you see.

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

After rendering, look specifically for text touching an edge or overlapping a
neighbour. This is a recurring defect and it is only visible in the output.

---

## Every layout has its own caption position

A caption position tuned for a full frame will sit on the speaker's forehead
once the layout becomes a split. Each layout state gets its own caption
placement, and switching layouts must switch it.

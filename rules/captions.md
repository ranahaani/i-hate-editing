# Captions

Captions are not an accessibility afterthought on short-form video — most of
the audience watches muted, so the captions *are* the delivery. Get them wrong
and the edit fails regardless of how good the cut is.

Hard rules 1 and 5 apply: captions composite last, and their times are
**output-timeline** times, not source times.

---

## Timing

**Never early.** A caption that appears before the word is spoken is the single
most-reported caption defect. It reads as broken sync even when the drift is a
fraction of a second, because the viewer's ear notices the word arriving after
the text.

Set each chunk's start to the word onset **plus 0.08s**, so the word is heard
as, or just before, it appears. Late is invisible; early is a bug.

**Re-derive onsets on the file you are actually captioning.** Any speed change,
re-cut or trim moves every onset. Times taken from the source and applied to
the cut will drift progressively.

**Never let a caption start inside a silence.** Cross-check against
`scripts/silences.py`; a chunk that begins mid-pause has drifted.

---

## Chunking

**Two to five words per chunk**, appearing as spoken. Never dump a whole
sentence at once — the viewer reads ahead, finishes before the speaker does,
and disengages.

Break on, in priority order:

1. Punctuation (a clause ended)
2. A gap of 0.35s or more (they paused)
3. Five words (the ceiling)

A chunk should be readable in the time it is on screen. Under ~0.4s is too
fast to read regardless of length — merge it with its neighbour.

---

## Style

**Size hierarchy, one or two emphasis words per chunk.** The emphasis word is
large and in the brand accent; the surrounding words are smaller and white.
This is the whole effect — mark emphasis *sparingly*. When everything is
emphasised, nothing is.

Emphasis goes to the word carrying the meaning: a number, a product name, the
verb that makes the claim. Not articles, not filler.

**No background box.** Never a grey or black pill behind the text. Legibility
comes from a strong multi-directional dark outline, so the video stays visible
underneath:

```
0 0 9px #000, 3px 3px 0 #000, -3px -3px 0 #000,
3px -3px 0 #000, -3px 3px 0 #000, 5px 6px 0 rgba(0,0,0,0.55)
```

**Emphasis words pop in** as they are spoken — a short scale overshoot, not a
fade. Motion on the emphasis word is what makes captions feel authored rather
than burned in.

---

## Placement

**Lower-centre, clear of the face and the hands.** Never over the chin, never
over a microphone or gesturing hands. On a full-frame talking head that is
roughly 16% up from the bottom.

**When the layout changes, the captions move.** If a designed card takes the
top half and the face the bottom, captions that stayed at their full-frame
position now sit on the speaker's forehead. Every layout state needs its own
caption position.

**When a popup or image would collide with a caption, hide that caption.** The
image replaces it. Two things fighting for the same space is worse than
briefly having no caption.

---

## Language

**Caption in the language the audience reads, not necessarily the one spoken.**
For code-switched or non-English delivery aimed at an English-reading audience,
caption the English translation of the actual spoken words — a real
translation, not a paraphrase, and not sparse keywords.

**Machine translation is a draft, not caption copy.** Not a step to tidy up —
raw output is routinely unusable. On a real edit it produced `ALL NIGHT." A
JOKE,` (two sentences merged with stray punctuation), `THE WANT THIS LINK
THEN` (garbled), and fragments cut mid-clause. Expect to rewrite most chunks
against the timings, keeping what was actually said.

**Fix product and tool names by hand, every time.** ASR reliably destroys
exactly the words the audience is watching for — "Claude" comes back as
"cloud" almost every run. Keep a per-project list of corrections and apply it
before the captions are built.

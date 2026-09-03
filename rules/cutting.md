# Cutting

Take selection and cut placement. This is where a recording becomes an edit,
and it is the part no script can do for you.

Read `HARD-RULES.md` first — rules 6, 7 and 13 apply to everything here.

---

## Take selection

**Expect a retake at every source boundary.** People stop after a mistake and
restart. When a source file ends mid-thought and the next begins with the same
sentence, that is a retake, not new material.

**Keep the last complete attempt, not the first clean-sounding one.** Later
takes are usually more fluent — the speaker has warmed into the line.

**Scan every take of a beat before choosing.** The best version is often not
one continuous span. A false start can sit immediately before the correct
delivery, and the clean opening of a line may live in a take whose ending is
muddled. When that happens, stitch the strong head to the strong tail rather
than shipping a compromised single take.

**Prefer completeness over polish.** A slightly fumbled sentence that finishes
the thought beats a crisp one that trails off.

---

## Where cuts land

**Silence gaps are the cut candidates**, ranked by `scripts/silences.py`:

| Gap | Verdict |
|---|---|
| ≥ 0.40s | Clean. Cut here. |
| 0.15–0.40s | Usable, but look at a frame first — the speaker may still be mid-gesture. |
| < 0.15s | Mid-phrase. Unsafe. |

**Cross-check every edge against silence, never the transcript alone.**
Transcript times drift; the waveform does not.

**Cut on complete clauses.** Every kept block starts and ends on a finished
thought. A cut that lops a negation inverts the meaning of the sentence — this
is the single most damaging cutting error and it reads as a subtitle bug to
viewers who notice it.

**Check orphans.** When a cut removes half a sentence, read what remains on its
own. If it no longer stands up, cut it too.

---

## What to remove

- **Filler and false starts** — but not every one. Stripping all of them makes
  delivery sound synthetic. Remove the ones that break the sentence.
- **Dead air** — trim long pauses. Leave thinking pauses; they are rhythm.
- **Rambles** — anything that does not serve the point being made.
- **Weak openings** — start on the first complete thought. If the intro was
  restarted, keep the last version.

**Pacing follows `profile.yml`:**

| Setting | Pause handling | Feel |
|---|---|---|
| `punchy` | Trim gaps to 0.25–0.45s | Dense, fast, social |
| `balanced` | Trim only gaps over ~1s | Natural |
| `restrained` | Trim only dead air | Measured, long-form |

**Report a heavy cut.** If more than a quarter of the material is removed, say
what went and why rather than quietly shipping a much shorter video.

---

## The one deliberate pause

Do not remove every silence. Immediately after the opening claim, hold roughly
half a second of real footage with no speech. That beat is where a sound
transition lands, and it is what separates a hook from a sentence. A hook that
hard-cuts straight into the body feels rushed even when every word is right.

---

## Verifying a cut

A cut is not finished until it has been re-transcribed **in windows aligned to
each seam** — never one whole-file pass, which condenses and hides exactly the
defects you are looking for.

Hunt for two things specifically:

1. **Repeated words across a join.** "so so", or a phrase delivered twice from
   two different takes. Confirm a suspected double by re-transcribing the two
   or three seconds straddling the seam, since overlapping windows can
   hallucinate one.
2. **Clauses that start or end mid-thought.**

Also check for **stale references**: dropping an item can leave the speaker
saying "fourth" about what is now the third thing.

Content being present is not the same as content being clean.

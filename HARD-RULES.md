# Hard rules

Correctness, not taste. Every rule here prevents a **silent failure** — output
that renders without error and is wrong. Deviating produces bugs you will not
notice until a viewer does.

Taste lives in `rules/`. This file is not negotiable.

---

**1. Captions composite last.** Any overlay applied after captions hides them.
The caption layer is always the final composite step.

**2. Extract per segment, then concatenate losslessly.** Cut each segment out
first, then join with stream copy. A single-pass filtergraph re-encodes every
segment again once overlays are added.

**3. Fade audio 30ms at every segment boundary.** `afade` in at the start and
out at the end of each extracted segment. Without it, every cut pops.

**4. Shift overlay timestamps to the overlay's own start.**
`setpts=PTS-STARTPTS+T/TB`. Without this you see the middle of an animation
during its window instead of its beginning.

**5. Caption times are output-timeline times.**
`output_time = word_start - segment_start + segment_offset`. Source times are
meaningless after segments are concatenated.

**6. Never cut inside a word.** Snap every edge to a word or phrase boundary
from the transcript, then confirm it against silence detection.

**7. Pad every cut edge, 30–200ms.** Transcript timestamps drift 50–100ms;
padding absorbs it. Tighter for fast pacing, looser for measured.

**8. Pin the transcription language.** Never auto-detect. Auto-detect silently
*translates* some languages instead of transcribing them, which corrupts every
downstream timestamp.

**9. Word-level tokens only where the script supports it.** whisper.cpp's
`-ml 1` splits multi-byte characters mid-sequence on non-Latin scripts,
producing corrupt UTF-8 and unusable subword fragments. Those languages use
segment-level output plus silence detection.

**9b. Never translate with a turbo model.** Turbo models are distilled for
transcription and have no translation capability. Asked to translate they
return the *source* language without error, which flows into captions as
untranslated text. Use `large-v3` or `medium` for any translate pass.

**10. Cache transcripts per source.** Re-transcribe only when the source file
itself changes. Immutable output of immutable input.

**11. Verify a sound effect is audible, not merely un-clipped.** A file whose
loud transient falls outside the window you play is silent in the mix while
every level check passes. Measure the peak inside the actual window against a
voice-only baseline. See `rules/sound.md`.

**12. Look at the output before presenting it.** Extract frames at every cut
boundary and at the start and end. Measure levels. A render that completed is
not a render that is correct.

**13. Approve the cut before building on it.** Captions, motion and sound all
carry timestamps derived from the cut. Changing the cut afterwards invalidates
every one of them.

**14. Never write into the skill directory.** All output belongs in
`<footage>/studio/`.

---

Rules 1–7 and 10 are adapted from [browser-use/video-use](https://github.com/browser-use/video-use)
(MIT), which isolated these production-correctness traps cleanly. Rules 8, 9,
11, 12 and 13 come from failures observed in this project.

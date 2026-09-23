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

**9c. Apply speed changes in the render, never afterwards.** Captions, sound
and motion are all timed from the rendered timeline, so speeding up a finished
cut drifts every one of them. Two traps come with it: `-ss` and `-t` must both
precede `-i` (after `-i`, `-t` is an output-side limit measured on the sped
timeline and cancels the speed change entirely), and any offset within a
segment must be divided by the speed before being added to an output-timeline
anchor.

**9d. Probe display dimensions, not stream dimensions.** Phone footage carries
a rotation matrix rather than rotated pixels: the stream reports 1920x1080
while the decoder outputs 1080x1920. Reading width and height directly sizes a
vertical video as landscape and letterboxes the entire edit, silently.

**10. Cache transcripts per source.** Re-transcribe only when the source file
itself changes. Immutable output of immutable input.

**11. Verify a sound effect is audible by differencing, not by measuring the
master.** A file whose loud transient falls outside the window you play is
silent in the mix while every level check passes. But measuring the master
*alone* cannot tell you either: wherever a sting sits under speech, the loudest
thing in that window is the voice, so the number describes the voice and not
the sting. `sound.py check` works this way and will report every sting on a
talking-head mix as TOO LOUD.

Measure the rendered master **against the voice-only cut** — that delta is the
sting. Correct for the 2–3 dB the render attenuates the video's own audio by,
measured on sting-free speech windows. A negative lift is impossible from
addition, so if you see one you have not applied that correction. See
`rules/sound.md`.

**12. Look at the output before presenting it.** Extract frames at every cut
boundary and at the start and end. Measure levels. A render that completed is
not a render that is correct.

**13. Approve the cut before building on it.** Captions, motion and sound all
carry timestamps derived from the cut. Changing the cut afterwards invalidates
every one of them.

**14. Never write into the skill directory.** All output belongs in
`<footage>/studio/`.

**15. A scene renders at the cut's dimensions and frame rate, or it judders.**
An overlay at a different rate is resampled on composite — a frame dropped or
doubled every few frames, on exactly the moves meant to look designed. A
different size is rescaled. Both render without a warning. `scenes.py` takes
both numbers from the cut for this reason; never set them in `Root.tsx`.

**16. Scene audio never reaches the mix.** Overlays composite with the `muted`
attribute, so a sting baked into a Remotion scene is dropped silently. It also
escapes the voice-only differencing in rule 11, so it cannot be proven
audible. Every sting belongs in `sfx.json`.

**17. Frame-driven motion only inside a scene.** The renderer advances frames
out of real time. A CSS transition, a timer or a `requestAnimationFrame` loop
has no wall clock to run against, so it renders as a still — with no error and
a plausible-looking first frame.

**18. Anchor cut edges on silence, not on word onsets.** ASR word onsets land
on the consonant, so an edge placed at the onset chops the attack off the first
word — the edit sounds clipped even though the transcript says every word is
present. Find the edge in the silence either side, then use the transcript only
to decide which silences are legal boundaries. Rule 6 has the dependency the
wrong way round when read alone; this rule governs. Padding does not fix it:
the offset is systematic toward the consonant, not random drift, so a 50ms
in-pad can sit entirely inside the attack.

**19. Time every cue to a word onset, never to a caption chunk.** When ASR
returns segment-level timing — which it does for every language in
`transcribe.py`'s `NON_LATIN` set — `captions.py` divides each segment evenly
across its words. Those positions are arithmetic, not speech. A cue placed on
one lands up to 1.4s away from the word it illustrates, and the error is
invisible in every file: the transcript reads correctly and the chunk times
look plausible. Re-derive onsets with `whisper-cli --dtw` per segment
(a whole-file DTW pass smears across cut seams) and verify a few by
transcribing the slice on its own.

**20. A panel composited after the render loses the layers above it.** Cropping
a finished frame and pasting it back drops anything outside the crop window —
captions sit below it, so they vanish for exactly as long as the panel is up,
and nothing warns. Composite B-roll in the composition, where the caption layer
still draws on top.

---

Rules 1–7 and 10 are adapted from [browser-use/video-use](https://github.com/browser-use/video-use)
(MIT), which isolated these production-correctness traps cleanly.
Rules 8, 9, 11–13 and 18–20 come from failures observed in this project.

Rules 15–17 govern the Remotion scene layer. Its structure — a spec
approved before anything is built, one composition per scene, frame-driven
motion — is adapted from [Creatorberry/flick](https://github.com/Creatorberry/flick)
(MIT).

*Rule 18 was reported by u/MRRmaker on r/ContentCreators, 2026-09-08,
who works on a tool in this space and pointed it out unprompted.*

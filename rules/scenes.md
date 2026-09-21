# Designed scenes

A card is text on a ground. A **scene** is a built visual: a product card that
assembles, a counter that runs, a fake terminal that types, a diagram whose
parts arrive in the order the sentence explains them.

Cards cover most beats and stay where they are. Reach for a scene when the
sentence describes something with *structure* — a comparison, a sequence, a
mechanism, a number that moves. Forcing that into a headline and a sub-line is
how a piece ends up reading as a slideshow with a face attached.

Scenes are React components rendered by Remotion, one MP4 per scene,
composited back through the overlay path B-roll uses. The approach — a spec
approved before anything is built, one composition per scene, frame-driven
motion, no background music — is adapted from
[Creatorberry's flick](https://github.com/Creatorberry/flick) (MIT).

---

## Real material still wins

Nothing here changes `rules/proof.md`. When the speaker names a repo, a page,
a product or a number, capture the real thing. A scene is for what has no real
artefact: an abstract mechanism, a comparison, a payoff.

A scene must never imply a screenshot of something real. A simulated UI reads
as simulated — stylised, obviously drawn — or it is a fabricated screenshot.

## Plan before you build

Author `studio/scenes.json` first and show it. Each entry states the line it
covers, what is on screen, and what moves in what order:

```json
{"scenes": [
  {"id": "token-waste", "start": 12.4, "duration": 3.2, "full": true,
   "line": "every retry re-sends the whole conversation",
   "visual": "context bar fills to 100%, three retry chips stack on top, the bar turns red on the third",
   "assets": ["claude.svg"]}
]}
```

`full: true` gives the scene the whole frame and steps the face away; without
it the scene takes the top half and the face repositions below it, exactly
like a half-card. Captions keep drawing on top either way — a full scene does
*not* suppress them the way a full card does — so leave the bottom third of
the frame clear or the caption lands on your artwork.

Do not write components before that plan is agreed. A component written
against an unapproved beat is thrown away, and it is the expensive artefact in
this pipeline.

## One composition per scene

Each scene is its own Remotion composition, registered on its own. Never build
a single all-scenes composition: the edit's timeline lives in the cut, not in
Remotion, and an all-in-one composition has to be re-rendered in full every
time one beat changes.

`scenes.py sync` generates `Root.tsx` and `src/data/scene-spec.json` from
`scenes.json` and the cut. Do not edit either by hand — a registration that
drifts from the spec renders a truncated scene with no error.

## Frame-driven motion only

Drive everything from `useCurrentFrame()`. No CSS transitions, no
`requestAnimationFrame`, no timers: the renderer advances frames out of real
time, so anything driven by the wall clock renders as a still.

`rules/motion.md` governs the craft — err large, hold the zoom, one thing at a
time, vary the entrance, sync the landing frame to the word. A scene is not
exempt because it was built in React.

## Every scene is concrete

The failure is a scene that is a title card with extra steps: a word fading in
over a gradient. If the description of a scene could be written for any other
sentence in the script, it is not a scene yet.

## Sound stays in the mix

Plan the sting in `sfx.json`, never inside the component. Overlays composite
muted, so audio baked into a scene is dropped silently — and even if it were
not, a sting inside the scene escapes `sound.py check` and the voice-only
differencing that proves it is audible (`rules/sound.md`).

No background music in a scene, ever. Music is one bed over the whole piece,
added at delivery.

## Before you show it

- [ ] The beat had nothing real to capture.
- [ ] `scenes.py check` passes, including `tsc --noEmit`.
- [ ] The scene renders at the cut's own dimensions and frame rate.
- [ ] Something changes at least every three seconds inside it.
- [ ] Every on-screen word is readable on a phone at arm's length.
- [ ] The bottom third is clear, where the caption lands.
- [ ] Only assets the user supplied, or brand marks `icons.py` fetched.
- [ ] The rendered MP4 has no audio stream.
- [ ] You looked at first, middle and last frames of the render.

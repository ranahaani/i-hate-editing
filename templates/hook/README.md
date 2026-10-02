# Hook effects

## Shatter text (`shatter.py`)

One word, whole and legible for `lead` seconds (default 1.1s, so it is on screen
at least 1.5s with the 0.4s break), then 24 triangular shards fly outward over
0.4s starting at `t_hit`. Fires once. Placement is a zone box (`x,y,w,h`, frame
pixels) from `safe_zone.py`; pass the face box and every shard's flight path is
kept clear of it (shards heading at the face are mirrored away, then shortened).
A zone that overlaps the face is refused.

Composed inside the HyperFrames composition so captions stay on top (hard rule 20):

```python
import shatter
frag = shatter.build("NEVER", t_hit, zone, face, color=accent)   # frame=(w, h)
html = shatter.splice(compose.build_html(...), frag)   # or append frag["css"/"clips"/"anims"]
```

`frag["anims"]` are plain statements for the `tl` script; the clip lives on track
55 (cards 15, proof 45, captions 60). Put the impact sting in `sfx.json` at
`t_hit` (hard rule 16). Render check: `python3 demo.py clip.mp4 --word NEVER
--t-hit 1.8 --zone 90,330,900,260 --face 250,600,580,640 --out <workdir> --render`.

A dark scrim sits behind the word so `hyperframes check` passes its contrast
audit on light walls; it fades just after the hit. Shard count stays at 24 to
stay under the check's heavy-overlay (clip-path) warning at about 40.

## Semantic grade

`scripts/grade.py cut.mp4 --preset loss_red --window t0:t1 [--ease 0.1]`.
Applies to any preset via `--window`; `loss_red` requires it.

## Headline (`headline.py`)

Stacked 2-3 line headline with an entity mark on the left, replacing the flat
slab. Same pattern as shatter: `build(lines, accent, mark, t_in, t_out, zone,
face=None, avoid=(), assets_dir=...)` returns `{css, clips, anims}`;
`splice(html, frag)` inserts it. Clip on track 50 (shatter 55, captions 60).

- 3-5 words (6 warns, 7+ errors); a last line holding one word, or a line
  ending on a connector, is refused. `--text` breaks by meaning for you.
- Marks: `face` (YuNet-centred circular crop, accent ring, crop only), `logo`
  (SVG/PNG), `icon` (`scripts/icons.py`, exact match or error).
- Accent comes from the mark: `--accent "#hex"` or `--accent-from brand.png`.
- Entrance is a slide + back-ease scale snap inside ~0.3s, never a fade; exits
  by sliding left at `t_out`. Zone must clear `face` and every `avoid` box.
- The Archivo Black TTF is copied into `assets_dir/fonts` and loaded with
  `@font-face`; copy `assets_dir` beside index.html (`preview` does this).
- Preview: `~/.cache/i-hate-editing/venv/bin/python headline.py --lines
  "LIMIT HIT?|SAVE THE SESSION" --accent-word SAVE --accent "#D97757" --mark face
  --mark-src ../../assets/people/anthropic.png --t-in 0.08 --t-out 3.2
  --zone 54,288,864,166 --face 389,695,452,575 --clip cut.mp4 --out <dir> --render`

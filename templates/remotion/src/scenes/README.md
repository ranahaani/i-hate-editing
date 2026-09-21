# Scene components

One file per scene, named after the scene's `component` in `scenes.json`, each
exporting that component as a named export:

```tsx
export const TokenWaste: React.FC = () => { … };
```

`scenes.py sync` writes `src/Root.tsx` and `src/data/scene-spec.json` from
`scenes.json`. Do not edit either by hand — the next sync overwrites them, and
a registration that drifts from the spec renders the wrong duration silently.

Read timing from the spec rather than hardcoding it:

```tsx
import {useCurrentFrame, useVideoConfig} from 'remotion';
```

Craft rules: `rules/scenes.md` and `rules/motion.md`.

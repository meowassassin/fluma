# ArtCraft video editor (vendored)

Source: https://github.com/storytold/artcraft — `frontend/libs/components/video-editor/src` at commit a787c37 (2026-11-12),
package `@storyteller/ui-video-editor`. Itself derived from OpenCut (MIT).
License: MIT or Apache-2.0 at your option (LICENSE-MIT, LICENSE-APACHE, NOTICE in this folder). The ArtCraft name and logos are not covered.
Fluma changes are marked with `// fluma:` comments.

## Fluma changes (2026-11-12 overhaul)
- Fonts: curated catalog `lib/fonts/catalog.ts` (124 families, ~40 Korean) + loader `lib/fonts/google-fonts.ts`
  (renderer requests faces/subsets per text, preview re-renders on load, export awaits all fonts). New `FontPicker`.
- Text: numeric weights, `skewX`, `stroke.*`, `shadow.*` params; drawn in `text/primitives.ts` / `nodes/text-node.ts`.
- Properties: consistent controls (`property-param-field.tsx`), grouped sections, Korean labels, labelled tabs,
  effects tab on text, fit presets computed from media size.
- Effects: host `effectProvider` seam (`lib/effects/provider.tsx`); built-in blur kept as fallback.
- Host hooks: `VideoEditor` props `extraPanels`, `effectProvider`.
- Captions tab: caption list (`text/components/captions-view.tsx`) instead of the placeholder.

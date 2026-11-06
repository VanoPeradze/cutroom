# CUTROOM workspace artwork

The November 2026 visual set uses the original CUTROOM screenshots captured on 19 October 2026. The interface has not been redrawn or reconstructed by AI. Screenshots are scaled as complete rectangles; their layout, controls, labels and demo footage are preserved. The separate graphite/metal background was generated with OpenAI image generation, then composed with native typography and the existing CUTROOM mark.

The photographs of a physical editing room used in earlier concepts are not part of this set. No customer footage or personal data is included. These are product illustrations, not evidence of AI editing quality or newly qualified application builds.

## Files

All workspace cards are 1600 × 900 JPEGs. `social-20261106.jpg` is a separate 1200 × 630 layout for Open Graph and Twitter previews. Original PNGs remain in `../readme/` (or `../ai-options.png`) and are linked from the website and documentation.

| Card | Original screenshot |
| --- | --- |
| Cover, Edit, Social | `../readme/studio-edit-20261019.png` |
| Home | `../readme/studio-home-20261019.png` |
| Media | `../readme/studio-media-20261019.png` |
| Layout | `../readme/studio-layout-20261019.png` |
| Audio | `../readme/studio-audio-20261019.png` |
| Captions | `../readme/studio-captions-20261019.png` |
| Output | `../readme/studio-output-20261019.png` |
| AI | `../ai-options.png` |

## Rebuilding

`source/render-artwork.ps1` composes the existing screenshots and background using the built-in Windows System.Drawing renderer and Segoe UI. It requires no new packages. Run it from PowerShell; pass `-Repository` only when rendering against a different checkout. Then run `npm run prepare:assets` from `website/` to synchronize the explicitly listed public assets.

The background prompt: a premium editorial study of editing rhythms, graphite matte material, restrained brushed aluminium and teal strips, a small muted lavender accent, quiet negative space, physical studio lighting, no typography, UI, invented controls, people or devices. Final headlines and product interface pixels are composed independently of the generated background.

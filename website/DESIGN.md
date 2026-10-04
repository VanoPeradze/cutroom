# CUTROOM website — studio design, October 2026

Mode: Persuade. The visual authority is the approved 12-screen CUTROOM studio concept set (Audio, Media, Edit/Effects, Layout, Captions, Output, Home, Preparation, Director, First Draft, Projects/AI and supporting dialogs). The website borrows its language, not its pixels: those screens are design concepts that are not implemented, so none of them is published or presented as the product.

The page shares the editor's dark room. Tokens match `web/studio-design.css`: background #11181d/#121a20, panels #1a242b and #1f2b33, lines #2b3740, text #edf2f5, secondary #bfcbd3, muted #8c9ca7, cyan action #1bd9ce (text on cyan #062522) and violet signal #a38bd0. The mark is the two slanted cyan/violet bars (`public/assets/mark.svg`); the favicon stays unchanged. System sans typography only; no remote fonts.

Structure: a centered introduction (eyebrow, two-line display heading with a cyan-to-violet second line, one primary Windows action and a secondary Mac action), a framed real editor capture, three start cards (Short/Reel, YouTube, manual), the six-workspace tour in editor order with the concept's bottom workspace bar, the three AI modes, installation help and a closing call to action. Illustrations are CSS-only schematics marked `aria-hidden`, never fake screenshots; product claims stay limited to features documented in the user guide.

The hero image remains `public/assets/editor-demo.png`, an unaltered capture of the released editor that must equal `docs/images/editor.png`. When the studio redesign ships in a validated release, replace that canonical capture; until then the page must not show the concept UI as the product.

Without JavaScript every workspace panel stays visible in reading order; the script adds tab roles, arrow/Home/End keys and RTL-aware direction. The strict CSP forbids inline `style` attributes, so illustration geometry lives in `styles.css`.

Release gates: desktop and mobile in English and Hebrew without horizontal scroll at 320 px, visible keyboard focus, contrast, reduced motion, the screenshot dialog, the linked installation disclosure, and the existing download bytes, checksums and protected-branch workflow.

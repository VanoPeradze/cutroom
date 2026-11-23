# CUTROOM application

CUTROOM is a free, local-first beta video editor. This is the application surface, not its marketing website.

## Audience and task

Creators import recordings, prepare an optional AI draft or edit manually, review the result, adjust layouts, mix sound, correct captions and export. The editor must remain useful without an AI account or model. Existing projects, imports, source marks, edit history, export settings and user footage must not change as a consequence of appearance updates.

## Platforms and constraints

A local Python/Flask server serves the existing vanilla JavaScript/CSS application in a browser on Windows, macOS or Linux. Desktop is the primary workspace; compact screens retain all tools through the existing scroll-based layout. Six existing workspaces share one media library, monitor and timeline. Panel resizing, keyboard shortcuts and persisted display preferences are owned by their existing controllers.

## Current owner direction

- Substantially redesign the application with the same care as the new public site, not just the website.
- Light mode should be predominantly gray, not white. Preserve dark mode and all existing features.
- Keep a professional, understandable media organization comparable in purpose to established editing tools.
- No neon/lime green, Lucide icons, decorative eyebrow text, monospace UI typography or green badge/border glow.
- No application publication or pull request is authorized by this design pass.

## Success

Readable, calm, coherent tools; a clear media pool; stable preview and timeline geometry; keyboard-visible controls; correctly themed canvas as well as DOM; no external font fetch; validated primary editing flows in both themes. Synthetic fixture screenshots are testing evidence, not a demonstration of automatic-edit quality.

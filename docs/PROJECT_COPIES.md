# Save a copy

Use **Save a copy** on an existing Home or Projects row to branch an edit without overwriting the original. Review the name and disclosure, then choose **Create copy**. Completion does not switch projects. Use **Open copy** when you want to work in the new project.

## What is preserved

The server copies the complete saved project, not a reconstruction from the browser: timeline/source mappings, imported clips and custom text, editable tracks and locks, settings, saved captions and their alternatives/provenance, analysis, and saved AI proposals. Media and preview files have independent ownership and contents. Copying does not run AI or generate another draft.

The copy has a new project identity and starts at revision 1. **Undo/Redo history starts fresh, and previous exports are not copied.** The source retains its own history and exports. A new export in the copy is independent. Copying is not a portable archive or backup outside the configured project storage.

## Unsaved changes and active work

For the current project, queued autosaves must finish successfully first. Explicit caption, Chroma Key and transcript drafts must be saved or discarded by you; copying never silently drops or applies them. Finish live timeline/frame gestures before copying. Copying a different saved project does not flush, discard or navigate your current editor.

Imports, preparation, rendering and other file-processing work must be idle before admission. One copy runs at a time. While its source is being copied, that source is protected from changes. If the source editor is visible, the status dialog remains modal; **Back to Projects** leaves the copy running so you can open another project. Other projects can still be edited, but new file-processing work waits until the copy resolves.

## Progress, cancellation and uncertain connections

The visible source-row status and its **Copy details** action reopen the same operation. Closing details from Projects does not cancel. **Cancel copy** requests cancellation before publication; wait for a confirmed result. A copy that already committed may finish instead.

If a connection fails, the status can remain unconfirmed. **Check status** looks up the durable operation. **Retry same request** uses the original source, revision, name and operation key; it cannot create a second copy. Reload recovery does not automatically resubmit a request. An unknown lookup is not treated as proof of cancellation. Do not delete browser operation state to work around an uncertain result.

Success is reported only from a validated durable receipt. A later deletion of the new project does not make retry recreate it. **Save another copy** first opens a fresh named-copy form and requires another explicit submission.

## Storage and compatibility limits

The independent files require their full additional size plus safety headroom on the project volume. Missing originals or explicit media-preview references, unsafe links/reparse points, unsupported temporary files, insufficient disk space or a changed source cause refusal rather than a visible partial project. Copy preserves existing owned cache files; it does not generate or repair missing optional source thumbnails. File timestamps are retained, but machine/file-identity-dependent preparation caches may need normal regeneration later.

Supported deployment: one CUTROOM server per data directory. This is not a distributed filesystem transaction and does not authorize external programs or older binaries to edit storage during a copy. Detected external changes stop publication. An unverified post-publication recovery remains protected for diagnosis rather than deleting or recopying potentially committed data.

# Verify and repair an imported preview

Use **Verify & repair preview** on a ready imported file in the Media pool when its picture, sound, or thumbnail is unavailable. The command checks the original and the prepared files, then rebuilds only the prepared preview if needed. It does not reimport the file, replace the original, rerun stabilization, or change clip IDs, source marks, timing, tracks, levels, captions, history, or exports.

## What to expect

- Finish or cancel an active gesture, import, processing job, or project copy first. Queued saves are flushed; explicit caption, transcript, Chroma, or track-level drafts must be saved or discarded through their existing controls.
- Playback pauses in place. The edit cursor, selected clips, and unaffected media remain where they were. Successful repair can reload the affected media, but never starts playback automatically.
- An open imported Source monitor retains its In/Out fields and marks. Its audition time is restored only when that same view still owns it; newer navigation or playback intent wins. A previously stale source placement review still needs **Use current edit**.
- A healthy prepared preview is verified without rebuilding it. Repair is derived-media maintenance, not a timeline Undo step.
- Edit locks continue to protect clips. They do not prohibit verification or rebuilding a preview from the same verified original.

## Safe refusals

A missing original cannot be repaired this way. A known original-content mismatch is reported as changed. An older or copied binding without sufficient provenance is reported as **unverifiable**, not changed. These cases preserve the saved asset and edit. This command is not file relinking, and does not guess by filename or accept a replacement original.

Original A/B recording previews use their existing preparation flow. This command applies only to imported media, including the already-created output of stabilization; it never regenerates stabilization.

## Cancellation and uncertain requests

Use the card's **Check status** or **Cancel verification** controls. Cancellation is confirmed only by the worker's terminal result. If a response is lost, the request stays unconfirmed and is not automatically submitted again. Reopening the project can recover retained job status, but cannot restore a previous browser's audition state.

If the job is no longer retained and a complete status check finds no matching or active repair, **Verify again** starts a new explicit operation. Job retention is bounded, not an indefinite exactly-once guarantee. An earlier operation that later becomes visible remains checkable/cancellable; it never automatically reloads the current view. A stale saved revision requires reopening and reviewing the project, not replaying the old request.

## Compatibility and output

No timeline or track-format upgrade is required. New preparations save a private original-content proof; public media URLs use an opaque prepared-preview version to avoid stale browser caches. Verification does not expose private filesystem paths. Existing originals and exports are not removed. A repaired derived generation can invalidate render freshness while retaining the same intended picture and sound; render/preview equivalence is validated separately from browser cache identity.

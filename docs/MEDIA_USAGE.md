# Imported-file usage navigation

This is read-only navigation over the saved project, not a second editing model.

- Media pool cards show the number of saved imported-media timeline occurrences by exact asset ID. Disabled, muted, covered and locked clips still count. This is not an audibility/visibility measurement or a count of stabilization, effect or other asset references. A zero count does not mean a file is safe to delete.
- The existing Media pool search, type and List/Grid controls remain. Imported usage can additionally filter files with or without timeline occurrences. A/B source cards are outside that imported-usage filter. Malformed/ambiguous membership is unknown, never silently zero.
- **Find uses** opens the existing Timeline Index scoped by exact asset ID. Identical filenames remain distinct. Opening, searching, filtering, closing and returning to all timeline items do not select, seek, submit a save or change the project.
- Choosing one imported occurrence is an explicit navigation intent. The host validates the current project, saved revision, asset/clip identity, raw timing and current dialog request. Pending/explicit drafts, saves, active gestures or processing refuse navigation; this action never flushes or discards them. On a clean state, selection, inspector reveal and seek to that saved occurrence are synchronous. Lock or disabled state alone does not prevent navigation.
- **Reveal in Media pool** in the selected imported clip's inspector resolves the exact file, opens the existing pool without changing its saved visibility preference, clears obstructing local filters, then scrolls/focuses the existing card. It does not seek, reselect, recreate the Source monitor or change marks. Temporary groups must first choose a single clip.
- Imported preview-repair links use the same filter-owner reveal path, so active pool filters cannot hide the requested repair card.

## Ownership

`libraryAssetUsage` in MediaStudio projects counts only from unique raw `manual.media_clips` references. It is evaluated on saved snapshot renders, not playback frames. Card identity captures project/view ownership, because independent project copies deliberately retain asset IDs.

Timeline Index owns exact-asset scope, its origin focus and its activation token. The optional host activation bridge receives `{projectId, revision, assetId, clipId, isCurrent}`. It never preselects or seeks before admission, never treats a Promise as success, and cannot close/focus a replacement dialog after a late result.

The existing `studio-screens` filter owner exposes `mediaPoolNavigation.revealAsset(assetId)`. No caller independently toggles card visibility or creates a second search/filter model. Stable imported name metadata, not repair/progress button prose, supplies name search.

There is no new backend route, persisted field, project schema, render/audio policy, edit action, Undo entry, keyboard remap, media deletion, relink, bin, portable source mark or automatic import.

# CUTROOM manual listening and device acceptance

Use the final reviewed source/package pair identified by its explicit review
record. This checklist requires actual tester sign-off; automated passes do not
complete it. Use disposable project copies and permitted representative media.

Record `case | archive/export SHA | device | OS/architecture | browser/version |
tester/date | steps/settings | Pass/Fail/Blocked/Not tested | error/timestamp`.
Keep media, transcripts, machine-specific paths and detailed logs private. Public
reports should contain only a redacted result and relevant product limitation.

## 1. Verify identity

Compare each ZIP with its reviewed SHA-256 and manifest. Confirm the source
revision and scope of the evidence. Stop on any mismatch. A filename or version
label does not prove identity, and testing a private candidate cannot approve an
older public download. Record each listening export's checksum privately.

## 2. Review English and Hebrew speech

Watch each complete representative export outside the editor with headphones,
then speakers. Compare it with the original selected speech and the saved source
summary. Replay every join and the opening/final speech boundaries.

Require intelligible complete speech, preserved negations and qualifications,
correct speaker/context continuity, and no clipped word, repeated syllable,
click, unintended black/frozen frame, loudness jump or sync drift. Record source
references that cannot be understood from the retained material. Do not infer a
missing event, ending or outcome; revise the edit if context is inadequate.

A transcript/audio disagreement requires correction and renewed source and export
validation. Changing text alone does not repair audio. Restoring excluded source
changes the approved scope and requires a new review.

Keep **extractive rough cut accepted for review** and **generative Story
accepted** as separate sign-offs. Rough cuts must retain their review-required
label and cannot qualify generative quality.

## 3. Review captions, mixer and saved edits

| Check | Action and pass criterion |
| --- | --- |
| Caption ownership | Correct a line with **What was said** and confirm every reuse updates. Use **Only this caption** and confirm another reuse remains unchanged. Move, trim, hide, undo/redo, save and reopen. Reorder repeated speech and trim its first word: changes must follow the original surviving speech. |
| Encoded captions and SRT | Export with **Burn into video** and **Export SRT file** enabled. Check MP4 and UTF-8 SRT outside the editor. Verify text, order, timing, Hebrew RTL/mixed punctuation, negations, line breaks and legibility. Disable AI burning and confirm custom text remains independent. |
| Mixer | Change a channel to -7.5 dB, mute/unmute, reset and save/reopen. Verify the intended source alone changes, Original follows chosen A/B audio, solo remains preview-only, and meters clear on pause/seek. Compare preview/export with normalization on/off and inspect master level, clipping, pumping, missing channels, fades and sync. |
| Timeline/export persistence | Trim/reorder/restore, undo/redo, save, restart and reopen. Export must follow saved sequence, composition, audio and captions. Cancel/retry a disposable export and verify prior exports remain intact. Test A/B sync and embedded-camera composition separately when claimed. |

## 4. Test actual devices

- **Clean Windows:** extract to a new writable folder, without overlaying an old
  installation. Run **START CUTROOM.bat** and record normal setup prompts or
  blocks. Do not disable security controls. Manual editing must open without
  selecting/downloading a Story model. Import a permitted clip, cut, save and
  export; play it externally. Repeat launch and normal restart must preserve
  state without competing servers.
- **macOS 15 Apple Silicon and Intel:** test each supported architecture on an
  actual device. Launch **START CUTROOM.command** beside **App** through Finder
  with normal per-item security review. Record download/quarantine behavior;
  a local copy without quarantine does not prove real-download Gatekeeper
  acceptance. Never disable Gatekeeper globally. Verify setup, manual export,
  repeat launch, immediate restart, Safari and the intended everyday browser.
- **Transcription:** keep missing-model downloads pending until separately
  authorized. Require actual native-worker success, saved language/text/timing
  and representative accuracy. English smoke transcription does not establish
  Hebrew comprehension or generative Story quality.

A warm machine with cached dependencies is not clean-install coverage.

## 5. Review stabilization and chroma

For stabilization, create a separate copy and preserve the original/edit. Inspect
movement, crop, dimensions, audio, sync and duration; download, reuse and reopen.
Cancel/retry and verify unfinished owned output is removed. Include the Windows
long-path publication regression; a shorter-path success cannot replace it.
Missing filters must explain unavailability without automatic installation.

For chroma, compare the saved current-frame preview with an MP4 over moving
footage. Inspect edges, hair, spill, placement/order, audio and per-video
isolation. Check undo/redo/reset/reopen and unchanged original footage. Direct
transparent A/B compositing and alpha MP4 are not supported.

Manual quality may be marked **Not tested** with the related claim withheld;
required automated release feature cases must still pass without silent skips.

## 6. Release decision

Identity, final-source checks, required native/feature/transcription gates and
human acceptance must be qualified separately. Unresolved hard gates mean
**NO-GO**. Public staging, approved-pin changes and promotion require their own
authorization; source or documentation updates do not authorize deployment.

See [the qualification summary](../docs/plans/SEMANTIC_ACCEPTANCE_2026-10-17.md),
[platform guidance](../docs/PLATFORMS.md), [Mac beta guidance](../docs/MAC_BETA.md),
[chroma](../docs/CHROMA_KEY.md) and [stabilization](../docs/STABILIZATION.md).

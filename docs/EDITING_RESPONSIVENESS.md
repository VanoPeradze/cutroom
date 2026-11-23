# Dense timeline header responsiveness

## Scope

This local change reduces repeated validation while painting saved track
headers. It does not change project data, schema, rendering, audio, timeline
geometry, zoom limits, gestures, selection, keyboard bindings or save policy.
It adds no editor controls and does not publish or package the application.

Every synchronous header pass now shares one local validated track model and
track-ID map. The host supplies one exact paint-only receipt containing the
same timeline project object plus separate Lock and Unlock refusal reasons.
The receipt exists only during that pass. It is not stored between frames,
attached to buttons or used to authorize an edit.

Save/readiness notifications also request the existing coalesced timeline
draw. This fixes a verified pre-existing paused-state affordance: an unfinished
local draft could leave a Lock button looking enabled until an incidental
redraw, although the action guard correctly refused it. There is no new polling
loop, save or seek. A pending post-draw focus callback is preserved.

The existing click-time `layerTrackLockReadiness`, `toggleLayerTrackLock`,
`trackLockIssue`, `layerTrackActionIssue`, `editLayerTrack` and `applyManualEdit`
paths remain unchanged. A click rechecks the current model, drafts, gestures
and saves. Unlock can still recover a protected local draft without applying
or discarding it. It cannot bypass a malformed model or an actual active save.

The host receipt validates the saved model, including v3 mix and protection
fields, and checks project object, revision, view and saved track-model
ownership. The timeline independently validates the receipt shape and current
saved locked state. A present malformed, asynchronous, throwing or mismatched
callback disables protection controls. A host without the optional callback
retains the original singular readiness path.

## Why this change

A paired synthetic baseline used a small six-second edit and a dense edit with
199 saved tracks and 200 imported occurrences. Most additional dense clips
were disabled. This intentionally isolates editor overhead, not simultaneous
decoder saturation.

The baseline ran eight cases: both projects, with and without a selected clip,
and the Media/pool presentation versus the Audio pane. Each case had three
warmed five-second uninstrumented playback windows followed by three separate
instrumented windows. Viewport, browser, source files and project settings
were held constant. Mutation requests were blocked and recorded.

Before the change:

- Dense editor animation callbacks: 6.98-7.21 per second.
- Small editor animation callbacks: 73.53-74.10 per second.
- Dense track headers consumed 124.4-127.2 ms per draw and 98.0-98.3% of the
  measured inclusive timeline draw time.
- Enter-to-two-animation-frame seek latency was 129.5-144.1 ms on the dense
  edit versus 10.8-14.1 ms on the small edit.

These are headless Chromium measurements, not a physical display frame-rate
guarantee. Importantly, separate explicit video-quality counters showed
119-122 decoded base-video frames per five seconds, with zero dropped or
corrupt frames. The bottleneck was timeline/UI cadence, not seven-FPS decoded
video. Initial raw WebIDL quality objects did not serialize their counters;
only the corrected explicit-counter supplemental run is decoder evidence.

Prototype timers are inclusive and were collected separately from the
uninstrumented runs. Nested durations must not be added together.

## Paired results on the frozen runtime

All eight cases were repeated with the same three-window protocol on final
app `header-paint2`, with timeline/drop/SourceReview `header-paint1`. Independent
analysis of the complete reports found:

| Measurement | Before | After |
| --- | --- | --- |
| Dense editor animation callbacks per second | 6.98-7.21 | 64.73-71.90 |
| Small editor animation callbacks per second | 73.53-74.10 | 73.58-74.09 |
| Dense header time per draw | 124.42-127.24 ms | 1.30-1.46 ms |
| Dense total timeline draw time | 126.68-129.50 ms | 3.04-3.30 ms |
| Dense animation callback gap, 95th percentile | 143.14-169.90 ms | 20.00-20.10 ms |

The dense cases' median animation-callback rates improved by 9.39-10.01 times.
No long tasks were observed in the 24 uninstrumented after windows; each dense
baseline window had 33-36. Small-project cadence did not regress in this run.
The singular lock-readiness function was no longer called per row during
instrumented header painting. It remains the direct click-time guard.

The explicit base-video counters in the 24 uninstrumented after windows
recorded 119-123 frames per five seconds, no dropped frames and no corrupted
frames. The earlier app1 diagnostic recorded one isolated dropped frame; that
evidence is retained separately. The separate final matched decoder supplement
also recorded one dropped frame in its first dense window and none in the
remaining windows. These counters are reported separately from UI cadence.
This is not a universal zero-drop claim or a video-decoding frame-rate
improvement. In that matched supplement, dense Enter-to-two-animation-frame
latency fell from 129.5-144.1 ms to 20.2-22.6 ms.

## Safety and validation boundaries

- No persistent cache or asynchronous readiness receipt.
- Existing buttons and event listeners are reused; no header reconstruction
  is required on ordinary playback ticks.
- Saved clip content, file ownership, history and output are untouched.
- Unit tests cover exact guard-reason equivalence, malformed models and
  receipts, local-draft Unlock, synchronous ownership changes, bounded
  validation counts and fresh direct-action checks after a permissive paint.
- Native tests use only separate synthetic copies. Existing files and raw
  project documents are hashed before and after, including helper shutdown.
- No new render or inference is needed for this paint-only change. Existing
  output can be decoded read-only; that is not a new export or a byte-parity
  claim about a renderer change.

Zoom precision, canvas virtualization and broader MediaStudio readiness work
remain separate possible improvements. This change does not claim to resolve
them or to remove all large-project performance limits.

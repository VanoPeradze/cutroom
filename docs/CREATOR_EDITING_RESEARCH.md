# Creator editing: output contracts and quality bar

Research date: 5 September 2026. This document separates verified platform facts, observed examples, proposed product behavior, and implemented changes. No creator assets or proprietary code are bundled.

## What the finished edit must do

The user's reference is a vertical, edge-filled composition, now implemented as camera 30% above gameplay 70% following the follow-up preference. This is a composition preference, not a platform requirement. A two-source edit must follow semantic camera/screen roles, regardless of upload order. A combined recording needs a confirmed camera rectangle before it can become two views; game imagery alone must not be duplicated and called a facecam.

An editorial style must affect which complete moments survive, not just colors or cutting frequency:

| Editorial profile | Selection unit | Story requirement |
| --- | --- | --- |
| Competitive clutch | One engagement | Stakes and setup → continuous action → result and reaction |
| Funny moments | A few complete jokes | Setup → escalation → punchline, including the reaction |
| Reaction | Reveal and response | Enough context to understand the reveal, followed by the complete reaction |
| Commentary / explainer | One complete idea | Question or premise → supporting explanation/example → answer |
| Stream story | Connected events | Premise → essential setup → development → actual result |

These are CUTROOM editorial designs. They are not claims to reproduce a creator exactly or to guarantee engagement.

## Creator references and limits

- [StoneMountain64's official about page](https://stonemountain64.com/about) describes his FPS content and Commanding Officer persona. The [official highlights playlist](https://www.youtube.com/playlist?list=PLm5ULqUEpfidh2PwPwdTa39JeNPLx7z2i) supports squad interaction and stream highlights as reference categories.
- The main agent inspected frames during playback of [this official Short](https://www.youtube.com/shorts/w01FHCClut4). Direct observations: a camera window in the upper region; gameplay given most of the vertical area; a softened/blurred background around the facecam; large white, dark-outlined, short emphasis captions near the camera/game boundary. One sample does not establish a channel-wide cut rate, narrative formula, or zoom policy. YouTube's separate accessibility captions were also visible and must not be confused with the creator's burned-in text.
- “הבוטן” may mean [TheBurntPeanut](https://www.youtube.com/@TheBurntPeanut), whose [primary social profile](https://x.com/theburntpeanut/with_replies?lang=en) links that channel. That identity matching is an inference. No precise BurntPeanut editing rules were extracted from observed playback, so a named imitation preset would currently overstate the research.

## Platform contracts versus editing defaults

| Destination | Verified constraint / guidance | CUTROOM recommendation, not a platform maximum |
| --- | --- | --- |
| YouTube Shorts | Square/vertical, up to 3 minutes ([official Help](https://support.google.com/youtube/answer/15424877?hl=en)) | 9:16, 1080×1920; one gaming payoff or complete explanation. Do not pad a good 25-second moment to 60 seconds. |
| YouTube long form | 16:9 is the standard desktop ratio; upload at the recorded frame rate ([encoding guidance](https://support.google.com/youtube/answer/1722171?hl=en)) | Preserve wide gameplay/HUD and readable screen demonstrations. Build connected sections rather than stretching a Short. Current CUTROOM export uses a fixed frame rate; source-FPS export is not implemented by this change. |
| Instagram Reels | Meta's [publishing API documentation](https://www.postman.com/meta/instagram/folder/f95kq5e/reels-publishing) recommends 9:16. API requirements are not the consumer app's universal limits. | 1080×1920 with independently reviewed opening, captions and cover. A ≤3-minute local preset is a deliberate product default. |
| TikTok | [Content Posting API guide](https://developers.tiktok.com/docs/en/content-posting-api-media-transfer-guide) describes format constraints and account-dependent length; it is not a universal consumer-app duration limit. | 1080×1920, an immediately understandable first shot, readable captions, and a complete payoff. |

[YouTube's organic Shorts visual guides](https://support.google.com/youtube/answer/16215842?hl=en) warn about interface/device occlusion. TikTok/Meta downloadable ad safe-zone templates are ad guidance, not a guaranteed organic safe area. Platform-specific overlays should be adjustable and reviewed at phone size. The current caption-position controls remain manual; this change does not implement automated safe-area certification or publishing.

## Implemented in this iteration

- Creator frame button: 9:16, camera top 30%, screen bottom 70%, filled crop. Explicit Fit mode is retained for material where edge content is essential.
- Preview panes clip their own video; the embedded camera preview crops the selected rectangle rather than magnifying an approximate center across the other pane.
- The existing style catalog supplies a narrative structure to the AI and affects deterministic selection/context. Short complete candidates need not be filled with unrelated footage. Manual cuts remain authoritative.
- Failed/low-confidence Hebrew refinement cannot overwrite a usable first transcript. This prevents a known regression; it does not establish improved word accuracy.

## Acceptance gate before claiming “finished editing”

Build a small consented test set: Hebrew/English, speech over game audio, single baked-in camera, separate A/B, explanation and gameplay. Compare original audio against transcripts (word errors, missing sentences, names), then review setup/payoff completeness, cut boundaries, camera crop, caption timing/readability, and export sync. Compare against a human reference edit, including CPU time and memory.

Current tests verify control behavior, timing/selection contracts, and synthetic rendered pixels. They cannot prove that an unseen real recording tells a good story. No claim of professional-editor parity, universal platform readiness, or exact named-creator emulation is justified yet. Keep all defaults local/open-source; no model downloads or paid cloud calls are needed for the changes above.

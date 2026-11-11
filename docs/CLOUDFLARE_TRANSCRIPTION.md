# Optional Cloudflare transcription

**Experimental provider integration.** Offline contract tests exercise routing, privacy and failure behavior. No real recording has been uploaded for this implementation; live response compatibility, word-timing quality, Hebrew accuracy and billing behavior are not yet verified. Missing provider word timestamps fail safely rather than being fabricated.

## Separate speech from Story AI

Open **Transcription** in the top bar:

- **On this computer only:** no audio is dispatched to a cloud provider, even if Story AI uses Groq or another API. Story AI can still receive transcript text under its separate connection.
- **Cloudflare only:** audio goes to the reviewed account/model after explicit consent. A failure does not switch provider or run local inference.
- **Cloudflare, then cached local fallback:** the same explicit cloud consent, plus one local attempt after eligible rate-limit, service, connection or schema failures. A complete cached model/runtime and resource checks must pass before the first upload and are checked again after failure. No model downloads or cloud retries occur. Authentication, permission and oversized-request failures require correction rather than silent fallback.
- **Follow existing AI connection:** preserves the prior Groq/compatible/local speech route, including its existing credentials and consent. This is a one-time migration for previously saved cloud connections, not the fresh-install default.

Saving a choice changes future jobs only. Existing transcripts, captions and manual edits are preserved. Rebuild explicitly for a different transcription. Changing only the Story model does not invalidate unchanged speech cache or cause another audio upload. Route, model and account changes do invalidate incompatible speech cache.

## Configure your own account

The app reads `CUTROOM_CF_ACCOUNT_ID` and `CUTROOM_CF_API_TOKEN` from its launch environment. Supply these through your own trusted environment/secret-management workflow, then restart CUTROOM. Never put a token in a project, repository, URL, screenshot or issue report. CUTROOM has no shared account/key and does not create an account, accept provider terms or change a billing plan for you.

The supported fixed destination is `https://api.cloudflare.com`, using the Workers AI model `@cf/openai/whisper-large-v3-turbo`. This is generic Whisper Turbo, **not** the local ivrit.ai model. Cloudflare account IDs are displayed so you can verify the destination. The token is never sent to the browser, persisted by the app, included in project/cache metadata, or passed to a local speech worker. A job freezes the chosen configuration; connection changes cannot race past job admission.

Refresh the dialog, check the account/model and linked terms, and check the consent box yourself. Consent covers selected audio in future transcription jobs until you change the choice. It is bound to the account, model, fixed endpoint and disclosure version; a material destination/disclosure change requires fresh consent. Selecting a menu option is not consent and sends no audio. Selecting Local revokes saved Cloudflare consent for future jobs; it cannot reverse previous uploads.

## Privacy, costs and cancellation

[Cloudflare data usage](https://developers.cloudflare.com/workers-ai/platform/data-usage/) states that Customer Content is not used to train models and normally is not retained after processing, with documented safety, security, legal and feature exceptions. Operational metadata can be retained. Review the current provider documents rather than relying on this summary as a guarantee.

[Pricing and limits](https://developers.cloudflare.com/workers-ai/platform/pricing/) depend on your account/plan. A free allowance is not unlimited free processing; paid accounts can incur charges. HTTP 429 can mean a rate limit, not necessarily exhaustion of a daily free quota. CUTROOM does not verify your billing plan, impose an account spending cap, upgrade plans or automatically retry cloud requests. Check and control your account's limits yourself before enabling it.

Only selected audio, not video frames, is uploaded for speech. It is extracted into bounded mono PCM chunks with overlap; actual WAV duration/frame count and encoded request size are checked before each upload. HTTPS is fixed-host and does not follow redirects or system proxies. Responses must contain complete, finite, ordered, in-range word timings consistent with returned text. Silence requires an explicit empty response structure, not missing data. Partial or invalid results never replace a saved transcript.

Stop process cancels the local request and never starts fallback after cancellation. Already accepted audio or charges cannot be recalled. Fallback results record Cloudflare upload attempts and actual local execution; they must not be represented as wholly local processing. Temporary extracted audio is cleaned up at completion/failure/cancellation.

## What remains to validate

Before a real-service trial, obtain permission for the exact recording, recipient account/provider and any possible spending. Use a bounded synthetic or otherwise authorized recording, verify the actual provider schema/timestamps, compare mixed Hebrew/English captions and test quota/cancellation behavior. Do not claim lower WER, equal ivrit.ai accuracy or measured hardware performance based on offline tests.

[Local model policy](MODELS.md) · [Consented accuracy evaluation](TRANSCRIPT_EVALUATION.md) · [Model API documentation](https://developers.cloudflare.com/workers-ai/models/whisper-large-v3-turbo/)

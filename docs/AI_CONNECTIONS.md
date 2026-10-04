# AI, on your terms

CUTROOM is free and open source. AI can run locally, through your Groq account, or through a compatible cloud API provider. Manual cutting, imported media, audio mixing and MP4 export need no AI model, API key or provider account.

## Pick your connection

Open **AI connection** at the top of the app, choose an option, then select **Use local AI** or **Use this cloud connection**. Merely clicking an option does not change your connection or send your content anywhere.

**On my computer:** uses CUTROOM's local transcription and Story models. Model downloads, disk space and processing resources are required. No cloud key is needed.

**Online — Free tier:** uses your own Groq Free account, free within its quotas. Create your key in the [Groq console](https://console.groq.com/keys), paste it into CUTROOM, review your account's limits, and confirm cloud processing. Long recordings can exceed free quotas. CUTROOM cannot verify whether your key belongs to a free or paid account; a paid account may incur charges.

**My own API account:** choose Groq or an OpenAI-compatible provider. For another provider, enter its public HTTPS base URL, transcription model ID and Story model ID. Your account's billing and limits apply; the selection does not purchase or upgrade anything. A chat subscription alone does not supply API access.

The compatible endpoint must support both `/chat/completions` with JSON object response mode and `/audio/transcriptions` with `verbose_json` output and word timestamps. Both models must be available through the same base URL, API key and account. Compatibility with only chat completions is insufficient. HTTP, local and private-network destinations are rejected. Use the provider's API base URL, not its website or chat page.

These models do different jobs: **transcription** listens to selected audio and returns words with timing; **Story AI** reads those words and returns a JSON edit plan. A text-only chat model does not replace a timed speech model. This integration currently uses one provider connection for both jobs; choosing separate providers for speech and Story is not supported. Check both model IDs and both capabilities with your provider before using a long recording.

Thanks to Groq for making a free API tier available. CUTROOM is independent and is not sponsored or endorsed by Groq. [Groq rate limits](https://console.groq.com/docs/rate-limits) · [Billing FAQ](https://console.groq.com/docs/billing-faqs)

You can change connections when no processing job is active. Your saved projects do not contain the connection key.

## Prepare local AI

Models are separate downloads, not files bundled in the ZIP. **Transcription** turns speech into timed text; **Story AI** plans an edit from that text. Manual editing needs neither. Local Short/Reel planning needs both; default chronological YouTube cleanup does not require a Story model.

1. Choose **On my computer → Use local AI**, then reopen **AI connection**.
2. Under **Prepare local AI**, select **Refresh status**. Story AI needs the Ollama engine as well as model weights. If it is missing, **Get Ollama** opens the [official installer](https://ollama.com/download). Install it yourself, return and refresh. If installed but stopped, use **Start local engine**. Story downloads are unavailable until the engine is ready; transcription has its own model and does not require Ollama.
3. Select a suitable model and read its purpose and estimated size. Choose **Download transcription model** or **Download Story model**, then **Confirm download**. **Not now** dismisses the confirmation without starting. Opening the panel or refreshing status never starts a model download.
4. Watch progress in the same panel. Only one model download runs at a time. **Cancel download** requests cancellation; closing the panel does not cancel it. Wait for the task to stop before starting another. Reusable partial cache files may remain after cancellation.
5. Check **Downloaded** after completion. That checks local files, not available memory, inference speed or successful model execution. Internet is needed for missing files; cached models are reused.

Downloading a model does **not** select that project's performance profile or switch between local/cloud AI. Choose the corresponding Lite, Balanced or Quality profile in the project; Hebrew Quality has a separate configured speech model. You do not need every model. Estimated download sizes are not total installation sizes or memory requirements. See the [English guide](USER_GUIDE_EN.md#local-models-what-to-download), [מדריך בעברית](USER_GUIDE_HE.md), and [model details](MODELS.md).

The in-app model action does not silently install Ollama or approve operating-system permissions. Setup failures still need their cause resolved; use [first-run help](TEST_ON_ANOTHER_PC.md) or continue with Manual edit meanwhile.

Hebrew local transcription uses a short Hebrew/English spelling hint. In Auto, that hint is used for recovery only after Hebrew text has been recognized. Balanced and Quality can recheck up to two weak units, each at most 30 seconds, with at most 48 seconds of audio retried per local pass. They reuse the loaded speech model; Lite adds no such pass. Replacements must pass confidence, timing, speech-coverage and recognized English-spelling checks. Uncertain passages remain marked for review. This is transcription, not translation or text rewriting by Story AI. See [quality limits](QUALITY_AND_LIMITS.md) for the separate existing model-upgrade paths and validation limits.

## What leaves your computer?

For cloud transcription, CUTROOM extracts the selected audio track into small temporary chunks and sends those to your selected provider endpoint. For Story AI, it sends transcript text and editing context/instructions. It does not send video frames. Transcripts and instructions may contain sensitive information from your recording, so use cloud AI only for content you are allowed to share with the provider.

Editing, preview generation and video export still run locally. This is not a browser-only hosted editor, and it does not eliminate the local video-processing installation. Existing installers and ZIPs have not been made smaller by this change.

## Keys and privacy

- A key pasted into CUTROOM is held in the running server's memory, not written to project files, preferences, logs or browser storage by CUTROOM.
- Your selected mode and model are remembered, but the key must be reconnected after restarting CUTROOM.
- A session key is bound to its provider and base URL. Changing either requires a new key and fresh consent; CUTROOM does not forward the previous destination's key to a new endpoint.
- **Forget session key** clears the in-memory key and selects local AI.
- Advanced users can set `CUTROOM_GROQ_API_KEY` in their own launch environment for Groq. It is not a credential for a custom endpoint. CUTROOM does not create or persist that environment variable. Remove it yourself if you want to revoke that local configuration; the Forget button cannot remove a user-managed environment key.
- Provider retention and billing policies are governed by your provider account. Do not paste keys into feedback reports or screenshots.

## Models used online

Groq defaults:

- Transcription: **Whisper Large V3** (`whisper-large-v3`), with word timestamps.
- Story AI default: **GPT-OSS 120B** (`openai/gpt-oss-120b`), hosted by Groq.

You can enter another supported Story model ID under **Model settings**. For Groq, [check its model documentation](https://console.groq.com/docs/models). For a compatible provider, supply that provider's own model IDs and verify the endpoint requirements above; Groq model names do not automatically work elsewhere. Availability, retention and quotas are controlled by the selected provider. A connected key means it has been supplied, not that its permissions or model access have been verified.

## If a request fails

A missing or rejected key, exhausted quota, timeout or invalid/truncated JSON response stops the job with an explanation. CUTROOM does not retry failed network requests automatically, fall back to another provider, start a local model, or switch to a paid plan. Your originals remain unchanged.

One Story job normally makes several requests: understanding sections, planning, selection and review. If an otherwise valid summary omits a chapter, the existing planner may make a focused follow-up request for that chapter. Those calls also consume your provider quota; this is not a single-request workflow.

Cancel stops CUTROOM from continuing the job and closes the local request. It cannot reverse a request the provider has already accepted or any associated usage. Manually retrying a failed job may send audio again and consume quota.

## Beta verification

Automated tests cover opt-in consent, credential redaction, restart behavior, provider failures, cancellation, chunk timing and routing without local-model fallback. Responses are mocked: real provider inference has not been verified with a user API key in this change. No new claim is made about Hebrew accuracy or Story quality. Review transcripts, edits and exports before using them.

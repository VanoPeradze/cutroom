# Contributing to CUTROOM

Contributions can improve the editor, installation, documentation, accessibility, translations, or the website. CUTROOM is in beta; make small, reviewable changes and describe what you verified. See [beta status](BETA_STATUS.md) for the limits of existing validation.

## Before starting

Search existing issues for the same problem. Use the [bug report or feature request form](https://github.com/VanoPeradze/cutroom/issues/new/choose) to provide context. Discuss substantial features, new dependencies, and changes to project storage or editing behavior before starting a large implementation.

For a suspected vulnerability, follow the [security policy](../.github/SECURITY.md) instead of opening an ordinary issue.

Use synthetic or non-sensitive test media. Keep credentials, personal configuration, recordings, transcripts, client information, projects, logs, and model caches out of Git and issue attachments. The tracked `config.json` should contain shareable application defaults only. Review your staged diff even when files are covered by `.gitignore`.

## Project structure

| Path | Purpose |
| --- | --- |
| `server.py` | Local HTTP server and application API. |
| `cutroom/` | Python editing, analysis, transcription, AI connections, and rendering. |
| `cutroom/config.py` | Default settings, overridden by `config.json`. |
| `web/` | Editor interface in plain JavaScript, HTML, and CSS; no frontend build step. |
| `tests/` | Python regression tests, Node frontend tests, and synthetic smoke checks. |
| `scripts/` | Runtime checks, transcript evaluation, validation, and packaging tools. |
| `docs/` | User guides, developer notes, screenshots, and beta validation records. |
| `website/` | Separate static introduction/download website and its checks. |

## Local development

Clone the repository using your existing access, or fork it if repository permissions allow. Create a focused working branch. Work in a writable local folder and use disposable projects for testing.

### Windows

Run `run_windows.bat` from the repository root. The launcher performs initial setup when needed and opens the editor. Setup accepts Python 3.11 or 3.12, creates `.venv`, installs Python dependencies, and checks FFmpeg/FFprobe. It may download runtimes and attempt to install Ollama. Read the [setup guide](TEST_ON_ANOTHER_PC.md) for installation behavior and troubleshooting.

Keep the launcher console open while using the editor. Local AI models are separate downloads; manual editing does not require them or an AI account. See [AI connections](AI_CONNECTIONS.md) and [models](MODELS.md) before testing AI-specific changes.

### Linux development path

The repository includes Linux scripts. Install Python 3.11 or 3.12 and FFmpeg/FFprobe with your distribution's tools, then run from the repository root:

```sh
bash setup_linux.sh
bash run_linux.sh
```

The setup script creates `.venv` and downloads Python dependencies. These scripts are available for development; the shipped download and current beta validation focus on Windows. Report the exact distribution and environment with Linux findings.

The editor normally opens at `http://127.0.0.1:8765`. Keep it on the local computer; do not expose the development server publicly.

## Run the checks

After initial setup, install test dependencies in the same virtual environment. From the repository root on Windows:

```powershell
.\.venv\Scripts\python.exe -m pip install -r tests/requirements.txt
.\.venv\Scripts\python.exe -m pytest -q
node --test tests/frontend*.test.cjs
```

On Linux, use `.venv/bin/python` in place of `.\.venv\Scripts\python.exe`. Node.js is needed for frontend tests, not for running the editor. Node.js 22 or newer also covers the website's documented runtime requirement. Rendering checks need a working FFmpeg/FFprobe installation.

Run focused checks while developing, then the relevant broader suite before submitting code changes. For example:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_manual_start.py -q
node --test tests/frontend_welcome.test.cjs
```

For interface or editing changes, also exercise the affected workflow with non-sensitive footage. Describe the input, settings, and observed result in the pull request. Automated regression tests and synthetic rendering checks do not establish speech accuracy, editorial quality, or a successful installation on a clean PC. AI-quality work should follow [transcript evaluation](TRANSCRIPT_EVALUATION.md) and state which models and examples were actually evaluated.

### Website changes

The website has its own source and checks. From the repository root:

```powershell
cd website
npm test
node --check public/site.js
```

These checks do not need an npm dependency install. The full `npm run check` also validates the exact approved beta ZIP and requires it in `website/public/downloads/`. If it is missing, `npm run prepare:download` fetches the approved archive from the existing public website; it requires network access. See the [website guide](https://github.com/VanoPeradze/cutroom/blob/HEAD/website/README.md) for using a local approved archive instead.

Publishing the website or changing its advertised beta download is a separate maintainer action. A contributor does not need to deploy it to submit a pull request.

## Submit a pull request

1. Keep each change focused on one issue or related behavior. Follow the surrounding Python, JavaScript, and CSS conventions.
2. Add a regression test when changing behavior that can be checked meaningfully. Keep the application interface and main README in English; update translated user guides where applicable.
3. Explain the problem, resulting behavior, and relevant tradeoffs. Include issue links and sanitized screenshots for visible interface changes.
4. List the checks you ran, their results, and any untested behavior. Avoid claiming a clean-machine installation or real-media quality test unless you performed it.
5. Review the complete diff and attachments for private content, generated files, and unrelated changes before submitting.

Preserve Windows installer encodings and line endings using the repository's `.gitattributes`. Avoid unrelated dependency upgrades or formatting sweeps. Include only code, media, fonts, and other assets you have permission to contribute; preserve applicable license notices. Contributions are made under the [MIT License](../LICENSE).

## Build a shareable package

Packaging is useful when testing distribution changes. From the repository root, with the existing runtime ready:

```powershell
.\.venv\Scripts\python.exe scripts/build_test_package.py
.\.venv\Scripts\python.exe scripts/build_test_package.py --verify PATH_TO_ZIP
```

The builder uses an allowlist, fresh default settings and per-file SHA-256 hashes. It writes the archive and checksum to `dist/`. It does not bundle runtimes or model weights.

Never ZIP the whole working directory: it may contain private footage, projects and installed runtimes. Check the extracted package as well as the source tree before sharing it. Creating or verifying a package does not publish a release or change repository visibility.

## Further reading

- [Installation, hardware notes and troubleshooting](TEST_ON_ANOTHER_PC.md)
- [Models and evaluation recommendations](MODELS.md)
- [Independent editing behavior](INDEPENDENT_TRACKS.md)
- [License](../LICENSE) and [third-party notices](THIRD_PARTY_NOTICES.md)

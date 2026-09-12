# Contributing to CUTROOM

Thank you for helping make editing more accessible. For the private beta, coordinate changes and reports with whoever shared the project with you. Please keep recordings, transcripts and client information private.

## Project structure

- `web/`: plain JavaScript and CSS frontend.
- `cutroom/`: Python editing, analysis and rendering code.
- `server.py`: application entry point.
- `cutroom/config.py`: default settings, overridden by `config.json`.

Keep credentials, personal configuration, media, projects and model caches out of Git. The shipped configuration contains only application defaults.

## Run the checks

After [initial setup](TEST_ON_ANOTHER_PC.md), install test dependencies in the virtual environment:

```powershell
.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.venv\Scripts\python.exe -m pytest -o addopts='' -q
node --test tests/frontend*.test.cjs
```

Node is needed for frontend tests, not for running CUTROOM. Regression tests and synthetic rendering checks do not establish speech accuracy or editorial quality. See [transcript evaluation](TRANSCRIPT_EVALUATION.md) and [beta status](BETA_STATUS.md).

## Build a shareable package

```powershell
.venv\Scripts\python.exe scripts/build_test_package.py
.venv\Scripts\python.exe scripts/build_test_package.py --verify PATH_TO_ZIP
```

The builder uses an allowlist, fresh default settings and per-file SHA-256 hashes. It writes the archive and checksum to `dist/`. It does not bundle runtimes or model weights.

Never ZIP the whole working directory: it may contain private footage, projects and installed runtimes. Check the extracted package as well as the source tree before sharing it. Preserve Windows installer encodings and line endings using the repository's `.gitattributes`.

## Further reading

- [Installation, hardware notes and troubleshooting](TEST_ON_ANOTHER_PC.md)
- [Models and evaluation recommendations](MODELS.md)
- [Independent editing behavior](INDEPENDENT_TRACKS.md)
- [License](../LICENSE) and [third-party notices](../THIRD_PARTY_NOTICES.md)

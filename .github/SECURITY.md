# Security policy

CUTROOM is beta software. There is no published long-term support schedule or guarantee of fixes for older beta builds. Include the exact version or commit when reporting a problem.

## Report a vulnerability privately

Do not disclose a suspected vulnerability in a public issue or pull request.

Use GitHub's [private vulnerability reporting form](https://github.com/VanoPeradze/cutroom/security/advisories/new). Private vulnerability reporting is enabled for this repository. A report is not an ordinary public issue.

If that option is unavailable, contact the repository owner privately through an existing trusted contact channel and ask where to send the report. If you received a beta build directly, you can use the private channel through which it was shared. Do not post exploit details or sensitive attachments while arranging contact.

A useful report includes:

- The affected CUTROOM version, beta archive filename, or Git commit.
- Operating system, browser, and relevant configuration, with secrets removed.
- A description of the issue, its possible impact, and the conditions required to reproduce it.
- Minimal reproduction steps using synthetic or non-sensitive data.
- Sanitized logs or a small proof of concept, if needed.

Exclude API keys, credentials, private footage, transcripts, client data, and full project or data directories. Redact usernames, local paths, and other identifying details from logs and screenshots. Coordinate any disclosure with the maintainer through the private reporting channel.

## Scope and safe use

This repository contains the local editor, its setup and packaging scripts, and the static website source. Reports about those components are welcome. Vulnerabilities in third-party tools, models, or AI services should also be reported through the affected project's own security process.

CUTROOM is intended to run on the local computer. Keep its server on the default loopback interface; do not expose it through public hosting, tunnels, or port forwarding. Use copies of source media and review exported files. Optional online AI sends selected audio and editing context to the chosen provider; see [AI connections](../docs/AI_CONNECTIONS.md) before processing sensitive material.

For ordinary bugs and feature requests, use the [issue forms](https://github.com/VanoPeradze/cutroom/issues/new/choose). See [beta status](../docs/BETA_STATUS.md) for current validation limits.

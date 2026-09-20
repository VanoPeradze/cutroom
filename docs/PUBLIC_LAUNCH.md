# Public repository launch checklist

Preparation does not authorize changing repository visibility or publishing a GitHub Release.
The repository remains private until its owner explicitly chooses to open it.

## Before changing visibility

- Confirm the intended default branch includes the reviewed source and new README.
- Review all reachable Git history, commit authors, screenshots and prose. The current
  conservative scanner is useful but does not detect every secret or privacy concern.
- Keep model weights, API keys, recordings, transcripts, local projects and generated ZIPs out of Git.
- Verify the chosen beta archive and checksum, including clean-machine setup and a real
  footage test. The existing source package is not an offline installer.
- Run full backend/frontend tests and synthetic renders for an application release.
  The **Repository checks** workflow only covers documentation, frontend tests and the
  website download validator; it never proves speech accuracy or editing quality.
- Confirm third-party notices and model licenses. The application's MIT license does
  not relicense its dependencies or model weights.
- Choose a private security-reporting channel. Enable GitHub private vulnerability
  reporting after the repository is public, then verify the Security tab shows it.

## Honest badges and release statistics

The README uses public static badges for the real application version, MIT license,
beta status, Windows download and optional AI. These work while the repository is private.

There are currently no GitHub Releases or release assets. Consequently, no GitHub
download count is displayed. Downloads from the Expo website are not GitHub downloads,
and neither source-clone counts nor a made-up number is an appropriate substitute.

After a reviewed **public GitHub Release** with a ZIP asset actually exists, the owner
may add a download badge, labelled precisely:

```markdown
[![GitHub release downloads](https://img.shields.io/github/downloads/VanoPeradze/cutroom/total?style=flat-square)](https://github.com/VanoPeradze/cutroom/releases)
```

After the repository and workflow are publicly accessible, a live status badge can be added:

```markdown
[![Repository checks](https://github.com/VanoPeradze/cutroom/actions/workflows/repository-checks.yml/badge.svg?branch=master)](https://github.com/VanoPeradze/cutroom/actions/workflows/repository-checks.yml)
```

Verify both badges anonymously before adding them. Do not expose credentials in badge URLs,
show a passing badge before a successful run, or advertise a release that does not exist.
Use a prerelease tag for beta packages and keep source-version and packaged-build labels distinct.

## Website and repository publishing

- Website publishing stays in `website/`; opening GitHub does not move the editor to the cloud.
- Update private-repository wording in website and maintainer docs only after visibility changes.
- `PUBLISH.bat git` intentionally refuses public repositories. Do not disable its safeguards;
  review and explicitly choose a public Git workflow before using it after opening the repo.

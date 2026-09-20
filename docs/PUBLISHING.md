# Package and publish CUTROOM

The [CUTROOM GitHub repository](https://github.com/VanoPeradze/cutroom) is public. Publish reviewed source changes through the normal Git workflow; publish the introduction/download website through the separate Expo workflow below.

`PUBLISH.bat` remains useful for inspecting and building the clean beta ZIP. Its legacy Git commands require an **existing private GitHub repository** and intentionally reject the current public repository. That guard has not been removed; it does not change repository visibility.

Double-clicking `PUBLISH.bat` only inspects the package candidate and displays its exact file list. It does not upload, install, commit, or change accounts.

## Choose the action you actually need

Run maintainer commands from the repository root in a Git checkout. In the downloaded Windows beta, these technical files live inside `App`; that package contains source but no Git metadata.

| Command | What happens | Internet / external changes |
| --- | --- | --- |
| `PUBLISH.bat` or `PUBLISH.bat plan` | Show the exact source-package inventory and basic privacy checks. | None. |
| `PUBLISH.bat package` | Build a clean ZIP and SHA-256 checksum in `dist`. | None. You decide who receives it. |
| `PUBLISH.bat git` | Legacy private-target checks. Rejects the current public repository. | Read-only GitHub/Git requests; no push. |
| `PUBLISH.bat git --publish` | Legacy private-target checks, tests, and exact typed confirmation before a push. Rejects the current public repository. | Writes only to a confirmed private GitHub repository. |
| `PUBLISH.bat expo` | Explain why the local editing backend cannot be deployed this way, then stop. | None. |

### 1. Make a tester ZIP

```bat
PUBLISH.bat package
```

The existing allowlist builder includes application source, user guides, tests and fresh default configuration. It excludes your recordings, projects, transcripts, exports, logs, API connection settings, installed runtimes, model weights and Git metadata. It never ZIPs the entire folder. The finished archive is checked again before it is copied into `dist`.

The ZIP contains your **current source files**, including intentional uncommitted changes. A ZIP and a Git push are different operations: the Git workflow only accepts a clean, committed checkout. Review the displayed inventory before sharing either one.

Send the ZIP together with its `.sha256` file. Ask the tester to use **Extract All** and double-click **START CUTROOM.bat**. The extracted folder has three top-level entries: **START CUTROOM.bat**, **START HERE.html** (offline help), and **App** (source, technical files and saved work). Keep them together. The launcher runs the existing `App/run_windows.bat` setup/startup flow; Git source checkouts and older flat packages still use `run_windows.bat` directly.

The first setup still downloads dependencies; optional local AI models require their own downloads. This is a source-based test package, not a fully offline or single-file installer.

Do not send personal source footage along with the app unless you have permission. Screenshots and other committed images still need a human privacy and rights check: an automated scanner cannot understand everything inside an image.

### 2. Publish reviewed source to the public repository

Use a Git checkout and the normal Git workflow to review differences, stage the intended files, and commit the reviewed changes. Check the staged diff and attachments for private content, and run the relevant [contributor checks](CONTRIBUTING.md) before publishing. Leave recordings, local configuration, generated ZIPs and unrelated drafts out of the commit.

Confirm that `origin`, the destination branch and the commit are the ones you intend to publish, then use a normal non-force Git push of that reviewed branch. If the remote has changed, fetch and review it before proceeding. This publishes committed source; it does not upload the beta ZIP, create a GitHub Release or deploy the website. Review and publish the download through the Expo workflow separately.

Do not use `PUBLISH.bat git --publish` for this public repository or change visibility to satisfy it. Its private-target restriction is a legacy safeguard, not the public repository's publishing workflow.

### Legacy Git helper: private targets only

The helper deliberately does not run `git add .`, create a commit, discard files or hide changes in a stash. Unlike a normal Git push, it requires a clean committed checkout and also blocks on untracked files. Ignored user data is left alone.

The helper's default expected repository is still `VanoPeradze/cutroom`, so its visibility check now rejects that public target. Both fetch and push URLs of `origin` must resolve to the selected GitHub repository. An existing private repository can be selected explicitly with `--repo owner/name`; this does not create it or change `origin`.

For the Git actions, install Git and the GitHub CLI yourself and sign in using your normal workflow. The publisher uses the current account and verifies that the repository is private, writable and not archived. It does not log in for you, request broader scopes, print tokens or change visibility. If authentication or network access is unavailable, it stops.

For an intentionally selected private target only:

```bat
PUBLISH.bat git
PUBLISH.bat git --publish
```

The second command requires an interactive terminal. It runs the Python regression suite, including the repository's frontend test wrappers; Node.js and development dependencies must already be installed. It displays the repository, branch, full commit ID and committed file inventory, then asks you to type a confirmation containing the repository, branch and abbreviated commit ID. It checks the state again afterward.

Only the confirmed commit is pushed to the current branch name. Tags and submodule pushes are disabled. There is no force push, merge, automatic fetch, GitHub Release, ZIP attachment, public visibility change or website deployment. If the remote branch changed, is ahead or is not available locally for comparison, fetch and review it yourself before trying again.

A branch that does not yet exist remotely requires an additional explicit `--new-branch` option. This creates only that branch, not a repository. Do not use it to bypass a rejected push to an existing branch.

The checks inspect all reachable file history, not just the newest files. Historical runtime data, private files, large binaries, symlinks/submodules and recognizable credentials stop publishing. Scanner output names the file/reason, never the suspected secret value. The scanner has conservative limits and is **not a complete secret/security audit**. It may reject harmless fixtures; review them rather than weakening the guardrail or committing real keys. It cannot guarantee that prose, commit messages or images contain no personal information.

If the terminal closes or the network fails during a push, inspect GitHub before retrying. Do not assume the push failed just because the final message was not shown. Cancelling cannot undo a push already accepted by GitHub.

## Website hosting is separate from the editing engine

The public introduction and download website is hosted on **Expo / EAS Hosting** at [cutroom-studio.expo.app](https://cutroom-studio.expo.app/). Its maintained source is in the public repository's `website/` directory. That directory is intentionally excluded from the application tester ZIP.

To update the website from a Git checkout, open `website/`, follow its README and run `npm run deploy`. The website workflow verifies the approved download and publishes only its `public/` directory to the existing Expo project. Generated ZIP files are ignored by Git and restored using a pinned size and checksum. When publishing a newly approved ZIP, supply it locally before its first deployment; it is not available from the live site yet. GitHub source, the website and the beta download are public; each still has its own publishing step.

CUTROOM's **editor** still uses a Python server, native FFmpeg and optional local AI processes. Uploading its frontend alone would not make video editing work in the cloud. `PUBLISH.bat expo` remains a safety stop for that application backend, not the website deployment command. An actual hosted editor would require a separate design for private media, job isolation, retention, authentication and processing costs. No such infrastructure or paid plan is created by either workflow.

## Before inviting testers

- Run the regression suite and synthetic render checks on the same source you package.
- Extract the generated ZIP on another computer and test first-time setup without your development environment.
- Exercise manual editing, local model preparation and opt-in cloud mode separately.
- Use a real short recording you know well to check speech, cuts, source layout, captions, audio and the exported result. Automated tests do not establish real-world editorial quality.
- Say clearly that CUTROOM is free/open source and in beta. A provider's free tier has limits; a personal paid API account may incur that provider's charges.
- Provide the [tester guide](TEST_ON_ANOTHER_PC.md) and [feedback form](BETA_FEEDBACK.md). Keep private client material out of bug reports.

## בקצרה בעברית

לחיצה כפולה על `PUBLISH.bat` מבצעת בדיקה בלבד ולא מעלה דבר. כדי ליצור חבילה נקייה לשליחה לבודקים מריצים `PUBLISH.bat package`; התוצאה נשמרת בתיקיית `dist`, ללא הסרטונים, הפרויקטים, המפתחות והמודלים שלכם. אחרי חילוץ מלא מפעילים את **START CUTROOM.bat** ומשאירים לצדו את **START HERE.html** ואת תיקיית **App**.

מאגר GitHub של CUTROOM כבר ציבורי. מפרסמים אליו שינויים בדוקים באמצעות commit ו־push רגילים לענף שנבדק. הפקודות הישנות `PUBLISH.bat git` ו־`PUBLISH.bat git --publish` עדיין מיועדות למאגרים פרטיים בלבד ולכן דוחות את המאגר הציבורי; אין לשנות את ההגנה או את נראות המאגר כדי לעקוף זאת. יש לבדוק את ה־ZIP במחשב נוסף לפני שמפיצים אותו.

אתר ההצגה וההורדה כבר פועל ב־https://cutroom-studio.expo.app/. כדי לעדכן אותו מתוך עותק Git, נכנסים לתיקיית `website`, קוראים את ה־README שלה ומריצים `npm run deploy`. רק האתר והחבילה המאושרת מתפרסמים; עורך הווידאו, הסרטונים והמודלים נשארים במחשב המשתמש. תיקיית האתר אינה חלק מחבילת הבטא להורדה.

# Prepare CUTROOM for testers

`PUBLISH.bat` is a maintainer tool. It can prepare a clean tester ZIP and, after checks and confirmation, push an already reviewed commit to an **existing private GitHub repository**. It does not turn CUTROOM into a hosted editing service.

Double-clicking it is safe: the default only inspects the package candidate and displays its exact file list. It does not upload, install, commit, change accounts or change repository visibility.

## Choose the action you actually need

Open a terminal in the CUTROOM folder:

| Command | What happens | Internet / external changes |
| --- | --- | --- |
| `PUBLISH.bat` or `PUBLISH.bat plan` | Show the exact source-package inventory and basic privacy checks. | None. |
| `PUBLISH.bat package` | Build a clean ZIP and SHA-256 checksum in `dist`. | None. You decide who receives it. |
| `PUBLISH.bat git` | Check the existing private GitHub target, clean committed branch, history and fast-forward safety. | Read-only GitHub/Git requests; no push. |
| `PUBLISH.bat git --publish` | Perform those checks, run regression tests, ask for an exact typed confirmation, then push that one commit/branch. | Writes to the confirmed private GitHub repository only. |
| `PUBLISH.bat expo` | Explain the unsupported hosting target and stop. | None. |

### 1. Make a tester ZIP

```bat
PUBLISH.bat package
```

The existing allowlist builder includes application source, user guides, tests and fresh default configuration. It excludes your recordings, projects, transcripts, exports, logs, API connection settings, installed runtimes, model weights and Git metadata. It never ZIPs the entire folder. The finished archive is checked again before it is copied into `dist`.

The ZIP contains your **current source files**, including intentional uncommitted changes. A ZIP and a Git push are different operations: the Git workflow only accepts a clean, committed checkout. Review the displayed inventory before sharing either one.

Send the ZIP together with its `.sha256` file. Ask the tester to extract the entire ZIP and start `run_windows.bat`. The first setup still downloads dependencies; optional local AI models require their own downloads. This is a source-based test package, not a fully offline or single-file installer.

Do not send personal source footage along with the app unless you have permission. Screenshots and other committed images still need a human privacy and rights check: an automated scanner cannot understand everything inside an image.

### 2. Review and commit intended changes

The publisher deliberately does not run `git add .`, create a commit, discard files or hide changes in a stash. Use your normal Git workflow to review differences and commit only the files you intend to share. Untracked files also block pushing until you make a deliberate decision about them; ignored user data is left alone.

The default expected repository is `VanoPeradze/cutroom`. Both the fetch and push URLs of `origin` must resolve to that same GitHub repository. Another private repository can be chosen explicitly with `--repo owner/name`; this does not create it or change `origin`.

For the Git actions, install Git and the GitHub CLI yourself and sign in using your normal workflow. The publisher uses the current account and verifies that the repository is private, writable and not archived. It does not log in for you, request broader scopes, print tokens or change visibility. If authentication or network access is unavailable, it stops.

### 3. Check, then publish deliberately

```bat
PUBLISH.bat git
PUBLISH.bat git --publish
```

The second command requires an interactive terminal. It runs the Python regression suite, including the repository's frontend test wrappers; Node.js and development dependencies must already be installed. It displays the repository, branch, full commit ID and committed file inventory, then asks you to type a confirmation containing the repository, branch and abbreviated commit ID. It checks the state again afterward.

Only the confirmed commit is pushed to the current branch name. Tags and submodule pushes are disabled. There is no force push, merge, automatic fetch, GitHub Release, ZIP attachment, public visibility change or website deployment. If the remote branch changed, is ahead or is not available locally for comparison, fetch and review it yourself before trying again.

A branch that does not yet exist remotely requires an additional explicit `--new-branch` option. This creates only that branch, not a repository. Do not use it to bypass a rejected push to an existing branch.

The checks inspect all reachable file history, not just the newest files. Historical runtime data, private files, large binaries, symlinks/submodules and recognizable credentials stop publishing. Scanner output names the file/reason, never the suspected secret value. The scanner has conservative limits and is **not a complete secret/security audit**. It may reject harmless fixtures; review them rather than weakening the guardrail or committing real keys. It cannot guarantee that prose, commit messages or images contain no personal information.

If the terminal closes or the network fails during a push, inspect GitHub before retrying. Do not assume the push failed just because the final message was not shown. Cancelling cannot undo a push already accepted by GitHub.

## Why there is no Expo upload button yet

If “EXPO” means **Expo / EAS Hosting**, its documented deployment path is an Expo Router/React web build with a JavaScript/Workers server runtime. CUTROOM currently uses a plain JavaScript frontend with a Python server, native FFmpeg rendering and optional local AI processes. It is not an Expo project, and uploading the frontend alone would not provide working video editing. See [Expo's hosting overview](https://docs.expo.dev/eas/hosting/introduction/) and [web deployment instructions](https://docs.expo.dev/deploy/web/).

The appropriate near-term distribution is a private tester ZIP plus the private source repository. A public introduction/download page could be hosted separately later. An actual hosted editor needs a deliberate backend design: authentication, private media storage, job isolation, deletion/retention controls, resource limits and a budget for processing. A free API tier does not supply free hosting or unlimited rendering. None of those services is provisioned by this tool.

If “EXPO” refers to a different product or destination, confirm its exact URL/account before connecting a deployment command. No guessed deployment or paid resource is created.

## Before inviting testers

- Run the regression suite and synthetic render checks on the same source you package.
- Extract the generated ZIP on another computer and test first-time setup without your development environment.
- Exercise manual editing, local model preparation and opt-in cloud mode separately.
- Use a real short recording you know well to check speech, cuts, source layout, captions, audio and the exported result. Automated tests do not establish real-world editorial quality.
- Say clearly that CUTROOM is free/open source and in beta. A provider's free tier has limits; a personal paid API account may incur that provider's charges.
- Provide the [tester guide](TEST_ON_ANOTHER_PC.md) and [feedback form](BETA_FEEDBACK.md). Keep private client material out of bug reports.

## בקצרה בעברית

לחיצה כפולה על `PUBLISH.bat` מבצעת בדיקה בלבד ולא מעלה דבר. כדי ליצור חבילה נקייה לשליחה לבודקים מריצים `PUBLISH.bat package`; התוצאה נשמרת בתיקיית `dist`, ללא הסרטונים, הפרויקטים, המפתחות והמודלים שלכם.

`PUBLISH.bat git` בודק את יעד ה־GitHub הפרטי ללא העלאה. `PUBLISH.bat git --publish` מריץ בדיקות ודורש אישור מפורש לפני העלאת השינוי שכבר בדקתם ושמרתם ב־commit. הוא לא הופך את המאגר לציבורי ולא מעלה אתר עובד. יש לבדוק את ה־ZIP במחשב נוסף לפני שמפיצים אותו. פרסום ב־Expo אינו מחובר כרגע: קודם צריך להבהיר את היעד ולהתאים לו את צד השרת, ולא רק להעלות את המסך החיצוני.

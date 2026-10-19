# Offline, unpublished review candidates

`verify_review_candidate.py` is a separate source/identity gate for an explicitly
selected private review pair. It does not select or replace an approved release,
change current/historical release pins, build a ZIP, or make a native-installation
claim. A passing report always remains **unpublished, review only, native pending,
not qualified for release**.

The explicitly reviewed record is the trust anchor. It pins the Windows and
combined ZIPs, their raw manifests, and the original source archive and Git
commit/tree. No record contains a download URL. Keep the record under review;
do not regenerate hashes to accept an unexplained change. A historical record
can only verify its own matching source and artifacts.

The historical October 18 private pair is anchored by [fe35453.json](review-candidates/fe35453.json)
for source `fe35453119305a33e0890a25e627a4fa47ad353d`. Its source/identity pass
keeps native acceptance and release qualification pending. See the
[qualification summary](../docs/plans/SEMANTIC_ACCEPTANCE_2026-10-17.md) for the
separate source, feature and human acceptance results.

The October 19 candidate is anchored by [7019b64.json](review-candidates/7019b64.json)
for source `7019b6423ce9d66531e933ee5cac42968f9e96e7`. Both packages were built
from that exact Git source archive. Its local source and platform-projection gates
passed. Native run [39244037429](https://github.com/VanoPeradze/cutroom/actions/runs/39244037429)
then passed on both ARM and Intel: 69 offline checks, 348 extracted feature tests,
all 50 required cases with zero skips, fresh installation, restart and missing-pip
recovery. The orchestration head is `b28561c7a3d277e90381d2e720eb50ab2fe001fb`;
the App source remains `7019b64`. The private record itself remains review only.
Public beta metadata records the separately authorized promotion and pending
Windows fresh-install, physical-device, human, model and real A/B acceptance.
That manual run selected this record and accepted exactly its three private ZIPs.
No model download or transcription is enabled by default.

The October 19 FFmpeg hotfix candidate is anchored by [8542cfb.json](review-candidates/8542cfb.json)
for source `8542cfb38275dcfacf2ad98788331ed8815a63f8`. The prior public Windows
package installed and opened in a fresh Windows Sandbox, but its first real
export failed after setup selected FFmpeg 9.0.2. The hotfix checks graph-file/CFR
capabilities and uses working modern or legacy options. Local synthetic exports
passed on FFmpeg 7.1.1 and 9.0.2; 346 relevant regressions passed without skips.
These configured-host checks do not replace exact-package native qualification.
That intermediate manual review selects this hotfix record and exactly its three
private ZIPs. Fresh Windows Sandbox exports/restart and both native Mac jobs
remain pending. Public downloads and historical validation pins are unchanged.

The final hotfix record is [0c28168.json](review-candidates/0c28168.json), source
`0c28168999f3500092d1954b9a17419400648684`. It also includes the English/Hebrew
README links for the hotfix downloads; the renderer and compatibility helper are
unchanged from the tested intermediate source. The manual workflow selects this
final record and its three exact private ZIPs. Its own fresh Windows and native
Mac qualification is required before publication; intermediate reports do not
qualify this new archive identity.

The command uses Python's standard library and local Git objects only. It never
imports or executes application or builder code, installs dependencies, downloads
`tiny.en` or any other model, calls a server, or accesses a remote service.

From a checkout whose complete package inputs still match that frozen source:

```powershell
python -B -X utf8 packaging/verify_review_candidate.py `
  --record PATH_TO_REVIEWED_RECORD_JSON `
  --windows-zip PATH_TO_MATCHING_WINDOWS_ZIP `
  --combined-zip PATH_TO_MATCHING_COMBINED_ZIP `
  --source-archive PATH_TO_ORIGINAL_TRACKED_SOURCE_ZIP `
  --repo . `
  --output PATH_TO_NEW_PRIVATE_QUALIFICATION_JSON
```

Supply the original source archive with the SHA-256 pinned in that record;
an arbitrary checkout export is not an interchangeable input. Omit `--output` to
print the report without creating a file. An output path must be new; overwrites
are refused. The output must have a `.json` extension and an existing parent
directory. It must be outside every frozen `SOURCE_TREES` directory and must not
resolve to a required source/overlay file or any verification input. Parent links
are resolved, and these protections are checked before qualification and again
before exclusive creation. Use an ignored `dist` review folder for local reports.
Exit status zero means the private source gate passed, not that
release or native acceptance passed. An error returns status one and a failed
review report.

The verifier checks:

- Exact archive sizes, SHA-256 values, build IDs and raw manifest hashes.
- Every original source-archive file against actual local Git blobs and the
  pinned full commit/tree. Only declared UTF-8 CRLF/LF differences are allowed;
  Windows BAT/PowerShell and binary bytes stay exact.
- The complete frozen payload allowlist, derived from AST literals in the
  frozen builder, including scripts, tests, docs, images and launchers.
- The complete current package-input inventory and bytes, so added/deleted
  eligible files or changed scripts/docs/launchers also fail. Unpackaged
  maintainer files may differ without pretending the entire Git HEAD is the
  frozen commit.
- Fresh default configuration and the generated testing guide, reconstructed
  from frozen AST literals. Actual local `config.json` is never used.
- All Windows entries preserved in the combined ZIP, all inherited Mac App
  entries identical, and precisely the seven frozen Mac overlays.
- Canonical paths, duplicates, collisions, links, permission bits, inventories,
  CRC/hash integrity, LF Mac launcher shebangs, and privacy exclusions.
- Both archive identities and current inputs again before a successful return,
  to reject concurrent changes. Installation-verification flags remain false.

The verifier and its tests live under `packaging/`, outside the application ZIP's
source allowlist. Adding this maintainer gate does not change or rebuild the
frozen application candidate. Focused synthetic/provenance regressions run with:

```sh
python -B -X utf8 -m unittest discover -s packaging/tests -p 'test_*review*.py'
```

## Explicit native review path

`native_review_candidate.py` is maintainer orchestration outside the frozen App
inputs. It first proves that the selected record is the unchanged committed
`HEAD:packaging/review-candidates/*.json` blob, then runs the full identity gate
again against all three original ZIPs and the current checkout. A saved PASS
report cannot authorize execution. Only after qualification does it create a
new report directory and derive an unpublished Windows baseline from the pinned
archive and verified manifest. No approved pin or application input is edited.

```sh
python -B -X utf8 packaging/native_review_candidate.py \
  --record packaging/review-candidates/fe35453.json --repo . \
  --windows-zip /review/inputs/CUTROOM-1.2-Beta-Windows-review-fe35453.zip \
  --combined-zip /review/inputs/CUTROOM-1.2-Beta-combined-review-fe35453.zip \
  --source-archive /review/inputs/SOURCE-fe35453.zip \
  --output-dir /review/new-reports
```

Default execution only qualifies and prepares local JSON; it does not import App
code, install anything, or run a model. `--native` explicitly enables native
macOS/Python 3.12 checks through the existing unchanged strict package verifier,
FFmpeg/source checks, extracted feature gate, and installation/restart helpers.
Normal fresh installation and missing-pip recovery are separate strict scenarios;
neither receives the previous-release restart exception. Archive/source/record
identity and all six approved pins are checked again around execution. Reports
remain unpublished and never assert human acceptance or release qualification.
`--transcribe` requires `--native`, defaults off, and separately permits the
existing synthetic-English `tiny.en` smoke. It does not establish Hebrew speech
quality or human editorial acceptance.

The existing `macos.yml` adds an explicit manual review mode. Supply
`review_release_id` only for the expected **draft**, unpublished
`cutroom-review-fe35453` release targeting the full frozen source commit. Its
committed record, exact three asset names and sizes, optional GitHub SHA-256
digests, release/asset IDs and repository API URLs must match before download.
Authenticated downloads use asset IDs; metadata download URLs are never used.
Fresh raw ZIP/Git qualification then precedes dependency installation.

GitHub rejected the draft fetch with HTTP 403 when the review job used only
`contents: read`. The proposed exception grants `contents: write` to the
temporary token of the manual review job only, because draft visibility requires
push access. This capability requires explicit approval before delivery/run;
the token has write capability for the whole review job even though transport
performs only fixed GET requests. The ordinary public job keeps
`contents: read`, and checkout credentials are not persisted. No personal token,
repository secret, repository/organization settings change or publication is introduced.

The two standard native runners use the exact downloaded ZIPs without rebuilding
them. `review_transcribe` defaults **false** and is independent of the historical
workflow's `transcribe` input. Only JSON evidence is retained for seven days;
candidate ZIPs, speech and model files are not uploaded as Actions artifacts.
This path requires an explicitly authorized draft upload and manual dispatch.
Preparing this code does not create a release, upload assets, dispatch a run or
authorize a model download.

The ordinary push/PR/public-baseline job and all current/historical approved pins
keep their existing checks. On source `596dcb2`, both native architectures passed
2,722 source tests (nine skips) and 623 frontend tests, then failed the unchanged
old-baseline comparison at `cutroom/caption_items.py`. All subsequent extracted
feature, install, restart and transcription steps were skipped. A separate manual
review result must not be presented as a successful public-baseline run.

For this pair, transfer the original Windows ZIP (3,708,965 bytes), combined ZIP
(7,452,329 bytes) and source ZIP (7,145,010 bytes): **18,306,304 bytes** total.
Use the 975-byte record from the trusted checkout and retain the frozen Git
objects. Do not upload private raw test evidence, personal media or models.

Local verification on 2026-10-18 passed all 69 synthetic provenance,
orchestration and transport regressions. The original `fe35453` pair also passed
fresh preparation, strict combined-package verification with the derived private
baseline, and source agreement for all 77 product files per platform. Ordinary
verification still rejected it with `Unexpected Windows baseline`. The three
original archive hashes, original verifier and all six public pins stayed
unchanged. No new native run, installation, model operation, artifact upload or
workflow dispatch was performed by these local checks.

Native Intel/Apple Silicon execution of the exact candidate, required setup and
restart checks, `tiny.en` transcription, clean-machine Windows installation,
Finder/Gatekeeper/Safari checks, and human editing/listening acceptance remain
separate evidence. Keep model downloads pending when they are not authorized.

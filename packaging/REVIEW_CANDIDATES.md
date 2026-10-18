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

The current private pair is anchored by [fe35453.json](review-candidates/fe35453.json)
for source `fe35453119305a33e0890a25e627a4fa47ad353d`. Its source/identity pass
keeps native acceptance and release qualification pending. See the
[qualification summary](../docs/plans/SEMANTIC_ACCEPTANCE_2026-10-17.md) for the
separate source, feature and human acceptance results.

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
python -B -X utf8 -m unittest discover -s packaging/tests -p test_review_candidate.py
```

## Remaining native/public gates

The existing native CI still selects the approved public baseline. That older
baseline/source comparison is unchanged and can still fail for this newer
candidate. A passing local review report does not turn that workflow green or
skip its checks. The native workflow and current/historical approved pins remain
unchanged. Repository checks run the verifier's synthetic tests; they do not
consume or publish the private review pair.

The same offline verifier can run on a native machine when the exact local ZIPs,
source archive, record and Git objects are provided there. This qualifies source
identity only. The existing CI has no local-path review-pair input; transporting
private artifacts into CI would require a separately authorized artifact/workflow
path, while public immutable staging/pin changes require release authorization.
Neither transport was performed here.

Native Intel/Apple Silicon execution of the exact candidate, required setup and
restart checks, `tiny.en` transcription, clean-machine Windows installation,
Finder/Gatekeeper/Safari checks, and human editing/listening acceptance remain
separate evidence. Keep model downloads pending when they are not authorized.

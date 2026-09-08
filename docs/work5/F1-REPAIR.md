# Work 5 — G5 F1 repair handback

The first binding G5 at 55912da264dab923eddc8f5545b78b0e91b3a369 returned FAIL/F1.
Its importer/runtime checks passed. F1: a file-only ZIP lost empty required
workspace directories, so a normal extraction could not be opened by installed CLI.
The author independently reproduced the refusal: evidence/g5-f1-before.json.

## Invariant and repair scope

A retained fictional trial must preserve its selected directory layout as well as
all file bytes. A manifest's file hashes alone do not establish restorability.
tools/retain_trial.py writes explicit directory entries, including empty nested
directories; it verifies CRC, decompressed file hashes and directory inventory.
It only creates a new archive outside the stopped source trial and excludes the
separately installed venv and Python caches. It does not promise live-DB snapshots.
The regression extracts an actual initialized workspace, reopens it and runs init
without repair, preserving DB bytes and an additional nested empty directory.

New artifact: evidence/retained-trial-v2.zip, SHA-256
fdb39d39441f9e739e2d6ec17391ad7500a8d86284a79b186df073088487bb51.
Manifest: evidence/retained-trial-v2-manifest.json, 26 original files and 15 directories.
All 26 file hashes equal the old manifest and original trial. Original archive and
manifest remain untouched as historical FAIL evidence; current instructions use v2.
src/, migrations, dependencies, wheel and the trial are unchanged.

## Class sweep

| Site | Disposition and evidence |
|---|---|
| Work5 main workspace backup | Fixed locally: processes/inbox and all other selected directories survive actual extraction. status/list/history/init and result/basis reads pass. |
| Work5 fault-workspace backup | Fixed locally by the same mechanism. Layout opens; the intentional missing-result refusal remains. No fabricated repair of fault evidence. |
| Other empty/nested directories | Complete source inventory includes unrelated-cwd; regression also covers nested empty inbox child. No per-directory hard-coded repair list. |
| Accepted Work4 retained-trial.zip outside the diff | Already contains all 14 workspace/fault directory entries, including processes/inbox. SHA-256 1cc89ce63d6b6ff7e73699257db7dfbf80a6025076edad056cbfa3fc0f856f82 unchanged; inventory in g5-f1-before.json. |
| Earlier Work1–3 locators and 162 preserved original files | Not new ZIP writers in this Product scope. Original hashes rechecked unchanged in g5-f1-restored.json. |
| G5 evidence archive and failing original extraction | Reviewer-owned evidence; not a repair target. Original report and archive hashes checked unchanged. |
| Core layout validation / init | Correct existing refusal; unchanged. Runtime reopening verifies the repair without weakening it. |

## Actual local verification

evidence/g5-f1-restore-script.txt extracts v2 into a new folder, compares all files
and directories, then calls original installed zara.exe from an unrelated cwd.
Result: evidence/g5-f1-restored.json — 11 CLI checks. Both main/fault copies pass
status, handoff list, history and init. Main result and basis bytes match saved
hashes; fault result still refuses as content_unavailable. Both extracted copies
retain every byte/directory after reads. Original trial, 162 earlier originals,
14 Direction sources and the first G5 report/archive remain unchanged.
All 16 installed Python files equal unchanged source and the retained wheel.
The documented PowerShell Expand-Archive route was also executed with a separate
fresh offline wheel installation: evidence/g5-f1-walkthrough.json and
g5-f1-walkthrough-install.txt. All four commands passed; 26 file hashes and all
15 directories were verified after reading, without manual layout repair.

Full native gate: evidence/g5-f1-deliver.txt — 99 tests, format/lint/hygiene,
strict types, two dependency boundaries, wheel/sdist and report structure.
The earlier first scoped lint attempt found one overlong line, corrected before
this full run. No product behavior or old evidence was changed for verification.

## Independent recheck required

The local checks above are executor evidence. The original binding FAIL remains
until the separate reviewer verifies the exact new commit/artifact. Recheck normal
extraction and installed reads, all files/directories, unchanged runtime/wheel and
the original archive. Existing runtime claims may reuse the first G5 after exact
source comparison. Record the new verdict separately, preserving G5-REPORT.md.
This Product repair neither closes T4/open_call/M0 nor starts Work6; HOME is solmax.
No owner runtime words or full Work8 demonstration are claimed.

END_OF_FILE: docs/work5/F1-REPAIR.md

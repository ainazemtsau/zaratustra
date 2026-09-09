# Reproduce the bounded G5 checks

Review files are outputs only. Use a NEW clean worktree at exact candidate
`f917565e141804508c11954c5de51566e82c48ca`; do not switch or modify Work3,
Work7 or the author's execution copy. Preserve STOP/STEER and obey them.
Candidate must be clean for the evidence audit. Do not run against setup/main.

1. Read candidate AGENTS/validation.config/PLAN and the named CALL. Check cwd,
   `git rev-parse HEAD`, clean status and STOP/STEER.
2. Make `_scratch/g5-reproduce/tmp` in that new copy. Copy the retained
   `independent_probe.py.txt` to `_scratch/g5-reproduce/independent_probe.py`
   and `audit_evidence.py.txt` to `_scratch/g5-reproduce/audit_evidence.py`.
   Keep this two-level layout under the repo: the scripts derive repo ROOT
   from it. Both scripts require a NEW output directory inside that copy's
   `_scratch`. Nothing under docs, src, tests, tools or config needs editing.
3. In PowerShell from the new repo root:

```powershell
$env:TMP = Join-Path (Get-Location) '_scratch/g5-reproduce/tmp'
$env:TEMP = $env:TMP
uv sync --locked
uv run --locked python -m tools.check --deliver
uv run --locked python _scratch/g5-reproduce/independent_probe.py _scratch/g5-reproduce/behavior-01
uv run --locked python _scratch/g5-reproduce/audit_evidence.py _scratch/g5-reproduce/audit-01
```

Use the approved managed Python 3.13.7. If sandbox denies uv/cache/runtime,
request allowed escalation; do not replace the candidate or runtime.
Never reuse an existing output folder. A failure is retained with its outputs;
do not repair DB/Markdown or delete evidence to obtain PASS.

Expected: full native PASS; 41 independent groups PASS; all 8 audit groups
PASS. UUIDs and new timestamps differ in fresh fixtures. The three author
backup restores must reproduce original proposals, pre-submit context bytes,
result fingerprints/revisions and exact next phases. Full post-replay DB bytes
are not expected to equal the historical DB because confirmation/time is new.

The scripts operate through installed public Core and process_probe surfaces;
they do not run the author's tools.probe_m1. Only the backup retention utility
is reused. Archive extraction verifies paths/layout/SHA and always targets
new fictional scratch directories; historical absolute paths are provenance.

## Saved evidence locators

- `behavior-evidence.zip`: independent fixtures, every mutation input/request/
  authority/receipt, rejection before/after DB hash/state/history, own pre-submit
  backups, contexts and three original-backup restorations.
- `audit-evidence.zip`: source/authority hashes, runtime, re-derived diffs,
  exact original archive restoration and byte/state audit results.
- `raw/behavior-checks.json`: named independent outcomes.
- `raw/audit-checks.json`: named evidence audit outcomes.
- `raw/native-deliver.txt`: complete native stdout/stderr.
- `review-manifest.json`: every other review output's SHA-256 and size;
  self excluded. ZIP manifests additionally hash all decompressed members and
  inventory directories. The manifest is anchored by the review commit.

Original product evidence remains unchanged at candidate under
`docs/m1-probe/evidence/`. Original-backup success locators are
`two-rule-contrast.zip!batch/step-1/before.zip`,
`two-rule-contrast.zip!cycle/step-0/before.zip` and
`two-rule-contrast.zip!cycle/step-2/before.zip`.

Review commit can be derived with
`git log -1 --format=%H codex/g5-m1-probe-20260909 -- docs/g5/m1-probe-20260909`.
Its parent is the exact product candidate; it changes only this review folder.
The commit's own hash is deliberately not embedded in its tracked contents.

END_OF_FILE: docs/g5/m1-probe-20260909/REPRODUCE.md

# Work 7 — runnable local walkthrough

Candidate source: 5866a48c5f9d0f492ad55723120366ffe8f08921, branch codex/work7-result.
Product checkout: C:/projects/zaratustra/_scratch/work7-result. Version0.7.0.
Commands below use PowerShell. Before commands, read any STOP or STEER.md in the
checkout. Never use accepted Work5/6 data or negative-copies as a write target.
Native command: uv run --locked python -m tools.check --deliver.

## Restore the exact accepted-effect trial into a new directory

This route reproduces saved Result discovery and next context. The archive already
contains schema6/revision12; do not resubmit its completed Work. It includes the
wheel, runtime dependency pins, raw inputs and scripts, all 149 files and 136
directories, excluding disposable venv/__pycache__. Offline dependencies must be
available in the existing uv cache; if unavailable, report that concrete blocker.

```powershell
Set-Location -LiteralPath 'C:/projects/zaratustra/_scratch/work7-result'
$evidence7 = Join-Path (Get-Location) 'docs/work7/evidence'
$archive7 = Join-Path $evidence7 'retained-trial.zip'
$restore7 = Join-Path ([IO.Path]::GetTempPath()) ('zaratustra-work7-owner-' + [guid]::NewGuid())
New-Item -ItemType Directory -Path $restore7 | Out-Null
Get-FileHash -Algorithm SHA256 -LiteralPath $archive7
Expand-Archive -LiteralPath $archive7 -DestinationPath $restore7
uv venv --python 3.13.7 (Join-Path $restore7 'venv')
$python7 = Join-Path $restore7 'venv/Scripts/python.exe'
$zara7 = Join-Path $restore7 'venv/Scripts/zara.exe'
$workspace7 = Join-Path $restore7 'workspace'
uv pip install --offline --python $python7 -r (Join-Path $restore7 'runtime-requirements.txt') (Join-Path $restore7 'zaratustra-0.7.0-py3-none-any.whl')
uv pip check --python $python7
Set-Location -LiteralPath (Join-Path $restore7 'unrelated-cwd')
& $zara7 --version
& $zara7 status $workspace7
& $zara7 projections status $workspace7
$receiptQuery7 = Get-Content -Raw -LiteralPath (Join-Path $restore7 'receipt-query.json')
& $zara7 result read $workspace7 $receiptQuery7
& $zara7 work open '09154bbb-34e0-4917-ad85-74cbaee0824d' --workspace $workspace7 --workspace-id '4846e59f-b3f8-4ed1-9bb3-fea22f713b88' --process 'bae978a9-a181-4368-be55-b1837fd47747' --expected-revision 12 --max-bytes 65536
```

result read and work open each ask for the exact separate local console
confirmation. Read the displayed path/operation/request and enter the exact
displayed confirmation only for this selected fictional copy. A file or flag is
not permission. The session's recorded seven confirmations were executor actions,
not owner runtime acceptance. Actual console prompts and byte capture are retained
in console-*-prompt.json and terminal-session.json/final-console-session.json.

Expected: version0.7.0, schema6/revision12, recorded Result operation
9179d4f8-d868-49c0-8ec8-3df7078bffc8, source done and next Work
09154bbb-34e0-4917-ad85-74cbaee0824d ready. Source completion never reopens.
The package is 20873/65536 bytes, eight sources, SHA-256
f9549bbbfd83eed752dae510c2f91db06217ff130673558c0643af5744fe1894.
Compare exact stdout bytes, not PowerShell formatted/re-encoded text. Our capture
drivers use subprocess.capture_output and Path.write_bytes. The retained
restart_read.py can reproduce exact Core wire in a separate OS process:

```powershell
$context7 = Join-Path $restore7 'recovered-context.json'
& $python7 -I (Join-Path $restore7 'restart_read.py') $workspace7 $context7 $restore7
Get-FileHash -Algorithm SHA256 -LiteralPath $context7
```

That diagnostic explicitly simulates already-granted local-chat permission; it is
not evidence that a real chat adapter received permission. CLI above exercises
the actual console. Result JSON spelling can use Unicode escapes without changing
decoded values. See OUTPUT-REPAIR.md for the repaired Windows encoding failure.

Archive SHA-256:
90acb543e44959949ea90a94a004528598fcc75b70bb58a6f2f6f21079bcdd2f.
retained-trial-manifest.json maps every exact file and directory. Our actual
PowerShell restoration is recorded in restore-verification.json and restore-* raw;
all 149 retained bytesets and 136 directories were checked before and after reads.
Its location was C:/Users/Anton/AppData/Local/Temp/zaratustra-work7-restore-0dy2qb3o.

## Reproduce submission from the accepted Work6 starting point

Use only a NEW copy of accepted Work6 main. The native probe validates accepted
Work6's entire retained file/directory inventory first, creates a new temporary
trial, copies only workspace, installs the built wheel outside checkout, compares
the old schema5 context byte-for-byte and explicitly migrates the NEW copy to6.
init remains1; plain migrate still targets4 and never silently upgrades to6.

```powershell
Set-Location -LiteralPath 'C:/projects/zaratustra/_scratch/work7-result'
uv build --no-sources
uv run --locked python -m tools.probe_result --accepted-trial 'C:/Users/Anton/AppData/Local/Temp/zaratustra-work6-_0caf231'
```

The last line prints the newly selected trial path. Substitute that actual path
below. If accepted Work6 is absent, first restore it per docs/work6/INSTALL.md;
use its main workspace and full retained inventory, never a negative copy.

```powershell
$trial7 = 'REPLACE_WITH_NEW_PROBE_PATH'
$trialPython7 = Join-Path $trial7 'venv/Scripts/python.exe'
Set-Location -LiteralPath (Join-Path $trial7 'unrelated-cwd')
& $trialPython7 -I (Join-Path $trial7 'exercise.py') --console $trial7
& $trialPython7 -I (Join-Path $trial7 'exercise.py') --exercise $trial7
```

The console driver asks for six separate exact confirmations and captures raw
submit/discover/next/replay/stale/budget stdout. The fictional next-content is
exactly OWNER-FIXTURE.md and request.json; new ids/events/timestamps mean a fresh
reproduction's context hash differs from the retained original. Compare that
run's own library/CLI/restart output. Successful submit advances11->12 once.
Terminal resubmit refuses (exit1, empty stdout); use original-id result read to
discover the committed effect. Stale11 and max-bytes5000 open also refuse with no
partial package. The installed exercise uses only labeled new negative copies
for the 14 fault groups. Additional retained installed_extra-source.txt records
SQLite rollback/exact retry, exact repair/quarantine, ungranted registered version
and separate-process lost-reply checks; it is not a general installer.

For manual API use the prepared request.json is the full bounded JSON input:
zara result submit <new-workspace> <request-file>. New file/model text never
authorizes itself. New actual consumer permissions and expected current revision
are always checked. Result read is durable metadata discovery; use work open for
fully revalidated current bytes. Physical loss can invalidate context without a
DB revision change. Repair follows the existing exact restore API/current rights,
or a faithful backup restored into another NEW selected copy; never patch DB.

## Evidence to retain and interpretation

Save actual Git HEAD/branch, PLAN and full base diff, wheel/source/installed hashes,
exact request, receipt query, context query, event/receipt/Result/next identities,
complete stdout/stderr and confirmation prompts, manifest and byte counts, native
--deliver output, installed diagnostic logs, full files AND directories backup,
restore comparison and old Work5/6 preservation. Runtime venv is reconstructible
from the wheel and exact pinned requirements. pre-repair-wheel.zip and initial
failed logs are diagnostics; final wheel is the one named in final-build.json.

Current inheritance grants two exact historical content versions and all recorded
acceptances. It does not grant arbitrary foreign/ancestor content or permission
to publish the next Artifact. Old acceptance decisions preserve their effective
revisions and do not claim to accept this new comparison task. The five facts
are recoverable in these bytes; actual clean-chat understanding/owner demonstration
remains Work8 and was not run. HOME: solmax; fresh physical G5 is still required.

END_OF_FILE: docs/work7/INSTALL.md

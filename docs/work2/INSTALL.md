# Install and try Work 2 — Zaratustra 0.2.0

Use the implementation commit named in RESULT.md. Prerequisites are the existing
uv and managed Python 3.13.7. No editable checkout, remote hosting or new service is
required. The exact tested wheel hash, paths and raw output are in RESULT.md.

## Reproduce the retained installed trial

From that product checkout:

```powershell
uv sync --locked
uv run --locked python -m tools.check
uv run --locked python -m tools.probe_install
uv run --locked python -m tools.probe_records --accepted-trial 'C:/Users/Anton/AppData/Local/Temp/solmax-work1-accept-20260907-a1/retained-trial'
```

The final path is the runtime locator from Direction's Work 1 acceptance receipt,
not a permanent user workspace. If it is no longer available, the probe cannot
claim that exact sample was preserved. Keep or restore that accepted trial from its
actual evidence before claiming the same migration check; do not fabricate its DB.

probe_records creates a new temporary directory outside checkout and retains it.
It copies the accepted workspace before running any migration, separately installs
the 0.2.0 wheel with locked dependencies, checks both versions and reads, runs
explicit migration, creates initial records and rereads them in new OS processes.
It confirms the accepted 0.1.0 wheel/DB hashes remain unchanged and that the old
executable still reads the original. It also runs a fresh empty-folder scenario.
Its printed receipt.json contains the installed executable and workspace paths.

## Manual trial in a new temporary folder

Build the wheel with the full check above, then from the product checkout:

```powershell
$zaraTrial = Join-Path ([IO.Path]::GetTempPath()) ('zaratustra-manual-' + [guid]::NewGuid())
New-Item -ItemType Directory -Path $zaraTrial | Out-Null
$zaraEnvironment = Join-Path $zaraTrial 'venv'
$zaraWorkspace = Join-Path $zaraTrial 'workspace'
$zaraRequirements = Join-Path $zaraTrial 'runtime-requirements.txt'
$zaraWheel = (Resolve-Path 'dist/zaratustra-0.2.0-py3-none-any.whl').Path
uv export --locked --no-dev --no-emit-project --no-hashes --output-file $zaraRequirements
if ($LASTEXITCODE -ne 0) { throw 'Dependency export failed' }
uv venv --python 3.13.7 --python-preference only-managed $zaraEnvironment
if ($LASTEXITCODE -ne 0) { throw 'Environment creation failed' }
$zaraPython = Join-Path $zaraEnvironment 'Scripts/python.exe'
uv pip install --python $zaraPython -r $zaraRequirements $zaraWheel
if ($LASTEXITCODE -ne 0) { throw 'Installation failed' }
uv pip check --python $zaraPython
if ($LASTEXITCODE -ne 0) { throw 'Dependency check failed' }
New-Item -ItemType Directory -Path $zaraWorkspace | Out-Null
$zaraCommand = Join-Path $zaraEnvironment 'Scripts/zara.exe'
Set-Location $zaraWorkspace
& $zaraCommand --version
& $zaraCommand init
if ($LASTEXITCODE -ne 0) { throw 'Initialization failed' }
& $zaraCommand migrate
if ($LASTEXITCODE -ne 0) { throw 'Migration failed' }
& $zaraCommand records create --process-title 'Fictional observatory' --goal 'Describe an imaginary moon' --expected-result 'A short fictional observation' --acceptance 'The observation is saved' --boundary 'Fictional data only' --budget 'One short local session' --artifact-title 'Observation draft'
if ($LASTEXITCODE -ne 0) { throw 'Record creation failed' }
& $zaraCommand records read
Write-Output ('Installed command: ' + $zaraCommand)
Write-Output ('Trial workspace: ' + $zaraWorkspace)
```

Expected: zara 0.2.0; init schema 1; migrate schema 2 with unchanged workspace_id
and created_at. records create/read show the same four UUIDs, stored fields, revision=1
on each record and state_revision=1. Work has status=draft and authority_scope=none;
Artifact has status=declared and active_version=null. Event identifies the local
creation and the actual package version, not an owner approval or accepted result.

In a different terminal, invoke the printed installed command with
`records read <printed-workspace-path>`. Compare all fields with the earlier output.
Repeating create fails and preserves existing data; it is not a replay receipt.
Repeated migrate/init/status/read leave the saved DB unchanged.

To try migration of older data, COPY the whole stopped disposable v1 workspace to a
new trial first, and point only the new executable there. Never migrate the retained
accepted original. There is no downgrade command; 0.1.0 refuses schema 2. No manual
SQLite/state Markdown edits, automatic repair or restoration guarantee is offered.
Failed trial directories remain available for diagnosis. Remove only your own
disposable trial later after checking its resolved absolute path and contents.

This trial is local executor/owner preparation. Independent install/upgrade proof,
owner runtime acceptance, binding fresh Direction G5 and the Work 8 demonstration
are separate, still-pending claims. Work 3–8, T1 and M0 are not closed here.

END_OF_FILE: docs/work2/INSTALL.md

# Install and try Zaratustra 0.1.0 locally

Prerequisites: uv, managed Python 3.13.7, and the local source revision named in
RESULT.md under `implementation_commit`. The wheel is not published remotely.
Use that revision's source to build; do not install an editable checkout as the trial.
The raw installation evidence records the exact wheel SHA-256 and installed version.

## Reproduce the automated trial

From the product checkout at the recorded revision:

```powershell
uv sync --locked
uv run --locked python -m tools.check
uv run --locked python -m tools.probe_install
```

The probe creates empty temporary directories, installs a non-editable wheel plus
locked dependencies, verifies the package resolves inside that environment outside
checkout, and invokes `--version`, `init`, `status`, `init`, `status <path>` through
the installed executable. Every invocation is a new process. Persisted JSON and
the complete DB bytes must remain equal after the first init. It removes only its
own temporary tree when finished. No personal data or manual DB changes are used.

## Try the same commands yourself (PowerShell)

Start in the product checkout at the recorded revision. This creates a new temporary
trial, with a separate installation and workspace, and leaves them available for
your next terminal session. It does not choose your permanent personal workspace.

```powershell
uv sync --locked
uv run --locked python -m tools.check
if ($LASTEXITCODE -ne 0) { throw 'Build/check failed' }
$zaraTrial = Join-Path ([IO.Path]::GetTempPath()) ('zaratustra-trial-' + [guid]::NewGuid())
New-Item -ItemType Directory -Path $zaraTrial | Out-Null
$zaraEnvironment = Join-Path $zaraTrial 'venv'
$zaraWorkspace = Join-Path $zaraTrial 'workspace'
$zaraRequirements = Join-Path $zaraTrial 'runtime-requirements.txt'
$zaraWheel = (Resolve-Path 'dist/zaratustra-0.1.0-py3-none-any.whl').Path
uv export --locked --no-dev --no-emit-project --no-hashes --output-file $zaraRequirements
if ($LASTEXITCODE -ne 0) { throw 'Dependency export failed' }
uv venv --python 3.13.7 --python-preference only-managed $zaraEnvironment
if ($LASTEXITCODE -ne 0) { throw 'Environment creation failed' }
$zaraPython = Join-Path $zaraEnvironment 'Scripts/python.exe'
New-Item -ItemType Directory -Path $zaraWorkspace | Out-Null
Set-Location $zaraWorkspace
uv pip install --python $zaraPython -r $zaraRequirements $zaraWheel
if ($LASTEXITCODE -ne 0) { throw 'Installation failed' }
uv pip check --python $zaraPython
if ($LASTEXITCODE -ne 0) { throw 'Installed dependencies conflict' }
$zaraCommand = Join-Path $zaraEnvironment 'Scripts/zara.exe'
& $zaraCommand --version
& $zaraCommand init
& $zaraCommand status
& $zaraCommand init
Write-Output ('Installed command: ' + $zaraCommand)
Write-Output ('Trial workspace: ' + $zaraWorkspace)
```

Expected: `zara 0.1.0`, then the same `workspace_id`, `created_at` and
`schema_version: 1` from every workspace command. The JSON paths point to the
trial workspace, not the installation or source. Retain the two printed paths.
In another PowerShell session, invoke that exact executable with
`status <printed-workspace-path>`; no activation or checkout is required.
You can alternatively activate the environment to put `zara` on that terminal's PATH.

You may later delete the disposable trial folder you created after inspecting its
resolved path and contents. Never repair SQLite or state Markdown to make a trial
pass. If init fails partway, it retains files and reports failure; recovery after
process/OS interruption is not implemented in Work 1. Use a new empty trial folder
for a new trial and retain the failed one for diagnosis.

This local trial is preparation for owner acceptance. It does not constitute an
independent participant's installation, an owner-performed run, an upgrade proof,
fresh Direction G5 or the complete M0 demonstration.

END_OF_FILE: docs/work1/INSTALL.md

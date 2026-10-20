# Reproduce E1 (developer/operator)

Qualified runtime candidate: `6659f4c4d9de1871624efaec37933aa8d03dc0bf`, public branch
`codex/zaratustra-v1`. A containing documentation/evidence commit must have identical
product inputs; use `scripts/c-identity.mjs` with this candidate as the previous ref.
The handback reports the exact final public and actually installed SHA separately.
This procedure is for qualification, not daily product UI.

Profile: Windows 11 x64, Node 22.19.0, npm 11.6.2, Pi 1.3.0, typebox host peer
1.3.27; one trusted personal writer, selected `openai-codex/gpt-6.1-sol`, medium.
Use new isolated directories outside checkout, package storage and personal data.
Do not read/copy credentials; native Pi authentication or supported authPath only.

```powershell
$candidate = '6659f4c4d9de1871624efaec37933aa8d03dc0bf'
$testRoot = Join-Path $env:TEMP ('zara-E1-' + [guid]::NewGuid())
New-Item -ItemType Directory -Path $testRoot | Out-Null
$env:PI_CODING_AGENT_DIR = Join-Path $testRoot 'agent'
$env:ZARATUSTRA_HOME = Join-Path $testRoot 'home'
$env:ZARATUSTRA_IMPORT_ROOTS = '["<absolute synthetic input root>"]'
# Declare one profile before its first conversation; never escalate a failing history.
$env:ZARATUSTRA_SCOPES = '["restricted:read","restricted:write"]'
pi install "git:github.com/ainazemtsau/zaratustra@$candidate"
pi list
$testPackage = Join-Path $env:PI_CODING_AGENT_DIR 'git/github.com/ainazemtsau/zaratustra'
git -C $testPackage rev-parse HEAD
pi update --extensions
git -C $testPackage rev-parse HEAD
$env:ZARA_PI_SDK = Join-Path (npm root -g) '@earendil-works/pi-coding-agent/dist/index.js'
node (Join-Path $testPackage 'scripts/c-identity.mjs') $testPackage (Join-Path $testRoot 'identity.json')
```

Unset scopes or `[]` means workspace-only. A separate protected profile has the two
trusted scopes shown above. The model cannot supply scope/home/principal arguments.
Native Pi/npm removes six `peer:true` flags in the installed lockfile; the identity
tool checks that these are the only differences. Versions/resolved/integrity stay exact.

For checkout: pinned `npm ci`, `npm run check`, `npm run deliver`, with a new absolute
`ZARATUSTRA_TEST_ROOT`. For installed disk suites, install only the existing pinned
test runner outside the package:

```powershell
npm install --prefix (Join-Path $testRoot 'tools') --no-audit --no-fund tsx@4.20.6
$env:ZARATUSTRA_TEST_ROOT = Join-Path $testRoot 'disk-tests'
New-Item -ItemType Directory -Path $env:ZARATUSTRA_TEST_ROOT | Out-Null
# Existing exporter/material tests use cwd-relative read-only assets.
# Keep the actual cwd outside the installed package as well.
$testRunCwd = Join-Path $testRoot 'disk-cwd'
New-Item -ItemType Directory -Path (Join-Path $testRunCwd 'scripts'), (Join-Path $testRunCwd 'tests/fixtures') | Out-Null
Copy-Item -LiteralPath (Join-Path $testPackage 'scripts/export-evidence.mjs') -Destination (Join-Path $testRunCwd 'scripts/export-evidence.mjs')
Copy-Item -LiteralPath (Join-Path $testPackage 'tests/fixtures/c') -Destination (Join-Path $testRunCwd 'tests/fixtures/c') -Recurse
$testAssetFiles = @((Get-Item -LiteralPath (Join-Path $testPackage 'scripts/export-evidence.mjs'))) + @(Get-ChildItem -LiteralPath (Join-Path $testPackage 'tests/fixtures/c') -Recurse -File)
foreach ($testAssetFile in $testAssetFiles) {
  $testRelative = $testAssetFile.FullName.Substring($testPackage.Length + 1)
  if ((Get-FileHash -LiteralPath $testAssetFile.FullName).Hash -ne (Get-FileHash -LiteralPath (Join-Path $testRunCwd $testRelative)).Hash) { throw 'Test asset drift' }
}
$testModulePaths = @('core','work','materials','p2','evidence','memory','experience') | ForEach-Object { Join-Path $testPackage "tests/$_.test.ts" }
Push-Location $testRunCwd
& (Join-Path $testRoot 'tools/node_modules/.bin/tsx.cmd') --test @testModulePaths
Pop-Location
node (Join-Path $testPackage 'scripts/e1-provenance.mjs') $testPackage (Join-Path $testRoot 'sdk-provenance')
node (Join-Path $testPackage 'scripts/p2-probe.mjs') $testPackage (Join-Path $testRoot 'p2') fixed
```

SDK provenance is **M**, zero provider dispatch. It injects interactive/rpc/extension
events through the real Pi event runner, checks unknown/transformed stage and caller,
and separately tests the trusted first/untransformed interactive contract. These are
mechanical injections, never genuine Anton feedback. Native loading supplies host peers;
directly importing the extension with a bare jiti loader does not reproduce Pi loading.
The retained first failed probe demonstrates that distinction. Four incompatible read
modifier combinations are negative controls. P2 tests unexplained selection with zero
provider requests/denied source reads/UUID allocations; it is not an alternate live model.

The production default does not attest original keystrokes or owner feedback. Only trusted
setup may assert `ZARATUSTRA_INTERACTIVE_INPUT_CONTRACT=first-untransformed`, after verifying
that this capture handler precedes transforming input handlers. With uncertain order, leave
it unset. Even this contract identifies the trusted local channel, not biometric authorship
or the truth of quoted material. The model must distinguish own speech from quotations;
semantic classification cannot elevate a programmatic source. This is not E2 action approval.

For a real filled D upgrade, install exact `1b742a6e774eaa14826c036977ae2a42ff1ca46a`
in another fresh Pi config. With its installed path as `$oldPackage`:

```powershell
$upgradeHome = Join-Path $testRoot 'upgrade-home'
$proof = Join-Path $testRoot 'upgrade-proof'
node (Join-Path $testPackage 'scripts/e1-upgrade.mjs') seed $oldPackage $upgradeHome $proof
node (Join-Path $testPackage 'scripts/e1-upgrade.mjs') verify $testPackage $upgradeHome $proof
node (Join-Path $testPackage 'scripts/e1-upgrade.mjs') old-reject $oldPackage $upgradeHome $proof
```

The old writer creates real schema-3 rows, Work completion/reopen/wait, claims, handoff
and BOM/CRLF/Unicode material. Final E1 migrates that filled home to schema 4 and compares
every old canonical row/material, identity, epoch, receipt replay and historical result.
The old D writer must refuse schema 4 without replacement. Fault tests cover backup,
transaction and manifest-repair boundaries. This developer copy is not E3 backup/restore.

Live qualification uses the existing `scripts/live.mjs`, one empty in-memory session per
new process and a different actual cwd. A scenario JSON contains agentDir/home/cwd/output,
budgetPath/importRoots, predeclared scopes and an **ordinary conversational prompt**.
Run `node <installed-package>/scripts/live.mjs <scenario.json>` from that scenario's cwd.
No mutation JSON, prescribed tool calls or scripted model replies belong in a prompt.
If an isolated config delegates existing native authentication, provide ZARA_AUTH_PATH
to Pi's supported ModelRuntime option; never copy or inspect its contents manually.

Initialize one new ledger once, then reuse it for every candidate/error/retry:

```json
{
  "provider": "openai-codex",
  "model": "gpt-6.1-sol",
  "prompts": 0,
  "requests": 0,
  "input": 0,
  "output": 0,
  "cache_read": 0,
  "estimated_usd": 0,
  "limits": {
    "prompts": 24,
    "requests": 180,
    "input": 9007199254740991,
    "output": 9007199254740991,
    "estimated_usd": 15
  }
}
```

Stop at the first cap. Record failed/incomplete attempts and actual dispatch hooks;
unknown provider/subscription billing stays unknown. These are development limits.
The executed E1 story and all preliminary attempts are in E1-VALIDATION.md/e1-evidence.
Reproduce save/application, fresh task without a method name/reminder, substantive unit
correction and exact old/new versions, late/corrected feedback, incomplete-data failure,
unresolved correction and read/foreign-report negative control. A synthetic RPC controller
checks addressing/handling; it never becomes real owner usefulness or T31.

Inspect actual calls and retained refs/versions, not only invocation rows. Recompute the
six small fixtures independently and link observed native calculation call IDs/digests
to retained Evidence. Check that old Runs/results stay exact, feedback creates no new
case and a method edit does not resolve the problem. Source retrieval, a model report,
technical observation, ended Run, Work acceptance and benefit remain separate.

Only after all producers finish and the ledger closes, freeze a fixed SHA256/length
list and use the existing `scripts/export-evidence.mjs`. Keep raw originals, declare
path/JSON/reasoning transformations and verify every exported digest. Never export
credentials, mutable current stdout, Pi config/cache or live database binaries. Final
public-SHA installation/readback uses new files after sealing; originals stay unchanged.

END_OF_FILE: docs/E1-REPRODUCE.md

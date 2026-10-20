# Reproduce the installed path (operator/developer)

For the current zero-model developer-exporter correction, use the focused
[stdout-alias recipe](C-STDOUT-ALIAS.md). It requires native Pi installation only;
the historical model-session recipes below are outside this correction's budget.

Select the exact public commit you intend to test. No historical candidate or branch
name is the default. Use the qualified Windows 11 x64 / Node 22.19.0 / Pi 1.3.0
profile. All homes, configuration and output below are disposable synthetic data,
outside checkout and package storage. Preserve each attempt in a fresh output folder.

```powershell
$publicCommit = Read-Host 'Exact published 40-character commit to install'
if ($publicCommit -notmatch '^[0-9a-f]{40}$') { throw 'A full exact commit is required' }
$testRoot = Join-Path $env:TEMP ('zaratustra-probe-' + [guid]::NewGuid())
$agentDir = Join-Path $testRoot 'pi-agent'
$zaraHome = Join-Path $testRoot 'home'
$cwdA = Join-Path $testRoot 'cwd-a'
$cwdB = Join-Path $testRoot 'cwd-b'
New-Item -ItemType Directory -Path $agentDir,$cwdA,$cwdB | Out-Null
$env:PI_CODING_AGENT_DIR = $agentDir
$env:ZARATUSTRA_HOME = $zaraHome
$env:ZARATUSTRA_IMPORT_ROOTS = '[]'
$source = "git:github.com/ainazemtsau/zaratustra@$publicCommit"
pi install $source
if ($LASTEXITCODE -ne 0) { throw 'Pi installation failed' }
pi list
$package = Join-Path $agentDir 'git/github.com/ainazemtsau/zaratustra'
$installedCommit = git -C $package rev-parse HEAD
if ($installedCommit -ne $publicCommit) { throw 'Installed identity mismatch' }
```

For interactive Pi, use its normal login/model selection in this isolated config,
start in cwdA, say the create request below, close Pi, then start in cwdB and say
the continuation. Do not resume a transcript or copy authentication files.

For the actual SDK observer, use the consciously selected recipient and delegate
authentication to Pi's supported authPath. Do not inspect or copy credentials:

```powershell
$env:ZARA_PI_SDK = Join-Path (npm root -g) '@earendil-works/pi-coding-agent/dist/index.js'
$env:ZARA_AUTH_PATH = Join-Path $env:USERPROFILE '.pi/agent/auth.json'
$budgetPath = Join-Path $testRoot 'budget.json'
@{
  provider='openai-codex'; model='gpt-6.1-sol'; prompts=0; requests=0
  input=0; output=0; cache_read=0; estimated_usd=0
  limits=@{prompts=24; requests=140; input=9007199254740991; output=9007199254740991; estimated_usd=15}
} | ConvertTo-Json -Depth 5 | Set-Content -Encoding utf8 $budgetPath
$scenario = @{
  agentDir=$agentDir; home=$zaraHome; cwd=$cwdA
  output=(Join-Path $testRoot 'create'); budgetPath=$budgetPath
  prompt='Создай область «Чтение». Хочу разобраться в книге, которую пришлю позже. Отвечай мне по-русски.'
}
$first = Join-Path $testRoot 'create.json'
$scenario | ConvertTo-Json -Depth 5 | Set-Content -Encoding utf8 $first
Push-Location $cwdA
node (Join-Path $package 'scripts/live.mjs') $first
Pop-Location
$scenario.cwd=$cwdB
$scenario.output=Join-Path $testRoot 'continue'
$scenario.prompt='Продолжим чтение. Что сейчас нужно?'
$second = Join-Path $testRoot 'continue.json'
$scenario | ConvertTo-Json -Depth 5 | Set-Content -Encoding utf8 $second
Push-Location $cwdB
node (Join-Path $package 'scripts/live.mjs') $second
Pop-Location
```

Record the recipient and limits before the first request. Retain failures and the
same ledger; never reset it during this check. The runner uses medium thinking,
checks the request/cost caps before another request, and counts attempts including
setup failures. Pi's cost is an estimate learned after responses. These are test
limits only. Each Node command creates a new in-memory session and exits its process.
Inspect actual tool calls, receipt, SQLite rows and Russian response; exit status
and prose alone do not prove persistence.

P2 mechanical reproductions (native SDK, zero model requests):

```powershell
node (Join-Path $package 'scripts/p2-probe.mjs') $package (Join-Path $testRoot 'p2-fixed') fixed
```

This observes actual source reads and UUID allocations with a permitted positive
control, calls native session.setModel without prompting that model, and proves
no denied read/staging/material/handle/domain mutation. It also checks the long
observed Evidence tail and Unicode boundary. `baseline` is only for the original
reviewed commit; `import-fixed` is the intentionally intermediate reproduction.

Fresh-process live tail retrieval uses a declared synthetic fixture retained by
installed Core capture/commit. The fixture controller is not a model-created user
path. The separate create/continue check above proves that path.

```powershell
node (Join-Path $package 'scripts/p2-tail.mjs') $package $zaraHome (Join-Path $testRoot 'tail-fixture')
$scenario.cwd=Join-Path $testRoot 'cwd-tail'
$scenario.output=Join-Path $testRoot 'tail'
$scenario.prompt='Где по сохранённому журналу наблюдений нужно оставить контрольный образец? Ответь по-русски.'
$third = Join-Path $testRoot 'tail.json'
$scenario | ConvertTo-Json -Depth 5 | Set-Content -Encoding utf8 $third
New-Item -ItemType Directory -Path $scenario.cwd | Out-Null
Push-Location $scenario.cwd
node (Join-Path $package 'scripts/live.mjs') $third
Pop-Location
```

The fixture proves the answer is past code point 8000 and absent from snapshot,
material cards and ordinary read. Verify it is also absent from the new prompt and
startup messages. Inspect actual zara_read.range calls and their returned tail;
only then assess the answer. Do not provide the fixture text/answer in the question.

Development checkout: `npm ci`, `npm run check`, `npm run deliver`. For installed
Core regressions, install a pinned `tsx@4.20.6` into a separate test-tools folder
and run installed `tests/core.test.ts` and `tests/p2.test.ts`. Set
`ZARATUSTRA_TEST_ROOT` to a fresh isolated output root. The extension peer mapping
is qualified through Pi SDK, not through direct tsx import.

```powershell
$tools = Join-Path $testRoot 'test-tools'
npm install --prefix $tools --no-audit --no-fund tsx@4.20.6
$env:ZARATUSTRA_TEST_ROOT = $testRoot
& (Join-Path $tools 'node_modules/.bin/tsx.cmd') --test (Join-Path $package 'tests/core.test.ts') (Join-Path $package 'tests/p2.test.ts')
```

Earlier first-block failure/lifecycle scenarios remain documented in
`docs/EVIDENCE.md` and `docs/ATTEMPTS.md`. For an independently justified rerun:
use `dropCommitResponse:true` for lost-response recovery, permitted synthetic
TXT/Markdown paths and importRoots for real imports, native package resource filters
for disable, and `pi remove $source; pi install $source` for same-commit reinstall.
Retain a separate observer outside cache before removing a package. Compare managed
workspace/material bytes. `pi update --extensions` reconciles installed resources;
bare `pi update` targets the host. Never run lifecycle probes against personal data.

## Outcome C exact-version reproduction

Code pin: `334c572691df179cbf37d9a6582e69effc8a4aed`; main completed live pin:
`55fac403fd4aba2f6e6ccb81d4e569ec5c0fde33`. Use the exact final public delivery SHA
from the return message for final installation; it changes docs/evidence only from
334c572. Never infer that a branch name is the tested executable version.

Use the initial native pi install recipe above outside checkout. The SDK resource
check below does not prompt a model. Set ZARA_PI_SDK and native ZARA_AUTH_PATH as above;
the path is passed to Pi, never read/copied by the controller.

```powershell
node (Join-Path $package 'scripts/c-identity.mjs') $package (Join-Path $testRoot 'identity.json')
node (Join-Path $package 'scripts/resources.mjs')
node (Join-Path $package 'scripts/p2-probe.mjs') $package (Join-Path $testRoot 'p2-c') fixed
& (Join-Path $tools 'node_modules/.bin/tsx.cmd') --test (Join-Path $package 'tests/core.test.ts') (Join-Path $package 'tests/p2.test.ts') (Join-Path $package 'tests/work.test.ts') (Join-Path $package 'tests/materials.test.ts')
```

Observed native lockfile delta is six removed peer:true flags; c-identity verifies
that every other tracked byte is exact and rejects any broader lockfile difference.
It does not call the installed tree clean. For a docs-only final delivery, pass
334c572691df179cbf37d9a6582e69effc8a4aed as c-identity's last argument to check every
product input (including scripts/tests/manifests/AGENTS) against the code candidate.

For the accepted-version upgrade, create a second isolated config/home, use native
pi install at full 27a74fd pin, then seed with the _new candidate's_ developer observer:

```powershell
$proof = Join-Path $testRoot 'upgrade-proof'
node (Join-Path $candidatePackage 'scripts/c-upgrade.mjs') seed $oldPackage $upgradeHome $proof
# In that isolated config, native pi install git:github.com/ainazemtsau/zaratustra@<full-new-SHA>
node (Join-Path $candidatePackage 'scripts/c-upgrade.mjs') verify $upgradedPackage $upgradeHome $proof
# A separately installed exact 27a74fd package must now reject this schema-2 home.
node (Join-Path $candidatePackage 'scripts/c-upgrade.mjs') old-reject $oldReaderPackage $upgradeHome $proof
```

Variables denote different genuine Pi installations, never a checkout copied into
package cache. Seed/verify are explicitly synthetic mechanical setup, not model acts.
Seed preserves 4 records/5 revisions/2 Changes/intents/receipts, long original material
and two Work revisions. Verify compares all original rows byte-for-byte, original
material hashes, workspace/epoch, receipt replay and P2 tail; tests also cover migration
faults, backups, interrupted manifests and unknown schemas.

[All 20 original scenario derivatives](c-evidence/scenarios) and
[actual conversations](C-CONVERSATIONS.md) are the reproducible live recipes. Replace
path placeholders with a new isolated synthetic root; preserve the same home across
related scenarios, use a new cwd/process/output per attempt, and retain one ledger.
The development ledger is already exhausted at 140 requests: **do not reset it or run
more development model calls**. A future separately authorized review uses its own
explicit budget and must not relabel our aborted attempt 20 a PASS.

For 14–15, copy synthetic tests/fixtures/c/book.pdf, book.epub and notes.md into
permitted importRoots using the scenario filenames. Retain via ordinary model request,
record original/derivative hashes, delete only those synthetic source copies, then
start process 15. Do not place hidden facts in prompts/snapshots/cards. The model must
choose real zara_read ranges. Compare actual provider tool outputs to managed bytes
and Unicode code-point offsets. Raw provider logs are available as sanitized gzip
JSONL; decompress with Python gzip or another standard gzip reader.

Parser generation is optional: scripts/c-fixtures.py uses separate fixture-only
pypdf 6.1.3, not a product dependency. Checked-in synthetic fixtures avoid regenerating
them for ordinary checks. The c-evidence/tools probes are inspectable mechanical
observers; they make no model requests. Public derivatives omit reasoning/local paths;
manifest.json records original and derivative digests and transformations. Original
managed homes/raw evidence remain in the isolated evidence root, outside Git.

## Targeted C continuation after PARTIAL

Previous C reviewer artifact is exactly 0d188eee3d25ac26a24d28b5a363e5c4b75a2e7c.
Fixed executable candidate is 14c4e0d263542344c9d577ef4035fefba5afcac4; final delivery
adds documentation/evidence only. Install the final exact SHA reported in the return
using the isolated native pi install recipe above. Keep separate Pi config/home/cwd;
never change personal credentials or copy auth files. Same supported ModelRuntime
native authPath and medium openai-codex/gpt-6.1-sol apply.

Required checkout commands remain npm run check and npm run deliver. Installed affected
checks (cwd must be the actual installed package; create the test root beforehand):

```powershell
$env:ZARATUSTRA_TEST_ROOT = Join-Path $testRoot 'affected-tests'
New-Item -ItemType Directory -Path $env:ZARATUSTRA_TEST_ROOT | Out-Null
& (Join-Path $tools 'node_modules/.bin/tsx.cmd') --test tests/work.test.ts tests/evidence.test.ts
node scripts/p2-probe.mjs $package (Join-Path $testRoot 'p2-targeted') fixed
node scripts/c-identity.mjs $package (Join-Path $testRoot 'identity.json') 14c4e0d263542344c9d577ef4035fefba5afcac4
```

The affected suite passes 13/13; full check/deliver 37/37. Source proof in
c-evidence/fix-20261020/parser-inputs-unchanged.json compares all 22 parser/storage,
dependency and fixture inputs to 0d188eee. No reason to repeat the reviewer's complete
material qualification, and it is not relabelled as a new run.

New actual scenarios, runner logs and readbacks are under c-evidence/fix-20261020.
All eight attempts used installed 14c4e0d2, fresh cwd/PID and empty transcripts.
The new ledger is closed at 8 attempts / 57 requests / USD 1.035156 Pi estimate;
**do not reset it or run a ninth development conversation**. Original executor and
reviewer ledgers remain separate and unchanged. A future independently authorized
review must name its own budget. In 06 provider transport failed four times. Pair
setup for 07–08 is explicitly mechanical via seed-pair.mjs, not model preparation.
Use the ordinary prompts as recorded; do not add tool names, IDs/statuses or mutation
JSON to steer the model. Read real records after each significant action.

The developer upgrade observer upgrade.mjs creates a new synthetic schema-2 fixture
using genuinely installed 0d188eee, then validates all ten tables after native Pi
upgrade before reconciling its legacy handoff/step/new wait through current API.
Old history/results/Changes/receipts stay exact. old-reject uses a separately retained
old installation against that isolated fixture and proves failed record-only resolution
without domain or receipt mutation. This is not a user restore or migration feature.

For evidence export, finish all selected commands first. Build a fixed sealed JSON
with root, explicit relative entries [{path,bytes,sha256}] and optional path-redaction
pairs. Keep stdout outside the selected inputs. Then run:

```powershell
node scripts/export-evidence.mjs $sealedInputs $newDerivativeDirectory $currentStdoutLog *> $currentStdoutLog
```

The exporter refuses a listed current stdout even if it was empty when sealed, checks
all source hashes before and after processing, canonicalizes LF before hashing, omits
reasoning, and gzip-compresses provider JSONL. Validate exported and staged Git blob
digests before push. The exporter log can enter only a _later_ completed sealed export.
The historical old manifest and empty derivative remain in c-evidence/history; current
source/version correction is explained in C-PROVENANCE-CORRECTION.md. No raw log is edited.

END_OF_FILE: docs/REPRODUCE.md

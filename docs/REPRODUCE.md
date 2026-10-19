# Reproduce the installed path (operator/developer)

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
  limits=@{prompts=6; requests=30; input=1500000; output=90000; estimated_usd=5}
} | ConvertTo-Json -Depth 5 | Set-Content -Encoding utf8 $budgetPath
$scenario = @{
  agentDir=$agentDir; home=$zaraHome; cwd=$cwdA
  output=(Join-Path $testRoot 'create'); budgetPath=$budgetPath
  prompt='Создай область «Чтение». Хочу разобраться в книге, которую пришлю позже. Отвечай мне по-русски.'
}
$first = Join-Path $testRoot 'create.json'
$scenario | ConvertTo-Json -Depth 5 | Set-Content -Encoding utf8 $first
node (Join-Path $package 'scripts/live.mjs') $first
$scenario.cwd=$cwdB
$scenario.output=Join-Path $testRoot 'continue'
$scenario.prompt='Продолжим чтение. Что сейчас нужно?'
$second = Join-Path $testRoot 'continue.json'
$scenario | ConvertTo-Json -Depth 5 | Set-Content -Encoding utf8 $second
node (Join-Path $package 'scripts/live.mjs') $second
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
node (Join-Path $package 'scripts/live.mjs') $third
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

Earlier first-block failure/lifecycle scenarios remain documented in
`docs/EVIDENCE.md` and `docs/ATTEMPTS.md`. For an independently justified rerun:
use `dropCommitResponse:true` for lost-response recovery, permitted synthetic
TXT/Markdown paths and importRoots for real imports, native package resource filters
for disable, and `pi remove $source; pi install $source` for same-commit reinstall.
Retain a separate observer outside cache before removing a package. Compare managed
workspace/material bytes. `pi update --extensions` reconciles installed resources;
bare `pi update` targets the host. Never run lifecycle probes against personal data.

END_OF_FILE: docs/REPRODUCE.md

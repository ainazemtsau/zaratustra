# Reproduce the installed path (operator/developer)

Use the qualified Windows 11 x64 / Node 22.19.0 / Pi 1.3.0 profile. The tested runtime
candidate is `8c9340d4a6717cf4c22ab1a8592378115a5d17aa`. The final handoff commit has
identical runtime inputs and its exact public hash is returned separately.

```powershell
$testRoot = Join-Path $env:TEMP ('zaratustra-probe-' + [guid]::NewGuid())
$agentDir = Join-Path $testRoot 'pi-agent'
$zaraHome = Join-Path $testRoot 'home'
$cwdA = Join-Path $testRoot 'cwd-a'
$cwdB = Join-Path $testRoot 'cwd-b'
New-Item -ItemType Directory -Path $agentDir,$cwdA,$cwdB | Out-Null
$env:PI_CODING_AGENT_DIR = $agentDir
$env:ZARATUSTRA_HOME = $zaraHome
$env:ZARATUSTRA_IMPORT_ROOTS = '[]'
$publicCommit = '8c9340d4a6717cf4c22ab1a8592378115a5d17aa'
$source = "git:github.com/ainazemtsau/zaratustra@$publicCommit"
pi install $source
pi list
$package = Join-Path $agentDir 'git/github.com/ainazemtsau/zaratustra'
git -C $package rev-parse HEAD
```

For native interactive Pi, use its normal login/model selection in the isolated
config, start from cwdA, say the create request below, close Pi, then start from
cwdB and say the continuation. No old transcript/resume and no copied auth files.

For the exact SDK observer used here, retain the owner's consciously selected
recipient and delegate authentication to Pi's supported authPath. The auth file is
never read manually or copied by these commands:

```powershell
$env:ZARA_PI_SDK = Join-Path (npm root -g) '@earendil-works/pi-coding-agent/dist/index.js'
$env:ZARA_AUTH_PATH = Join-Path $env:USERPROFILE '.pi/agent/auth.json'
$budgetPath = Join-Path $testRoot 'budget.json'
@{
  provider='openai-codex'; model='gpt-6.1-sol'; prompts=0; requests=0
  input=0; output=0; cache_read=0; estimated_usd=0
  limits=@{prompts=18; requests=80; input=1500000; output=90000; estimated_usd=20}
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

Each Node command creates a fresh in-memory session and terminates the process.
Inspect summaries/events/requests and real SQLite rows. For TXT/Markdown, create a
synthetic input directory, put it into scenario.importRoots (array), give the model
the ordinary material path in conversation, and inspect its actual zara_import,
committed Evidence and zara_read.range calls. For lost-response proof set
`dropCommitResponse:true` on a synthetic creation scenario; a new process with a
normal interrupted-answer question must discover its receipt without the request ID.
Never seed a response, a prepared commit, or the needed answer into the prompt.

Native lifecycle commands:

```powershell
pi update --extensions
git -C $package rev-parse HEAD
pi config
# In the isolated config disable this package's extension AND both skills.
node (Join-Path $package 'scripts/resources.mjs')
# Re-enable, then remove/reinstall the exact same source:
pi remove $source
pi install $source
```

The automated lifecycle used Pi's documented native package-resource filter form
`{source,extensions:[],skills:[]}` in isolated settings; it did not alter owner config.
Compare workspace/material hashes before/after and run a new conversation after
reinstall. `pi remove` removes the cache, so run a separately retained observer when
checking resource absence after removal. Explicit upgrade installs another exact
real commit; bare `pi update` targets the host and is not the package test.

Development checkout: `npm ci; npm run check; npm run deliver`. On the installed
candidate, use an isolated tsx tool installation to run its `tests/core.test.ts`;
the extension peer mapping itself is qualified through Pi, not direct tsx import.
Source/evidence inputs and failures are under `docs/evidence/`. Keep all test homes
outside package storage and never use a personal home as a disposable fixture.

END_OF_FILE: docs/REPRODUCE.md

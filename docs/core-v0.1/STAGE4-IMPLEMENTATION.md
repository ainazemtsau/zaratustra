# Core v0.1 Stage 4 — interactive Pi path

## Boundary

`zaratustra.pi_adapter` starts an ordinary upstream Pi process with an extension.
Pi owns the conversation, authentication, provider protocol and model cycle. A
localhost bridge owns one selected Core space and one trusted local actor. The
foundation remains the sole domain store. No independent RPC executor, DBOS
production dependency, scheduler or dispatcher is installed by this stage.

The host asks the console user to confirm the resolved new Core space, working
directory, local OS account and selected initial Activity/Work. It then binds
`LocalAuthority` to space id and execution epoch. The bridge has a random bearer
token, listens on `127.0.0.1`, and only accepts typed execution operations for
the selected Work. Text from a model cannot establish actor, grant or acceptance.

## User path

1. Create an empty Core space and synthetic or authorized Activity/Work using
   the public foundation operations. Provide the exact `--space`, `--workspace`,
   `--pi-cli` and `--pi-runtime` paths to
   `python -m zaratustra.pi_adapter`. Set a positive `--limit-units` and
   `--reserve-units`; select provider/model explicitly. Pi starts without tools
   unless the local operator chooses `--pi-tools`. Optional
   `--activity-id` and `--work-id` preselect one existing Work. The local runtime
   must contain ordinary upstream Pi and be writable for the temporary extension
   copy. The host removes that copy at exit.
2. In Pi, `/zara-work` chooses an Activity and Work, creates a persistent
   Attempt bound to its exact Work revision, input references, resource revision,
   session, epoch and generation. An active prior Attempt requires an explicit
   interruption after the old Pi process has stopped. `/zara-status` reads the
   current Core snapshot, including saved input/output bytes, basis, current
   Work rights, status and model ledger.
3. Before a prompt, the extension reads the exact current input Artifacts and
   injects a hidden context message. For each final observable HTTP body, including
   service calls and repeats, it creates a distinct invocation and records the
   body SHA-256 and byte length. It prepares, reserves and marks the invocation
   sent through atomic Core operations before calling `fetch`. A denied operation
   stops the HTTP request. Provider `stream` and `streamSimple` are wrapped; the
   Codex profile forces SSE because Pi's default Codex WebSocket path bypasses
   the observable `fetch` seam. The extension also wraps every other provider
   visible to Pi and refuses its stream while a Work is selected. Session start,
   model selection and the pre-request event refresh these guards. A model switch
   to an unsupported transport therefore fails before provider HTTP; it does
   not silently use another model or skip Core admission.
4. A completed answer with usage records actual units. Missing or failed
   outcomes remain `unknown` and hold the full reserve. A successful single
   textual Work output becomes a new Artifact and Work output link in one Core
   transaction. That transaction checks the Attempt's exact Work revision,
   current inputs, resource, session, epoch, generation and answered invocation;
   a later Work link prevents the old Attempt from publishing. An exact replay
   returns the same receipt. Work remains `proposed`. `/zara-accept` shows the
   exact current Work revision,
   outputs and requested basis, asks for an explicit UI confirmation, then uses
   a separate `work.accept` Grant and Core receipt to set `succeeded`.
5. A new session reads Core again. It sees the original Activity, Work, exact
   inputs/outputs, acceptance, resource and invocation history. Restore rotates
   the execution epoch and invalidates old authority; recovery interrupts active
   Attempts and leaves admitted/sent calls unknown. Work deletion removes its
   execution rows, receipts and content-derived fingerprints through the same
   maintenance path as its prior subject data. The host always places Pi JSONL
   sessions in `<space>/.zara-core/pi-sessions`, marked with the space id. The
   directory is adapter-owned; an alternate `--session-dir` is refused. During
   deletion maintenance the local Pi process must be stopped, then all managed
   histories for that space are retired before deletion jobs are completed.
   This deliberately broad retirement prevents a mixed session from retaining
   deleted Core content. Pending deletion blocks a new Pi launch and model
   execution. The host and maintenance use the same local lock, so an active Pi
   cannot recreate files while they are being purged.

Preselecting a proposed Work with an already linked output reads the saved
result without creating an empty Attempt. If the user explicitly accepts
while an Attempt is active, Core interrupts that Attempt atomically with the
exact acceptance receipt under `work.accept`; no separate `work.execute` grant
is needed. Any admitted or sent calls retain their unknown reserve. This
releases the exclusive resource without treating a new Pi session as a new
model run.

The supported transport profiles are `codex-sse` and a configurable local
OpenAI-completions HTTP/SSE profile for tests or explicitly chosen providers.
Model, provider, working directory, resource limit, reserve and Pi tool
allowlist are launch choices. The first trial's model and call count are not
product defaults or an allowlist. An unobserved transport is refused.

## Evidence and limits

The localhost synthetic run used upstream Pi 0.87.0 in RPC mode solely as a
test driver of the same extension. Its `/zara-work` UI chose Activity/Work; it
observed one final HTTP body whose SHA-256 matched Core's pre-send invocation,
then an answered invocation, Artifact and Work output link with Work still
`proposed`. The separate `/zara-accept` basis and confirmation changed Work to
`succeeded`. A deliberately insufficient reserve produced a prepared record
and zero provider HTTP requests. Focused tests cover stale input, current
separate rights, unknown reserve after a new session, explicit result
acceptance, and deletion. Pi's authorization readiness check
does not prove a token remains valid at the provider; a rejected real trial
request must be counted and retained as unknown.

This stage automatically publishes only a single nonempty text output from a
completed turn. Multi-slot and non-text Work require a later explicit output
path. Token usage is provider-reported; an answered call can exceed its prior
reserve, and that overrun remains charged and blocks later admission. An
`unknown` call retains its full reserve until a separately justified
reconciliation. The adapter does not inspect opaque provider transports,
persist Pi's own session JSONL as Core evidence, or claim recovery of a
standalone RPC executor. Adapter-created Pi histories in the reserved directory
are Core-managed copies and are purged after any Core Artifact, Activity or Work
deletion. Histories created before this correction with an arbitrary session
directory have no retained path inventory and require explicit operator review
and removal. Provider-side retention, user-exported transcripts, OS snapshots
and manually copied files remain outside this local maintenance boundary.

The correction was checked against three before-fix reproductions. Pi's normal
`set_model` to a second localhost provider had sent one unreserved request
containing Core input; after the guard it sent zero HTTP requests. A late
Attempt had replaced a separate Work@2 output; after the atomic operation it
gets `stale_work` and the Work@2 output remains. A synthetic Pi JSONL file
had retained input text after Work deletion; now maintenance removes it and
refuses to complete while Pi owns the space. A supported localhost provider
still made one observed call, saved an Artifact and linked output, and left
the Work proposed before the synthetic acceptance step. These checks used no
real model calls.

## Manual acceptance

From PowerShell, these commands create a new space, synthetic document and
proposed Work entirely inside ignored `_scratch`, then open the ordinary Pi
path with the previously installed Pi runtime. The shown provider/model and
limits are manual trial selections, not product defaults.

```powershell
Set-Location 'C:\my_global_workflow\core-v0-1\zaratustra'
$env:UV_CACHE_DIR = Join-Path (Get-Location) '_scratch\stage4-uv-cache'
$env:ZARATUSTRA_SQLITE_DLL = Join-Path (Get-Location) '_scratch\stage4-interactive-20260923-a\sqlite\sqlite3.dll'
$env:PYTHONPATH = Join-Path (Get-Location) 'tools\sqlite_bootstrap'
$trial = uv run --locked python -m tools.probe_stage4_manual --output ("_scratch\manual-stage4-" + (Get-Date -Format 'yyyyMMdd-HHmmss')) | ConvertFrom-Json
$piRuntime = Join-Path (Get-Location) '_scratch\stage4-pi-runtime'
$piCli = Join-Path $piRuntime 'node_modules\@earendil-works\pi-coding-agent\dist\bundle\cli.js'
uv run --locked python -m zaratustra.pi_adapter --space $trial.space --workspace $trial.workspace --pi-cli $piCli --pi-runtime $piRuntime --limit-units 20000 --reserve-units 8000 --provider-profile codex-sse --model gpt-5.6-luna --thinking low --activity-id $trial.activity_id --work-id $trial.work_id
```

Confirm the host's path and actor prompt. The command preselects the synthetic
Work; ask Pi to summarize its fictional note. For a launch without preselection,
choose Activity/Work through `/zara-work`. Run `/zara-status`: verify the exact
input, an answered invocation,
saved output Artifact, its Work link and `proposed` status. Quit and reopen Pi
against the same Core space; verify the same output and resource ledger. Review
the text, invoke `/zara-accept`, enter a basis and confirm the exact revision.
Run `/zara-status` again: `succeeded` and the acceptance receipt must appear,
while the Activity remains `ongoing`. The owner decides acceptance from that
review; engineering checks alone do not accept the Work or this stage.

END_OF_FILE

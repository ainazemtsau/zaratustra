# Process creation T2 readout

T2 adds the complete installed path from an ordinary saved need to one
exact-confirmed constructed Process and its first openable Work. The product
implementation is commit `13f542f042393462421066e9453fc34dfd5da7c3`, based on
T1 commit `31113d89bd447aa5f485b8735dbc610e7017365a`.

## Shipped path and retained distinctions

Version 0.14.0 adds `zara entry create draft|request|receive|propose|status|activate`.
The draft contains a title, need, desired outcomes, constraints, relevant declared
capabilities, and only necessary clarification questions/reasons/answers. It asks the
ordinary user for no Core id. A request cannot be fixed while a saved clarification
is unanswered; after it is fixed, the draft cannot be rewritten.

`request` saves one canonical non-overwriting transport file and prints the exact
provider-neutral `copyable_request` as plain stdout. It includes the saved need,
outcomes, constraints, clarifications and capabilities and explicitly instructs a
human to choose/run research elsewhere. It contacts no provider. `receive` accepts
only bounded UTF-8 text linked to those exact request bytes and retains the request
id/digest, returned bytes/digest, source label and creator. Its durable state is
`untrusted_research`, `approval: false`; changed request or return bytes refuse.

`propose` accepts a generic assistant-authored `ProcessDefinition`; the product has
no canned subject workflow or assistant-reasoning template. Every definition source
must point to the exact request digest, returned-text digest, or one exact declared
capability. Reasons must use both saved textual grounds. The T1 constructor validates
the graph, dependencies, data, recurrence and supported capabilities. Unsupported
capabilities refuse explicitly and remain visible in status. A different proposal
under the same creation refuses; T3 owns safe evolution.

`activate` reserves only a previously uninitialized selected workspace, pins its new
Core workspace identity, creates Core-owned draft ids, and retains six exact requests:
`authorize_work`, `set_work_requirements`, `bind_pack`, `authorize_artifact`,
`publish_artifact`, `accept_handoff`. One readable UTF-8 preview contains the full
proposal, exact evaluated first Work/reasons, exact request/research text and trust
labels, derived immutable Pack reference, canonical empty snapshot and pending
requests. The trusted console confirms the SHA-256 of those complete bytes once.
Only then are request-bound Core authorizations derived and the missing suffix run.

The empty canonical definition snapshot is accepted solely as the first Work's
starting basis so the existing common-entry context can open; it is not a node Result
and does not complete Work. The T1 requirements pin its exact digest, definition,
node and occurrence, retaining the repaired prior-snapshot invariant. After revision
7, the existing designation-based `entry open` performs its own current exact
`ContextQuery` confirmation and returns the accepted basis. Status keeps `draft`,
`research_waiting`, `research_returned`, `proposal_pending`, `activation_pending` and
`activated` distinct, rechecks Core records/history/content, and reports current Work
status/authority rather than treating its journal as permission.

## Recovery and adversarial behavior

The catalog-adjacent journal is atomic and locked, but non-authoritative. Once Core
bootstrap begins, recovery validates the pinned workspace id, exact record graph,
contiguous request/event/receipt prefix, immutable binding, registered snapshot bytes
and accepted Handoff. It reuses pending identities and runs only the missing suffix.
An exact completed replay returns the same six receipts; changed target, aliases,
source, response, definition, operation intent or Core prefix refuses. A catalog add
failure remains recoverable after Core activation.

HOME's first pre-pass exposed strict decoded-JSON tuple rejection. The fixed boundary
combines bounded UTF-8/duplicate-key checks with Pydantic's strict JSON validator; an
actual `CreationDraft.model_dump_json().encode()` round-trip passes. HOME also found
that a wrong initialized schema-2 target could be migrated before later refusal. The
failure was independently reproduced: the regression observed schema 7 after a
`workspace_collision`. With the ownership preflight restored, the same regression
passes and both public `WorkspaceInfo` and full records remain unchanged at schema 2.

HOME's second pre-pass found that the initial confirmation displayed only digests.
The exact preview now embeds the full definition, first Work/reasons and both source
texts. A Cyrillic regression proves the displayed bytes contain real UTF-8, not
escaped `\\u` reconstruction. Both notes and their dispositions are retained in
`docs/process-t2/STEER.md`, `docs/process-t2/STEER-2.md` and the PLAN.

## Reproducible evidence

The focused T2 suite exited 0 with 13 tests covering two full paths, CLI presentation,
strict model JSON, source/request/return identity, capability refusal, no confirmation,
stale preview, partial restart, exact replay, terminal current rights, wrong-target
non-mutation and readable UTF-8 preview.

The final full native command `uv run --locked python -m tools.check` exited 0. It
formatted 114 files, passed Ruff, passed strict mypy over 99 source files, kept all 16
import contracts, passed all 343 tests in 116.94 seconds, and built the 0.14.0 wheel
and sdist. The full log is retained at
`_scratch/process-t2-gates-executor-03/full-check.log`.

The separate report-aware `uv run --locked python -m tools.check --deliver` also
exited 0 after the final RESULT/READOUT existed: the same 114/99/16/343 surface,
343 tests in 126.22 seconds, both artifacts, and `report structure` passed. Its full
log is `_scratch/process-t2-gates-executor-04/deliver.log`.

The wheel-only command below exited 0 on exact implementation commit `13f542f...`.
It installed wheel SHA-256
`060d033e1484dc0a7ccf68b53e68ed10d733d4819f4a00d6cd2cf6c0296e7441`
under a retained isolated venv, proved tests/tools absent before explicit fixture
exposure, and proved every loaded `zaratustra.*` module came from that venv. Both
external development fixtures reached `activated`, current
`work_metadata_and_artifact`, and `first_work_openable: true`; small retained lawful
recurrence and project retained missing predecessors `read-request,read-research`.
Its return remained `approval: false` and `provider_contacted: false`.

```text
uv run --locked python -m tools.probe_process_t2 --case small --output _scratch/process-t2-small-<new>
uv run --locked python -m tools.probe_process_t2 --case project --output _scratch/process-t2-project-<new>
uv run --locked python -m tools.probe_process_t2_install --output _scratch/process-t2-installed-<new>
```

Exact installed evidence is retained in
`_scratch/process-t2-installed-executor-01/verification.json`,
`small/summary.json`, `project/summary.json`, both activation previews and both opened
first-Work contexts. All needs, research and definitions in those trials are explicit
technical fixtures under `tests/fixtures/process_creation`; they are not packaged
examples, real data or evidence that an actual human performed research.

## Honest limits and next work

T2 creates one immutable edition and first Work. It does not safely revise an active
definition, rebind a Process, migrate Pack state, or replace earlier canonical
snapshots; full reviewed evolution remains T3. Full physical installed readers and
their later lifecycle proof remain T4. The catalog continues to designate the first
Work; advancing designation policy is not silently invented here. No provider,
browser, account, paid service, arbitrary loader/interpreter, universal database,
GUI, CI/integration, personal workspace or Direction state was used. A future actual
human research handoff must be run and labelled separately. Technical executor proof
does not constitute fresh HOME G5, owner acceptance or task close.

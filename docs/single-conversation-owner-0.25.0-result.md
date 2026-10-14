# One conversational owner — 0.25.0 implementation evidence

## Scope and architecture

Owner-authorized implementation of
[the audited plan](single-conversation-owner-plan.md), based on public main
`130fbea98d420b6301a5ec4e16ca152eef8d736f`, on
`codex/single-conversation-owner`. Core stays schema **18**. Native Pi owns
conversation turns, history and presentation. Existing Core/DBOS/WorkPlan
remain authoritative for execution, rights, original materials and accounting.

The main agent's lifecycle tool now observes an exact process until a saved
result, addressed question or obstacle can be returned to that same agent.
Observers publish progress only. The competing completion poller and its
conversation wake creation were removed. Tools admit effects sequentially;
native abort requests an exact executor pause without joining its live RPC.
Opening or switching a session performs passive discovery and awaits the owner.

Known empty native finals use bounded continuation of the same native run.
Exact terminal originals and invocation proof are checked read-only in Core.
Native branch metadata retains two repair reservations; native context edits
omit only empty model projection, preserving originals. This adds no Core
delivery ledger or schema. Repair exposes no model tools: it only formulates an
explanation from its already supplied context. Backend admission separately
forbids domain effects, answers, acceptance, retained memory/data selections
and Git delivery reconciliation.
An unknown send, error, abort, changed generation or queued owner input does
not become an empty-response retry.

Exports, Git projections, real personal spaces, Activity deletion and installed
private runtime updates are outside this implementation. Work acceptance
remains an owner action.

## Reproductions and checks

All scenarios below use fictional local spaces, raw localhost provider replies
and ordinary Pi **1.0.4**, through its supported SDK and RPC interfaces.
These are execution and protocol checks, not claims about real model judgement.

| Scenario | Observed evidence |
| --- | --- |
| Old competing publication path | Controlled actual observer barrier: 4 HTTP requests, 3 ordinary and 1 host; saved completion wake and second visible explanation |
| Corrected ordinary publication | 3 ordinary HTTP requests, 0 host requests or completion wakes; retained output remains unaccepted |
| Empty and whitespace native finals | 3 HTTP requests, 2 durable native repair reservations/context edits, 0 new Core delivery claims |
| Repair exhaustion | 3 HTTP requests, 2 repairs; no fourth send |
| Ordinary Work publication followed by repair | 5 HTTP requests; exact retained terminal proof, closed Attempts and unaccepted output; no host wake |
| Full setup conversation | 11 HTTP requests plus 1 reopen request; exact answered accounting, 0 host requests, first Work unaccepted |
| Legacy schema 14 setup | 19 HTTP requests across setup, two full reviews, compact, first Work and maintenance; original schema 13 copy preserved |
| Native input origins | 3 HTTP requests; identical owner text retains distinct native identities, extension input rejected |
| Fresh obsolete wake | Initial HTTP request only; 0 requests after branch switch and attempted fresh wake |
| Passive UI and compaction | Native SDK loader/hooks; restored questions are status only, reopening does not resume execution, legacy wake history excluded from model and compact inputs |

Read-only independent review found omitted response-repair capabilities:
memory `read_batch`/`prepare_cache` and data `query_entries` retain derived views,
and workspace `check` reconciles delivery state. Direct and integration entry
points now refuse these effects during repair. Behavior checks verify no view
creation and restore valid admission only after genuine owner ingress. Native
repair requests must contain an empty tool list, removing this entire model
capability surface from the repair stage.

## Native gate and remaining verification

One full `uv run --locked python -m tools.check --deliver` passed: **1177 tests**
in 974.10 seconds, formatting, hygiene, types, 32 import contracts and build.
That run began before the final repair capability restrictions. A later
48-test conversation/boundary run passed after the first memory restriction.
Final affected file check passed: **51 tests** in 64.55 seconds, types, hygiene,
32 import contracts and rebuild. Its first attempt exposed an incomplete test
request (`query_entries` lacked `operation_key`); the request was corrected,
not the product contract. The earlier 50 passing cases were not represented as
a complete PASS.

The wheel was installed into an isolated non-editable environment outside the
checkout. All **122 package members** were checked byte-for-byte against it.
The first installed candidate passed publication, ordinary Work repair,
exhaustion, complete Activity/first Work and new owner request after reopening.
After the final tool-free repair restriction, affected installed Work repair
and exhaustion passed again (5 and 3 HTTP requests respectively, 0 host requests,
no tools in repair requests and no automatic acceptance).

SHA-256 of the final local candidate wheel:
`0980f22040590d292962740d781c7d16964cd0e164f528712445adfa730b3abc`.

One bounded read-only evaluator smoke verified isolated imports, all 122 packaged
members, public terminal APIs, unchanged schema 18/storage and ordinary Pi 1.0.4.
It made no model calls or domain-space mutations and did not waive the blocker.

One strengthened interruption probe encountered `SQLITE_BUSY` in SQLite
identity inspection before the assigned request was sent. The exact local
trace is retained; its cause is under investigation. It is not counted as a
successful interruption check. An earlier interruption run did preserve an
exact pause and an unknown assigned invocation without activation or acceptance.

One later native diagnostic did not reproduce SQLite contention. It did retain
an exact pause before releasing the held reply. The late reply was truthfully
accounted as answered, with its complete original retained; the Attempt stayed
interrupted, assignment stopped and outputs/acceptance absent. The old fixture's
unknown-only assertion was too narrow for this legal race. This is not a claim
that the original SQLite failure was fixed.

## Structural stop: completed assigned answer without output

Continuation audit confirmed a material gap. Status permits resume from an
answered invocation with a retained Source but no output Artifact. The allowed
coordinator path would assign a fresh Attempt for the same stage. The Source
lacks exact native terminal/manifest proof, so it cannot be automatically copied
into a valid output or attributed to a successful stopped Attempt. A second
provider request was not started by the audit.

The owner required stopping for structural changes. Publication and private
installation are held. The general proposed recovery contract and regressions
are recorded in
[the completed-response audit](completed-response-recovery-audit.md).
The one-owner code is a local development candidate, not a finished release.

## Evidence limits and owner acceptance

No real-model or paid API calls were made by this implementation. Previous
real-model allowances are exhausted and do not authorize new calls. Local
fixture replies deliberately include invalid and empty raw strings; successful
fixtures do not prove every future model response or semantic design choice.

The tests and release evidence are separate from owner acceptance. Acceptance
of this release and personal installation remain pending.

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

## Pre-recovery checkpoint checks

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

SHA-256 of the pre-recovery checkpoint wheel:
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

## Original structural stop: completed assigned answer without output

Continuation audit confirmed a material gap. Status permits resume from an
answered invocation with a retained Source but no output Artifact. The allowed
coordinator path would assign a fresh Attempt for the same stage. The Source
lacks exact native terminal/manifest proof, so it cannot be automatically copied
into a valid output or attributed to a successful stopped Attempt. A second
provider request was not started by the audit.

The owner required stopping for structural changes. The general recovery contract and regressions
are recorded in
[the completed-response audit](completed-response-recovery-audit.md).
The owner subsequently explicitly authorized this contract.

## Completed-response implementation and current verification

Schema 18 is unchanged. The exact raw assigned original is retained before
finish accounting; the persisted native entry/protocol is retained before output
interpretation. One public Core recovery operation supplies honest proposed
output provenance without claiming success of the stopped Attempt. Existing
setup/workflow/procedure validators remain responsible for admissibility.

Read-only review found two cross-generation fences that needed strengthening:
linked outputs could mask a newer unresolved send, and a later no-send Attempt
could mask an older unknown invocation. Both are covered by actual public-Core
regressions and fixed before release. The final bounded recheck found no further
material blocker in that recovery scope.

The full recovery package gate ran once: **1212 passed, 2 failed** in 1015.39
seconds. Formatting, hygiene, types (280 files), 32 import contracts and report
structure passed; that run as a whole did not pass. Its two failures were:

- The assignment fence rejected a legitimate continuation after the first slot
  of a multi-slot parent Work. The correction checks exact publication/recovery
  events, receipts, managed Artifact identity and current slot; a real partial
  publication admits the remaining slots.
- A restored unknown-send test expected stopping its live process to resolve the
  send. The test now verifies the actual stop, unchanged reserve/accounting and
  refusal of a new assignment while that send remains unknown. The historical
  rights, receipt and late-response assertions are retained.

The affected native gate then passed **126 tests** in 145.01 seconds, formatting,
hygiene, types, 32 import contracts and rebuild. Its first attempt stopped on
import sorting only; formatting was corrected. A final narrow assignment review
added the plain-link/no-send fence and exact slot check. **41 affected tests**
passed in 45.87 seconds after that correction; final native file gate/build is
reported below. The full suite is not rerun as a substitute for
those affected checks, per the owner delivery policy.

Addressed foundation/boundary checks: 29 passed. Adapter response recovery checks
covered setup, workflow and typed procedure, including raw malformed/blank
results, missing proof, unavailable model selection, real entry/snapshot
validation, active/absent executor, unknown outcomes and read-only status. Initial
test preparations that violated existing typed-output, Source immutability and
resource-state contracts were corrected; the product contracts were not relaxed.

The isolated recovery candidate wheel has 124 packaged members, byte-identical to installed
files and current source. One new bounded read-only evaluator smoke verified the
public recovery exports, absent optional protocol canonical bytes, unchanged
storage/schema 18 and ordinary Pi 1.0.4. It made no domain or provider writes.
The final read-only delta check confirmed those 124 files after the narrow
assignment correction (candidate SHA-256
`42366a270c1929a931f038b26e9daec9daf81cbff8203a34b678e05e3b0cc525`).

Installed interruption/reopen: 4 HTTP (3 ordinary including the new owner
request, 1 assigned). The committed pause, retained raw original and truthful
unknown accounting survived; no replacement draft, activation or acceptance.
The first attempt of that probe incorrectly treated native abort ACK as a Core
pause receipt. The corrected observer waits for actual saved public state; no
runtime patch, model text matching, test hook or timing workaround was added.

The assigned child has no supported observer between terminal capture and
publication. Its exact completed-response recovery is tested at public Core and
coordinator boundaries; the native interruption probe records the actual race
outcome without claiming it deterministically exercises that positive branch.

The first installed complete-setup check stopped after two ordinary requests
with SQLITE_BUSY during application_id validation in message_end. Dependent
provider sends stopped. The holder/cause is not established. An independent
review's initial native message_end/turn_end overlap hypothesis was disproved by
the installed SDK's awaited listener chain and retracted; no speculative queue
or mutex was introduced. This failed run is not counted as complete setup proof.

The repeat's shell process was interrupted before the harness emitted a PASS
report. Public inspection of its saved fictional Core confirmed both questions
and original answers, the answered first draft and exact published empty output;
the Attempt was interrupted and assignment stopped, with no automatic
acceptance. This incomplete run is not reported as a completed check.

Continuation from that same saved space then **passed through ordinary installed
Pi**: 7 new HTTP requests, **0 repeats of the original draft**, two corrections
after the retained blank response, two complete reviews and six exact native
terminal proofs. The same Activity became ready. Original questions, answers,
Attempt and invocation accounting were preserved. Every new preparation/review
packet included the exact saved inputs. No model or runtime patch was used.

The first ordinary procedure Work passed with **4 HTTP requests**: a real typed
entry and its exact output snapshot were retained, and its result remained
unaccepted. A later harness discovery call used a nonexistent API; the Work had
already succeeded. Correct public read APIs verified its saved result and
idempotent repeated start without a state change or another Work/send. Continuing
the existing fictional Development then passed with **1 HTTP request**; its exact
old Work input, revisions and original Artifact stayed unchanged.

These runs use the same installed recovery candidate bytes above. The separate
initial SQLITE_BUSY observation remains unresolved; successful continuation is
not evidence of its cause or correction. No new real-model calls were used.

The final affected native file gate passed **55 tests** in 86.44 seconds,
formatting, hygiene, types, all 32 import contracts, report structure and
sdist/wheel build. The final dist wheel was reinstalled into the same isolated
non-editable environment. The bounded read-only packaging delta verified all
124 product members against installed files and current source, and every archive
member against the native-run candidate: **zero differences**, including metadata.
The public APIs, `partial_output`, old canonical optional fields and unchanged
schema 18 were rechecked without domain/provider effects.

Final dist wheel SHA-256:
`42366a270c1929a931f038b26e9daec9daf81cbff8203a34b678e05e3b0cc525`.

Authorized public publication is pending readback. Personal installation is a
separate action and has not been performed.

## Evidence limits and owner acceptance

No real-model or paid API calls were made by this implementation. Previous
real-model allowances are exhausted and do not authorize new calls. Local
fixture replies deliberately include invalid and empty raw strings; successful
fixtures do not prove every future model response or semantic design choice.

Automatic copied-output recovery admits a simple Work with one supported text
or typed JSON output. Method/composite outputs still require their real producer
and ordinary validation proof; an unsupported contract is an addressed obstacle,
not an inferred successful Attempt. Existing genuine multi-slot publication is
separately supported and regression-tested. Legacy originals with absent exact
terminal/protocol proof remain readable but do not authorize an automatic resend.

A bounded read-only assessment compared the initial SQLITE_BUSY trace with the
pre-recovery checkpoint: the same `application_id` failure was already present,
and the storage/runtime identity path is unchanged. This does not establish its
holder or environmental cause. Current successful paths show no permanent
continuation blockade; rare storage contention remains an open observation.

The tests and release evidence are separate from owner acceptance. Acceptance
of this release and personal installation remain pending.

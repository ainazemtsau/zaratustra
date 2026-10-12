# Workflow 0.23.0 — implementation and release evidence

## Delivered scope

Core explicitly upgrades schema 15 to 16. Versioned WorkflowDefinition records
instantiate ordinary composite Work and WorkPlan. Work, Attempt, readiness and
receipts remain execution authority. Host waits retain exact questions and owner
Sources without creating a fictitious Pi session. Internal validation permits
internal transitions without accepting Work or satisfying owner obligations.
Root publication has its own Attempt, current plan pin and output proof.

The ordinary Activity entry uses this workflow for preparation, whole-proposal
review, correction and activation. Deferred procedure questions are reviewed
before they can block setup. Original answers, exact Source fragments and
question–answer pairs enter the next packet. Invalid raw responses are retained
before parsing; bounded repairs and the five-review limit survive reopening.

The Pi coordinator uses ordinary assigned Pi/DBOS, at most two compatible model
nodes, pinned provider/profile/model/reasoning, and addressed interactions.
Selected project tools use its resource root. Preparation and review receive
only allowed Core reads. Explicit model choices persist locally; an unavailable
choice is reported instead of silently substituted.

Workflow changes use Candidate, validation results, Decision and application.
Explicit migration checks completed effects, inputs, waits and unknown sends.
Sleep keeps its existing cursor, cutoff, analyses, remainder and spend; its Work
uses the same execution authority. Maintenance covers new references and exact
definition versions. Old JSON, checksums, protocols, pins and acceptances remain.

## Native checks

The one complete native gate passed on the coherent initial package:

- 881 tests; build, hygiene, Ruff, mypy and report structure passed.
- 32 import contracts passed.
- This gate preceded the corrections listed below. Its test count is not a
  claim that every later byte received another full-suite run.

Only affected checks were repeated after demonstrated defects:

- Exact Method-version deletion and nested workflow dependencies: 24 relevant
  workflow/Sleep checks, with two separate deletion regressions.
- Bounded retries of SQLite identity reads: 39 storage/operation checks.
- Assigned Pi parent polling during concurrent Core writes: six checks,
  including recovery and exhausted retries without reissuing a send.
- Actual review-component catalog and Source receipt time: 49 setup,
  structures and recovery checks. A retained real review was revalidated
  against its original manifest without changing the old run or its unknown
  second review.
- The real-trial observation harness: four regressions check that a live
  coordinator is not polled through unused Core reads, transient boundary
  reads recover, and persistent lock/rights errors remain bounded.
- The final Pi failure and executor paths: 20 affected checks passed. They
  cover typed preflight refusal, exact Attempt diagnostic pins, preservation of
  an already published result, unknown sends and held reserve, and two executor
  slots shared by a Pi window. A retained native wait keeps its slot; confirmed
  process exit releases the exact lease once. Closing one coordinator stops
  only its owned processes.
- Changed Python files passed Ruff, mypy and formatting; whitespace checks passed.

## Installed ordinary Pi

Verification imports the wheel from a separate virtual environment, outside the
checkout. Fixtures and development probes are supplied separately. The native
Pi version is 1.0.4; SQLite uses the pinned runtime DLL. All automatic scenarios
use fictional spaces and local synthetic providers, with zero paid API calls.

| Scenario | Actual provider sends | Observed result |
|---|---:|---|
| Activity creation after the review-catalog correction | 42 | Schema 15 → 16; two addressed questions; clarification leaves the wait open; close/reopen and answer; malformed JSON and invalid operation repairs; full review, corrections of several parts, new full review; activation; two compactions; first typed Work result remains unaccepted; legacy Development history remains |
| General workflow and native Method | 25 | Independent branches overlap; choice and join use native WorkPlan; two host waits remain separately addressable; Method wait closes and resumes with its exact packet; root has actual producer proof; registered project tools use the selected folder |
| Explicit model and reasoning changes | 8 | Actual requests change model and reasoning; previous node pins stay unchanged; the next opening retains the explicit selection |

Every listed HTTP count equals the corresponding Core delivery count. Request
bytes and hashes are compared with ContextManifest and saved delivery records.
The Activity scenario was repeated after the review-catalog correction. These
three reports precede the final Pi refusal and executor-lease corrections;
their counts do not claim execution of those later bytes. Final installed
rechecks of the affected paths are recorded below.
Synthetic responses check contracts and execution, not unrestricted model
understanding of every possible user description.

The final wheel was then installed again and its affected native paths checked:

| Final-wheel recheck | Actual provider sends | Observed result |
|---|---:|---|
| General workflow, native Method and registered project | 25 | 11 general, 10 Method and four project requests equal their Core delivery counts; overlap, addressed waits, exact native continuation, own root proof and separate acceptance passed |
| Refusal before provider send | 0 | Native Pi and DBOS retain `trial_send_limit`, a short stopped status and an exact diagnostic Source; zero Invocation, output, extra Work or Artifact, and no acceptance |

The first attempt at this final general recheck stopped on SQLITE_BUSY while
reading status, followed by the harness's read poll. The saved attempt is not a
pass. Later public reads confirmed that resume had succeeded, one node's raw
answer was published, and the window closed before its validation and next
transition. That result remains available; there are no unknown sends in this
failed attempt. A second fictional space completed the same installed check without code
or harness changes. This remains an intermittent read-contention observation;
its lock holder and historical cause were not established. Successful rechecks
do not prove that every future concurrent read will avoid it. Listed successful
scenario counts do not include every failed investigative synthetic attempt.

## Failures found and resolved during verification

Concurrent assigned execution exposed SQLITE_BUSY in schema identity reads and
parent polling. The fix retries bounded read-only observations, never an
operation body, commit or model send. The original lock holder was not identified;
the evidence does not establish its historical cause.

During the real trial, an unused harness status poll also encountered a lock
and closed coordination. The completed draft remained; the review had only a
prepared context and no model Invocation. The harness now reads the boundary
after coordination stops. Continuation uses the same setup and retained draft;
a prepared context is counted separately from an actual provider send.

One synthetic probe's short turn deadline interrupted activation after a complete
review was already published. Reopening consumed that retained result, preserving
identity and counters, without another assigned send. The harness deadline was
corrected and the complete installed scenario passed.

The real model addressed valid proposal components that the validator did not
accept. A shared exact catalog now supplies the review schema, packet and
validator diagnostics. No prose-to-operation parser or domain keyword gate was
introduced. Source packets now expose immutable receipt time separately from
event time; historical measurements are not rewritten.

An assigned preflight refusal was being reduced to a missing-result error. The
bridge now retains the exact stable cause and Attempt-scoped diagnostic Source.
The parent reports that cause briefly, without a stack trace in the user status,
new model send, fabricated output, or Work acceptance. Only an explicit native
preflight marker can produce this refusal; ordinary read errors cannot.

A native Method wait left its Pi process alive while releasing an executor
slot. A shared per-window lease now lasts until process exit, including resumed
waits. A further check found a close-return race; synchronous release after
confirmed exit and the asynchronous exit watcher share an exact token, preventing
double release and release of a newer lease.

The first three attempts at the affected failure gate did not complete: two
fixture revision pins were corrected, then sandbox loopback denial and a broad
subprocess mock prevented meaningful execution. The test uses the direct RPC
boundary and permitted loopback access. The corrected focused gate passed six
checks; the final combined affected gate passed twenty. No sandbox failure was
reported as a product behavior check.

## Real subscription trial

The authorized limit is forty actual sends in total, using Sol 6.1, high and the
existing codex-sse subscription profile, with no paid API fallback. Evidence
contains fictional inputs and request bodies, not authorization headers or
credential files.

The first attempt recorded twelve sends and 126614 known usage units. Interview,
clarification, reopening and exact answer transfer worked. Preparation completed.
The review-catalog defect rejected the first report. The harness's whole-cycle
deadline then interrupted the second review after approximately three seconds.
That send remains unknown with unknown usage; no completed reply was found and
it has not been repeated. The remaining test allowance is twenty-eight sends.

The corrected package then retained and continued a second fictional space.
Its draft survived an observation failure. The review was stopped before any
model Invocation or provider HTTP; reopening used the same setup and draft.

| Real input case | Observed result |
|---|---|
| Short goal | Activity activated after one full review; exact question–answer pair and original input survived reopening |
| Detailed description | Activity activated after review, whole-proposal correction and a second full review |
| Forwarded prior answers | Full original retained in the correct setup packet; stopped before draft HTTP when the trial admission cap was exhausted |

Detailed correction changed ten parts of the proposal. The second review's
actual HTTP packet contained the new draft, new manifest, whole original request
and exact catalog of 45 components. The old draft remained a historical reference,
not the active proposal. Remaining personal-program questions did not block the
usable foundation. Both activated cases expose a first ordinary Work using known
data without a fresh general questionnaire. Execution of that first real Work
was not part of this bounded model trial; the installed synthetic scenario covers it.

Final real accounting across all attempts: **39 actual provider sends**, **581918
known usage units**, and **two unknown sends with additional unknown usage**.
One dormant prepared context reserved a trial slot without a send. The final
space contains 27 actual HTTP/delivery pairs plus that separate prepared context.
All 27 request-body and decoded-body hashes were independently checked against
ContextManifest. Every actual request used Sol 6.1/high/codex-sse. No unknown
request was repeated or declared completed.

One unknown was the first harness interruption; the other was an external
provider error during explanation of the user's confusion. Waiting state survived,
but that explanation did not complete. Main replies did not falsely declare
activation or an ordinary diary write. Detailed and forwarded inputs were not
asked to repeat the general questionnaire.

**The overall real trial is incomplete.** Forwarded did not reach review or
activation; the admission guard stopped at 39 actual sends because its count
also reserves prepared contexts. The fixed limit was not reset. These observations
are evidence for the reached paths, not a guarantee for all future conversations.

## Read-only evaluator

One bounded setup evaluator inspected the installed wheel metadata, layout,
source correspondence and retained automatic reports. Its affected rechecks
confirmed the earlier setup/workflow bytes and then the final wheel hash,
metadata 0.23.0 and byte equality of bridge, assigned execution, workflow
coordination and the Pi extension across source, wheel and installed package.
The final read-only inspection found no new blocker in the preflight and lease
changes and checked the final 25-send and zero-send reports.
The final Activity report records 42 local HTTP requests and 42 accounted sends;
these scenario reports have no own wheel-hash stamp, so runtime provenance also
relies on the isolated installed launch and the file comparison. This is a read-only smoke;
it is not a second broad execution review or owner acceptance.

## Artifact and boundaries

Wheel: `zaratustra-0.23.0-py3-none-any.whl`.

SHA-256: `fa76c995c2a17b4cc4c50ee87bf0f797fbe5923dd5474aee79b1d679745a1857`.

Exporters, Git representations, personal Activity changes and installation in a
personal space are outside this package. No personal Activity was deleted or
recreated. Existing parallel checkout materials were preserved. No new queue,
background service or separate SleepRun was introduced. A Method-backed node in
this first version produces one text report and retains its native obligations
and separate child acceptance.

Owner acceptance of the release and later Work results remains separate.

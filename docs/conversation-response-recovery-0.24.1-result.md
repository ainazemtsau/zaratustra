# Native response recovery — 0.24.1, schema 18

## Outcome and scope

The owner-authorized schema 17 → 18 correction is implemented and checked.
The final wheel passed the affected native gate, explicit upgrade tests and
eight ordinary installed Pi scenarios outside checkout. The selected personal
installation, verified backup, restore rehearsal and explicit upgrade are complete.
Public code was published to the authorized `ainazemtsau/zaratustra/main`, and
authenticated GitHub readback confirmed the source commit. These engineering
checks are separate from owner acceptance.

The package corrects completed native assistant responses with no visible text
and preserves delivery-to-Work/Attempt/session correlation through deletion.
Activity readiness, Work execution, response delivery and owner acceptance
remain separate Core facts. Existing Activity and Development history are
preserved. Exporters and Git representations are outside this package.

## Confirmed failure and correction

The previous native trial established an answered invocation and a persisted
completed-stop assistant entry with empty visible text. The extension discarded
that observation, classified the delivery as unknown and left a promise in the
ready widget. The previous localhost fixture supplied final text on every path
and did not exercise the native Codex Responses empty-output boundary.

Typed Source observations now retain the exact visible UTF-8 bytes, including
empty and whitespace-only text, before classification. Thinking is not a visible
answer. Delivery outcomes and the two-correction bound derive from existing
operation events and receipts. A completed, answered empty response can authorize
a checked repair; an unknown send, storage failure, missing rights, changed bases
or incomplete capture cannot authorize a blind model repeat. Each repair retains
the original observation and diagnostics with a freshly checked manifest.

Ordinary Pi uses its supported boundary and custom-message APIs. The checked host
task reaches the actual native instructions. Host notifications remain distinct
from owner input and cannot answer a saved user question or accept Work. Startup
and conversation status read saved Core state; restoration does not invent a new
user answer. Whitespace cannot acknowledge delivery or complete an Attempt.

### Durable correlation and explicit upgrade

The final audit reproduced a structural gap: deleting the Context payload could
erase the evidence used by no-send cleanup while delivery accounting survived.
The owner authorized schema 18 and its migration checks on 2026-10-13.

Schema 18 stores immutable exact Work, Attempt and session correlation beside
each delivery. Registration checks both orderings: a delivery created before an
execution invocation and an execution invocation created before a delivery must
agree for the same invocation UUID. A mismatch is rejected atomically.

Migration reads legacy evidence sequentially. A surviving Context or the exact
same-invocation execution tuple supplies correlation. Legacy Context
`attempt_id = NULL` is an optional omitted field, not an assertion that no Attempt
exists: migration checks every positively supplied identity field against the
execution tuple before using that tuple. Historical JSON, hashes, revisions and
receipts are not rewritten. New schema 18 registration remains strict.

When neither original nor execution evidence survives, migration records
unresolved legacy correlation. An affected old Attempt cannot claim no send;
explicit interruption, new Attempts and unrelated work remain available. Deleting
content does not erase the saved correlation or authorize a resend. Backup,
restore and dependent-material maintenance include the new relationships.

### Additional audited boundaries

- Replayed observations under another operation ID retain deletion-tracked
  replay events without another correction or changed logical ordering.
- A visible terminal answer cannot have its invocation correlation replaced
  before acknowledgement.
- Pending provider accounting preserves the raw observation and refuses
  classification; later processing uses the saved original without a model resend.
- An unknown terminal clears obsolete host explanation work. A fresh owner turn
  clears capture failure only after that actual turn is retained and bound.
- Ordinary cleanup and recovery require exact saved final proof. Observed sends
  without proof preserve the Attempt and results with a concrete obstacle.

The plan and contracts are in
[conversation-response-recovery-plan.md](conversation-response-recovery-plan.md).
No runtime patch, second execution graph or automatic Work acceptance was added.

## Checks and exact attribution

The full gate is evidence for the bytes it checked. Later changes have affected
native gates and installed-wheel evidence; they are not attributed retroactively
to that earlier full run.

| Check | Result | Artifact and boundary |
|---|---|---|
| Schema 18 full native gate | 1111 tests in 1101.18 seconds; build, hygiene, Ruff, Mypy for 271 files, 32 import contracts and report structure passed | Wheel `dacc5a8a…`; before symmetric registration and legacy optional-Attempt corrections |
| Affected native gate after symmetric registration | 105 tests in 124.33 seconds; all required native checks passed | Wheel `43992ac1…`; before legacy optional-Attempt compatibility correction |
| Final affected native gate | 82 tests in 109.04 seconds; all required native checks and build passed | Final wheel `8baa304e…` |
| Final installed upgrade tests | 11 passed in 17.41 seconds | Final wheel outside checkout |
| Final installed product comparison | All 121 product files match wheel bytes | Final isolated installation |
| Final ordinary Pi scenarios | Eight scenarios passed; 49 actual localhost HTTP requests including reopening | Final wheel, ordinary Pi 1.0.4 |

The final upgrade coverage includes preserved original Context revisions, hashes,
receipts, pins, outputs, acceptance and invocation accounting; prepared and sent
legacy records with optional Attempt identity; positive identity conflicts;
deletion and restore. Focused checks also covered explicit upgrade refusal and
the deletion/no-send boundary. These synthetic spaces contain no personal data.

### Ordinary installed Pi

| Scenario | Initial + reopening HTTP | Observed result |
|---|---:|---|
| Creation, full review, first Work | 13 + 1 | First result saved; no owner acceptance |
| Empty and Unicode whitespace, then visible explanation | 5 + 1 | Exactly two repairs; visible delivery |
| Two repairs still empty | 5 + 1 | Persistent attention bound; no fourth automatic send |
| Tool call before terminal reply | 6 + 1 | Intermediate tool call did not acknowledge final response |
| Capture/storage failure and fresh owner input | 4 + 1 | Zero repairs; recovery in the same session and after reopening |
| Native provider failure and a new owner topic | 4 + 1 | Unknown outcome retained; obsolete host task not reused |
| Ordinary Work saves output, then ends empty | 2 + 1 | Output and active Attempt preserved; no acceptance |
| EOF after exact final proof | 2 + 1 | Previous Attempt completed from proof; no blind repeat |

The probes used the native Codex Responses SSE path, compressed request decoding,
raw response strings and fictional credentials. Product imports came from the
installed wheel; development helpers came from the repository. The final upgrade
tests ran in a separate child process from native Pi probes. No installed product
or runtime bytes were changed to obtain a pass.

### Independent bounded checks

Independent review found the deletion/correlation and reverse-registration gaps;
both are corrected. Its final bounded rechecks found no material finding in the
changed correlation and legacy-compatibility boundaries.

One bounded read-only evaluator smoke and its final artifact follow-up inspected
20 native HTTP bodies, persisted entries and Core snapshots. It confirmed schema
18, exact execution correlation, separate owner/host origins, the host task in
native instructions, persistent repair receipts and an unaccepted first Work
result. It found no material finding in that scope. It did not rerun the full
gate, mutate state or make model calls. This is neither owner acceptance nor a
fresh Direction G5.

A further bounded read-only compatibility check confirmed that an unknown legacy
conversation delivery permits a fresh owner request, reading current facts and
selecting an existing first Work. It blocks only a blind claim about the same
action digest. This check did not run a real personal Activity conversation.

### Earlier checks and failed trials

Earlier schema 17 candidate checks passed 1077 full-gate tests in 1003.27 seconds,
then 73 affected tests in 69.55 seconds. They also passed eight native fixture
scenarios with 49 HTTP requests. Those runs preceded the schema 18 structural
fix and do not establish its invariant.

The first schema 18 installed trial, using wheel `dacc5a8a…`, passed 11 upgrade
tests but failed in creation: the review RPC ended with EOF after preparing its
Context and before execution invocation registration or a provider send. The
Context and Attempt session identities matched. The exact process cause remains
unestablished. A diagnostic repeat with unchanged product and fixture passed
creation with 13 + 1 HTTP requests; the final wheel then passed all eight scenarios.
Separating upgrade pytest from the native driver is test isolation, not a claimed
fix for that EOF cause. The failing traces are retained.

Early fixtures also had an incorrect Responses envelope assumption, a fresh-versus-
previous Attempt assertion and a relative-path launch that did not execute. Some
new migration fixtures lacked required invocation fields or compared against a
baseline taken before resource registration. Those initial runs are not passes;
their fixture corrections did not relax the product invariants. Disposed localhost
connections printed socket-reset diagnostics in successful runs too; final probe
assertions passed and the process exited with code 0.

## Selected installation and upgrade

After the owner closed Pi, the selected schema 17 space received a verified
backup retained outside the active Core. A public restore into a separate empty
directory, public recovery and explicit schema 17 → 18 upgrade passed before the
active space was upgraded.

The final wheel replaced only the installed Zaratustra package; locked runtime
dependencies stayed unchanged. All 121 installed product files matched the final
wheel. Model-free comparison of original table columns and public reads confirmed
unchanged original revisions, addresses, outputs, owner acceptance, receipts and
invocation accounting in both rehearsal and selected upgrade. The active space
identity, epoch and configuration bytes stayed unchanged.

Installed `zaratustra verify` confirmed version 0.24.1, schema 18, active selected
space and ordinary system Pi 1.0.4 without a model request.

Early rehearsal-script errors were retained in private evidence: loading SQLite
before setting its runtime environment; including backup-maintenance rows in a
domain baseline; copying a backup under a non-UUID directory name, correctly
rejected by public restore; and opening a backup inspection without immutable
snapshot mode, which created empty SQLite sidecars. Only those exact generated
empty sidecars were removed. The harness was corrected; no product bytes or
strict restore checks were changed or relaxed. The final rehearsal passed.

No real model call, Activity deletion or recreation, exporter operation or private
Git update was performed. Detailed personal paths, addresses and operational
receipts remain private.

## Final package

File: `zaratustra-0.24.1-py3-none-any.whl`.

SHA-256: `8baa304e3b2374a1cae5a84b7e9262ec9716c45b994d366275b8dcb3da06a95e`.

Earlier schema 18 gate artifact SHA-256:
`dacc5a8a061b474e31f83ada093c7df873c727309dd34c9ba7751c162fe455b4`.

Intermediate symmetric-registration artifact SHA-256:
`43992ac14b38c2e7f0c7f2444b16b5e30528fa6b67e96f841626bb7343202110`.

The final artifact is immutable; later report edits do not change its packaged
bytes. Selected personal installation and explicit upgrade are complete. Source
commit [8fc0b0ae9f9abf131266a887c2e290a3641368ec](https://github.com/ainazemtsau/zaratustra/commit/8fc0b0ae9f9abf131266a887c2e290a3641368ec)
was pushed as a fast-forward to the authorized public `main`. Authenticated
GitHub API readback confirmed that exact commit and the intended public files.
Subsequent report-only commits do not change the final wheel SHA or packaged bytes.

## Evidence limits, cost and acceptance

Zero real-provider or paid API calls were made in this correction. Final ordinary
Pi fixture scenarios made 49 actual localhost HTTP requests. Mechanism and
persistence checks do not guarantee every future model interpretation or prove
the cause of the earlier intermittent RPC EOF.

No personal Activity deletion, export change, Git representation publication or
automatic Work acceptance was performed by this package. The verified private
backup, restore rehearsal, installation and selected upgrade are complete with
preservation evidence. Public code publication and authenticated readback are
complete. Private addresses, receipts, paths and configuration are retained
outside the public report.

Owner acceptance pending. Next: solmax.

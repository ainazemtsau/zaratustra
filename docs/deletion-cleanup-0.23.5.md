# Derived Artifact cleanup — 0.23.5

## Observed failure

A schema-16 workflow can create several derived Artifacts under one operation.
The deletion job is keyed by that operation, but three sanitation producers kept
the first job address and overwrote its technical cleanup event with the last
Artifact address. Assigned maintenance correctly refused this mismatch.
The failure occurred in a restored maintenance rehearsal before live deletion.

## Correction

Workflow, Activity setup and typed-data sanitation share one registration helper.
It preserves the job's canonical Artifact address and merges exact Work/Attempt
cleanup pairs. Repeated sanitation of completed, unavailable bytes does not reopen
the job; newly retained material under the same origin can reopen it.
The strict address check is unchanged. Malformed existing pending jobs are refused;
this package does not silently reinterpret or repair their stored addresses.
Schema remains 16. No model call, export or owner Work acceptance is added.

## Evidence

The adapter regression uses a real schema-16 setup, shared-origin workflow packets,
actual DBOS queue records and assigned RPC copies. It deletes the owned Works and
Activity through Core, completes maintenance and repeats it, while checking an
independent Work. A corrupted cleanup address is refused before technical copies
are removed. Both variants passed from an isolated installed wheel; the prior
0.23.4 wheel fails the same regression at the cleanup-address invariant. A fresh
private restore rehearsal completed selected deletion and maintenance, preserving
independent Work history, original sources and send accounting. No private data
is included here. The full native gate passed 1026 tests, hygiene, Ruff, mypy,
32 import contracts, build and report structure. Both regression variants passed
again from the final wheel outside checkout. The bounded read-only evaluator
checked installed module hashes and the changed boundary without personal access.

The selected installation preserved the existing domain state and configuration.
Owner-authorized live maintenance then completed deletion with exact independent
history and accounting checks; no new Activity or real-model call was made.
Operational receipts, original answers and archived Pi sessions remain private.

Final wheel SHA-256:
`1688DC147501385AB4DF55ED53A77A0996F10DDE3B8F9E0DD318E05DA83FD99B`.

## Limits

Maintenance evidence is separate from model understanding of a new Activity.
Old malformed pending jobs need an explicit recovery path; a fresh checked backup
can be used for a rehearsal. Managed Pi session cleanup remains space-wide, so
operational history must be archived before selected personal deletion.
The bounded read-only evaluator found no material flaw in the changed registration
or reader. The new adapter test has one assigned Attempt; union of different
Work/Attempt pairs and reopening a completed group are not separately exercised
by this test. No broad claim about every possible maintenance state is made.

## Acceptance

Owner-authorized selected deletion and installation do not accept future Work.
Public code publication is not part of this maintenance action.

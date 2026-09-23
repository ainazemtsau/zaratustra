# Core v0.1 Stage 3 — Activity and Work

## Authority and scope

The owner accepted Stage 2 at
`62a173c7d9a875e6709bf2e0dbe0d8d7e7fa31df` and separately authorized
this minimal Stage 3. The specification is
`Zaratustra_Core_Specification_v0.1.md` with SHA-256
`1DDCBF9DBFD58426781F61A67A170D3CE85FCD2BA27B17549773ED3356F9428D`.
The exact technical plan is `STAGE3-PLAN.md`.

This stage persists one continuing Activity and concrete Works inside the
independent foundation. It does not execute a Work. It does not introduce Method,
Attempt, planner, scheduler, dispatcher, Pi, DBOS, memory, Sleep, old `.zara` data,
or a real owner Activity.

## Stored contract

An Activity has a stable id, immutable revisions, title, goal and current
`ongoing`, `paused` or `completed` state. A Work has a distinct id and exactly
one Activity parent. Its first revision records a concrete goal, exact Artifact
input references, constraints, named expected outputs with media types, and
`method="none"`. The supported Work states in this stage are `proposed` and
`succeeded`; no execution or failure state is simulated.

`CreateActivityRequest`, `ReviseActivityRequest`, `CreateWorkRequest`,
`LinkWorkOutputRequest`, `AcceptWorkRequest`, and the two terminal subject
deletion requests use the foundation's single `apply_operation` transaction.
Each has an exact operation id and fingerprint. Revisions, operation audit and
metadata-only receipts
commit atomically. Stale revisions and changed intent under a used operation id
are refused.

Creating an Artifact or linking it to an output slot leaves the Work
`proposed`. `AcceptWorkRequest` requires a separate current `work.accept`
Grant, the current Work revision, every declared slot linked, matching exact
Artifact revisions and media types, and current `record.read` rights for all
inputs and results. Its explicit basis and trusted authority source are saved
with the acceptance operation. Only then is the Work `succeeded`. This is a
structural check plus an authorized actor's judgment; the program does not
infer semantic success from a file or text.
`read_operation_audit` exposes the exact content-free target, Grant and
Decision revision references and trusted source under the separate
`receipt.read` right.

The Activity does not become completed when one Work succeeds. A paused or
completed Activity cannot receive a new Work. Completing an Activity with an
unfinished Work is refused. A deleted Artifact leaves exact references in Work
history, but `read_work` marks those references unavailable instead of silently
substituting another revision.

## Rights, schema and maintenance

The three new actions are `activity.write`, `work.write` and `work.accept`.
Creation of an Activity uses a space Grant; changing it uses an Activity Grant.
Creating Work uses a Grant scoped to its Activity; linking or deleting Work uses
a Work Grant; accepting it uses a distinct Work Grant. Existing space Grants may
cover these actions. Resource type and id must both match, so a Work Grant
cannot authorize an Artifact with a coincident id. Current Decision denies,
epoch binding, trusted local authority, separate `record.read` and
`receipt.read` remain active.

`initialize_space` still produces Stage 2 schema 1. `upgrade_space` is an
explicit, additive, `maintenance.backup`-authorized transaction. It adds
strict subject record/revision/content, backup inventory and deletion-job
tables, records migration 2 and advances the space state revision. It does not
silently expand an existing Grant: a schema 1 owner whose Grant lacks the new
actions must issue a current Grant through the existing `grant.write` path.
Stage 2 schema 1 spaces remain readable and writable for their Stage 2
operations until explicitly upgraded.

Activity/Work prose lives in managed `subject_content`, with exact revision
addresses. Subject deletion tombstones the subject, removes all of its managed
content, blocks future subject reads and writes, and contaminates registered
backups that contain it. An Activity cannot be deleted while a non-deleted
Work belongs to it. `complete_deletions` captures exact initial subject and
Artifact jobs, removes affected backup packages and performs the existing
closed-connection checkpoint/VACUUM sanitation. It leaves concurrently created
jobs pending for a later run. As in Stage 2, deletion removes the prior
revision-forming operations' receipts and replaces their content-derived
fingerprints with a non-replayable marker. Their operation ids and permitted
audit references remain. Replaying one of those ids returns
`history_unavailable` after the current `receipt.read` check and cannot
recreate the subject; direct receipt read returns `not_found`. The deletion
operation's own content-free receipt and fingerprint remain, so its exact
authorized replay returns that receipt without another effect. Unaffected
objects and receipts keep their ordinary semantics.

Verified schema 2 backup and restore use the existing SQLite Backup API,
manifest and inventory path. Restore is quarantined, rotates the epoch and
requires fresh trusted-local recovery before subject reads or writes. Schema 1
backup compatibility and Stage 2 Artifact deletion remain supported.

## Reproduction and verification

With the verified SQLite 3.53.3 DLL set in `ZARATUSTRA_SQLITE_DLL`, run:

```powershell
uv run --locked python -m tools.probe_stage3 run --output _scratch/<new-directory>
```

The probe creates only fictional data, checks that the Work stays proposed
after both Artifact creation and output linking, explicitly accepts it, then
starts a new Python process to read the Activity, Work, exact input/output
references, result digest, acceptance basis, trusted source and receipt.
Its JSON summary stays in the ignored scratch directory.

Focused tests cover independent Activity/Work lifecycles, exact historical
reads, replay, stale revisions, incomplete/mismatched outputs, separate
write/accept rights, subject deletion, backup contamination, quarantine and
fresh recovery, old-operation `history_unavailable`, deletion-operation
replay, unaffected receipts and unavailability after result Artifact deletion. The full
`uv run --locked python -m tools.check --deliver` is the delivery gate.

## Next boundary

This stage establishes persisted intent and authorized acceptance only. The
next separately authorized step may connect a real developer workflow and
execution/Attempt lifecycle to these records, with explicit owner review of
the technical runner and any Pi/DBOS dependency. The present stage contains
no automatic action or model integration.

END_OF_FILE

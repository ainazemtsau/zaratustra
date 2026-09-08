# Work 4 — Artifacts + projections: PLAN

call: c-solmax-zaratustra-m0-artifacts-20260908-work4
mode: PROBA; engineering_contract: 36
product_basis: 11b4b95d0f696c63e3ae4d56cb8fb4b748cd933d
direction_admission: e223143d9fc90127ae3e198b96f57d49254a171b
actual_worktree: C:/my_global_workflow/68ce/zaratustra
branch: codex/work4-artifacts-projections
status: technical decisions conform to the admitted plan; implementation authorized

## Sources, delegated decision and size

The complete committed CALL and closed T2 were read before product changes.
The accepted architecture hash is
4f90d19fc742ab616301b6b4121880f76c75faaeb1f606c8190a84853d8b3e0e.
The comparison uses §§3–7,26–29,41, Product AGENTS/validation.config, Work 3 PLAN,
W21 owner words and retained evidence. Committed Direction source hashes and the
unaltered CALL copy are retained in evidence/sources.json and CALL.md.

Verdict under owner-ack:solmax-plan-conforming-20260907: the lifecycle below
implements §§4.2,4.4,5 and Work 4 without altering accepted WHAT, replay ordering,
trust or the Works sequence. Architecture candidates are supporting design evidence.
This is the executor applying existing delegation, not invented new owner words.

Sizing: one existing fictional graph, one version table, three narrow operations,
one generated overview, read/inspection and explicit rebuild; no new dependencies.
Estimated within a focused half-day, including failure and installed checks.
No external service, account, expense, new deadline or permanent workspace.

## W19 / W21 — same mutation and exact current authority

Version 1 requests and their canonical digest/fingerprint remain compatible.
Version 2 adds artifact descriptors and exact version/hash references, never file
text, a caller identity or an approval field. LocalAuthorization still binds the
whole request, expected global revision and selected resolved workspace path.
CLI content-file bytes are separately compared with the exact confirmed digest/size.

One apply_mutation handles existing operations plus authorize_artifact,
publish_artifact and restore_artifact. The new administrative grant requires exact
owner-channel authorization, a ready Work with work_metadata, and the sole declared
Artifact belonging to that Work/Process. Its scope is work_metadata_and_artifact:
metadata plus only that Artifact's versioned content. It is not arbitrary files,
another Artifact, another Work or a future grant. authorize_work continues to grant
metadata only; revoke_work removes both; terminal Work cannot be reopened. Migration
and initial bootstrap grant nothing. Metadata/receipt read accept either current
metadata scope; artifact writes additionally require the new scope.

Literal order remains schema -> current Work/authority -> global revision ->
duplicate -> referenced artifacts -> mutation/event -> receipt -> projections.
Original stale replay conflicts; a refreshed same-id/same-intent request returns
its saved receipt after current rights checks; changed intent collides. Duplicate
does not republish content, even if a referenced file is now missing. It may rebuild
the current projection. Receipt proves the DB effect; content read separately
validates current bytes and never interprets a receipt as present availability.

## W20 / W24 — observable file and DB boundary

Explicit schema 4 adds immutable artifact_versions metadata. Released v1/v2/v3
migration source bytes stay fixed. init remains schema 1; migrate explicitly
targets 2, 3 or 4. Read/init never migrate. No accepted DB is upgraded in place.

Publication holds the same BEGIN IMMEDIATE transaction as current authority and
revision checks. Core writes a uniquely named staging file inside the selected
Artifact directory, flushes/fsyncs it, checks SHA-256 and length, then publishes
artifacts/<artifact-id>/<operation-id>.blob without replacing an existing file.
An existing name is reusable only when its bytes exactly match this descriptor.
The version id is the globally unique publication operation id. DB registration,
Artifact active_version/status/revision, Work/global revision, event and receipt
then commit together. Long content is not stored in DB or the event.

Before DB commit a final file may exist but is not registered/active. A write,
publication or DB failure keeps the previous DB effect. Unregistered files and
staging leftovers are reported by owner-local inspection and retained, never
silently registered or deleted. A same-id retry can reuse the complete verified
orphan. There is no automatic cleanup or background recovery process.

After commit, a lost reply leaves one durable receipt. There is no cross-filesystem
atomicity claim. SQLite statement/commit rejection, publication interruption,
lost reply, contention and rebuild failure are tested. File fsync plus SQLite FULL
are used; power loss, disk/controller failure and hostile same-user replacement
races are not proved or promised by this local slice.

Each content read resolves a registered version in a coherent DB snapshot and
checks the file type/path, exact length and SHA-256 before returning bytes. Missing,
modified, foreign and unregistered content is refused with no fallback to an older
version. Metadata/history remain readable so the failure can be diagnosed. A later
successful read validates bytes again; late availability is never inferred from DB.

Explicit restore_artifact uses the same current authority and Mutation API, an
exact registered version/hash and caller-supplied matching bytes. It can restore a
missing file, or retain a damaged file under a unique quarantine name before
publishing the verified replacement. This is a separately requested audited repair,
not a second publication/active switch or an automatic replay effect. On failure,
DB remains unchanged; retained files permit inspection and an explicit retry.
No DB/state Markdown hand edit is a recovery path.

## W22 / W27 — revisions, audit, public consumers and projections

Each domain mutation advances global/Work revision together. Publication also
advances Artifact revision and changes its active_version; historical descriptors
and files remain. References bind Artifact id, immutable version id and SHA-256
inside the current Work/Process. There is no mutable-path-only reference. Global
revision changes cover rights and all admitted artifact changes, including repair.

History validates the old Work chain plus new Artifact before/after images and
version descriptors against the saved version table/current Artifact. Physical
availability is checked by content reads/inspection rather than making metadata
history impossible to inspect after file loss.

One projection, projections/overview.md, includes Process, current Work, Artifact
version metadata and provenance. It is generated owner-local inspection, not a
Work context package. It labels generated_from_revision and generated_at. For
deterministic rebuild, generated_at is the retained source event timestamp (or
initial/workspace creation for an empty history), not rebuild wall time. It makes
no claim that file bytes are currently available. Raw artifact content is not read
or copied into this DB-derived overview.

Every schema-4 mutation records overview.md in affected_projections. After the
effect commits, rebuild obtains the workspace write lock without changing DB,
reads the latest coherent saved state and atomically replaces a complete overview.
Thus a delayed rebuild cannot overwrite a newer revision. Rebuild failure reports
the committed receipt plus rebuild_required (CLI exit 2); it never reports rollback
or issues a second mutation. Explicit projections rebuild uses the same path,
no revision/event/receipt change. Projections status compares deterministic bytes
with DB-derived bytes and reports missing/stale/changed. Projection input is never
parsed into authority or state; edits are discarded by explicit rebuild.

Public Core seams expose immutable metadata, verified bytes, owner-local inspection
and rebuild alongside the one mutation API. CLI delegates. Existing recursive
core/local/cli contracts cover new files within Core; no new package boundary.

## Remaining W19–W27 and checks

| ID | Work 4 disposition | Remaining answerer, point and rewrites |
|---|---|---|
| W19 | Lifecycle retains literal order, current rights and one receipt/effect. | PLAN before Works 5/7: importer and Result/next unit; rewrites importer/receipts/linkage/tests/migrations; cheap reversal unproved. |
| W20 | Publication/orphans/repair/rebuild/late availability boundary above. | PLAN before Work 7 Result continuation and any broader durability claim; rewrites references/recovery/evidence/migrations. |
| W21 | Exact owner channel and narrow current Artifact scope above. | PLAN before Works 5/6/7: actual importer/context consumer binding; rewrites adapters/permissions; no runtime acceptance inferred. |
| W22 | Global/Artifact revisions and exact immutable references above. | PLAN before Work 6: context scope/freshness/budget/delivered manifest, decision/membership dependencies; rewrites snapshot/context/tests. |
| W23 | No clean-chat claim. | PLAN before Works 6/8; exact input and actual separate response on five facts in Work 8; rewrites delivery/demo; unprovable cleanliness blocks. |
| W24 | Explicit v4, versioned requests, SHA-256, staging/no-replace, deterministic rebuild above. | PLAN before later cleanup/recovery consumers; rewrites mechanics/tests/migrations, semantics return W19–W22. |
| W25 | One fictional graph per new copy; foreign id/hash/path and file failure fixtures. | PLAN before Works 5/6/8 context isolation fixture; rewrites fixtures/tests/demo, no second full Process. |
| W26 | Isolated worktree, same accepted base, no remote, separate installation and preserved originals. | PLAN before permanent folder/hosting/independent external install-upgrade; rewrites package/layout/docs; reassess with external consumers. |
| W27 | Public Core/data/receipt/files/projection seams for E1/E2/E3/E6/E8/E9/E10/E11. | PLAN at each consumer admission; rewrites Core/data/consumer migrations; E4/E5/E7/E12 get no invented API, M1+ not prerequisite. |

Failure checks cover publication and DB boundaries, new authority/references,
original/refreshed replay, corruption/unavailability/repair, projection rebuild,
migration preservation, contention and historical audit compatibility. Full native
check/deliver and installed wheel on a new copied 0.3 trial are required. Setup uses
one bounded read-only evaluator per AGENTS; no further delegation is requested.
Tests check hidden consistency, not owner-visible prose or tuning magnitudes.

Owner runtime PASS, binding fresh G5, T3/M0 closure, Work 5–8 and Direction CALLs
are not produced here. Both no-automation owner acknowledgments remain operative.

END_OF_FILE: docs/work4/PLAN.md

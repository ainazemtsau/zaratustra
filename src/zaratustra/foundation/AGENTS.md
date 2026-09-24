# Core v0.1 domain foundation

This package is the independent Core v0.1 subject foundation. It never imports the
legacy `zaratustra.core` package or higher product surfaces. Its public contract is
`__init__.py`; internal modules share only explicit typed models.

`runtime.py` admits the exact supported SQLite build before stdlib `sqlite3` loads;
the public package initializer calls it before importing any Core submodule.
`storage.py` owns the `.zara-core` layout, schema definitions, checked connections,
backup/restore and deletion sanitation. `operations.py` owns the authorized
additive schema 2 upgrade, the sole domain mutation path after space creation,
and current Decision/Grant checks. `execution.py` owns the explicit schema 3
upgrade, resource/Attempt/invocation state, the explicit schema 4 continuation
upgrade and addressed execution reads. `models.py` owns frozen wire/domain values
and must not become an unvalidated JSON bag.

Artifact bytes exist once in `managed_content`; Activity/Work prose lives in
`subject_content`. Revisions, audit and receipts may
retain identifiers and permitted outcome metadata but never copy managed payload.
Historical reads are exact and never fall forward. Stage 3 Activity/Work content
uses `subject_content` and the same operation/audit/receipt path. Work acceptance
is a separate authorized operation after exact output checks; Activity remains
independent of a Work outcome. Restore stays quarantined until a
fresh trusted-local recovery operation establishes the new epoch.

Schema 5 is an explicit additive upgrade for immutable Method versions, exact
composite Work plan revisions, child ownership/issue, materialized obligations,
and Method deletion jobs. `composition.py` owns these records and direct
model-free coordination. The shared `apply_operation` gate checks composite
child readiness and parent acceptance before old Work/Attempt routes; in schema 5
composite Stage 4/5 execution routes refuse explicitly.
Method use requires current Decision/Grant authority. Child deletion preserves
the parent obligation while sanitizing dependent plan revisions and confirmation
bases. Artifact deletion also sanitizes dependent plans and confirmations. An
affected exact historical revision is addressable but returns
`content_unavailable`; a lost confirmation reopens its obligation. A parent
whose current plan was sanitized cannot continue under that plan. Parent and
Method deletion sanitize all new content through the existing maintenance
boundary. Sanitized plan payload retains only validated structural role edges
and Artifact addresses so a later deletion can still find dependent bases after
restart. Pre-index sanitized plans use conservative obligation sanitation.
See
`docs/core-v0.1/STAGE6-PASS1-IMPLEMENTATION.md`.

Schema 6 is an explicit additive upgrade for exact child Attempt plan pins
(parent, role, plan revision and Method id/version/checksum). An assigned child
Attempt rechecks its pin, current issue, dependencies, exact inputs and
`method.use` in the shared gate before every effect; stop and sent-call outcome
records stay available. Parent execution and interactive composite Attempts stay
unconnected. `work_status.py` derives proposed/ready/running/waiting/blocked/
succeeded (and reads recorded schema 7 outcomes) from the same Core records in the
reading transaction; never store a
second editable status or copy plan content into pins, outbox or technical
payload. Derived readiness asks the same Core issue/acceptance rules without an
actor (`check_parent_acceptance`); a stale prerequisite reads `blocked` with its
address, while the operation still checks current rights. See
`docs/core-v0.1/STAGE6-PASS2-IMPLEMENTATION.md`.

Schema 7 is one explicit upgrade (`upgrade_plan_revision_space`) for all of pass 3;
its DDL grows by part and is frozen only at the pass release, so checkpoint spaces
are disposable. `close_work` records failed/cancelled/stale as one `WorkClosure`
inside the Work revision (absent from canonical JSON while empty) under
`work.accept`, plus `method.use` for composite members. It holds execution exactly
like acceptance (`_hold_work_execution`). `stale` names only premises of that Work
that held at their exact address (retained `record_revisions` metadata, never
deleted bytes) and then changed; Core never assigns it. A composite parent closes
only after every child is closed; there is no cascade. A closed child makes
dependent leaves `dependency_closed`; `any` is closed only when every member is.
At schema 7, `sanitize_deleted_dependency` also retires every WorkAcceptance or
WorkClosure basis (`basis = null`, receipt out of replay, holding backups
contaminated) that structurally depends on the deleted Artifact or child Work: the
Work's own revisions, its own plan history and children, or its parent's plan history
(global, own and upstream role addresses, upstream children), read through the
retained index once sanitized. Outcomes, audit, obligations and independent bases
stay. Schemas 2-6 never store a retired basis: a deletion that would need one is
refused with addressed `upgrade_required` before any change (`require_outcome_upgrade`
in the shared gate); nothing upgrades implicitly. A basis an earlier deletion left
there (dependency deleted after the outcome was recorded) is withheld from Work reads
without rewriting, its replay/receipt answer `upgrade_required`, and
`complete_deletions` changes nothing and reports `retained_bases` with
`upgrade_required = 7`. The explicit 6 to 7 upgrade retires exactly those and then
needs `maintenance.delete`. That order decides only retrospective sanitation; it does
not prove a later basis holds no copy. Quotes without a stored structural link are not
covered. See `docs/core-v0.1/STAGE6-PASS3-CHECKPOINT-3.1.md`.

Part 3.2 adds no records. Independent children of one parent run at once, each through
its own Attempt and resource; an exclusive root stays single until a stop is recorded
(the unchanged Stage 5 `resource_busy` rule). `work_status` keeps the pass 2 phase order
but names every active branch and every closed branch that the current plan or an open
obligation refers to (`branch_review`), each with role and Work address; with nothing
waiting or running a failed branch makes the parent `ready` for review, and a stale
prerequisite still blocks it first. `acceptance_pending` appears exactly when the
structural rules of the acceptance operation hold (every declared obligation, possibly
none; exact bound outputs; the completion, such as `any`), not only after every child
succeeded; acceptance itself stays separate and rights-checked. Integration that needs a closed branch (issue,
confirmation, a parent output link bound to it, parent acceptance) refuses
`dependency_closed` with its address; nothing is cancelled. See
`docs/core-v0.1/STAGE6-PASS3-CHECKPOINT-3.2.md`.

Part 3.3 adds no DDL. `choices.py` owns addressed choices: a Decision variant
(`ChoiceState`: name, value, one Work or Activity scope) written by the existing
Decision operations under `decision.write`. `_authorize` skips choices, so access stays
with `require_grant`/`deny` rules; a revision keeps the variant, name and scope. The
choices that apply to a Work are the current active ones covering it, a composite Work
above it or its Activity; differing values are a formal `decision_conflict` naming every
address, never ordered by scope or time. A conditional obligation
(`ChoiceApplicability`) materializes `unresolved`; `resolve_obligation_applicability`
(`work.write` + `method.use`) records `active`/`open` or `inactive` with the exact choice
address, and only when the instance is unresolved or its choice no longer holds. The
recorded revision is never rewritten: a revised or revoked choice reads
`applicability_stale` and acceptance refuses `stale_basis`. The `decision_value` leaf
closes on another exact value. Issue, child effects, confirmation, a parent output link,
acceptance and `work_status` recompute the applicable choices in their own transaction.
Everything new is refused below schema 7 and absent from earlier canonical JSON. See
`docs/core-v0.1/STAGE6-PASS3-CHECKPOINT-3.3.md`.

The foundation stores Work execution records but never imports Pi or runs a model.
Schema 4 adds durable assignment, addressed wait/answer, a saved remainder,
stop state and pending/cancelled outbox records in the same operation/receipt path.
The Work remains proposed until its exact result is separately accepted. Recovery
closes old-epoch waits and cancels old outbox; unknown stop retains the resource.
Deletion purges these managed rows and payload in affected backups/live SQLite.
Schema 4 backup may also carry a checked DBOS SQLite snapshot and managed Pi RPC
home; restore keeps them inert in the new epoch. Core requires a technical cleanup
adapter before completing deletion when such data exists. The package still does
not import DBOS, Pi, a scheduler, dispatcher, memory or Sleep.
Stage/check numbers stay in documentation and tests, not product module names.

END_OF_FILE: src/zaratustra/foundation/AGENTS.md

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
closes on another exact value. A formal conflict keeps its code and addresses through
`all`/`any`: `any` refuses `decision_conflict` when every other member is closed for
good, `all` names it unless a member is closed; true alternatives and plain
`dependency_open`/`dependency_closed` are unchanged. Issue, child effects, confirmation,
a parent output link, acceptance and `work_status` recompute the applicable choices in
their own transaction.
Everything new is refused below schema 7 and absent from earlier canonical JSON. See
`docs/core-v0.1/STAGE6-PASS3-CHECKPOINT-3.3.md`.

Part 3.4: `waivers.py` owns addressed exceptions, a third Decision variant
(`ExceptionState`: one target requirement, parent Work and obligation key, and the exact
Method versions it covers) written under `decision.write`; `_authorize` skips every
variant but rules, and a revision keeps the variant and target. `waive_obligation`
(`work.accept` + `method.use`) needs an `active/open` instance (or one whose waiver went
stale) and an exact current exception whose target and limits match; it records `waived`
with the exception address and no evidence. A waiver is not a result and opens no
dependency. Acceptance refuses a waiver whose exception no longer holds (`stale_basis`),
and names waived requirements in its result and `WorkAcceptance.waived`; reads show
`waived`/`waiver_stale`. Deleting a dependency of the role takes a waiver off (execution
`open`) while addressed applicability stays. At schema 7 an obligation revision depends on
the deleted subject through its role under the current plan and under the plan revision
current when it was recorded (a resolution or waiver may precede a plan revision).

Part 3.5: `revalidation.py` owns `premise_changed`. At schema 7 an accepted child result
whose own premises changed (exact inputs of its accepted revision, Artifact/Decision
leaves of its readiness in the issuing plan revision) stays succeeded, but every
integration (dependent leaves and effects, confirmation, a bound parent output link,
parent acceptance) refuses `premise_changed` with held and current revisions until
`revalidate_result` (`work.accept` + `method.use`) names exactly those changes. Rechecks
live in the schema 7 table `result_revalidations` and permit integration only while the
named revisions stay current. Like a formal conflict, `premise_changed` keeps its code
through composite conditions while it blocks (`_BLOCKING_CODES`: the conflict first); a
true `any` alternative passes and `stale_basis` keeps its earlier semantics. A recheck
basis goes with any known structural dependency of the child's outcome
(`_outcome_dependencies`: its revisions, its parent's plan history with basis and inputs,
upstream children) or its own addresses, found before the deleting transaction changes
anything; deleting the parent removes the records. See
`docs/core-v0.1/STAGE6-PASS3-CHECKPOINT-3.4-3.5.md`.

Parts 3.6–3.7: `active_plan.py` owns `revise_active_plan` and the exact reads
`read_plan_nodes`/`read_role_history`. A started plan gets revision N+1 only with an
explicit decision for every node of N and every new node (keep, replace, cancel, stale,
release, add), under `work.write` + `method.use`; a node leaving unfinished is closed as
`close_work` records it (`work.accept` on it, the 3.1 hold). The schema 5 row per role is
never rewritten: Works joining through a revision are members in `work_plan_members`,
each revision's decisions are addresses in `work_plan_nodes`, and the effective issue of a
child is its issue revision or the last revision a `keep` carried it into, only after the
node's rights, inputs and readiness were rechecked under N+1 (`child_binding`). An
obligation whose evidence belongs to a Work that left the role reopens `node_replaced`.
An active Attempt of a kept node continues through `execution_plan_transfers`; the pin
check accepts its pin or a transfer into the current revision. Any other effect of a
child's pinned Attempt refuses `stale_plan` before `work_closed`, a late answer to a closed
wait `stale_wait`; stop and sent-call outcomes stay open. The retained plan index names the
Work of each role (`role_works`, schema 7 only), so deletion seeds, outcome and recheck
dependencies follow the Work that filled a role in each revision. Deleting a child takes
its transfers with its pins; deleting the parent removes members and decisions. The
3.6–3.7 review correction also sanitizes a plan revision when a node decision
addresses the departing Work: its rationale may quote that Work, so the revision
operation loses replay while the address-only node history stays. Obligation evidence
and child outcome bases follow the then-current role filler and plan revision; deleting
old evidence leaves a replacement's independent confirmation, basis and replay intact.
Child outcome and recheck bases also depend on a historical plan revision that named
that same Work before it was issued; an issue revision is not a history cutoff. See
`docs/core-v0.1/STAGE6-PASS3-CHECKPOINT-3.6-3.7.md`.

Part 3.8 records an exact Method binding for every schema 7 plan revision in
`work_plan_methods`. `revise_active_plan` alone changes the Method of a started
composite Work: it checks `method.use` for the target, the parent input/output
contract, every old obligation mapping, and the current node decisions before
writing the parent Work revision and plan N+1 together. `work_obligation_transitions`
keeps address-only mappings and retirement Decisions; all old keys get a retired
revision, including keys reused by v2, while every v2 requirement gets a new
instance. Carried evidence is rechecked against the current accepted child output;
applicability and waiver have their own exact conditions. Kept Attempts transfer
only after the current pin and node recheck under the target Method. Active or
unknown Attempt pins/transfers hold their old Method against deletion. Historical
plan Method bindings remain readable by address after deleting the old definition.
Copied obligation bases retain their source revision for deletion sanitation;
deleting the parent removes both new tables. See
`docs/core-v0.1/STAGE6-PASS3-CHECKPOINT-3.8.md`.
The 3.8 review correction validates all obligation heads but returns only the
current Method's instances to operations and acceptance. `read_obligation` still
reads exact retired revisions. A new confirmation or waiver and any reopening
that discards a copied basis clear its `carried_from_*` address. Deleting a Method
redacts its `MethodObligation.source` copies by the Method bound to the recording
plan; a retired revision belongs to the preceding binding named by its transition.
The exact key, revision, status and Decision remain readable, while independent
later Method instances stay intact.

Part 3.9 uses existing schema 7 records for nested composite Works. An `add` or
`replace` node in `revise_active_plan` may carry `nested_plan`; the new Work,
initial plain children, plan, Method binding and obligations are one transaction.
`role_methods` pins an exact role Method when declared; otherwise the new
`PlanChild.state.method` records the chosen exact version before issue. Issue,
execution and integration check the full issued ancestor chain and `method.use`
at each level; closure retains the explicit 3.1 outcome path. A nested composite
Work has no own Attempt before schema 8; its acceptance applies its
own completion and obligations plus current parent membership. A departing
nested node must explicitly list every unfinished descendant with its own Work
revision and immediate parent's plan revision; closures run deepest first,
atomically. Address-only membership finds nested descendants during historical
plan and outcome sanitation; delete Works bottom-up. See
`docs/core-v0.1/STAGE6-PASS3-CHECKPOINT-3.9.md`.
The open 3.9 review correction follows Artifact addresses through saved descendant
Works, their plan histories and confirmation evidence. The retained plan index keeps
these addresses by exact role, including unknown pre-index descendants, so a later
deletion after restart can still retire dependent plan, outcome and recheck bases.
Each ancestor plan is considered only where its exact role filler matches;
independent replacements keep their own evidence, receipts and replay. The 3.9
technical review closed on exact `73fffa7afb7bdfcc815938a132ab73d3955115e0`
without schema 7, pass 3 or Stage 6 acceptance. Part 3.10 adds address-only
current plan decisions and the immediate owned plan of a nested composite
Work to `CompositionView`. A child's view includes its immediate parent's
addressed obligation, applicability and waiver states; `nested` holds the child's
own distinct plan and obligations. Neither view copies plan text. See
`docs/core-v0.1/STAGE6-PASS3-REVIEW-3.9.md` and
`docs/core-v0.1/STAGE6-PASS3-IMPLEMENTATION.md`.

Schema 8 is a separate explicit additive upgrade for a composite Work's own
assigned Attempt. `execution_parent_pins` records its own exact plan revision and
Method, while `parent_output_proofs` records the producing Attempt, pin and exact
Artifact. A plan declares an own output by Work and slot, not by Attempt; another
valid Attempt of that Work can publish a replacement without a plan revision, but
the old confirmation reopens and cannot silently attach to the new result.
`MethodObligation.role` is absent only for the schema 8 own-result variant.
The ordinary assigned Core gate checks the full issued ancestor chain, Method use,
current inputs/basis and both pins for a nested parent. Plan or Method revision
fences its Attempt; a sent call remains unknown with resource/reserve held.
`CompositionView.own_pins` and derived Work status expose addresses and own phase.
Exact history, backup format 2/schema 8, inert restore and dependent deletion use
the existing maintenance path. Schema 7 payloads and DDL remain byte compatible.
Its technical review closed at `2cd3cf8bd021be5584db4ea963799ec0fc2bc4f7`,
separately from Stage 6 acceptance. Pass 4 has only a working failure-matrix
plan; see `docs/core-v0.1/STAGE6-PARENT-EXECUTION-REVIEW.md` and
`docs/core-v0.1/STAGE6-PASS4-PLAN.md`. The implemented contract is recorded in
`docs/core-v0.1/STAGE6-PARENT-EXECUTION-IMPLEMENTATION.md`.

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

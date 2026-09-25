# Stage 6 pass 3, part 3.9 — open technical review

Independent Codex review of exact commit
`74485ca8f6b2b8c8d895ebfa800b3994ef737ebf` confirmed P1. Review is OPEN.
The full Windows `tools.check --deliver` PASS (662 tests, types, Ruff, 21
contracts, sdist, wheel) is the implementation session's result; the reviewer
did not repeat that full gate.

Public Core reproducer and report:
`C:\Users\Anton\AppData\Local\Temp\zaratustra-stage6-3.9-review-74485ca-1790326772351\review_nested_artifact.py`
and `READONLY-REVIEW.md` beside it. In P→N→G, unique Artifact X is only an
input of G. After G/Y and N are accepted, P is accepted with a basis quoting
X. Deleting X and completing deletions clears N's basis but leaves P's basis,
replay and receipt; the marker remains after restart in closed SQLite and a
new backup, despite `pending_jobs=0` and `live_store_sanitized=true`.

`_outcome_dependencies` included descendant Work IDs but only collected
Artifact dependencies of immediate children. The correction follows saved
structural addresses through descendants, their plan histories, confirmation
evidence and exact ancestor role fillers. A sanitized plan retains those
addresses for later deletion after restart. Plan text itself is checked against
its own references and nested plans already recorded at that revision: later
child outputs cannot retrospectively contaminate an earlier plan. This
distinction was required to keep two existing 3.6–3.8 regressions passing.

The implementation session reran the public reproducer on the unchanged
`f336fabee317da865b5e5ac45b8e3c1c48f2c186` checkout before editing:
P's basis and replay/receipt remained, and the unique X marker was present in
closed SQLite and a new backup, while maintenance reported `pending_jobs=0`
and `live_store_sanitized=true`. After the correction the same reproducer
retired P's basis, replay and receipt; the marker was absent from SQLite and
the new backup. Seven new public Core test cases cover acceptance, closure,
revalidation, nested plan basis, a historical nested plan before issue,
sequential deletion with a new process, quarantine restore, and an independent
replacement branch. The replacement's acceptance, Y confirmation, receipts and
replay remain available, as do the independent sibling's acceptance, receipt
and replay. Existing 3.6–3.8 tests are retained.

Implementation-session Windows checks on the corrected code:

- Final `uv run --locked python -m tools.check --deliver`: **PASS**, 669 tests,
  mypy on 187 files, Ruff format/check, 21 import contracts, sdist and wheel.
  Earlier full attempts exposed formatting and typing errors in the new tests,
  then two overbroad plan sanitation regressions; these were corrected before
  this final full pass.
- Checkout `tools.probe_stage6_rpc`: **passed**, 3 synthetic localhost HTTP
  calls, restart, backup/restore and deletion.
- Checkout `tools.probe_stage5_rpc`: the first invocation used the wrong Pi CLI
  entry and refused `pi_version`; with the pinned bundle entry it **passed**,
  2 synthetic provider calls and sanitized deletion.
- `tools.probe_install_stage6`: first run failed with `rpc_transport` and the
  ordinary Pi status assertion; its log did not contain `database is locked`.
  One repeat from the same source tree **passed** outside the checkout with an
  isolated Python environment and 3 synthetic HTTP calls. The successful
  report records source HEAD `f336fab` with a dirty source tree before commit
  and wheel SHA-256
  `9C6A8C6C1B8E2F887E90187EA6F58008B2FD8BC8AF698360B815EA6C8D23B1C9`.
  The intermittent failure's cause is not established; the passing repeat is
  not a claimed fix.

These are checks by the implementation session, not a new independent review.
The earlier 662-test full Windows pass belongs to the original implementation
session; the independent Codex reviewer did not rerun that gate. Arbitrary
quotes without a stored structural link remain outside the deletion contract.
This review stays OPEN for one combined independent review of the corrected
package. Part 3.10, schema 7/pass 3/Stage 6 acceptance, real models,
development migration and PR remain unstarted. The earlier `database is locked`
observation remains open separately.

## Independent review of `63f64eb` and implementation follow-up

A separate Codex review of exact commit
`63f64ebce37502028eca93a77db6c8458d1d5add` independently confirmed
that the previous nested Artifact sanitation P1 is fixed. Its own full Windows
`tools.check --deliver` passed: 669 tests, types on 187 files, Ruff, 21 import
contracts, sdist and wheel. The review then independently reproduced the
three findings below using public Core operations. Its read-only report and
scripts are at
`C:\Users\Anton\AppData\Local\Temp\zaratustra-stage6-3.9-fix-review-63f64eb-1790333378457\READONLY-REVIEW.md`.
These 669 tests and the findings belong to the independent review, not to the
current implementation session.

1. Nested N was accepted after a required input of ancestor P changed,
   although N's derived status was `blocked:stale_basis`. Its composite
   acceptance branch skipped the existing `check_child_plan` ancestor gate.
2. Replacing N skipped open optional S below already accepted composite H.
   Omission succeeded; explicit address refused `mapping_invalid`. With S's
   active Attempt and a sent synthetic invocation, the Attempt remained
   assigned and the invocation sent with held units. H's acceptance with S
   still open is valid under the declared completion condition.
3. Nested `add` accepted a text/plain Artifact in a named Method input
   declared application/json, while direct composite creation refused
   `output_mismatch`. Nested creation checked slot and address but not the
   pinned media type.

The implementation session repeated all three exact scripts on the unchanged
`63f64eb` checkout before editing, including the running-Attempt variant of
finding 2. Reports remain in ignored `_scratch/repro-3-9-review-*`. On the
corrected source, the same scripts show atomic `stale_basis` and
`output_mismatch` refusals; explicit S closure succeeds and preserves H/L,
while the sent invocation becomes `unknown`, the assignment `stop_requested`,
and held units remain 5. A separate regression tests the missing-S refusal
before committing the explicit replacement.

The correction uses `check_child_plan` for nested acceptance before checking
N's own completion. Subtree closure traverses finished composite nodes and
allows their addressed open descendants to close only within the atomic
departing-tree path. The ordinary direct closed-ancestor gate remains in
force. Nested creation checks each named input against the exact Method's
declared media type in the shared `add`/`replace` path. Five new regression
variants cover these refusals and valid cases, H's acceptance while optional
S remains open, S's active Attempt, the preserved finished nodes and
independent replacement. The prior sanitation and G → N → P tests remain.

Current implementation-session evidence: the focused nested-composition and
nested-deletion run passed 13 tests before the additional replacement-media
regression; the nested-composition run then passed all 7 cases. Focused Ruff
and mypy passed on the changed source and test files. Final full gate and
integration-probe results are recorded below after execution. Review remains
OPEN for one combined independent pass; no acceptance is recorded.

Implementation-session integration probes on this correction passed:

- Checkout `tools.probe_stage6_rpc`: 3 synthetic localhost HTTP calls,
  restart, backup/restore and deletion; report status `passed`.
- Checkout `tools.probe_stage5_rpc`: 2 synthetic provider calls, continuation,
  backup/restore and sanitized deletion; report status `passed`.
- `tools.probe_install_stage6`: wheel installed outside the checkout in an
  isolated Python 3.13.7 environment, SQLite 3.53.3, synthetic trial status
  `passed` with 3 HTTP calls. Its wheel SHA-256 is
  `BA6AB4A1F617682F3F27B778C25EE08420AA211B2E029A7036253D46F0D6A13D`.
  The report records source HEAD `63f64eb` and a dirty source tree because the
  corrections had not yet been committed.

These passing runs do not establish causes or fixes for the separate intermittent
`database is locked` and `rpc_transport` observations. No real model was called.

Final implementation-session Windows `uv run --locked python -m tools.check
--deliver` on the corrected package: **PASS**, 674 tests in 456.19 seconds,
213 format-clean files, Ruff clean, mypy clean on 187 files, 21 import
contracts kept, sdist and wheel built, and report structure passed. The full
gate log is in ignored `_scratch/final-3-9-followup-deliver.log`. This is the
implementation session's check. Its subsequent independent review follows.

## Independent review of `d0a117c`: one remaining P2

A separate Codex review of exact clean commit
`d0a117cf4cc59713ff96bdb6db6e82de2022897a` confirmed all three
preceding corrections and the earlier nested sanitation case. The reviewer
independently ran the complete Windows `tools.check --deliver`: **PASS**,
674 tests, types on 187 files, Ruff, 21 import contracts, sdist and wheel.
The reviewer also installed a wheel from that exact clean commit outside the
checkout and passed the Stage 6 compatibility trial with 3 synthetic HTTP
calls. This is independent evidence, separate from the implementation
session's 674-test run and pre-commit installed probe. The read-only report,
script and evidence are at
`C:\Users\Anton\AppData\Local\Temp\zaratustra-stage6-3.9-final-review-d0a117c-1790336242591\READONLY-REVIEW.md`.

The remaining P2 occurs when the *replaced node itself* is a succeeded
composite H: P → N → H, with accepted required L and open optional S.
Replacing H in N's plan without S correctly refuses `open_children`, but an
exact `DescendantClosure` for S refused `work_closed` on H. The reviewer
reproduced this with S idle and with an assigned, claimed Attempt and sent
synthetic invocation. Both refusals were atomic. This case was also present
on `63f64eb`; no partial commit or new data loss was observed.

The implementation session repeated both exact scripts on unchanged
`d0a117c` before editing. After the narrow correction, the same scripts
report atomic `open_children` on omission and a committed replacement with
exact S closure. H/L retain `succeeded`; S becomes `cancelled`. With an active
Attempt, assignment becomes `stop_requested`, the sent invocation becomes
`unknown`, the outbox is cancelled and held units remain 5. Reports are in
ignored `_scratch/repro-3-9-root-*` and `_scratch/verify-3-9-root-*`.

`_close_descendants` now checks the departing composite root's actual
current Work state and includes it in the local set of succeeded ancestors
only when it is already `succeeded`. The direct closed-ancestor gate remains
unchanged. Two new public-Core regression variants cover idle and active S,
omission, stale plan/Work revisions, permission denial, direct `work_closed`,
exact replay, preserved H/L receipts and the independent neighbor. The
focused nested-composition and nested-deletion run passed 16 tests; focused
Ruff and mypy passed. Final full-gate and probe results for this correction
are recorded below. Review remains OPEN and no acceptance is recorded.

Implementation-session probes on the narrow P2 correction passed:

- Checkout `tools.probe_stage6_rpc`: 3 synthetic localhost HTTP calls,
  report status `passed`, SQLite 3.53.3.
- Checkout `tools.probe_stage5_rpc`: 2 synthetic provider calls, report status
  `passed`, sanitized deletion.
- Installed `tools.probe_install_stage6`: outside checkout, isolated Python,
  SQLite 3.53.3, trial status `passed` with 3 synthetic HTTP calls. The
  report records source HEAD `d0a117c` and `source_tree_dirty=true`, because
  the correction had not yet been committed. Built wheel SHA-256 is
  `255B4B123B63AA5A7349D16DEA34BA48B581D02CA7A4452422522CB16D971DED`.
  This is author evidence, distinct from the reviewer's installed trial of
  the previous clean `d0a117c` wheel.

No real model calls were made. `database is locked` and `rpc_transport`
remain separate open observations; these passing trials do not establish
their causes or fixes.

Final implementation-session Windows `uv run --locked python -m tools.check
--deliver` on the narrow P2 package: **PASS**, 676 tests in 438.21 seconds,
213 format-clean files, Ruff clean, mypy clean on 187 files, 21 import
contracts kept, sdist and wheel built, report structure passed. The complete
log remains in ignored `_scratch/final-3-9-root-p2-deliver.log`. This is the
implementation session's result; the 674-test gate and clean installed wheel
of `d0a117c` above belong to the independent reviewer. The new correction
awaits its own review.

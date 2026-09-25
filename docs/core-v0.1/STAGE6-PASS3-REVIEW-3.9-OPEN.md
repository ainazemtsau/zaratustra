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

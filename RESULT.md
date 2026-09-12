# Recoverable exact material transfer

## outcome

Scope achieved for the bounded entry-T4 recovery increment.

The existing intake seam now saves one exact coordinator plan before its first Core
effect and its returned stage receipts after publication and acceptance. A stable
per-intake advisory lock serializes cooperating retries. Every recovery obtains a new
trusted confirmation, uses current authorized Core receipt reads, compares the exact
original request fingerprints/revisions, verifies registered bytes and the accepted
Handoff, and runs only a missing stage whose revision was produced by this transfer.

The saved transfer continuation remains the selected ready Work at the acceptance
revision. A separate current continuation reports ready, cancelled or the standard
saved Result/next Work when the Work later closes. Intake never completes or reopens
Work and never fabricates a Result. Version 0.11.0 changes no Core transaction,
authority, identity, Pack-binding, Handoff or Result semantics.

## evidence

Focused checks on the candidate:

- 38 intake/reproduction tests passed, including repeat/restart, absent/stale/
  malformed/inconsistent journal, changed content/target/basis identity collisions,
  before-first-effect failure, publication file versus registration, publication and
  acceptance commits before progress persistence, final-response loss, unrelated
  post-publication revision, terminal Result, revoked read rights, projection errors
  and cooperating simultaneous retry.
- Strict mypy passed for all 85 checked source files; focused Ruff passed.
- `uv run --locked python -m tools.probe_entry_t4 --output
  _scratch/entry-t4-installed-20260912` exited 0. Two fresh isolated installed-wheel
  processes from an unrelated directory returned the same publication, acceptance
  and saved-continuation receipts with no second revision and one acceptance. Raw
  proof is retained under `_scratch/entry-t4-installed-20260912/`.

The complete delivery gate passed formatting for 97 files, Ruff, strict types for 85
source files, all 13 import contracts, 303 tests, report structure, and wheel/source
build. Its terminal exit was 0. The final task-local-cache output is retained at
`_scratch/entry-t4-final-deliver-cache-20260912.log`.

## assumptions

The caller explicitly selects one catalog Work and supplies the same exact external
envelope on retry. A trusted local console or already-authorized local-chat adapter
reviews the complete plan in every new session. The selected schema-7 workspace and
its existing `inbox` are local, writable and on a filesystem supporting the retained
advisory-lock and atomic-replace behavior used elsewhere in the product.

## cuts

No spanning rollback is claimed: publication and acceptance remain two standard Core
transactions. An unregistered leftover file is reported and may be reused only by the
ordinary exact Core retry; it is not acceptance. Journal inspection without approval
shows only its unverified intake id, preview hash and claimed stage names. Receipt
lookup still requires current metadata rights.

No hostile same-user writer, network-filesystem, sudden-power-loss or disk-loss
guarantee is added. No provider is contacted; this is not automatic research, a full
constructor/startup flow, actual ChatGPT transfer, personal workspace use, Pack
execution, UI, memory/model routing, paid service, CI/CD or notification work.

## cost

One coordinator journal/lock and recovery path in the installed intake package, a
public alias for the existing Core request fingerprint, focused generic fault and
concurrency tests, one two-process installed reproduction, documentation and a minor
version bump. No schema, migration or dependency was added.

## manual-acceptance

No personal-use pass or owner acceptance is claimed. Automated checks substantiate
only the stated technical behavior; a separate fresh physical reviewer follows.

## next

solmax

Remaining engineering risk is the next increment's full first-use setup and actual
external-chat handoff. This coordinator is intentionally limited to cooperating local
processes and the existing trusted adapter boundary.

END_OF_FILE: RESULT.md

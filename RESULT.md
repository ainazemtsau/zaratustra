# Readable manual external-chat request correction

## outcome

The bounded correction is implemented in version 0.12.1. New manual external-chat
requests use package format 2. Their `copyable_request` contains a mechanically derived
readable UTF-8 rendering of the selected Work goal, expected result, acceptance,
boundaries and budget and of every Artifact-version source present in the authorized
Core context. Each version is labelled with its source locator/revision, Artifact id,
version id, SHA-256, byte size and whether it is a direct accepted reference. The
complete original Core context follows unchanged and retains its original request
hash and byte size.

Rendering reads no workspace or external source. It verifies each embedded descriptor
against the embedded bytes, verifies every accepted reference has a matching version,
and refuses missing, duplicate, inconsistent or non-UTF-8 material instead of omitting
or mislabelling it. Embedded text and links remain inert data. The request does not
grant rights, confirm intake, impersonate approval or contact a provider.

Already-exported v0.12.0 format-1 requests remain accepted only with their original
exact rendering. Receive and same-intent recovery preserve their captured revision,
basis, context hash and request/intake/publication/acceptance identities. Both formats
enter the unchanged current-target/current-rights checks, strict full-material preview,
separate trusted confirmation and recoverable Entry T4 intake. Core source, schema,
identity, authority and mutation semantics are unchanged.

## evidence

- The focused correction gate exited 0 for the coordinator, its tests and the installed
  probe: formatting and Ruff passed, strict mypy passed, all 14 import contracts were
  kept, 10 focused tests passed, and the 0.12.1 distributions built. The new public
  regression uses a Russian route-choice basis with multiple numeric constraints. It
  verifies the exact readable goal, result conditions, constraints, saved bytes,
  Artifact/version ids and hash; it also verifies no post-open workspace read and
  refusal of an undecodable purported rendering. A format-1 request is received and
  retried with the original receipts, and a prompt edited to claim approval is refused.
- `uv run --locked python -m tools.probe_entry_t5 --output
  _scratch/entry-t5-readable-0.12.1-proof-20260912` exited 0. It built and installed the
  0.12.1 wheel offline with locked runtime dependencies, passed `uv pip check`, ran
  from an unrelated working directory, and used only installed public APIs plus newly
  created generic data. The summary records format 2, exact readable Unicode basis,
  format-1 identity preservation and same-intent receipt recovery, as well as retained
  `permission_denied`, `output_exists`, `wrong_target`, `stale_basis`, `ambiguous` and
  unavailable-neighbor outcomes. No provider was contacted. Evidence is retained in
  `_scratch/entry-t5-readable-0.12.1-proof-20260912/summary.json`, `commands.json`, the
  installed wheel and the two saved request packages.
- `uv sync --locked` exited 0. The full `uv run --locked python -m tools.check` then
  exited 0: 102 files were formatted, Ruff passed, strict mypy passed for 89 source
  files, all 14 import contracts were kept, all 314 tests passed, and the 0.12.1 sdist
  and wheel built. The report-aware `uv run --locked python -m tools.check --deliver`
  separately exited 0 with the same counts and passed the report-structure gate.

## assumptions

The human copies the complete product-supplied `copyable_request` field to the chosen
ordinary external chat and keeps the saved request file unchanged for receive/retry.
A trusted controlling terminal reviews the exact response preview before authorizing
intake. Saved material used through this manual text path is valid UTF-8; a binary or
otherwise undecodable version requires a different explicitly designed interface.

## cuts

No provider rerun, owner-usefulness result or owner acceptance is claimed; the parent
owns the real ChatGPT rerun and physically separate Sol review. This correction adds
no provider/API integration, automatic research, GUI, memory, model routing, Process
constructor, Pack behavior, new runtime dependency, Core change, migration, authority
or completion behavior. The existing 1,048,576-byte Core-context limit and
4,500,000-byte saved-request limit remain; a rendered package that exceeds the latter
is refused rather than truncated.

## cost

One versioned rendering path in the existing installed `first_use` wrapper, explicit
format-1 validation compatibility, two focused public regressions, an expanded
installed-wheel proof, a patch version bump, and bounded public documentation updates.

## manual-acceptance

Pending parent real-provider rerun and independent physically separate Sol review.
The technical checks above do not establish provider usefulness or owner acceptance.

## next

solmax

END_OF_FILE: RESULT.md

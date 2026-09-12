# Installed entry recovery probe

## outcome

A development evaluator reproduces creation, authorization, new content publication,
acceptance and bounded context opening through the installed package's public Core
operations on explicit disposable data and current schema 7.

It exits after publication and resumes in a separate process. Repeated recovery
returns the prior receipt without another effect. A foreign state change is
rejected while the original source revision remains unchanged.
Installed product sources and Core semantics are unchanged.

## evidence

Code commit: 64e5e6c579d225d8d82bc21fa77ef071f49c9a1e.
Instructions: docs/entry-t1/REPRODUCE.md.

Commands successfully executed at that code version:

- uv run --locked python -m tools.check --deliver
- uv run --locked python -m tools.probe_entry_t1 --output _scratch/<new-trial>

The native gate passed 255 tests and 11 import contracts, formatting, lint, types,
wheel/source build and report structure. One non-fatal local pytest-cache warning was recorded. The installed probe produced one accepted
Handoff after interruption, an exact bounded context, a no-effect duplicate
recovery, and a foreign-revision refusal. Three focused tests cover recovery,
publication-intent mismatch and foreign state changes.

Each local probe preserves its own exact inputs, states, history, receipts, context,
installed-source hashes and command transcript in the requested output directory.
The detailed run records are retained by the project maintainer. Running the
documented command produces fresh independently inspectable records.
Final report-only edits do not change the tested executable files.

## assumptions

The evaluator acts as an explicitly requested, trusted development application.
Its disposable-workspace inspection is not a production multi-process permission
interface. The coordinator derives its known publication progress and validates
the exact operation before accepting; it cannot substitute an unrelated revision.

## cuts

A shipped catalog, user entry shell, complete durable transfer coordinator,
constructor, real process, real chat-to-coding-agent transfer, and every interruption
boundary remain outside this probe. No new runtime dependencies, paid services,
automatic research, or installed Core changes.

## cost

One developer tool, three hidden-behavior tests, and reproduction instructions.
Reuses the public Core operations and the existing locked toolchain.

## manual-acceptance

No personal-use test or owner acceptance is claimed. Technical feasibility of
this bounded composition is not completion of the user entry or the product.

## next

solmax

Continue with human-readable process and work discovery while preserving current
authority and exact accepted context.

END_OF_FILE: RESULT.md

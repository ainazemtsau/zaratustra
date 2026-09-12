# Exact incoming material preview and acceptance

## outcome

Scope achieved for the bounded new-material intake increment.

One installed coordinator receives a strict external-material envelope for an
explicitly selected catalog Work, validates the current workspace/Process/Work/
Artifact identities, original revision, ready Artifact rights, immutable Pack
binding and every declared basis version and byte hash. Its confirmation preview
contains the full exact UTF-8 material, input/material hashes, current active version,
target/rights, basis and the complete planned `publish_artifact` and `accept_handoff`
requests.

After one exact trusted confirmation, the coordinator uses those two standard Core
mutations. The returned receipt distinguishes validated input receipt, immutable-byte
publication/registration, material acceptance and Work completion. Publication and
acceptance have separate Core receipts. Completion is explicitly `not_requested`,
and the accepted Work remains ready with no Result or invented next Work.

The original envelope revision is never refreshed. Material, target, basis or state
changes invalidate prior confirmation. Partial cross-call failure reports every known
committed receipt and does not claim rollback. Core identity, authority, immutable
Pack binding, Artifact and accepted-Handoff semantics are unchanged.

## evidence

Commands executed on the finished candidate:

- `uv run --locked python -m pytest tests/zaratustra/intake/test_material.py tests/tools/test_entry_t3.py -q`
- `uv run --locked python -m tools.probe_entry_t3 --output _scratch/<new-entry-t3-run>`
- `uv run --locked python -m tools.check --deliver`

The focused suite passed 20 tests. It covers exact new-byte preview/publication/
acceptance, first-version creation, current basis and content integrity, selected
identities, stale state, insufficient rights, terminal Work, malformed/duplicate/
oversized input, hidden approval, payload/target/basis changes after preview, missing
confirmation, partial acceptance and committed projection-error reporting.

The installed-wheel probe exited successfully from an unrelated directory in an
isolated Python 3.13.7 environment. On one newly created generic schema-7 source, it
measured original revision 4, publication revision 5 and acceptance/final revision 6.
The new material hash had no registered version before intake; afterward the exact
bytes and exact prior basis were verified through public reads. Publication and
acceptance event receipts were distinct, completion was `not_requested`, and the
continuation was the same ready Work. Missing confirmation, changed material, an
asserted approval field and a foreign Work identity were refused before success.

The final complete native delivery gate exited successfully after formatting, lint,
strict types, 13 import contracts, 284 passing tests and wheel/source build. Technical
decisions and limits are in `docs/entry-t3/PLAN.md`; reproducible installed steps and
retained-output inventory are in `docs/entry-t3/REPRODUCE.md`.

## assumptions

The caller explicitly chooses the catalog, designation and external envelope. The
catalog is discovery only. A trusted local console or already-authorized local-chat
application confirms the complete preview; no envelope/file field grants authority.
The selected schema-7 workspace contains the existing one-Process graph and a ready
Work with Artifact rights. Incoming material is UTF-8 text, not arbitrary binary.

## cuts

No provider is launched or contacted. This increment does not add durable transfer
replay/restart recovery, an all-or-nothing transaction across both Core calls, a
Process constructor, startup assistant, Pack installation/execution, Result/next
Work, subject-specific methods, real health or game data, model routing, memory, GUI,
actual ChatGPT transfer, paid/API activity or CI. A failed publication can retain an
unregistered final file under existing Core semantics; the incomplete receipt reports
that possibility.

The envelope is limited to 393,216 bytes and its UTF-8 material to 262,144 bytes.
Those are wrapper limits only, not universal Artifact or future research-report
limits. Generated Handoff metadata remains subject to Core's separate 64 KiB limit.

## cost

One dependency-bounded installed coordinator, one trusted-console wrapper, one CLI
subcommand, one added import contract, focused regression coverage, one installed
generic-data probe and two compact product documents. Envelope/preview/confirmation
policy is isolated from Core. The exact ids, hashes, planned requests and stage
receipts are a small compatible boundary for the next replay/recovery increment.

## manual-acceptance

No personal-use pass or owner acceptance is claimed. Automated checks establish the
stated technical behavior only; the parent performs the separate fresh review.

## next

solmax

The next engineering risk is durable cross-invocation transfer replay and recovery:
it must discover already committed publication/acceptance stages without refreshing
the original intended basis, duplicating effects or misreporting orphaned bytes.

END_OF_FILE: RESULT.md

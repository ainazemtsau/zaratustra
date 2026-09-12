# Exact incoming material preview and acceptance

## outcome

Scope achieved for the bounded new-material intake increment.

Follow-up correction: external-material envelope `version` is now exactly the JSON
integer `1`, without Pydantic coercion. JSON `true`, `1.0`, and `"1"` are refused
at intake parsing; no Core semantics, authority behavior, or feature scope changed.

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

- `uv run --locked python -m pytest tests/zaratustra/intake/test_material.py -q -o cache_dir=_scratch/toolchain/entry-t3-version-pytest-cache`
- `uv run --locked python -m tools.check --deliver` (complete output:
  `_scratch/entry-t3-version-final-deliver-20260912.log`)

The focused suite passed 22 tests. It covers exact new-byte preview/publication/
acceptance, first-version creation, current basis and content integrity, selected
identities, stale state, insufficient rights, terminal Work, malformed/duplicate/
oversized input, hidden approval, payload/target/basis changes after preview, missing
confirmation, partial acceptance and committed projection-error reporting. The
version regression accepts only JSON integer `1`; JSON `true`, `1.0`, and `"1"` are
refused through the public preparation path before any workspace effect.

Before the correction, a disposable new generic schema-7 workspace showed that JSON
`true` and `1.0` were accepted and normalized to parsed version `1`, while `"1"` was
refused (`_scratch/entry-t3-version-before-20260912.log`). After it, a separate new
generic workspace accepted integer `1` and refused all three invalid variants
(`_scratch/entry-t3-version-after-20260912.log`).

The final complete native delivery gate exited successfully after formatting, lint,
strict types, 13 import contracts, 287 passing tests and wheel/source build. Technical
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

One strict intake-schema field correction, focused regression coverage and factual
public documentation/report updates. Envelope/preview/confirmation policy remains
isolated from Core. The exact ids, hashes, planned requests and stage receipts are a
small compatible boundary for the next replay/recovery increment.

## manual-acceptance

No personal-use pass or owner acceptance is claimed. Automated checks establish the
stated technical behavior only; the parent performs the separate fresh review.

## next

solmax

The next engineering risk is durable cross-invocation transfer replay and recovery:
it must discover already committed publication/acceptance stages without refreshing
the original intended basis, duplicating effects or misreporting orphaned bytes.

END_OF_FILE: RESULT.md

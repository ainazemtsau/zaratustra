# Core v0.1 Stage 3 — minimal Activity/Work contract

Stage 3 starts at `62a173c7d9a875e6709bf2e0dbe0d8d7e7fa31df`.
The governing specification is `Zaratustra_Core_Specification_v0.1.md`, SHA-256
`1DDCBF9DBFD58426781F61A67A170D3CE85FCD2BA27B17549773ED3356F9428D`.

## Contract

- Activity is a continuing, addressable purpose with its own revision. It remains
  open when a particular Work succeeds.
- Work belongs to exactly one Activity and records a concrete goal, exact input
  Artifact revisions, constraints, named expected output types, and explicit absence
  of Method. Its result starts unaccepted.
- A result is linked to a named output slot by exact active Artifact revision.
  Linking does not imply acceptance. A separate authorized acceptance operation
  checks the current Work revision, exact linked result and declared output contract
  before recording `succeeded` and its grounds.
- Creation, linking and acceptance use the foundation's one transaction, current
  Decision/Grant checks, immutable revisions, audit and receipts. Read rights remain
  distinct. New subject data joins verified backup, quarantined restore and managed
  deletion without weakening Stage 2 behavior.
- Subject deletion removes earlier revision-forming receipts and content-derived
  fingerprints. It retains minimal operation ids and permitted audit, returns
  `history_unavailable` on old replay, and preserves the deletion receipt for
  exact replay under current rights.

## Proof

Use only fictional data. In one process create “Разработка Заратустры”, a specific
Work with input, expected output and no Method, then link an Artifact. Prove that
presence and linking alone leave the Work unfinished. Accept explicitly, reopen in
a new process, and read exact state and grounds. Exercise refusal on stale revision,
wrong output, missing rights and deleted source/result. Run focused tests and the
full `uv run --locked python -m tools.check --deliver` gate.

## Boundary

No Pi, DBOS, scheduler, dispatcher, automatic execution, Attempt, memory, Sleep,
legacy `.zara` import or real personal Activity is introduced.

END_OF_FILE

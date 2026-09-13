# Process creation T3 technical handback

## outcome

Version 0.15.0 implementation commit
`3c9db45f1518da617de7c72fb388c01eb69d4495` implements the approved T3 safe
future-edition change. Reviewed/rejected/pending/planned/applied stages are durable;
the current Work, prior snapshots/grounds, Core identities and immutable Pack bytes
remain exact. The new edition first has a real effect in the existing authorized
Core Result transaction that creates its applicable future Work. This is technical
candidate delivery, not owner acceptance or Direction close.

## evidence

- Final native `uv run --locked python -m tools.check`: exit 0; 120 formatted files,
  Ruff, strict mypy over 104 sources, 17/17 contracts, 360 tests in 137.90 seconds,
  wheel and sdist. Log: `_scratch/process-t3-gates-02/full-check.log`.
- Exact committed wheel SHA-256
  `2e05915bd42060753a4a9b51a95cb5a58c0c8a75623ad53c8abb6ff88566e3c3`:
  isolated Python 3.13.7 `-I`, both explicit external fixtures, tests/tools absent
  before exposure, every product module from wheel `site-packages`. Evidence:
  `_scratch/process-t3-installed-01/verification.json` and
  `product-module-paths.json` there.
- Small: reject/approval preserved Core bytes; snapshots `c6ed4d81...7299` and
  `9e1c3956...50bf` plus Pack bytes survived; one effect revision 9→10, operation
  `c32f40b6-fc48-4f63-abc3-a67d7aac4c38`; authorized replay stayed 10.
- Project: snapshots `74a0e57b...db06` and `a50c11db...fab7` plus Pack bytes
  survived; one effect revision 9→10, operation
  `c497e03b-5db1-4f5c-87bf-e3eceacaa7dc`; authorized replay stayed 10.
- Behavioral coverage includes stale/wrong/missing-rights refusals, saved review
  resume, changed-current/source/edition refusals, mutable committed lineage, two
  completed edition changes, reconstructed projected bases, and a third saved review.
  Full reproduction/manifests/receipts: `docs/process-t3/READOUT.md`.
- Required `tools.check --deliver`: exit 0; same 120/104/17 surface, 360 tests in
  123.55 seconds, artifacts and report structure. Log:
  `_scratch/process-t3-gates-03/deliver.log`.

## assumptions

The fixed Pack identity is the immutable installed runtime contract; an explicitly
reviewed compatible definition edition can govern future Work without rebinding it.
Compatibility is narrow: same identity/title/sources/capabilities, exact completed/
current nodes, next edition only. Synthetic confirmations prove technical seams only.

## cuts

No migration/Core change, current-Work reinterpretation, implicit latest, personal or
domain process approval, real research/provider use, personal installation, other
checkout/private Direction access, paid service, SQL/state rewrite, CI, GUI,
integration, push or main update. T4 synthesis and Direction review remain out of scope.

## cost

One immutable transition extension, one installed non-authoritative coordinator, one
import boundary, 15 new behavioral/probe tests, two evidence tools, version metadata
and retained native/wheel evidence; no new runtime dependency or external expense.

## manual-acceptance

pending. Test/probe local-chat confirmations are simulated, not real owner manual
acceptance. HOME must run separate fresh binding refutation before T3 can close.

## next

solmax

END_OF_FILE: RESULT.md

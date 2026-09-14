# R2 T3 correction 2 — truthful projection warning on exact receipt recovery

call: c-solmax-zaratustra-public-onboarding-r2-t3-correction-2-20260914
mode: PROBA; engineering_contract: 36
failed_candidate: 7359be8fd8f7ea87b3c1f3e3d66dadfe74dd1268
failed_candidate_parent: 32c0fedba33b790bcbb594c66ec989f8cd2e2bf0
branch: codex/public-onboarding-r2-t3-correction-2

## Bounded rule

Only binding G5 r2 F3 is corrected. The existing exact Core receipt and separately
confirmed original Result request remain the recovery authority. After reconciling
the committed receipt, both first execution and recovery call the public Core
`read_projection_status`. That read derives the expected overview from one locked
Core snapshot and compares its bytes with the selected workspace projection.

If the projection is `missing` or `stale_or_changed`, the response contains one
`rebuild_required` warning naming that state. With unchanged Core/projection state,
first response and exact replay have identical complete stdout, including warnings.
No transient exception text is retained or replayed; the journal format is unchanged.
Recovery writes nothing, does not resubmit Result, and does not implicitly rebuild.

If an explicit rebuild or another authorized action repairs the projection before
replay, the warning is absent because the observed projection is `current`; the full
receipt and remaining response fields are unchanged. Status is an observation at the
Core read, not a promise against subsequent external filesystem changes. A concurrent
repair between failed replacement and this read can also yield an empty warning.
Only the existing `ProjectionRebuildError` is reconciled as a committed Result;
other submission errors and projection-status read errors propagate, without an
invented successful answer or a second authority.

## Reproduce

From this checkout, choose a NEW scratch output directory:

```powershell
uv sync --locked
uv build --no-sources
uv run --locked python -m tools.probe_public_onboarding_r2_t3_correction --output _scratch/t3-correction-2-installed
```

The retained installation uses locked dependencies and proves product modules load
only from the built wheel. Fictional development fixtures are exposed explicitly
only by the setup harness, never packaged. Every CLI invocation runs through the
registered installed `zara` entry point in a separate isolated Python process.
The inherited F1/F2 scenarios still run. The independent F3 scenario injects
`PermissionError` only at `os.replace` for `projections/overview.md` during the first
apply, after exact synthetic context and Result confirmation. Retry runs without
that fault and confirms only the exact original Result. Missing authority uses the
real console adapter with closed input; wrong authority confirms a different request.

`fresh-cli/correction.json` retains complete first/retry outputs and SHA-256, PIDs,
prompt digests, projection status, one revision/event, original receipt recovery,
and hashes for every selected change-state file. The `projection-failure` subdirectory
also retains separate stdout/stderr/runtime files, an explicit installed CLI rebuild,
and a fresh replay after repair. Only overview bytes change at rebuild; repaired
replay is byte-stable and changes no Core revision/event.

The harness records observations before asserting exact installed F3 stdout replay,
so a failing run retains its complete counterexample.
The regression test asserts warning equality and the complete output/authority/state
contract. On the unchanged baseline, this new test fails specifically because retry
warnings are empty. API tests separately cover missing/stale projections, concurrent
confirmed recoveries, missing/wrong confirmation, repair, and propagation of file and
non-projection errors. This is execution evidence, not an independent binding review
or actual human-terminal acceptance.

## Validation and handback

```powershell
uv run --locked python -m tools.check --files src/zaratustra/process_change/__init__.py tools/probe_public_onboarding_r2_t3_correction.py tests/zaratustra/process_change/test_process_change.py tests/tools/test_public_onboarding_r2_t3_correction.py
uv run --locked python -m pytest tests/zaratustra/onboarding tests/zaratustra/process_creation tests/zaratustra/process_change tests/zaratustra/process_packs/test_work_creation.py tests/zaratustra/core/test_terminal_materials.py tests/tools/test_public_onboarding_r2_t3.py tests/tools/test_public_onboarding_r2_t3_correction.py -q
uv run --locked python -m tools.check --deliver
```

Exact baseline/after observations, implementation/report commits and actual check
counts/times belong in root RESULT.md and the executor handback. Return HOME to
solmax for separate fresh binding G5 r3 of the COMPLETE original T3. Manual acceptance
is pending. No Core/Pack/schema/dependency changes, T4+, Direction writes, integration,
push, release, personal workspace or remote action is included.

END_OF_FILE: docs/public-onboarding-r2-t3/CORRECTION-2.md

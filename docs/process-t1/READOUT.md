# Process creation T1 readout

T1 validates the proposed adapter seam on two invented mechanical inputs. It does not
complete the larger process-creation outcome.

## What now exists

Version 0.13.0 exposes a generic public Python adapter from
`zaratustra.process_packs`. `ProcessDefinition` retains an exact definition id and
edition, declared capabilities, source references, reasons, domain nodes, output keys,
and acyclic dependency edges. `ProcessSnapshot` retains that whole definition plus the
ordered exact result data for every completed occurrence. These are frozen, strict
Pydantic boundary values; extra fields and malformed identities refuse.

`evaluate_snapshot` is the read-only observation/construction operation. It replays the
entire ordered snapshot, refuses a result that is not the currently selected eligible
occurrence, and returns:

- every currently ready node and its occurrence;
- every blocked node and its exact missing dependency ids;
- one deterministic selected node in definition order for the focused Core Work;
- exact predecessor data and a canonical result digest for each ground;
- the exact definition digest and an explicit complete flag.

`record_result` mechanically appends data only to that selected occurrence.
`initial_records` and `initial_requirements` translate its first selection to existing
Core bootstrap values. `registration` installs a `DefinitionRule` under an explicit
existing `PackReference`; there is no loader, implicit latest, or new authority.

Every focused Work requirement pins five facts: adapter contract, exact definition
SHA-256, exact prior canonical snapshot SHA-256, domain node id, and numbered
occurrence. The rule accepts only canonical complete snapshot bytes after the current
result, verifies the Work metadata and immutable Pack binding, replays eligibility,
then returns the existing Core `NextWork`. Existing `propose_result`, trusted exact
confirmation, and `submit_result` remain the only state transition. A real-Core test
publishes and accepts the snapshot through public APIs and verifies the committed next
Work inherits the exact Pack binding and requirements.

## The two mechanical constructions

The small fixture has one `capture` node marked recurring. Initially occurrence 1 is
selected. After its exact `note` result, occurrence 2 is selected and grounded by the
exact occurrence-1 data/digest. The definition contains no dependency self-edge:
recurrence is a new numbered occurrence.

The project-like fixture has independent `read-request` and `read-research` nodes and
one `assemble` node that depends on both. Initially `assemble` reports both missing
dependencies. After the first result it still reports `read-research` missing. After
both results it becomes selected with these distinct retained grounds:

- `request_fact = Fictional request selects three panels`;
- `research_fact = Fictional study permits seven marks`.

Its assembly reason points to the declared request, research, and capability sources.
The fixture definitions and values live only in `tests/fixtures/process_creation`; the
installed wheel contains the generic adapter but no examples or user state.

Reproduce the traces from a clean checkout of implementation commit
`fec97a4b3f858f174a495ef42fd26b711d65fff8` using two new ignored directories:

```text
uv run --locked python -m tools.probe_process_creation --case small --output _scratch/process-t1-small-<new>
uv run --locked python -m tools.probe_process_creation --case project --output _scratch/process-t1-project-<new>
```

Both commands exited 0 in this execution. The retained accepted-snapshot SHA-256 values
were `80f0691a06ed4b2467d0708e1c16904696d7adc4d6929a2770611d7f75db9efe`
for small and `76de1183664931898c526651ed4e2d67c98a47709ca35593ad6a9da14ebe0cac`
for project.

## Refusals and the repaired integrity class

Tests cover nonexistent, self, and cyclic dependency links; incomplete output keys;
out-of-order/ungrounded results; unsupported capabilities; unknown reason sources;
noncanonical snapshots; changed definition editions; wrong Pack bindings; and changed
Work selection. These raise explicit validation or `ConstructionError` codes and the
read-only evaluator writes nothing.

The retained engineering steering note identified that an early implementation pinned
definition/node/occurrence but not the exact preceding snapshot. A later structurally
valid snapshot could therefore replace already accepted predecessor data. The finding
was reproduced from its described behavior and fixed by the prior-snapshot digest in
each Work. Two sibling replacements of the earlier `request_fact` now refuse with
`history_mismatch`; the exact-history regression and real-Core continuation test pass.
The note is retained at `docs/process-t1/STEER.md`; it is technical evidence, not owner
acceptance or the separately requested fresh verifier.

## Checks and limitations

The scoped gate passed 16 tests. The full
`uv run --locked python -m tools.check` exited 0: formatting and Ruff passed, strict
mypy passed over 94 files, all 15 import contracts were kept, all 330 tests passed, and
the 0.13.0 source distribution and wheel built. Core, CLI, migrations, released
fictional pack fixtures, authority semantics, immutable binding semantics, and user
workspaces were not changed.

This is not a universal graph scheduler. If several nodes are ready, definition order
serializes them onto one focused Work chain. The adapter has no database or alternate
event log and requires the exact canonical snapshot artifact to carry its state. A
finite definition reports completion but T1 adds no terminal Core operation. It also
does not implement discovery/draft questions (W10), manual research request/return
(W11), full activation/first-use CLI (W14), recovery/status (W15/W17), or safe edition
change (full W13/A02). Those policies remain T2/T3 work. Manual owner acceptance and
the fresh separate verification after handback are pending.

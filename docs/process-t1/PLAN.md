# Process creation T1 plan

Basis: CALL `c-solmax-zaratustra-process-t1-20260913`, contract 36 PROBA,
starting commit `2b21060fc9d52d5f9ed7931482eb4892d04cb30a`. No STOP or STEER is
present. This is an early constructor/runtime-risk test, not the complete creation,
research, activation, recovery, or edition-change flow.

## W12 / A01: smallest executable contour

Add one generic `zaratustra.process_packs.construction` adapter. Its public immutable
values describe a definition edition, domain nodes, dependency edges, required output
fields, source references/reasons, and a complete ordered result snapshot. Definition
edges must be acyclic and target named nodes. Recurrence is a node property and creates
the next numbered occurrence; it is never represented as a dependency backedge.

`evaluate_snapshot` is the read-only construction/observation API. It validates the
whole history in order, rejects incomplete result data, computes all ready and blocked
nodes, attaches exact predecessor result data and digests to a ready selection, and
chooses the first eligible node in definition order for the one focused Core Work.
Known capabilities are explicit; a definition requiring any other capability refuses.
The API writes nothing and grants no authority.

`initial_records`, `initial_requirements`, and `registration` form the public execution
seam. They translate the selected domain occurrence to existing Core `InitialRecords`,
exact `Work.executor_requirements`, and one existing `PackRegistration`. The rule sees
only the immutable Core Work and verified accepted artifact bytes. Those bytes must be
the canonical full snapshot after the current occurrence; the rule verifies definition,
edition, Work selection, ordered history, and exact data before returning one
`NextWork`. Existing trusted confirmation and `submit_result` remain the only writer.

## W13 / A02: initial provenance contour

The definition snapshot is the source of truth for graph meaning and retains its own
stable id/edition and exact SHA-256. Each reason points to declared `request`,
`research`, or `capability` sources. The fixed Core `PackReference` remains the runtime
implementation identity. Each focused Work retains the definition digest, domain node,
occurrence, and exact prior canonical snapshot digest in executor requirements. Each
accepted canonical snapshot keeps the full definition plus ordered exact data/results.
Thus definition edition, Pack
binding, and Work occurrence are distinct and cross-checked, without changing Core or
claiming safe in-place edition migration. Full review/change policy stays in T2/T3.

## Evidence and boundaries

Create two explicit JSON definitions only under `tests/fixtures/process_creation`:
one small lawful recurring process and one project-like DAG with two predecessors whose
distinct exact outputs ground a dependent node. Product tests cover both successful
constructions plus invalid targets/cycles, incomplete data/grounds, unsupported
capability, recurrence, changed/noncanonical snapshots, and Work/definition mismatch.
A development-only probe loads those fixtures through public APIs and emits the two
observable construction traces in a new `_scratch` directory.

Add the nearest fixture instructions and import-linter contracts that keep installed
product code independent of fixtures/tools and the generic adapter independent of
trusted adapters. Run focused checks during implementation, both construction probes,
then the full native check and report-aware delivery check. Update READOUT and RESULT,
commit all authorized tracked changes, and return `next: solmax` with manual acceptance
pending. Do not alter Core, migrations, released fictional fixture bytes, CLI, external
services, or user workspaces.

## Risks and explicit cuts

The accepted result is the full state snapshot, so later tooling must preserve its
canonical bytes; T1 deliberately does not add a database or alternate event log. A
definition with several ready nodes is serialized by declared node order because Core
has one focused Work chain; this is not a universal parallel scheduler. Completion has
no new Core terminal operation and is reported explicitly by the evaluator/rule rather
than silently fabricating another domain step. Discovery questions (W10), manual
request/return (W11), activation/first-use (W14), full recovery/status (W15/W17), and
safe edition change (full W13/A02) remain later work.

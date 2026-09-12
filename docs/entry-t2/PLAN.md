# Entry T2: explicit discovery and basic authorized reading

## Scope

This increment adds an installed, local catalog for explicitly selected Zaratustra
workspaces and a generic Core reader for one selected Work. It does not create a
Process, execute a Pack, open Artifact bytes, import content, or coordinate a
transfer. One Process remains stored in each workspace.

## Catalog, designation, search and relocation

The catalog is an explicit JSON file chosen by the caller. Each row has a stable
catalog id, one human-readable designation, optional aliases, and the exact
workspace, Process and selected Work identities observed when it was added.
Designations are unique under Unicode case-folding; aliases may overlap so an
aliases-only term can produce an explicit list of choices. Exact designation
resolution takes precedence over alias matches, including a different row's shared
alias, so every offered designation is actionable in the exact read and relocate
surfaces. Search is case-insensitive substring matching over designation and aliases.

A workspace below the catalog directory is stored as a relative path; any other
workspace is stored as an absolute path. No directory scanning or implicit
discovery occurs. A missing source is reported as unavailable and an identity
mismatch is reported as mismatched, independently per row. Moving a source never
silently changes its identity: `entry relocate` validates all three stored
identities at the new explicit path before atomically rewriting only that row.
The catalog is a replaceable discovery adapter, not an authority store.

Every product catalog mutation uses a stable sibling advisory-lock file. The lock
is held across the authoritative catalog load, designation/identity validation and
atomic replacement, so successful overlapping add/add and add/relocate operations
compose instead of replacing a stale snapshot. The OS releases the advisory lock
when a process closes or crashes; the harmless lock file remains so its pathname
never changes between callers. Readers do not need the lock because replacement
exposes either the complete prior JSON or the complete replacement. A source-path
resolution failure is normalized into only that row's unavailable state.

Rewrite cost: changing path/alias/search policy is confined to the catalog module
and its CLI adapter. Core workspace identity and records are unchanged.

## Shipped basic reader

Before a Process constructor or production Pack registry exists, the installed
reader is a generic Core metadata projection. It accepts one exact `ProcessQuery`
whose visible scope is exactly its selected Work, verifies the existing trusted
authorization against the current path/query/revision, and holds the managed
writer lock while it validates records and mutation history. The output contains:

- current Process and selected Work metadata, including status and authority;
- direct accepted Handoff basis as exact artifact/version/hash references;
- inherited committed Result grounds as exact references;
- an exact saved Result continuation when the selected Work is done.

The reader returns no Artifact bytes, hidden Work metadata, owner-local history,
or inferred decisions. Its byte budget covers the complete canonical JSON output.
An absent acceptance or Result is represented as absent, never as an invented
next step. A saved continuation is the immutable next-Work value accepted in that
Result; it is not a claim that the next Work is currently authorized or openable.

Pack-specific reading remains separate. This reader does not bind an unbound
Process, resolve a Pack, or weaken exact Pack version/contract/permission checks.
Immutable binding and the absence of in-place Pack migration remain unchanged.

Rewrite cost: a future subject reader can replace the CLI bootstrap choice while
the generic Core projection remains the safe metadata fallback.

## State and continuation presentation

The projection reports one of four continuation states derived from committed
records only: `selected_work_ready`, `saved_result`, `cancelled`, or `draft`.
`saved_result` includes the Result operation id, committed revision, exact complete
result grounds and the accepted next-Work value. A terminal cancelled Work has no
continuation. A ready Work is only described as selected and ready; opening its
content still requires a separate exact `ContextQuery`, compatible basis and
current rights. Draft/no-authority state remains discoverable in the catalog but
cannot pass the Core reader's metadata authorization.

Rewrite cost: richer resume guidance is isolated to this read projection. No Work
transition, acceptance rule, identity, or authority behavior changes.

## Validation and limits

Tests cover two designations, alias ambiguity, independent unavailable neighbors,
explicit relocation, source identity mismatch, query/path/revision authorization,
selected-Work scope, exact direct/inherited basis, terminal continuation and
read-only/budget behavior. Spawned-process tests force overlapping distinct adds,
same-designation adds and add/relocate, proving preserved successful deltas rather
than only valid JSON. An installed-wheel probe forces the distinct-add overlap on
new generic demo workspaces through public bootstrap/mutation APIs and retains raw
evidence under a new ignored `_scratch` directory.

The lock coordinates cooperating local product callers on filesystems that honor
the platform's advisory byte/file locks and atomic same-directory replacement.
Arbitrary manual catalog edits do not take this lock, and network/distributed
filesystem lock and rename guarantees are outside this local adapter's contract.

Later entry construction, transfer recovery/import preview, startup guidance,
model choice, memory, GUI work, real subject Processes and external chat transfer
remain out of scope.

END_OF_FILE: docs/entry-t2/PLAN.md

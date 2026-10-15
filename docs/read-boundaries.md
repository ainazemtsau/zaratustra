# Reading saved materials and executing queries

Core schema stays 18. Saved definitions and existing exact reference JSON keep
their former meaning. These interfaces are for assistants and integrations;
users continue to describe their work in conversation.

## Exact materials

`open_material(path, ref, authority, offset=0, max_bytes=16384)` reads an exact
Artifact or knowledge revision. `ref.start/end` restrict the original bytes;
`offset/next_offset` refer to that fragment. Follow continuation until it ends.
The result names its actual kind, availability, representation, fragment digest
and returned-window digest. Binary content is base64; valid UTF-8 windows respect
code point boundaries. Navigation metadata does not disclose the body or claim
it was read. Rights and dependent-source rights are checked on each read.

In native Pi, `zara_memory open` accepts the same exact address and bounds.
Revisionless open remains a knowledge-only compatibility path; a known ordinary
Artifact receives reader guidance instead of a false global absence claim.
`read_batch material_refs=[...]` reads mixed exact revisions with one byte budget;
continue with `next_material_index` and `next_offset` and the same exact refs.
This is an addressed read, not a newly saved MemorySelection. Use selectors for
indexed knowledge batches and caches. The two input forms are exclusive.

## Runtime queries

`RuntimeMemorySelector` accepts exact Activity IDs, format revisions, scopes and
explicit date/time bounds. Lower bounds are inclusive and upper bounds exclusive.
Get format revisions from `describe_structure` for the selected `work_id`; this
preserves an old Work's format pins after the Activity structure changes.

`current_activity`, `format_keys` and `use_period` are bindings in saved process
definitions. Runtime tools do not advertise them or guess their meaning from
ambient focus. Definitions still use the original `MemorySelector` and retain
their old serialized bytes and FTS expressions.

## Search coverage

Runtime `query_mode="text"` treats input as one literal phrase, including quotes,
punctuation and operator words. Advanced callers explicitly choose `"fts5"`.
Search cursors bind the original input and mode. The low-level Core FTS API stays
compatible. Search covers indexed retained knowledge; an empty match does not
prove absence of Work inputs, ordinary Artifacts or non-indexed packets. Read
already addressed inputs through their exact references.

## Provider failure

The extension retains the first context-preparation refusal through Pi's hook
error handling. Its final provider guard still prevents HTTP without context.
An unknown delivery fences automatic continuation for that same native request:
the guard rechecks its exact durable invocation and manifest. Saved effects,
reserve and the unknown outcome remain intact. A fresh owner message can explain
or explicitly continue from current state; it does not replay or accept an old
result. Restored history is not a fresh owner message.

Native localhost probes cover HTTP refusal, TCP loss, SSE error, context refusal,
saved effects and reopening. They establish interface and execution behavior;
they do not prove every future model understands every user request.

# Public read-page projections

`read_page` accepts optional `columns`, a nonempty list of unique column names
from its selected table. Omit `columns` to retain the existing full-row response
and snapshot-token behavior. Explicit `null`, empty lists, duplicates, private
tables, unknown columns and SQL expressions are rejected.

Example request payload:

```json
{"table":"attempts","columns":["id","work"],"limit":100}
```

The existing `read` permission applies. Rows contain only requested fields;
`projection: {columns: [...], full_rows: false}` identifies this response.
Pagination still returns `next_cursor`, `has_more`, `snapshot_revision` and
coverage. Continue with the same table, filters, columns and snapshot token.
The token binds the ordered columns as well as the filtered table prefix.
Updates or deletions within that prefix invalidate the token, including changes
to an unreturned field. New rows above its high watermark require a fresh page.
Each table is independently fenced; multiple table reads are not one atomic
snapshot. No source rows, old receipts or retained history are removed.

| Table | Allowed columns |
|---|---|
| heads | id, revision, kind, key, scope |
| works | id, revision, conversation, status, generation, body, reserved |
| attempts | id, work, conversation, status, generation, original_cursor, cutoff, body |
| messages | conversation, seq, event, fingerprint, raw, origin, reply |
| conversations | id, cursor |
| waits | id, revision, conversation, work, status, body |
| results | attempt, slot, fingerprint, body |
| observations | attempt, event, fingerprint, body |
| actions | id, attempt, executor, state, correlation, reserve |
| intents | kind, subject, body |
| tool_calls | attempt, native_id, command, action, receipt |
| acceptance | attempt, slot, result_hash, principal |

`Coordinator.rows(table, columns=[...], **filters)` collects all pages of that
projection. Callers that need a body must explicitly read it using the applicable
public API; a compact row is not evidence of inspecting omitted content.

## History result byte boundary

`read_history` accepts optional positive integer `byte_limit`. Omit it or pass
`null` for the existing count-bounded response. An explicit value bounds the
entire canonical UTF-8 JSON result, including `query_coverage`, before Core saves
its event and receipt. The normal receipt envelope adds its command metadata.
Existing receipts and same-command replay remain unchanged; changing this field
while reusing a command id is an identity conflict.

The bounded response contains a whole-source prefix with original material,
source refs/hashes and high watermark. `query_coverage` identifies its budget,
returned count, whether bytes withheld a source, and the first withheld source's
exact ref and canonical whole-source byte size. A withheld source keeps
`has_more: true`; the cursor remains at the last returned source, or at the input
cursor if none fit. No omitted source is skipped or counted as analysed. A truly
exhausted range retains the existing terminal cursor behavior.

If the first source cannot fit, `state: NOT_DELIVERED` and
`reason: single_source_too_large` explain the unchanged cursor. A smaller row
count cannot split that source. A budget too small even for the response metadata
is rejected before persistence. There is no automatic retry or source truncation.

The native Pi port supplies a fixed 50 KiB query boundary for `zara_read`
`read_history`. Its later whole-tool-envelope presentation guard remains separate:
escaping and decoded source-data views can expand the model-facing representation.
Core query coverage and Pi presentation coverage identify those two stages.
This does not bound all other Core reads, the total model context, calls or cost,
and does not establish analysis or a completed Sleep result.

END_OF_FILE: docs/restart/PUBLIC-READ-PROJECTIONS.md

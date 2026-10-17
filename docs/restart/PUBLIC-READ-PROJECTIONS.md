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

END_OF_FILE: docs/restart/PUBLIC-READ-PROJECTIONS.md

import type { StoragePort } from "../core/index.ts";

export const ConcurrencySchemaSQL = `
CREATE TABLE IF NOT EXISTS concurrency_meta(singleton INTEGER PRIMARY KEY CHECK(singleton=1),state_revision INTEGER NOT NULL);
INSERT OR IGNORE INTO concurrency_meta VALUES(1,0);`;
const canonicalTables = [
  "meta",
  "records",
  "revisions",
  "changes",
  "intents",
  "receipts",
  "focus",
  "claims",
  "handoffs",
  "migrations",
  "experience_rows",
  "experience_versions",
  "relations",
  "relation_history",
  "lifecycle_pins",
  "recovery_barriers",
  "lifecycle_events",
  "sleep_reviews",
  "sleep_items",
  "sleep_coverage",
];
/** Same-transaction stamp: reads, traces and derived-index rebuilds do not stale restore approvals. */
export function initializeConcurrencyState(
  storage: Pick<StoragePort, "exec" | "get">,
) {
  storage.exec(ConcurrencySchemaSQL);
  for (const table of canonicalTables) {
    if (
      !storage.get(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
        table,
      )
    )
      continue;
    for (const event of ["INSERT", "UPDATE", "DELETE"])
      storage.exec(
        `CREATE TRIGGER IF NOT EXISTS concurrency_${table}_${event.toLowerCase()} AFTER ${event} ON ${table} BEGIN UPDATE concurrency_meta SET state_revision=state_revision+1 WHERE singleton=1; END;`,
      );
  }
}

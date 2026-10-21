import type { DatabaseSync } from "node:sqlite";
import {
  ApprovalSchemaSQL,
  ExperienceSchemaSQL,
  MemorySchemaSQL,
  requireThat,
} from "../core/index.ts";

// Same literal definitions used by workspace creation/migration and recovery.
export const BaseIndexesSQL = {
  kind_activity: "CREATE INDEX kind_activity ON records(kind,activity_id);",
  claim_work: "CREATE INDEX claim_work ON claims(work_id);",
};
// Extract only named index statements from our finite, trusted schema constants.
// This is not an arbitrary SQL parser or a general schema-diff/repair service.
const definitions = [
  ...Object.values(BaseIndexesSQL),
  MemorySchemaSQL,
  ExperienceSchemaSQL,
  ApprovalSchemaSQL,
].flatMap((sql) =>
  [...sql.matchAll(/CREATE (UNIQUE )?INDEX (\w+) [^;]+;/g)].map((m) => ({
    sql: m[0],
    unique: !!m[1],
    name: m[2],
  })),
);
const normalize = (sql: string) =>
  sql.trim().replace(/;$/, "").replace(/\s+/g, " ");

export function checkIndexes(
  db: DatabaseSync,
  mode: "require" | "allow-derived-repair" | "repair" = "require",
) {
  const missing: string[] = [];
  for (const expected of definitions) {
    let actual = db
      .prepare("SELECT sql FROM sqlite_schema WHERE type='index' AND name=?")
      .get(expected.name);
    if (!actual) {
      requireThat(
        !expected.unique && mode !== "require",
        "STORE_UNAVAILABLE",
        "Required schema index/unique constraint is absent: " + expected.name,
      );
      missing.push(expected.name);
      if (mode === "allow-derived-repair") continue;
      db.exec(expected.sql);
      actual = db
        .prepare("SELECT sql FROM sqlite_schema WHERE type='index' AND name=?")
        .get(expected.name);
    }
    requireThat(
      actual && normalize(String(actual.sql)) === normalize(expected.sql),
      "STORE_UNAVAILABLE",
      "Unsupported schema index definition: " + expected.name,
    );
  }
  return missing;
}

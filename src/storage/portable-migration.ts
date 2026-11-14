import { DatabaseSync } from "node:sqlite";
import { relative, isAbsolute, resolve } from "node:path";
import { canonical, refreshMemory, requireThat } from "../core/index.ts";
import type { StoragePort } from "../core/index.ts";
import { FileCorpus, canonicalCollections } from "./corpus.ts";
import type { CorpusStatus } from "./corpus.ts";
import { createProjectionSchema } from "./projection.ts";
import { initializeConcurrencyState } from "./schema.ts";
import { validateProjection } from "./administration.ts";
import { bytesHash } from "./control.ts";

type QuarantineStorage = StoragePort & {
  home: string;
  projectRoot: string;
  enablePortableGeneration(): CorpusStatus;
  withCommandSync<T>(callback: () => T, kind?: "maintenance" | "read"): T;
};

export interface PortableMigrationReport {
  format: 1;
  before: StoragePort["workspace"];
  after: StoragePort["workspace"];
  source: "verified-quarantine-copy";
  corpus_root: string;
  exact_preserved: true;
  rebuilt_without_source_sqlite: true;
  collections: { table: string; rows: number; sha256: string }[];
}

/** The caller verifies a full cold copy before opening this isolated schema-10 copy.
 * Source workspaces and later personal cutover are outside this entry point. */
export function migratePortableWorkspace(
  storage: QuarantineStorage,
  options: { quarantineRoot: string; source: "verified-quarantine-copy" },
): PortableMigrationReport {
  const root = resolve(options.quarantineRoot);
  const inside = relative(root, resolve(storage.home));
  requireThat(
    options.source === "verified-quarantine-copy" &&
      root === resolve(storage.projectRoot) &&
      inside !== "" &&
      !inside.startsWith("..") &&
      !isAbsolute(inside),
    "PERMISSION_DENIED",
    "Portable transition requires the designated isolated project copy.",
  );
  const before = { ...storage.workspace };
  requireThat(
    before.schema_version === 10,
    "MIGRATION_REQUIRED",
    "Only schema-10 corpus copies enter the portable transition.",
  );
  const snapshots = storage.withCommandSync(
    () =>
      new Map(
        canonicalCollections()
          .filter(({ table }) =>
            storage.get(
              "SELECT name FROM sqlite_schema WHERE type='table' AND name=?",
              table,
            ),
          )
          .map(({ table }) => [
            table,
            storage.all(
              `SELECT rowid AS _rowid,* FROM "${table}" ORDER BY rowid`,
            ),
          ]),
      ),
    "read",
  );
  const state = storage.enablePortableGeneration();
  return storage.withCommandSync(() => {
    for (const [table, rows] of snapshots)
      if (table !== "meta")
        requireThat(
          canonical(
            storage.all(
              `SELECT rowid AS _rowid,* FROM "${table}" ORDER BY rowid`,
            ),
          ) === canonical(rows),
          "STORE_UNAVAILABLE",
          "Portable transition changed existing canonical rows in " +
            table +
            ".",
        );
    requireThat(
      storage.workspace.workspace_id === before.workspace_id &&
        storage.workspace.schema_version === 11 &&
        storage.workspace.epoch !== before.epoch,
      "STORE_UNAVAILABLE",
      "Portable transition identity or fence differs.",
    );
    const corpus = new FileCorpus(state.root);
    const rebuilt = new DatabaseSync(":memory:");
    try {
      createProjectionSchema(rebuilt, storage.workspace);
      corpus.restoreRows(rebuilt);
      const port: StoragePort = {
        workspace: { ...storage.workspace },
        readonly: false,
        exec: (sql) => rebuilt.exec(sql),
        get: <T>(sql: string, ...p: (string | number | null)[]) =>
          rebuilt.prepare(sql).get(...p) as T | undefined,
        all: <T>(sql: string, ...p: (string | number | null)[]) =>
          rebuilt.prepare(sql).all(...p) as T[],
        run: (sql, ...p) => {
          rebuilt.prepare(sql).run(...p);
        },
        readMaterial: (hash) => corpus.material(hash).toString("utf8"),
        readMaterialBytes: (hash) => corpus.material(hash),
      };
      initializeConcurrencyState(port);
      refreshMemory(port, true);
      rebuilt.exec("PRAGMA foreign_keys=ON");
      validateProjection(rebuilt, storage.home, true);
      for (const [table, rows] of snapshots)
        if (table !== "meta") {
          const retained =
            table === "lifecycle_pins"
              ? rows.filter(
                  (row) =>
                    JSON.parse(String((row as { json: string }).json)).kind !==
                    "source",
                )
              : rows;
          requireThat(
            canonical(
              rebuilt
                .prepare(
                  `SELECT rowid AS _rowid,* FROM "${table}" ORDER BY rowid`,
                )
                .all(),
            ) === canonical(retained),
            "STORE_UNAVAILABLE",
            "Portable corpus rebuild lost retained rows in " + table + ".",
          );
        }
      const report: PortableMigrationReport = {
        format: 1,
        before,
        after: { ...storage.workspace },
        source: options.source,
        corpus_root: state.root,
        exact_preserved: true,
        rebuilt_without_source_sqlite: true,
        collections: [...snapshots].map(([table, rows]) => ({
          table,
          rows: rows.length,
          sha256: bytesHash(canonical(rows)),
        })),
      };
      corpus.writeAuxiliary(
        "portable-migration-" + storage.workspace.epoch + ".json",
        report,
      );
      return report;
    } finally {
      corpus.close();
      rebuilt.close();
    }
  }, "read");
}

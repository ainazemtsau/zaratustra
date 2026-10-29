import { DatabaseSync } from "node:sqlite";
import { randomUUID } from "node:crypto";
import { relative, isAbsolute, resolve } from "node:path";
import type { StoragePort } from "../core/index.ts";
import { canonical, refreshMemory, requireThat } from "../core/index.ts";
import { canonicalCollections, FileCorpus } from "./corpus.ts";
import type { CorpusStatus } from "./corpus.ts";
import { createProjectionSchema } from "./projection.ts";
import { initializeConcurrencyState } from "./schema.ts";
import { validateProjection } from "./administration.ts";
import { bytesHash } from "./control.ts";

type QuarantineStorage = StoragePort & {
  home: string;
  projectRoot: string;
  enableFileAuthority(): CorpusStatus;
  corpusCheckpoint():
    | (CorpusStatus & {
        files: { path: string; sha256: string; length: number }[];
      })
    | undefined;
  withCommandSync<T>(callback: () => T, kind?: "maintenance"): T;
};
export interface MigrationReport {
  format: 1;
  migration_id: string;
  before: StoragePort["workspace"];
  after: StoragePort["workspace"];
  source: "verified-quarantine-copy";
  corpus_root: string;
  exact_preserved: true;
  rebuilt_without_source_sqlite: true;
  collections: { table: string; rows: number; sha256: string }[];
  prior_metadata: {
    meta: unknown[];
    concurrency_meta: unknown[];
    source_pins: unknown[];
  };
  files: number;
}
/** The coordinator first makes and verifies a cold copy of the entire private project.
 * This deliberately accepts an already-open QUARANTINE, never opens a source or copies
 * an active SQLite. Its caller owns the later verified control switch in real ZT.
 */
export function migrateQuarantinedStore(
  storage: QuarantineStorage,
  options: { quarantineRoot: string; source: "verified-quarantine-copy" },
): MigrationReport {
  const root = resolve(options.quarantineRoot),
    inside = relative(root, resolve(storage.home));
  requireThat(
    options.source === "verified-quarantine-copy" &&
      root === resolve(storage.projectRoot) &&
      inside !== "" &&
      !inside.startsWith("..") &&
      !isAbsolute(inside),
    "PERMISSION_DENIED",
    "Migration requires the designated isolated project copy.",
  );
  return storage.withCommandSync(() => {
    requireThat(
      storage.workspace.schema_version === 9,
      "MIGRATION_REQUIRED",
      "Only explicitly verified schema9 quarantine stores enter file migration.",
    );
    const before = { ...storage.workspace };
    const beforeCounter = storage.all(
      "SELECT rowid AS _rowid,* FROM concurrency_meta ORDER BY rowid",
    );
    const sourcePins = storage.all<{ json: string }>(
      "SELECT rowid AS _rowid,* FROM lifecycle_pins WHERE json_extract(json,'$.kind')='source' ORDER BY rowid",
    );
    const snapshots = new Map<string, unknown[]>();
    for (const { table } of canonicalCollections())
      if (
        storage.get(
          "SELECT name FROM sqlite_schema WHERE type='table' AND name=?",
          table,
        )
      )
        snapshots.set(
          table,
          storage.all(
            `SELECT rowid AS _rowid,* FROM "${table}" ORDER BY rowid`,
          ),
        );
    const state = storage.enableFileAuthority();
    for (const [table, rows] of snapshots)
      if (!["meta", "concurrency_meta"].includes(table))
        requireThat(
          canonical(
            storage.all(
              `SELECT rowid AS _rowid,* FROM "${table}" ORDER BY rowid`,
            ),
          ) === canonical(rows),
          "STORE_UNAVAILABLE",
          "Migration altered preexisting canonical rows in " +
            table +
            "; do not activate this copy.",
        );
    requireThat(
      storage.workspace.workspace_id === before.workspace_id &&
        storage.workspace.epoch === before.epoch,
      "STORE_UNAVAILABLE",
      "Migration changed workspace identity or epoch.",
    );
    const corpus = new FileCorpus(state.root),
      rebuilt = new DatabaseSync(":memory:");
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
      };
      initializeConcurrencyState(port);
      refreshMemory(port, true);
      rebuilt.exec("PRAGMA foreign_keys=ON");
      validateProjection(rebuilt, storage.home, true);
      for (const [table, rows] of snapshots)
        if (!["meta", "concurrency_meta"].includes(table)) {
          const durable =
            table === "lifecycle_pins"
              ? rows.filter(
                  (value) =>
                    JSON.parse(String((value as { json: string }).json))
                      .kind !== "source",
                )
              : rows;
          requireThat(
            canonical(
              rebuilt
                .prepare(
                  `SELECT rowid AS _rowid,* FROM "${table}" ORDER BY rowid`,
                )
                .all(),
            ) === canonical(durable),
            "STORE_UNAVAILABLE",
            "Corpus-only reconstruction lost durable rows in " + table + ".",
          );
        }
      const checkpoint = corpus.checkpoint();
      const report: MigrationReport = {
        format: 1,
        migration_id: randomUUID(),
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
        prior_metadata: {
          meta: snapshots.get("meta") ?? [],
          concurrency_meta: beforeCounter,
          source_pins: sourcePins,
        },
        files: checkpoint.files.length,
      };
      corpus.writeAuxiliary(
        "migration-" + report.migration_id + ".json",
        report,
        {
          home: storage.home,
          hashes: [
            ...new Set(
              sourcePins.flatMap(
                (row) => (JSON.parse(row.json).hashes ?? []) as string[],
              ),
            ),
          ],
        },
      );
      return report;
    } finally {
      corpus.close();
      rebuilt.close();
    }
  }, "maintenance");
}

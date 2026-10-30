import { randomUUID } from "node:crypto";
import { DatabaseSync } from "node:sqlite";
import {
  existsSync,
  mkdirSync,
  readFileSync,
  readdirSync,
  renameSync,
  unlinkSync,
  rmdirSync,
  statSync,
  lstatSync,
  realpathSync,
  watch,
  type FSWatcher,
} from "node:fs";
import { dirname, isAbsolute, join, relative, resolve } from "node:path";
import { canonical, requireThat } from "../core/contracts.ts";
import { bytesHash, durableNew, safePath } from "./control.ts";

export const CORPUS_FORMAT = 1;
export const SEMANTIC_FILE_LIMIT = 256 * 1024;
export const CORPUS_CHUNK_LIMIT = 1024 * 1024;
export const CORPUS_HARD_LIMIT = 8 * 1024 * 1024;
export const CorpusMetadataSQL = `CREATE TABLE IF NOT EXISTS corpus_entries(id TEXT NOT NULL,revision INTEGER NOT NULL,contour TEXT NOT NULL CHECK(contour IN ('active','legacy')),PRIMARY KEY(id,revision));`;
export const SleepCycleSQL = `CREATE TABLE IF NOT EXISTS sleep_cycles(id TEXT PRIMARY KEY,json TEXT NOT NULL); CREATE TABLE IF NOT EXISTS memory_candidates(id TEXT PRIMARY KEY,json TEXT NOT NULL); CREATE TABLE IF NOT EXISTS corpus_operations(operation_id TEXT PRIMARY KEY,json TEXT NOT NULL);`;
export interface CorpusCollection {
  table: string;
  keyColumns: string[];
}
const registry = new Map<string, CorpusCollection>(
  [
    ["meta", []],
    ["records", ["id"]],
    ["revisions", ["id", "revision"]],
    ["changes", ["seq"]],
    ["intents", ["request_id"]],
    ["receipts", ["request_id"]],
    ["focus", ["session_id"]],
    ["claims", ["token"]],
    ["handoffs", ["id"]],
    ["migrations", ["version"]],
    ["relations", ["id"]],
    ["relation_history", ["id", "seq"]],
    ["experience_rows", ["id"]],
    ["experience_versions", ["id", "revision"]],
    ["lifecycle_pins", ["key"]],
    ["recovery_barriers", ["work_id", "step_id"]],
    ["lifecycle_events", ["id"]],
    ["sleep_reviews", ["id"]],
    ["sleep_items", ["id"]],
    ["sleep_coverage", ["profile", "scope", "epoch"]],
    ["corpus_entries", ["id", "revision"]],
    ["sleep_cycles", ["id"]],
    ["memory_candidates", ["id"]],
    ["corpus_operations", ["operation_id"]],
  ].map(([table, keyColumns]) => [
    table as string,
    { table: table as string, keyColumns: keyColumns as string[] },
  ]),
);
export function canonicalCollections(): CorpusCollection[] {
  return [...registry.values()].map((value) => ({
    table: value.table,
    keyColumns: [...value.keyColumns],
  }));
}
export function registerCorpusCollection(collection: CorpusCollection) {
  requireThat(
    /^[a-z][a-z0-9_]*$/.test(collection.table) &&
      collection.keyColumns.every((c) => /^[a-z][a-z0-9_]*$/.test(c)),
    "VALIDATION_ERROR",
    "Invalid canonical collection registration.",
  );
  const prior = registry.get(collection.table);
  requireThat(
    !prior || canonical(prior) === canonical(collection),
    "VALIDATION_ERROR",
    "Canonical collection key changed.",
  );
  registry.set(collection.table, collection);
}
export interface CorpusStatus {
  format: 1;
  authority: "files";
  root: string;
  workspace_id: string;
  epoch: string;
  revision: number;
  schema: 10;
  complete: true;
  last_transaction: string | null;
}
export interface CorpusInventory {
  root: string;
  revision: number;
  files: { path: string; sha256: string }[];
}
interface Manifest extends Omit<CorpusStatus, "root" | "authority"> {
  collections: string[];
  collection_roots: Record<string, { sha256: string; rows: number }>;
  auxiliary?: Record<string, { sha256: string; length: number }>;
  semantic_revision?: number;
}
type Scalar = string | number | null;
type Row = Record<string, Scalar>;
interface Envelope {
  format: 1;
  collection: string;
  key: Scalar[];
  rowid: number;
  sha256: string;
  length: number;
  row?: Row;
  parts?: string[];
}
interface Mutation {
  path: string;
  before: string | null;
  after: string | null;
  before_hash: string | null;
  after_hash: string | null;
}
interface Intent {
  format: 1;
  id: string;
  before_revision: number;
  after_revision: number;
  mutations: Mutation[];
}
const q = (v: string) => '"' + v.replaceAll('"', '""') + '"';
const has = (db: DatabaseSync, table: string) =>
  !!db
    .prepare("SELECT name FROM sqlite_schema WHERE type='table' AND name=?")
    .get(table);
const rowPath = (table: string, key: unknown[]) =>
  `objects/${table}/${bytesHash(canonical(key))}.json`;
function manifestValue(value: unknown): Manifest {
  const m = value as Manifest;
  requireThat(
    m &&
      m.format === 1 &&
      m.schema === 10 &&
      m.complete === true &&
      typeof m.workspace_id === "string" &&
      typeof m.epoch === "string" &&
      Number.isSafeInteger(m.revision) &&
      m.revision >= 0 &&
      Array.isArray(m.collections) &&
      m.collection_roots &&
      typeof m.collection_roots === "object" &&
      m.collections.every((t) => registry.has(t)) &&
      (m.last_transaction === null || typeof m.last_transaction === "string"),
    "STORE_UNAVAILABLE",
    "Invalid canonical corpus manifest; preserve the corpus.",
  );
  return m;
}
/** File authority. All mutation/recovery methods require the caller's whole-command gate. */
export class FileCorpus {
  private static observers = new Map<string, Set<WeakRef<FileCorpus>>>();
  private observation: WeakRef<FileCorpus>;
  readonly root: string;
  private notifyCommitted(
    mutations: Map<string, Buffer | null>,
    revision: number,
  ) {
    for (const observer of FileCorpus.observers.get(this.root) ?? []) {
      const instance = observer.deref();
      if (!instance) {
        FileCorpus.observers.get(this.root)?.delete(observer);
        continue;
      }
      if (instance.expectedFiles.size)
        for (const [path, bytes] of mutations) {
          if (bytes === null) instance.expectedFiles.delete(path);
          else instance.expectedFiles.set(path, bytesHash(bytes));
        }
      instance.knownRevision = revision;
      instance.verifiedReads.clear();
      instance.verifiedRows.clear();
      instance.beginCommand();
    }
  }
  private installed = new Set<string>();
  private schemaVersion = -1;
  private captureDatabase?: DatabaseSync;
  private replaying = false;
  private watcher?: FSWatcher;
  private changed = new Set<string>();
  private expectedFiles = new Map<string, string>();
  private verifiedReads = new Set<string>();
  private verifiedRows = new Map<string, Row>();
  private verifyAll = false;
  private knownRevision = -1;
  private pathDirectories = new Set<string>();
  private rootChecked = false;
  beginCommand() {
    this.pathDirectories.clear();
    this.rootChecked = false;
  }
  acceptPublishedRevision(revision: number, db?: DatabaseSync) {
    if (this.knownRevision === revision) return;
    if (
      db &&
      this.expectedFiles.size &&
      this.knownRevision >= 0 &&
      has(db, "corpus_deltas")
    ) {
      const rows = db
        .prepare(
          "SELECT revision,json FROM corpus_deltas WHERE revision>? AND revision<=? ORDER BY revision",
        )
        .all(this.knownRevision, revision);
      if (rows.length === revision - this.knownRevision) {
        const changed = new Map<string, string | null>();
        let next = this.knownRevision + 1;
        for (const row of rows) {
          requireThat(
            row.revision === next++,
            "STORE_UNAVAILABLE",
            "Projection publication delta gap.",
          );
          const delta = JSON.parse(String(row.json));
          for (const [path, hash] of Object.entries(delta))
            changed.set(path, hash as string | null);
        }
        for (const [path, hash] of changed) {
          requireThat(
            hash === null
              ? !existsSync(this.path(path))
              : existsSync(this.path(path)) &&
                  bytesHash(readFileSync(this.path(path))) === hash,
            "STORE_UNAVAILABLE",
            "Canonical source differs from the committed publication delta.",
          );
          if (hash === null) this.expectedFiles.delete(path);
          else this.expectedFiles.set(path, hash);
        }
        this.knownRevision = revision;
        return;
      }
    }
    this.checkpoint();
  }
  close() {
    FileCorpus.observers.get(this.root)?.delete(this.observation);
    this.watcher?.close();
    this.watcher = undefined;
  }
  private observe() {
    if (this.watcher || !existsSync(this.root)) return;
    this.watcher = watch(this.root, { recursive: true }, (_event, name) => {
      if (!name) {
        this.verifyAll = true;
        return;
      }
      const path = String(name).replaceAll("\\", "/");
      if (
        path.startsWith(".pending/") ||
        path.startsWith(".garbage/") ||
        path.endsWith(".tmp")
      )
        return;
      this.pathDirectories.clear();
      this.rootChecked = false;
      this.changed.add(path);
    });
    this.watcher.unref();
    this.watcher.on("error", () => {
      this.verifyAll = true;
    });
  }
  assertNoDrift() {
    this.beginCommand();
    this.verifiedReads.clear();
    this.verifiedRows.clear();
    if (!this.expectedFiles.size) {
      this.checkpoint();
      return;
    }
    const expectedManifest = this.expectedFiles.get("corpus.json");
    requireThat(
      expectedManifest === bytesHash(readFileSync(this.path("corpus.json"))),
      "STORE_UNAVAILABLE",
      "Canonical manifest changed outside a managed publication; explicit reconciliation is required.",
    );
    for (const path of this.changed) {
      if (
        !this.expectedFiles.has(path) &&
        existsSync(this.path(path)) &&
        statSync(this.path(path)).isDirectory()
      )
        continue;
      const expected = this.expectedFiles.get(path);
      if (!expected && !existsSync(this.path(path))) continue;
      requireThat(
        expected &&
          existsSync(this.path(path)) &&
          bytesHash(readFileSync(this.path(path))) === expected,
        "STORE_UNAVAILABLE",
        "Canonical source changed outside a managed publication; preserve and reconcile it.",
      );
    }
    this.changed.clear();
    if (this.verifyAll) {
      this.checkpoint();
      this.verifyAll = false;
    }
  }
  private verifyObject(table: string, key: Scalar[]) {
    const path = rowPath(table, key);
    if (this.verifiedReads.has(path)) return this.verifiedRows.get(path);
    const manifest = this.manifest(),
      root = manifest.collection_roots[table];
    if (!root) return;
    const name = path.split("/").at(-1)!,
      prefix = name.slice(0, 2);
    const buckets = this.readCatalog(
      `catalog/${table}/root.json`,
      root.sha256,
    ) as Record<string, { sha256: string; rows: number }>;
    if (!buckets[prefix]) return;
    const bucket = this.readCatalog(
      `catalog/${table}/${prefix}.json`,
      buckets[prefix].sha256,
    ) as Record<string, { sha256: string; length: number }>;
    const expected = bucket[name];
    if (!expected) return;
    const bytes = readFileSync(this.path(path));
    requireThat(
      bytes.length === expected.length && bytesHash(bytes) === expected.sha256,
      "STORE_UNAVAILABLE",
      "Canonical object changed or disappeared outside a managed publication.",
    );
    const envelope = JSON.parse(bytes.toString("utf8")) as Envelope;
    const body = envelope.row
      ? Buffer.from(canonical(envelope.row))
      : Buffer.concat((envelope.parts ?? []).map((hash) => this.chunk(hash)));
    requireThat(
      envelope.collection === table &&
        canonical(envelope.key) === canonical(key) &&
        body.length === envelope.length &&
        bytesHash(body) === envelope.sha256,
      "STORE_UNAVAILABLE",
      "Canonical source envelope differs.",
    );
    const row = JSON.parse(body.toString("utf8")) as Row;
    this.verifiedReads.add(path);
    this.verifiedRows.set(path, row);
    return row;
  }
  verifyReadRows(sql: string, items: unknown[]) {
    for (const item of items) {
      if (!item || typeof item !== "object") continue;
      const row = item as Record<string, unknown>;
      if (typeof row.json === "string") {
        let value: Record<string, unknown>;
        try {
          value = JSON.parse(row.json);
        } catch {
          continue;
        }
        if (
          typeof value.id === "string" &&
          typeof value.revision === "number"
        ) {
          for (const [table, key] of [
            ["records", [value.id]],
            ["experience_rows", [value.id]],
            ["revisions", [value.id, value.revision]],
            ["experience_versions", [value.id, value.revision]],
          ] as [string, Scalar[]][]) {
            const stored = this.verifyObject(table, key);
            if (typeof stored?.json === "string") {
              const original = JSON.parse(stored.json);
              if (
                original.id === value.id &&
                original.revision === value.revision
              )
                requireThat(
                  stored.json === row.json,
                  "STORE_UNAVAILABLE",
                  "SQLite projection differs from the canonical source; rebuild before reading.",
                );
            }
          }
        }
      }
      for (const spec of registry.values())
        if (
          new RegExp('\b(?:FROM|JOIN)\s+["`]?' + spec.table + "\b", "i").test(
            sql,
          ) &&
          spec.keyColumns.every((k) => k in row)
        )
          this.verifyObject(
            spec.table,
            spec.keyColumns.map((k) => row[k] as Scalar),
          );
    }
  }
  constructor(
    root: string,
    private fault?: (point: string) => void,
  ) {
    this.root = resolve(root);
    this.observation = new WeakRef(this);
    if (!FileCorpus.observers.has(this.root))
      FileCorpus.observers.set(this.root, new Set());
    FileCorpus.observers.get(this.root)!.add(this.observation);
  }
  static exists(root: string) {
    return existsSync(join(root, "corpus.json"));
  }
  private path(path: string) {
    requireThat(
      /^[a-zA-Z0-9_.\/-]+$/.test(path) && !path.split("/").includes(".."),
      "STORE_UNAVAILABLE",
      "Invalid canonical relative path.",
    );
    const full = resolve(this.root, path),
      rel = relative(this.root, full);
    requireThat(
      rel !== "" && !rel.startsWith("..") && !isAbsolute(rel),
      "STORE_UNAVAILABLE",
      "Canonical path escaped its root.",
    );
    if (!this.rootChecked) {
      safePath(this.root, this.root, true);
      this.rootChecked = true;
      this.pathDirectories.add(this.root);
    }
    let parent = dirname(full);
    const unseen: string[] = [];
    while (parent !== this.root && !this.pathDirectories.has(parent)) {
      unseen.push(parent);
      parent = dirname(parent);
    }
    for (const directory of unseen.reverse())
      if (existsSync(directory)) {
        const info = lstatSync(directory),
          actual = relative(realpathSync(this.root), realpathSync(directory));
        requireThat(
          info.isDirectory() &&
            !info.isSymbolicLink() &&
            !actual.startsWith("..") &&
            !isAbsolute(actual),
          "PERMISSION_DENIED",
          "Canonical parent is not an owned ordinary directory.",
        );
        this.pathDirectories.add(directory);
      }
    if (existsSync(full))
      requireThat(
        !lstatSync(full).isSymbolicLink(),
        "PERMISSION_DENIED",
        "Canonical paths refuse symbolic/reparse aliases.",
      );
    return full;
  }
  private write(path: string, bytes: Uint8Array) {
    const dest = this.path(path);
    mkdirSync(dirname(dest), { recursive: true });
    safePath(this.root, dest);
    const tmp = dest + "." + randomUUID() + ".tmp";
    durableNew(tmp, bytes);
    renameSync(tmp, dest);
    if (this.expectedFiles.size) this.expectedFiles.set(path, bytesHash(bytes));
  }
  status(): CorpusStatus {
    const m = manifestValue(
      JSON.parse(readFileSync(this.path("corpus.json"), "utf8")),
    );
    return {
      format: 1,
      authority: "files",
      root: this.root,
      workspace_id: m.workspace_id,
      epoch: m.epoch,
      revision: m.revision,
      schema: 10,
      complete: true,
      last_transaction: m.last_transaction,
    };
  }
  private manifest(): Manifest {
    return manifestValue(
      JSON.parse(readFileSync(this.path("corpus.json"), "utf8")),
    );
  }
  installCapture(db: DatabaseSync) {
    if (this.captureDatabase !== db) {
      this.captureDatabase = db;
      this.installed.clear();
      this.schemaVersion = -1;
    }
    const v = Number(db.prepare("PRAGMA schema_version").get()!.schema_version);
    if (this.schemaVersion === v) return;
    db.exec(
      "CREATE TABLE IF NOT EXISTS corpus_dirty(collection TEXT NOT NULL,identity TEXT NOT NULL,PRIMARY KEY(collection,identity)); CREATE TABLE IF NOT EXISTS corpus_projection(singleton INTEGER PRIMARY KEY CHECK(singleton=1),revision INTEGER NOT NULL); INSERT OR IGNORE INTO corpus_projection VALUES(1,0); CREATE TABLE IF NOT EXISTS corpus_deltas(revision INTEGER PRIMARY KEY,json TEXT NOT NULL);",
    );
    for (const spec of registry.values()) {
      if (!has(db, spec.table)) continue;
      const newly = !this.installed.has(spec.table);
      const key = (row: string) =>
        `json_array(${spec.keyColumns.map((c) => row + "." + q(c)).join(",")})`;
      for (const event of ["INSERT", "UPDATE", "DELETE"]) {
        const ref = event === "DELETE" ? "OLD" : "NEW";
        db.exec(
          `DROP TRIGGER IF EXISTS corpus_capture_${spec.table}_${event.toLowerCase()}`,
        );
        db.exec(
          `CREATE TRIGGER IF NOT EXISTS corpus_capture2_${spec.table}_${event.toLowerCase()} AFTER ${event} ON ${q(spec.table)} BEGIN INSERT INTO corpus_dirty SELECT '${spec.table}',${key(ref)} WHERE NOT EXISTS(SELECT 1 FROM corpus_dirty WHERE collection='${spec.table}' AND identity=${key(ref)}); END;`,
        );
      }
      if (newly && FileCorpus.exists(this.root)) {
        // New lazy tables may have been populated by the creating SQL batch.
        const expr = `json_array(${spec.keyColumns.map(q).join(",")})`;
        const count = Number(
          db.prepare(`SELECT count(*) AS n FROM ${q(spec.table)}`).get()!.n,
        );
        const manifest = this.manifest();
        if (!manifest.collections.includes(spec.table) && count)
          db.exec(
            `INSERT OR IGNORE INTO corpus_dirty SELECT '${spec.table}',${expr} FROM ${q(spec.table)}`,
          );
      }
      this.installed.add(spec.table);
    }
    this.schemaVersion = Number(
      db.prepare("PRAGMA schema_version").get()!.schema_version,
    );
  }
  private addChunk(bytes: Buffer, mutations: Map<string, Buffer | null>) {
    requireThat(
      bytes.length <= CORPUS_HARD_LIMIT,
      "VALIDATION_ERROR",
      "Canonical chunk exceeds bound.",
    );
    const hash = bytesHash(bytes),
      path = "chunks/" + hash;
    if (existsSync(this.path(path)))
      requireThat(
        bytesHash(readFileSync(this.path(path))) === hash,
        "STORE_UNAVAILABLE",
        "Existing canonical chunk is corrupt.",
      );
    else mutations.set(path, bytes);
    return hash;
  }
  private envelope(
    spec: CorpusCollection,
    key: Scalar[],
    row: Row,
    mutations: Map<string, Buffer | null>,
  ) {
    if (FileCorpus.exists(this.root)) this.verifyObject(spec.table, key);
    const rowid = Number(row._corpus_rowid);
    const copy = { ...row };
    delete copy._corpus_rowid;
    const bytes = Buffer.from(canonical(copy));
    const e: Envelope = {
      format: 1,
      collection: spec.table,
      key,
      rowid,
      sha256: bytesHash(bytes),
      length: bytes.length,
    };
    if (bytes.length < SEMANTIC_FILE_LIMIT - 1024) e.row = copy;
    else {
      e.parts = [];
      for (let offset = 0; offset < bytes.length; offset += CORPUS_CHUNK_LIMIT)
        e.parts.push(
          this.addChunk(
            bytes.subarray(offset, offset + CORPUS_CHUNK_LIMIT),
            mutations,
          ),
        );
    }
    const encoded = Buffer.from(canonical(e) + "\n");
    requireThat(
      encoded.length <= SEMANTIC_FILE_LIMIT,
      "VALIDATION_ERROR",
      "Canonical object envelope exceeds bound.",
    );
    return encoded;
  }
  private retainMaterials(
    row: Row,
    home: string,
    mutations: Map<string, Buffer | null>,
  ) {
    if (typeof row.json !== "string") return;
    const hashes = new Set<string>();
    const walk = (v: unknown) => {
      if (!v || typeof v !== "object") return;
      for (const [k, x] of Object.entries(v)) {
        if (k === "hashes" && Array.isArray(x))
          for (const h of x)
            if (typeof h === "string" && /^[a-f0-9]{64}$/.test(h))
              hashes.add(h);
        if (
          ["blob_ref", "text_blob_ref"].includes(k) &&
          typeof x === "string" &&
          /^[a-f0-9]{64}$/.test(x)
        )
          hashes.add(x);
        else if (x && typeof x === "object") walk(x);
      }
    };
    walk(JSON.parse(row.json));
    for (const hash of hashes) {
      const path = `materials/${hash}.json`;
      if (existsSync(this.path(path))) {
        this.material(hash);
        continue;
      }
      const bytes = readFileSync(safePath(home, join(home, "materials", hash)));
      requireThat(
        bytesHash(bytes) === hash,
        "STORE_UNAVAILABLE",
        "Managed material hash differs before canonical retention.",
      );
      const parts: string[] = [];
      for (let offset = 0; offset < bytes.length; offset += CORPUS_CHUNK_LIMIT)
        parts.push(
          this.addChunk(
            bytes.subarray(offset, offset + CORPUS_CHUNK_LIMIT),
            mutations,
          ),
        );
      mutations.set(
        path,
        Buffer.from(
          canonical({ format: 1, sha256: hash, length: bytes.length, parts }) +
            "\n",
        ),
      );
    }
  }
  publish(db: DatabaseSync, home: string, seed = false): CorpusStatus {
    mkdirSync(this.root, { recursive: true });
    safePath(this.root, this.root, true);
    if (FileCorpus.exists(this.root)) this.assertNoDrift();
    this.installCapture(db);
    requireThat(
      !db.isTransaction,
      "STORE_BUSY",
      "Canonical publication requires the settled complete SQL command.",
    );
    const existing = FileCorpus.exists(this.root) ? this.manifest() : undefined;
    requireThat(
      seed || existing,
      "STORE_UNAVAILABLE",
      "Known canonical manifest is missing.",
    );
    const mutations = new Map<string, Buffer | null>();
    const dirty = seed
      ? [...registry.values()]
          .filter((s) => has(db, s.table))
          .flatMap((s) =>
            db
              .prepare(`SELECT rowid AS _corpus_rowid,* FROM ${q(s.table)}`)
              .all()
              .map((r) => ({
                collection: s.table,
                identity: canonical(s.keyColumns.map((c) => r[c])),
              })),
          )
      : (db.prepare("SELECT collection,identity FROM corpus_dirty").all() as {
          collection: string;
          identity: string;
        }[]);
    for (const d of dirty) {
      const spec = registry.get(String(d.collection));
      requireThat(
        spec,
        "STORE_UNAVAILABLE",
        "Unregistered canonical collection changed.",
      );
      const key = JSON.parse(String(d.identity)) as Scalar[];
      if (existing) this.verifyObject(spec.table, key);
      const row = db
        .prepare(
          `SELECT rowid AS _corpus_rowid,* FROM ${q(spec.table)}${spec.keyColumns.length ? " WHERE " + spec.keyColumns.map((c) => q(c) + " IS ?").join(" AND ") : " LIMIT 1"}`,
        )
        .get(...key) as Row | undefined;
      const path = rowPath(spec.table, key);
      const transientCandidate =
        row &&
        ((spec.table === "memory_candidates" &&
          JSON.parse(String(row.json)).pinned !== true) ||
          (spec.table === "lifecycle_pins" &&
            JSON.parse(String(row.json)).kind === "source"));
      if (row && !transientCandidate) {
        this.retainMaterials(row, home, mutations);
        const bytes = this.envelope(spec, key, row, mutations);
        if (
          !existsSync(this.path(path)) ||
          bytesHash(readFileSync(this.path(path))) !== bytesHash(bytes)
        )
          mutations.set(path, bytes);
      } else if (existsSync(this.path(path))) mutations.set(path, null);
    }
    const workspace = JSON.parse(
      String(db.prepare("SELECT json FROM meta").get()!.json),
    );
    const collections = [...registry.keys()].filter((t) => has(db, t)).sort();
    if (
      !mutations.size &&
      existing &&
      canonical(existing.collections) === canonical(collections)
    ) {
      if (dirty.length) db.exec("DELETE FROM corpus_dirty");
      db.prepare(
        "UPDATE corpus_projection SET revision=? WHERE singleton=1 AND revision<>?",
      ).run(existing.revision, existing.revision);
      return this.status();
    }
    const tx = randomUUID();
    const collection_roots = this.updateCatalogs(
      mutations,
      collections,
      existing,
    );
    const next: Manifest = {
      format: 1,
      schema: 10,
      complete: true,
      workspace_id: workspace.workspace_id,
      epoch: workspace.epoch,
      revision: (existing?.revision ?? 0) + 1,
      last_transaction: tx,
      collections,
      collection_roots,
      semantic_revision: has(db, "concurrency_meta")
        ? Number(
            db
              .prepare(
                "SELECT state_revision FROM concurrency_meta WHERE singleton=1",
              )
              .get()!.state_revision,
          )
        : (existing?.semantic_revision ?? 0) + 1,
      ...(existing?.auxiliary ? { auxiliary: existing.auxiliary } : {}),
    };
    mutations.set("corpus.json", Buffer.from(canonical(next) + "\n"));
    this.transact(tx, existing?.revision ?? 0, next.revision, mutations);
    this.knownRevision = next.revision;
    db.exec("BEGIN IMMEDIATE");
    try {
      db.prepare(
        "UPDATE corpus_projection SET revision=? WHERE singleton=1",
      ).run(next.revision);
      db.prepare("INSERT OR REPLACE INTO corpus_deltas VALUES(?,?)").run(
        next.revision,
        canonical(
          Object.fromEntries(
            [...mutations].map(([path, bytes]) => [
              path,
              bytes === null ? null : bytesHash(bytes),
            ]),
          ),
        ),
      );
      db.prepare("DELETE FROM corpus_deltas WHERE revision<=?").run(
        next.revision - 16,
      );
      db.exec("DELETE FROM corpus_dirty; COMMIT");
    } catch (error) {
      db.exec("ROLLBACK");
      throw error;
    }
    return this.status();
  }
  private readCatalog(
    path: string,
    hash: string | undefined,
  ): Record<string, unknown> {
    if (!hash) {
      requireThat(
        !existsSync(this.path(path)),
        "STORE_UNAVAILABLE",
        "Unmanifested canonical catalog exists.",
      );
      return {};
    }
    const bytes = readFileSync(this.path(path));
    requireThat(
      bytes.length <= CORPUS_HARD_LIMIT && bytesHash(bytes) === hash,
      "STORE_UNAVAILABLE",
      "Canonical membership catalog differs.",
    );
    return JSON.parse(bytes.toString("utf8"));
  }
  private updateCatalogs(
    mutations: Map<string, Buffer | null>,
    collections: string[],
    existing?: Manifest,
  ) {
    const result = { ...(existing?.collection_roots ?? {}) };
    for (const table of collections) {
      const changed = [...mutations.entries()].filter(([p]) =>
        p.startsWith(`objects/${table}/`),
      );
      if (!changed.length && result[table]) continue;
      const rootPath = `catalog/${table}/root.json`;
      const prior = result[table];
      const buckets = this.readCatalog(rootPath, prior?.sha256) as Record<
        string,
        { sha256: string; rows: number }
      >;
      for (const prefix of new Set(
        changed.map(([p]) => p.split("/").at(-1)!.slice(0, 2)),
      )) {
        const path = `catalog/${table}/${prefix}.json`;
        const entries = this.readCatalog(
          path,
          buckets[prefix]?.sha256,
        ) as Record<string, { sha256: string; length: number }>;
        for (const [p, bytes] of changed) {
          const name = p.split("/").at(-1)!;
          if (!name.startsWith(prefix)) continue;
          if (bytes)
            entries[name] = { sha256: bytesHash(bytes), length: bytes.length };
          else delete entries[name];
        }
        const count = Object.keys(entries).length;
        if (count) {
          const bytes = Buffer.from(canonical(entries) + "\n");
          requireThat(
            bytes.length <= CORPUS_CHUNK_LIMIT,
            "VALIDATION_ERROR",
            "Canonical catalog bucket exceeds shard bound.",
          );
          mutations.set(path, bytes);
          buckets[prefix] = { sha256: bytesHash(bytes), rows: count };
        } else {
          mutations.set(path, null);
          delete buckets[prefix];
        }
      }
      const bytes = Buffer.from(canonical(buckets) + "\n");
      requireThat(
        bytes.length <= SEMANTIC_FILE_LIMIT,
        "VALIDATION_ERROR",
        "Canonical collection catalog exceeds bound.",
      );
      mutations.set(rootPath, bytes);
      result[table] = {
        sha256: bytesHash(bytes),
        rows: Object.values(buckets).reduce((n, b) => n + b.rows, 0),
      };
    }
    return result;
  }
  private transact(
    id: string,
    before: number,
    after: number,
    mutations: Map<string, Buffer | null>,
  ) {
    requireThat(
      [...mutations.values()].every(
        (bytes) => bytes === null || bytes.length <= CORPUS_HARD_LIMIT,
      ),
      "VALIDATION_ERROR",
      "Canonical component exceeds the hard part limit; split before publication.",
    );
    const dir = this.path(".pending/" + id);
    mkdirSync(dir, { recursive: true });
    const intent: Intent = {
      format: 1,
      id,
      before_revision: before,
      after_revision: after,
      mutations: [],
    };
    let index = 0;
    for (const [path, bytes] of mutations) {
      const old = existsSync(this.path(path))
        ? readFileSync(this.path(path))
        : null;
      const beforeName = old ? `before-${index}` : null,
        afterName = bytes ? `after-${index}` : null;
      if (old) durableNew(join(dir, beforeName!), old);
      if (bytes) durableNew(join(dir, afterName!), bytes);
      intent.mutations.push({
        path,
        before: beforeName,
        after: afterName,
        before_hash: old ? bytesHash(old) : null,
        after_hash: bytes ? bytesHash(bytes) : null,
      });
      index++;
    }
    const descriptor = Buffer.from(canonical(intent));
    requireThat(
      descriptor.length <= CORPUS_HARD_LIMIT,
      "VALIDATION_ERROR",
      "Canonical mutation set exceeds recovery bound.",
    );
    durableNew(join(dir, "intent.json"), descriptor);
    this.fault?.("corpus_after_prepare");
    this.applyIntent(dir, intent, true);
    this.fault?.("corpus_before_marker");
    durableNew(join(dir, "COMMITTED"), bytesHash(descriptor));
    this.notifyCommitted(mutations, after);
    this.fault?.("corpus_after_marker");
    this.removeJournal(dir);
    this.fault?.("corpus_after_cleanup");
  }
  private applyIntent(dir: string, intent: Intent, forward: boolean) {
    for (const m of intent.mutations) {
      const name = forward ? m.after : m.before,
        hash = forward ? m.after_hash : m.before_hash;
      if (name === null) {
        if (existsSync(this.path(m.path))) unlinkSync(this.path(m.path));
        this.expectedFiles.delete(m.path);
        continue;
      }
      requireThat(
        /^(before|after)-\d+$/.test(name),
        "STORE_UNAVAILABLE",
        "Invalid recovery component.",
      );
      const bytes = readFileSync(safePath(this.root, join(dir, name)));
      requireThat(
        bytesHash(bytes) === hash,
        "STORE_UNAVAILABLE",
        "Recovery component hash differs.",
      );
      this.write(m.path, bytes);
      if (!this.replaying) this.fault?.("corpus_after_file");
    }
  }
  private removeJournal(dir: string) {
    // Retire atomically before deleting components. A crash during deletion must
    // never leave a replayable intention without its before/after images.
    const garbage = this.path(".garbage");
    mkdirSync(garbage, { recursive: true });
    const retired = this.path(".garbage/" + dir.split(/[\\/]/).at(-1)!);
    renameSync(dir, retired);
    if (!this.replaying) this.fault?.("corpus_after_retire");
    this.cleanRetired(retired);
  }
  private cleanRetired(dir: string) {
    for (const name of readdirSync(safePath(this.root, dir))) {
      requireThat(
        /^(before-\d+|after-\d+|intent\.json|COMMITTED)$/.test(name),
        "STORE_UNAVAILABLE",
        "Unrecognized retired recovery component.",
      );
      const path = safePath(this.root, join(dir, name));
      requireThat(
        statSync(path).isFile(),
        "STORE_UNAVAILABLE",
        "Unexpected retired recovery component.",
      );
      unlinkSync(path);
      if (!this.replaying) this.fault?.("corpus_during_cleanup");
    }
    rmdirSync(safePath(this.root, dir));
  }
  private recoverGarbage() {
    const garbage = this.path(".garbage");
    if (!existsSync(garbage)) return;
    for (const name of readdirSync(garbage)) {
      requireThat(
        /^[a-f0-9-]{36}$/.test(name),
        "STORE_UNAVAILABLE",
        "Unrecognized retired recovery folder.",
      );
      this.cleanRetired(this.path(".garbage/" + name));
    }
  }
  recoveryNeeded() {
    return [".pending", ".garbage"].some(
      (name) =>
        existsSync(this.path(name)) && readdirSync(this.path(name)).length > 0,
    );
  }
  recover(): boolean {
    this.beginCommand();
    this.replaying = true;
    try {
      this.recoverGarbage();
    } finally {
      this.replaying = false;
    }
    const pending = join(this.root, ".pending");
    if (!existsSync(pending)) return false;
    let recovered = false;
    for (const name of readdirSync(pending).sort()) {
      requireThat(
        /^[a-f0-9-]{36}$/.test(name),
        "STORE_UNAVAILABLE",
        "Unrecognized canonical recovery folder.",
      );
      const dir = this.path(".pending/" + name),
        file = join(dir, "intent.json");
      // An incomplete prepare has not changed canonical paths. Preserve it for diagnostics.
      if (!existsSync(file)) continue;
      const bytes = readFileSync(safePath(this.root, file));
      requireThat(
        bytes.length <= CORPUS_HARD_LIMIT,
        "STORE_UNAVAILABLE",
        "Recovery intent exceeds bound.",
      );
      const intent = JSON.parse(bytes.toString("utf8")) as Intent;
      requireThat(
        intent.format === 1 &&
          intent.id === name &&
          Array.isArray(intent.mutations) &&
          intent.mutations.every((m) => typeof m.path === "string"),
        "STORE_UNAVAILABLE",
        "Invalid canonical recovery intention.",
      );
      const committed = existsSync(join(dir, "COMMITTED"));
      if (committed)
        requireThat(
          readFileSync(join(dir, "COMMITTED"), "utf8") === bytesHash(bytes),
          "STORE_UNAVAILABLE",
          "Canonical commit marker differs.",
        );
      this.replaying = true;
      try {
        this.applyIntent(dir, intent, committed);
        this.notifyCommitted(
          new Map(
            intent.mutations.map((m) => {
              const name = committed ? m.after : m.before;
              return [
                m.path,
                name === null ? null : readFileSync(join(dir, name)),
              ];
            }),
          ),
          committed ? intent.after_revision : intent.before_revision,
        );
        this.removeJournal(dir);
        recovered = true;
      } finally {
        this.replaying = false;
      }
    }
    return recovered;
  }
  rows(): Map<string, { rowid: number; row: Row }[]> {
    const manifest = this.manifest(),
      result = new Map<string, { rowid: number; row: Row }[]>();
    for (const table of manifest.collections) {
      const spec = registry.get(table)!;
      const rows: { rowid: number; row: Row }[] = [];
      const root = manifest.collection_roots[table];
      requireThat(
        root,
        "STORE_UNAVAILABLE",
        "Missing canonical collection membership.",
      );
      const buckets = this.readCatalog(
        `catalog/${table}/root.json`,
        root.sha256,
      ) as Record<string, { sha256: string; rows: number }>;
      const expected = new Map<string, { sha256: string; length: number }>();
      for (const [prefix, bucket] of Object.entries(buckets)) {
        requireThat(
          /^[a-f0-9]{2}$/.test(prefix),
          "STORE_UNAVAILABLE",
          "Invalid catalog bucket.",
        );
        const entries = this.readCatalog(
          `catalog/${table}/${prefix}.json`,
          bucket.sha256,
        ) as Record<string, { sha256: string; length: number }>;
        requireThat(
          Object.keys(entries).length === bucket.rows,
          "STORE_UNAVAILABLE",
          "Canonical bucket count differs.",
        );
        for (const [name, entry] of Object.entries(entries)) {
          requireThat(
            name.startsWith(prefix) && !expected.has(name),
            "STORE_UNAVAILABLE",
            "Canonical membership duplicate.",
          );
          expected.set(name, entry);
        }
      }
      requireThat(
        expected.size === root.rows,
        "STORE_UNAVAILABLE",
        "Canonical collection count differs.",
      );
      const dir = this.path(`objects/${table}`);
      requireThat(
        !existsSync(dir) || readdirSync(dir).length === expected.size,
        "STORE_UNAVAILABLE",
        "Canonical object membership differs.",
      );
      for (const [name, entry] of [...expected.entries()].sort()) {
        requireThat(
          /^[a-f0-9]{64}\.json$/.test(name),
          "STORE_UNAVAILABLE",
          "Unknown canonical object filename.",
        );
        const raw = readFileSync(this.path("objects/" + table + "/" + name));
        requireThat(
          raw.length <= SEMANTIC_FILE_LIMIT,
          "STORE_UNAVAILABLE",
          "Canonical object exceeds limit.",
        );
        requireThat(
          raw.length === entry.length && bytesHash(raw) === entry.sha256,
          "STORE_UNAVAILABLE",
          "Canonical object differs from membership.",
        );
        const e = JSON.parse(raw.toString("utf8")) as Envelope;
        requireThat(
          e.format === 1 &&
            e.collection === table &&
            Array.isArray(e.key) &&
            Number.isSafeInteger(e.rowid) &&
            e.rowid > 0 &&
            rowPath(table, e.key).endsWith(name) &&
            e.key.length === spec.keyColumns.length,
          "STORE_UNAVAILABLE",
          "Canonical object identity differs.",
        );
        const bytes = e.row
          ? Buffer.from(canonical(e.row))
          : Buffer.concat((e.parts ?? []).map((h) => this.chunk(h)));
        requireThat(
          bytes.length === e.length && bytesHash(bytes) === e.sha256,
          "STORE_UNAVAILABLE",
          "Canonical object body hash differs.",
        );
        const row = JSON.parse(bytes.toString("utf8")) as Row;
        requireThat(
          canonical(spec.keyColumns.map((c) => row[c])) === canonical(e.key),
          "STORE_UNAVAILABLE",
          "Canonical row key differs.",
        );
        rows.push({ rowid: e.rowid, row });
      }
      result.set(table, rows);
    }
    return result;
  }
  private chunk(hash: string): Buffer {
    requireThat(
      /^[a-f0-9]{64}$/.test(hash),
      "STORE_UNAVAILABLE",
      "Invalid canonical chunk identity.",
    );
    const bytes = readFileSync(this.path("chunks/" + hash));
    requireThat(
      bytes.length <= CORPUS_HARD_LIMIT && bytesHash(bytes) === hash,
      "STORE_UNAVAILABLE",
      "Canonical chunk differs.",
    );
    return bytes;
  }
  restoreRows(db: DatabaseSync) {
    const rows = this.rows();
    for (const [table, items] of rows) {
      requireThat(
        has(db, table),
        "STORE_UNAVAILABLE",
        "Canonical table has no supported compiled schema: " + table,
      );
      const columns = new Set(
        db
          .prepare(`PRAGMA table_info(${q(table)})`)
          .all()
          .map((r) => String(r.name)),
      );
      db.exec(`DELETE FROM ${q(table)}`);
      for (const { rowid, row } of items) {
        const keys = Object.keys(row);
        requireThat(
          keys.every(
            (k) =>
              (columns.has(k) &&
                ["string", "number"].includes(typeof row[k])) ||
              (columns.has(k) && row[k] === null),
          ),
          "STORE_UNAVAILABLE",
          "Unsupported canonical row shape.",
        );
        db.prepare(
          `INSERT INTO ${q(table)}(rowid,${keys.map(q).join(",")}) VALUES(${[rowid, ...keys].map(() => "?").join(",")})`,
        ).run(rowid, ...keys.map((k) => row[k]));
      }
    }
    db.prepare("UPDATE corpus_projection SET revision=? WHERE singleton=1").run(
      this.status().revision,
    );
    if (has(db, "concurrency_meta"))
      db.prepare(
        "UPDATE concurrency_meta SET state_revision=? WHERE singleton=1",
      ).run(this.manifest().semantic_revision ?? 0);
    db.exec("DELETE FROM corpus_dirty");
  }
  material(hash: string): Buffer {
    requireThat(
      /^[a-f0-9]{64}$/.test(hash),
      "STORE_UNAVAILABLE",
      "Invalid material identity.",
    );
    const m = JSON.parse(
      readFileSync(this.path(`materials/${hash}.json`), "utf8"),
    );
    requireThat(
      m.format === 1 && m.sha256 === hash && Array.isArray(m.parts),
      "STORE_UNAVAILABLE",
      "Invalid canonical material manifest.",
    );
    const bytes = Buffer.concat(m.parts.map((h: string) => this.chunk(h)));
    requireThat(
      bytes.length === m.length && bytesHash(bytes) === hash,
      "STORE_UNAVAILABLE",
      "Canonical material differs.",
    );
    return bytes;
  }
  restoreMaterials(home: string, readOnly = false) {
    const dir = this.path("materials");
    if (!readOnly) mkdirSync(join(home, "materials"), { recursive: true });
    if (!existsSync(dir)) return;
    for (const name of readdirSync(dir)) {
      requireThat(
        /^[a-f0-9]{64}\.json$/.test(name),
        "STORE_UNAVAILABLE",
        "Invalid retained material name.",
      );
      const hash = name.slice(0, -5),
        bytes = this.material(hash),
        path = safePath(home, join(home, "materials", hash));
      if (existsSync(path))
        requireThat(
          bytesHash(readFileSync(path)) === hash,
          "STORE_UNAVAILABLE",
          "Projection material differs; preserve external data.",
        );
      else {
        requireThat(
          !readOnly,
          "INDEX_UNAVAILABLE",
          "Read-only projection is missing retained material; writable repair required.",
        );
        durableNew(path, bytes);
      }
    }
  }
  contentFingerprint() {
    const m = this.manifest();
    return bytesHash(
      canonical({
        workspace_id: m.workspace_id,
        epoch: m.epoch,
        semantic_revision: m.semantic_revision ?? m.revision,
      }),
    );
  }
  /** Durable non-SQL administrative previews are data too, not runtime cache. */
  writeAuxiliary(
    name: string,
    value: unknown,
    retainedMaterials?: { home: string; hashes: string[] },
  ) {
    requireThat(
      /^[a-z0-9-]+\.json$/.test(name),
      "VALIDATION_ERROR",
      "Invalid canonical auxiliary identity.",
    );
    this.assertNoDrift();
    const manifest = this.manifest(),
      path = "auxiliary/" + name,
      body = Buffer.from(canonical(value)),
      id = randomUUID(),
      mutations = new Map<string, Buffer | null>();
    if (retainedMaterials)
      this.retainMaterials(
        { json: canonical({ hashes: retainedMaterials.hashes }) },
        retainedMaterials.home,
        mutations,
      );
    const parts: string[] = [];
    for (let offset = 0; offset < body.length; offset += CORPUS_CHUNK_LIMIT)
      parts.push(
        this.addChunk(
          body.subarray(offset, offset + CORPUS_CHUNK_LIMIT),
          mutations,
        ),
      );
    const bytes = Buffer.from(
      canonical({
        format: "zara.aux1",
        sha256: bytesHash(body),
        length: body.length,
        parts,
      }) + "\n",
    );
    requireThat(
      bytes.length <= SEMANTIC_FILE_LIMIT,
      "VALIDATION_ERROR",
      "Administrative envelope exceeds semantic bound.",
    );
    const next: Manifest = {
      ...manifest,
      revision: manifest.revision + 1,
      last_transaction: id,
      auxiliary: {
        ...(manifest.auxiliary ?? {}),
        [path]: { sha256: bytesHash(bytes), length: bytes.length },
      },
    };
    mutations.set(path, bytes);
    mutations.set("corpus.json", Buffer.from(canonical(next) + "\n"));
    this.transact(id, manifest.revision, next.revision, mutations);
    this.knownRevision = next.revision;
    return this.status();
  }
  readAuxiliary(name: string) {
    const manifest = this.manifest(),
      path = "auxiliary/" + name,
      entry = manifest.auxiliary?.[path];
    if (!entry) return undefined;
    const bytes = readFileSync(this.path(path));
    requireThat(
      bytes.length === entry.length && bytesHash(bytes) === entry.sha256,
      "STORE_UNAVAILABLE",
      "Canonical administrative preview differs.",
    );
    const envelope = JSON.parse(bytes.toString("utf8"));
    if (envelope.format !== "zara.aux1") return envelope;
    requireThat(
      Array.isArray(envelope.parts),
      "STORE_UNAVAILABLE",
      "Invalid administrative content manifest.",
    );
    const body = Buffer.concat(
      envelope.parts.map((hash: string) => this.chunk(hash)),
    );
    requireThat(
      body.length === envelope.length && bytesHash(body) === envelope.sha256,
      "STORE_UNAVAILABLE",
      "Canonical administrative content differs.",
    );
    return JSON.parse(body.toString("utf8"));
  }
  /** Approved restore only. The caller holds the exclusive maintenance fence. */
  replaceFrom(source: FileCorpus) {
    const snapshot = source.checkpoint(),
      mutations = new Map<string, Buffer | null>();
    const walk = (dir: string) => {
      if (!existsSync(dir)) return;
      for (const entry of readdirSync(dir, { withFileTypes: true })) {
        if ([".pending", ".garbage"].includes(entry.name)) continue;
        const path = safePath(this.root, join(dir, entry.name));
        if (entry.isDirectory()) walk(path);
        else {
          requireThat(
            entry.isFile(),
            "STORE_UNAVAILABLE",
            "Restore refuses unexpected filesystem objects.",
          );
          mutations.set(relative(this.root, path).replaceAll("\\", "/"), null);
        }
      }
    };
    walk(this.root);
    for (const file of snapshot.files)
      mutations.set(file.path, readFileSync(source.path(file.path)));
    let before = 0;
    try {
      before = this.status().revision;
    } catch {
      /* Explicit restore can repair a damaged manifest. */
    }
    const manifest = source.manifest(),
      id = randomUUID();
    manifest.revision = before + 1;
    manifest.last_transaction = id;
    mutations.set("corpus.json", Buffer.from(canonical(manifest) + "\n"));
    this.transact(id, before, manifest.revision, mutations);
    this.knownRevision = manifest.revision;
    return this.status();
  }
  /** Verified inventory, not a new raw-byte snapshot. The caller must compare captured
   * bytes and exact membership before publishing. DiskStorage calls this under its
   * whole-command gate after accepting committed cross-process deltas. */
  inventory(): CorpusInventory {
    const state = this.status();
    if (!this.expectedFiles.size || this.knownRevision !== state.revision)
      this.checkpoint();
    else this.assertNoDrift();
    // Watcher notifications are asynchronous. Recheck every path before exposing
    // cached hashes; shared parents are checked once, leaves remain checked each time.
    this.beginCommand();
    for (const path of this.expectedFiles.keys()) this.path(path);
    return {
      root: this.root,
      revision: this.knownRevision,
      files: [...this.expectedFiles]
        .map(([path, sha256]) => ({ path, sha256 }))
        .sort((a, b) => a.path.localeCompare(b.path)),
    };
  }
  checkpoint(): CorpusStatus & {
    files: { path: string; sha256: string; length: number }[];
  } {
    const rows = this.rows();
    const required = new Set<string>();
    const collect = (value: unknown) => {
      if (!value || typeof value !== "object") return;
      for (const [key, item] of Object.entries(value)) {
        if (
          ["blob_ref", "text_blob_ref"].includes(key) &&
          typeof item === "string" &&
          /^[a-f0-9]{64}$/.test(item)
        )
          required.add(item);
        else if (key === "hashes" && Array.isArray(item)) {
          for (const hash of item)
            if (typeof hash === "string" && /^[a-f0-9]{64}$/.test(hash))
              required.add(hash);
        } else if (key === "json" && typeof item === "string") {
          try {
            collect(JSON.parse(item));
          } catch {
            /* An opaque legacy string is not a source address. */
          }
        } else if (item && typeof item === "object") collect(item);
      }
    };
    for (const items of rows.values())
      for (const { row } of items)
        if (typeof row.json === "string") collect(JSON.parse(row.json));
    for (const [path, expected] of Object.entries(
      this.manifest().auxiliary ?? {},
    )) {
      requireThat(
        /^auxiliary\/[a-z0-9-]+\.json$/.test(path),
        "STORE_UNAVAILABLE",
        "Invalid auxiliary canonical path.",
      );
      const bytes = readFileSync(this.path(path));
      requireThat(
        bytes.length === expected.length &&
          bytesHash(bytes) === expected.sha256,
        "STORE_UNAVAILABLE",
        "Canonical auxiliary content differs.",
      );
      collect(this.readAuxiliary(path.slice("auxiliary/".length)));
    }
    for (const hash of required) this.material(hash);
    const mat = this.path("materials");
    if (existsSync(mat))
      for (const f of readdirSync(mat)) this.material(f.slice(0, -5));
    const files: { path: string; sha256: string; length: number }[] = [];
    const walk = (dir: string) => {
      for (const e of readdirSync(dir, { withFileTypes: true })) {
        if ([".pending", ".garbage"].includes(e.name)) continue;
        const p = this.path(
          relative(this.root, join(dir, e.name)).replaceAll("\\", "/"),
        );
        if (e.isDirectory()) walk(p);
        else {
          requireThat(
            e.isFile(),
            "STORE_UNAVAILABLE",
            "Unexpected canonical filesystem object.",
          );
          const bytes = readFileSync(p);
          requireThat(
            bytes.length <= CORPUS_HARD_LIMIT,
            "STORE_UNAVAILABLE",
            "Canonical component exceeds bound.",
          );
          files.push({
            path: relative(this.root, p).replaceAll("\\", "/"),
            sha256: bytesHash(bytes),
            length: bytes.length,
          });
        }
      }
    };
    walk(this.root);
    this.expectedFiles = new Map(files.map((f) => [f.path, f.sha256]));
    this.knownRevision = this.status().revision;
    this.observe();
    return {
      ...this.status(),
      files: files.sort((a, b) => a.path.localeCompare(b.path)),
    };
  }
}

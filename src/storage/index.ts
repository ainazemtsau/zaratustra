import {
  FileCorpus,
  CorpusMetadataSQL,
  SleepCycleSQL,
  registerCorpusCollection,
} from "./corpus.ts";
import type { CorpusStatus } from "./corpus.ts";
import { createProjectionSchema } from "./projection.ts";
import { validateProjection } from "./administration.ts";
export { FileCorpus, registerCorpusCollection } from "./corpus.ts";
export type { CorpusStatus } from "./corpus.ts";
import {
  Coordination,
  type CommandKind,
  type OperationOptions,
} from "./coordination.ts";
import { verifyRuntime } from "./runtime.ts";
import { initializeConcurrencyState } from "./schema.ts";
export { Coordination } from "./coordination.ts";
export type { CommandKind, OperationOptions } from "./coordination.ts";
export { verifyRuntime } from "./runtime.ts";
export { DocumentFiles } from "./documents.ts";
import {
  activeLocation,
  adoptInitializationMaintenance,
  atomicJSON,
  readControl,
  writeControl,
  safePath,
  bytesHash,
} from "./control.ts";
export {
  activeLocation,
  readControl,
  recoverMaintenance,
  removeOwned,
  safePath,
} from "./control.ts";
import { backup, DatabaseSync } from "node:sqlite";
import { randomUUID, createHash } from "node:crypto";
import {
  closeSync,
  existsSync,
  fsyncSync,
  fstatSync,
  mkdirSync,
  openSync,
  readFileSync,
  readdirSync,
  realpathSync,
  renameSync,
  statSync,
  unlinkSync,
  writeFileSync,
} from "node:fs";
import {
  dirname,
  extname,
  isAbsolute,
  join,
  relative,
  resolve,
} from "node:path";
import type { StoragePort } from "../core/index.ts";
import {
  CoreError,
  requireThat,
  MemorySchemaSQL,
  ExperienceSchemaSQL,
  ApprovalSchemaSQL,
  LifecycleSchemaSQL,
  SleepSchemaSQL,
  refreshMemory,
  addressedRefs,
  MemoryIndexSchemaSQL,
  validateMemory,
  validateWorks,
} from "../core/index.ts";
import type { RecordRow } from "../core/index.ts";
import { extract } from "./extract.ts";
import { BaseIndexesSQL } from "./indexes.ts";

const sha = (bytes: Uint8Array) =>
  createHash("sha256").update(bytes).digest("hex");
export function within(root: string, path: string) {
  const rel = relative(root, path);
  return rel === "" || (!rel.startsWith("..") && !isAbsolute(rel));
}
// Resolve existing ancestors before creating a workspace; reject forbidden aliases before writes.
export function resolvedLocation(path: string) {
  let ancestor = resolve(path);
  while (!existsSync(ancestor)) ancestor = dirname(ancestor);
  return resolve(realpathSync(ancestor), relative(ancestor, resolve(path)));
}
function durableWrite(path: string, bytes: Uint8Array | string) {
  const fd = openSync(path, "wx");
  try {
    writeFileSync(fd, bytes);
    fsyncSync(fd);
  } finally {
    closeSync(fd);
  }
}
export class DiskStorage implements StoragePort {
  workspace!: StoragePort["workspace"];
  readonly coordination: Coordination;
  private ownsCoordination: boolean;
  private flushingMemory = false;
  private checkedPhase: object | undefined;
  readonly = false;
  private db!: DatabaseSync;
  private lockToken = randomUUID();
  private ownsLock = false;
  private closed = false;
  connectionClosed = false;
  private initializing = true;
  private administrative = false;
  readonly controlHome: string;
  readonly projectRoot: string;
  private corpus?: FileCorpus;
  private corpusMode: "create" | "require" | "legacy";
  private corpusRoot: string;
  private corpusPublishing = false;
  private projectionInstance?: string;
  private corpusFault?: (point: string) => void;
  private transientCleanupDeferred = false;
  private transientCleanupRetry = 0;
  private initializationFence?: string;
  constructor(
    public home: string,
    private migrationFault?: (point: string) => void,
    options: {
      coordination?: Coordination;
      runtimeId?: string;
      readOnly?: boolean;
      projectRoot?: string;
      corpus?: "create" | "require" | "legacy";
      corpusFault?: (point: string) => void;
    } = {},
  ) {
    verifyRuntime();
    requireThat(
      isAbsolute(home),
      "VALIDATION_ERROR",
      "Memory home must be absolute.",
    );
    this.controlHome = resolve(home);
    this.projectRoot = resolve(options.projectRoot ?? home);
    this.corpusRoot = join(this.projectRoot, "memory");
    this.corpusMode = options.corpus ?? "create";
    this.corpusFault = options.corpusFault;
    this.readonly = options.readOnly ?? false;
    const control = readControl(this.controlHome);
    this.ownsCoordination = !options.coordination;
    this.coordination =
      options.coordination ??
      new Coordination(this.controlHome, options.runtimeId, {
        expectedId: control?.coordination_id,
        create: !control || control.format === 1,
      });
    try {
      this.initializationFence = adoptInitializationMaintenance(
        this.controlHome,
        this.coordination,
      );
      this.coordination.sync("maintenance", () => {
        this.initialize(home);
        this.commandResult(() => this.maybeReclaimTransientImports());
        if (this.initializationFence) {
          requireThat(
            readControl(this.controlHome)?.format === 3,
            "STORE_UNAVAILABLE",
            "Initialization did not reach file authority; retain its fence.",
          );
          const state = this.coordination.maintenanceInfo();
          if (state.mode !== "normal")
            this.coordination.endMaintenance(this.initializationFence);
          this.initializationFence = undefined;
        }
      });
      const bootstrap = join(this.controlHome, "corpus-bootstrap.json");
      if (existsSync(bootstrap))
        this.coordination.sync("maintenance", () => {
          const intention = JSON.parse(readFileSync(bootstrap, "utf8"));
          requireThat(
            readControl(this.controlHome)?.epoch === intention.epoch,
            "STORE_UNAVAILABLE",
            "Clone control did not commit.",
          );
          unlinkSync(bootstrap);
        });
    } catch (error) {
      try {
        this.close();
      } catch {
        /* Preserve the initialization error. */
      }
      throw error;
    }
  }
  private initialize(home: string) {
    requireThat(
      isAbsolute(home),
      "VALIDATION_ERROR",
      "ZARATUSTRA_HOME must be an absolute trusted setup path.",
    );
    home = resolve(home);
    home = activeLocation(home);
    this.home = home;
    mkdirSync(home, { recursive: true });
    const manifest = join(home, "workspace.json");
    const dbPath = join(home, "zara.sqlite");
    const hadManifest = existsSync(manifest);
    const hadDb = existsSync(dbPath);
    const initialControl = readControl(this.controlHome);
    this.resumeCorpusRestore();
    if (existsSync(this.activationPath())) {
      this.resumeCorpusActivation();
      this.initializing = false;
      return;
    }
    if (FileCorpus.exists(this.corpusRoot) || initialControl?.format === 3) {
      requireThat(
        FileCorpus.exists(this.corpusRoot),
        "STORE_UNAVAILABLE",
        "Known canonical corpus is missing; never create replacement memory.",
      );
      this.corpus = new FileCorpus(this.corpusRoot, this.corpusFault);
      if (this.readonly)
        requireThat(
          !this.corpus.recoveryNeeded(),
          "INDEX_UNAVAILABLE",
          "Read-only memory requires writable filesystem recovery.",
        );
      else this.corpus.recover();
      this.openFileProjection();
      this.initializing = false;
      return;
    }
    requireThat(
      !hadDb || this.corpusMode === "legacy",
      "MIGRATION_REQUIRED",
      "Existing SQLite memory requires verified quarantine migration to the file corpus; preserve it.",
    );
    requireThat(
      !readControl(this.controlHome) || (hadManifest && hadDb),
      "STORE_UNAVAILABLE",
      "Known active memory is missing; use quarantine recovery, never initialize an empty replacement.",
    );
    requireThat(
      hadManifest === hadDb,
      "STORE_UNAVAILABLE",
      "Workspace manifest/database mismatch; preserve files and diagnose.",
    );
    try {
      // Only the one-time legacy transition takes the old lifetime lease.
      if ((readControl(this.controlHome)?.format ?? 1) < 2) {
        const lock = join(this.controlHome, "writer.lock");
        if (existsSync(lock)) {
          const owner = JSON.parse(readFileSync(lock, "utf8")) as {
            pid: number;
          };
          let alive = true;
          try {
            process.kill(owner.pid, 0);
          } catch (error) {
            alive = (error as NodeJS.ErrnoException).code !== "ESRCH";
          }
          requireThat(
            !alive,
            "STORE_BUSY",
            "Close old Pi sessions before upgrading this workspace to concurrent access.",
          );
          unlinkSync(lock);
        }
        try {
          durableWrite(
            lock,
            JSON.stringify({ pid: process.pid, token: this.lockToken }),
          );
          this.ownsLock = true;
        } catch (error) {
          if ((error as NodeJS.ErrnoException).code === "EEXIST")
            throw new CoreError(
              "STORE_BUSY",
              "Another session is upgrading this workspace; retry.",
            );
          throw error;
        }
      }
      this.db = new DatabaseSync(dbPath, { readOnly: this.readonly });
      this.db.exec("PRAGMA foreign_keys=ON; PRAGMA busy_timeout=0;");
      if (!this.readonly)
        this.db.exec("PRAGMA journal_mode=WAL; PRAGMA synchronous=FULL;");
      if (!hadDb) {
        this.workspace = {
          workspace_id: randomUUID(),
          epoch: randomUUID(),
          schema_version: 8,
        };
        this.db.exec(`BEGIN IMMEDIATE;
          CREATE TABLE meta(json TEXT NOT NULL);
          CREATE TABLE records(id TEXT PRIMARY KEY,kind TEXT NOT NULL,activity_id TEXT,json TEXT NOT NULL);
          ${BaseIndexesSQL.kind_activity}
          CREATE TABLE revisions(id TEXT NOT NULL,revision INTEGER NOT NULL,json TEXT NOT NULL,PRIMARY KEY(id,revision));
          CREATE TABLE changes(seq INTEGER PRIMARY KEY,json TEXT NOT NULL);
          CREATE TABLE intents(request_id TEXT PRIMARY KEY,hash TEXT NOT NULL,json TEXT NOT NULL);
          CREATE TABLE receipts(request_id TEXT PRIMARY KEY,hash TEXT NOT NULL,json TEXT NOT NULL,bindings TEXT NOT NULL);
          CREATE TABLE focus(session_id TEXT PRIMARY KEY,json TEXT NOT NULL);
          CREATE TABLE claims(token TEXT PRIMARY KEY,work_id TEXT NOT NULL,json TEXT NOT NULL);
          ${BaseIndexesSQL.claim_work}
          CREATE TABLE handoffs(id TEXT PRIMARY KEY,json TEXT NOT NULL);
          CREATE TABLE migrations(version INTEGER PRIMARY KEY,json TEXT NOT NULL);
          ${MemorySchemaSQL}
          ${ExperienceSchemaSQL}
          ${ApprovalSchemaSQL}
          ${LifecycleSchemaSQL}
          ${SleepSchemaSQL}
          PRAGMA user_version=8;`);
        this.db
          .prepare("INSERT INTO meta(json) VALUES(?)")
          .run(JSON.stringify(this.workspace));
        this.db.exec("COMMIT");
        durableWrite(manifest, JSON.stringify(this.workspace, null, 2));
      } else {
        this.workspace = JSON.parse(
          readFileSync(manifest, "utf8"),
        ) as StoragePort["workspace"];
        const meta = this.get<{ json: string }>("SELECT json FROM meta");
        const version = this.get<{ user_version: number }>(
          "PRAGMA user_version",
        )?.user_version;
        if (version === 9 && this.workspace.schema_version === 8) {
          const receipt = this.get<{ json: string }>(
            "SELECT json FROM migrations WHERE version=9",
          );
          const migration = receipt ? JSON.parse(receipt.json) : null;
          requireThat(
            migration &&
              migration.before === JSON.stringify(this.workspace) &&
              migration.after === meta?.json,
            "STORE_UNAVAILABLE",
            "Unrecognized interrupted concurrent migration; preserve store.",
          );
          this.replaceManifest(meta!.json);
          this.workspace = JSON.parse(meta!.json);
        }
        if (
          version === 8 &&
          this.workspace.schema_version === 7 &&
          !this.readonly
        ) {
          const receipt = this.get<{ json: string }>(
            "SELECT json FROM migrations WHERE version=8",
          );
          const migration = receipt ? JSON.parse(receipt.json) : null;
          requireThat(
            migration &&
              migration.before === JSON.stringify(this.workspace) &&
              migration.after === meta?.json,
            "STORE_UNAVAILABLE",
            "Unrecognized interrupted document migration; preserve store.",
          );
          this.replaceManifest(meta!.json);
          this.workspace = JSON.parse(meta!.json);
        }
        if (
          version === 7 &&
          this.workspace.schema_version === 6 &&
          !this.readonly
        ) {
          const receipt = this.get<{ json: string }>(
            "SELECT json FROM migrations WHERE version=7",
          );
          const migration = receipt ? JSON.parse(receipt.json) : null;
          requireThat(
            migration &&
              migration.before === JSON.stringify(this.workspace) &&
              migration.after === meta?.json,
            "STORE_UNAVAILABLE",
            "Unrecognized interrupted Sleep migration; preserve store.",
          );
          this.replaceManifest(meta!.json);
          this.workspace = JSON.parse(meta!.json);
        }
        if (
          version === 6 &&
          this.workspace.schema_version === 5 &&
          !this.readonly
        ) {
          const receipt = this.get<{ json: string }>(
            "SELECT json FROM migrations WHERE version=6",
          );
          const m = receipt ? JSON.parse(receipt.json) : null;
          requireThat(
            m &&
              m.before === JSON.stringify(this.workspace) &&
              m.after === meta?.json,
            "STORE_UNAVAILABLE",
            "Unrecognized lifecycle migration; preserve store.",
          );
          this.replaceManifest(meta!.json);
          this.workspace = JSON.parse(meta!.json);
        }
        if (
          version === 5 &&
          this.workspace.schema_version === 4 &&
          !this.readonly
        ) {
          const receipt = this.get<{ json: string }>(
            "SELECT json FROM migrations WHERE version=5",
          );
          const m = receipt ? JSON.parse(receipt.json) : null;
          requireThat(
            m &&
              m.before === JSON.stringify(this.workspace) &&
              m.after === meta?.json,
            "STORE_UNAVAILABLE",
            "Unrecognized interrupted approval migration; preserve store.",
          );
          this.replaceManifest(meta!.json);
          this.workspace = JSON.parse(meta!.json);
        }
        // A crash after the schema transaction may precede the manifest rename.
        // Only our exact retained migration receipt permits this narrow repair.
        if (
          version === 2 &&
          this.workspace.schema_version === 1 &&
          !this.readonly
        ) {
          const receipt = this.get<{ json: string }>(
            "SELECT json FROM migrations WHERE version=2",
          );
          const m = receipt ? JSON.parse(receipt.json) : null;
          requireThat(
            m &&
              m.before === JSON.stringify(this.workspace) &&
              m.after === meta?.json,
            "STORE_UNAVAILABLE",
            "Unrecognized interrupted migration; preserve the store.",
          );
          this.replaceManifest(meta!.json);
          this.workspace = JSON.parse(meta!.json);
        }
        if (
          version === 4 &&
          this.workspace.schema_version === 3 &&
          !this.readonly
        ) {
          const receipt = this.get<{ json: string }>(
            "SELECT json FROM migrations WHERE version=4",
          );
          const m = receipt ? JSON.parse(receipt.json) : null;
          requireThat(
            m &&
              m.before === JSON.stringify(this.workspace) &&
              m.after === meta?.json,
            "STORE_UNAVAILABLE",
            "Unrecognized interrupted experience migration; preserve the store.",
          );
          this.replaceManifest(meta!.json);
          this.workspace = JSON.parse(meta!.json);
        }
        if (
          version === 3 &&
          this.workspace.schema_version === 2 &&
          !this.readonly
        ) {
          const receipt = this.get<{ json: string }>(
            "SELECT json FROM migrations WHERE version=3",
          );
          const m = receipt ? JSON.parse(receipt.json) : null;
          requireThat(
            m &&
              m.before === JSON.stringify(this.workspace) &&
              m.after === meta?.json,
            "STORE_UNAVAILABLE",
            "Unrecognized interrupted memory migration; preserve the store.",
          );
          this.replaceManifest(meta!.json);
          this.workspace = JSON.parse(meta!.json);
        }
        requireThat(
          meta &&
            meta.json === JSON.stringify(this.workspace) &&
            (this.workspace.schema_version === 1 ||
              this.workspace.schema_version === 2 ||
              this.workspace.schema_version === 3 ||
              this.workspace.schema_version === 4 ||
              this.workspace.schema_version === 5 ||
              this.workspace.schema_version === 6 ||
              this.workspace.schema_version === 7 ||
              this.workspace.schema_version === 8 ||
              this.workspace.schema_version === 9) &&
            version === this.workspace.schema_version,
          "STORE_UNAVAILABLE",
          "Unknown schema or workspace identity mismatch; no replacement store will be created.",
        );
      }
      if (!hadDb || this.workspace.schema_version < 9) {
        requireThat(
          this.get<{ integrity_check: string }>("PRAGMA integrity_check")
            ?.integrity_check === "ok",
          "STORE_UNAVAILABLE",
          "SQLite integrity check failed.",
        );
      } else {
        // Validated schema-9 generations do not re-scan every historical page for
        // each new client. Creation/migration/restore and explicit doctor retain
        // full integrity checks; ordinary queries still fail closed on IO/corruption.
        const index = this.get<{ format: number }>(
          "SELECT format FROM memory_index_meta WHERE singleton=1",
        );
        requireThat(
          [1, 2].includes(index?.format ?? 0),
          "STORE_UNAVAILABLE",
          "Unknown access-index format; preserve this store for recovery.",
        );
      }
      if (this.workspace.schema_version === 1) this.migrate();
      if (this.workspace.schema_version === 2) this.migrateMemory();
      if (this.workspace.schema_version === 3) this.migrateMemory(4);
      if (this.workspace.schema_version === 4) this.migrateMemory(5);
      if (this.workspace.schema_version === 5) this.migrateMemory(6);
      if (this.workspace.schema_version === 6) this.migrateMemory(7);
      if (this.workspace.schema_version === 7) this.migrateMemory(8);
      if (this.workspace.schema_version === 8) this.migrateMemory(9);
      const control = readControl(this.controlHome);
      if (control)
        requireThat(
          control.workspace_id === this.workspace.workspace_id &&
            control.epoch === this.workspace.epoch,
          "STORE_UNAVAILABLE",
          "Active control identity mismatch; no replacement.",
        );
      if (!control || control.format < 2)
        writeControl(this.controlHome, {
          ...(control ?? { generation: ".", restoration: null }),
          format: 2,
          coordination_id: this.coordination.identity,
          coordination_protocol: 1,
          workspace_id: this.workspace.workspace_id,
          epoch: this.workspace.epoch,
        });
      if (this.ownsLock) {
        const legacy = join(this.controlHome, "writer.lock");
        if (
          existsSync(legacy) &&
          JSON.parse(readFileSync(legacy, "utf8")).token === this.lockToken
        )
          unlinkSync(legacy);
        this.ownsLock = false;
      }
      if (!hadDb && this.corpusMode !== "legacy") this.activateCorpus(false);
      this.initializing = false;
      if (!this.readonly) {
        mkdirSync(join(home, "materials"), { recursive: true });
        mkdirSync(join(home, "staging"), { recursive: true });
      }
      for (const name of [
        "importFile",
        "readBlob",
        "readMaterial",
        "doctor",
        "pinSource",
        "unpinSource",
      ] as const) {
        const original = this[name].bind(this) as (...args: never[]) => unknown;
        Object.defineProperty(this, name, {
          value: (...args: never[]) =>
            this.withCommandSync(() => original(...args)),
          configurable: true,
        });
      }
    } catch (e) {
      try {
        this.db?.close();
        this.connectionClosed = true;
      } catch {
        /* Preserve original failure. */
      }
      throw e;
    }
  }
  registerCanonicalCollection(table: string, keyColumns: string[]) {
    return this.withCommandSync(() => {
      registerCorpusCollection({ table, keyColumns });
      if (this.corpus && !this.readonly) this.corpus.installCapture(this.db);
    });
  }
  runtimeGitExclusions(projectRoot = this.projectRoot): string[] {
    const roots = new Set([this.controlHome, this.home]);
    const generations = join(this.controlHome, "generations");
    if (existsSync(generations))
      for (const name of readdirSync(generations))
        if (/^[a-f0-9-]{36}$/.test(name)) roots.add(join(generations, name));
    const paths: string[] = [];
    const add = (path: string) => {
      if (within(projectRoot, path) && resolve(path) !== resolve(projectRoot))
        paths.push(
          relative(projectRoot, path).replaceAll("\\", "/") +
            ([
              "runtimes",
              "staging",
              "materials",
              "administration",
              ".pending",
              ".garbage",
              "transient-imports",
            ].includes(path.split(/[\\/]/).at(-1)!)
              ? "/"
              : ""),
        );
    };
    for (const root of roots) {
      for (const name of [
        "active.json",
        "workspace.json",
        "projection.instance",
        "coordination.sqlite",
        "coordination.sqlite-journal",
        "coordination.sqlite-wal",
        "coordination.sqlite-shm",
        "writer.lock",
        "corpus-activation.json",
        "corpus-restore.json",
        "transient-materials.json",
        "corpus-bootstrap.json",
        "transient-imports",
        "runtimes",
        "staging",
        "materials",
        "administration",
      ])
        add(join(root, name));
      if (existsSync(root))
        for (const name of readdirSync(root))
          if (
            /^(zara\.sqlite(?:-wal|-shm|\.preserved-[a-f0-9-]+)?|(?:pre-[a-z0-9-]+|projection-build-[a-f0-9-]+)\.sqlite(?:-wal|-shm)?)$/.test(
              name,
            )
          )
            add(join(root, name));
    }
    add(join(this.corpusRoot, ".pending"));
    add(join(this.corpusRoot, ".garbage"));
    return [...new Set(paths)].sort();
  }
  corpusStatus(): CorpusStatus | undefined {
    return this.withCommandSync(() => this.corpus?.status(), "read");
  }
  corpusCheckpoint() {
    return this.withCommandSync(() => this.corpus?.checkpoint(), "read");
  }
  private projectionPath() {
    return join(this.home, "zara.sqlite");
  }
  private projectionTokenPath() {
    return join(this.home, "projection.instance");
  }
  private openFileProjection() {
    try {
      this.db?.close();
    } catch {
      /* A stale projection handle is disposable. */
    }
    let state = this.corpus!.status();
    this.workspace = {
      workspace_id: state.workspace_id,
      epoch: state.epoch,
      schema_version: 10,
    };
    const control = readControl(this.controlHome);
    requireThat(
      !control ||
        (control.workspace_id === state.workspace_id &&
          control.epoch === state.epoch),
      "STORE_UNAVAILABLE",
      "Corpus/control identity differs; preserve both.",
    );
    this.corpus!.checkpoint();
    let rebuild = !existsSync(this.projectionPath());
    if (!rebuild)
      try {
        this.db = new DatabaseSync(this.projectionPath(), {
          readOnly: this.readonly,
        });
        const value = this.db
          .prepare("SELECT revision FROM corpus_projection WHERE singleton=1")
          .get();
        const projectionWorkspace = JSON.parse(
          String(this.db.prepare("SELECT json FROM meta").get()?.json),
        );
        rebuild =
          JSON.stringify(projectionWorkspace) !==
            JSON.stringify(this.workspace) ||
          !!this.db.prepare("SELECT 1 FROM corpus_dirty LIMIT 1").get() ||
          Number(value?.revision) !== state.revision ||
          Number(this.db.prepare("PRAGMA user_version").get()!.user_version) !==
            10;
      } catch {
        rebuild = true;
      }
    if (rebuild) {
      requireThat(
        !this.readonly,
        "INDEX_UNAVAILABLE",
        "File corpus requires a writable projection rebuild.",
      );
      this.rebuildFileProjection();
    } else this.configureFileConnection();
    this.corpus!.restoreMaterials(this.home, this.readonly);
    this.rehydratePortableOperations();
    if (
      !control ||
      existsSync(join(this.controlHome, "corpus-bootstrap.json"))
    ) {
      requireThat(
        !this.readonly,
        "INDEX_UNAVAILABLE",
        "Fresh clone requires a writable reconciliation epoch.",
      );
      this.initializeCloneEpoch();
      state = this.corpus!.status();
    }
    if (
      !existsSync(join(this.home, "workspace.json")) ||
      readFileSync(join(this.home, "workspace.json"), "utf8") !==
        JSON.stringify(this.workspace, null, 2)
    ) {
      requireThat(
        !this.readonly,
        "INDEX_UNAVAILABLE",
        "Projection metadata requires repair.",
      );
      atomicJSON(join(this.home, "workspace.json"), this.workspace);
    }
    if (!control || control.format !== 3) {
      requireThat(
        !this.readonly,
        "INDEX_UNAVAILABLE",
        "File control requires a writable transition.",
      );
      writeControl(this.controlHome, {
        ...(control ?? { generation: ".", restoration: null }),
        format: 3,
        corpus_root: this.corpusRoot,
        coordination_id: this.coordination.identity,
        coordination_protocol: 1,
        workspace_id: state.workspace_id,
        epoch: state.epoch,
      });
    }
    const bootstrap = join(this.controlHome, "corpus-bootstrap.json");
    if (existsSync(bootstrap)) {
      const intention = JSON.parse(readFileSync(bootstrap, "utf8"));
      requireThat(
        intention.epoch === state.epoch &&
          intention.workspace_id === state.workspace_id,
        "STORE_UNAVAILABLE",
        "Clone completion does not match its descriptor.",
      );
    }
    if (existsSync(this.projectionTokenPath()))
      this.projectionInstance = readFileSync(
        this.projectionTokenPath(),
        "utf8",
      );
  }
  private configureFileConnection() {
    this.connectionClosed = false;
    this.db.exec("PRAGMA foreign_keys=ON; PRAGMA busy_timeout=0;");
    if (!this.readonly) {
      this.db.exec("PRAGMA journal_mode=WAL; PRAGMA synchronous=FULL;");
      this.corpus!.installCapture(this.db);
    }
  }
  private rebuildFileProjection() {
    requireThat(
      this.corpus && !this.readonly,
      "INDEX_UNAVAILABLE",
      "A writable file projection is required.",
    );
    const state = this.corpus.status();
    this.workspace = {
      workspace_id: state.workspace_id,
      epoch: state.epoch,
      schema_version: 10,
    };
    const path = join(
      this.home,
      "projection-build-" + randomUUID() + ".sqlite",
    );
    const next = new DatabaseSync(path);
    try {
      createProjectionSchema(next, this.workspace);
      this.corpus.restoreRows(next);
      const projection: StoragePort = {
        workspace: this.workspace,
        readonly: false,
        exec: (sql) => next.exec(sql),
        get: <T>(sql: string, ...p: (string | number | null)[]) =>
          next.prepare(sql).get(...p) as T | undefined,
        all: <T>(sql: string, ...p: (string | number | null)[]) =>
          next.prepare(sql).all(...p) as T[],
        run: (sql, ...p) => {
          next.prepare(sql).run(...p);
        },
        readMaterial: (hash) => this.corpus!.material(hash).toString("utf8"),
      };
      initializeConcurrencyState(projection);
      refreshMemory(projection, true);
      next.exec("DELETE FROM corpus_dirty; PRAGMA foreign_keys=ON;");
      requireThat(
        next.prepare("PRAGMA integrity_check").get()!.integrity_check ===
          "ok" && next.prepare("PRAGMA foreign_key_check").all().length === 0,
        "STORE_UNAVAILABLE",
        "Canonical projection rebuild failed integrity.",
      );
      validateProjection(next, this.home, false);
      next
        .prepare("UPDATE corpus_projection SET revision=? WHERE singleton=1")
        .run(state.revision);
    } finally {
      next.close();
    }
    try {
      this.db?.close();
    } catch {
      /* Corrupt projection is not authority. */
    }
    const suffix = ".preserved-" + randomUUID();
    for (const ext of ["", "-wal", "-shm"]) {
      const old = this.projectionPath() + ext;
      if (existsSync(old))
        renameSync(safePath(this.home, old), safePath(this.home, old + suffix));
    }
    renameSync(
      safePath(this.home, path),
      safePath(this.home, this.projectionPath()),
    );
    this.db = new DatabaseSync(this.projectionPath());
    this.configureFileConnection();
    const token = randomUUID();
    atomicJSON(this.projectionTokenPath(), { token });
    this.projectionInstance = readFileSync(this.projectionTokenPath(), "utf8");
  }
  private ensureFileProjection() {
    if (this.readonly)
      requireThat(
        !this.corpus!.recoveryNeeded(),
        "INDEX_UNAVAILABLE",
        "Read-only memory requires writable filesystem recovery.",
      );
    else this.corpus!.recover();
    const token = existsSync(this.projectionTokenPath())
      ? readFileSync(this.projectionTokenPath(), "utf8")
      : undefined;
    if (token !== this.projectionInstance) {
      try {
        this.db.close();
      } catch {
        /* Reopen known replacement. */
      }
      this.db = new DatabaseSync(this.projectionPath(), {
        readOnly: this.readonly,
      });
      this.configureFileConnection();
      this.projectionInstance = token;
    }
    const revision = Number(
      this.db
        .prepare("SELECT revision FROM corpus_projection WHERE singleton=1")
        .get()?.revision,
    );
    const state = this.corpus!.status();
    const projectionWorkspace = JSON.parse(
      String(this.db.prepare("SELECT json FROM meta").get()?.json),
    );
    if (
      !!this.db.prepare("SELECT 1 FROM corpus_dirty LIMIT 1").get() ||
      revision !== state.revision ||
      JSON.stringify(projectionWorkspace) !==
        JSON.stringify({
          workspace_id: state.workspace_id,
          epoch: state.epoch,
          schema_version: 10,
        })
    ) {
      requireThat(
        !this.readonly,
        "INDEX_UNAVAILABLE",
        "File projection is stale.",
      );
      this.rebuildFileProjection();
    }
    this.corpus!.acceptPublishedRevision(state.revision, this.db);
    this.corpus!.assertNoDrift();
  }
  private rehydratePortableOperations() {
    if (!this.corpus || !this.db || this.connectionClosed) return;
    this.coordination.importMissingUnknown(
      this.db
        .prepare("SELECT json FROM corpus_operations")
        .all()
        .map((row) => JSON.parse(String(row.json))),
    );
  }
  private captureRuntimeOperations() {
    this.rehydratePortableOperations();
    const pending = this.coordination.pending();
    const ids = new Set(pending.map((o) => o.operation_id));
    for (const old of this.db
      .prepare("SELECT operation_id FROM corpus_operations")
      .all())
      if (!ids.has(String(old.operation_id)))
        this.db
          .prepare("DELETE FROM corpus_operations WHERE operation_id=?")
          .run(String(old.operation_id));
    for (const op of pending) {
      const json = JSON.stringify(op);
      const prior = this.db
        .prepare("SELECT json FROM corpus_operations WHERE operation_id=?")
        .get(op.operation_id);
      if (prior?.json !== json)
        this.db
          .prepare(
            "INSERT INTO corpus_operations VALUES(?,?) ON CONFLICT(operation_id) DO UPDATE SET json=excluded.json",
          )
          .run(op.operation_id, json);
    }
  }
  private initializeCloneEpoch() {
    const descriptor = join(this.controlHome, "corpus-bootstrap.json");
    let intention: {
      format: number;
      kind: string;
      coordination_id: string;
      corpus_root: string;
      workspace_id: string;
      previous_epoch: string;
      epoch: string;
      restoration_id: string;
    };
    if (existsSync(descriptor))
      intention = JSON.parse(readFileSync(descriptor, "utf8"));
    else {
      intention = {
        format: 1,
        kind: "corpus-clone",
        coordination_id: this.coordination.identity,
        corpus_root: this.corpusRoot,
        workspace_id: this.workspace.workspace_id,
        previous_epoch: this.workspace.epoch,
        epoch: randomUUID(),
        restoration_id: "clone-" + randomUUID(),
      };
      atomicJSON(descriptor, intention);
    }
    requireThat(
      intention.format === 1 &&
        intention.kind === "corpus-clone" &&
        intention.coordination_id === this.coordination.identity &&
        intention.corpus_root === this.corpusRoot &&
        intention.workspace_id === this.workspace.workspace_id &&
        [intention.previous_epoch, intention.epoch].includes(
          this.workspace.epoch,
        ),
      "STORE_UNAVAILABLE",
      "Clone descriptor and canonical identity disagree.",
    );
    const oldEpoch = intention.previous_epoch,
      epoch = intention.epoch,
      restoration_id = intention.restoration_id;
    const token = this.coordination.beginMaintenance("corpus-clone", oldEpoch);
    this.initializationFence = token;
    this.corpusFault?.("corpus_clone_fenced");
    try {
      this.coordination.exclusiveMaintenance(token);
      const pending = this.db
        .prepare("SELECT json FROM corpus_operations")
        .all()
        .map((r) => ({
          ...JSON.parse(String(r.json)),
          status: "unknown" as const,
        }));
      this.coordination.importUnknown(pending);
      if (this.workspace.epoch === epoch) return;
      this.db.exec("BEGIN IMMEDIATE");
      try {
        this.workspace = { ...this.workspace, epoch };
        this.db
          .prepare("UPDATE meta SET json=?")
          .run(JSON.stringify(this.workspace));
        for (const row of this.db
          .prepare("SELECT json FROM records WHERE kind='work'")
          .all()) {
          const work = JSON.parse(String(row.json));
          if (work.storage === "tombstone") continue;
          for (const step of [
            "",
            ...(work.data.steps ?? []).map(
              (s: { step_id: string }) => s.step_id,
            ),
          ])
            this.db
              .prepare(
                "INSERT INTO recovery_barriers VALUES(?,?,?) ON CONFLICT(work_id,step_id) DO UPDATE SET json=excluded.json",
              )
              .run(
                work.id,
                step,
                JSON.stringify({
                  epoch,
                  restoration_id,
                  status: "required",
                  reason:
                    "Cloned corpus can predate external effects; inspect current-world postconditions before effectful continuation.",
                }),
              );
        }
        this.db.prepare("INSERT INTO lifecycle_events VALUES(?,?)").run(
          restoration_id,
          JSON.stringify({
            kind: "restoration",
            epoch,
            previous_epoch: oldEpoch,
            barrier:
              "all restored Work and steps; imported pending operations unknown",
            authority: "historical claims/approvals are not runnable",
          }),
        );
        this.db.exec("COMMIT");
      } catch (error) {
        this.db.exec("ROLLBACK");
        throw error;
      }
      this.captureRuntimeOperations();
      this.corpus!.publish(this.db, this.home);
    } finally {
      // The fence remains through local control publication; constructor completes it.
    }
  }
  /** Explicit operator migration entry. Call only on an isolated, verified quarantine copy. */
  enableFileAuthority() {
    return this.coordination.sync("maintenance", () =>
      this.activateCorpus(true),
    );
  }
  private resumeCorpusRestore() {
    const path = join(this.controlHome, "corpus-restore.json");
    if (!existsSync(path)) return;
    requireThat(
      !this.readonly,
      "STORE_UNAVAILABLE",
      "Interrupted canonical restore requires recovery.",
    );
    const intention = JSON.parse(readFileSync(path, "utf8"));
    requireThat(
      intention.format === 1 &&
        intention.corpus_root === this.corpusRoot &&
        intention.previous_epoch &&
        intention.next_control?.format === 3,
      "STORE_UNAVAILABLE",
      "Unknown canonical restore intention.",
    );
    const corpus = new FileCorpus(this.corpusRoot);
    try {
      corpus.recover();
      const state = corpus.status();
      if (state.epoch === intention.next_control.epoch)
        writeControl(this.controlHome, intention.next_control);
      else
        requireThat(
          state.epoch === intention.previous_epoch,
          "STORE_UNAVAILABLE",
          "Canonical restore outcome is unknown; preserve its fence.",
        );
      unlinkSync(path);
    } finally {
      corpus.close();
    }
    this.home = activeLocation(this.controlHome);
    mkdirSync(this.home, { recursive: true });
  }
  private activationPath() {
    return join(this.controlHome, "corpus-activation.json");
  }
  private finishCorpusActivation() {
    this.replaceManifest(JSON.stringify(this.workspace));
    const control = readControl(this.controlHome);
    writeControl(this.controlHome, {
      ...(control ?? { generation: ".", restoration: null }),
      format: 3,
      corpus_root: this.corpusRoot,
      coordination_id: this.coordination.identity,
      coordination_protocol: 1,
      workspace_id: this.workspace.workspace_id,
      epoch: this.workspace.epoch,
    });
    atomicJSON(this.projectionTokenPath(), { token: randomUUID() });
    this.projectionInstance = readFileSync(this.projectionTokenPath(), "utf8");
    if (existsSync(this.activationPath())) unlinkSync(this.activationPath());
  }
  private resumeCorpusActivation() {
    requireThat(
      !this.readonly,
      "MIGRATION_REQUIRED",
      "Interrupted file activation requires writable recovery.",
    );
    const intent = JSON.parse(readFileSync(this.activationPath(), "utf8"));
    requireThat(
      intent.format === 1 &&
        intent.corpus_root === this.corpusRoot &&
        intent.home === this.home &&
        intent.after?.schema_version === 10 &&
        intent.before?.workspace_id === intent.after.workspace_id &&
        intent.before?.epoch === intent.after.epoch,
      "STORE_UNAVAILABLE",
      "Unknown file activation intention; preserve all files.",
    );
    this.db = new DatabaseSync(this.projectionPath());
    this.db.exec(
      "PRAGMA foreign_keys=ON; PRAGMA busy_timeout=0; PRAGMA journal_mode=WAL; PRAGMA synchronous=FULL;",
    );
    const meta = JSON.parse(
      String(this.db.prepare("SELECT json FROM meta").get()!.json),
    );
    const version = Number(
      this.db.prepare("PRAGMA user_version").get()!.user_version,
    );
    requireThat(
      (version === 9 &&
        JSON.stringify(meta) === JSON.stringify(intent.before)) ||
        (version === 10 &&
          JSON.stringify(meta) === JSON.stringify(intent.after)),
      "STORE_UNAVAILABLE",
      "File activation projection differs from its exact intention.",
    );
    this.workspace = meta;
    this.corpus = new FileCorpus(this.corpusRoot, this.corpusFault);
    this.corpus.recover();
    if (version === 9) {
      this.corpus = undefined;
      this.activateCorpus(Boolean(intent.legacy));
    } else {
      if (!FileCorpus.exists(this.corpusRoot)) {
        this.captureRuntimeOperations();
        this.corpus.publish(this.db, this.home, true);
      } else this.openFileProjection();
      this.finishCorpusActivation();
    }
  }
  private activateCorpus(legacy: boolean) {
    requireThat(
      !this.readonly && !this.db.isTransaction,
      "READ_ONLY",
      "Cannot migrate an active/read-only transaction.",
    );
    if (this.corpus) return this.corpus.status();
    const before = { ...this.workspace },
      after = { ...this.workspace, schema_version: 10 };
    let maintenance: string | undefined;
    try {
      if (legacy) {
        maintenance = this.coordination.beginMaintenance(
          "file-migration",
          this.workspace.epoch,
        );
        requireThat(
          this.coordination.drainMaintenance().pending === 0,
          "STORE_BUSY",
          "Let admitted operations settle before file migration.",
        );
        this.coordination.exclusiveMaintenance(maintenance);
        const backup = join(
          this.home,
          "pre-file-corpus-" + randomUUID() + ".sqlite",
        );
        this.db.prepare("VACUUM INTO ?").run(backup);
        const check = new DatabaseSync(backup, { readOnly: true });
        try {
          requireThat(
            check.prepare("PRAGMA integrity_check").get()!.integrity_check ===
              "ok",
            "STORE_UNAVAILABLE",
            "Pre-file backup verification failed.",
          );
        } finally {
          check.close();
        }
      }
      if (!existsSync(this.activationPath()))
        atomicJSON(this.activationPath(), {
          format: 1,
          before,
          after,
          legacy,
          coordination_id: this.coordination.identity,
          home: this.home,
          corpus_root: this.corpusRoot,
        });
      this.corpusFault?.("corpus_activation_prepared");
      this.db.exec("BEGIN IMMEDIATE");
      try {
        this.db.exec(CorpusMetadataSQL + SleepCycleSQL);
        if (legacy) this.classifyLegacyCorpus();
        this.workspace = after;
        this.db.prepare("UPDATE meta SET json=?").run(JSON.stringify(after));
        this.db.exec("PRAGMA user_version=10; COMMIT");
      } catch (error) {
        this.db.exec("ROLLBACK");
        this.workspace = before;
        throw error;
      }
      this.corpusFault?.("corpus_activation_sql_committed");
      this.corpus = new FileCorpus(this.corpusRoot, this.corpusFault);
      this.captureRuntimeOperations();
      const state = this.corpus.publish(this.db, this.home, true);
      this.finishCorpusActivation();
      return state;
    } finally {
      if (maintenance) this.coordination.endMaintenance(maintenance);
    }
  }
  private classifyLegacyCorpus() {
    const all = this.db
      .prepare("SELECT json FROM addressed_versions")
      .all()
      .map((r) => JSON.parse(String(r.json)) as RecordRow);
    const current = this.db
      .prepare("SELECT json FROM addressed_current")
      .all()
      .map((r) => JSON.parse(String(r.json)) as RecordRow);
    const active = new Set<string>();
    for (const r of current)
      if (
        [
          "activity",
          "work",
          "knowledge",
          "entity",
          "method",
          "concept",
        ].includes(r.kind) ||
        (r.kind === "run" && r.data.execution === "running") ||
        (String(r.kind) === "signal" &&
          ["open", "observing"].includes(String(r.data.problem_state)))
      )
        active.add(r.id + ":" + r.revision);
    let changed = true;
    while (changed) {
      changed = false;
      for (const r of all)
        if (active.has(r.id + ":" + r.revision))
          for (const ref of addressedRefs(r)) {
            const target =
              ref.revision === undefined
                ? current.find((x) => x.id === ref.id)
                : all.find(
                    (x) => x.id === ref.id && x.revision === ref.revision,
                  );
            if (target && !active.has(target.id + ":" + target.revision)) {
              active.add(target.id + ":" + target.revision);
              changed = true;
            }
          }
    }
    for (const r of all)
      this.db
        .prepare("INSERT OR REPLACE INTO corpus_entries VALUES(?,?,?)")
        .run(
          r.id,
          r.revision,
          active.has(r.id + ":" + r.revision) ? "active" : "legacy",
        );
  }
  private replaceManifest(json: string) {
    const temp = join(
      this.home,
      "workspace-migration-" + randomUUID() + ".tmp",
    );
    durableWrite(temp, json);
    renameSync(temp, join(this.home, "workspace.json"));
  }
  private migrateMemory(target = 3) {
    requireThat(
      !this.readonly,
      "READ_ONLY",
      "Schema " +
        (target - 1) +
        " needs an exclusive writer for migration; no replacement database.",
    );
    const before = JSON.stringify(this.workspace);
    const current = this.all<{ json: string }>("SELECT json FROM records").map(
      (r) => JSON.parse(r.json) as RecordRow,
    );
    const get = (ref: unknown, kind?: string) => {
      const p = ref as { id: string; revision?: number };
      const row =
        p.revision === undefined
          ? this.get<{ json: string }>(
              "SELECT json FROM records WHERE id=?",
              p.id,
            )
          : this.get<{ json: string }>(
              "SELECT json FROM revisions WHERE id=? AND revision=?",
              p.id,
              p.revision,
            );
      requireThat(
        row,
        "STORE_UNAVAILABLE",
        "Memory migration found an unresolved reference.",
      );
      const r = JSON.parse(row.json) as RecordRow;
      requireThat(
        !kind || r.kind === kind,
        "STORE_UNAVAILABLE",
        "Memory migration found a wrong reference kind.",
      );
      return r;
    };
    validateMemory(current, get);
    validateWorks(current, get, (ref, workId) => {
      const r = ref as { id: string; revision?: number };
      const row = this.get<{ json: string }>(
        "SELECT json FROM handoffs WHERE id=?",
        r.id,
      );
      if (!row) {
        get(ref);
        return;
      }
      const h = JSON.parse(row.json);
      requireThat(
        h.work_ref.id === workId &&
          h.transport_state === "prepared_not_sent" &&
          (r.revision === undefined || r.revision === 1),
        "STORE_UNAVAILABLE",
        "Memory migration found an invalid handoff step reference.",
      );
      get(h.work_ref, "work");
    });
    for (const row of this.all<{ json: string }>("SELECT json FROM handoffs")) {
      const h = JSON.parse(row.json);
      get(h.work_ref, "work");
      for (const ref of h.context_refs) get(ref);
    }
    for (const row of this.all<{ json: string }>(
      "SELECT json FROM records UNION ALL SELECT json FROM revisions",
    )) {
      const r = JSON.parse(row.json) as RecordRow;
      if (typeof r.data.blob_ref === "string") {
        requireThat(
          sha(readFileSync(join(this.home, "materials", r.data.blob_ref))) ===
            r.data.blob_ref,
          "STORE_UNAVAILABLE",
          "Memory migration found a corrupt retained material.",
        );
      }
    }
    const backup = join(
      this.home,
      "pre-schema-" + target + "-" + randomUUID() + ".sqlite",
    );
    this.db.prepare("VACUUM INTO ?").run(backup);
    const check = new DatabaseSync(backup, { readOnly: true });
    try {
      requireThat(
        (
          check.prepare("PRAGMA integrity_check").get() as {
            integrity_check: string;
          }
        ).integrity_check === "ok",
        "STORE_UNAVAILABLE",
        "Memory migration backup failed verification.",
      );
    } finally {
      check.close();
    }
    const faultPrefix =
      target === 3
        ? "memory"
        : target === 4
          ? "experience"
          : target === 5
            ? "approval"
            : target === 6
              ? "lifecycle"
              : target === 7
                ? "sleep"
                : target === 8
                  ? "documents"
                  : "concurrency";
    this.migrationFault?.(faultPrefix + "_after_backup");
    const after = JSON.stringify({ ...this.workspace, schema_version: target });
    this.exec("BEGIN IMMEDIATE");
    try {
      this.exec(
        target === 9 &&
          this.get(
            "SELECT name FROM sqlite_master WHERE name='memory_index_meta'",
          )
          ? "SELECT 1;"
          : target === 3
            ? MemorySchemaSQL
            : target === 4
              ? ExperienceSchemaSQL
              : target === 5
                ? ApprovalSchemaSQL
                : target === 6
                  ? LifecycleSchemaSQL
                  : target === 7
                    ? SleepSchemaSQL
                    : target === 9
                      ? MemoryIndexSchemaSQL
                      : "SELECT 1;",
      );
      if (target === 9) initializeConcurrencyState(this);
      refreshMemory(this, true);
      this.run(
        "INSERT INTO migrations VALUES(?,?)",
        target,
        JSON.stringify({
          before,
          after,
          backup,
          backup_sha256: sha(readFileSync(backup)),
          recorded_at: new Date().toISOString(),
        }),
      );
      this.run("UPDATE meta SET json=?", after);
      this.exec("PRAGMA user_version=" + target);
      this.migrationFault?.(faultPrefix + "_before_schema_commit");
      requireThat(
        this.get<{ integrity_check: string }>("PRAGMA integrity_check")
          ?.integrity_check === "ok" &&
          this.all("PRAGMA foreign_key_check").length === 0,
        "STORE_UNAVAILABLE",
        "Memory migration integrity failed.",
      );
      this.exec("COMMIT");
    } catch (e) {
      this.exec("ROLLBACK");
      throw e;
    }
    this.migrationFault?.(faultPrefix + "_after_schema_commit");
    this.replaceManifest(after);
    this.workspace = JSON.parse(after);
  }
  private migrate() {
    requireThat(
      !this.readonly,
      "READ_ONLY",
      "Schema 1 needs an exclusive writer for migration; no replacement database.",
    );
    const before = JSON.stringify(this.workspace);
    // Verify existing references and blobs before touching schema. Current domain JSON is untouched.
    const ids = new Set(
      this.all<{ id: string }>("SELECT id FROM records").map((r) => r.id),
    );
    const visit = (v: unknown) => {
      if (Array.isArray(v)) for (const item of v) visit(item);
      else if (v && typeof v === "object") {
        const o = v as Record<string, unknown>;
        if (
          typeof o.id === "string" &&
          Object.keys(o).every((k) => ["id", "revision"].includes(k))
        )
          requireThat(
            ids.has(o.id),
            "STORE_UNAVAILABLE",
            "Migration found an unresolved record reference.",
          );
        for (const value of Object.values(o)) visit(value);
      }
    };
    for (const row of this.all<{ json: string }>(
      "SELECT json FROM records UNION ALL SELECT json FROM revisions",
    )) {
      const r = JSON.parse(row.json);
      visit(r.data);
      if (r.data.blob_ref) {
        const b = readFileSync(join(this.home, "materials", r.data.blob_ref));
        requireThat(
          sha(b) === r.data.blob_ref,
          "STORE_UNAVAILABLE",
          "Migration found a missing/corrupt retained material.",
        );
      }
    }
    const backup = join(this.home, "pre-schema-2-" + randomUUID() + ".sqlite");
    this.db.prepare("VACUUM INTO ?").run(backup);
    const check = new DatabaseSync(backup, { readOnly: true });
    try {
      requireThat(
        (
          check.prepare("PRAGMA integrity_check").get() as {
            integrity_check: string;
          }
        ).integrity_check === "ok",
        "STORE_UNAVAILABLE",
        "Migration backup failed integrity check.",
      );
    } finally {
      check.close();
    }
    this.migrationFault?.("after_backup");
    const after = JSON.stringify({ ...this.workspace, schema_version: 2 });
    this.db.exec("BEGIN IMMEDIATE");
    try {
      this.db.exec(
        `CREATE TABLE claims(token TEXT PRIMARY KEY,work_id TEXT NOT NULL,json TEXT NOT NULL); ${BaseIndexesSQL.claim_work} CREATE TABLE handoffs(id TEXT PRIMARY KEY,json TEXT NOT NULL); CREATE TABLE migrations(version INTEGER PRIMARY KEY,json TEXT NOT NULL);`,
      );
      this.db.prepare("INSERT INTO migrations VALUES(2,?)").run(
        JSON.stringify({
          before,
          after,
          backup,
          backup_sha256: sha(readFileSync(backup)),
          recorded_at: new Date().toISOString(),
        }),
      );
      this.db.prepare("UPDATE meta SET json=?").run(after);
      this.db.exec("PRAGMA user_version=2");
      this.migrationFault?.("before_schema_commit");
      requireThat(
        this.get<{ integrity_check: string }>("PRAGMA integrity_check")
          ?.integrity_check === "ok" &&
          this.all("PRAGMA foreign_key_check").length === 0,
        "STORE_UNAVAILABLE",
        "Migration integrity check failed.",
      );
      this.db.exec("COMMIT");
    } catch (e) {
      this.db.exec("ROLLBACK");
      throw e;
    }
    this.migrationFault?.("after_schema_commit");
    this.replaceManifest(after);
    this.workspace = JSON.parse(after);
  }
  assertActive(epoch: string, write = false) {
    if (this.initializing) return;
    requireThat(
      !this.closed && !this.connectionClosed && epoch === this.workspace.epoch,
      "RESTORE_RECONCILIATION_REQUIRED",
      "Workspace connection/epoch is no longer active; reload.",
    );
    const phase = this.coordination.phaseToken;
    // The stable operation gate excludes every generation switch. Validate filesystem
    // authority once per capability, never once per SQL statement or across phases.
    if (!phase || this.checkedPhase !== phase) {
      const control = readControl(this.controlHome);
      requireThat(
        control &&
          control.epoch === epoch &&
          control.workspace_id === this.workspace.workspace_id &&
          activeLocation(this.controlHome) === this.home,
        "RESTORE_RECONCILIATION_REQUIRED",
        "Active generation changed; reload the workspace.",
      );
      this.checkedPhase = phase;
    }
    if (write) {
      requireThat(
        !this.administrative,
        "WORK_IN_USE",
        "A consistent backup is capturing this connection.",
      );
      requireThat(
        !this.readonly,
        "READ_ONLY",
        "Writes are explicitly disabled for this connection.",
      );
      this.coordination.assertHeld();
    }
  }
  private flushMemory() {
    if (
      this.initializing ||
      this.flushingMemory ||
      this.closed ||
      this.connectionClosed ||
      this.db.isTransaction
    )
      return;
    if (
      !this.db
        .prepare("SELECT name FROM sqlite_master WHERE name='memory_dirty'")
        .get() ||
      !this.db.prepare("SELECT 1 FROM memory_dirty LIMIT 1").get()
    )
      return;
    requireThat(
      !this.readonly,
      "INDEX_UNAVAILABLE",
      "Derived state needs a writable coordinated refresh before this read.",
    );
    this.flushingMemory = true;
    this.db.exec("BEGIN IMMEDIATE");
    try {
      refreshMemory(this, false, [], []);
      this.db.exec("COMMIT");
    } catch (error) {
      this.db.exec("ROLLBACK");
      throw error;
    } finally {
      this.flushingMemory = false;
    }
  }
  private commandResult<T>(callback: () => T): T {
    if (this.corpus && !this.initializing) {
      this.ensureFileProjection();
      this.rehydratePortableOperations();
    }
    this.flushMemory();
    let failed = false;
    try {
      return callback();
    } catch (error) {
      failed = true;
      throw error;
    } finally {
      try {
        this.maybeReclaimTransientImports();
        this.flushMemory();
        if (
          this.corpus &&
          !this.initializing &&
          !this.connectionClosed &&
          !this.closed &&
          !this.readonly &&
          !this.db.isTransaction &&
          !this.corpusPublishing
        ) {
          this.corpusPublishing = true;
          try {
            this.captureRuntimeOperations();
            this.corpus.publish(this.db, this.home);
          } catch (error) {
            // File commit point owns the outcome, even if SQLite already committed.
            this.corpus.recover();
            this.rebuildFileProjection();
            throw error;
          } finally {
            this.corpusPublishing = false;
          }
        }
      } catch (error) {
        // A durability failure is never hidden behind a prior validation error.
        if (!failed || this.corpus) throw error;
      }
    }
  }
  withCommandSync<T>(callback: () => T, kind: CommandKind = "mutate"): T {
    if (this.initializing || this.coordination.held) return callback();
    return this.coordination.sync(kind, () => this.commandResult(callback));
  }
  withOperation<T>(
    kind: CommandKind,
    callback: () => T,
    options?: OperationOptions,
  ): Promise<T> {
    return this.coordination.run(
      kind,
      () => this.commandResult(callback),
      options,
    );
  }
  withReadSnapshot<T>(callback: () => T): T {
    return this.withCommandSync(() => {
      if (this.db.isTransaction) return callback();
      this.db.exec("BEGIN DEFERRED");
      try {
        const value = callback();
        this.db.exec("COMMIT");
        return value;
      } catch (error) {
        this.db.exec("ROLLBACK");
        throw error;
      }
    }, "read");
  }
  async backupTo(path: string, operationId?: string) {
    await this.withOperation(
      "settle",
      () => {
        this.assertActive(this.workspace.epoch, true);
        this.administrative = true;
      },
      { operationId },
    );
    try {
      await backup(this.db, path);
    } finally {
      await this.withOperation(
        "settle",
        () => {
          this.administrative = false;
        },
        { operationId },
      );
    }
    await this.withOperation(
      "settle",
      () => this.assertActive(this.workspace.epoch, true),
      { operationId },
    );
  }
  pinSource(key: string, hashes: string[]) {
    this.run(
      "INSERT OR REPLACE INTO lifecycle_pins VALUES(?,?)",
      key,
      JSON.stringify({
        kind: "source",
        hashes,
        expires_at: Date.now() + 1800000,
      }),
    );
  }
  unpinSource(key: string) {
    this.run("DELETE FROM lifecycle_pins WHERE key=?", key);
  }
  exec(sql: string) {
    return this.withCommandSync(() => {
      this.assertActive(this.workspace?.epoch, true);
      this.db.exec(sql);
      if (this.corpus && !this.readonly && /\b(CREATE|ALTER|DROP)\b/i.test(sql))
        this.corpus.installCapture(this.db);
    });
  }
  get<T>(sql: string, ...params: (string | number | null)[]) {
    return this.withCommandSync(() => {
      this.assertActive(this.workspace?.epoch);
      const result = this.db.prepare(sql).get(...params) as T | undefined;
      if (this.corpus && !this.initializing && result)
        this.corpus.verifyReadRows(sql, [result]);
      return result;
    }, "read");
  }
  all<T>(sql: string, ...params: (string | number | null)[]) {
    return this.withCommandSync(() => {
      this.assertActive(this.workspace?.epoch);
      const result = this.db.prepare(sql).all(...params) as T[];
      if (this.corpus && !this.initializing)
        this.corpus.verifyReadRows(sql, result);
      return result;
    }, "read");
  }
  run(sql: string, ...params: (string | number | null)[]) {
    return this.withCommandSync(() => {
      this.assertActive(this.workspace?.epoch, true);
      this.db.prepare(sql).run(...params);
    });
  }
  importFile(path: string, roots: string[], fault?: (point: string) => void) {
    this.assertActive(this.workspace.epoch, true);
    requireThat(!this.readonly, "READ_ONLY", "Imports need the one writer.");
    requireThat(
      isAbsolute(path),
      "VALIDATION_ERROR",
      "Import path must be absolute.",
    );
    const real = realpathSync(path);
    requireThat(
      roots.some((root) => within(realpathSync(root), real)),
      "PERMISSION_DENIED",
      "Import escapes trusted permitted roots.",
    );
    requireThat(
      [".txt", ".md", ".markdown"].includes(extname(real).toLowerCase()),
      "VALIDATION_ERROR",
      "This block reads only UTF-8 TXT/Markdown.",
    );
    const stat = statSync(real);
    requireThat(
      stat.isFile() && stat.size <= 1024 * 1024,
      "VALIDATION_ERROR",
      "Import requires an ordinary file of at most 1 MiB.",
    );
    const bytes = readFileSync(real);
    requireThat(
      bytes.length <= 1024 * 1024,
      "VALIDATION_ERROR",
      "Input grew beyond the import bound.",
    );
    let text: string;
    try {
      text = new TextDecoder("utf-8", { fatal: true, ignoreBOM: true }).decode(
        bytes,
      );
    } catch {
      throw new CoreError(
        "VALIDATION_ERROR",
        "The material is not valid UTF-8 text; no readable import was created.",
      );
    }
    const hash = sha(bytes);
    const pending_key = "pending-" + randomUUID();
    this.pinSource(pending_key, [hash]);
    const stage = join(this.home, "staging", randomUUID());
    const target = join(this.home, "materials", hash);
    this.trackTransientMaterial(hash, stage);
    durableWrite(stage, bytes);
    fault?.("after_stage");
    if (existsSync(target)) {
      requireThat(
        sha(readFileSync(target)) === hash,
        "STORE_UNAVAILABLE",
        "Existing material digest mismatch.",
      );
      unlinkSync(stage);
    } else renameSync(stage, target);
    fault?.("after_rename");
    requireThat(
      sha(readFileSync(target)) === hash,
      "STORE_UNAVAILABLE",
      "Retained material failed readback.",
    );
    return {
      text,
      blob_ref: hash,
      byte_length: bytes.length,
      locator: real,
      pending_key,
    };
  }
  async importMaterial(
    path: string,
    roots: string[],
    authorize: () => void,
    signal?: AbortSignal,
    fault?: (point: string) => void,
  ) {
    const { bytes, format, real, pendingKey } = await this.withOperation(
      "mutate",
      () => {
        authorize();
        this.assertActive(this.workspace.epoch, true);
        requireThat(
          !this.readonly,
          "READ_ONLY",
          "Imports need the one writer.",
        );
        requireThat(
          isAbsolute(path),
          "VALIDATION_ERROR",
          "Import path must be absolute.",
        );
        const real = realpathSync(path);
        requireThat(
          roots.some((root) => within(realpathSync(root), real)),
          "PERMISSION_DENIED",
          "Import escapes trusted permitted roots.",
        );
        const format = extname(real).slice(1).toLowerCase();
        const limit = ["txt", "md", "markdown"].includes(format)
          ? 1024 * 1024
          : 64 * 1024 * 1024;
        const fd = openSync(real, "r");
        let bytes: Buffer;
        try {
          const stat = fstatSync(fd);
          requireThat(
            stat.isFile() && stat.size <= limit,
            "MATERIAL_TOO_LARGE",
            "Material must be an ordinary file within its declared size limit.",
          );
          bytes = readFileSync(fd);
          requireThat(
            bytes.length <= limit,
            "MATERIAL_TOO_LARGE",
            "Material grew beyond the size limit.",
          );
        } finally {
          closeSync(fd);
        }
        const pendingKey = "pending-" + randomUUID();
        this.pinSource(pendingKey, [sha(bytes)]);
        this.coordination.reserve({
          operation_id: pendingKey,
          epoch: this.workspace.epoch,
          kind: "import",
          digest: sha(bytes),
          resources: ["import:" + pendingKey],
        });
        this.coordination.phase(pendingKey, "dispatching");
        return { bytes, format, real, pendingKey };
      },
      { signal },
    );
    try {
      let extraction: Awaited<ReturnType<typeof extract>>;
      if (["txt", "md", "markdown"].includes(format)) {
        let text = "",
          status: "readable" | "damaged" = "readable";
        try {
          text = new TextDecoder("utf-8", {
            fatal: true,
            ignoreBOM: true,
          }).decode(bytes);
        } catch {
          status = "damaged";
        }
        extraction = {
          format,
          status,
          parser: "WHATWG TextDecoder",
          parser_version: process.version + " UTF-8",
          text,
          text_blob_ref: null,
          text_hash: null,
          total_characters: Array.from(text).length,
          sections: [
            {
              locator: "text:1",
              label: "Text",
              start: 0,
              end: Array.from(text).length,
              available: status === "readable",
            },
          ],
          warnings:
            status === "damaged"
              ? [
                  "Invalid UTF-8; original bytes retained without readable text.",
                ]
              : [],
        };
      } else if (["pdf", "epub"].includes(format))
        extraction = await extract(bytes, format, signal);
      else
        extraction = {
          format,
          status: "unsupported",
          parser: "none",
          parser_version: "none",
          text: "",
          text_blob_ref: null,
          text_hash: null,
          total_characters: 0,
          sections: [],
          warnings: [
            "Unsupported format; retained original is not readable text.",
          ],
        };
      return await this.withOperation(
        "settle",
        () => {
          authorize();
          requireThat(
            !signal?.aborted,
            "PERMISSION_DENIED",
            "Import runtime was invalidated.",
          );
          this.pinSource(pendingKey, [
            sha(bytes),
            ...(extraction.text ? [sha(Buffer.from(extraction.text))] : []),
          ]);
          const blob_ref = this.retain(bytes, fault);
          const { text, ...metadata } = extraction;
          if (["readable", "partial"].includes(metadata.status)) {
            metadata.text_blob_ref = this.retain(Buffer.from(text), fault);
            metadata.text_hash = metadata.text_blob_ref;
          }
          this.coordination.phase(pendingKey, "complete");
          this.coordination.release(pendingKey);
          return {
            pending_key: pendingKey,
            text,
            blob_ref,
            byte_length: bytes.length,
            locator: real,
            extraction: metadata,
          };
        },
        { operationId: pendingKey },
      );
    } catch (error) {
      try {
        await this.withOperation(
          "settle",
          () => {
            this.unpinSource(pendingKey);
            this.coordination.release(pendingKey);
          },
          { operationId: pendingKey },
        );
      } catch {
        /* Durable import reservation remains recoverable. */
      }
      throw error;
    }
  }
  private trackTransientMaterial(hash: string, stage: string) {
    if (
      !this.corpus ||
      existsSync(join(this.corpus.root, "materials", hash + ".json"))
    )
      return;
    const folder = join(this.home, "transient-imports");
    mkdirSync(folder, { recursive: true });
    const path = safePath(this.home, join(folder, hash + ".json"));
    const previous = existsSync(path)
      ? JSON.parse(readFileSync(path, "utf8"))
      : undefined;
    atomicJSON(path, {
      format: 1,
      hash,
      created_at: previous?.created_at ?? Date.now(),
      expires_at: previous?.expires_at ?? Date.now() + 1800000,
      stages: [...new Set([...(previous?.stages ?? []), stage])].slice(-8),
    });
  }
  private maybeReclaimTransientImports() {
    if (Date.now() < this.transientCleanupRetry) return;
    try {
      this.reclaimTransientImports();
      this.transientCleanupDeferred = false;
    } catch {
      this.transientCleanupDeferred = true;
      this.transientCleanupRetry = Date.now() + 300000;
    }
  }
  /** Runtime-only cache reclamation. Selected canonical bytes are never candidates. */
  reclaimTransientImports(now = Date.now()) {
    if (this.readonly || !this.corpus || this.closed || this.connectionClosed)
      return { checked: 0, removed: 0, protected: 0 };
    this.coordination.assertHeld();
    const folder = join(this.home, "transient-imports"),
      statePath = join(this.home, "transient-materials.json");
    if (!existsSync(folder)) return { checked: 0, removed: 0, protected: 0 };
    const state = existsSync(statePath)
      ? JSON.parse(readFileSync(statePath, "utf8"))
      : { last: 0, cursor: "" };
    if (now - state.last < 300000)
      return { checked: 0, removed: 0, protected: 0 };
    const pending = this.coordination.pending(),
      pendingIds = new Set(pending.map((row) => row.operation_id));
    const protectedHashes = new Set(
      pending
        .map((row) => row.digest)
        .filter((hash) => /^[a-f0-9]{64}$/.test(hash)),
    );
    let allPinned = false;
    for (const row of this.db
      .prepare("SELECT key,json FROM lifecycle_pins")
      .all()) {
      const pin = JSON.parse(String(row.json));
      if (
        pin.expires_at === null ||
        Number(pin.expires_at) > now ||
        pendingIds.has(String(row.key))
      ) {
        if (pin.kind === "backup-all") allPinned = true;
        for (const hash of pin.hashes ?? []) protectedHashes.add(hash);
      }
    }
    const names = readdirSync(folder)
        .filter((name) => /^[a-f0-9]{64}\.json$/.test(name))
        .sort(),
      later = names.filter((name) => name > state.cursor),
      selected = (later.length ? later : names).slice(0, 64);
    let checked = 0,
      removed = 0,
      protectedCount = 0,
      bytesRead = 0;
    for (const name of selected) {
      const index = safePath(this.home, join(folder, name)),
        entry = JSON.parse(readFileSync(index, "utf8"));
      requireThat(
        entry.format === 1 &&
          entry.hash + ".json" === name &&
          Array.isArray(entry.stages),
        "STORE_UNAVAILABLE",
        "Invalid transient import cache index; preserve it.",
      );
      checked++;
      if (
        existsSync(join(this.corpus.root, "materials", entry.hash + ".json"))
      ) {
        unlinkSync(index);
        continue;
      }
      if (
        entry.expires_at > now ||
        allPinned ||
        protectedHashes.has(entry.hash)
      ) {
        protectedCount++;
        continue;
      }
      const material = join(this.home, "materials", entry.hash),
        paths = [material, ...entry.stages];
      let finished = true;
      for (const candidate of paths) {
        const allowed =
          candidate === material ||
          within(join(this.home, "staging"), candidate);
        requireThat(
          allowed,
          "PERMISSION_DENIED",
          "Transient import stage escaped its runtime root.",
        );
        const path = safePath(this.home, candidate);
        if (!existsSync(path)) continue;
        const info = statSync(path, { bigint: true });
        requireThat(
          info.isFile() && info.nlink === 1n,
          "PERMISSION_DENIED",
          "Transient cleanup refuses linked/nonregular bytes.",
        );
        if (bytesRead + Number(info.size) > 134217728) {
          finished = false;
          break;
        }
        const bytes = readFileSync(path);
        bytesRead += bytes.length;
        requireThat(
          bytesHash(bytes) === entry.hash,
          "STORE_UNAVAILABLE",
          "Transient import changed; preserve its bytes.",
        );
        unlinkSync(path);
        removed++;
      }
      if (finished) unlinkSync(index);
      if (bytesRead >= 134217728) break;
    }
    atomicJSON(statePath, { last: now, cursor: selected.at(-1) ?? "" });
    return { checked, removed, protected: protectedCount };
  }
  private retain(bytes: Uint8Array, fault?: (point: string) => void) {
    const hash = sha(bytes),
      stage = join(this.home, "staging", randomUUID()),
      target = join(this.home, "materials", hash);
    this.trackTransientMaterial(hash, stage);
    durableWrite(stage, bytes);
    fault?.("after_stage");
    if (existsSync(target)) {
      requireThat(
        sha(readFileSync(target)) === hash,
        "STORE_UNAVAILABLE",
        "Existing material digest mismatch.",
      );
      unlinkSync(stage);
    } else renameSync(stage, target);
    fault?.("after_rename");
    requireThat(
      sha(readFileSync(target)) === hash,
      "STORE_UNAVAILABLE",
      "Retained material failed readback.",
    );
    return hash;
  }
  readBlob(hash: string) {
    this.assertActive(this.workspace.epoch);
    requireThat(
      /^[0-9a-f]{64}$/.test(hash),
      "VALIDATION_ERROR",
      "Invalid blob address.",
    );
    const path = safePath(this.home, join(this.home, "materials", hash));
    const bytes = readFileSync(path);
    requireThat(
      bytesHash(bytes) === hash,
      "STORE_UNAVAILABLE",
      "Blob digest mismatch.",
    );
    return bytes;
  }
  readMaterial(hash: string) {
    requireThat(
      /^[0-9a-f]{64}$/.test(hash),
      "VALIDATION_ERROR",
      "Invalid managed material address.",
    );
    const path = join(this.home, "materials", hash);
    requireThat(
      existsSync(path),
      "CONTENT_NOT_RETAINED",
      "The referenced material is missing.",
    );
    const bytes = readFileSync(path);
    requireThat(
      sha(bytes) === hash,
      "STORE_UNAVAILABLE",
      "Retained material digest mismatch.",
    );
    return new TextDecoder("utf-8", { fatal: true, ignoreBOM: true }).decode(
      bytes,
    );
  }
  doctor() {
    return {
      workspace: this.workspace,
      node: process.version,
      platform: process.platform,
      architecture: process.arch,
      sqlite: this.get<{ version: string }>(
        "SELECT sqlite_version() AS version",
      )!.version,
      integrity: this.get("PRAGMA integrity_check"),
      journal: this.get("PRAGMA journal_mode"),
      schema_version: this.get("PRAGMA user_version"),
      read_only: this.readonly,
      concurrency: this.coordination.describe(),
      ...(this.transientCleanupDeferred
        ? {
            temporary_cleanup: "deferred; cache bytes preserved for inspection",
          }
        : {}),
    };
  }
  closeConnection() {
    if (this.connectionClosed) return;
    const close = () => {
      this.connectionClosed = true;
      this.db?.close();
    };
    if (this.initializing || this.coordination.held) close();
    else this.coordination.sync("maintenance", close);
  }
  close() {
    this.corpus?.close();
    if (this.closed) return;
    // A busy close remains retryable; never strand an open DB/OS lease behind a closed flag.
    this.closeConnection();
    if (this.ownsLock) {
      const path = join(this.controlHome, "writer.lock");
      if (
        existsSync(path) &&
        JSON.parse(readFileSync(path, "utf8")).token === this.lockToken
      )
        unlinkSync(path);
      this.ownsLock = false;
    }
    if (this.ownsCoordination) this.coordination.close({ poisonUnknown: true });
    this.closed = true;
  }
}
export { CoreError };
export { OutputBoundary } from "./output.ts";

export { Administration, fullAccess } from "./administration.ts";

export {
  GitSynchronizer,
  loadSyncBinding,
  saveSyncBinding,
  syncBindingPath,
  DEFAULT_SYNC_EXCLUSIONS,
  GIT_BLOB_LIMIT,
  validateSyncBinding,
} from "./git-sync.ts";
export type {
  SyncBinding,
  SyncRevision,
  SyncOptions,
  SyncStatus,
  RemoteIdentity,
  SyncCode,
} from "./git-sync.ts";

export { migrateQuarantinedStore } from "./migration.ts";
export type { MigrationReport } from "./migration.ts";

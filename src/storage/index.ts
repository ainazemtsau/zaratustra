import { DatabaseSync } from "node:sqlite";
import { randomUUID, createHash } from "node:crypto";
import {
  closeSync,
  existsSync,
  fsyncSync,
  fstatSync,
  mkdirSync,
  openSync,
  readFileSync,
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
  refreshMemory,
  validateMemory,
} from "../core/index.ts";
import type { RecordRow } from "../core/index.ts";
import { extract } from "./extract.ts";

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
  workspace: StoragePort["workspace"];
  readonly = false;
  private db!: DatabaseSync;
  private lockToken = randomUUID();
  private ownsLock = false;
  private closed = false;
  constructor(
    public home: string,
    private migrationFault?: (point: string) => void,
  ) {
    requireThat(
      isAbsolute(home),
      "VALIDATION_ERROR",
      "ZARATUSTRA_HOME must be an absolute trusted setup path.",
    );
    home = resolve(home);
    this.home = home;
    mkdirSync(home, { recursive: true });
    const manifest = join(home, "workspace.json");
    const dbPath = join(home, "zara.sqlite");
    const hadManifest = existsSync(manifest);
    const hadDb = existsSync(dbPath);
    requireThat(
      hadManifest === hadDb,
      "STORE_UNAVAILABLE",
      "Workspace manifest/database mismatch; preserve files and diagnose.",
    );
    try {
      const lock = join(home, "writer.lock");
      if (existsSync(lock)) {
        const owner = JSON.parse(readFileSync(lock, "utf8")) as { pid: number };
        let alive = true;
        try {
          process.kill(owner.pid, 0);
        } catch (e) {
          alive = (e as NodeJS.ErrnoException).code !== "ESRCH";
        }
        if (!alive) unlinkSync(lock);
      }
      try {
        durableWrite(
          lock,
          JSON.stringify({ pid: process.pid, token: this.lockToken }),
        );
        this.ownsLock = true;
      } catch (e) {
        if ((e as NodeJS.ErrnoException).code === "EEXIST")
          this.readonly = true;
        else throw e;
      }
      requireThat(
        hadDb || !this.readonly,
        "READ_ONLY",
        "Workspace is being initialized by another writer.",
      );
      this.db = new DatabaseSync(dbPath, { readOnly: this.readonly });
      this.db.exec("PRAGMA foreign_keys=ON; PRAGMA busy_timeout=1000;");
      if (!this.readonly)
        this.db.exec("PRAGMA journal_mode=WAL; PRAGMA synchronous=FULL;");
      if (!hadDb) {
        this.workspace = {
          workspace_id: randomUUID(),
          epoch: randomUUID(),
          schema_version: 3,
        };
        this.db.exec(`BEGIN IMMEDIATE;
          CREATE TABLE meta(json TEXT NOT NULL);
          CREATE TABLE records(id TEXT PRIMARY KEY,kind TEXT NOT NULL,activity_id TEXT,json TEXT NOT NULL);
          CREATE INDEX kind_activity ON records(kind,activity_id);
          CREATE TABLE revisions(id TEXT NOT NULL,revision INTEGER NOT NULL,json TEXT NOT NULL,PRIMARY KEY(id,revision));
          CREATE TABLE changes(seq INTEGER PRIMARY KEY,json TEXT NOT NULL);
          CREATE TABLE intents(request_id TEXT PRIMARY KEY,hash TEXT NOT NULL,json TEXT NOT NULL);
          CREATE TABLE receipts(request_id TEXT PRIMARY KEY,hash TEXT NOT NULL,json TEXT NOT NULL,bindings TEXT NOT NULL);
          CREATE TABLE focus(session_id TEXT PRIMARY KEY,json TEXT NOT NULL);
          CREATE TABLE claims(token TEXT PRIMARY KEY,work_id TEXT NOT NULL,json TEXT NOT NULL);
          CREATE INDEX claim_work ON claims(work_id);
          CREATE TABLE handoffs(id TEXT PRIMARY KEY,json TEXT NOT NULL);
          CREATE TABLE migrations(version INTEGER PRIMARY KEY,json TEXT NOT NULL);
          ${MemorySchemaSQL}
          PRAGMA user_version=3;`);
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
              this.workspace.schema_version === 3) &&
            version === this.workspace.schema_version,
          "STORE_UNAVAILABLE",
          "Unknown schema or workspace identity mismatch; no replacement store will be created.",
        );
      }
      requireThat(
        this.get<{ integrity_check: string }>("PRAGMA integrity_check")
          ?.integrity_check === "ok",
        "STORE_UNAVAILABLE",
        "SQLite integrity check failed.",
      );
      if (this.workspace.schema_version === 1) this.migrate();
      if (this.workspace.schema_version === 2) this.migrateMemory();
      if (!this.readonly) {
        mkdirSync(join(home, "materials"), { recursive: true });
        mkdirSync(join(home, "staging"), { recursive: true });
      }
    } catch (e) {
      this.close();
      throw e;
    }
  }
  private replaceManifest(json: string) {
    const temp = join(
      this.home,
      "workspace-migration-" + randomUUID() + ".tmp",
    );
    durableWrite(temp, json);
    renameSync(temp, join(this.home, "workspace.json"));
  }
  private migrateMemory() {
    requireThat(
      !this.readonly,
      "READ_ONLY",
      "Schema 2 needs an exclusive writer for memory migration; no replacement database.",
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
    const backup = join(this.home, "pre-schema-3-" + randomUUID() + ".sqlite");
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
    this.migrationFault?.("memory_after_backup");
    const after = JSON.stringify({ ...this.workspace, schema_version: 3 });
    this.exec("BEGIN IMMEDIATE");
    try {
      this.exec(MemorySchemaSQL);
      refreshMemory(this, true);
      this.run(
        "INSERT INTO migrations VALUES(3,?)",
        JSON.stringify({
          before,
          after,
          backup,
          backup_sha256: sha(readFileSync(backup)),
          recorded_at: new Date().toISOString(),
        }),
      );
      this.run("UPDATE meta SET json=?", after);
      this.exec("PRAGMA user_version=3");
      this.migrationFault?.("memory_before_schema_commit");
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
    this.migrationFault?.("memory_after_schema_commit");
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
        "CREATE TABLE claims(token TEXT PRIMARY KEY,work_id TEXT NOT NULL,json TEXT NOT NULL); CREATE INDEX claim_work ON claims(work_id); CREATE TABLE handoffs(id TEXT PRIMARY KEY,json TEXT NOT NULL); CREATE TABLE migrations(version INTEGER PRIMARY KEY,json TEXT NOT NULL);",
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
  exec(sql: string) {
    this.db.exec(sql);
  }
  get<T>(sql: string, ...params: (string | number | null)[]) {
    return this.db.prepare(sql).get(...params) as T | undefined;
  }
  all<T>(sql: string, ...params: (string | number | null)[]) {
    return this.db.prepare(sql).all(...params) as T[];
  }
  run(sql: string, ...params: (string | number | null)[]) {
    this.db.prepare(sql).run(...params);
  }
  importFile(path: string, roots: string[], fault?: (point: string) => void) {
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
    const stage = join(this.home, "staging", randomUUID());
    const target = join(this.home, "materials", hash);
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
    return { text, blob_ref: hash, byte_length: bytes.length, locator: real };
  }
  async importMaterial(
    path: string,
    roots: string[],
    authorize: () => void,
    signal?: AbortSignal,
    fault?: (point: string) => void,
  ) {
    authorize();
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
        parser_version: "Node 22.19.0 UTF-8",
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
            ? ["Invalid UTF-8; original bytes retained without readable text."]
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
    authorize();
    requireThat(
      !signal?.aborted,
      "PERMISSION_DENIED",
      "Import runtime was invalidated.",
    );
    const blob_ref = this.retain(bytes, fault);
    const { text, ...metadata } = extraction;
    if (["readable", "partial"].includes(metadata.status)) {
      metadata.text_blob_ref = this.retain(Buffer.from(text), fault);
      metadata.text_hash = metadata.text_blob_ref;
    }
    return {
      text,
      blob_ref,
      byte_length: bytes.length,
      locator: real,
      extraction: metadata,
    };
  }
  private retain(bytes: Uint8Array, fault?: (point: string) => void) {
    const hash = sha(bytes),
      stage = join(this.home, "staging", randomUUID()),
      target = join(this.home, "materials", hash);
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
    };
  }
  close() {
    if (this.closed) return;
    this.closed = true;
    try {
      this.db?.close();
    } finally {
      if (this.ownsLock) {
        const path = join(this.home, "writer.lock");
        try {
          if (JSON.parse(readFileSync(path, "utf8")).token === this.lockToken)
            unlinkSync(path);
        } finally {
          this.ownsLock = false;
        }
      }
    }
  }
}
export { CoreError };

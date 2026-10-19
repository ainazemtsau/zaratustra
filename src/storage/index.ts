import { DatabaseSync } from "node:sqlite";
import { randomUUID, createHash } from "node:crypto";
import {
  closeSync,
  existsSync,
  fsyncSync,
  mkdirSync,
  openSync,
  readFileSync,
  realpathSync,
  renameSync,
  statSync,
  unlinkSync,
  writeFileSync,
} from "node:fs";
import { extname, isAbsolute, join, relative, resolve } from "node:path";
import type { StoragePort } from "../core/index.ts";
import { CoreError, requireThat } from "../core/index.ts";

const sha = (bytes: Uint8Array) =>
  createHash("sha256").update(bytes).digest("hex");
export function within(root: string, path: string) {
  const rel = relative(root, path);
  return rel === "" || (!rel.startsWith("..") && !isAbsolute(rel));
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
  constructor(public home: string) {
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
          schema_version: 1,
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
          PRAGMA user_version=1;`);
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
        requireThat(
          meta &&
            meta.json === JSON.stringify(this.workspace) &&
            this.workspace.schema_version === 1 &&
            this.get<{ user_version: number }>("PRAGMA user_version")
              ?.user_version === 1,
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
      if (!this.readonly) {
        mkdirSync(join(home, "materials"), { recursive: true });
        mkdirSync(join(home, "staging"), { recursive: true });
      }
    } catch (e) {
      this.close();
      throw e;
    }
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
    const text = new TextDecoder("utf-8", {
      fatal: true,
      ignoreBOM: true,
    }).decode(bytes);
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

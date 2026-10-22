import { DatabaseSync } from "node:sqlite";
import { randomUUID } from "node:crypto";
import {
  existsSync,
  mkdirSync,
  readFileSync,
  readdirSync,
  statSync,
  lstatSync,
} from "node:fs";
import { basename, join, resolve } from "node:path";
import { z } from "zod";
import { checkIndexes } from "./indexes.ts";
import {
  Approvals,
  addressedRefs,
  canonical,
  refreshMemory,
  requireThat,
  validateMemory,
  validateMethods,
  validateWorks,
  ActivityData,
  WorkData,
  KnowledgeData,
  ConceptData,
  EntityData,
  MethodData,
  RunData,
  TombstoneSchema,
  PersistedSupportData,
  PersistedEvidenceData,
  SleepSchemaSQL,
  validateSleep,
} from "../core/index.ts";
import type {
  CallContext,
  JsonObject,
  PreviewStore,
  RecordRow,
  StoragePort,
} from "../core/index.ts";
import {
  activeLocation,
  atomicJSON,
  bytesHash,
  durableNew,
  newDirectory,
  readControl,
  safePath,
  writeControl,
  removeOwned,
} from "./control.ts";

const tables = [
  "records",
  "revisions",
  "changes",
  "intents",
  "receipts",
  "focus",
  "claims",
  "handoffs",
  "migrations",
  "relations",
  "relation_history",
  "experience_rows",
  "experience_versions",
  "lifecycle_pins",
  "recovery_barriers",
  "lifecycle_events",
];
const sleepTables = ["sleep_reviews", "sleep_items", "sleep_coverage"];
const component = z.strictObject({
  path: z
    .string()
    .regex(/^(database\.sqlite|export\.json|materials\/[0-9a-f]{64})$/),
  length: z.number().int().min(0).max(536870912),
  sha256: z.string().regex(/^[0-9a-f]{64}$/),
});
const Manifest = z.strictObject({
  format: z.literal("zaratustra.bundle.v1"),
  schema: z.union([z.literal(6), z.literal(7)]),
  workspace_id: z.string(),
  captured_epoch: z.string(),
  captured_seq: z.number().int().nonnegative(),
  captured_at: z.iso.datetime(),
  complete: z.literal(true),
  coverage: z.literal(
    "full current and retained historical/deleted metadata; historical authority is not runnable",
  ),
  components: z.array(component).min(2).max(1002),
});
export type BundleManifest = z.infer<typeof Manifest>;
type Disk = StoragePort & {
  home: string;
  controlHome: string;
  backupTo(path: string): Promise<void>;
  readBlob(hash: string): Buffer;
  close(): void;
  closeConnection(): void;
  connectionClosed: boolean;
};
export function fullAccess(ctx: CallContext, write = false) {
  requireThat(
    ctx.principal === "trusted-personal" &&
      ctx.processing_allowed &&
      ctx.scopes?.includes("restricted:read") &&
      (!write || (ctx.can_write && ctx.scopes.includes("restricted:write"))),
    "PERMISSION_DENIED",
    "Full backup/export requires fixed full-read setup; restore requires full-read and full-write setup. No bundle inspection was authorized.",
  );
}
function port(db: DatabaseSync, home: string): StoragePort {
  const workspace = JSON.parse(
    String(db.prepare("SELECT json FROM meta").get()!.json),
  );
  return {
    workspace,
    readonly: false,
    exec: (s) => db.exec(s),
    get: <T>(s: string, ...p: (string | number | null)[]) =>
      db.prepare(s).get(...p) as T | undefined,
    all: <T>(s: string, ...p: (string | number | null)[]) =>
      db.prepare(s).all(...p) as T[],
    run: (s, ...p) => {
      db.prepare(s).run(...p);
    },
    readMaterial: (hash) =>
      readFileSync(safePath(home, join(home, "materials", hash)), "utf8"),
  };
}
function dbRows(db: DatabaseSync) {
  return Object.fromEntries(
    [
      ...tables,
      ...(db.prepare("PRAGMA user_version").get()!.user_version === 7
        ? sleepTables
        : []),
    ].map((t) => [t, db.prepare(`SELECT * FROM ${t} ORDER BY rowid`).all()]),
  );
}
function blobs(db: DatabaseSync) {
  const set = new Set<string>();
  // Only retained managed versions, never source_locator or a guessed path.
  for (const { json } of db
    .prepare("SELECT json FROM records UNION ALL SELECT json FROM revisions")
    .all()) {
    const r = JSON.parse(String(json));
    if (r.storage === "tombstone") continue;
    for (const h of [r.data?.blob_ref, r.data?.extraction?.text_blob_ref])
      if (h) {
        requireThat(
          typeof h === "string" && /^[0-9a-f]{64}$/.test(h),
          "STORE_UNAVAILABLE",
          "Invalid managed material address in snapshot.",
        );
        set.add(h);
      }
  }
  return [...set].sort();
}
function validate(
  db: DatabaseSync,
  home: string,
  materials = true,
  allowDerivedIndexRepair = false,
) {
  requireThat(
    [6, 7].includes(
      Number(db.prepare("PRAGMA user_version").get()!.user_version),
    ),
    "STORE_UNAVAILABLE",
    "Unsupported bundle schema.",
  );
  requireThat(
    db
      .prepare("PRAGMA integrity_check")
      .all()
      .every((r) => r.integrity_check === "ok") &&
      db.prepare("PRAGMA foreign_key_check").all().length === 0,
    "STORE_UNAVAILABLE",
    "SQLite integrity/foreign keys failed.",
  );
  const index_repairs_required = checkIndexes(
    db,
    allowDerivedIndexRepair ? "allow-derived-repair" : "require",
  );
  const s = port(db, home),
    rows = db
      .prepare("SELECT json FROM records")
      .all()
      .map((r) => JSON.parse(String(r.json)) as RecordRow);
  requireThat(
    s.workspace.schema_version ===
      Number(db.prepare("PRAGMA user_version").get()!.user_version),
    "STORE_UNAVAILABLE",
    "Snapshot schema metadata mismatch.",
  );
  const schemas: Record<string, z.ZodType> = {
    activity: ActivityData,
    work: WorkData,
    knowledge: KnowledgeData,
    concept: ConceptData,
    entity: EntityData,
    method: MethodData,
    run: RunData,
    evidence: PersistedEvidenceData,
    ...PersistedSupportData,
  };
  for (const [current, versions] of [
    ["records", "revisions"],
    ["experience_rows", "experience_versions"],
  ]) {
    for (const row of db.prepare(`SELECT id,kind,json FROM ${current}`).all()) {
      const r = JSON.parse(String(row.json)),
        version = db
          .prepare(`SELECT json FROM ${versions} WHERE id=? AND revision=?`)
          .get(String(row.id), r.revision);
      requireThat(
        r.id === row.id &&
          r.kind === row.kind &&
          version &&
          canonical(JSON.parse(String(version.json))) === canonical(r),
        "STORE_UNAVAILABLE",
        "Current identity/kind/version disagrees with retained canonical version.",
      );
    }
    for (const row of db
      .prepare(`SELECT id,revision,json FROM ${versions}`)
      .all()) {
      const r = JSON.parse(String(row.json));
      requireThat(
        r.id === row.id && r.revision === row.revision,
        "STORE_UNAVAILABLE",
        "Retained version identity/revision mismatch.",
      );
    }
  }
  const get = (value: unknown, kind?: string): RecordRow => {
    const r = value as {
      id: string;
      revision?: number;
      content_version?: number;
    };
    const found =
      r.content_version !== undefined
        ? db
            .prepare(
              "SELECT json FROM revisions WHERE id=? AND json_extract(json,'$.data.content_version')=? AND (? IS NULL OR revision=?) ORDER BY revision LIMIT 1",
            )
            .get(
              r.id,
              r.content_version,
              r.revision ?? null,
              r.revision ?? null,
            )
        : r.revision === undefined
          ? db
              .prepare("SELECT json FROM addressed_current WHERE id=?")
              .get(r.id)
          : db
              .prepare(
                "SELECT json FROM addressed_versions WHERE id=? AND revision=?",
              )
              .get(r.id, r.revision);
    requireThat(
      found,
      "STORE_UNAVAILABLE",
      "Unresolved snapshot reference/version.",
    );
    const row = JSON.parse(String(found.json)) as RecordRow;
    requireThat(
      !kind || row.kind === kind,
      "STORE_UNAVAILABLE",
      "Wrong snapshot reference kind.",
    );
    return row;
  };
  for (const { json } of db
    .prepare(
      "SELECT json FROM addressed_versions UNION ALL SELECT json FROM addressed_current",
    )
    .all()) {
    const r = JSON.parse(String(json)) as RecordRow;
    requireThat(
      Number.isInteger(r.revision) &&
        r.revision > 0 &&
        ["live", "archive", "tombstone"].includes(r.storage),
      "STORE_UNAVAILABLE",
      "Invalid snapshot envelope.",
    );
    if (r.storage === "tombstone") {
      TombstoneSchema.parse(r.data);
      requireThat(
        r.body === null && r.data.content_not_retained === true,
        "STORE_UNAVAILABLE",
        "Invalid tombstone.",
      );
      continue;
    }
    requireThat(
      r.kind in schemas,
      "STORE_UNAVAILABLE",
      "Unknown persisted domain/support kind.",
    );
    schemas[r.kind].parse(r.data);
    if (String(r.kind) === "signal" || String(r.kind) === "signal_review") {
      requireThat(
        r.data.problem_state !== "observing" ||
          (r.data.applied_change_ref && r.data.next_check),
        "STORE_UNAVAILABLE",
        "Observing Signal lacks its exact change/future check.",
      );
      requireThat(
        r.data.problem_state !== "resolved" || r.data.grounds,
        "STORE_UNAVAILABLE",
        "Resolved Signal lacks grounds.",
      );
      requireThat(
        r.data.problem_state !== "dismissed" || r.data.dismissal_reason,
        "STORE_UNAVAILABLE",
        "Dismissed Signal lacks reason.",
      );
    }
    for (const ref of addressedRefs(r.data)) {
      const handoff = db
        .prepare("SELECT json FROM handoffs WHERE id=?")
        .get(ref.id);
      if (handoff) {
        const h = JSON.parse(String(handoff.json));
        requireThat(
          ref.content_version === undefined &&
            (ref.revision === undefined || ref.revision === 1),
          "STORE_UNAVAILABLE",
          "Invalid historical handoff reference.",
        );
        get(h.work_ref, "work");
        for (const source of h.context_refs ?? []) get(source);
      } else get(ref);
    }
  }
  const retained = rows.filter((r) => r.storage !== "tombstone");
  validateMemory(retained, get);
  validateMethods(retained, get);
  validateWorks(retained, get, (ref, work) => {
    const p = ref as { id: string };
    const h = db.prepare("SELECT json FROM handoffs WHERE id=?").get(p.id);
    if (h)
      requireThat(
        JSON.parse(String(h.json)).work_ref.id === work,
        "STORE_UNAVAILABLE",
        "Invalid handoff Work.",
      );
    else get(ref);
  });
  if (s.workspace.schema_version === 7) validateSleep(s, get);
  if (materials)
    for (const h of blobs(db)) {
      const p = safePath(home, join(home, "materials", h));
      requireThat(
        existsSync(p) && bytesHash(readFileSync(p)) === h,
        "STORE_UNAVAILABLE",
        "Missing/corrupt snapshot material; bundle incomplete.",
      );
    }
  return { storage: s, rows, index_repairs_required };
}

/** One self-contained directory artifact, no scheduler or alternate recovery database. */
export class Administration {
  readonly approvals: Approvals;
  private drafts = new Set<string>();
  private listCursors = new Map<string, { generation: string; last: number }>();
  constructor(
    readonly home: string,
    readonly backupRoot: string,
    readonly context: CallContext,
    private fault?: (point: string) => void,
  ) {
    const store: PreviewStore = {
      get workspace() {
        return {
          workspace_id: context.workspace_id,
          epoch: context.epoch,
          schema_version: 6,
        };
      },
      assertActive: (e) => {
        fullAccess(this.context, true);
        requireThat(
          (readControl(home)?.epoch ?? context.epoch) === e,
          "APPROVAL_STALE",
          "Active restore control changed.",
        );
      },
      readPreview: (ref) => {
        this.authorize(true);
        const p = join(home, "administration", ref + ".json");
        if (!/^preview-[a-f0-9-]+$/.test(ref) || !existsSync(p))
          return undefined;
        return JSON.parse(readFileSync(safePath(home, p), "utf8"));
      },
      writePreview: (p, create) => {
        this.authorize(true);
        const dir = join(home, "administration");
        mkdirSync(dir, { recursive: true });
        safePath(home, dir);
        const path = join(dir, p.request_id + ".json");
        if (create) durableNew(path, JSON.stringify(p));
        else atomicJSON(path, p);
      },
    };
    this.approvals = new Approvals(
      store,
      context,
      () => true,
      () => {
        throw new Error(
          "Restore uses exact control/bundle guards, no current-DB dependency.",
        );
      },
    );
  }
  private authorize(write = false) {
    fullAccess(this.context, write);
    const control = readControl(this.home);
    requireThat(
      !control ||
        (control.epoch === this.context.epoch &&
          control.workspace_id === this.context.workspace_id),
      "RESTORE_RECONCILIATION_REQUIRED",
      "Administrative context belongs to an inactive generation/epoch; reload.",
    );
  }
  owns(ref: string) {
    return this.drafts.has(ref);
  }
  private location(path: string) {
    this.authorize();
    requireThat(
      existsSync(this.backupRoot),
      "REFERENCE_NOT_FOUND",
      "Designated backup root is unavailable.",
    );
    return safePath(this.backupRoot, resolve(this.backupRoot, path));
  }
  private fingerprint() {
    const data = activeLocation(this.home);
    return bytesHash(
      canonical(
        [
          "active.json",
          ...["workspace.json", "zara.sqlite", "zara.sqlite-wal"].map((n) =>
            join(data, n),
          ),
        ].map((n) => {
          const p = n === "active.json" ? join(this.home, n) : n;
          return existsSync(p)
            ? [p, bytesHash(readFileSync(safePath(this.home, p)))]
            : [p, null];
        }),
      ),
    );
  }
  verify(path: string) {
    path = this.location(path);
    const manifestBytes = readFileSync(
      safePath(path, join(path, "manifest.json")),
    );
    requireThat(
      manifestBytes.length <= 16000000,
      "VALIDATION_ERROR",
      "Bundle manifest exceeds bound.",
    );
    const manifest = Manifest.parse(JSON.parse(manifestBytes.toString("utf8")));
    requireThat(
      new Set(manifest.components.map((c) => c.path)).size ===
        manifest.components.length &&
        manifest.components.some((c) => c.path === "database.sqlite") &&
        manifest.components.some((c) => c.path === "export.json"),
      "STORE_UNAVAILABLE",
      "Duplicate/missing bundle components.",
    );
    for (const c of manifest.components) {
      const p = safePath(path, join(path, c.path));
      requireThat(
        existsSync(p) && statSync(p).isFile() && statSync(p).size === c.length,
        "STORE_UNAVAILABLE",
        "Bundle component missing/length mismatch.",
      );
      requireThat(
        bytesHash(readFileSync(p)) === c.sha256,
        "STORE_UNAVAILABLE",
        "Bundle digest mismatch.",
      );
    }
    const db = new DatabaseSync(join(path, "database.sqlite"), {
      readOnly: true,
    });
    let index_repairs_required: string[] = [];
    try {
      const checked = validate(db, path, true, true),
        { storage } = checked;
      index_repairs_required = checked.index_repairs_required;
      requireThat(
        storage.workspace.workspace_id === manifest.workspace_id &&
          storage.workspace.schema_version === manifest.schema &&
          storage.workspace.epoch === manifest.captured_epoch &&
          Number(
            db.prepare("SELECT coalesce(max(seq),0) AS seq FROM changes").get()!
              .seq,
          ) === manifest.captured_seq,
        "STORE_UNAVAILABLE",
        "Snapshot identity/sequence mismatch.",
      );
      requireThat(
        canonical(blobs(db)) ===
          canonical(
            manifest.components
              .filter((c) => c.path.startsWith("materials/"))
              .map((c) => basename(c.path))
              .sort(),
          ),
        "STORE_UNAVAILABLE",
        "Snapshot blob set differs from manifest.",
      );
      const exported = JSON.parse(
        readFileSync(join(path, "export.json"), "utf8"),
      );
      requireThat(
        exported.format === "zaratustra.export.v1" &&
          exported.schema === manifest.schema &&
          exported.workspace_id === manifest.workspace_id &&
          canonical(exported.tables) === canonical(dbRows(db)),
        "STORE_UNAVAILABLE",
        "JSON export differs from completed snapshot.",
      );
    } finally {
      db.close();
    }
    return {
      path,
      manifest,
      identity: bytesHash(manifestBytes),
      index_repairs_required,
      schema_ready: index_repairs_required.length === 0,
    };
  }
  async backup(disk: Disk, holdLivePin = false) {
    this.authorize();
    disk.assertActive?.(this.context.epoch, true);
    requireThat(
      !disk.readonly,
      "READ_ONLY",
      "Backup capture requires the stable writer.",
    );
    const bundle = newDirectory(this.backupRoot, "backup-"),
      key = "backup-" + randomUUID();
    disk.run(
      "INSERT INTO lifecycle_pins VALUES(?,?)",
      key,
      JSON.stringify({ kind: "backup-all", expires_at: Date.now() + 1800000 }),
    );
    try {
      await disk.backupTo(join(bundle, "database.sqlite"));
      this.fault?.("after_snapshot");
      const db = new DatabaseSync(join(bundle, "database.sqlite"), {
        readOnly: true,
      });
      let manifest: BundleManifest;
      try {
        const s = port(db, bundle),
          hashes = blobs(db);
        disk.run(
          "UPDATE lifecycle_pins SET json=? WHERE key=?",
          JSON.stringify({
            kind: "backup",
            hashes,
            expires_at: holdLivePin ? null : Date.now() + 1800000,
            bundle,
          }),
          key,
        );
        mkdirSync(join(bundle, "materials"));
        for (const hash of hashes) {
          durableNew(join(bundle, "materials", hash), disk.readBlob(hash));
          this.fault?.("during_blob_copy");
        }
        const exported = {
          format: "zaratustra.export.v1",
          workspace_id: s.workspace.workspace_id,
          schema: s.workspace.schema_version,
          coverage:
            "current and retained history; tombstones have no retained bodies; authority is historical",
          tables: dbRows(db),
          included_blobs: hashes,
        };
        durableNew(join(bundle, "export.json"), JSON.stringify(exported));
        const paths = [
          "database.sqlite",
          "export.json",
          ...hashes.map((h) => "materials/" + h),
        ];
        manifest = {
          format: "zaratustra.bundle.v1",
          schema: s.workspace.schema_version as 6 | 7,
          workspace_id: s.workspace.workspace_id,
          captured_epoch: s.workspace.epoch,
          captured_seq: Number(
            db.prepare("SELECT coalesce(max(seq),0) AS seq FROM changes").get()!
              .seq,
          ),
          captured_at: new Date().toISOString(),
          complete: true,
          coverage:
            "full current and retained historical/deleted metadata; historical authority is not runnable",
          components: paths.map((path) => {
            const b = readFileSync(join(bundle, path));
            return { path, length: b.length, sha256: bytesHash(b) };
          }),
        };
      } finally {
        db.close();
      }
      requireThat(
        manifest.components.length <= 1002 &&
          manifest.components.reduce((n, c) => n + c.length, 0) <= 1073741824,
        "VALIDATION_ERROR",
        "Bundle exceeds 1000 managed blobs or 1 GiB total; no complete artifact was delivered.",
      );
      durableNew(
        join(bundle, "manifest.json"),
        JSON.stringify(manifest, null, 2),
      );
      const verified = this.verify(bundle);
      return {
        backup: bundle,
        identity: verified.identity,
        complete: true,
        captured_seq: manifest.captured_seq,
        export: "export.json",
        live_pin: holdLivePin ? key : null,
        coverage: manifest.coverage,
        index_repairs_required: verified.index_repairs_required,
        schema_ready: verified.schema_ready,
      };
    } catch (e) {
      atomicJSON(join(bundle, "INCOMPLETE.json"), {
        complete: false,
        error: e instanceof Error ? e.message : "failed",
      });
      throw e;
    } finally {
      if (!holdLivePin) disk.run("DELETE FROM lifecycle_pins WHERE key=?", key);
    }
  }
  restorePreview(backup: string, consequence: string, alternatives: string) {
    this.authorize(true);
    const b = this.verify(backup),
      fingerprint = this.fingerprint();
    const generations = join(this.home, "generations");
    const quarantine = newDirectory(generations, "");
    mkdirSync(join(quarantine, "materials"));
    for (const c of b.manifest.components.filter(
      (c) => c.path !== "export.json",
    ))
      durableNew(
        join(quarantine, c.path === "database.sqlite" ? "zara.sqlite" : c.path),
        readFileSync(join(b.path, c.path)),
      );
    this.fault?.("restore_after_copy");
    const epoch = randomUUID(),
      restoration_id = randomUUID();
    const db = new DatabaseSync(join(quarantine, "zara.sqlite"));
    let rebuilt_indexes: string[] = [];
    try {
      db.exec("PRAGMA foreign_keys=ON;");
      const { storage, rows } = validate(db, quarantine, true, true);
      let migration:
        | {
            before: string;
            after: string;
            backup: string;
            backup_sha256: string;
            recorded_at: string;
          }
        | undefined;
      if (storage.workspace.schema_version === 6) {
        const backup = join(
          quarantine,
          "pre-schema-7-" + randomUUID() + ".sqlite",
        );
        db.prepare("VACUUM INTO ?").run(backup);
        const check = new DatabaseSync(backup, { readOnly: true });
        try {
          validate(check, quarantine, true, true);
        } finally {
          check.close();
        }
        migration = {
          before: JSON.stringify(storage.workspace),
          after: JSON.stringify({ ...storage.workspace, schema_version: 7 }),
          backup,
          backup_sha256: bytesHash(readFileSync(backup)),
          recorded_at: new Date().toISOString(),
        };
        this.fault?.("restore_sleep_after_backup");
      }
      db.exec("BEGIN IMMEDIATE");
      if (migration) {
        db.exec(SleepSchemaSQL);
        db.prepare("INSERT INTO migrations VALUES(7,?)").run(
          JSON.stringify(migration),
        );
        db.exec("PRAGMA user_version=7");
        storage.workspace = JSON.parse(migration.after);
        this.fault?.("restore_sleep_before_schema_commit");
      }
      rebuilt_indexes = checkIndexes(db, "repair");
      const workspace = { ...storage.workspace, epoch };
      db.prepare("UPDATE meta SET json=?").run(JSON.stringify(workspace));
      storage.workspace = workspace;
      db.exec("DELETE FROM recovery_barriers;");
      for (const w of rows.filter(
        (r) => r.kind === "work" && r.storage !== "tombstone",
      ))
        for (const step of [
          "",
          ...(w.data.steps as { step_id: string }[]).map((s) => s.step_id),
        ])
          db.prepare("INSERT INTO recovery_barriers VALUES(?,?,?)").run(
            w.id,
            step,
            JSON.stringify({
              epoch,
              restoration_id,
              status: "required",
              reason:
                "Restored Work can predate all intents/receipts; inspect current-world postconditions.",
            }),
          );
      db.prepare("INSERT INTO lifecycle_events VALUES(?,?)").run(
        restoration_id,
        JSON.stringify({
          kind: "restoration",
          backup_identity: b.identity,
          epoch,
          captured_seq: b.manifest.captured_seq,
          barrier: "all restored Work and steps",
          authority: "historical claims/approvals cannot authorize",
          rebuilt_indexes,
        }),
      );
      refreshMemory(storage, true);
      db.exec("COMMIT");
      validate(db, quarantine);
      durableNew(
        join(quarantine, "workspace.json"),
        JSON.stringify(workspace, null, 2),
      );
    } finally {
      db.close();
    }
    const quarantine_components = [
      "zara.sqlite",
      "workspace.json",
      ...b.manifest.components
        .filter((c) => c.path.startsWith("materials/"))
        .map((c) => c.path),
    ].map((path) => {
      const bytes = readFileSync(join(quarantine, path));
      return { path, length: bytes.length, sha256: bytesHash(bytes) };
    });
    this.fault?.("restore_after_verify");
    const exact = {
      rebuilt_indexes,
      quarantine_components,
      backup: b.path,
      backup_identity: b.identity,
      destination: quarantine,
      new_epoch: epoch,
      workspace_id: b.manifest.workspace_id,
      captured_seq: b.manifest.captured_seq,
      current_fingerprint: fingerprint,
      restoration_id,
      coverage: b.manifest.coverage,
      loss: "All current database changes after this snapshot are lost from active memory. External files/effects are NOT rolled back. Every restored potentially effectful Work/step requires current-world reconciliation, including absent receipts.",
      previous_generation: readControl(this.home)?.generation ?? ".",
    };
    const draft = this.approvals.draft(
      "restore",
      exact,
      [],
      consequence,
      alternatives,
    );
    this.drafts.add(draft.request_id);
    return {
      preview: draft,
      backup: b.path,
      destination: quarantine,
      coverage: exact.coverage,
      loss: exact.loss,
    };
  }
  restore(ref: string, disk?: Disk) {
    this.authorize(true);
    const p = this.approvals.read(ref),
      e = p.payload.exact;
    this.approvals.verify(ref, "restore", e);
    requireThat(
      this.fingerprint() === e.current_fingerprint,
      "APPROVAL_STALE",
      "Current memory changed since restore preview.",
    );
    requireThat(
      this.verify(String(e.backup)).identity === e.backup_identity,
      "APPROVAL_STALE",
      "Backup identity changed.",
    );
    const lock = join(this.home, "writer.lock"),
      token = randomUUID();
    if (disk) {
      disk.assertActive?.(this.context.epoch, true);
      // Keep the SAME stable lease while SQLite checkpoints/closes. No new
      // fingerprint baseline can absorb another writer's unapproved commit.
      disk.closeConnection();
    } else {
      if (existsSync(lock)) {
        const owner = JSON.parse(readFileSync(lock, "utf8"));
        let alive = true;
        try {
          process.kill(owner.pid, 0);
        } catch (err) {
          alive = (err as NodeJS.ErrnoException).code !== "ESRCH";
        }
        requireThat(
          !alive,
          "WORK_IN_USE",
          "A conflicting writer owns the stable control lock.",
        );
        removeLock(safePath(this.home, lock));
      }
      durableNew(lock, JSON.stringify({ pid: process.pid, token }));
    }
    try {
      if (!disk)
        requireThat(
          this.fingerprint() === e.current_fingerprint,
          "APPROVAL_STALE",
          "Current memory changed before the stable writer lease was acquired.",
        );
      const dest = safePath(this.home, String(e.destination));
      for (const c of e.quarantine_components as {
        path: string;
        length: number;
        sha256: string;
      }[]) {
        const bytes = readFileSync(safePath(dest, join(dest, c.path)));
        requireThat(
          bytes.length === c.length && bytesHash(bytes) === c.sha256,
          "APPROVAL_STALE",
          "Verified quarantine bytes changed after preview.",
        );
      }
      const db = new DatabaseSync(join(dest, "zara.sqlite"), {
        readOnly: true,
      });
      try {
        validate(db, dest);
      } finally {
        db.close();
      }
      this.approvals.consume(ref, "restore", e, String(e.restoration_id));
      this.fault?.("restore_before_switch");
      // A manifest-only legacy admission guard also makes old E2 writers refuse
      // a recovered root whose legacy DB and manifest were both lost.
      if (
        !existsSync(join(this.home, "workspace.json")) &&
        !existsSync(join(this.home, "zara.sqlite"))
      )
        durableNew(
          join(this.home, "workspace.json"),
          JSON.stringify({
            workspace_id: e.workspace_id,
            epoch: e.new_epoch,
            schema_version: 7,
            inactive_generation_guard: true,
          }),
        );
      writeControl(this.home, {
        format: 1,
        generation: "generations/" + basename(dest),
        workspace_id: String(e.workspace_id),
        epoch: String(e.new_epoch),
        restoration: {
          ...e,
          preview_digest: p.operation_digest,
          decision: p.answer ?? null,
          recorded_at: new Date().toISOString(),
        },
      });
      this.fault?.("restore_after_switch");
      return {
        switched: true,
        epoch: e.new_epoch,
        backup_identity: e.backup_identity,
        captured_seq: e.captured_seq,
        loss: e.loss,
        reconciliation_required: true,
      };
    } finally {
      if (disk) disk.close();
      else if (
        existsSync(lock) &&
        JSON.parse(readFileSync(lock, "utf8")).token === token
      )
        removeLock(safePath(this.home, lock));
    }
  }

  list(cursor?: string) {
    this.authorize();
    if (!existsSync(this.backupRoot)) {
      requireThat(
        !cursor,
        "CURSOR_INVALIDATED",
        "Backup catalog changed; restart listing.",
      );
      return { backups: [], has_more: false, next_cursor: null, limit: 50 };
    }
    const names = readdirSync(this.backupRoot)
      .filter((n) => /^backup-[a-f0-9-]+$/.test(n))
      .sort();
    requireThat(
      names.length <= 10000,
      "VALIDATION_ERROR",
      "Backup catalog exceeds the bounded 10000-entry scan; listing refused.",
    );
    const entries = names.map((name) => {
      const path = safePath(this.backupRoot, join(this.backupRoot, name)),
        manifest = join(path, "manifest.json");
      const stat = existsSync(manifest)
        ? lstatSync(safePath(this.backupRoot, manifest), { bigint: true })
        : null;
      return {
        path,
        manifest_available: !!stat,
        modified_at: stat ? new Date(Number(stat.mtimeMs)).toISOString() : null,
        signature: stat
          ? [
              stat.dev.toString(),
              stat.ino.toString(),
              stat.size.toString(),
              stat.mtimeNs.toString(),
            ]
          : null,
      };
    });
    const generation = bytesHash(
      canonical([
        this.backupRoot,
        this.context.workspace_id,
        this.context.epoch,
        this.context.principal,
        this.context.scopes,
        entries,
      ]),
    );
    const prior = cursor ? this.listCursors.get(cursor) : undefined;
    requireThat(
      !cursor || prior?.generation === generation,
      "CURSOR_INVALIDATED",
      "Backup catalog/access generation changed; restart listing.",
    );
    const last = prior?.last ?? 0,
      backups = entries.slice(last, last + 50).map(({ signature, ...card }) => {
        void signature;
        return card;
      }),
      has_more = last + backups.length < entries.length;
    let next_cursor: string | null = null;
    if (has_more) {
      next_cursor = "backups-" + randomUUID();
      this.listCursors.set(next_cursor, {
        generation,
        last: last + backups.length,
      });
      if (this.listCursors.size > 256)
        this.listCursors.delete(this.listCursors.keys().next().value!);
    }
    return {
      backups,
      has_more,
      next_cursor,
      limit: 50,
      generation,
      applied_filters: {
        scope: "fixed full-read",
        root: "designated backup root",
      },
    };
  }
  private garbage(disk: Disk) {
    this.authorize(true);
    disk.assertActive?.(this.context.epoch, true);
    const live = new Set<string>();
    for (const { json } of disk.all<{ json: string }>(
      "SELECT json FROM records UNION ALL SELECT json FROM revisions",
    )) {
      const r = JSON.parse(json);
      if (r.storage === "tombstone") continue;
      for (const h of [r.data?.blob_ref, r.data?.extraction?.text_blob_ref])
        if (typeof h === "string") live.add(h);
    }
    const pins = disk
      .all<{ json: string }>("SELECT json FROM lifecycle_pins")
      .map((r) => JSON.parse(r.json))
      .filter((p) => p.expires_at === null || p.expires_at > Date.now());
    requireThat(
      !pins.some((p) => p.kind === "backup-all"),
      "WORK_IN_USE",
      "A backup capture pins candidate materials; cleanup is unavailable.",
    );
    for (const p of pins) for (const h of p.hashes ?? []) live.add(h);
    const candidates: {
      path: string;
      hash: string;
      length: number;
      dev: string;
      ino: string;
      mtime: string;
    }[] = [];
    let total = 0,
      has_more = false;
    for (const folder of ["materials", "staging"])
      for (const name of readdirSync(join(disk.home, folder)).sort()) {
        if (
          folder === "materials" &&
          (!/^[0-9a-f]{64}$/.test(name) || live.has(name))
        )
          continue;
        if (folder === "staging" && !/^[a-f0-9-]+$/.test(name)) continue;
        const path = safePath(disk.home, join(disk.home, folder, name)),
          stat = lstatSync(path, { bigint: true });
        requireThat(
          stat.isFile() && stat.nlink === 1n,
          "PERMISSION_DENIED",
          "Cleanup refuses linked/nonregular candidates.",
        );
        if (folder === "staging" && Number(stat.mtimeMs) > Date.now() - 1800000)
          continue;
        requireThat(
          stat.size <= 67108864n,
          "VALIDATION_ERROR",
          "Cleanup candidate exceeds managed import bound.",
        );
        if (candidates.length >= 200 || total + Number(stat.size) > 134217728) {
          has_more = true;
          continue;
        }
        candidates.push({
          path,
          hash: bytesHash(readFileSync(path)),
          length: Number(stat.size),
          dev: stat.dev.toString(),
          ino: stat.ino.toString(),
          mtime: stat.mtimeNs.toString(),
        });
        total += Number(stat.size);
      }
    return {
      candidates,
      has_more,
      byte_limit: 134217728,
      entry_limit: 200,
      coverage:
        "Only exact unreferenced/unpinned managed materials and expired staging files in the current generation; no prior generations, external bundles/logs/transcripts.",
    };
  }
  cleanupPreview(disk: Disk, consequence: string, alternatives: string) {
    const exact = this.garbage(disk);
    const draft = this.approvals.draft(
      "cleanup",
      exact,
      [],
      consequence,
      alternatives,
    );
    this.drafts.add(draft.request_id);
    return draft;
  }
  cleanup(ref: string, disk: Disk) {
    this.authorize(true);
    this.approvals.read(ref);
    const exact = this.garbage(disk);
    this.approvals.verify(ref, "cleanup", exact);
    const id = "cleanup-" + randomUUID(),
      removed: string[] = [];
    this.approvals.consume(ref, "cleanup", exact, id);
    disk.run(
      "INSERT INTO lifecycle_events VALUES(?,?)",
      id,
      JSON.stringify({ kind: "cleanup", status: "requested", exact, removed }),
    );
    const persist = (status: string) => {
      const receipt = {
        kind: "cleanup",
        visibility: "restricted",
        request_id: id,
        status,
        epoch: this.context.epoch,
        removed: [...removed],
        coverage: exact.coverage,
      };
      disk.exec("BEGIN IMMEDIATE");
      try {
        disk.run(
          "UPDATE lifecycle_events SET json=? WHERE id=?",
          JSON.stringify(receipt),
          id,
        );
        disk.run(
          "INSERT INTO intents VALUES(?,?,?) ON CONFLICT(request_id) DO UPDATE SET json=excluded.json",
          id,
          bytesHash(canonical(exact)),
          JSON.stringify({
            request_id: id,
            kind: "cleanup",
            status,
            epoch: this.context.epoch,
            payload: exact,
            receipt,
          }),
        );
        disk.run(
          "INSERT INTO receipts VALUES(?,?,?,?) ON CONFLICT(request_id) DO UPDATE SET json=excluded.json",
          id,
          bytesHash(canonical(exact)),
          JSON.stringify(receipt),
          "{}",
        );
        disk.exec("COMMIT");
        return receipt;
      } catch (err) {
        disk.exec("ROLLBACK");
        throw err;
      }
    };
    persist("requested");
    try {
      for (const item of exact.candidates) {
        // Fresh references/pins and exact file identity before every native unlink.
        const current = this.garbage(disk).candidates.find(
          (c) => c.path === item.path,
        );
        requireThat(
          current && canonical(current) === canonical(item),
          "REVISION_CONFLICT",
          "Cleanup references/pins/identity changed.",
        );
        removeOwned(disk.home, item.path);
        removed.push(item.path);
        persist("requested");
        this.fault?.("cleanup_after_unlink");
      }
      return persist("confirmed");
    } catch (err) {
      persist("unknown");
      throw err;
    }
  }
  releasePinPreview(
    disk: Disk,
    key: string,
    consequence: string,
    alternatives: string,
  ) {
    this.authorize(true);
    disk.assertActive?.(this.context.epoch, true);
    const row = disk.get<{ json: string }>(
        "SELECT json FROM lifecycle_pins WHERE key=?",
        key,
      ),
      pin = row ? JSON.parse(row.json) : null;
    requireThat(
      pin?.kind === "backup" && pin.bundle,
      "REFERENCE_NOT_FOUND",
      "Held backup pin unavailable.",
    );
    const verified = this.verify(pin.bundle),
      draft = this.approvals.draft(
        "release_backup_pin",
        { key, pin, backup_identity: verified.identity },
        [],
        consequence,
        alternatives,
      );
    this.drafts.add(draft.request_id);
    return draft;
  }
  releasePin(ref: string, disk: Disk) {
    this.authorize(true);
    disk.assertActive?.(this.context.epoch, true);
    const p = this.approvals.read(ref),
      e = p.payload.exact;
    const row = disk.get<{ json: string }>(
      "SELECT json FROM lifecycle_pins WHERE key=?",
      String(e.key),
    );
    requireThat(
      row && canonical(JSON.parse(row.json)) === canonical(e.pin),
      "APPROVAL_STALE",
      "Backup pin changed.",
    );
    requireThat(
      this.verify(String((e.pin as JsonObject).bundle)).identity ===
        e.backup_identity,
      "APPROVAL_STALE",
      "Held independent bundle changed.",
    );
    this.approvals.consume(
      ref,
      "release_backup_pin",
      e,
      "release-" + randomUUID(),
    );
    disk.run("DELETE FROM lifecycle_pins WHERE key=?", String(e.key));
    return {
      released: e.key,
      backup_identity: e.backup_identity,
      independent_bundle_preserved: true,
    };
  }
}
import { unlinkSync } from "node:fs";
function removeLock(path: string) {
  const before = statSync(path, { bigint: true }),
    after = statSync(path, { bigint: true });
  requireThat(
    before.dev === after.dev && before.ino === after.ino,
    "WORK_IN_USE",
    "Lock identity changed.",
  );
  unlinkSync(path);
}

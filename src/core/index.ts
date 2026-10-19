import { createHash, randomUUID } from "node:crypto";
import {
  ActivityData,
  canonical,
  CommitSchema,
  CoreError,
  KnowledgeData,
  requireThat,
  WorkData,
} from "./contracts.ts";
import type {
  CallContext,
  JsonObject,
  RecordRow,
  Source,
  StoragePort,
  Receipt,
} from "./contracts.ts";
export * from "./contracts.ts";

export const digest = (value: string | Uint8Array) =>
  createHash("sha256").update(value).digest("hex");
const id = (prefix: string) => prefix + "-" + randomUUID();
const unpack = (row: { json: string }) => JSON.parse(row.json) as RecordRow;
export class Core {
  private sources = new Map<string, Source>();
  constructor(
    public storage: StoragePort,
    public context: CallContext,
    private fault?: (point: string) => void,
  ) {}
  private authorize(write = false) {
    requireThat(
      this.context.processing_allowed,
      "PERMISSION_DENIED",
      "Provider processing authority is unresolved.",
    );
    requireThat(
      this.context.workspace_id === this.storage.workspace.workspace_id &&
        this.context.epoch === this.storage.workspace.epoch,
      "PERMISSION_DENIED",
      "Workspace or epoch mismatch.",
    );
    requireThat(
      this.context.principal === "trusted-personal",
      "PERMISSION_DENIED",
      "Unsupported principal.",
    );
    if (write)
      requireThat(
        this.context.can_write && !this.storage.readonly,
        "READ_ONLY",
        "Another writing process owns this workspace, or writes are disabled.",
      );
    this.storage.get("SELECT count(*) AS n FROM records");
  }
  capture(
    text: string,
    transport: string,
    channel_identity: string | null,
    material?: { blob_ref: string; byte_length: number; locator: string },
  ) {
    this.authorize();
    requireThat(
      Buffer.byteLength(text) <= 1024 * 1024,
      "VALIDATION_ERROR",
      "Source exceeds the first-block 1 MiB bound.",
    );
    const source: Source = {
      handle: id("source"),
      source_ref: id("observed"),
      text,
      content_hash: material?.blob_ref ?? digest(text),
      transport,
      channel_identity,
      session_id: this.context.session_id,
      runtime_id: this.context.runtime_id,
      captured_at: new Date().toISOString(),
      capture_stage: material
        ? "validated-file-bytes"
        : "pi-input-hook-observed",
      original_keystrokes: false,
      byte_length: Buffer.byteLength(text),
      ...material,
    };
    this.sources.set(source.handle, source);
    return {
      source_handle: source.handle,
      source_ref: source.source_ref,
      transport,
      channel_identity,
      capture_stage: source.capture_stage,
      content_hash: source.content_hash,
      byte_length: source.byte_length,
    };
  }
  expireSources() {
    this.sources.clear();
  }
  sequence() {
    return this.storage.get<{ seq: number }>(
      "SELECT coalesce(max(seq),0) AS seq FROM changes",
    )!.seq;
  }
  private record(recordId: string, revision?: number) {
    const row =
      revision === undefined
        ? this.storage.get<{ json: string }>(
            "SELECT json FROM records WHERE id=?",
            recordId,
          )
        : this.storage.get<{ json: string }>(
            "SELECT json FROM revisions WHERE id=? AND revision=?",
            recordId,
            revision,
          );
    requireThat(
      row,
      revision === undefined ? "REFERENCE_NOT_FOUND" : "CONTENT_NOT_RETAINED",
      "Requested record/version is unavailable.",
    );
    return unpack(row);
  }
  private envelope<T>(data: T) {
    return {
      ok: true,
      workspace_id: this.context.workspace_id,
      schema_version: 1,
      snapshot_seq: this.sequence(),
      data,
      warnings: [],
    };
  }
  map() {
    this.authorize();
    return this.envelope({
      entries: [
        "activities",
        "work",
        "knowledge",
        "materials",
        "operations",
      ].map((view) => ({ label: view, selector: { view } })),
      focus: this.focus(),
    });
  }
  focus() {
    const row = this.storage.get<{ json: string }>(
      "SELECT json FROM focus WHERE session_id=?",
      this.context.session_id,
    );
    return row ? JSON.parse(row.json) : null;
  }
  browse(view: string, recordId?: string, limit = 20, cursor?: string) {
    this.authorize();
    requireThat(
      [
        "activities",
        "work",
        "knowledge",
        "materials",
        "operations",
        "changes",
      ].includes(view),
      "VALIDATION_ERROR",
      "Unsupported view.",
    );
    requireThat(
      Number.isInteger(limit) && limit > 0 && limit <= 50,
      "VALIDATION_ERROR",
      "Page limit must be 1..50.",
    );
    const seq = this.sequence();
    let offset = 0;
    if (cursor) {
      const c = JSON.parse(Buffer.from(cursor, "base64url").toString()) as {
        seq: number;
        view: string;
        recordId?: string;
        offset: number;
      };
      requireThat(
        c.seq === seq &&
          c.view === view &&
          c.recordId === recordId &&
          Number.isInteger(c.offset) &&
          c.offset >= 0,
        "CURSOR_INVALIDATED",
        "Restart this bounded query after a change.",
      );
      offset = c.offset;
    }
    let rows: unknown[];
    if (view === "operations") {
      rows = this.storage
        .all<{
          json: string;
        }>(
          "SELECT json FROM intents WHERE (? IS NULL OR EXISTS(SELECT 1 FROM json_tree(intents.json) WHERE atom=?)) ORDER BY rowid DESC LIMIT ? OFFSET ?",
          recordId ?? null,
          recordId ?? null,
          limit + 1,
          offset,
        )
        .map((r) => JSON.parse(r.json));
    } else if (view === "changes") {
      rows = this.storage
        .all<{
          json: string;
        }>(
          "SELECT json FROM changes WHERE (? IS NULL OR EXISTS(SELECT 1 FROM json_tree(changes.json) WHERE atom=?)) ORDER BY seq DESC LIMIT ? OFFSET ?",
          recordId ?? null,
          recordId ?? null,
          limit + 1,
          offset,
        )
        .map((r) => JSON.parse(r.json));
    } else {
      const kind = {
        activities: "activity",
        work: "work",
        knowledge: "knowledge",
        materials: "evidence",
      }[view]!;
      rows = this.storage
        .all<{ json: string }>(
          "SELECT json FROM records WHERE kind=? AND (? IS NULL OR activity_id=?) ORDER BY id LIMIT ? OFFSET ?",
          kind,
          recordId ?? null,
          recordId ?? null,
          limit + 1,
          offset,
        )
        .map(unpack)
        .map((r) => ({
          id: r.id,
          kind: r.kind,
          title: r.title,
          revision: r.revision,
          storage: r.storage,
          state: r.data.status ?? r.data.state ?? null,
          description: r.body,
          selector: { record_id: r.id },
        }));
    }
    const has_more = rows.length > limit;
    return this.envelope({
      cards: rows.slice(0, limit),
      applied_filters: { view, record_id: recordId ?? null, limit },
      generation: seq,
      has_more,
      next_cursor: has_more
        ? Buffer.from(
            JSON.stringify({ seq, view, recordId, offset: offset + limit }),
          ).toString("base64url")
        : null,
    });
  }
  read(
    recordId: string,
    revision?: number,
    range?: { start: number; length: number },
  ) {
    this.authorize();
    const r = this.record(recordId, revision);
    if (range) {
      requireThat(
        r.kind === "evidence" && typeof r.data.blob_ref === "string",
        "VALIDATION_ERROR",
        "Only retained imported material has addressable ranges.",
      );
      requireThat(
        Number.isInteger(range.start) &&
          range.start >= 0 &&
          Number.isInteger(range.length) &&
          range.length > 0 &&
          range.length <= 8000,
        "VALIDATION_ERROR",
        "Use a character range of 1..8000.",
      );
      const text = this.storage.readMaterial(r.data.blob_ref);
      return this.envelope({
        ref: { id: r.id, revision: r.revision },
        source_language: r.data.source_language,
        content_hash: r.data.content_hash,
        range_unit: "Unicode code points",
        start: range.start,
        text: Array.from(text)
          .slice(range.start, range.start + range.length)
          .join(""),
        total_characters: Array.from(text).length,
        has_more: range.start + range.length < Array.from(text).length,
        next_start: Math.min(
          range.start + range.length,
          Array.from(text).length,
        ),
        untrusted_source_data: true,
      });
    }
    if (
      r.kind === "evidence" &&
      typeof r.data.retained_excerpt === "string" &&
      r.data.retained_excerpt.length > 8000
    ) {
      return this.envelope({
        ...r,
        data: {
          ...r.data,
          retained_excerpt: r.data.retained_excerpt.slice(0, 8000),
          excerpt_truncated: true,
          must_read_material_range: true,
        },
      });
    }
    return this.envelope(r);
  }
  operation(requestId: string) {
    this.authorize();
    const row = this.storage.get<{ json: string }>(
      "SELECT json FROM intents WHERE request_id=?",
      requestId,
    );
    requireThat(row, "REFERENCE_NOT_FOUND", "Operation not found.");
    return this.envelope(JSON.parse(row.json));
  }
  snapshot() {
    this.authorize();
    const rows = this.storage
      .all<{
        json: string;
      }>(
        "SELECT json FROM records WHERE kind IN ('work','knowledge') ORDER BY json_extract(json,'$.updated_at') DESC,id LIMIT 21",
      )
      .map(unpack);
    const selected = rows.slice(0, 20).map((r) => ({
      id: r.id,
      kind: r.kind,
      revision: r.revision,
      title: r.title,
      data: r.data,
    }));
    const items: typeof selected = [];
    const must_read: string[] = [];
    for (const r of selected) {
      if (Buffer.byteLength(JSON.stringify([...items, r])) <= 12000)
        items.push(r);
      else must_read.push(r.id);
    }
    return {
      available: true,
      workspace_id: this.context.workspace_id,
      active_epoch: this.context.epoch,
      snapshot_seq: this.sequence(),
      focus: this.focus(),
      records: items,
      must_read,
      has_more: rows.length > 20 || must_read.length > 0,
      warnings:
        rows.length > 20
          ? ["Snapshot is incomplete; browse current catalog."]
          : [],
      write_mode: this.storage.readonly ? "read-only" : "single-writer",
      data_only: true,
    };
  }
  commit(input: unknown): Receipt {
    this.authorize(true);
    const request = CommitSchema.parse(input);
    requireThat(
      Buffer.byteLength(JSON.stringify(request)) <= 128000,
      "VALIDATION_ERROR",
      "Commit payload exceeds 128 KB.",
    );
    const previous = this.storage.get<{
      hash: string;
      json: string;
      bindings: string;
    }>(
      "SELECT hash,json,bindings FROM receipts WHERE request_id=?",
      request.request_id,
    );
    const oldBindings = previous
      ? (JSON.parse(previous.bindings) as Record<string, string>)
      : {};
    const bindings: Record<string, string> = {};
    for (const handle of request.source_handles) {
      const source = this.sources.get(handle);
      const stable = source?.source_ref ?? oldBindings[handle];
      requireThat(
        stable,
        "SOURCE_EXPIRED",
        "The exact source handle is missing or expired; never bind it to a later input.",
      );
      bindings[handle] = stable;
    }
    const canonicalInput = JSON.parse(JSON.stringify(request)) as JsonObject;
    canonicalInput.source_handles = request.source_handles
      .map((h) => bindings[h])
      .sort();
    canonicalInput.ops = request.ops.map((op) =>
      op.op === "import_evidence"
        ? { ...op, source_handle: bindings[op.source_handle] ?? null }
        : op,
    );
    const hash = digest(canonical(canonicalInput));
    if (previous) {
      requireThat(
        previous.hash === hash,
        "IDEMPOTENCY_CONFLICT",
        "This request ID belongs to a different canonical payload.",
      );
      return JSON.parse(previous.json) as Receipt;
    }
    for (const handle of request.source_handles)
      requireThat(
        this.sources.has(handle),
        "SOURCE_EXPIRED",
        "New commits require current exact source handles.",
      );
    const intent = {
      request_id: request.request_id,
      operation_digest: hash,
      source_refs: Object.values(bindings),
      session_id: this.context.session_id,
      epoch: this.context.epoch,
      status: "prepared",
      reason: request.reason,
      payload: canonicalInput,
      receipt: null as Receipt | null,
    };
    const existing = this.storage.get<{ hash: string }>(
      "SELECT hash FROM intents WHERE request_id=?",
      request.request_id,
    );
    requireThat(
      !existing || existing.hash === hash,
      "IDEMPOTENCY_CONFLICT",
      "A prepared intent with different payload uses this ID.",
    );
    this.storage.run(
      "INSERT OR IGNORE INTO intents(request_id,hash,json) VALUES(?,?,?)",
      request.request_id,
      hash,
      JSON.stringify(intent),
    );
    this.fault?.("after_prepare");
    this.storage.exec("BEGIN IMMEDIATE");
    try {
      const created: Record<string, string> = {};
      const changed = new Map<string, RecordRow>();
      const before: Record<string, number | null> = {};
      for (const op of request.ops)
        if ("client_ref" in op) {
          requireThat(
            !created[op.client_ref],
            "VALIDATION_ERROR",
            "Duplicate client_ref.",
          );
          created[op.client_ref] = id(
            op.op === "import_evidence" ? "evidence" : op.kind,
          );
        }
      const resolve = (v: unknown): unknown => {
        if (Array.isArray(v)) return v.map(resolve);
        if (v && typeof v === "object") {
          const o = v as JsonObject;
          if (typeof o.client_ref === "string" && Object.keys(o).length === 1) {
            requireThat(
              created[o.client_ref],
              "REFERENCE_NOT_FOUND",
              "Unresolved client_ref.",
            );
            return { id: created[o.client_ref] };
          }
          return Object.fromEntries(
            Object.entries(o).map(([k, value]) => [k, resolve(value)]),
          );
        }
        return v;
      };
      for (const guard of request.guards)
        requireThat(
          this.record(guard.ref.id).revision === guard.expected_revision,
          "REVISION_CONFLICT",
          "A guarded premise changed; read current records.",
        );
      const now = new Date().toISOString();
      let focus: unknown = undefined;
      for (const raw of request.ops) {
        const op = resolve(raw) as typeof raw;
        if (op.op === "set_focus") {
          focus = { activity_ref: op.activity_ref, work_ref: op.work_ref };
          continue;
        }
        if (op.op === "update_record") {
          requireThat(
            !changed.has(op.ref.id),
            "VALIDATION_ERROR",
            "Update each record once per batch.",
          );
          const current = this.record(op.ref.id);
          requireThat(
            current.kind !== "evidence",
            "VALIDATION_ERROR",
            "Original Evidence is immutable.",
          );
          requireThat(
            request.guards.some(
              (g) =>
                g.ref.id === current.id &&
                g.expected_revision === current.revision,
            ),
            "REVISION_CONFLICT",
            "Every updated record requires its exact revision guard.",
          );
          before[current.id] = current.revision;
          changed.set(current.id, {
            ...current,
            title: op.title ?? current.title,
            body: op.body === undefined ? current.body : op.body,
            data: op.data,
            revision: current.revision + 1,
            updated_at: now,
          });
        } else {
          const recordId = created[op.client_ref];
          before[recordId] = null;
          let data: JsonObject;
          if (op.op === "import_evidence") {
            requireThat(
              request.source_handles.includes(op.source_handle),
              "SOURCE_MISSING",
              "Declare the imported source handle in source_handles.",
            );
            const s = this.sources.get(op.source_handle)!;
            data = {
              source_kind: s.blob_ref ? "imported_file" : "observed_input",
              source_locator: s.locator ?? s.source_ref,
              captured_at: s.captured_at,
              content_hash: s.content_hash,
              retained_excerpt: s.blob_ref ? null : s.text,
              blob_ref: s.blob_ref ?? null,
              byte_length: s.byte_length,
              availability: "retained",
              source_language: op.source_language,
              language_assignment: "model-reported",
              provenance: { ...s, text: undefined, handle: undefined },
              trust_origin:
                s.transport === "interactive"
                  ? "trusted-desktop-observed-stage"
                  : "programmatic-or-file-not-owner-approval",
            };
          } else data = op.data;
          changed.set(recordId, {
            id: recordId,
            kind: op.op === "import_evidence" ? "evidence" : op.kind,
            title: op.title,
            body: op.op === "import_evidence" ? null : (op.body ?? null),
            revision: 1,
            created_at: now,
            updated_at: now,
            storage: "live",
            concept_ids: [],
            origin_activity_id: null,
            visibility: "workspace",
            data,
          });
        }
      }
      const get = (ref: unknown, kind?: string): RecordRow => {
        requireThat(
          ref && typeof ref === "object" && "id" in ref,
          "REFERENCE_NOT_FOUND",
          "A permanent reference is required.",
        );
        const r = ref as { id: string; revision?: number };
        const result =
          r.revision === undefined
            ? (changed.get(r.id) ?? this.record(r.id))
            : this.record(r.id, r.revision);
        requireThat(
          !kind || result.kind === kind,
          "REFERENCE_TYPE_MISMATCH",
          "Reference target has the wrong kind.",
        );
        return result;
      };
      for (const r of changed.values()) {
        if (r.kind === "activity") ActivityData.parse(r.data);
        if (r.kind === "work") {
          const w = WorkData.parse(r.data);
          if (w.activity_id) get(w.activity_id, "activity");
          requireThat(
            w.status !== "waiting" || w.waits.length > 0,
            "INVALID_TRANSITION",
            "Waiting Work needs an addressed wait.",
          );
          requireThat(
            w.status !== "active" || w.next_action,
            "INVALID_TRANSITION",
            "Active Work needs a meaningful next action.",
          );
          requireThat(
            new Set(w.waits.map((x) => x.wait_id)).size === w.waits.length,
            "VALIDATION_ERROR",
            "Wait IDs must be unique.",
          );
          for (const ref of w.context_refs) get(ref);
          for (const item of w.waits)
            for (const ref of item.received_refs) get(ref, "evidence");
        }
        if (r.kind === "knowledge") {
          const k = KnowledgeData.parse(r.data);
          requireThat(
            k.state !== "current" ||
              k.evidence_refs.length > 0 ||
              k.basis === "inference",
            "SOURCE_MISSING",
            "Current grounded Knowledge needs retained evidence.",
          );
          for (const ref of k.evidence_refs) get(ref, "evidence");
          get(k.representation.source_ref, "evidence");
        }
      }
      if (focus) {
        const f = focus as { activity_ref: unknown; work_ref: unknown };
        if (f.activity_ref) get(f.activity_ref, "activity");
        if (f.work_ref) get(f.work_ref, "work");
        this.storage.run(
          "INSERT OR REPLACE INTO focus(session_id,json) VALUES(?,?)",
          this.context.session_id,
          JSON.stringify(focus),
        );
      }
      const revisions: Record<string, number> = {};
      for (const r of changed.values()) {
        revisions[r.id] = r.revision;
        const activity = r.data.activity_id as { id?: string } | null;
        this.storage.run(
          "INSERT INTO records(id,kind,activity_id,json) VALUES(?,?,?,?) ON CONFLICT(id) DO UPDATE SET activity_id=excluded.activity_id,json=excluded.json",
          r.id,
          r.kind,
          activity?.id ?? null,
          JSON.stringify(r),
        );
        this.storage.run(
          "INSERT INTO revisions(id,revision,json) VALUES(?,?,?)",
          r.id,
          r.revision,
          JSON.stringify(r),
        );
      }
      this.fault?.("after_records");
      const seq = this.sequence() + 1;
      const transaction_id = id("txn");
      const change = {
        transaction_id,
        request_id: request.request_id,
        change_seq: seq,
        changed_refs: [...changed.values()].map((r) => ({
          id: r.id,
          before_revision: before[r.id],
          after_revision: r.revision,
        })),
        actor: this.context.principal,
        session_id: this.context.session_id,
        reason: request.reason,
        caused_by: Object.values(bindings),
        recorded_at: now,
      };
      const receipt = {
        ok: true,
        request_id: request.request_id,
        workspace_id: this.context.workspace_id,
        schema_version: 1,
        snapshot_seq: seq,
        transaction_id,
        committed: true,
        created,
        new_revisions: revisions,
        warnings: [],
      };
      this.storage.run(
        "INSERT INTO changes(seq,json) VALUES(?,?)",
        seq,
        JSON.stringify(change),
      );
      this.storage.run(
        "INSERT INTO receipts(request_id,hash,json,bindings) VALUES(?,?,?,?)",
        request.request_id,
        hash,
        JSON.stringify(receipt),
        JSON.stringify(bindings),
      );
      intent.status = "committed";
      intent.receipt = receipt;
      this.storage.run(
        "UPDATE intents SET json=? WHERE request_id=?",
        JSON.stringify(intent),
        request.request_id,
      );
      this.fault?.("before_commit");
      this.storage.exec("COMMIT");
      this.fault?.("after_commit");
      return receipt;
    } catch (error) {
      try {
        this.storage.exec("ROLLBACK");
      } catch {
        /* COMMIT may have succeeded; its receipt remains authoritative. */
      }
      throw error;
    }
  }
}

export function failure(error: unknown) {
  const known = error instanceof CoreError;
  const validation = error instanceof Error && error.name === "ZodError";
  return {
    ok: false,
    code: known
      ? error.code
      : validation
        ? "VALIDATION_ERROR"
        : "STORE_UNAVAILABLE",
    message: known
      ? error.message
      : validation
        ? "Input does not match the published first-block schema."
        : "Storage operation failed; inspect current operations before retrying any uncertain commit.",
    retryable: false,
  };
}

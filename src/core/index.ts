import { createHash, randomUUID } from "node:crypto";
import {
  ActivityData,
  canonical,
  CommitSchema,
  CoreError,
  KnowledgeData,
  requireThat,
  WorkData,
  WorkStatus,
} from "./contracts.ts";
import {
  plan,
  protectWorkUpdate,
  refId,
  terminal,
  validateWorks,
} from "./work.ts";
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
  authorizeImport() {
    this.authorize(true);
  }
  capture(
    text: string,
    transport: string,
    channel_identity: string | null,
    material?: {
      blob_ref: string;
      byte_length: number;
      locator: string;
      extraction?: Source["extraction"];
    },
  ) {
    this.authorize();
    requireThat(
      Buffer.byteLength(text) <=
        (material?.extraction ? 32 * 1024 * 1024 : 1024 * 1024),
      "VALIDATION_ERROR",
      "Source exceeds its observed-input or extracted-text bound.",
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
      ...(source.extraction ? { extraction: source.extraction } : {}),
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
      schema_version: this.storage.workspace.schema_version,
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
        "handoffs",
        "claims",
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
        "handoffs",
        "claims",
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
    if (view === "handoffs" || view === "claims") {
      rows = this.storage
        .all<{
          json: string;
        }>(
          view === "handoffs"
            ? "SELECT json FROM handoffs WHERE (? IS NULL OR json_extract(json,'$.work_ref.id')=?) ORDER BY rowid DESC LIMIT ? OFFSET ?"
            : "SELECT json FROM claims WHERE (? IS NULL OR work_id=?) ORDER BY rowid DESC LIMIT ? OFFSET ?",
          recordId ?? null,
          recordId ?? null,
          limit + 1,
          offset,
        )
        .map((r) => JSON.parse(r.json));
    } else if (view === "operations") {
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
          "SELECT json FROM records WHERE kind=? AND (? IS NULL OR activity_id=? OR json_extract(json,'$.data.parent_work_id.id')=?) ORDER BY id LIMIT ? OFFSET ?",
          kind,
          recordId ?? null,
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
    locator?: string,
  ) {
    this.authorize();
    const r = this.record(recordId, revision);
    if (range)
      requireThat(
        Number.isInteger(range.start) &&
          range.start >= 0 &&
          Number.isInteger(range.length) &&
          range.length > 0 &&
          range.length <= 8000,
        "VALIDATION_ERROR",
        "Use a code-point range of 1..8000 with a nonnegative integer start.",
      );
    let sectionBounds: { start: number; end: number } | undefined;
    const extraction = r.data.extraction as Source["extraction"];
    requireThat(
      !range || !extraction,
      "CONTENT_NOT_RETAINED",
      "Read the addressed text_derivative_ref, not the binary/opaque original.",
    );
    if (locator) {
      const sections = r.data.sections as
        | NonNullable<Source["extraction"]>["sections"]
        | undefined;
      const section = sections?.find((s) => s.locator === locator);
      requireThat(
        section,
        "REFERENCE_NOT_FOUND",
        "Unknown material section locator.",
      );
      requireThat(
        section.available,
        "CONTENT_NOT_RETAINED",
        "The selected page/chapter has no available extracted text.",
      );
      const relative = range?.start ?? 0;
      sectionBounds = section;
      requireThat(
        relative <= section.end - section.start,
        "VALIDATION_ERROR",
        "Range starts beyond the selected section.",
      );
      range = {
        start: section.start + relative,
        length: Math.min(
          range?.length ?? 8000,
          section.end - section.start - relative,
        ),
      };
      if (range.length === 0)
        return this.envelope({
          ref: { id: r.id, revision: r.revision },
          locator,
          text: "",
          has_more: false,
          next_start: relative,
          range_unit: "Unicode code points within section",
        });
    }
    if (range) {
      requireThat(
        r.kind === "evidence" &&
          (typeof r.data.blob_ref === "string" ||
            typeof r.data.retained_excerpt === "string"),
        "VALIDATION_ERROR",
        "Only retained Evidence text has addressable ranges.",
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
      const text =
        typeof r.data.blob_ref === "string"
          ? this.storage.readMaterial(r.data.blob_ref)
          : (r.data.retained_excerpt as string);
      const characters = Array.from(text);
      const nextStart = Math.min(range.start + range.length, characters.length);
      return this.envelope({
        ref: { id: r.id, revision: r.revision },
        source_language: r.data.source_language,
        content_hash: r.data.content_hash,
        range_unit: locator
          ? "Unicode code points within section"
          : "Unicode code points",
        start: range.start - (sectionBounds?.start ?? 0),
        text: characters.slice(range.start, nextStart).join(""),
        total_characters: sectionBounds
          ? sectionBounds.end - sectionBounds.start
          : characters.length,
        has_more: nextStart < (sectionBounds?.end ?? characters.length),
        next_start: nextStart - (sectionBounds?.start ?? 0),
        global_start: range.start,
        global_next_start: nextStart,
        untrusted_source_data: true,
        ...(locator
          ? {
              locator,
              section_start:
                range.start -
                (
                  r.data.sections as NonNullable<
                    Source["extraction"]
                  >["sections"]
                ).find((s) => s.locator === locator)!.start,
              section_next_start:
                nextStart -
                (
                  r.data.sections as NonNullable<
                    Source["extraction"]
                  >["sections"]
                ).find((s) => s.locator === locator)!.start,
            }
          : {}),
      });
    }
    if (r.kind === "evidence" && typeof r.data.retained_excerpt === "string") {
      const characters = Array.from(r.data.retained_excerpt);
      if (characters.length > 8000)
        return this.envelope({
          ...r,
          data: {
            ...r.data,
            retained_excerpt: characters.slice(0, 8000).join(""),
            range_unit: "Unicode code points",
            total_characters: characters.length,
            has_more: true,
            next_start: 8000,
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
  handoff(handoffId: string) {
    this.authorize();
    const row = this.storage.get<{ json: string }>(
      "SELECT json FROM handoffs WHERE id=?",
      handoffId,
    );
    requireThat(row, "REFERENCE_NOT_FOUND", "Handoff not found.");
    return this.envelope(JSON.parse(row.json));
  }
  private handoffStale(
    h: {
      work_ref: { id: string };
      plan_version: number;
      plan_snapshot?: { id: string; plan_version: number }[];
      context_refs?: { id: string; revision?: number }[];
    },
    get: (ref: unknown, kind?: string) => RecordRow,
  ) {
    const own = get({ id: h.work_ref.id }, "work");
    const snapshot = h.plan_snapshot ?? [
      { id: h.work_ref.id, plan_version: h.plan_version },
    ];
    // Earlier development artifacts did not bind ancestors. Preserve them, but
    // never certify an unchanged parent plan from missing snapshot metadata.
    if (!h.plan_snapshot && own.data.parent_work_id) return true;
    for (const premise of snapshot) {
      const current = get({ id: premise.id }, "work");
      if (
        (current.data.plan_version ?? 1) !== premise.plan_version ||
        ["paused", "done", "cancelled"].includes(current.data.status as string)
      )
        return true;
    }
    return (h.context_refs ?? []).some(
      (ref) =>
        ref.revision !== undefined &&
        get({ id: ref.id }).revision !== ref.revision,
    );
  }
  private decision(handle: string | undefined, handles?: string[]) {
    const s = handle ? this.sources.get(handle) : undefined;
    requireThat(
      s &&
        (!handles || handles.includes(handle!)) &&
        s.runtime_id === this.context.runtime_id &&
        s.session_id === this.context.session_id &&
        (s.transport === "interactive" ||
          (s.transport === "rpc" && s.channel_identity !== null)),
      "SOURCE_MISSING",
      "Explicit lifecycle/plan decision needs a current observed interactive source or trusted controller; external Evidence grants no decision authority.",
    );
    return s.source_ref;
  }
  private assertExecutable(workId: string) {
    const seen = new Set<string>();
    const plan_guards: { id: string; revision: number }[] = [];
    let r = this.record(workId);
    while (r) {
      requireThat(!seen.has(r.id), "GRAPH_CYCLE", "Parent cycle.");
      seen.add(r.id);
      plan_guards.push({ id: r.id, revision: r.revision });
      requireThat(
        !["paused", "done", "cancelled"].includes(r.data.status as string),
        "INVALID_TRANSITION",
        "Work or ancestor suppresses continuation; explicit resume/reopen is required.",
      );
      if (r.data.activity_id)
        requireThat(
          this.record(refId(r.data.activity_id)).data.status === "active",
          "INVALID_TRANSITION",
          "Activity is paused/closed.",
        );
      if (!r.data.parent_work_id) break;
      r = this.record(refId(r.data.parent_work_id));
    }
    return plan_guards;
  }
  claim(input: {
    action: "acquire" | "release" | "reconcile";
    work_id: string;
    expected_revision: number;
    step_id?: string;
    purpose?: "work" | "step" | "handoff";
    token?: string;
    reason: string;
    source_handle?: string;
  }) {
    this.authorize(true);
    this.storage.exec("BEGIN IMMEDIATE");
    try {
      this.authorize(true);
      const w = this.record(input.work_id);
      requireThat(
        w.kind === "work",
        "REFERENCE_TYPE_MISMATCH",
        "Claim target must be Work.",
      );
      requireThat(
        w.revision === input.expected_revision,
        "REVISION_CONFLICT",
        "Claim premise changed.",
      );
      const rows = this.storage
        .all<{ json: string }>("SELECT json FROM claims WHERE work_id=?", w.id)
        .map((r) => JSON.parse(r.json));
      let claim;
      if (input.action === "acquire") {
        const plan_guards = this.assertExecutable(w.id);
        const data = WorkData.parse(w.data);
        requireThat(
          !input.step_id || data.steps.some((s) => s.step_id === input.step_id),
          "REFERENCE_NOT_FOUND",
          "Claim step not found.",
        );
        requireThat(
          !rows.some(
            (c) =>
              c.state === "active" &&
              (!c.step_id || !input.step_id || c.step_id === input.step_id),
          ),
          "WORK_IN_USE",
          "Unresolved managed claim exists; expiry alone does not establish non-execution. Inspect and explicitly release/reconcile it.",
        );
        claim = {
          token: id("claim"),
          work_id: w.id,
          step_id: input.step_id ?? null,
          purpose: input.purpose ?? "work",
          expected_revision: w.revision,
          plan_guards,
          session_id: this.context.session_id,
          runtime_id: this.context.runtime_id,
          epoch: this.context.epoch,
          acquired_at: new Date().toISOString(),
          expires_at: new Date(Date.now() + 15 * 60 * 1000).toISOString(),
          state: "active",
          reason: input.reason,
          coverage:
            "Core local Work/step result recording and handoff preparation only; no external dispatch guarantee",
        };
        this.storage.run(
          "INSERT INTO claims VALUES(?,?,?)",
          claim.token,
          w.id,
          JSON.stringify(claim),
        );
      } else {
        claim = rows.find((c) => c.token === input.token);
        requireThat(claim, "REFERENCE_NOT_FOUND", "Claim not found.");
        if (input.action === "release")
          requireThat(
            claim.session_id === this.context.session_id &&
              claim.runtime_id === this.context.runtime_id,
            "WORK_IN_USE",
            "A different runtime's unresolved claim needs explicit reconciliation.",
          );
        else this.decision(input.source_handle);
        claim = {
          ...claim,
          state: "released",
          released_at: new Date().toISOString(),
          release_reason: input.reason,
          reconciled_by: this.context.runtime_id,
        };
        this.storage.run(
          "UPDATE claims SET json=? WHERE token=?",
          JSON.stringify(claim),
          claim.token,
        );
      }
      this.storage.exec("COMMIT");
      return this.envelope(claim);
    } catch (e) {
      this.storage.exec("ROLLBACK");
      throw e;
    }
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
      this.authorize(true);
      requireThat(
        !this.storage.get(
          "SELECT request_id FROM receipts WHERE request_id=?",
          request.request_id,
        ),
        "REVISION_CONFLICT",
        "Receipt changed under transaction; discover and retry identical request.",
      );
      const created: Record<string, string> = {};
      const changed = new Map<string, RecordRow>();
      const before: Record<string, number | null> = {};
      const handoffs: { id: string; json: string }[] = [];
      const consumed = new Set<string>();
      const checkDecision = (handle?: string) =>
        this.decision(handle, request.source_handles);
      const guarded = (recordId: string) => {
        const current = this.record(recordId);
        requireThat(
          request.guards.some(
            (g) =>
              g.ref.id === recordId && g.expected_revision === current.revision,
          ),
          "REVISION_CONFLICT",
          "Every changed or execution premise requires its exact revision guard.",
        );
        return current;
      };
      const requireClaim = (
        workId: string,
        stepId: string | null,
        purpose: string,
      ) => {
        const current = guarded(workId);
        const plan_guards = this.assertExecutable(workId);
        const claim = (request.claim_tokens ?? [])
          .map((token) =>
            this.storage.get<{ json: string }>(
              "SELECT json FROM claims WHERE token=?",
              token,
            ),
          )
          .filter(Boolean)
          .map((r) => JSON.parse(r!.json))
          .find(
            (c) =>
              c.work_id === workId &&
              c.step_id === stepId &&
              c.purpose === purpose,
          );
        requireThat(
          claim &&
            claim.state === "active" &&
            claim.expected_revision === current.revision &&
            claim.session_id === this.context.session_id &&
            claim.runtime_id === this.context.runtime_id &&
            claim.epoch === this.context.epoch &&
            canonical(claim.plan_guards) === canonical(plan_guards) &&
            Date.parse(claim.expires_at) > Date.now(),
          "WORK_IN_USE",
          "A current revision/session/epoch-bound managed execution claim is required.",
        );
        consumed.add(claim.token);
      };
      const stage = (current: RecordRow, data: JsonObject) => {
        before[current.id] ??= current.revision;
        changed.set(current.id, {
          ...current,
          data,
          revision: (before[current.id] ?? 0) + 1,
          updated_at: new Date().toISOString(),
        });
      };
      for (const op of request.ops)
        if ("client_ref" in op) {
          requireThat(
            !created[op.client_ref],
            "VALIDATION_ERROR",
            "Duplicate client_ref.",
          );
          created[op.client_ref] = id(
            op.op === "prepare_handoff"
              ? "handoff"
              : op.op === "import_evidence" ||
                  op.op === "receive_handoff" ||
                  op.op === "record_result"
                ? "evidence"
                : op.kind,
          );
          if (
            op.op === "import_evidence" &&
            this.sources.get(op.source_handle)?.extraction?.text_blob_ref
          ) {
            const key = op.client_ref + "_text";
            requireThat(
              !request.ops.some(
                (o) => "client_ref" in o && o.client_ref === key,
              ),
              "VALIDATION_ERROR",
              "Reserved derivative client_ref collides.",
            );
            created[key] = id("evidence");
          }
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
        if (op.op === "prepare_handoff") {
          const workId = refId(op.work_ref),
            current = changed.get(workId) ?? this.record(workId);
          requireThat(
            current.kind === "work",
            "REFERENCE_TYPE_MISMATCH",
            "Handoff needs Work.",
          );
          requireClaim(workId, op.step_id ?? null, "handoff");
          const w = WorkData.parse(current.data);
          requireThat(
            !op.step_id || w.steps.some((s) => s.step_id === op.step_id),
            "REFERENCE_NOT_FOUND",
            "Handoff step not found.",
          );
          const hid = created[op.client_ref];
          const artifact = {
            handoff_id: hid,
            work_ref: { id: workId, revision: current.revision },
            plan_version: w.plan_version ?? 1,
            step_id: op.step_id ?? null,
            objective: op.objective,
            conditions: op.conditions,
            expected_result: op.expected_result,
            context_refs: op.context_refs,
            message: op.message,
            prepared_at: now,
            prepared_by: this.context.runtime_id,
            transport_state: "prepared_not_sent",
            source_refs: Object.values(bindings),
          };
          handoffs.push({ id: hid, json: JSON.stringify(artifact) });
          continue;
        }
        if (op.op === "transition_work" || op.op === "transition_step") {
          const original = guarded(op.ref.id),
            current = changed.get(op.ref.id) ?? original;
          requireThat(
            current.kind === "work",
            "REFERENCE_TYPE_MISMATCH",
            "Lifecycle target must be Work.",
          );
          const w = WorkData.parse(current.data);
          if (op.op === "transition_work") {
            requireThat(
              w.status !== op.status,
              "INVALID_TRANSITION",
              "Transition must change Work state.",
            );
            if (
              w.status === "paused" ||
              terminal(w.status) ||
              op.status === "paused" ||
              op.status === "cancelled"
            )
              checkDecision(op.decision_source_handle);
            if (terminal(w.status))
              requireThat(
                ["active", "waiting", "blocked", "draft"].includes(op.status),
                "INVALID_TRANSITION",
                "Explicit reopen returns to an unfinished state.",
              );
            else if (w.status === "draft")
              requireThat(
                ["active", "waiting", "paused", "cancelled", "done"].includes(
                  op.status,
                ),
                "INVALID_TRANSITION",
                "Invalid draft transition.",
              );
            else if (w.status === "paused")
              requireThat(
                ["active", "waiting", "blocked", "cancelled"].includes(
                  op.status,
                ),
                "INVALID_TRANSITION",
                "Resume explicitly to active/waiting/blocked or cancel.",
              );
            else
              requireThat(
                op.status !== "draft",
                "INVALID_TRANSITION",
                "Open Work cannot silently return to draft.",
              );
            if (op.status === "done") {
              requireClaim(current.id, null, "work");
              w.completion = {
                grounds: op.grounds ?? [],
                recorded_at: now,
                decision_actor: this.context.principal,
              };
            } else w.completion = null;
            w.cancellation =
              op.status === "cancelled"
                ? {
                    reason: op.reason,
                    consequences: op.consequences ?? "",
                    recorded_at: now,
                    decision_actor: this.context.principal,
                  }
                : null;
            w.status = WorkStatus.parse(op.status);
            w.current_state = op.reason;
            if (op.next_action !== undefined) w.next_action = op.next_action;
            if (terminal(op.status)) w.next_action = null;
          } else {
            const step = w.steps.find((s) => s.step_id === op.step_id);
            requireThat(step, "REFERENCE_NOT_FOUND", "Step does not exist.");
            requireThat(
              !terminal(w.status),
              "INVALID_TRANSITION",
              "Reopen Work before executing its steps.",
            );
            if (["done", "skipped", "cancelled"].includes(step.status))
              checkDecision(op.decision_source_handle);
            if (["running", "done"].includes(op.status))
              requireClaim(current.id, op.step_id, "step");
            if (["skipped", "cancelled"].includes(op.status))
              checkDecision(op.decision_source_handle);
            step.status = op.status;
            step.result_refs = op.result_refs ?? step.result_refs;
          }
          stage(current, w);
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
          if (current.kind === "work") {
            const w = WorkData.parse(op.data),
              old = WorkData.parse(current.data);
            protectWorkUpdate(old, w, op, checkDecision);
            requireThat(
              (w.plan_version ?? old.plan_version ?? 1) ===
                (old.plan_version ?? 1),
              "REVISION_CONFLICT",
              "Core assigns plan_version; supply the current version.",
            );
            w.plan_version =
              (old.plan_version ?? 1) +
              (canonical(plan(old)) === canonical(plan(w)) ? 0 : 1);
            op.data = w;
          }
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
          if (op.op === "record_result") {
            const workId = refId(op.work_ref);
            requireClaim(
              workId,
              op.step_id ?? null,
              op.step_id ? "step" : "work",
            );
            const work = WorkData.parse(
              (changed.get(workId) ?? this.record(workId)).data,
            );
            requireThat(
              !op.step_id || work.steps.some((s) => s.step_id === op.step_id),
              "REFERENCE_NOT_FOUND",
              "Generated result step not found.",
            );
            data = {
              source_kind: "generated_artifact",
              source_locator: "core-model-result",
              captured_at: now,
              content_hash: digest(op.content),
              retained_excerpt: op.content,
              blob_ref: null,
              availability: "retained",
              source_language: op.source_language,
              work_ref: {
                id: workId,
                revision: (changed.get(workId) ?? this.record(workId)).revision,
              },
              step_id: op.step_id ?? null,
              plan_version: work.plan_version ?? 1,
              provenance: {
                transport: "model-generated",
                runtime_id: this.context.runtime_id,
                session_id: this.context.session_id,
                source_refs: Object.values(bindings),
              },
              trust_origin: "model-generated-content-not-proof-of-correctness",
            };
          } else if (
            op.op === "import_evidence" ||
            op.op === "receive_handoff"
          ) {
            requireThat(
              request.source_handles.includes(op.source_handle),
              "SOURCE_MISSING",
              "Declare the imported source handle in source_handles.",
            );
            const s = this.sources.get(op.source_handle)!;
            data = {
              source_kind:
                op.op === "receive_handoff" ||
                op.semantic_source_kind === "external_reply"
                  ? "external_reply"
                  : s.blob_ref
                    ? "imported_file"
                    : "observed_input",
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
            if (op.op === "receive_handoff") {
              const h = this.handoff(op.handoff_id).data;
              const current =
                changed.get(h.work_ref.id) ?? guarded(h.work_ref.id);
              guarded(h.work_ref.id);
              const w = WorkData.parse(current.data);
              const stale = this.handoffStale(
                h,
                (ref) => changed.get(refId(ref)) ?? this.record(refId(ref)),
              );
              requireThat(
                !stale ||
                  op.disposition === "late" ||
                  op.disposition === "unrelated",
                "INVALID_TRANSITION",
                "Changed/paused/terminal plans require a late/unrelated reply disposition; content does not resume a plan.",
              );
              requireThat(
                op.accepted_wait_ids.every((waitId) =>
                  w.waits.some((wait) => wait.wait_id === waitId),
                ),
                "REFERENCE_NOT_FOUND",
                "Reply names an unknown wait.",
              );
              data.handoff_reply = {
                handoff_id: op.handoff_id,
                original_work_ref: h.work_ref,
                original_plan_version: h.plan_version,
                current_work_ref: {
                  id: current.id,
                  revision: current.revision,
                },
                current_plan_version: w.plan_version ?? 1,
                comparison: op.comparison,
                disposition: op.disposition,
                useful_content: op.useful_content,
                accepted_wait_ids: op.accepted_wait_ids,
                stale,
              };
            }
            if (op.op === "import_evidence" && s.extraction) {
              data.extraction = s.extraction;
              data.text_derivative_ref = s.extraction.text_blob_ref
                ? { id: created[op.client_ref + "_text"], revision: 1 }
                : null;
              if (s.extraction.text_blob_ref) {
                const derivativeId = created[op.client_ref + "_text"];
                const derivative: RecordRow = {
                  id: derivativeId,
                  kind: "evidence",
                  title: op.title + " — extracted text",
                  body: "Parser-derived text; consult extraction limitations and original source.",
                  revision: 1,
                  created_at: now,
                  updated_at: now,
                  storage: "live",
                  visibility: "workspace",
                  concept_ids: [],
                  origin_activity_id: null,
                  data: {
                    source_kind: "extracted_text",
                    derived_from: { id: recordId, revision: 1 },
                    source_hash: s.blob_ref,
                    content_hash: s.extraction.text_hash,
                    blob_ref: s.extraction.text_blob_ref,
                    retained_excerpt: null,
                    availability: "retained",
                    source_language: op.source_language,
                    parser: s.extraction.parser,
                    parser_version: s.extraction.parser_version,
                    sections: s.extraction.sections,
                    extraction_status: s.extraction.status,
                    warnings: s.extraction.warnings,
                    total_characters: s.extraction.total_characters,
                  },
                };
                changed.set(derivativeId, derivative);
                before[derivativeId] = null;
              }
            }
          } else {
            data = op.data;
            if (op.kind === "work") {
              const w = WorkData.parse(data);
              requireThat(
                !terminal(w.status) &&
                  w.completion === null &&
                  !w.cancellation &&
                  w.steps.every(
                    (s) => s.status === "todo" && s.result_refs.length === 0,
                  ),
                "INVALID_TRANSITION",
                "Create unfinished Work and todo steps; use guarded transitions for execution/completion.",
              );
              w.plan_version = 1;
              data = w;
            }
          }
          changed.set(recordId, {
            id: recordId,
            kind:
              op.op === "import_evidence" ||
              op.op === "receive_handoff" ||
              op.op === "record_result"
                ? "evidence"
                : op.kind,
            title: op.title,
            body:
              op.op === "import_evidence" ||
              op.op === "receive_handoff" ||
              op.op === "record_result"
                ? null
                : (op.body ?? null),
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
            : changed.get(r.id)?.revision === r.revision
              ? changed.get(r.id)!
              : this.record(r.id, r.revision);
        requireThat(
          !kind || result.kind === kind,
          "REFERENCE_TYPE_MISMATCH",
          "Reference target has the wrong kind.",
        );
        return result;
      };
      const guardedIfExisting = (recordId: string) => {
        if (before[recordId] !== null) guarded(recordId);
      };
      for (const r of changed.values()) {
        if (r.kind === "activity") ActivityData.parse(r.data);
        if (r.kind === "work") {
          const w = WorkData.parse(r.data);
          // Pin technical completion grounds to the exact final addressed revision.
          if (w.completion)
            for (const ground of w.completion.grounds)
              ground.evidence_refs = ground.evidence_refs.map((ref) => {
                const target = get(ref);
                if ("id" in ref && ref.revision !== undefined) return ref;
                guardedIfExisting(target.id);
                return { id: target.id, revision: target.revision };
              });
          r.data = w;
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
      const all = this.storage
        .all<{ json: string }>("SELECT json FROM records")
        .map(unpack);
      const final = [
        ...all.filter((r) => !changed.has(r.id)),
        ...changed.values(),
      ];
      validateWorks(final, get, (ref, workId) => {
        // A prepared message already has one immutable address. Reuse it only
        // as step-result grounds; do not invent an Evidence copy or widen the
        // record resolver used by input waits, Knowledge and completion criteria.
        const r = ref as { id: string; revision?: number };
        const row =
          handoffs.find((h) => h.id === r.id) ??
          this.storage.get<{ json: string }>(
            "SELECT json FROM handoffs WHERE id=?",
            r.id,
          );
        if (!row) {
          get(ref);
          return;
        }
        const h = JSON.parse(row.json);
        requireThat(
          h.work_ref.id === workId && h.transport_state === "prepared_not_sent",
          "REFERENCE_TYPE_MISMATCH",
          "Handoff step grounds must be a prepared message for this Work.",
        );
        requireThat(
          r.revision === undefined || r.revision === 1,
          "REFERENCE_NOT_FOUND",
          "An immutable handoff has only revision 1.",
        );
        get(h.work_ref, "work");
      });
      for (const h of handoffs) {
        const data = JSON.parse(h.json);
        get(data.work_ref, "work");
        const finalWork = WorkData.parse(
          get({ id: data.work_ref.id }, "work").data,
        );
        requireThat(
          (finalWork.plan_version ?? 1) === data.plan_version &&
            !["paused", "done", "cancelled"].includes(finalWork.status),
          "INVALID_TRANSITION",
          "Prepared handoff no longer matches the final executable plan.",
        );
        for (const ref of data.context_refs) get(ref);
        data.context_refs = data.context_refs.map((ref: unknown) => {
          const r = get(ref);
          if (!(ref as { revision?: number }).revision && r.kind !== "evidence")
            guardedIfExisting(r.id);
          return { id: r.id, revision: r.revision };
        });
        data.plan_snapshot = [];
        let work = get({ id: data.work_ref.id }, "work");
        for (;;) {
          requireThat(
            !["paused", "cancelled", "done"].includes(
              work.data.status as string,
            ),
            "INVALID_TRANSITION",
            "An ancestor suppresses handoff preparation.",
          );
          data.plan_snapshot.push({
            id: work.id,
            revision: work.revision,
            plan_version: work.data.plan_version ?? 1,
            status: work.data.status,
          });
          guardedIfExisting(work.id);
          if (!work.data.parent_work_id) break;
          work = get(work.data.parent_work_id, "work");
        }
        h.json = JSON.stringify(data);
      }
      for (const r of changed.values()) {
        if (r.kind === "work") {
          const w = WorkData.parse(r.data);
          const old = before[r.id]
            ? WorkData.parse(this.record(r.id).data)
            : undefined;
          for (const s of w.steps)
            if (
              ["running", "done"].includes(s.status) &&
              old?.steps.find((x) => x.step_id === s.step_id)?.status !==
                s.status
            ) {
              if (s.child_work_id) guardedIfExisting(refId(s.child_work_id));
              for (const d of s.depends_on)
                if ("work_ref" in d) guardedIfExisting(refId(d.work_ref));
            }
          for (const row of this.storage.all<{ json: string }>(
            "SELECT json FROM claims WHERE work_id=?",
            r.id,
          )) {
            const claim = JSON.parse(row.json);
            requireThat(
              claim.state !== "active" ||
                (claim.session_id === this.context.session_id &&
                  claim.runtime_id === this.context.runtime_id),
              "WORK_IN_USE",
              "A different runtime has an unresolved claim on this Work.",
            );
          }
        }
        const reply = r.data.handoff_reply as
          | {
              current_work_ref: { id: string; revision: number };
              accepted_wait_ids: string[];
              original_plan_version: number;
              current_plan_version: number;
              stale: boolean;
              disposition: string;
            }
          | undefined;
        if (reply) {
          const w = WorkData.parse(
            get({ id: reply.current_work_ref.id }, "work").data,
          );
          const current = get({ id: reply.current_work_ref.id }, "work");
          reply.current_work_ref = {
            id: current.id,
            revision: current.revision,
          };
          reply.current_plan_version = w.plan_version ?? 1;
          const h = this.handoff(
            (r.data.handoff_reply as { handoff_id: string }).handoff_id,
          ).data;
          reply.stale = this.handoffStale(h, get);
          requireThat(
            !reply.stale || ["late", "unrelated"].includes(reply.disposition),
            "INVALID_TRANSITION",
            "Final transaction changed/paused/terminal plan requires a late/unrelated reply disposition.",
          );
          for (const waitId of reply.accepted_wait_ids)
            requireThat(
              w.waits
                .find((wait) => wait.wait_id === waitId)
                ?.received_refs.some((ref) => refId(ref) === r.id),
              "VALIDATION_ERROR",
              "Accepted reply portions must be attached to the corresponding waits in this transaction.",
            );
        }
        if (
          r.kind === "evidence" &&
          typeof r.data.blob_ref === "string" &&
          !r.data.extraction
        )
          this.storage.readMaterial(r.data.blob_ref);
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
      for (const token of consumed) {
        const claim = JSON.parse(
          this.storage.get<{ json: string }>(
            "SELECT json FROM claims WHERE token=?",
            token,
          )!.json,
        );
        let work = get({ id: claim.work_id }, "work");
        for (;;) {
          requireThat(
            !["paused", "cancelled"].includes(work.data.status as string),
            "INVALID_TRANSITION",
            "The final linked plan suppresses this managed execution.",
          );
          if (work.data.activity_id)
            requireThat(
              get(work.data.activity_id, "activity").data.status === "active",
              "INVALID_TRANSITION",
              "The final Activity suppresses this managed execution.",
            );
          if (!work.data.parent_work_id) break;
          work = get(work.data.parent_work_id, "work");
        }
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
        schema_version: this.storage.workspace.schema_version,
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
      for (const handoff of handoffs)
        this.storage.run(
          "INSERT INTO handoffs(id,json) VALUES(?,?)",
          handoff.id,
          handoff.json,
        );
      for (const token of consumed) {
        const claim = JSON.parse(
          this.storage.get<{ json: string }>(
            "SELECT json FROM claims WHERE token=?",
            token,
          )!.json,
        );
        claim.state = "consumed";
        claim.receipt_request_id = request.request_id;
        this.storage.run(
          "UPDATE claims SET json=? WHERE token=?",
          JSON.stringify(claim),
          token,
        );
      }
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

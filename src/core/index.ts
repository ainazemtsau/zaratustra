import { Lifecycle } from "./lifecycle.ts";
import { Sleep } from "./sleep.ts";
export { SleepSchemaSQL, validateSleep, sleepGrounds } from "./sleep.ts";
export {
  LifecycleSchemaSQL,
  StorageActionSchema,
  TombstoneSchema,
} from "./lifecycle.ts";
import { createHash, randomUUID } from "node:crypto";
import {
  ActivityData,
  canonical,
  CommitSchema,
  CoreError,
  KnowledgeData,
  ConceptData,
  EntityData,
  MethodData,
  RunData,
  requireThat,
  WorkData,
  WorkStatus,
} from "./contracts.ts";
import {
  Memory,
  addressedIds,
  addressedRefs,
  refreshMemory,
  validateMemory,
} from "./memory.ts";
import {
  ExperienceTransaction,
  exactRef,
  methodClosure,
  methodUpdate,
  validateMethods,
} from "./experience.ts";
import type { CursorState } from "./memory.ts";
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
  AddressedRow,
} from "./contracts.ts";
import { Approvals } from "./approval.ts";
import { Effects, FileEffectSchema } from "./effects.ts";
import type { FileEffect } from "./effects.ts";
export { Approvals, ApprovalSchemaSQL, APPROVAL_POLICY } from "./approval.ts";
export { NativeArguments, FileEffectSchema } from "./effects.ts";
export type { FileEffect } from "./effects.ts";
export * from "./contracts.ts";
export { validateWorks } from "./work.ts";
export { ExperienceSchemaSQL, validateMethods } from "./experience.ts";
export {
  MemorySchemaSQL,
  refreshMemory,
  validateMemory,
  SearchSchema,
  literalFTS,
} from "./memory.ts";

export const digest = (value: string | Uint8Array) =>
  createHash("sha256").update(value).digest("hex");
const id = (prefix: string) => prefix + "-" + randomUUID();
const unpack = (row: { json: string }) => JSON.parse(row.json) as RecordRow;
/** Shared exact generated values for domain merge and its native presentation. */
export const mergedAliases = (from: RecordRow, to: RecordRow) => [
  ...new Set([
    ...((to.data.aliases as string[]) ?? []),
    from.title,
    ...((from.data.aliases as string[]) ?? []),
  ]),
];
export class Core {
  private sources = new Map<string, Source>();
  private _approvals?: Approvals;
  get approvals() {
    this.authorize();
    return (this._approvals ??= new Approvals(
      this.storage,
      this.context,
      (v) => this.memory.technical(v),
      (id) => this.addressed(id).revision,
    ));
  }
  private get effects() {
    return new Effects(this.storage, this.context, this.approvals, (v) =>
      this.memory.technical(v),
    );
  }
  private previewExact(
    request: ReturnType<typeof CommitSchema.parse>,
    bindings?: Record<string, string>,
  ) {
    const exact = JSON.parse(JSON.stringify(request)) as JsonObject;
    delete exact.preview_ref;
    const stable = (h: string) => {
      const s = this.sources.get(h);
      return s &&
        s.workspace_id === this.context.workspace_id &&
        s.epoch === this.context.epoch
        ? s.source_ref
        : bindings?.[h];
    };
    exact.source_handles = request.source_handles
      .map((h) => {
        const ref = stable(h);
        requireThat(
          ref,
          "SOURCE_EXPIRED",
          "Preview needs current exact captured sources.",
        );
        return ref;
      })
      .sort();
    const walk = (v: unknown): unknown => {
      if (Array.isArray(v)) return v.map(walk);
      if (v && typeof v === "object")
        return Object.fromEntries(
          Object.entries(v).map(([k, x]) => [
            k,
            ["source_handle", "decision_source_handle"].includes(k) &&
            typeof x === "string"
              ? (stable(x) ?? null)
              : walk(x),
          ]),
        );
      return v;
    };
    exact.ops = walk(request.ops);
    return exact;
  }
  private previewAccess(before: { id: string }[]) {
    return before.map((r) => ({
      id: r.id,
      restricted: this.memory.isRestricted(r.id),
    }));
  }
  prepareCommit(
    input: unknown,
    consequence: string,
    alternatives: string,
    seconds?: number,
  ) {
    this.authorize(true);
    this.memory.barrier();
    const request = CommitSchema.parse(input);
    const dependencies = new Map<string, number>();
    for (const ref of addressedRefs(request)) {
      if (
        this.storage.get("SELECT id FROM addressed_current WHERE id=?", ref.id)
      ) {
        const current = this.addressed(ref.id);
        const updated = request.ops.some(
          (op) => "ref" in op && op.ref.id === ref.id,
        );
        const future =
          updated &&
          (ref.revision === current.revision + 1 ||
            (current.kind === "method" &&
              ref.content_version ===
                Number(current.data.content_version) + 1));
        const row = future ? current : this.addressed(ref.id, ref.revision);
        dependencies.set(ref.id, this.addressed(ref.id).revision);
        requireThat(
          future ||
            !ref.content_version ||
            row.data.content_version === ref.content_version,
          "REFERENCE_TYPE_MISMATCH",
          "Method version mismatch.",
        );
      } else
        requireThat(
          false,
          "REFERENCE_NOT_FOUND",
          "Preview target unavailable.",
        );
    }
    for (const g of request.guards)
      requireThat(
        dependencies.get(g.ref.id) === g.expected_revision,
        "REVISION_CONFLICT",
        "Preview guard changed.",
      );
    const before = [...dependencies].map(([id, revision]) =>
      this.addressed(id, revision),
    );
    const exact = this.previewExact(request);
    // Exact before values and rights are immutable, and are also independently checked at consumption.
    exact.before = before;
    exact.effective_access = this.previewAccess(before);
    exact.assigned_method_versions = request.ops
      .filter(
        (op) =>
          op.op === "revise_method" ||
          (op.op === "update_record" &&
            this.record(op.ref.id).kind === "method"),
      )
      .map((op) => {
        const update = op as {
          ref: { id: string };
          data: JsonObject;
          body?: string | null;
        };
        const row = this.record(update.ref.id);
        return {
          id: row.id,
          content_version: methodUpdate(
            row,
            update.data,
            update.body === undefined ? row.body : update.body,
          ).content_version,
        };
      });
    return this.approvals.draft(
      "commit",
      exact,
      [...dependencies].map(([id, revision]) => ({ id, revision })),
      consequence,
      alternatives,
      seconds,
    );
  }
  prepareFile(
    input: unknown,
    consequence: string,
    alternatives: string,
    seconds?: number,
  ) {
    this.authorize(true);
    const e = FileEffectSchema.parse(input);
    requireThat(
      e.work_ref ? !e.independent_basis : !!e.independent_basis,
      "VALIDATION_ERROR",
      "Bind a Work/step or explain why this is an independent new action.",
    );
    requireThat(
      digest(e.final_text) === e.final_hash &&
        Buffer.byteLength(e.final_text) === e.final_length,
      "VALIDATION_ERROR",
      "Final native bytes/digest mismatch.",
    );
    requireThat(
      !this.storage.get(
        "SELECT request_id FROM intents WHERE request_id=?",
        e.request_id,
      ),
      "UNKNOWN_EFFECT",
      "Attempt exists; inspect the operation and current bytes before any new decision.",
    );
    requireThat(
      e.work_ref || !e.step_id,
      "VALIDATION_ERROR",
      "A step association requires its Work.",
    );
    const deps = [e.work_ref, e.method_export?.method_ref]
      .filter(Boolean)
      .map((r) => {
        const row = this.record(r!.id, r!.revision);
        return { id: row.id, revision: this.record(row.id).revision };
      });
    for (const g of e.material_guards ?? []) {
      const row = this.addressed(g.ref.id);
      requireThat(
        row.revision === g.expected_revision,
        "REVISION_CONFLICT",
        "File material guard changed.",
      );
      if (!deps.some((d) => d.id === row.id))
        deps.push({ id: row.id, revision: row.revision });
    }
    if (e.work_ref) {
      this.assertReconciled(e.work_ref.id, e.step_id);
      const w = this.record(e.work_ref.id);
      requireThat(
        w.kind === "work" && w.revision === e.work_ref.revision,
        "REVISION_CONFLICT",
        "Managed file Work premise changed.",
      );
      const foreign = this.storage
        .all<{ json: string }>("SELECT json FROM claims WHERE work_id=?", w.id)
        .map((r) => JSON.parse(r.json))
        .some(
          (c) =>
            c.epoch === this.context.epoch &&
            c.state === "active" &&
            (c.runtime_id !== this.context.runtime_id ||
              c.session_id !== this.context.session_id),
        );
      requireThat(
        !foreign,
        "WORK_IN_USE",
        "A different runtime has an unresolved Work claim; inspect and reconcile it before a new managed effect.",
      );
      e.work_snapshot = {
        title: w.title,
        objective: w.data.objective as string,
        plan_version: (w.data.plan_version as number) ?? 1,
        step_intent: e.step_id
          ? (WorkData.parse(w.data).steps.find((s) => s.step_id === e.step_id)
              ?.intent ?? null)
          : null,
      };
      requireThat(
        w.data.status === "active",
        "INVALID_TRANSITION",
        "Activate/reconsider Work before a managed file effect.",
      );
      if (e.step_id)
        requireThat(
          WorkData.parse(w.data).steps.find((s) => s.step_id === e.step_id)
            ?.status === "running",
          "INVALID_TRANSITION",
          "Start the claimed step with satisfied dependencies before its native file action.",
        );
      for (const ref of WorkData.parse(w.data).context_refs) {
        if ("id" in ref) {
          const current = this.addressed(ref.id);
          if (!deps.some((d) => d.id === current.id))
            deps.push({ id: current.id, revision: current.revision });
        }
      }
      this.assertExecutable(w.id);
      requireThat(
        !e.step_id ||
          WorkData.parse(w.data).steps.some((s) => s.step_id === e.step_id),
        "REFERENCE_NOT_FOUND",
        "Step unavailable.",
      );
      for (const g of this.assertExecutable(w.id)) {
        if (!deps.some((d) => d.id === g.id)) deps.push(g);
        const activity = this.record(g.id).data.activity_id as {
          id: string;
        } | null;
        if (activity && !deps.some((d) => d.id === activity.id))
          deps.push({
            id: activity.id,
            revision: this.record(activity.id).revision,
          });
      }
    }
    if (e.method_export) {
      const m = this.record(
        e.method_export.method_ref.id,
        e.method_export.method_ref.revision,
        false,
        e.method_export.method_ref.content_version,
      );
      e.method_snapshot = {
        title: m.title,
        body: m.body,
        data: MethodData.parse(m.data),
      };
      requireThat(
        m.kind === "method" &&
          e.method_export.content_hash === digest(canonical(m.data)) &&
          e.method_export.export_hash === e.final_hash &&
          e.tool === "write",
        "VALIDATION_ERROR",
        "Textual export must bind exact canonical Method content and native final bytes.",
      );
    }
    if (e.retry_of) {
      const prior = this.effects.read(e.retry_of);
      requireThat(
        e.retry_risk && prior.payload.target === e.target,
        "UNKNOWN_EFFECT",
        "Risky repeat requires a linked prior target and explicit consequence.",
      );
    }
    return this.approvals.draft(
      "managed_file",
      e,
      deps,
      consequence,
      alternatives,
      seconds,
    );
  }
  interruptFiles(reason: string, previousRuntime = false) {
    this.authorize(true);
    this.effects.interrupt(reason, previousRuntime);
  }
  fileReplay(
    requestId: string,
    tool: string,
    args: unknown,
    declared?: JsonObject,
  ) {
    this.authorize();
    if (
      !this.storage.get(
        "SELECT request_id FROM intents WHERE request_id=?",
        requestId,
      )
    )
      return null;
    const e = this.effects.read(requestId);
    requireThat(
      e.payload.tool === tool &&
        canonical(e.payload.arguments) === canonical(args),
      "IDEMPOTENCY_CONFLICT",
      "Attempt ID belongs to different native arguments.",
    );
    if (declared)
      for (const [key, value] of Object.entries(declared))
        requireThat(
          canonical(
            (e.payload as unknown as JsonObject)[key] ??
              (key === "material_guards" ? [] : null),
          ) === canonical(value ?? null),
          "IDEMPOTENCY_CONFLICT",
          "Attempt ID belongs to a different target, Work/step or material binding.",
        );
    return { replayed: true, dispatch: false, ...e };
  }
  dispatchFile(effect: FileEffect, preview: string, call: string) {
    this.authorize(true);
    if (effect.work_ref)
      this.assertReconciled(effect.work_ref.id, effect.step_id);
    return this.effects.dispatch(effect, preview, call);
  }
  inspectFile(request: string) {
    this.authorize();
    return this.effects.read(request);
  }
  observeFile(
    request: string,
    observation: JsonObject,
    call?: { id: string; runtime_id: string; is_error: boolean },
  ) {
    this.authorize(true);
    return this.effects.observe(request, observation, call);
  }
  private requiresApproval(request: ReturnType<typeof CommitSchema.parse>) {
    if (this.sleep.needsApproval(request)) return true;
    const catalogUpdates = request.ops.filter(
      (op) =>
        op.op === "update_record" &&
        (op.concept_ids !== undefined ||
          (this.record(op.ref.id).kind === "concept" &&
            canonical(this.record(op.ref.id).data.broader_ids) !==
              canonical((op.data as JsonObject).broader_ids))),
    );
    if (catalogUpdates.length > 1) return true;
    return request.ops.some((op) => {
      if (
        ["merge_identity", "merge_activity", "reorganize_catalog"].includes(
          op.op,
        )
      )
        return true;
      if (
        op.op === "revise_method" &&
        request.source_handles.some(
          (h) => this.sources.get(h)?.transport === "file",
        )
      )
        return true;
      if (op.op === "transition_work" && op.status === "cancelled") return true;
      if (op.op === "update_record") {
        const r = this.record(op.ref.id);
        if (r.kind === "activity")
          return canonical(r.data) !== canonical(op.data);
        if (r.kind === "work")
          return [
            "objective",
            "priority",
            "acceptance",
            "activity_id",
            "parent_work_id",
            "required_for_parent",
          ].some(
            (k) =>
              canonical(r.data[k] ?? null) !==
              canonical((op.data as JsonObject)[k] ?? null),
          );
      }
      return false;
    });
  }
  methodExport(recordId: string, contentVersion?: number, revision?: number) {
    this.authorize();
    const m = this.record(recordId, revision, false, contentVersion);
    requireThat(
      m.storage !== "tombstone",
      "CONTENT_NOT_RETAINED",
      "Method body is not retained.",
    );
    requireThat(
      m.kind === "method",
      "REFERENCE_TYPE_MISMATCH",
      "Only textual Methods can be exported.",
    );
    const ref = {
      id: m.id,
      revision: m.revision,
      content_version: m.data.content_version as number,
    };
    const content_hash = digest(canonical(m.data));
    const text = `---\nname: zara-${m.id}\ndescription: ${JSON.stringify(m.title)}\nzaratustra_method_ref: ${canonical(ref)}\nzaratustra_content_sha256: ${content_hash}\n---\n\n# ${m.title}\n\nDerived textual export. Core remains canonical. External edits are drift; explicitly import as a new version or regenerate with a new bound decision. No executable installation or authority is granted.\n\n${m.body ?? ""}\n\n${Object.entries(
      m.data,
    )
      .map(([k, v]) => `## ${k}\n\n${typeof v === "string" ? v : canonical(v)}`)
      .join("\n\n")}\n`;
    requireThat(
      Buffer.byteLength(text) <= 64000,
      "VALIDATION_ERROR",
      "Textual export exceeds the controlled file bound.",
    );
    return { method_ref: ref, content_hash, export_hash: digest(text), text };
  }
  skillExportStatus(target: string, observedHash: string | null) {
    this.authorize();
    const r = this.storage.get<{ json: string }>(
      `SELECT t.json FROM intents t WHERE json_extract(t.json,'$.kind')='managed_file' AND json_extract(t.json,'$.payload.target')=? AND json_extract(t.json,'$.payload.method_export') IS NOT NULL AND ${this.memory.technicalSQL("t")} ORDER BY t.rowid DESC LIMIT 1`,
      target,
    );
    requireThat(
      r,
      "REFERENCE_NOT_FOUND",
      "No accessible managed textual export for this target.",
    );
    const e = JSON.parse(r.json);
    return {
      export_request_id: e.request_id,
      method_export: e.payload.method_export,
      drift: observedHash !== e.payload.final_hash,
      observed_hash: observedHash,
      expected_hash: e.payload.final_hash,
      attempt_state: e.status,
      canonical_method_changed:
        digest(
          canonical(this.record(e.payload.method_export.method_ref.id).data),
        ) !== e.payload.method_export.content_hash,
      export_current:
        e.status === "confirmed" &&
        observedHash === e.payload.final_hash &&
        digest(
          canonical(this.record(e.payload.method_export.method_ref.id).data),
        ) === e.payload.method_export.content_hash,
    };
  }
  private cursors = new Map<string, CursorState>();
  private get memory() {
    return new Memory(this.storage, this.context, this.cursors);
  }
  private get sleep() {
    return new Sleep(
      this.storage,
      this.context,
      (id, revision) => this.addressed(id, revision),
      (id, revision) => this.memory.allowed(id, revision),
    );
  }
  sleepBatch(runId?: string, cursor?: string) {
    this.authorize();
    this.memory.barrier();
    return this.sleep.batch(runId, cursor);
  }
  constructor(
    public storage: StoragePort,
    public context: CallContext,
    private fault?: (point: string) => void,
  ) {}
  private authorize(write = false) {
    this.storage.assertActive?.(this.context.epoch, write);
    for (const source of this.sources.values())
      if (Date.parse(source.captured_at) < Date.now() - 1800000) {
        if (this.context.can_write && !this.storage.readonly)
          this.storage.unpinSource?.(source.handle);
        this.sources.delete(source.handle);
      }
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
      pending_key?: string;
      blob_ref: string;
      byte_length: number;
      locator: string;
      extraction?: Source["extraction"];
    },
    observation?: Source["observation"],
  ) {
    this.authorize();
    requireThat(
      Buffer.byteLength(text) <=
        (material?.extraction ? 32 * 1024 * 1024 : 1024 * 1024),
      "VALIDATION_ERROR",
      "Source exceeds its observed-input or extracted-text bound.",
    );
    const source: Source = {
      workspace_id: this.context.workspace_id,
      epoch: this.context.epoch,
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
        : observation
          ? "pi-tool-result-hook-observed"
          : "pi-input-hook-observed",
      original_keystrokes: false,
      input_integrity:
        transport === "interactive" &&
        this.context.interactive_input?.contract === "first-untransformed"
          ? "trusted_first_untransformed"
          : "observed_stage_only",
      owner_channel_eligible:
        transport === "interactive" &&
        !!this.context.interactive_input &&
        !material &&
        !observation,
      ...(observation ? { observation } : {}),
      byte_length: Buffer.byteLength(text),
      ...material,
    };
    this.sources.set(source.handle, source);
    if (material && this.context.can_write)
      this.storage.pinSource?.(source.handle, [
        material.blob_ref,
        ...(material.extraction?.text_blob_ref
          ? [material.extraction.text_blob_ref]
          : []),
      ]);
    return {
      source_handle: source.handle,
      source_ref: source.source_ref,
      transport,
      channel_identity,
      capture_stage: source.capture_stage,
      content_hash: source.content_hash,
      byte_length: source.byte_length,
      input_integrity: source.input_integrity,
      owner_channel_eligible: source.owner_channel_eligible,
      ...(source.observation ? { observation: source.observation } : {}),
      ...(source.extraction ? { extraction: source.extraction } : {}),
    };
  }
  expireSources() {
    if (this.context.can_write && !this.storage.readonly)
      for (const source of this.sources.values()) {
        try {
          this.storage.unpinSource?.(source.handle);
        } catch {
          /* expired generation cannot mutate pins */
        }
      }
    this.sources.clear();
    this._approvals?.invalidate();
  }
  sequence() {
    this.authorize();
    return this.visibleSequence();
  }
  private domainSequence() {
    return this.storage.get<{ seq: number }>(
      "SELECT coalesce(max(seq),0) AS seq FROM changes",
    )!.seq;
  }
  private record(
    recordId: string,
    revision?: number,
    internal = false,
    contentVersion?: number,
  ) {
    // Authorize current identity before distinguishing a missing historical body.
    // A guessed hidden primary ID must have the same result as an unknown ID.
    if (!internal)
      requireThat(
        this.memory.allowed(recordId),
        "REFERENCE_NOT_FOUND",
        "Requested record/version is unavailable.",
      );
    const row =
      contentVersion !== undefined && revision === undefined
        ? this.storage.get<{ json: string }>(
            "SELECT json FROM revisions WHERE id=? AND json_extract(json,'$.data.content_version')=? ORDER BY revision LIMIT 1",
            recordId,
            contentVersion,
          )
        : revision === undefined
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
      revision === undefined && contentVersion === undefined
        ? "REFERENCE_NOT_FOUND"
        : "CONTENT_NOT_RETAINED",
      "Requested record/version is unavailable.",
    );
    const result = unpack(row);
    if (!internal)
      requireThat(
        this.memory.allowed(recordId, result.revision),
        "REFERENCE_NOT_FOUND",
        "Requested record/version is unavailable.",
      );
    requireThat(
      contentVersion === undefined ||
        (result.kind === "method" &&
          result.data.content_version === contentVersion),
      "REFERENCE_TYPE_MISMATCH",
      "Requested content_version does not match this Method revision.",
    );
    return result;
  }
  private addressed(recordId: string, revision?: number): AddressedRow {
    if (this.storage.get("SELECT id FROM records WHERE id=?", recordId))
      return this.record(recordId, revision);
    requireThat(
      this.memory.allowed(recordId, revision),
      "REFERENCE_NOT_FOUND",
      "Requested record/version is unavailable.",
    );
    const row = this.storage.get<{ json: string }>(
      revision === undefined
        ? "SELECT json FROM experience_rows WHERE id=?"
        : "SELECT json FROM experience_versions WHERE id=? AND revision=?",
      recordId,
      ...(revision === undefined ? [] : [revision]),
    );
    requireThat(
      row,
      "REFERENCE_NOT_FOUND",
      "Requested record/version is unavailable.",
    );
    return JSON.parse(row.json);
  }
  private envelope<T>(data: T) {
    return {
      ok: true,
      workspace_id: this.context.workspace_id,
      schema_version: this.storage.workspace.schema_version,
      snapshot_seq: this.visibleSequence(),
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
        "resources",
        "people",
        "topics",
        "entities",
        "unfiled",
        "relations",
        "methods",
        "runs",
        "evaluations",
        "signals",
        "invocations",
      ].map((view) => ({
        label: view,
        description: "Permitted existing " + view,
        selector: { view },
        has_more: this.memory.browse(view, undefined, 1).has_more,
      })),
      focus: this.focus(),
      applied_filters: { access: "trusted context" },
      generation: this.memory.generation(),
      has_more: false,
      next_cursor: null,
    });
  }
  private visibleSequence() {
    return this.memory.visibleSequence();
  }
  focus() {
    this.authorize();
    const row = this.storage.get<{ json: string }>(
      "SELECT json FROM focus WHERE session_id=?",
      this.context.session_id,
    );
    return row && this.memory.technical(JSON.parse(row.json))
      ? JSON.parse(row.json)
      : null;
  }
  browse(
    view: string,
    recordId?: string,
    limit = 20,
    cursor?: string,
    mode?: string,
  ) {
    this.authorize();
    return this.retrieval(
      "browse",
      { view, recordId, limit, cursor, mode },
      () =>
        this.envelope(this.memory.browse(view, recordId, limit, cursor, mode)),
    );
  }
  private retrieval<T>(operation: string, input: unknown, action: () => T): T {
    const start = performance.now();
    try {
      const result = action();
      const data = (result as { data?: unknown }).data ?? result;
      this.memory.trace(operation, input, data, start);
      return result;
    } catch (e) {
      this.memory.trace(operation, input, null, start, e);
      throw e;
    }
  }
  search(input: unknown) {
    this.authorize();
    return this.retrieval("search", input, () =>
      this.envelope(this.memory.search(input)),
    );
  }
  rebuildIndex() {
    this.authorize(true);
    this.storage.exec("BEGIN IMMEDIATE");
    try {
      // Recreate only derived FTS surfaces; never touch canonical revisions/materials.
      this.storage.exec(
        "DROP TABLE IF EXISTS memory_text; DROP TABLE IF EXISTS memory_names; CREATE VIRTUAL TABLE memory_text USING fts5(text,tokenize='porter unicode61'); CREATE VIRTUAL TABLE memory_names USING fts5(names,tokenize='unicode61 remove_diacritics 0');",
      );
      refreshMemory(this.storage, true);
      this.memory.barrier();
      this.storage.exec("COMMIT");
      return this.envelope({
        rebuilt: true,
        generation: this.memory.generation(),
      });
    } catch (e) {
      this.storage.exec("ROLLBACK");
      throw e;
    }
  }
  diagnostics() {
    this.authorize();
    let index = "checked";
    try {
      this.memory.barrier();
    } catch {
      index = "INDEX_UNAVAILABLE";
    }
    const traces = this.storage
      .all<{
        json: string;
      }>(
        "SELECT json FROM retrieval_trace WHERE access_key=? ORDER BY seq DESC LIMIT 20",
        this.memory.accessKey,
      )
      .map((r) => JSON.parse(r.json))
      .filter((value) => this.memory.technical(value));
    return this.envelope({
      schema_version: this.storage.workspace.schema_version,
      read_only: this.storage.readonly,
      index,
      retrieval_trace: traces,
      trace_bound: 512,
      managed_access: "Trusted personal process; not OS isolation",
    });
  }
  read(
    recordId: string,
    revision?: number,
    range?: { start: number; length: number },
    locator?: string,
    contentVersion?: number,
  ) {
    this.authorize();
    return this.retrieval(
      "read",
      {
        id: recordId,
        revision,
        content_version: contentVersion,
        range,
        locator,
      },
      () => this.readRecord(recordId, revision, range, locator, contentVersion),
    );
  }
  private readRecord(
    recordId: string,
    revision?: number,
    range?: { start: number; length: number },
    locator?: string,
    contentVersion?: number,
  ) {
    const r = this.storage.get("SELECT id FROM records WHERE id=?", recordId)
      ? this.record(recordId, revision, false, contentVersion)
      : this.addressed(recordId, revision);
    requireThat(
      contentVersion === undefined || r.kind === "method",
      "REFERENCE_TYPE_MISMATCH",
      "Only Methods have content_version.",
    );
    if (r.storage === "tombstone") {
      requireThat(
        revision === undefined &&
          contentVersion === undefined &&
          !range &&
          !locator,
        "CONTENT_NOT_RETAINED",
        "The addressed historical body is not retained.",
      );
      return this.envelope(r);
    }
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
    if (
      r.kind === "work" &&
      revision === undefined &&
      this.storage.workspace.schema_version >= 6
    ) {
      const recovery = this.storage
        .all<{
          step_id: string;
          json: string;
        }>(
          "SELECT step_id,json FROM recovery_barriers WHERE work_id=? ORDER BY step_id",
          r.id,
        )
        .map((b) => ({ step_id: b.step_id || null, ...JSON.parse(b.json) }));
      if (recovery.length)
        return this.envelope({
          ...r,
          current_runtime_recovery: {
            epoch: this.context.epoch,
            actions: recovery,
          },
        });
    }
    return this.envelope(r);
  }
  methodBundle(
    recordId: string,
    contentVersion?: number,
    revision?: number,
    limit = 5,
    cursor?: string,
  ) {
    this.authorize();
    requireThat(
      Number.isInteger(limit) && limit >= 1 && limit <= 5,
      "VALIDATION_ERROR",
      "Method bundle body limit is 1..5.",
    );
    return this.retrieval(
      "method_bundle",
      {
        id: recordId,
        content_version: contentVersion,
        revision,
        limit,
        cursor,
      },
      () => {
        const root = this.record(recordId, revision, false, contentVersion);
        requireThat(
          root.storage !== "tombstone",
          "CONTENT_NOT_RETAINED",
          "Method body is not retained.",
        );
        const rows = methodClosure(exactRef(root), (ref, kind) => {
          const p = ref as {
            id: string;
            revision?: number;
            content_version?: number;
          };
          const r = this.record(p.id, p.revision, false, p.content_version);
          requireThat(
            r.storage !== "tombstone",
            "CONTENT_NOT_RETAINED",
            "Required Method/dependency body is not retained.",
          );
          requireThat(
            !kind || r.kind === kind,
            "REFERENCE_TYPE_MISMATCH",
            "Expected Method.",
          );
          return r;
        });
        const filters = { root: exactRef(root), limit },
          generation = this.memory.generation();
        const last = this.memory.cursor(cursor, filters, generation);
        const remaining = rows
          .slice(last)
          .map((r, index) => ({ key: last + index + 1, record: r }));
        let bytes = 0,
          count = 0;
        for (const row of remaining.slice(0, limit)) {
          const size = Buffer.byteLength(JSON.stringify(row));
          if (count && bytes + size > 48000) break;
          bytes += size;
          count++;
        }
        const page = this.memory.page(
          remaining,
          Math.max(1, count),
          filters,
          generation,
          (row) => row.key,
        );
        return this.envelope({
          ...page,
          cards: page.cards.map((row) => row.record),
          selected_versions: rows.map(exactRef),
          root_ref: exactRef(root),
          body_byte_budget: 48000,
          closure_limit: 256,
          meaning:
            "Resolved selection only; reading is not reported application or observed execution.",
        });
      },
    );
  }
  operation(requestId: string) {
    this.authorize();
    const row =
      this.storage.get<{ json: string }>(
        "SELECT json FROM intents WHERE request_id=?",
        requestId,
      ) ??
      this.storage.get<{ json: string }>(
        "SELECT t.json FROM intents t WHERE json_extract(t.json,'$.kind')='managed_file' AND EXISTS(SELECT 1 FROM json_each(t.json,'$.receipt_history') r WHERE json_extract(r.value,'$.receipt_id')=?)",
        requestId,
      );
    requireThat(row, "REFERENCE_NOT_FOUND", "Operation not found.");
    requireThat(
      this.memory.technical(JSON.parse(row.json)),
      "REFERENCE_NOT_FOUND",
      "Operation not found.",
    );
    return this.envelope(this.memory.sanitizeTechnical(JSON.parse(row.json)));
  }
  handoff(handoffId: string) {
    this.authorize();
    const row = this.storage.get<{ json: string }>(
      "SELECT json FROM handoffs WHERE id=?",
      handoffId,
    );
    requireThat(row, "REFERENCE_NOT_FOUND", "Handoff not found.");
    requireThat(
      this.memory.technical(JSON.parse(row.json)),
      "REFERENCE_NOT_FOUND",
      "Handoff not found.",
    );
    const value = JSON.parse(row.json);
    requireThat(
      !value.payload_not_retained,
      "CONTENT_NOT_RETAINED",
      "Handoff body is not retained.",
    );
    return this.envelope(value);
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
        s.workspace_id === this.context.workspace_id &&
        s.epoch === this.context.epoch &&
        s.runtime_id === this.context.runtime_id &&
        s.session_id === this.context.session_id &&
        (s.transport === "interactive" ||
          (s.transport === "rpc" && s.channel_identity !== null)),
      "SOURCE_MISSING",
      "Explicit lifecycle/plan decision needs a current observed interactive source or trusted controller; external Evidence grants no decision authority.",
    );
    return s.source_ref;
  }
  storagePreview(input: unknown, consequence: string, alternatives: string) {
    this.authorize(true);
    return new Lifecycle(
      this.storage,
      this.context,
      () => this.authorize(true),
      (id) => this.record(id),
      this.approvals,
      (id, revision) => this.memory.allowed(id, revision),
      (id) => this.memory.isRestricted(id),
    ).preview(input, consequence, alternatives);
  }
  applyStorage(ref: string) {
    this.authorize(true);
    const result = new Lifecycle(
      this.storage,
      this.context,
      () => this.authorize(true),
      (id) => this.record(id),
      this.approvals,
      (id, revision) => this.memory.allowed(id, revision),
      (id) => this.memory.isRestricted(id),
    ).apply(ref);
    if (result.action === "tombstone") this.expireSources();
    return this.envelope(this.memory.sanitizeTechnical(result));
  }
  private recovery(workId: string, stepId: string | null = null) {
    if (this.storage.workspace.schema_version < 6) return undefined;
    const row = this.storage.get<{ json: string }>(
      "SELECT json FROM recovery_barriers WHERE work_id=? AND step_id=?",
      workId,
      stepId ?? "",
    );
    return row ? (JSON.parse(row.json) as JsonObject) : undefined;
  }
  private assertReconciled(workId: string, stepId: string | null = null) {
    if (this.storage.workspace.schema_version < 6) return;
    // A new step ID is not proof that a restored Work's external effect never
    // happened. A new dependent child also inherits an unresolved ancestor;
    // genuinely independent new Work has no such restored ancestry.
    let barrier = this.recovery(workId, stepId) ?? this.recovery(workId);
    const seen = new Set<string>();
    while (!barrier) {
      requireThat(!seen.has(workId), "GRAPH_CYCLE", "Parent cycle.");
      seen.add(workId);
      const parent = this.record(workId).data.parent_work_id;
      if (!parent) break;
      workId = refId(parent);
      barrier = this.recovery(workId);
    }
    requireThat(
      !barrier ||
        (barrier.epoch === this.context.epoch && barrier.status === "cleared"),
      "RESTORE_RECONCILIATION_REQUIRED",
      "Restored Work/step requires current-world inspection and a named fresh reconciliation decision, even when no receipt exists.",
    );
  }
  private recoveryWrite(workId: string) {
    const r = this.record(workId),
      restricted = this.memory.isRestricted(workId);
    requireThat(
      !restricted || this.context.scopes?.includes("restricted:write"),
      "PERMISSION_DENIED",
      "Restricted write scope required for reconciliation.",
    );
    return r;
  }
  recoveryInspect(
    workId: string,
    stepId: string | null,
    observation: JsonObject,
  ) {
    this.authorize(true);
    const w = this.recoveryWrite(workId);
    requireThat(
      w.kind === "work" &&
        (!stepId ||
          WorkData.parse(w.data).steps.some((s) => s.step_id === stepId)),
      "REFERENCE_NOT_FOUND",
      "Work/step unavailable.",
    );
    requireThat(
      w.visibility !== "restricted" ||
        this.context.scopes?.includes("restricted:write"),
      "PERMISSION_DENIED",
      "Restricted write scope required.",
    );
    const barrier = this.recovery(workId, stepId);
    requireThat(
      barrier && barrier.epoch === this.context.epoch,
      "REFERENCE_NOT_FOUND",
      "No restored barrier for this Work/step.",
    );
    const inspected = {
      ...observation,
      work_revision: w.revision,
      observed_at: new Date().toISOString(),
      writer_attribution: "unknown",
    };
    this.storage.run(
      "UPDATE recovery_barriers SET json=? WHERE work_id=? AND step_id=?",
      JSON.stringify({ ...barrier, inspection: inspected }),
      workId,
      stepId ?? "",
    );
    return this.envelope({
      work_ref: { id: w.id, revision: w.revision },
      step_id: stepId,
      barrier: barrier.status,
      inspection: inspected,
    });
  }
  prepareReconciliation(
    workId: string,
    stepId: string | null,
    disposition: "observed_satisfied" | "risky_repeat",
    expectedHash: string | null,
    explanation: string,
    consequence: string,
    alternatives: string,
  ) {
    this.authorize(true);
    const w = this.recoveryWrite(workId),
      barrier = this.recovery(workId, stepId),
      inspection = barrier?.inspection as JsonObject | undefined;
    requireThat(
      inspection &&
        inspection.work_revision === w.revision &&
        Date.parse(String(inspection.observed_at)) > Date.now() - 300000,
      "RESTORE_RECONCILIATION_REQUIRED",
      "Inspect current output for this exact Work/step first.",
    );
    requireThat(
      disposition !== "observed_satisfied" ||
        (typeof expectedHash === "string" && inspection.hash === expectedHash),
      "UNKNOWN_EFFECT",
      "Observed bytes do not establish the supplied current postcondition; absence never proves non-execution.",
    );
    return this.approvals.draft(
      "reconcile",
      {
        work_ref: { id: w.id, revision: w.revision },
        work_title: w.title,
        step_id: stepId,
        disposition,
        expected_hash: expectedHash,
        explanation,
        inspection,
      },
      [{ id: w.id, revision: w.revision }],
      consequence,
      alternatives,
    );
  }
  finishReconciliation(ref: string, observation: JsonObject) {
    this.authorize(true);
    const p = this.approvals.read(ref),
      e = p.payload.exact,
      w = e.work_ref as { id: string; revision: number },
      step = e.step_id as string | null;
    this.recoveryWrite(w.id);
    const inspected = e.inspection as JsonObject;
    requireThat(
      ["target", "hash", "byte_length", "boundary"].every(
        (k) => canonical(observation[k]) === canonical(inspected[k]),
      ),
      "APPROVAL_STALE",
      "Current output changed since recovery inspection.",
    );
    requireThat(
      canonical(this.recovery(w.id, step)?.inspection) === canonical(inspected),
      "APPROVAL_STALE",
      "Recovery inspection changed.",
    );
    const receipt = {
      request_id: id("reconciliation"),
      kind: "reconciliation",
      epoch: this.context.epoch,
      work_ref: w,
      step_id: step,
      disposition: e.disposition,
      explanation: e.explanation,
      observation,
      writer_attribution: "unknown",
      committed: true,
    };
    this.storage.exec("BEGIN IMMEDIATE");
    try {
      this.authorize(true);
      this.approvals.consume(ref, "reconcile", e, receipt.request_id);
      this.storage.run(
        "UPDATE recovery_barriers SET json=? WHERE work_id=? AND step_id=?",
        JSON.stringify({
          ...this.recovery(w.id, step),
          status: "cleared",
          disposition: e.disposition,
          receipt,
        }),
        w.id,
        step ?? "",
      );
      this.storage.run(
        "INSERT INTO intents VALUES(?,?,?)",
        receipt.request_id,
        digest(canonical(e)),
        JSON.stringify({
          kind: "reconciliation",
          request_id: receipt.request_id,
          epoch: this.context.epoch,
          status: "committed",
          payload: e,
          receipt,
        }),
      );
      this.storage.run(
        "INSERT INTO receipts VALUES(?,?,?,?)",
        receipt.request_id,
        digest(canonical(e)),
        JSON.stringify(receipt),
        "{}",
      );
      this.storage.exec("COMMIT");
      return this.envelope(receipt);
    } catch (err) {
      this.storage.exec("ROLLBACK");
      throw err;
    }
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
        this.assertReconciled(w.id, input.step_id ?? null);
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
              c.epoch === this.context.epoch &&
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
        `SELECT r.json FROM records r WHERE ${this.memory.visibleSQL("r")} AND json_extract(r.json,'$.storage')='live' AND (r.kind='work' OR (r.kind='knowledge' AND json_extract(r.json,'$.data.knowledge_kind')='preference' AND json_extract(r.json,'$.data.state')='current')) ORDER BY json_extract(r.json,'$.updated_at') DESC,r.id LIMIT 21`,
      )
      .map(unpack);
    const items: {
        id: string;
        kind: string;
        revision: number;
        title: string;
        data: JsonObject;
      }[] = [],
      must_read: string[] = [];
    const context_current: {
      id: string;
      revision: number;
      state: unknown;
      historical_revision: number | null;
      content_version?: number;
      historical_content_version?: number | null;
      must_read: boolean;
    }[] = [];
    for (const r of rows.slice(0, 20)) {
      const item = {
        id: r.id,
        kind: r.kind,
        revision: r.revision,
        title: r.title,
        data: r.data,
      };
      if (Buffer.byteLength(JSON.stringify([...items, item])) <= 10000)
        items.push(item);
      else must_read.push(r.id);
      if (r.kind === "work")
        for (const ref of r.data.context_refs as {
          id: string;
          revision?: number;
          content_version?: number;
        }[]) {
          if (!this.memory.allowed(ref.id)) continue;
          const current = this.record(ref.id);
          if (current.kind === "knowledge" || current.kind === "method") {
            if (context_current.length < 20)
              context_current.push({
                id: current.id,
                revision: current.revision,
                state: current.data.state,
                historical_revision: ref.revision ?? null,
                ...(current.kind === "method"
                  ? {
                      content_version: current.data.content_version as number,
                      historical_content_version: ref.content_version ?? null,
                    }
                  : {}),
                must_read: true,
              });
            else must_read.push(r.id);
          }
        }
    }
    const openSignals = this.storage.all<{ json: string }>(
      `SELECT t.json FROM experience_rows t WHERE t.kind='signal' AND json_extract(t.json,'$.data.problem_state') IN ('open','observing') AND ${this.memory.technicalSQL("t")} ORDER BY t.rowid DESC LIMIT 6`,
    );
    // Shared facts are discovered through catalog/search, never silently injected into every prompt.
    const recoveryRequired =
      this.storage.workspace.schema_version >= 6
        ? this.storage
            .all<{
              work_id: string;
              step_id: string;
            }>(
              "SELECT work_id,step_id FROM recovery_barriers WHERE json_extract(json,'$.status')='required' ORDER BY work_id,step_id",
            )
            .filter((r) => this.memory.allowed(r.work_id))
        : [];
    const snapshot = {
      available: true,
      workspace_id: this.context.workspace_id,
      active_epoch: this.context.epoch,
      snapshot_seq: this.visibleSequence(),
      generation: this.memory.generation(),
      focus: this.focus(),
      records: items,
      context_current,
      open_signals: openSignals.slice(0, 5).map((row) => {
        const r = JSON.parse(row.json);
        return {
          id: r.id,
          revision: r.revision,
          state: r.data.problem_state,
          must_read: true,
        };
      }),
      operations_selector: { view: "operations" },
      restore_compatibility:
        "Every restored potentially effectful Work/step requires named reconciliation, including absent receipts. Inspect current output before repeat.",
      recovery_required: recoveryRequired
        .slice(0, 20)
        .map((r) => ({ work_id: r.work_id, step_id: r.step_id || null })),
      recovery_required_has_more: recoveryRequired.length > 20,
      recovery_selector: { view: "work" },
      open_signals_has_more: openSignals.length > 5,
      open_signals_selector: { view: "signals" },
      must_read: [...new Set(must_read)],
      has_more:
        rows.length > 20 ||
        must_read.length > 0 ||
        openSignals.length > 5 ||
        recoveryRequired.length > 20,
      warnings: [
        "Shared memory is not loaded: use catalog/search and read selected claims plus conditions. Historical tool messages may be stale.",
        ...(rows.length > 20 ||
        must_read.length ||
        openSignals.length > 5 ||
        recoveryRequired.length > 20
          ? ["Snapshot incomplete; read must_read refs and catalog."]
          : []),
      ],
      write_mode: this.storage.readonly ? "read-only" : "single-writer",
      data_only: true,
    };
    while (
      Buffer.byteLength(JSON.stringify(snapshot)) > 12000 &&
      snapshot.records.length
    ) {
      snapshot.must_read.push(snapshot.records.pop()!.id);
      snapshot.has_more = true;
    }
    snapshot.must_read = [...new Set(snapshot.must_read)];
    return { ...snapshot, byte_budget: 12288, incomplete: snapshot.has_more };
  }
  commit(input: unknown): Receipt {
    this.authorize(true);
    this.memory.barrier();
    const request = CommitSchema.parse(input);
    let restrictedSource = request.ops.some(
      (op) => "visibility" in op && op.visibility === "restricted",
    );
    for (const recordId of addressedIds(request)) {
      if (
        this.storage.get(
          "SELECT id FROM addressed_current WHERE id=?",
          recordId,
        )
      ) {
        requireThat(
          this.memory.allowed(recordId),
          "REFERENCE_NOT_FOUND",
          "Requested record/version is unavailable.",
        );
        const restricted = this.memory.isRestricted(recordId);
        if (restricted) restrictedSource = true;
        requireThat(
          !restricted || this.context.scopes?.includes("restricted:write"),
          "PERMISSION_DENIED",
          "Restricted writes require trusted setup scope.",
        );
      }
    }
    for (const ref of addressedRefs(request))
      if (
        this.storage.get("SELECT id FROM addressed_current WHERE id=?", ref.id)
      ) {
        const current = this.addressed(ref.id);
        const changesTarget = request.ops.some(
          (op) => "ref" in op && op.ref.id === ref.id,
        );
        // The batch may reference its guarded final version before it exists on disk.
        // The in-transaction resolver and final access index must still validate it.
        if (
          changesTarget &&
          (ref.revision === current.revision + 1 ||
            (current.kind === "method" &&
              ref.content_version ===
                (current.data.content_version as number) + 1))
        )
          continue;
        if (ref.content_version !== undefined)
          this.record(ref.id, ref.revision, false, ref.content_version);
        else
          requireThat(
            this.memory.allowed(ref.id, ref.revision),
            "REFERENCE_NOT_FOUND",
            "Requested record/version is unavailable.",
          );
      }
    requireThat(
      !JSON.stringify(request).includes('"visibility":"restricted"') ||
        this.context.scopes?.includes("restricted:write"),
      "PERMISSION_DENIED",
      "Restricted writes require trusted setup scope.",
    );
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
    const oldIntent = this.storage.get<{ json: string }>(
      "SELECT json FROM intents WHERE request_id=?",
      request.request_id,
    );
    requireThat(
      !oldIntent || this.memory.technical(JSON.parse(oldIntent.json)),
      "REFERENCE_NOT_FOUND",
      "Operation not found.",
    );
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
      const existingIntent = this.storage.get<{ json: string }>(
        "SELECT json FROM intents WHERE request_id=?",
        request.request_id,
      );
      requireThat(
        existingIntent &&
          this.memory.technical(JSON.parse(existingIntent.json)),
        "REFERENCE_NOT_FOUND",
        "Operation not found.",
      );
      requireThat(
        previous.hash === hash,
        "IDEMPOTENCY_CONFLICT",
        "This request ID belongs to a different canonical payload.",
      );
      return this.memory.sanitizeTechnical(
        JSON.parse(previous.json),
      ) as Receipt;
    }
    for (const handle of request.source_handles)
      requireThat(
        this.sources.get(handle)?.workspace_id === this.context.workspace_id &&
          this.sources.get(handle)?.epoch === this.context.epoch &&
          this.sources.get(handle)?.runtime_id === this.context.runtime_id &&
          this.sources.get(handle)?.session_id === this.context.session_id,
        "SOURCE_EXPIRED",
        "New commits require current exact source handles.",
      );
    if (request.preview_ref || this.requiresApproval(request)) {
      const exact = this.previewExact(request, bindings);
      const preview = request.preview_ref
        ? this.approvals.read(request.preview_ref)
        : null;
      exact.before = preview?.payload.exact.before;
      exact.effective_access = this.previewAccess(
        (preview?.payload.exact.before ?? []) as RecordRow[],
      );
      exact.assigned_method_versions =
        preview?.payload.exact.assigned_method_versions;
      this.approvals.verify(request.preview_ref, "commit", exact);
    }
    // Until progress commits, a Sleep preparation capable of reading restricted
    // inputs has unknown inherited sensitivity. A crash/rollback must not leave
    // its prepared text public after its supporting rows disappear.
    const sleepPreparation = request.ops.some(
      (op) => op.op === "start_sleep" || op.op === "sleep_checkpoint",
    );
    const protectedSleepPreparation =
      sleepPreparation && this.context.scopes?.includes("restricted:read");
    const intent = {
      visibility: protectedSleepPreparation
        ? ("restricted" as const)
        : sleepPreparation
          ? ("workspace" as const)
          : undefined,
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
      if (request.preview_ref || this.requiresApproval(request)) {
        const exact = this.previewExact(request, bindings);
        const preview = request.preview_ref
          ? this.approvals.read(request.preview_ref)
          : null;
        exact.before = preview?.payload.exact.before;
        exact.effective_access = this.previewAccess(
          (preview?.payload.exact.before ?? []) as RecordRow[],
        );
        exact.assigned_method_versions =
          preview?.payload.exact.assigned_method_versions;
        this.approvals.consume(
          request.preview_ref,
          "commit",
          exact,
          request.request_id,
        );
      }
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
      const relations: {
        id: string;
        json: string | null;
        previous?: string;
      }[] = [];
      const consumed = new Set<string>();
      const checkDecision = (handle?: string) =>
        request.preview_ref
          ? this.approvals.read(request.preview_ref).answer?.source_ref
          : this.decision(handle, request.source_handles);
      const guarded = (recordId: string) => {
        const current = this.record(recordId);
        requireThat(
          current.storage !== "tombstone",
          "CONTENT_NOT_RETAINED",
          "Removed body cannot be updated through an ordinary mutation.",
        );
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
      // Guards always verify persisted before revisions; merge semantics use the
      // latest staged row so earlier approved edits cannot be silently overwritten.
      const guardedStaged = (recordId: string) => {
        const original = guarded(recordId);
        return changed.get(recordId) ?? original;
      };
      const guardedAddress = (recordId: string) => {
        const current = this.addressed(recordId);
        requireThat(
          request.guards.some(
            (g) =>
              g.ref.id === recordId && g.expected_revision === current.revision,
          ),
          "REVISION_CONFLICT",
          "Relation premises require their exact current revision guards.",
        );
        return current;
      };
      const requireClaim = (
        workId: string,
        stepId: string | null,
        purpose: string,
      ) => {
        const current = guarded(workId);
        this.assertReconciled(workId, stepId);
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
        if (!(current.id in before))
          before[current.id] = this.storage.get(
            "SELECT id FROM records WHERE id=?",
            current.id,
          )
            ? current.revision
            : null;
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
              : op.op === "put_relation"
                ? "relation"
                : op.op === "import_evidence" ||
                    op.op === "receive_handoff" ||
                    op.op === "record_result"
                  ? "evidence"
                  : op.op === "create_record"
                    ? op.kind
                    : op.op === "start_run"
                      ? "run"
                      : op.op === "invoke_method"
                        ? "invocation"
                        : op.op === "record_evaluation"
                          ? "evaluation"
                          : op.op === "open_signal"
                            ? "signal"
                            : "signal_review",
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
          this.addressed(guard.ref.id).revision === guard.expected_revision,
          "REVISION_CONFLICT",
          "A guarded premise changed; read current records.",
        );
      const now = new Date().toISOString();
      const get = (ref: unknown, kind?: string): RecordRow => {
        requireThat(
          ref && typeof ref === "object" && "id" in ref,
          "REFERENCE_NOT_FOUND",
          "A permanent reference is required.",
        );
        const p = ref as {
          id: string;
          revision?: number;
          content_version?: number;
        };
        const staged = changed.get(p.id);
        const result =
          staged &&
          (p.revision === undefined || staged.revision === p.revision) &&
          (p.content_version === undefined ||
            staged.data.content_version === p.content_version)
            ? staged
            : this.record(p.id, p.revision, true, p.content_version);
        requireThat(
          !kind || result.kind === kind,
          "REFERENCE_TYPE_MISMATCH",
          "Reference target has the wrong kind.",
        );
        requireThat(
          p.content_version === undefined || result.kind === "method",
          "REFERENCE_TYPE_MISMATCH",
          "Only Methods have content_version.",
        );
        return result;
      };
      const experience = new ExperienceTransaction(
        this.storage,
        this.context,
        request,
        created,
        changed,
        (ref, kind) => {
          const r = get(ref, kind);
          if (changed.get(r.id)?.revision !== r.revision)
            requireThat(
              this.memory.allowed(r.id, r.revision),
              "REFERENCE_NOT_FOUND",
              "Requested record/version is unavailable.",
            );
          return r;
        },
        stage,
        now,
      );
      let focus: unknown = undefined;
      for (const raw of request.ops) {
        const op = resolve(raw) as typeof raw;
        if (op.op === "start_sleep" || op.op === "sleep_checkpoint") continue;
        if (experience.apply(op)) continue;
        if (op.op === "merge_activity") {
          const from = guardedStaged(op.from_ref.id),
            to = guardedStaged(op.to_ref.id);
          requireThat(
            from.kind === "activity" &&
              to.kind === "activity" &&
              from.id !== to.id &&
              ["active", "paused"].includes(from.data.status as string) &&
              to.data.status === "active",
            "VALIDATION_ERROR",
            "Activity merge needs distinct open source and active target.",
          );
          const members = this.storage
            .all<{
              id: string;
            }>(
              "SELECT id FROM records WHERE kind='work' AND activity_id=? ORDER BY id",
              from.id,
            )
            .map((r) => r.id);
          requireThat(
            canonical(members) ===
              canonical(op.moved_work_refs.map((r) => r.id).sort()),
            "VALIDATION_ERROR",
            "Finite Activity merge must explicitly include every moved Work; incomplete or oversized merges are unavailable.",
          );
          for (const id of members) {
            const w = guarded(id);
            requireThat(
              !changed.has(id),
              "VALIDATION_ERROR",
              "Moved Work target duplicated.",
            );
            stage(w, {
              ...w.data,
              activity_id: { id: to.id },
              plan_version: ((w.data.plan_version as number) ?? 1) + 1,
            });
          }
          const aliases = mergedAliases(from, to);
          requireThat(
            aliases.length <= 30,
            "VALIDATION_ERROR",
            "Activity alias bound exceeded.",
          );
          stage(to, { ...to.data, aliases });
          if (
            from.visibility === "restricted" ||
            to.visibility === "restricted" ||
            this.previewAccess([from, to]).some((a) => a.restricted)
          )
            changed.get(to.id)!.visibility = "restricted";
          stage(from, {
            ...from.data,
            status: "merged",
            redirect_to: { id: to.id },
          });
          continue;
        }
        if (op.op === "merge_identity") {
          const from = guardedStaged(op.from_ref.id),
            to = guardedStaged(op.to_ref.id);
          requireThat(
            from.id !== to.id &&
              from.kind === to.kind &&
              ["concept", "entity"].includes(from.kind) &&
              from.data.status === "active" &&
              to.data.status === "active",
            "VALIDATION_ERROR",
            "Merge needs two distinct active identities of the same supported kind.",
          );
          if (from.kind === "entity")
            requireThat(
              from.data.entity_kind === to.data.entity_kind,
              "REFERENCE_TYPE_MISMATCH",
              "Entity types differ.",
            );
          const aliases = mergedAliases(from, to);
          requireThat(
            aliases.length <= 30,
            "VALIDATION_ERROR",
            "Merged alias limit exceeded; choose a smaller explicit proposal.",
          );
          stage(to, { ...to.data, aliases });
          if (
            from.visibility === "restricted" ||
            to.visibility === "restricted" ||
            this.previewAccess([from, to]).some((a) => a.restricted)
          )
            changed.get(to.id)!.visibility = "restricted";
          stage(from, {
            ...from.data,
            status: "merged",
            redirect_to: { id: to.id },
            ...(from.kind === "concept" ? { broader_ids: [] } : {}),
          });
          continue;
        }
        if (op.op === "reorganize_catalog") {
          requireThat(
            new Set(op.changes.map((c) => c.ref.id)).size === op.changes.length,
            "VALIDATION_ERROR",
            "Catalog targets must be unique.",
          );
          for (const c of op.changes) {
            const current = guarded(c.ref.id);
            requireThat(
              !changed.has(current.id) &&
                (!c.broader_ids || current.kind === "concept"),
              "VALIDATION_ERROR",
              "Catalog target is duplicated or has wrong kind.",
            );
            stage(current, {
              ...current.data,
              ...(c.broader_ids ? { broader_ids: c.broader_ids } : {}),
            });
            const row = changed.get(current.id)!;
            row.title = c.title ?? row.title;
            row.concept_ids = (c.concept_ids ??
              row.concept_ids) as RecordRow["concept_ids"];
          }
          continue;
        }
        if (op.op === "put_relation") {
          relations.push({
            id: created[op.client_ref],
            json: JSON.stringify({
              id: created[op.client_ref],
              relation: op.relation,
              from_ref: op.from_ref,
              to_ref: op.to_ref,
              reason: op.reason,
            }),
          });
          continue;
        }
        if (op.op === "remove_relation") {
          const row = this.storage.get<{ json: string }>(
            "SELECT json FROM relations WHERE id=?",
            op.relation_id,
          );
          requireThat(
            row && this.memory.technical(JSON.parse(row.json)),
            "REFERENCE_NOT_FOUND",
            "Relation not found.",
          );
          const relation = JSON.parse(row.json);
          guardedAddress(relation.from_ref.id);
          guardedAddress(relation.to_ref.id);
          relations.push({
            id: op.relation_id,
            json: null,
            previous: row.json,
          });
          continue;
        }
        if (op.op === "resolve_knowledge") {
          const current = changed.get(op.ref.id) ?? guarded(op.ref.id);
          guarded(op.ref.id);
          requireThat(
            current.kind === "knowledge",
            "REFERENCE_TYPE_MISMATCH",
            "Correction target must be Knowledge.",
          );
          const k = KnowledgeData.parse(current.data);
          k.state = op.state;
          k.resolution = {
            reason: op.reason,
            evidence_refs: op.evidence_refs,
            replacement_refs: op.replacement_refs,
          };
          stage(current, k);
          continue;
        }
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
          if (["concept", "entity", "activity"].includes(current.kind))
            requireThat(
              canonical(current.data.redirect_to ?? null) ===
                canonical((op.data as JsonObject).redirect_to ?? null) &&
                current.data.status !== "merged" &&
                (op.data as JsonObject).status !== "merged",
              "APPROVAL_REQUIRED",
              "Use an exact merge proposal; merged historical identities cannot be reassigned.",
            );
          if (current.kind === "method")
            op.data = methodUpdate(
              current,
              op.data,
              op.body === undefined ? current.body : op.body,
            );
          if (current.kind === "run")
            requireThat(
              canonical(current.data) === canonical(op.data),
              "INVALID_TRANSITION",
              "Run lifecycle/results are managed by start_run/finish_run; ordinary update cannot rewrite an episode.",
            );
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
            concept_ids: (op.concept_ids ??
              current.concept_ids) as RecordRow["concept_ids"],
            origin_activity_id: (op.origin_activity_id === undefined
              ? current.origin_activity_id
              : op.origin_activity_id) as RecordRow["origin_activity_id"],
          });
        } else {
          if (
            op.op !== "record_result" &&
            op.op !== "import_evidence" &&
            op.op !== "receive_handoff" &&
            op.op !== "create_record"
          )
            throw new CoreError("VALIDATION_ERROR", "Unsupported operation.");
          if (
            op.op === "create_record" &&
            ["concept", "entity", "activity"].includes(op.kind)
          )
            requireThat(
              (op.data as JsonObject).status !== "merged" &&
                !(op.data as JsonObject).redirect_to,
              "APPROVAL_REQUIRED",
              "New identities cannot start as redirects.",
            );
          const recordId = created[op.client_ref];
          before[recordId] = null;
          let data: JsonObject;
          if (op.op === "record_result") {
            requireThat(
              op.work_ref || op.run_ref,
              "VALIDATION_ERROR",
              "Result needs a Work or a running Run.",
            );
            const workId = op.work_ref ? refId(op.work_ref) : null;
            if (workId)
              requireClaim(
                workId,
                op.step_id ?? null,
                op.step_id ? "step" : "work",
              );
            const work = workId
              ? WorkData.parse(
                  (changed.get(workId) ?? this.record(workId)).data,
                )
              : null;
            const run = op.run_ref ? get(op.run_ref, "run") : null;
            requireThat(
              !run || get({ id: run.id }, "run").data.execution === "running",
              "INVALID_TRANSITION",
              "Result requires a currently running Run.",
            );
            requireThat(
              !op.step_id || work?.steps.some((s) => s.step_id === op.step_id),
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
              work_ref: workId
                ? {
                    id: workId,
                    revision: (changed.get(workId) ?? this.record(workId))
                      .revision,
                  }
                : null,
              run_ref: run ? exactRef(run) : null,
              step_id: op.step_id ?? null,
              plan_version: work?.plan_version ?? null,
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
                  : s.observation
                    ? "tool_result"
                    : op.op === "import_evidence" && op.semantic_source_kind
                      ? op.semantic_source_kind
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
                  visibility: restrictedSource
                    ? "restricted"
                    : (op.visibility ?? "workspace"),
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
            if (op.kind === "method")
              requireThat(
                MethodData.parse(data).content_version === 1,
                "VALIDATION_ERROR",
                "A new Method starts at content_version 1.",
              );
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
            concept_ids: ("concept_ids" in op
              ? (op.concept_ids ?? [])
              : []) as RecordRow["concept_ids"],
            origin_activity_id: ("origin_activity_id" in op
              ? (op.origin_activity_id ?? null)
              : null) as RecordRow["origin_activity_id"],
            visibility:
              op.op === "import_evidence" && restrictedSource
                ? "restricted"
                : "visibility" in op
                  ? (op.visibility ?? "workspace")
                  : "workspace",
            data,
          });
        }
      }
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
        if (r.kind === "knowledge") KnowledgeData.parse(r.data);
        if (r.kind === "concept") ConceptData.parse(r.data);
        if (r.kind === "entity") EntityData.parse(r.data);
        if (r.kind === "method") {
          const m = MethodData.parse(r.data);
          m.derived_from = m.derived_from.map((ref) =>
            exactRef(get(ref, "method")),
          );
          r.data = m;
          requireThat(
            Buffer.byteLength(JSON.stringify(r)) <= 32000,
            "VALIDATION_ERROR",
            "Method exceeds its 32,000-byte addressed-record limit.",
          );
        }
        if (r.kind === "run") {
          RunData.parse(r.data);
          requireThat(
            Buffer.byteLength(JSON.stringify(r)) <= 32000,
            "VALIDATION_ERROR",
            "Run exceeds its 32,000-byte addressed-record limit.",
          );
        }
      }
      const all = this.storage
        .all<{ json: string }>("SELECT json FROM records")
        .map(unpack);
      const final = [
        ...all.filter((r) => !changed.has(r.id)),
        ...changed.values(),
      ];
      for (const raw of request.ops) {
        if (raw.op !== "merge_activity") continue;
        const op = resolve(raw) as typeof raw;
        requireThat(
          !final.some(
            (r) =>
              r.kind === "work" && refId(r.data.activity_id) === op.from_ref.id,
          ),
          "VALIDATION_ERROR",
          "Final Activity merge cannot leave or introduce current Work in the merged source; list every moved Work in a separate valid finite proposal.",
        );
      }
      validateMemory(final, get);
      validateMethods(final, get);
      for (const r of changed.values()) {
        if (r.kind === "knowledge") {
          const k = KnowledgeData.parse(r.data);
          for (const ref of [
            ...k.evidence_refs,
            ...(k.supersedes_refs ?? []),
            ...(k.representation ? [k.representation.source_ref] : []),
          ]) {
            const target = get(ref);
            if ("id" in ref && ref.revision === undefined) {
              ref.revision = target.revision;
            }
          }
          if (k.resolution) {
            for (const ref of k.resolution.evidence_refs) get(ref, "evidence");
            for (const ref of k.resolution.replacement_refs)
              get(ref, "knowledge");
          }
          r.data = k;
        }
      }
      for (const relation of relations)
        if (relation.json) {
          const rel = JSON.parse(relation.json),
            from = experience.address(rel.from_ref),
            to = experience.address(rel.to_ref);
          requireThat(
            from.id !== to.id,
            "VALIDATION_ERROR",
            "Self navigation relation is not useful.",
          );
          if (["supports", "contradicts"].includes(rel.relation)) {
            requireThat(
              from.kind === "evidence" && to.kind === "knowledge",
              "REFERENCE_TYPE_MISMATCH",
              "Evidence relation requires Evidence to Knowledge.",
            );
            requireThat(
              !(to.data.evidence_refs as { id: string }[]).some(
                (ref) => ref.id === from.id,
              ),
              "VALIDATION_ERROR",
              "Do not duplicate typed Knowledge grounds through a relation.",
            );
          }
          if (rel.relation === "relevant_to")
            requireThat(
              ["activity", "work", "concept"].includes(to.kind),
              "REFERENCE_TYPE_MISMATCH",
              "relevant_to target must be Activity, Work or Concept.",
            );
          if (rel.relation === "derived_from") {
            requireThat(
              ["evidence", "knowledge", "method"].includes(from.kind) &&
                ["evidence", "knowledge", "method", "run"].includes(to.kind),
              "REFERENCE_TYPE_MISMATCH",
              "derived_from connects Evidence/Knowledge/Method to retained source content or a Run; it does not prove execution or causality.",
            );
            const typed = (from.data.derived_from ??
              (from.data.representation as { source_ref?: unknown } | undefined)
                ?.source_ref) as
              | { id?: string }
              | { id?: string }[]
              | undefined;
            requireThat(
              !(Array.isArray(typed) ? typed : typed ? [typed] : []).some(
                (ref) => ref.id === to.id,
              ),
              "VALIDATION_ERROR",
              "Do not duplicate typed derivation through a relation.",
            );
          }
          for (const target of [from, to])
            if (
              this.storage.get(
                "SELECT id FROM addressed_current WHERE id=?",
                target.id,
              )
            )
              guardedAddress(target.id);
          rel.from_ref = exactRef(from);
          rel.to_ref = exactRef(to);
          rel.symmetric = rel.relation === "related";
          relation.json = JSON.stringify(rel);
        }
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
      const sleepOps = request.ops.filter(
        (op) => op.op === "start_sleep" || op.op === "sleep_checkpoint",
      );
      this.sleep.assertBindings([...changed.values()]);
      requireThat(
        sleepOps.length <= 1,
        "VALIDATION_ERROR",
        "One Sleep start/checkpoint per atomic commit.",
      );
      for (const raw of sleepOps) {
        const op = resolve(raw) as typeof raw;
        this.sleep.apply(
          op,
          request,
          (id, revision) =>
            experience.address({ id, ...(revision ? { revision } : {}) }),
          [...changed.values(), ...experience.changed.values()],
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
      experience.write();
      for (const r of experience.changed.values()) revisions[r.id] = r.revision;
      this.fault?.("after_records");
      const seq = this.domainSequence() + 1;
      const transaction_id = id("txn");
      const change = {
        ...(sleepOps.length
          ? {
              sleep_review_ref: (
                resolve(sleepOps[0]) as (typeof sleepOps)[number]
              ).run_ref,
            }
          : {}),
        transaction_id,
        request_id: request.request_id,
        change_seq: seq,
        changed_refs: [...changed.values(), ...experience.changed.values()].map(
          (r) => ({
            id: r.id,
            before_revision: before[r.id] ?? experience.before[r.id] ?? null,
            after_revision: r.revision,
          }),
        ),
        relation_refs: relations.map((r) => ({
          ...JSON.parse(r.json ?? r.previous!),
          state: r.json ? "live" : "removed",
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
      for (const relation of relations) {
        if (relation.json)
          this.storage.run(
            "INSERT INTO relations VALUES(?,?)",
            relation.id,
            relation.json,
          );
        else this.storage.run("DELETE FROM relations WHERE id=?", relation.id);
        this.storage.run(
          "INSERT INTO relation_history VALUES(?,?,?)",
          relation.id,
          seq,
          relation.json ??
            JSON.stringify({
              ...JSON.parse(relation.previous!),
              state: "removed",
            }),
        );
      }
      refreshMemory(this.storage);
      for (const r of [...changed.values(), ...experience.changed.values()]) {
        requireThat(
          this.memory.allowed(r.id),
          "PERMISSION_DENIED",
          "New related data is outside the current managed read scope.",
        );
        const restricted = this.memory.isRestricted(r.id, r.revision);
        restrictedSource ||= restricted;
        requireThat(
          !restricted || this.context.scopes?.includes("restricted:write"),
          "PERMISSION_DENIED",
          "Related restricted writes need trusted setup scope.",
        );
      }
      this.fault?.("after_index");
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
      if (protectedSleepPreparation)
        intent.visibility = restrictedSource ? "restricted" : undefined;
      this.storage.run(
        "UPDATE intents SET json=? WHERE request_id=?",
        JSON.stringify(intent),
        request.request_id,
      );
      for (const handle of request.source_handles) {
        const source = this.sources.get(handle);
        if (
          source?.blob_ref &&
          this.storage.get(
            "SELECT id FROM records WHERE kind='evidence' AND json_extract(json,'$.data.blob_ref')=?",
            source.blob_ref,
          )
        ) {
          this.storage.unpinSource?.(handle);
          if (source.pending_key)
            this.storage.unpinSource?.(source.pending_key);
        }
      }
      this.fault?.("before_commit");
      this.storage.exec("COMMIT");
      this.fault?.("after_commit");
      return this.memory.sanitizeTechnical(receipt);
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
        ? "Input does not match the published runtime schema."
        : "Storage operation failed; inspect current operations before retrying any uncertain commit.",
    retryable: false,
  };
}

export type { PreviewStore, BoundPreview } from "./approval.ts";
export { addressedRefs } from "./memory.ts";

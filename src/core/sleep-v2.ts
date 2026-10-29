import { AsyncLocalStorage } from "node:async_hooks";
import { createHash, randomUUID } from "node:crypto";
import { z } from "zod";
import {
  canonical,
  CommitSchema,
  CoreError,
  requireThat,
} from "./contracts.ts";
import type {
  AddressedRow,
  CallContext,
  CommitRequest,
  JsonObject,
  Receipt,
  StoragePort,
} from "./contracts.ts";
import { DocumentPath, documentText, managedDocument } from "./documents.ts";
import type { FileEffect, EffectRow } from "./effects.ts";

export const SLEEP_LIMITS = Object.freeze({
  cases: 10,
  improvements: 3,
  generations: 20,
  milliseconds: 15 * 60 * 1000,
});
export const SleepV2Collections = [
  { table: "sleep_cycles", keyColumns: ["id"] },
] as const;
export const SleepV2SchemaSQL = `CREATE TABLE IF NOT EXISTS sleep_cycles(id TEXT PRIMARY KEY,json TEXT NOT NULL);
CREATE UNIQUE INDEX IF NOT EXISTS sleep_v2_one_active ON sleep_cycles((1)) WHERE json_extract(json,'$.status') IN ('running','paused','blocked');`;
const ref = z.strictObject({
  id: z.string().min(1).max(4000),
  revision: z.number().int().positive(),
});
export type SleepRef = z.infer<typeof ref>;
const short = z.string().min(1).max(4000);
export const SleepDocumentChangeSchema = z
  .strictObject({
    ref,
    action: z.enum(["update", "rename"]),
    path: DocumentPath.optional(),
    content: z
      .string()
      .max(64000)
      .refine(
        (v) => Buffer.byteLength(v) <= 64000,
        "Document exceeds its UTF-8 byte limit.",
      )
      .optional(),
    title: short.optional(),
  })
  .refine(
    (v) =>
      v.action === "update" ? v.content !== undefined : v.path !== undefined,
    "Document change requires exact replacement content or target path.",
  );
export type SleepDocumentChange = z.infer<typeof SleepDocumentChangeSchema>;
const phase = z.enum([
  "select",
  "read",
  "analyze",
  "propose",
  "validate",
  "apply",
  "future_check",
  "finish",
]);
export const SleepStatus = z.enum([
  "running",
  "paused",
  "blocked",
  "budget_exhausted",
  "completed",
  "cancelled",
  "stale",
]);
export const SleepProposalSchema = z.strictObject({
  id: short,
  reason: short,
  expected_benefit: short,
  limits: short,
  premises: z.array(ref).min(1).max(30),
  request: CommitSchema.nullable(),
  document_change: SleepDocumentChangeSchema.nullable(),
  request_hash: short,
  future_check: z.strictObject({ trigger: short, expected_observation: short }),
  status: z.enum([
    "proposed",
    "validated",
    "applying",
    "applied",
    "rejected",
    "unknown",
  ]),
  validation_reason: z.string().max(4000).nullable(),
  result_refs: z.array(ref).max(30),
  applied_at: z.number().int().nonnegative().optional(),
  native_request_id: short.optional(),
  check_observation: z
    .strictObject({
      refs: z.array(ref).min(1).max(20),
      verdict: z.enum(["helped", "no_help", "unknown"]),
      summary: short,
      observed_at: z.number().int().nonnegative(),
      evidence_basis: z.enum(["observed", "reported", "unverified"]).optional(),
      ground_refs: z.array(ref).max(20).optional(),
    })
    .optional(),
});
export type SleepProposal = z.infer<typeof SleepProposalSchema>;
const StateSchema = z.strictObject({
  format: z.literal(1),
  id: short,
  workspace_id: short,
  epoch: short,
  profile: short,
  owner_principal: short.optional(),
  runtime_id: short,
  activity_id: short.nullable(),
  visibility: z.enum(["workspace", "restricted"]),
  model: z.strictObject({ provider: short, id: short, thinking: short }),
  status: SleepStatus,
  phase,
  revision: z.number().int().positive(),
  started_at: z.number().int().nonnegative(),
  deadline_at: z.number().int().nonnegative(),
  updated_at: z.number().int().nonnegative(),
  generations: z.number().int().min(0).max(20),
  improvements: z.number().int().min(0).max(3),
  cases: z.array(ref).max(10),
  read_refs: z.array(ref).max(100),
  question: z.string().max(4000).nullable(),
  analysis: z
    .strictObject({
      observations: short,
      hypothesis: z.string().max(4000).nullable(),
      counterexamples: z.array(ref).max(20),
      grounds: z.array(ref).min(1).max(30),
    })
    .nullable(),
  proposals: z.array(SleepProposalSchema).max(3),
  outcome: z
    .enum([
      "no_change",
      "insufficient_evidence",
      "applied_unverified",
      "proposal_pending",
      "stopped",
    ])
    .nullable(),
  summary: z.string().max(4000).nullable(),
  continuation: z.string().max(4000).nullable(),
});
export type SleepState = z.infer<typeof StateSchema>;
export interface SleepV2Bindings {
  read(ref: SleepRef | { id: string }): AddressedRow;
  candidates(activityId: string | null): AddressedRow[];
  runtimeState?(runtimeId: string): "alive" | "dead" | "unknown";
  validateProposal?(
    proposal: SleepProposal,
    state: SleepState,
  ): { allowed: boolean; reason: string };
  now?(): number;
}
const hash = (value: unknown) =>
  createHash("sha256").update(canonical(value)).digest("hex");
const sameRef = (a: SleepRef, b: SleepRef) =>
  a.id === b.id && a.revision === b.revision;
const exact = (row: AddressedRow): SleepRef => ({
  id: row.id,
  revision: row.revision,
});
const active = (state: SleepState) =>
  ["running", "paused", "blocked"].includes(state.status);
const profile = (ctx: CallContext) =>
  hash([
    ctx.workspace_id,
    ctx.principal,
    [...(ctx.scopes ?? [])].sort(),
    ctx.can_write,
    ctx.policy_revision ?? null,
  ]);
type Execution = {
  controller: SleepV2;
  runId: string;
  proposalId?: string;
  requestHash?: string;
  coreEntered?: boolean;
  documentEffect?: { requestId: string; digest: string };
};
const execution = new AsyncLocalStorage<Execution>();
export interface PreparedSleepApply {
  readonly state: SleepState;
}
const preparedApplications = new WeakMap<
  PreparedSleepApply,
  { scope: Execution; proposal: SleepProposal }
>();
class SleepNotDispatched extends CoreError {
  constructor(reason: string) {
    super("SLEEP_NOT_DISPATCHED", reason);
  }
}
export const isSleepNotDispatched = (error: unknown) =>
  error instanceof SleepNotDispatched;

/** This guard is effective inside registered SDK execution only. Ordinary concurrent work is independent. */
export function assertSleepMutationAllowed(
  db: StoragePort,
  ctx: CallContext,
  request: CommitRequest,
) {
  if (
    db.workspace.schema_version >= 10 &&
    request.ops.some(
      (op) => op.op === "start_sleep" || op.op === "sleep_checkpoint",
    )
  )
    throw new CoreError(
      "USE_BOUNDED_SLEEP",
      "Use zara_sleep for new bounded reviews; legacy progress remains historical.",
    );
  const scope = execution.getStore();
  if (!scope) return false;
  requireThat(
    scope.controller.storage === db &&
      scope.controller.contextProfile === profile(ctx),
    "PERMISSION_DENIED",
    "Sleep execution context changed.",
  );
  scope.controller.assertApplyPermit(scope.runId, request, scope);
  scope.coreEntered = true;
  return true;
}

/** Native document dispatch has an independent exact delegated authority, never a fabricated user approval. */
export function assertSleepDocumentAllowed(
  db: StoragePort,
  ctx: CallContext,
  effect: FileEffect,
): boolean {
  const scope = execution.getStore();
  if (!scope) return false;
  requireThat(
    scope.controller.storage === db &&
      scope.controller.contextProfile === profile(ctx),
    "PERMISSION_DENIED",
    "Sleep execution context changed.",
  );
  scope.controller.assertDocumentPermit(scope.runId, effect, scope);
  return true;
}
export function sleepDelegationRef(): string | null {
  const scope = execution.getStore();
  return scope?.proposalId ? `sleep:${scope.runId}:${scope.proposalId}` : null;
}

/** Candidate selection is routing, not a semantic verdict. It never scans revisions. */
export function selectSleepCases(
  rows: readonly AddressedRow[],
  activityId: string | null,
  alreadyRead: readonly SleepRef[] = [],
): AddressedRow[] {
  const seen = new Set<string>();
  const eligible = rows.filter((r) => {
    if (
      seen.has(r.id) ||
      r.storage === "tombstone" ||
      alreadyRead.some((p) => sameRef(p, exact(r)))
    )
      return false;
    seen.add(r.id);
    const data = r.data;
    const bound =
      typeof data.activity_id === "object" && data.activity_id
        ? (data.activity_id as { id?: string }).id
        : null;
    const origin =
      typeof r.origin_activity_id === "object" && r.origin_activity_id
        ? r.origin_activity_id.id
        : null;
    if (
      activityId &&
      bound !== activityId &&
      origin !== activityId &&
      r.kind !== "knowledge"
    )
      return false;
    if (r.kind === "signal")
      return ["open", "observing"].includes(String(data.problem_state));
    if (r.kind === "work")
      return (
        ["blocked", "waiting"].includes(String(data.status)) &&
        data.review_run_ref === undefined
      );
    if (r.kind === "knowledge")
      return ["current", "tentative", "contested"].includes(String(data.state));
    if (r.kind === "run")
      return (
        data.mode !== "sleep" &&
        (data.execution === "failed" ||
          data.memory_purpose === "useful_experience")
      );
    return false;
  });
  const rank = (r: AddressedRow) =>
    r.kind === "signal" ? 0 : r.kind === "work" ? 1 : r.kind === "run" ? 2 : 3;
  return eligible
    .sort(
      (a, b) =>
        rank(a) - rank(b) ||
        String(b.updated_at).localeCompare(String(a.updated_at)) ||
        a.id.localeCompare(b.id),
    )
    .slice(0, SLEEP_LIMITS.cases);
}

/** Conservative default delegation. Broader document changes need the existing authorized adapter. */
export function defaultSleepProposalPolicy(
  proposal: SleepProposal,
  state: SleepState,
  read: SleepV2Bindings["read"],
): { allowed: boolean; reason: string } {
  if (proposal.document_change) {
    const change = proposal.document_change;
    const row = read(change.ref),
      document = row.data.document as { state?: string } | undefined;
    const activity = state.activity_id ? read({ id: state.activity_id }) : null;
    const refs = (
      activity?.data.contract as
        | { document_refs?: { id: string }[] }
        | undefined
    )?.document_refs;
    if (
      row.kind !== "entity" ||
      !document ||
      document.state !== "active" ||
      !refs?.some((r) => r.id === row.id)
    )
      return {
        allowed: false,
        reason:
          "Automatic document changes require an active explicitly local managed document.",
      };
    return {
      allowed: true,
      reason:
        "Reversible local document change; native adapter must validate exact bytes/path/versions and delegated authority.",
    };
  }
  if (!proposal.request)
    return { allowed: false, reason: "No applicable proposal payload." };
  const known = (id: string) => proposal.premises.some((p) => p.id === id);
  const idOf = (p: unknown) =>
    p && typeof p === "object" && "id" in p ? String(p.id) : null;
  for (const op of proposal.request.ops) {
    if (op.op === "put_relation") {
      if (![idOf(op.from_ref), idOf(op.to_ref)].every((id) => id && known(id)))
        return {
          allowed: false,
          reason: "Relations need read exact premises.",
        };
      continue;
    }
    if (op.op === "create_record" && op.kind === "knowledge") {
      const data = op.data as JsonObject;
      if (
        data.state !== "tentative" ||
        data.basis !== "inference" ||
        data.knowledge_kind !== "hypothesis"
      )
        return {
          allowed: false,
          reason:
            "Automatic new knowledge must remain an explicitly tentative hypothesis.",
        };
      const grounds = data.evidence_refs as unknown[];
      if (
        !grounds?.length ||
        !grounds.every((p) => {
          const id = idOf(p);
          return id && known(id) && read({ id }).kind === "evidence";
        })
      )
        return {
          allowed: false,
          reason:
            "A hypothesis needs read retained Evidence; no invented observations.",
        };
      continue;
    }
    if (
      op.op === "resolve_knowledge" &&
      op.state === "superseded" &&
      op.replacement_refs.length === 1
    ) {
      const target = read(op.ref),
        replacementId = idOf(op.replacement_refs[0]);
      if (!replacementId || !known(target.id) || !known(replacementId))
        return {
          allowed: false,
          reason: "Deduplication needs read original and replacement.",
        };
      const replacement = read({ id: replacementId });
      if (
        target.id === replacement.id ||
        target.storage === "tombstone" ||
        replacement.storage === "tombstone" ||
        target.kind !== "knowledge" ||
        replacement.kind !== "knowledge" ||
        target.data.state !== "current" ||
        replacement.data.state !== "current" ||
        canonical([target.visibility, target.data]) !==
          canonical([replacement.visibility, replacement.data])
      )
        return {
          allowed: false,
          reason:
            "Automatic deduplication requires two distinct current claims with identical grounding, strength, conditions and exact semantics.",
        };
      continue;
    }
    if (op.op === "reorganize_catalog") {
      if (
        !op.changes.every(
          (c) => known(c.ref.id) && read(c.ref).kind === "concept",
        )
      )
        return {
          allowed: false,
          reason:
            "Automatic organization is limited to read topic records, never identity merges.",
        };
      continue;
    }
    if (op.op === "update_record") {
      const current = read(op.ref);
      if (current.kind !== "method" || !state.activity_id || !known(current.id))
        return {
          allowed: false,
          reason:
            "Automatic update is limited to an explicitly bound local Procedure.",
        };
      const activity = read({ id: state.activity_id });
      const contract = activity.data.contract as
        | { procedure_refs?: unknown[] }
        | undefined;
      const refs =
        contract?.procedure_refs ??
        (activity.data.procedure_refs as unknown[] | undefined);
      if (
        !refs?.some((r) => idOf(r) === current.id) ||
        op.origin_activity_id !== undefined ||
        op.concept_ids !== undefined
      )
        return {
          allowed: false,
          reason:
            "Activity origin alone is not local ownership; explicit Procedure binding is required.",
        };
      if (
        (op.data as JsonObject).state !== current.data.state ||
        (op.data as JsonObject).content_version !== current.data.content_version
      )
        return {
          allowed: false,
          reason:
            "Procedure activation/deprecation is not delegated by this review.",
        };
      continue;
    }
    return {
      allowed: false,
      reason:
        "This change needs a separate authorized workflow; Sleep cannot alter goals, obligations, access, identity or external effects.",
    };
  }
  return {
    allowed: true,
    reason:
      "Finite reversible change within the explicit delegation; normal Core authority still applies.",
  };
}

export class SleepV2 {
  readonly contextProfile: string;
  private readonly now: () => number;
  constructor(
    public readonly storage: StoragePort,
    private readonly context: CallContext,
    private readonly bindings: SleepV2Bindings,
  ) {
    this.contextProfile = profile(context);
    this.now = bindings.now ?? Date.now;
    this.command(() => {
      for (const collection of SleepV2Collections)
        this.storage.registerCanonicalCollection?.(collection.table, [
          ...collection.keyColumns,
        ]);
      this.storage.exec(SleepV2SchemaSQL);
    });
  }
  private command<T>(callback: () => T): T {
    const run = () => {
      this.authorize();
      return callback();
    };
    return this.storage.withCommandSync
      ? this.storage.withCommandSync(run)
      : run();
  }
  private authorize() {
    requireThat(
      this.context.processing_allowed &&
        this.context.can_write &&
        !this.storage.readonly &&
        this.context.principal === "trusted-personal",
      "PERMISSION_DENIED",
      "Sleep requires the unchanged trusted processing/write context.",
    );
    requireThat(
      this.context.epoch === this.storage.workspace.epoch &&
        this.context.workspace_id === this.storage.workspace.workspace_id,
      "RESTORE_RECONCILIATION_REQUIRED",
      "Sleep context is stale.",
    );
    this.storage.assertActive?.(this.context.epoch, true);
  }
  private load(id: string): SleepState {
    const row = this.storage.get<{ json: string }>(
      "SELECT json FROM sleep_cycles WHERE id=?",
      id,
    );
    requireThat(row, "REFERENCE_NOT_FOUND", "Review not available.");
    const state = StateSchema.parse(JSON.parse(row.json));
    requireThat(
      state.profile === this.contextProfile,
      "REFERENCE_NOT_FOUND",
      "Review not available.",
    );
    const ids = new Set(
      [
        ...state.cases,
        ...state.read_refs,
        ...state.proposals.flatMap((p) => [
          ...p.premises,
          ...p.result_refs,
          ...(p.check_observation?.refs ?? []),
        ]),
      ].map((r) => r.id),
    );
    if (state.activity_id) ids.add(state.activity_id);
    for (const id of ids) this.bindings.read({ id });
    return state;
  }
  private save(state: SleepState) {
    state.updated_at = this.now();
    state.revision++;
    const json = JSON.stringify(StateSchema.parse(state));
    requireThat(
      Buffer.byteLength(json) <= 256 * 1024,
      "VALIDATION_ERROR",
      "Review state exceeds its semantic file bound.",
    );
    this.storage.run(
      "UPDATE sleep_cycles SET json=? WHERE id=?",
      json,
      state.id,
    );
  }
  private change<T>(
    id: string,
    callback: (state: SleepState) => T,
    observationOnly = false,
  ): T {
    return this.command(() => {
      this.storage.exec("BEGIN IMMEDIATE");
      try {
        const state = this.load(id);
        if (observationOnly)
          requireThat(
            state.epoch === this.context.epoch,
            "RESTORE_RECONCILIATION_REQUIRED",
            "Historical check belongs to another restored epoch.",
          );
        else this.assertCurrent(state);
        const result = callback(state);
        this.save(state);
        this.storage.exec("COMMIT");
        return result;
      } catch (e) {
        this.storage.exec("ROLLBACK");
        throw e;
      }
    });
  }
  private assertCurrent(state: SleepState) {
    requireThat(
      state.epoch === this.context.epoch,
      "RESTORE_RECONCILIATION_REQUIRED",
      "Historical review cannot execute after restore.",
    );
    if (state.runtime_id !== this.context.runtime_id)
      requireThat(
        this.bindings.runtimeState?.(state.runtime_id) === "dead",
        "STORE_BUSY",
        "Another live or unknown runtime owns this review.",
      );
  }
  private running(state: SleepState, phases?: SleepState["phase"][]) {
    requireThat(
      state.status === "running",
      "SLEEP_NOT_RUNNING",
      "Review is not running.",
    );
    requireThat(
      this.now() < state.deadline_at &&
        state.generations < SLEEP_LIMITS.generations + 1,
      "SLEEP_BUDGET_EXHAUSTED",
      "Review deadline has elapsed.",
    );
    if (phases)
      requireThat(
        phases.includes(state.phase),
        "INVALID_TRANSITION",
        "A required Sleep phase has not been completed.",
      );
  }
  start(activityId: string | null, model: SleepState["model"]): SleepState {
    return this.command(() => {
      this.storage.exec("BEGIN IMMEDIATE");
      try {
        const prior = this.storage.get<{ json: string }>(
          "SELECT json FROM sleep_cycles WHERE json_extract(json,'$.status') IN ('running','paused','blocked') LIMIT 1",
        );
        if (prior) {
          const old = StateSchema.parse(JSON.parse(prior.json));
          if (old.epoch === this.context.epoch) {
            requireThat(
              old.profile === this.contextProfile,
              "STORE_BUSY",
              "A review is already active.",
            );
            requireThat(
              old.activity_id === activityId &&
                canonical(old.model) === canonical(model),
              "STORE_BUSY",
              "The active review has another Activity or model; inspect, resume or cancel that exact cycle first.",
            );
            const accessible = this.load(old.id);
            this.storage.exec("COMMIT");
            return accessible;
          }
          old.status = "stale";
          old.continuation = "Restored history; start a new explicit review.";
          this.save(old);
        }
        const activity = activityId
          ? this.bindings.read({ id: activityId })
          : null;
        if (activityId)
          requireThat(
            activity?.kind === "activity",
            "REFERENCE_NOT_FOUND",
            "Activity not available.",
          );
        const previous = this.storage
          .all<{
            json: string;
          }>(
            "SELECT json FROM sleep_cycles WHERE json_extract(json,'$.profile')=?",
            this.contextProfile,
          )
          .map((r) => StateSchema.parse(JSON.parse(r.json)));
        const readBefore = previous
          .filter(
            (s) =>
              s.epoch === this.context.epoch &&
              s.activity_id === activityId &&
              s.status === "completed",
          )
          .flatMap((s) => s.read_refs);
        const cases = selectSleepCases(
          this.bindings.candidates(activityId),
          activityId,
          readBefore,
        );
        const now = this.now();
        const state: SleepState = {
          format: 1,
          id: "sleep-" + randomUUID(),
          workspace_id: this.context.workspace_id,
          epoch: this.context.epoch,
          profile: this.contextProfile,
          owner_principal: this.context.principal,
          runtime_id: this.context.runtime_id,
          activity_id: activityId,
          visibility:
            activity?.visibility === "restricted" ||
            cases.some((r) => r.visibility === "restricted")
              ? "restricted"
              : "workspace",
          model,
          status: "running",
          phase: "select",
          revision: 1,
          started_at: now,
          deadline_at: now + SLEEP_LIMITS.milliseconds,
          updated_at: now,
          generations: 0,
          improvements: 0,
          cases: cases.map(exact),
          read_refs: [],
          question: null,
          analysis: null,
          proposals: [],
          outcome: null,
          summary: null,
          continuation: null,
        };
        this.storage.run(
          "INSERT INTO sleep_cycles VALUES(?,?)",
          state.id,
          JSON.stringify(StateSchema.parse(state)),
        );
        this.storage.exec("COMMIT");
        return state;
      } catch (e) {
        this.storage.exec("ROLLBACK");
        throw e;
      }
    });
  }
  status(id?: string): SleepState | null {
    return this.command(() => {
      if (id) return this.load(id);
      const row = this.storage.get<{ json: string }>(
        "SELECT json FROM sleep_cycles WHERE json_extract(json,'$.profile')=? ORDER BY json_extract(json,'$.updated_at') DESC LIMIT 1",
        this.contextProfile,
      );
      return row ? this.load((JSON.parse(row.json) as SleepState).id) : null;
    });
  }
  resume(id: string, model: SleepState["model"]): SleepState {
    return this.change(id, (s) => {
      requireThat(
        active(s),
        "INVALID_TRANSITION",
        "A completed/exhausted review needs a new explicit cycle.",
      );
      requireThat(
        canonical(s.model) === canonical(model),
        "PERMISSION_DENIED",
        "The selected model changed; start a new explicitly selected cycle.",
      );
      requireThat(
        this.now() < s.deadline_at && s.generations < SLEEP_LIMITS.generations,
        "SLEEP_BUDGET_EXHAUSTED",
        "This review's persisted budget is exhausted.",
      );
      requireThat(
        !s.proposals.some(
          (p) => p.status === "applying" || p.status === "unknown",
        ),
        "RECONCILIATION_REQUIRED",
        "Discover the original receipt before resuming an uncertain application.",
      );
      for (const p of s.proposals)
        if (p.request && ["proposed", "validated"].includes(p.status)) {
          p.status = "rejected";
          p.validation_reason =
            "Resume requires a new exact proposal with fresh current source handles and guards; no action was dispatched.";
          p.request = null;
        }
      s.runtime_id = this.context.runtime_id;
      s.status = "running";
      if (["finish", "propose", "validate"].includes(s.phase))
        s.phase = s.proposals.some((p) => p.status === "validated")
          ? "validate"
          : s.proposals.some((p) => p.status === "proposed")
            ? "propose"
            : s.analysis
              ? "analyze"
              : "select";
      return s;
    });
  }
  cancel(id: string, reason = "Cancelled by explicit request."): SleepState {
    return this.change(id, (s) => {
      requireThat(
        active(s) || s.status === "budget_exhausted",
        "INVALID_TRANSITION",
        "A completed historical review cannot be cancelled.",
      );
      requireThat(
        !s.proposals.some(
          (p) => p.status === "applying" || p.status === "unknown",
        ),
        "RECONCILIATION_REQUIRED",
        "An admitted application must settle before cancellation.",
      );
      s.status = "cancelled";
      s.outcome = "stopped";
      s.continuation = short.parse(reason);
      return s;
    });
  }
  cancelMetadata(id?: string): {
    id: string;
    status: "cancelled";
    content_withheld: true;
  } {
    return this.command(() => {
      this.storage.exec("BEGIN IMMEDIATE");
      try {
        const admin =
          !!this.context.scopes?.includes("restricted:read") &&
          !!this.context.scopes?.includes("restricted:write");
        const row = id
          ? this.storage.get<{ json: string }>(
              "SELECT json FROM sleep_cycles WHERE id=?",
              id,
            )
          : this.storage.get<{ json: string }>(
              "SELECT json FROM sleep_cycles WHERE json_extract(json,'$.status') IN ('running','paused','blocked','budget_exhausted') AND (json_extract(json,'$.profile')=? OR ?=1) ORDER BY json_extract(json,'$.updated_at') DESC LIMIT 1",
              this.contextProfile,
              admin ? 1 : 0,
            );
        requireThat(
          row,
          "REFERENCE_NOT_FOUND",
          "Review is not available for cancellation.",
        );
        const state = StateSchema.parse(JSON.parse(row.json));
        requireThat(
          state.workspace_id === this.context.workspace_id &&
            state.epoch === this.context.epoch &&
            (state.profile === this.contextProfile ||
              (admin &&
                (state.owner_principal ?? "trusted-personal") ===
                  this.context.principal)),
          "REFERENCE_NOT_FOUND",
          "Review is not available for cancellation.",
        );
        this.assertCurrent(state);
        requireThat(
          active(state) || state.status === "budget_exhausted",
          "INVALID_TRANSITION",
          "Completed history cannot be cancelled.",
        );
        for (const p of state.proposals.filter((p) =>
          ["applying", "unknown"].includes(p.status),
        )) {
          requireThat(
            admin,
            "RECONCILIATION_REQUIRED",
            "Unresolved applications require trusted scoped reconciliation before cancellation.",
          );
          const requestId = p.native_request_id
            ? p.native_request_id + ":document"
            : p.request?.request_id;
          requireThat(
            requestId,
            "RECONCILIATION_REQUIRED",
            "Inspect the original uncertain operation before cancellation.",
          );
          const saved = this.storage.get<{ json: string }>(
            "SELECT json FROM receipts WHERE request_id=?",
            requestId,
          );
          requireThat(
            saved,
            "RECONCILIATION_REQUIRED",
            "No exact registered result; cancellation cannot dismiss an unknown effect.",
          );
          const receipt = JSON.parse(saved.json) as Receipt;
          requireThat(
            receipt.committed &&
              receipt.request_id === requestId &&
              receipt.workspace_id === state.workspace_id,
            "RECONCILIATION_REQUIRED",
            "Registered result differs from the admitted operation.",
          );
          p.status = "applied";
          p.result_refs = Object.entries(receipt.new_revisions).map(
            ([id, revision]) => ({ id, revision }),
          );
          p.applied_at = this.now();
          p.request = null;
          p.document_change = null;
          state.improvements++;
        }
        state.status = "cancelled";
        state.phase = "finish";
        state.outcome = state.improvements ? "applied_unverified" : "stopped";
        state.continuation =
          "Cancelled by the authorized owner; retained content was not disclosed.";
        this.save(state);
        this.storage.exec("COMMIT");
        return { id: state.id, status: "cancelled", content_withheld: true };
      } catch (error) {
        this.storage.exec("ROLLBACK");
        throw error;
      }
    });
  }
  reserveGeneration(id: string): SleepState {
    const result = this.change(id, (s) => {
      if (
        s.status !== "running" ||
        this.now() >= s.deadline_at ||
        s.generations >= SLEEP_LIMITS.generations
      ) {
        if (s.status === "running") {
          s.status = "budget_exhausted";
          s.outcome = "stopped";
          s.continuation =
            "Continue this concrete question in a new explicitly requested short cycle.";
        }
        return { state: s, admitted: false };
      }
      s.generations++;
      return { state: s, admitted: true };
    });
    requireThat(
      result.admitted,
      "SLEEP_BUDGET_EXHAUSTED",
      "No new model generation is admitted.",
    );
    return result.state;
  }
  read(id: string, input: SleepRef | { id: string }): AddressedRow {
    return this.change(id, (s) => {
      this.running(s, [
        "select",
        "read",
        "analyze",
        "propose",
        "validate",
        "future_check",
      ]);
      const row = this.bindings.read(input);
      const p = exact(row);
      if (!s.read_refs.some((r) => sameRef(r, p))) s.read_refs.push(p);
      if (row.visibility === "restricted") s.visibility = "restricted";
      if (["select", "read"].includes(s.phase)) s.phase = "read";
      return row;
    });
  }
  analyze(
    id: string,
    input: NonNullable<SleepState["analysis"]> & { question: string },
  ): SleepState {
    return this.change(id, (s) => {
      this.running(s, [
        "read",
        "analyze",
        "propose",
        "validate",
        "future_check",
      ]);
      const parsed = z
        .strictObject({
          question: short,
          observations: short,
          hypothesis: z.string().max(4000).nullable(),
          counterexamples: z.array(ref).max(20),
          grounds: z.array(ref).min(1).max(30),
        })
        .parse(input);
      requireThat(
        [...parsed.grounds, ...parsed.counterexamples].every((r) =>
          s.read_refs.some((p) => sameRef(p, r)),
        ),
        "SOURCE_MISSING",
        "Analysis must refer to actually read exact sources.",
      );
      s.question = parsed.question;
      s.analysis = {
        observations: parsed.observations,
        hypothesis: parsed.hypothesis,
        counterexamples: parsed.counterexamples,
        grounds: parsed.grounds,
      };
      s.phase = "analyze";
      return s;
    });
  }
  propose(
    id: string,
    input: Omit<
      SleepProposal,
      "id" | "status" | "validation_reason" | "result_refs" | "request_hash"
    >,
  ): SleepProposal {
    return this.change(id, (s) => {
      this.running(s, ["analyze", "propose", "validate", "future_check"]);
      requireThat(
        s.analysis && s.proposals.length < SLEEP_LIMITS.improvements,
        "VALIDATION_ERROR",
        "A proposal needs analysis and an unused improvement slot.",
      );
      const p = SleepProposalSchema.parse({
        ...input,
        request_hash: hash(input.request ?? input.document_change),
        id: "proposal-" + randomUUID(),
        status: "proposed",
        validation_reason: null,
        result_refs: [],
      });
      requireThat(
        p.premises.every((r) => s.read_refs.some((a) => sameRef(a, r))),
        "SOURCE_MISSING",
        "Proposal premises must have been read.",
      );
      requireThat(
        !!p.request !== !!p.document_change,
        "VALIDATION_ERROR",
        "Exactly one proposal payload is required.",
      );
      for (const op of p.request?.ops ?? [])
        if ("ref" in op && "id" in op.ref)
          requireThat(
            p.request!.guards.some((g) => g.ref.id === op.ref.id),
            "GUARD_REQUIRED",
            "Every changed existing target needs a current revision guard.",
          );
      requireThat(
        !s.proposals.some((v) => ["applying", "unknown"].includes(v.status)),
        "RECONCILIATION_REQUIRED",
        "A prior application must settle before another proposal.",
      );
      for (const op of p.request?.ops ?? [])
        if (op.op === "reorganize_catalog")
          for (const change of op.changes)
            requireThat(
              p.request!.guards.some((g) => g.ref.id === change.ref.id),
              "GUARD_REQUIRED",
              "Every catalog target needs a guarded exact revision.",
            );
      s.proposals.push(p);
      s.phase = "propose";
      return p;
    });
  }
  validate(id: string, proposalId: string): SleepProposal {
    return this.change(id, (s) => {
      this.running(s, ["propose", "validate"]);
      const p = this.proposal(s, proposalId);
      requireThat(
        p.status === "proposed",
        "INVALID_TRANSITION",
        "Only a proposed change can be validated.",
      );
      for (const guard of this.guards(p))
        requireThat(
          this.bindings.read(guard.ref).revision === guard.expected_revision,
          "REVISION_CONFLICT",
          "A proposal target changed; read and rebuild it.",
        );
      const result = this.bindings.validateProposal
        ? this.bindings.validateProposal(p, s)
        : defaultSleepProposalPolicy(p, s, this.bindings.read);
      p.status = result.allowed ? "validated" : "rejected";
      p.validation_reason = result.reason;
      s.phase = "validate";
      return p;
    });
  }
  beginApply(id: string, proposalId: string): SleepProposal {
    return this.change(id, (s) => {
      this.running(s, ["validate"]);
      requireThat(
        s.improvements < SLEEP_LIMITS.improvements,
        "SLEEP_BUDGET_EXHAUSTED",
        "Improvement budget exhausted.",
      );
      if (s.activity_id)
        requireThat(
          this.bindings.read({ id: s.activity_id }).data.status === "active",
          "INVALID_TRANSITION",
          "A paused or closed Activity cannot admit new automatic improvements.",
        );
      const p = this.proposal(s, proposalId);
      requireThat(
        p.status === "validated",
        "APPROVAL_REQUIRED",
        "Change was not authorized by delegated policy.",
      );
      for (const g of this.guards(p))
        requireThat(
          this.bindings.read(g.ref).revision === g.expected_revision,
          "REVISION_CONFLICT",
          "Validated payload is stale.",
        );
      p.status = "applying";
      s.phase = "apply";
      return p;
    });
  }
  inExecution<T>(id: string, callback: () => T): T {
    return execution.run({ controller: this, runId: id }, callback);
  }
  prepareApplyPermit(id: string, proposalId: string): PreparedSleepApply {
    const state = this.status(id)!;
    const p = this.proposal(state, proposalId);
    requireThat(
      state.status === "running" &&
        state.phase === "apply" &&
        p.status === "applying",
      "INVALID_TRANSITION",
      "No admitted proposal application.",
    );
    const token = Object.freeze({ state });
    preparedApplications.set(token, {
      proposal: p,
      scope: {
        controller: this,
        runId: id,
        proposalId,
        requestHash: p.request
          ? hash(CommitSchema.parse(p.request))
          : p.request_hash,
      },
    });
    return token;
  }
  /** Capture under the short operation; invoke the callback only after releasing it. */
  withPreparedApplyPermit<T>(token: PreparedSleepApply, callback: () => T): T {
    const prepared = preparedApplications.get(token);
    requireThat(
      prepared?.scope.controller === this,
      "PERMISSION_DENIED",
      "A current one-use private application token is required.",
    );
    preparedApplications.delete(token);
    const { scope, proposal: p } = prepared;
    const reject = (error: unknown): never => {
      if (
        (p.document_change && !scope.documentEffect) ||
        (p.request && !scope.coreEntered)
      )
        throw new SleepNotDispatched(
          error instanceof Error ? error.message : String(error),
        );
      throw error;
    };
    try {
      const result = execution.run(scope, callback);
      return result && typeof (result as { then?: unknown }).then === "function"
        ? (Promise.resolve(result).catch(reject) as T)
        : result;
    } catch (error) {
      return reject(error);
    }
  }
  /** Synchronous convenience for callers already inside a coordinated phase. */
  withApplyPermit<T>(id: string, proposalId: string, callback: () => T): T {
    return this.withPreparedApplyPermit(
      this.prepareApplyPermit(id, proposalId),
      callback,
    );
  }
  classifyCoreRefusal(id: string, proposalId: string, error: unknown): unknown {
    const deterministic =
      error instanceof CoreError &&
      [
        "VALIDATION_ERROR",
        "SOURCE_MISSING",
        "SOURCE_EXPIRED",
        "REFERENCE_NOT_FOUND",
        "REFERENCE_TYPE_MISMATCH",
        "REVISION_CONFLICT",
        "GUARD_REQUIRED",
        "PERMISSION_DENIED",
        "APPROVAL_REQUIRED",
        "APPROVAL_STALE",
        "IDEMPOTENCY_CONFLICT",
        "CLAIM_REQUIRED",
        "CLAIM_CONFLICT",
      ].includes(error.code);
    if (!deterministic) return error;
    return this.command(() => {
      const p = this.proposal(this.load(id), proposalId);
      return p.status === "applying" &&
        p.request &&
        !this.storage.get(
          "SELECT json FROM receipts WHERE request_id=?",
          p.request.request_id,
        )
        ? new SleepNotDispatched(error.message)
        : error;
    });
  }
  rejectUnapplied(id: string, proposalId: string, error: unknown): SleepState {
    requireThat(
      isSleepNotDispatched(error),
      "PERMISSION_DENIED",
      "A live private dispatch refusal is required.",
    );
    return this.change(id, (s) => {
      const p = this.proposal(s, proposalId);
      requireThat(
        p.status === "applying",
        "INVALID_TRANSITION",
        "No proposed dispatch to reject.",
      );
      p.status = "rejected";
      p.validation_reason =
        error instanceof Error ? error.message : String(error);
      p.request = null;
      p.document_change = null;
      s.phase = "analyze";
      return s;
    });
  }

  assertApplyPermit(id: string, request: CommitRequest, scope: Execution) {
    const s = this.status(id)!;
    const p = s.proposals.find(
      (p) => p.id === scope.proposalId && p.status === "applying",
    );
    requireThat(
      p && s.phase === "apply",
      "PERMISSION_DENIED",
      "Sleep has no admitted exact proposal.",
    );
    if (p.document_change && scope.documentEffect) {
      const accepted = scope.documentEffect;
      const row = this.storage.get<{ json: string }>(
        "SELECT json FROM intents WHERE request_id=?",
        accepted.requestId,
      );
      const effect = row ? (JSON.parse(row.json) as EffectRow) : null;
      requireThat(
        effect &&
          effect.epoch === s.epoch &&
          effect.status === "confirmed" &&
          hash(effect.payload) === accepted.digest &&
          request.request_id === accepted.requestId + ":document" &&
          request.ops.length === 1 &&
          request.ops[0].op === "commit_document" &&
          request.ops[0].effect_request_id === accepted.requestId &&
          request.source_handles.length === 1,
        "PERMISSION_DENIED",
        "Only the exact confirmed native document may register during Sleep.",
      );
      // Registration and cleanup settle a dispatch admitted before a deadline; they are not new work.
      return;
    }
    requireThat(
      s.status === "running" &&
        this.now() < s.deadline_at &&
        p.request &&
        hash(CommitSchema.parse(p.request)) === hash(request) &&
        scope.requestHash === hash(request),
      "PERMISSION_DENIED",
      "Sleep cannot bypass its exact validated proposal.",
    );
  }
  assertDocumentPermit(id: string, effect: FileEffect, scope: Execution) {
    const s = this.status(id)!;
    this.running(s, ["apply"]);
    const p = s.proposals.find(
      (p) => p.id === scope.proposalId && p.status === "applying",
    );
    const change = p?.document_change;
    requireThat(
      change && scope.requestHash === p.request_hash && !scope.documentEffect,
      "PERMISSION_DENIED",
      "Sleep has no unused exact document dispatch permit.",
    );
    const row = this.bindings.read({ id: change.ref.id });
    requireThat(
      row.kind === "entity",
      "REFERENCE_TYPE_MISMATCH",
      "Only an existing managed entity document may change.",
    );
    const d = effect.document,
      current = managedDocument(row);
    const activity = s.activity_id
      ? this.bindings.read({ id: s.activity_id })
      : null;
    const refs = (
      activity?.data.contract as
        | { document_refs?: { id: string }[] }
        | undefined
    )?.document_refs;
    const expectedText =
      change.content === undefined
        ? null
        : documentText(current.key, change.content);
    const previous = this.bindings.read(current.head_ref),
      previousHash = previous.data.content_hash;
    requireThat(
      row.revision === change.ref.revision &&
        d &&
        d.ref &&
        sameRef(d.ref, change.ref) &&
        refs?.some((r) => r.id === row.id) &&
        d.key === current.key &&
        d.state === "active" &&
        current.state === "active" &&
        d.path === (change.path ?? current.path) &&
        d.document_type === current.document_type &&
        canonical(d.format_ref) === canonical(current.format_ref) &&
        canonical(d.links) === canonical(current.links) &&
        d.title === (change.title ?? row.title) &&
        d.visibility === row.visibility &&
        d.source_language === previous.data.source_language &&
        d.activity_ref?.id === s.activity_id &&
        d.previous_path === current.path &&
        d.previous_hash === previousHash &&
        (d.path === current.path
          ? effect.before_hash === previousHash
          : effect.before_hash === null) &&
        effect.tool === "write" &&
        effect.arguments.path === effect.target &&
        "content" in effect.arguments &&
        effect.arguments.content === effect.final_text &&
        effect.work_ref === null &&
        effect.step_id === null &&
        effect.retry_of === null &&
        effect.method_export === null &&
        (expectedText === null
          ? effect.final_hash === previousHash
          : effect.final_text === expectedText),
      "PERMISSION_DENIED",
      "Native document action differs from its exact reversible proposal.",
    );
    requireThat(
      effect.final_hash ===
        createHash("sha256").update(effect.final_text).digest("hex") &&
        effect.final_length === Buffer.byteLength(effect.final_text),
      "PERMISSION_DENIED",
      "Native document bytes differ from the delegated payload.",
    );
    scope.documentEffect = {
      requestId: effect.request_id,
      digest: hash(effect),
    };
    // Called inside the native dispatch transaction: this marker and effect admission publish together.
    p.native_request_id = effect.request_id;
    this.save(s);
  }
  settleApply(id: string, proposalId: string, receipt: Receipt): SleepState {
    return this.change(id, (s) => {
      const p = this.proposal(s, proposalId);
      requireThat(
        ["applying", "unknown"].includes(p.status),
        "INVALID_TRANSITION",
        "Proposal was not dispatched.",
      );
      requireThat(
        receipt.committed &&
          receipt.request_id === p.request?.request_id &&
          receipt.workspace_id === s.workspace_id,
        "RECONCILIATION_REQUIRED",
        "No exact committed receipt for this application.",
      );
      p.result_refs = Object.entries(receipt.new_revisions).map(
        ([id, revision]) => ({ id, revision }),
      );
      p.status = "applied";
      p.applied_at = this.now();
      p.request = null;
      p.document_change = null;
      s.improvements++;
      s.phase = "future_check";
      if (s.status === "blocked")
        s.status =
          this.now() >= s.deadline_at ||
          s.generations >= SLEEP_LIMITS.generations
            ? "budget_exhausted"
            : "paused";
      return s;
    });
  }
  markUnknown(id: string, proposalId: string, reason: string): SleepState {
    return this.change(id, (s) => {
      const p = this.proposal(s, proposalId);
      requireThat(
        p.status === "applying",
        "INVALID_TRANSITION",
        "No in-flight application.",
      );
      p.status = "unknown";
      s.status = "blocked";
      s.continuation = short.parse(reason);
      return s;
    });
  }
  reconcile(id: string): SleepState {
    const state = this.status(id)!;
    const deadOwner =
      state.runtime_id !== this.context.runtime_id &&
      this.bindings.runtimeState?.(state.runtime_id) === "dead";
    for (const p of state.proposals.filter((p) =>
      ["applying", "unknown"].includes(p.status),
    )) {
      if (p.document_change) {
        if (!p.native_request_id && deadOwner) {
          // Native dispatch requires this canonical marker and effect intent in one transaction.
          // Its absence after complete recovery proves the dead runtime never admitted a write.
          this.change(id, (s) => {
            const pending = this.proposal(s, p.id);
            requireThat(
              !pending.native_request_id,
              "RECONCILIATION_REQUIRED",
              "Native admission changed during recovery.",
            );
            pending.status = "rejected";
            pending.validation_reason =
              "Prior runtime ended before atomic native admission; no write is replayed.";
            pending.document_change = null;
            s.phase = "analyze";
            if (s.status === "blocked") s.status = "paused";
          });
          continue;
        }
        requireThat(
          p.native_request_id,
          "RECONCILIATION_REQUIRED",
          "No retained native admission; inspect the original deterministic operation without replay.",
        );
        const row = this.command(() =>
          this.storage.get<{ json: string }>(
            "SELECT json FROM receipts WHERE request_id=?",
            p.native_request_id! + ":document",
          ),
        );
        requireThat(
          row,
          "RECONCILIATION_REQUIRED",
          "Inspect/finalize the original native document operation; never repeat its write.",
        );
        const receipt = JSON.parse(row.json) as Receipt;
        requireThat(
          receipt.committed &&
            receipt.workspace_id === state.workspace_id &&
            receipt.request_id === p.native_request_id + ":document",
          "RECONCILIATION_REQUIRED",
          "Native registration receipt differs from the retained admission.",
        );
        this.settleDocument(
          id,
          p.id,
          Object.entries(receipt.new_revisions).map(([id, revision]) => ({
            id,
            revision,
          })),
        );
        continue;
      }
      requireThat(
        p.request,
        "RECONCILIATION_REQUIRED",
        "No retained exact Core request.",
      );
      const receipt = this.command(() =>
        this.storage.get<{ json: string }>(
          "SELECT json FROM receipts WHERE request_id=?",
          p.request!.request_id,
        ),
      );
      if (!receipt && deadOwner) {
        // A pure Core transaction has no native dispatch; its receipt is atomic with its records.
        this.change(id, (s) => {
          const pending = this.proposal(s, p.id);
          pending.status = "rejected";
          pending.validation_reason =
            "Prior runtime ended without a canonical Core commit receipt; no change is replayed.";
          pending.request = null;
          s.phase = "analyze";
          if (s.status === "blocked") s.status = "paused";
        });
        continue;
      }
      requireThat(
        receipt,
        "RECONCILIATION_REQUIRED",
        "No receipt found; do not repeat the application.",
      );
      this.settleApply(id, p.id, JSON.parse(receipt.json) as Receipt);
    }
    return this.status(id)!;
  }
  finish(
    id: string,
    outcome: NonNullable<SleepState["outcome"]>,
    summary: string,
    continuation: string | null = null,
  ): SleepState {
    return this.change(id, (s) => {
      this.running(s);
      requireThat(
        !s.proposals.some((p) => ["applying", "unknown"].includes(p.status)),
        "RECONCILIATION_REQUIRED",
        "Application outcome is unresolved.",
      );
      if (s.improvements)
        requireThat(
          outcome === "applied_unverified",
          "VALIDATION_ERROR",
          "Applied changes have not proved future usefulness.",
        );
      else
        requireThat(
          outcome !== "applied_unverified",
          "VALIDATION_ERROR",
          "No change was actually applied.",
        );
      if (outcome === "no_change")
        requireThat(
          !!s.analysis || s.cases.length === 0,
          "INVALID_TRANSITION",
          "No-change requires grounds or an empty eligible set.",
        );
      if (outcome === "insufficient_evidence")
        requireThat(
          s.cases.length === 0 || s.read_refs.length > 0,
          "INVALID_TRANSITION",
          "Read selected cases before reporting insufficient evidence.",
        );
      s.status =
        outcome === "proposal_pending" || outcome === "stopped"
          ? "paused"
          : "completed";
      s.phase = "finish";
      s.outcome = outcome;
      s.summary = short.parse(summary);
      s.continuation = continuation === null ? null : short.parse(continuation);
      return s;
    });
  }
  pause(id: string, reason: string, exhausted = false): SleepState {
    return this.change(id, (s) => {
      if (!active(s)) return s;
      s.status = s.proposals.some((p) =>
        ["applying", "unknown"].includes(p.status),
      )
        ? "blocked"
        : exhausted ||
            this.now() >= s.deadline_at ||
            s.generations >= SLEEP_LIMITS.generations
          ? "budget_exhausted"
          : "paused";
      s.outcome = "stopped";
      s.continuation = short.parse(reason);
      return s;
    });
  }
  pendingChecks(): {
    run_id: string;
    proposal_id: string;
    activity_id: string | null;
    updated_at: number;
    future_check: SleepProposal["future_check"];
    result_refs: SleepRef[];
  }[] {
    return this.command(() =>
      this.storage
        .all<{
          json: string;
        }>(
          "SELECT json FROM sleep_cycles WHERE json_extract(json,'$.profile')=? ORDER BY json_extract(json,'$.updated_at') DESC",
          this.contextProfile,
        )
        .flatMap((r) => {
          let s: SleepState;
          try {
            s = this.load((JSON.parse(r.json) as SleepState).id);
          } catch (error) {
            if (
              error instanceof CoreError &&
              ["REFERENCE_NOT_FOUND", "PERMISSION_DENIED"].includes(error.code)
            )
              return [];
            throw error;
          }
          return s.proposals
            .filter(
              (p) =>
                p.status === "applied" &&
                (!p.check_observation ||
                  p.check_observation.verdict === "unknown" ||
                  !["observed", "reported"].includes(
                    p.check_observation.evidence_basis ?? "unverified",
                  )),
            )
            .map((p) => ({
              run_id: s.id,
              proposal_id: p.id,
              activity_id: s.activity_id,
              updated_at: s.updated_at,
              future_check: p.future_check,
              result_refs: p.result_refs,
            }));
        }),
    );
  }
  private checkGround(
    row: AddressedRow,
    after: number,
  ): { basis: "observed" | "reported"; refs: SleepRef[] } | null {
    if (row.storage === "tombstone") return null;
    if (row.kind === "evidence") {
      const data = row.data,
        provenance = data.provenance as JsonObject | undefined;
      const retained =
        data.availability === "retained" &&
        ((typeof data.retained_excerpt === "string" &&
          data.retained_excerpt.length > 0) ||
          (typeof data.blob_ref === "string" && data.blob_ref.length > 0));
      if (
        !retained ||
        !(Date.parse(row.created_at) > after) ||
        !(Date.parse(String(data.captured_at)) > after)
      )
        return null;
      const observation = provenance?.observation as JsonObject | undefined;
      if (
        data.source_kind === "tool_result" &&
        observation &&
        typeof observation.tool_name === "string" &&
        observation.tool_name.length > 0 &&
        typeof observation.tool_call_id === "string" &&
        observation.tool_call_id.length > 0 &&
        typeof observation.is_error === "boolean" &&
        typeof observation.full_content_hash === "string" &&
        /^[a-f0-9]{64}$/.test(observation.full_content_hash)
      )
        return { basis: "observed", refs: [exact(row)] };
      if (
        data.source_kind === "direct_statement" &&
        provenance?.transport === "interactive" &&
        provenance.owner_channel_eligible === true &&
        provenance.input_integrity === "trusted_first_untransformed"
      )
        return { basis: "reported", refs: [exact(row)] };
      return null;
    }
    if (
      row.kind === "run" &&
      row.data.mode !== "sleep" &&
      ["completed", "failed"].includes(String(row.data.execution)) &&
      Date.parse(String(row.data.ended_at)) > after &&
      typeof row.data.summary === "string" &&
      row.data.summary.trim()
    ) {
      const grounds = Array.isArray(row.data.result_refs)
        ? row.data.result_refs
        : [];
      const observations = grounds.slice(0, 50).flatMap((r) => {
        const parsed = ref.safeParse(r);
        if (!parsed.success) return [];
        const source = this.bindings.read(parsed.data);
        return source.kind === "evidence"
          ? [this.checkGround(source, after)].filter((v) => v !== null)
          : [];
      });
      if (observations.length)
        return {
          basis: observations.some((g) => g.basis === "observed")
            ? "observed"
            : "reported",
          refs: observations.flatMap((g) => g.refs).slice(0, 20),
        };
    }
    return null;
  }
  observeCheck(
    id: string,
    proposalId: string,
    observation: {
      refs: SleepRef[];
      verdict: "helped" | "no_help" | "unknown";
      summary: string;
    },
  ): SleepState {
    requireThat(
      !execution.getStore(),
      "PERMISSION_DENIED",
      "A Sleep cycle cannot declare its own future benefit.",
    );
    return this.change(
      id,
      (s) => {
        requireThat(
          !active(s),
          "INVALID_TRANSITION",
          "Finish the original review before observing later usefulness.",
        );
        const p = this.proposal(s, proposalId);
        requireThat(
          p.status === "applied" && p.applied_at !== undefined,
          "INVALID_TRANSITION",
          "No actually applied improvement awaits observation.",
        );
        const check = z
          .strictObject({
            refs: z.array(ref).min(1).max(20),
            verdict: z.enum(["helped", "no_help", "unknown"]),
            summary: short,
          })
          .parse(observation);
        const actualGrounds: {
          basis: "observed" | "reported";
          refs: SleepRef[];
        }[] = [];
        for (const r of check.refs) {
          const row = this.bindings.read(r);
          requireThat(
            Date.parse(row.updated_at) > p.applied_at!,
            "SOURCE_MISSING",
            "Future benefit needs a real observation created after application, not its own premises or output.",
          );
          const ground = this.checkGround(row, p.applied_at!);
          if (ground) actualGrounds.push(ground);
          if (row.visibility === "restricted") s.visibility = "restricted";
        }
        requireThat(
          check.verdict === "unknown" || actualGrounds.length > 0,
          "SOURCE_MISSING",
          "A usefulness verdict needs later actual observed Evidence or trusted direct owner feedback; inference/generated content remains unverified.",
        );
        p.check_observation = {
          ...check,
          observed_at: this.now(),
          evidence_basis: actualGrounds.some((g) => g.basis === "observed")
            ? "observed"
            : actualGrounds.length
              ? "reported"
              : "unverified",
          ground_refs: actualGrounds.flatMap((g) => g.refs).slice(0, 20),
        };
        return s;
      },
      true,
    );
  }
  settleDocument(
    id: string,
    proposalId: string,
    resultRefs: SleepRef[],
  ): SleepState {
    return this.change(id, (s) => {
      const p = this.proposal(s, proposalId);
      requireThat(
        p.document_change && ["applying", "unknown"].includes(p.status),
        "INVALID_TRANSITION",
        "No admitted native document change.",
      );
      requireThat(
        resultRefs.length > 0,
        "RECONCILIATION_REQUIRED",
        "A document update needs actual registered result refs.",
      );
      p.result_refs = z.array(ref).max(30).parse(resultRefs);
      p.status = "applied";
      p.applied_at = this.now();
      p.request = null;
      p.document_change = null;
      s.improvements++;
      s.phase = "future_check";
      if (s.status === "blocked")
        s.status =
          this.now() >= s.deadline_at ||
          s.generations >= SLEEP_LIMITS.generations
            ? "budget_exhausted"
            : "paused";
      return s;
    });
  }
  private guards(p: SleepProposal) {
    return (
      p.request?.guards ??
      (p.document_change
        ? [
            {
              ref: { id: p.document_change.ref.id },
              expected_revision: p.document_change.ref.revision,
            },
          ]
        : [])
    );
  }
  private proposal(state: SleepState, id: string) {
    const p = state.proposals.find((p) => p.id === id);
    requireThat(p, "REFERENCE_NOT_FOUND", "Proposal not available.");
    return p;
  }
}

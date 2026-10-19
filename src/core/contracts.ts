import { z } from "zod";

export const text = z.string().min(1).max(4000);
export const Ref = z.union([
  z.strictObject({
    id: text,
    revision: z.number().int().positive().optional(),
  }),
  z.strictObject({ client_ref: text }),
]);
const acceptance = z.strictObject({
  criterion_id: text,
  description: text,
  verification: text,
  required: z.boolean(),
});
export const WorkStatus = z.enum([
  "draft",
  "active",
  "waiting",
  "blocked",
  "paused",
  "done",
  "cancelled",
]);
export const StepStatus = z.enum([
  "todo",
  "running",
  "waiting",
  "blocked",
  "done",
  "skipped",
  "cancelled",
]);
export const Ground = z.strictObject({
  criterion_id: text,
  explanation: text,
  evidence_refs: z.array(Ref).min(1).max(20),
});
export const Step = z.strictObject({
  step_id: text,
  intent: text,
  status: StepStatus,
  depends_on: z
    .array(
      z.union([
        z.strictObject({ step_id: text }),
        z.strictObject({
          work_ref: Ref,
          step_id: text.optional(),
          criterion_id: text.optional(),
        }),
      ]),
    )
    .max(50),
  child_work_id: Ref.nullable().optional(),
  required: z.boolean().optional(),
  result_refs: z.array(Ref).max(20),
});
const wait = z.strictObject({
  wait_id: text,
  kind: z.enum(["user", "time", "external_result", "dependency"]),
  target: z.union([z.literal("work"), z.strictObject({ step_id: text })]),
  subject: text,
  satisfied_by: text,
  received_refs: z.array(Ref).max(50),
  question: text,
  status: z.enum(["pending", "partial", "satisfied", "withdrawn"]).optional(),
  resolution: text.optional(),
  due_at: z.iso.datetime({ offset: true }).optional(),
  timezone: text.optional(),
});
export const ActivityData = z.strictObject({
  purpose: text,
  status: z.enum(["active", "paused", "closed"]),
});
export const WorkData = z.strictObject({
  activity_id: Ref.nullable(),
  parent_work_id: Ref.nullable(),
  required_for_parent: z.boolean().optional(),
  objective: text,
  acceptance: z.array(acceptance).min(1).max(10),
  status: WorkStatus,
  current_state: text,
  next_action: text.nullable(),
  steps: z.array(Step).max(100),
  waits: z.array(wait).max(50),
  context_refs: z.array(Ref).max(100),
  completion: z
    .strictObject({
      grounds: z.array(Ground).max(20),
      recorded_at: text,
      decision_actor: text,
    })
    .nullable(),
  plan_version: z.number().int().positive().optional(),
  cancellation: z
    .strictObject({
      reason: text,
      consequences: text,
      recorded_at: text,
      decision_actor: text,
    })
    .nullable()
    .optional(),
});
export type Work = z.infer<typeof WorkData>;
export const KnowledgeData = z.strictObject({
  knowledge_kind: z.enum([
    "fact",
    "preference",
    "constraint",
    "observation",
    "hypothesis",
    "lesson",
  ]),
  statement: text,
  state: z.enum([
    "current",
    "tentative",
    "contested",
    "superseded",
    "retracted",
  ]),
  basis: z.enum([
    "user_statement",
    "observed_result",
    "inference",
    "external_source",
  ]),
  evidence_refs: z.array(Ref).max(20),
  conditions: text,
  representation: z.strictObject({
    kind: z.literal("English paraphrase"),
    source_ref: Ref,
    source_language: text,
  }),
});
const common = {
  client_ref: text,
  title: text,
  body: text.nullable().optional(),
  visibility: z.literal("workspace"),
};
const create = z.discriminatedUnion("kind", [
  z.strictObject({
    op: z.literal("create_record"),
    ...common,
    kind: z.literal("activity"),
    data: ActivityData,
  }),
  z.strictObject({
    op: z.literal("create_record"),
    ...common,
    kind: z.literal("work"),
    data: WorkData,
  }),
  z.strictObject({
    op: z.literal("create_record"),
    ...common,
    kind: z.literal("knowledge"),
    data: KnowledgeData,
  }),
]);
export const CommitSchema = z.strictObject({
  request_id: z.string().min(1).max(160),
  reason: text,
  source_handles: z.array(text).min(1).max(10),
  guards: z
    .array(
      z.strictObject({
        ref: z.strictObject({ id: text }),
        expected_revision: z.number().int().positive(),
      }),
    )
    .max(30),
  claim_tokens: z.array(text).max(20).optional(),
  ops: z
    .array(
      z.union([
        create,
        z.strictObject({
          op: z.literal("import_evidence"),
          client_ref: text,
          source_handle: text,
          title: text,
          source_language: text,
          semantic_source_kind: z.literal("external_reply").optional(),
        }),
        z.strictObject({
          op: z.literal("record_result"),
          client_ref: text,
          work_ref: Ref,
          step_id: text.optional(),
          title: text,
          content: z.string().min(1).max(32000),
          source_language: text,
        }),
        z.strictObject({
          op: z.literal("transition_work"),
          ref: z.strictObject({ id: text }),
          status: WorkStatus,
          reason: text,
          decision_source_handle: text.optional(),
          consequences: text.optional(),
          next_action: text.nullable().optional(),
          grounds: z.array(Ground).max(20).optional(),
        }),
        z.strictObject({
          op: z.literal("transition_step"),
          ref: z.strictObject({ id: text }),
          step_id: text,
          status: StepStatus,
          reason: text,
          result_refs: z.array(Ref).max(20).optional(),
          decision_source_handle: text.optional(),
        }),
        z.strictObject({
          op: z.literal("prepare_handoff"),
          client_ref: text,
          work_ref: Ref,
          step_id: text.optional(),
          objective: text,
          conditions: text,
          expected_result: text,
          context_refs: z.array(Ref).max(20),
          message: text,
        }),
        z.strictObject({
          op: z.literal("receive_handoff"),
          client_ref: text,
          handoff_id: text,
          source_handle: text,
          title: text,
          source_language: text,
          comparison: text,
          disposition: z.enum(["partial", "accepted", "late", "unrelated"]),
          useful_content: text,
          accepted_wait_ids: z.array(text).max(50),
        }),
        z.strictObject({
          op: z.literal("update_record"),
          ref: z.strictObject({ id: text }),
          title: text.optional(),
          body: text.nullable().optional(),
          data: z.union([ActivityData, WorkData, KnowledgeData]),
          plan_change_reason: text.optional(),
          decision_source_handle: text.optional(),
        }),
        z.strictObject({
          op: z.literal("set_focus"),
          activity_ref: Ref.nullable(),
          work_ref: Ref.nullable(),
        }),
      ]),
    )
    .min(1)
    .max(20),
});
export type CommitRequest = z.infer<typeof CommitSchema>;
export type JsonObject = Record<string, unknown>;
export interface RecordRow {
  id: string;
  kind: "activity" | "work" | "evidence" | "knowledge";
  title: string;
  body: string | null;
  revision: number;
  created_at: string;
  updated_at: string;
  storage: "live";
  visibility: "workspace";
  data: JsonObject;
  concept_ids: [];
  origin_activity_id: null;
}
export interface Source {
  handle: string;
  source_ref: string;
  text: string;
  content_hash: string;
  transport: string;
  channel_identity: string | null;
  session_id: string;
  runtime_id: string;
  captured_at: string;
  capture_stage: string;
  original_keystrokes: false;
  blob_ref?: string;
  byte_length: number;
  locator?: string;
  extraction?: Extraction;
}
export interface Extraction {
  format: string;
  status:
    | "readable"
    | "partial"
    | "scanned"
    | "encrypted"
    | "damaged"
    | "unsupported"
    | "limit_exceeded";
  parser: string;
  parser_version: string;
  text_blob_ref: string | null;
  text_hash: string | null;
  total_characters: number;
  sections: {
    locator: string;
    label: string;
    start: number;
    end: number;
    available: boolean;
  }[];
  warnings: string[];
}
export interface CallContext {
  workspace_id: string;
  epoch: string;
  principal: string;
  session_id: string;
  runtime_id: string;
  can_write: boolean;
  processing_allowed: boolean;
}
export interface StoragePort {
  workspace: { workspace_id: string; epoch: string; schema_version: number };
  readonly: boolean;
  exec(sql: string): void;
  get<T>(sql: string, ...params: (string | number | null)[]): T | undefined;
  all<T>(sql: string, ...params: (string | number | null)[]): T[];
  run(sql: string, ...params: (string | number | null)[]): void;
  readMaterial(hash: string): string;
}
export class CoreError extends Error {
  constructor(
    public code: string,
    message: string,
  ) {
    super(message);
  }
}
export function requireThat(
  value: unknown,
  code: string,
  message: string,
): asserts value {
  if (!value) throw new CoreError(code, message);
}
export function canonical(value: unknown): string {
  if (Array.isArray(value)) return "[" + value.map(canonical).join(",") + "]";
  if (value !== null && typeof value === "object") {
    const obj = value as JsonObject;
    return (
      "{" +
      Object.keys(obj)
        .sort()
        .map((k) => JSON.stringify(k) + ":" + canonical(obj[k]))
        .join(",") +
      "}"
    );
  }
  return JSON.stringify(value);
}

export interface Receipt {
  ok: boolean;
  request_id: string;
  workspace_id: string;
  schema_version: number;
  snapshot_seq: number;
  transaction_id: string;
  committed: boolean;
  created: Record<string, string>;
  new_revisions: Record<string, number>;
  warnings: string[];
}

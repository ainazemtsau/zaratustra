import { z } from "zod";

const text = z.string().min(1).max(4000);
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
const wait = z.strictObject({
  wait_id: text,
  kind: z.literal("user"),
  target: z.literal("work"),
  subject: text,
  satisfied_by: text,
  received_refs: z.array(Ref).max(10),
  question: text,
});
export const ActivityData = z.strictObject({
  purpose: text,
  status: z.enum(["active", "paused", "closed"]),
});
export const WorkData = z.strictObject({
  activity_id: Ref.nullable(),
  parent_work_id: z.null(),
  objective: text,
  acceptance: z.array(acceptance).min(1).max(10),
  status: z.enum(["draft", "active", "waiting", "blocked", "paused"]),
  current_state: text,
  next_action: text.nullable(),
  steps: z.array(z.never()).max(0),
  waits: z.array(wait).max(10),
  context_refs: z.array(Ref).max(20),
  completion: z.null(),
});
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
        }),
        z.strictObject({
          op: z.literal("update_record"),
          ref: z.strictObject({ id: text }),
          title: text.optional(),
          body: text.nullable().optional(),
          data: z.union([ActivityData, WorkData, KnowledgeData]),
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

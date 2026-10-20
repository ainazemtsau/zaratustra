import { z } from "zod";

export const text = z.string().min(1).max(4000);
export const Ref = z.union([
  z.strictObject({
    id: text,
    revision: z.number().int().positive().optional(),
    content_version: z.number().int().positive().optional(),
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
  subject_ref: Ref.nullable().optional(),
  predicate: z
    .enum([
      "has_access_to",
      "owns",
      "located_at",
      "available_for",
      "prefers",
      "requires",
      "avoids",
      "identifies",
    ])
    .optional(),
  object_ref: Ref.nullable().optional(),
  value: text.optional(),
  conditions: z.union([
    text,
    z
      .record(z.string().min(1).max(80), text)
      .refine((v) => Object.keys(v).length <= 20),
  ]),
  valid_from: z.iso.datetime({ offset: true }).nullable().optional(),
  valid_to: z.iso.datetime({ offset: true }).nullable().optional(),
  observed_at: z.iso.datetime({ offset: true }).nullable().optional(),
  supersedes_refs: z.array(Ref).max(20).optional(),
  resolution: z
    .strictObject({
      reason: text,
      evidence_refs: z.array(Ref).min(1).max(20),
      replacement_refs: z.array(Ref).max(20),
    })
    .optional(),
  representation: z
    .strictObject({
      kind: z.enum(["English paraphrase", "English translation"]),
      source_ref: Ref,
      source_language: text,
    })
    .optional(),
});
export const ConceptData = z.strictObject({
  definition: text,
  aliases: z.array(text).max(30),
  broader_ids: z.array(Ref).max(20),
  status: z.enum(["active", "retired"]),
  boundary_notes: text.optional(),
});
export const EntityData = z.strictObject({
  entity_kind: z.enum([
    "person",
    "device",
    "place",
    "organization",
    "item",
    "resource",
    "other",
  ]),
  aliases: z.array(text).max(30),
  disambiguation: text,
  external_ids: z.record(z.string().min(1).max(80), text).optional(),
  status: z.enum(["active", "retired"]),
});
export const MethodData = z.strictObject({
  applicability: text,
  instructions: z.string().min(1).max(16000),
  input_contract: text,
  expected_output: text,
  context_requirements: z
    .array(
      z.strictObject({
        description: text,
        refs: z.array(Ref).max(20),
        selector: text.nullable(),
        retrieval: text,
      }),
    )
    .max(20),
  dependencies: z.array(Ref).max(50),
  tool_requirements: z.array(text).max(30),
  content_version: z.number().int().positive(),
  state: z.enum(["candidate", "active", "deprecated"]),
  derived_from: z.array(Ref).max(20),
  limitations: text,
});
export const RunData = z.strictObject({
  work_ref: Ref.nullable(),
  mode: z.enum(["work", "conversation", "correction"]),
  episode_key: text,
  case_id: text,
  continuation_of: Ref.nullable(),
  execution: z.enum(["running", "completed", "failed", "interrupted"]),
  started_at: z.iso.datetime(),
  ended_at: z.iso.datetime().nullable(),
  summary: text,
  result_refs: z.array(Ref).max(50),
  starting_refs: z.array(Ref).max(50),
  environment_ref: Ref,
  local_metrics: z
    .array(
      z.strictObject({
        name: text,
        value: z.number().finite(),
        unit: text,
        scope: text,
      }),
    )
    .max(20),
});
export const ExperienceOps = [
  z.strictObject({
    op: z.literal("revise_method"),
    ref: z.strictObject({ id: text }),
    data: MethodData,
  }),
  z.strictObject({
    op: z.literal("set_method_state"),
    ref: z.strictObject({ id: text }),
    state: MethodData.shape.state,
  }),
  z.strictObject({
    op: z.literal("start_run"),
    client_ref: text,
    title: text,
    visibility: z.enum(["workspace", "restricted"]),
    episode_key: text,
    work_ref: Ref.nullable(),
    mode: RunData.shape.mode,
    continuation_of: Ref.nullable(),
    summary: text,
    starting_refs: z.array(Ref).max(50),
  }),
  z.strictObject({
    op: z.literal("finish_run"),
    ref: z.strictObject({ id: text }),
    execution: z.enum(["completed", "failed", "interrupted"]),
    summary: text,
    result_refs: z.array(Ref).max(50),
    local_metrics: RunData.shape.local_metrics.optional(),
  }),
  z.strictObject({
    op: z.literal("invoke_method"),
    client_ref: text,
    run_ref: Ref,
    invocation_key: text,
    method_ref: Ref,
    input_refs: z.array(Ref).max(50),
    context_refs: z.array(Ref).max(50),
    selected_versions: z.array(Ref).min(1).max(256),
    bindings: z
      .record(
        z.string().min(1).max(80),
        z.union([text, z.number().finite(), z.boolean(), z.null()]),
      )
      .refine((v) => Object.keys(v).length <= 30),
    parent_invocation_ref: Ref.nullable(),
  }),
  z.strictObject({
    op: z.literal("report_application"),
    ref: z.strictObject({ id: text }),
    output_refs: z.array(Ref).max(50),
    observation_refs: z.array(Ref).max(50),
    reported_application: z.strictObject({
      applied: z.boolean(),
      summary: text,
      deviations: z.array(text).max(20),
    }),
  }),
  z.strictObject({
    op: z.literal("record_evaluation"),
    client_ref: text,
    target_ref: Ref,
    run_ref: Ref.nullable(),
    assessment: z.enum(["helpful", "unhelpful", "mixed", "unknown"]),
    dimension: z.enum([
      "usefulness",
      "criterion",
      "technical_operation",
      "local_metric",
    ]),
    dimension_name: text,
    basis: z.enum([
      "user_feedback",
      "reported_feedback",
      "observed_criterion",
      "test_result",
      "model_assessment",
    ]),
    evidence_refs: z.array(Ref).min(1).max(20),
    event_time: z.iso.datetime({ offset: true }).nullable(),
    supersedes_evaluation_ref: Ref.nullable(),
    explanation: text,
  }),
  z.strictObject({
    op: z.literal("open_signal"),
    client_ref: text,
    kind: z.enum([
      "problem",
      "correction",
      "possible_regression",
      "useful_result",
      "novelty",
    ]),
    subject_refs: z.array(Ref).min(1).max(20),
    evidence_refs: z.array(Ref).min(1).max(20),
    description: text,
    next_check: text.nullable(),
    visibility: z.enum(["workspace", "restricted"]),
  }),
  z.strictObject({
    op: z.literal("review_signal"),
    client_ref: text,
    ref: z.strictObject({ id: text }),
    problem_state: z.enum(["open", "observing", "resolved", "dismissed"]),
    assessment: text,
    evidence_refs: z.array(Ref).min(1).max(20),
    applied_change_ref: Ref.nullable(),
    next_check: text.nullable(),
    grounds: text.nullable(),
    dismissal_reason: text.nullable(),
  }),
] as const;
const common = {
  client_ref: text,
  title: text,
  body: text.nullable().optional(),
  visibility: z.enum(["workspace", "restricted"]),
  concept_ids: z.array(Ref).max(30).optional(),
  origin_activity_id: Ref.nullable().optional(),
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
  z.strictObject({
    op: z.literal("create_record"),
    ...common,
    kind: z.literal("concept"),
    data: ConceptData,
  }),
  z.strictObject({
    op: z.literal("create_record"),
    ...common,
    kind: z.literal("entity"),
    data: EntityData,
  }),
  z.strictObject({
    op: z.literal("create_record"),
    ...common,
    kind: z.literal("method"),
    data: MethodData,
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
        ...ExperienceOps,
        z.strictObject({
          op: z.literal("import_evidence"),
          client_ref: text,
          source_handle: text,
          title: text,
          source_language: text,
          semantic_source_kind: z
            .enum([
              "direct_statement",
              "external_reply",
              "quotation",
              "agent_reply",
            ])
            .optional(),
          visibility: z.enum(["workspace", "restricted"]).optional(),
        }),
        z.strictObject({
          op: z.literal("resolve_knowledge"),
          ref: z.strictObject({ id: text }),
          state: z.enum(["tentative", "contested", "superseded", "retracted"]),
          reason: text,
          evidence_refs: z.array(Ref).min(1).max(20),
          replacement_refs: z.array(Ref).max(20),
        }),
        z.strictObject({
          op: z.literal("put_relation"),
          client_ref: text,
          relation: z.enum([
            "related",
            "relevant_to",
            "derived_from",
            "supports",
            "contradicts",
          ]),
          from_ref: Ref,
          to_ref: Ref,
          reason: text,
        }),
        z.strictObject({ op: z.literal("remove_relation"), relation_id: text }),
        z.strictObject({
          op: z.literal("record_result"),
          client_ref: text,
          work_ref: Ref.optional(),
          run_ref: Ref.optional(),
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
          result_refs: z
            .array(Ref)
            .max(20)
            .optional()
            .describe(
              "Addressed records or an existing immutable handoff for this Work (revision omitted or 1). Handoff grounds prove message preparation only; read via handoff_id. The model decides whether they satisfy the step's intent.",
            ),
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
          data: z.union([
            ActivityData,
            WorkData,
            KnowledgeData,
            ConceptData,
            EntityData,
            MethodData,
            RunData,
          ]),
          concept_ids: z.array(Ref).max(30).optional(),
          origin_activity_id: Ref.nullable().optional(),
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
  kind:
    | "activity"
    | "work"
    | "evidence"
    | "knowledge"
    | "concept"
    | "entity"
    | "method"
    | "run";
  title: string;
  body: string | null;
  revision: number;
  created_at: string;
  updated_at: string;
  storage: "live";
  visibility: "workspace" | "restricted";
  data: JsonObject;
  concept_ids: { id: string; revision?: number; content_version?: number }[];
  origin_activity_id: { id: string } | null;
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
  input_integrity: "observed_stage_only" | "trusted_first_untransformed";
  owner_channel_eligible: boolean;
  observation?: {
    tool_name: string;
    tool_call_id: string;
    is_error: boolean;
    full_content_hash: string;
    truncated: boolean;
  };
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
  /** Trusted setup only. Default permits workspace records, never restricted records. */
  scopes?: string[];
  /** Trusted deployment assertion, never model arguments. No biometric authorship claim. */
  interactive_input?: {
    contract: "first-untransformed";
    caller_identity: string;
  };
  environment?: JsonObject;
}
export interface SupportingRow extends Omit<RecordRow, "kind"> {
  kind:
    | "evaluation"
    | "signal"
    | "signal_review"
    | "invocation"
    | "environment";
}
export type AddressedRow = RecordRow | SupportingRow;
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

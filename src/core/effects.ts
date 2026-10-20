import { z } from "zod";
import { createHash, randomUUID } from "node:crypto";
import { canonical, requireThat, text, MethodData } from "./contracts.ts";
import type { CallContext, JsonObject, StoragePort } from "./contracts.ts";
import type { Approvals } from "./approval.ts";

const hash = (v: unknown) =>
  createHash("sha256").update(canonical(v)).digest("hex");
const sha = z.string().regex(/^[a-f0-9]{64}$/);
export const NativeArguments = z.union([
  z.strictObject({ path: text, content: z.string().max(64000) }),
  z.strictObject({
    path: text,
    edits: z
      .array(
        z.strictObject({
          oldText: z.string().min(1).max(64000),
          newText: z.string().max(64000),
        }),
      )
      .min(1)
      .max(20),
  }),
]);
export const FileEffectSchema = z.strictObject({
  request_id: text,
  tool: z.enum(["write", "edit"]),
  arguments: NativeArguments,
  target: text,
  boundary: z.record(z.string(), z.union([z.string(), z.number(), z.null()])),
  before_hash: sha.nullable(),
  before_length: z.number().int().nonnegative(),
  final_hash: sha,
  final_length: z.number().int().min(0).max(64000),
  final_text: z.string().max(64000),
  work_ref: z
    .strictObject({ id: text, revision: z.number().int().positive() })
    .nullable(),
  step_id: text.nullable(),
  independent_basis: text.nullable(),
  material_guards: z
    .array(
      z.strictObject({
        ref: z.strictObject({ id: text }),
        expected_revision: z.number().int().positive(),
      }),
    )
    .max(30)
    .optional(),
  work_snapshot: z
    .strictObject({
      title: text,
      objective: text,
      plan_version: z.number().int().positive(),
      step_intent: text.nullable(),
    })
    .optional(),
  method_snapshot: z
    .strictObject({
      title: text,
      body: z.string().nullable(),
      data: MethodData,
    })
    .optional(),
  method_export: z
    .strictObject({
      method_ref: z.strictObject({
        id: text,
        revision: z.number().int().positive(),
        content_version: z.number().int().positive(),
      }),
      content_hash: sha,
      export_hash: sha,
    })
    .nullable(),
  retry_of: text.nullable(),
  retry_risk: text.nullable(),
});
export type FileEffect = z.infer<typeof FileEffectSchema>;
export interface EffectRow {
  request_id: string;
  kind: "managed_file";
  status: string;
  operation_digest: string;
  payload: FileEffect;
  epoch: string;
  preview_ref: string;
  tool_call_id: string;
  runtime_id: string;
  observations: JsonObject[];
  receipt: JsonObject | null;
  receipt_history: JsonObject[];
  current_observation?: JsonObject;
}
/** SQLite mechanics only. The adapter supplies actual native identity and byte observations. */
export class Effects {
  constructor(
    private db: StoragePort,
    private ctx: CallContext,
    private approvals: Approvals,
    private accessible: (v: unknown) => boolean,
  ) {}
  interrupt(reason: string, previousRuntime = false) {
    this.db.run(
      "UPDATE intents SET json=json_set(json,'$.status','unknown','$.interruption',?) WHERE json_extract(json,'$.kind')='managed_file' AND json_extract(json,'$.status')='requested' AND (json_extract(json,'$.runtime_id')" +
        (previousRuntime ? "<>" : "=") +
        "?)",
      reason,
      this.ctx.runtime_id,
    );
  }
  read(requestId: string) {
    const r = this.db.get<{ json: string }>(
      "SELECT json FROM intents WHERE request_id=?",
      requestId,
    );
    const e = r ? (JSON.parse(r.json) as EffectRow) : undefined;
    requireThat(
      e?.kind === "managed_file" && this.accessible(e),
      "REFERENCE_NOT_FOUND",
      "Managed attempt unavailable.",
    );
    requireThat(
      e.operation_digest === hash(e.payload),
      "UNKNOWN_EFFECT",
      "Attempt digest mismatch.",
    );
    return e;
  }
  dispatch(effect: FileEffect, previewRef: string, callId: string) {
    const old = this.db.get(
      "SELECT request_id FROM intents WHERE request_id=?",
      effect.request_id,
    );
    requireThat(
      !old,
      "UNKNOWN_EFFECT",
      "This attempt already exists. Inspect its receipt/current bytes; native dispatch is never replayed.",
    );
    this.db.exec("BEGIN IMMEDIATE");
    try {
      const unresolved = this.db
        .all<{ json: string }>(
          "SELECT json FROM intents WHERE json_extract(json,'$.kind')='managed_file' AND json_extract(json,'$.status') IN ('requested','unknown')",
        )
        .map((r) => JSON.parse(r.json) as EffectRow)
        .filter(
          (e) =>
            e.payload.target === effect.target ||
            (effect.work_ref &&
              e.payload.work_ref?.id === effect.work_ref.id &&
              e.payload.step_id === effect.step_id),
        );
      requireThat(
        !unresolved.length ||
          (unresolved.length === 1 &&
            unresolved[0].request_id === effect.retry_of &&
            effect.retry_risk &&
            unresolved[0].observations.length > 0),
        "UNKNOWN_EFFECT",
        "Unresolved prior attempt requires current inspection and a separately approved linked risky repeat; a new ID is not authority.",
      );
      this.approvals.consume(
        previewRef,
        "managed_file",
        effect,
        effect.request_id,
      );
      const e: EffectRow = {
        request_id: effect.request_id,
        kind: "managed_file",
        status: "requested",
        operation_digest: hash(effect),
        payload: effect,
        epoch: this.ctx.epoch,
        preview_ref: previewRef,
        tool_call_id: callId,
        runtime_id: this.ctx.runtime_id,
        observations: [],
        receipt: null,
        receipt_history: [],
      };
      this.db.run(
        "INSERT INTO intents VALUES(?,?,?)",
        e.request_id,
        e.operation_digest,
        JSON.stringify(e),
      );
      this.db.exec("COMMIT");
      return e;
    } catch (err) {
      this.db.exec("ROLLBACK");
      throw err;
    }
  }
  observe(
    requestId: string,
    observation: JsonObject,
    nativeCall?: { id: string; runtime_id: string; is_error: boolean },
  ) {
    this.db.exec("BEGIN IMMEDIATE");
    try {
      const e = this.read(requestId);
      requireThat(
        Buffer.byteLength(canonical(observation)) <= 4000,
        "VALIDATION_ERROR",
        "Native observation exceeds its bounded metadata contract.",
      );
      if (nativeCall)
        requireThat(
          nativeCall.id === e.tool_call_id &&
            nativeCall.runtime_id === e.runtime_id,
          "UNKNOWN_EFFECT",
          "Native result belongs to a different dispatch.",
        );
      e.observations.push({
        ...observation,
        native_result: nativeCall ?? null,
        observed_at: new Date().toISOString(),
      });
      requireThat(
        e.observations.length <= 20,
        "VALIDATION_ERROR",
        "Attempt observation bound reached.",
      );
      const matches =
        observation.hash === e.payload.final_hash &&
        observation.byte_length === e.payload.final_length;
      e.current_observation = {
        ...e.observations.at(-1),
        postcondition_matches: matches,
        drift_from_confirmed: e.status === "confirmed" && !matches,
      };
      const next =
        e.status === "confirmed"
          ? "confirmed"
          : matches
            ? "confirmed"
            : "unknown";
      if (!e.receipt || next !== e.status) {
        e.status = next;
        e.receipt = {
          operation_id: e.request_id,
          request_id: e.request_id,
          state: e.status,
          postcondition_observed: e.status === "confirmed",
          writer_attribution: "unknown",
          native_call_id: e.tool_call_id,
          tool_error: nativeCall?.is_error ?? null,
          last_observation: e.observations.at(-1),
          epoch: this.ctx.epoch,
          receipt_id: "effect-receipt-" + randomUUID(),
        };
        (e.receipt_history ??= []).push(e.receipt);
      }
      this.db.run(
        "UPDATE intents SET json=? WHERE request_id=?",
        JSON.stringify(e),
        requestId,
      );
      this.db.run(
        "INSERT INTO receipts VALUES(?,?,?,?) ON CONFLICT(request_id) DO UPDATE SET json=excluded.json",
        requestId,
        e.operation_digest,
        JSON.stringify(e.receipt),
        "{}",
      );
      this.db.exec("COMMIT");
      return e;
    } catch (err) {
      this.db.exec("ROLLBACK");
      throw err;
    }
  }
}

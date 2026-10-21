import { z } from "zod";
import { randomUUID, createHash } from "node:crypto";
import { addressedIds, addressedRefs, refreshMemory } from "./memory.ts";
import { canonical, requireThat } from "./contracts.ts";
import type { CallContext, RecordRow, StoragePort } from "./contracts.ts";
import type { Approvals } from "./approval.ts";
export const LifecycleSchemaSQL = `
CREATE TABLE IF NOT EXISTS lifecycle_pins(key TEXT PRIMARY KEY,json TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS recovery_barriers(work_id TEXT NOT NULL,step_id TEXT NOT NULL,json TEXT NOT NULL,PRIMARY KEY(work_id,step_id));
CREATE TABLE IF NOT EXISTS lifecycle_events(id TEXT PRIMARY KEY,json TEXT NOT NULL);`;

export const TombstoneSchema = z.strictObject({
  content_not_retained: z.literal(true),
  deleted_at: z.iso.datetime(),
  previous_hash: z.string(),
  content_version: z.number().int().positive().optional(),
});
export const StorageActionSchema = z.strictObject({
  action: z.enum(["archive", "tombstone", "retain", "release"]),
  targets: z
    .array(
      z.strictObject({
        id: z.string().min(1),
        revision: z.number().int().positive(),
      }),
    )
    .min(1)
    .max(10),
});
const hash = (v: unknown) =>
  createHash("sha256").update(canonical(v)).digest("hex");
const fields = (value: unknown, keys: string[]) =>
  value && typeof value === "object"
    ? Object.fromEntries(
        Object.entries(value).filter(([key]) => keys.includes(key)),
      )
    : undefined;
const observationMetadata = (value: unknown) =>
  fields(value, [
    "hash",
    "byte_length",
    "boundary",
    "native_result",
    "observed_at",
    "postcondition_matches",
    "drift_from_confirmed",
  ]);
const receiptMetadata = (value: unknown) => {
  const result = fields(value, [
    "ok",
    "committed",
    "request_id",
    "workspace_id",
    "schema_version",
    "snapshot_seq",
    "transaction_id",
    "created",
    "new_revisions",
    "warnings",
    "operation_id",
    "receipt_id",
    "state",
    "epoch",
    "writer_attribution",
    "postcondition_observed",
    "native_call_id",
    "tool_error",
    "work_ref",
    "step_id",
    "disposition",
  ]);
  const last = (value as { last_observation?: unknown } | null)
    ?.last_observation;
  return result
    ? {
        ...result,
        ...(last ? { last_observation: observationMetadata(last) } : {}),
      }
    : undefined;
};
type Action = z.infer<typeof StorageActionSchema>;
/** Conservative addressed retention. No semantic or frequency-based forgetting. */
export class Lifecycle {
  constructor(
    private db: StoragePort,
    private ctx: CallContext,
    private authorize: () => void,
    private read: (id: string) => RecordRow,
    private approvals: Approvals,
    private allowed: (id: string, revision?: number) => boolean,
  ) {}
  private writeable(r: RecordRow) {
    requireThat(
      this.allowed(r.id),
      "REFERENCE_NOT_FOUND",
      "Record unavailable.",
    );
    const restriction = this.db.get<{ n: number }>(
      "SELECT max(restricted) AS n FROM memory_docs WHERE id=?",
      r.id,
    )?.n;
    requireThat(
      !restriction || this.ctx.scopes?.includes("restricted:write"),
      "PERMISSION_DENIED",
      "Restricted writes require trusted setup scope.",
    );
  }
  private obligation(target: string, selected: Set<string>) {
    type R = { id: string; revision?: number; content_version?: number };
    const queue: { ref: R; root: string }[] = [],
      visited = new Set<string>();
    const add = (value: unknown, root: string) => {
      for (const ref of addressedRefs(value)) queue.push({ ref, root });
    };
    for (const r of this.db.all<{ work_id: string }>(
      "SELECT DISTINCT work_id FROM recovery_barriers WHERE json_extract(json,'$.status')='required'",
    ))
      queue.push({
        ref: { id: r.work_id },
        root: `restored reconciliation ${r.work_id}`,
      });
    for (const { json } of this.db.all<{ json: string }>(
      "SELECT json FROM addressed_current",
    )) {
      const r = JSON.parse(json) as RecordRow;
      if (r.storage === "tombstone") continue;
      if (
        (r.kind === "work" &&
          !["done", "cancelled"].includes(String(r.data.status))) ||
        (String(r.kind) === "signal" &&
          ["open", "observing"].includes(String(r.data.problem_state)))
      ) {
        queue.push({
          ref: { id: r.id, revision: r.revision },
          root: `${r.kind} ${r.id}@${r.revision}`,
        });
      } else if (!selected.has(r.id) && r.kind === "method")
        add(
          {
            dependencies: r.data.dependencies,
            context_requirements: r.data.context_requirements,
            derived_from: r.data.derived_from,
          },
          `current Method ${r.id}@${r.revision}`,
        );
      else if (
        !selected.has(r.id) &&
        r.kind === "knowledge" &&
        r.data.state === "current"
      )
        add(r.data.evidence_refs, `current Knowledge ${r.id}@${r.revision}`);
    }
    for (const { json } of this.db.all<{ json: string }>(
      "SELECT json FROM lifecycle_pins WHERE json_extract(json,'$.kind')='library'",
    )) {
      const pin = JSON.parse(json);
      for (const row of this.db.all<{ revision: number }>(
        "SELECT revision FROM addressed_versions WHERE id=?",
        pin.record_id,
      ))
        queue.push({
          ref: { id: pin.record_id, revision: row.revision },
          root: `library retention ${pin.record_id}`,
        });
    }
    for (const { json } of this.db.all<{ json: string }>(
      "SELECT json FROM intents WHERE json_extract(json,'$.kind')='managed_file' AND json_extract(json,'$.status') IN ('requested','unknown')",
    )) {
      const effect = JSON.parse(json),
        root = `unresolved effect ${effect.request_id}`;
      add(effect.payload, root);
      const preview = this.db.get<{ json: string }>(
        "SELECT json FROM intents WHERE request_id=?",
        effect.preview_ref,
      );
      if (preview) add(JSON.parse(preview.json).payload?.dependencies, root);
    }
    for (let i = 0; i < queue.length; i++) {
      requireThat(
        i < 10000,
        "DEPENDENCY_UNSATISFIED",
        "Exact retention coverage exceeds 10000 addressed nodes; deletion refused.",
      );
      const { ref, root } = queue[i],
        key = canonical(ref);
      if (visited.has(key)) continue;
      visited.add(key);
      if (ref.id === target)
        return `${root} retains required exact dependency ${ref.id}${ref.content_version ? " content-version " + ref.content_version : ref.revision ? " revision " + ref.revision : " current"}.`;
      const row =
        ref.content_version !== undefined
          ? this.db.get<{ json: string }>(
              "SELECT json FROM revisions WHERE id=? AND json_extract(json,'$.data.content_version')=? AND (? IS NULL OR revision=?) ORDER BY revision LIMIT 1",
              ref.id,
              ref.content_version,
              ref.revision ?? null,
              ref.revision ?? null,
            )
          : ref.revision !== undefined
            ? this.db.get<{ json: string }>(
                "SELECT json FROM addressed_versions WHERE id=? AND revision=?",
                ref.id,
                ref.revision,
              )
            : this.db.get<{ json: string }>(
                "SELECT json FROM addressed_current WHERE id=?",
                ref.id,
              );
      const handoff = !row
        ? this.db.get<{ json: string }>(
            "SELECT json FROM handoffs WHERE id=?",
            ref.id,
          )
        : undefined;
      requireThat(
        row || handoff,
        "DEPENDENCY_UNSATISFIED",
        "An obligation has unresolved exact grounds; deletion coverage cannot be established.",
      );
      const r = JSON.parse((row ?? handoff)!.json);
      requireThat(
        r.storage !== "tombstone",
        "DEPENDENCY_UNSATISFIED",
        "An obligation already lacks required retained content; reconcile it before deletion.",
      );
      add(r.data ?? r, root);
    }
    return undefined;
  }
  private blocked(target: RecordRow, selected: Set<string>) {
    const library = this.db.get(
      "SELECT key FROM lifecycle_pins WHERE key=?",
      "library:" + target.id,
    );
    requireThat(
      !library,
      "DEPENDENCY_UNSATISFIED",
      "Explicit library retention pins this record; release that named retention under a separate decision first.",
    );
    requireThat(
      !(
        target.kind === "work" &&
        !["done", "cancelled"].includes(String(target.data.status))
      ),
      "DEPENDENCY_UNSATISFIED",
      "Open Work retains its own body and obligations.",
    );
    const obligation = this.obligation(target.id, selected);
    requireThat(
      !obligation,
      "DEPENDENCY_UNSATISFIED",
      obligation ?? "Required exact grounds are pinned.",
    );
    // All retained current reverse refs are conservatively pinned. This includes
    // open/observing Signals independent of review, exact Method dependencies,
    // completion grounds and open Work. No automatic semantic retirement.
    for (const { json } of this.db.all<{ json: string }>(
      "SELECT json FROM addressed_current",
    )) {
      const r = JSON.parse(json) as RecordRow;
      if (selected.has(r.id) || r.storage === "tombstone") continue;
      if (addressedRefs(r).some((ref) => ref.id === target.id)) {
        const visible = this.allowed(r.id);
        requireThat(
          false,
          "DEPENDENCY_UNSATISFIED",
          visible
            ? `Retained reverse dependency ${r.id} (${r.kind}) pins this body/version; correct or retire the dependency separately.`
            : "A protected retained dependency pins this body/version.",
        );
      }
    }
    const relatedPreviews = new Set(
      this.db
        .all<{ request_id: string; json: string }>(
          "SELECT request_id,json FROM intents WHERE json_extract(json,'$.kind')='preview'",
        )
        .filter((r) => addressedIds(JSON.parse(r.json)).includes(target.id))
        .map((r) => r.request_id),
    );
    for (const { json } of this.db.all<{ json: string }>(
      "SELECT json FROM intents WHERE json_extract(json,'$.kind')='managed_file' AND json_extract(json,'$.status') IN ('requested','unknown')",
    )) {
      const e = JSON.parse(json);
      requireThat(
        !addressedIds(e).includes(target.id) &&
          !relatedPreviews.has(e.preview_ref),
        "UNKNOWN_EFFECT",
        "An unresolved managed effect and its exact preview grounds pin this body/version.",
      );
    }
    for (const { id, json } of this.db.all<{ id: string; json: string }>(
      "SELECT id,json FROM handoffs",
    )) {
      const h = JSON.parse(json),
        work = this.db.get<{ json: string }>(
          "SELECT json FROM records WHERE id=?",
          h.work_ref?.id ?? "",
        );
      if (
        work &&
        !["done", "cancelled"].includes(JSON.parse(work.json).data.status) &&
        addressedRefs(h).some((r) => r.id === target.id)
      )
        requireThat(
          false,
          "DEPENDENCY_UNSATISFIED",
          this.allowed(h.work_ref.id)
            ? `Open handoff ${id} pins this exact source/version.`
            : "A protected open handoff pins this body/version.",
        );
    }
  }
  private exact(request: Action) {
    if (request.action === "tombstone")
      requireThat(
        this.ctx.scopes?.includes("restricted:read") &&
          this.ctx.scopes.includes("restricted:write"),
        "PERMISSION_DENIED",
        "Full retained-version/reverse-dependency body deletion requires fixed full-read/write administrative setup before analysis, independent of hidden data presence.",
      );
    requireThat(
      new Set(request.targets.map((t) => t.id)).size === request.targets.length,
      "VALIDATION_ERROR",
      "Duplicate storage target.",
    );
    return {
      action: request.action,
      targets: request.targets.map((ref) => {
        const r = this.read(ref.id);
        this.writeable(r);
        requireThat(
          r.revision === ref.revision,
          "REVISION_CONFLICT",
          "Storage target changed.",
        );
        requireThat(
          r.storage !== "tombstone",
          "CONTENT_NOT_RETAINED",
          "Body was already removed.",
        );
        if (request.action === "tombstone")
          this.blocked(r, new Set(request.targets.map((t) => t.id)));
        const versions = this.db.all<{ revision: number; json: string }>(
          "SELECT revision,json FROM revisions WHERE id=? ORDER BY revision",
          r.id,
        );
        requireThat(
          versions.every((v) => this.allowed(r.id, v.revision)),
          "REFERENCE_NOT_FOUND",
          "Retained version unavailable.",
        );
        return {
          id: r.id,
          kind: r.kind,
          title: r.title,
          revision: r.revision,
          storage: r.storage,
          versions: versions.map((v) => ({
            revision: v.revision,
            hash: hash(JSON.parse(v.json)),
          })),
          blob_hashes: [
            ...new Set(
              versions.flatMap((v) => {
                const d = JSON.parse(v.json).data;
                return [d.blob_ref, d.extraction?.text_blob_ref].filter(
                  (h): h is string => typeof h === "string",
                );
              }),
            ),
          ].sort(),
        };
      }),
      coverage:
        request.action === "tombstone"
          ? "All retained versions of selected IDs, current bodies, managed history/intents/preview payload copies and FTS. Managed blob copies become inaccessible for the deleted IDs; unreferenced unpinned blobs are eligible for exact cleanup. Independently retained shared blobs, prior generations, external backups/exports/Pi transcripts/logs are separate copies; no forensic erasure."
          : "Storage state or explicit library retention only; archive is not deletion.",
    };
  }
  preview(input: unknown, consequence: string, alternatives: string) {
    this.authorize();
    const request = StorageActionSchema.parse(input),
      exact = this.exact(request);
    return this.approvals.draft(
      "storage",
      exact,
      request.targets.map((r) => ({ id: r.id, revision: r.revision })),
      consequence,
      alternatives,
    );
  }
  apply(ref: string) {
    this.authorize();
    const p = this.approvals.read(ref),
      request = {
        action: p.payload.exact.action,
        targets: (
          p.payload.exact.targets as { id: string; revision: number }[]
        ).map((t) => ({ id: t.id, revision: t.revision })),
      };
    const action = StorageActionSchema.parse(request),
      exact = this.exact(action),
      requestId = "storage-" + randomUUID(),
      now = new Date().toISOString();
    this.db.exec("BEGIN IMMEDIATE");
    try {
      this.authorize();
      this.approvals.consume(ref, "storage", this.exact(action), requestId);
      const changed: Record<string, { before: number; after: number }> = {};
      const redactedIds = new Set(action.targets.map((t) => t.id));
      for (const target of exact.targets) {
        const current = this.read(target.id);
        if (action.action === "retain" || action.action === "release") {
          if (action.action === "retain")
            this.db.run(
              "INSERT OR REPLACE INTO lifecycle_pins VALUES(?,?)",
              "library:" + current.id,
              JSON.stringify({
                kind: "library",
                record_id: current.id,
                reason: p.payload.consequence,
                expires_at: null,
              }),
            );
          else
            this.db.run(
              "DELETE FROM lifecycle_pins WHERE key=?",
              "library:" + current.id,
            );
          continue;
        }
        const next: RecordRow = {
          ...current,
          storage: action.action === "archive" ? "archive" : "tombstone",
          revision: current.revision + 1,
          updated_at: now,
        };
        if (action.action === "tombstone") {
          const effectiveRestricted = !!this.db.get<{ n: number }>(
            "SELECT max(restricted) AS n FROM memory_docs WHERE id=?",
            current.id,
          )?.n;
          const tombstone = (row: RecordRow): RecordRow => ({
            ...row,
            visibility: effectiveRestricted ? "restricted" : row.visibility,
            title: "Content not retained",
            body: null,
            concept_ids: [],
            origin_activity_id: null,
            storage: "tombstone",
            data: TombstoneSchema.parse({
              content_not_retained: true,
              deleted_at: now,
              previous_hash: hash(row),
              ...(row.kind === "method"
                ? { content_version: row.data.content_version }
                : {}),
            }),
          });
          Object.assign(next, tombstone(next));
          for (const old of this.db.all<{ revision: number; json: string }>(
            "SELECT revision,json FROM revisions WHERE id=?",
            current.id,
          ))
            this.db.run(
              "UPDATE revisions SET json=? WHERE id=? AND revision=?",
              JSON.stringify(tombstone(JSON.parse(old.json))),
              current.id,
              old.revision,
            );
          // Remove whole addressed technical payload copies, preserve stable
          // request/digest/receipt identity. Hash remains evidence of original bytes.
          for (const table of [
            "intents",
            "changes",
            "lifecycle_events",
            "retrieval_trace",
            "handoffs",
            "receipts",
          ]) {
            const key =
              table === "intents" || table === "receipts"
                ? "request_id"
                : table === "changes" || table === "retrieval_trace"
                  ? "seq"
                  : "id";
            for (const entry of this.db.all<{
              key: string | number;
              json: string;
            }>(`SELECT ${key} AS key,json FROM ${table}`)) {
              const value = JSON.parse(entry.json);
              if (addressedIds(value).some((id) => redactedIds.has(id))) {
                if (typeof entry.key === "string") redactedIds.add(entry.key);
                const redacted = {
                  id: value.id,
                  request_id: value.request_id,
                  kind: value.kind ?? "change",
                  status: value.status ?? "committed",
                  operation_digest: value.operation_digest ?? hash(value),
                  epoch: value.epoch,
                  visibility: value.visibility,
                  work_ref: value.work_ref,
                  payload_not_retained: true,
                  affected_ids: [current.id],
                  receipt: receiptMetadata(value.receipt),
                  receipt_history: Array.isArray(value.receipt_history)
                    ? value.receipt_history.map(receiptMetadata)
                    : undefined,
                  observations: Array.isArray(value.observations)
                    ? value.observations.map(observationMetadata)
                    : undefined,
                  current_observation: observationMetadata(
                    value.current_observation,
                  ),
                  seq: value.seq,
                  transaction_id: value.transaction_id,
                  changed: value.changed,
                  changed_refs: value.changed_refs,
                  refs: value.refs,
                  operation: value.operation,
                  input_sha256: value.input ? hash(value.input) : undefined,
                };
                this.db.run(
                  `UPDATE ${table} SET json=? WHERE ${key}=?`,
                  JSON.stringify(
                    table === "receipts" ? receiptMetadata(value) : redacted,
                  ),
                  entry.key,
                );
              }
            }
          }
        }
        this.db.run(
          "UPDATE records SET json=? WHERE id=?",
          JSON.stringify(next),
          next.id,
        );
        this.db.run(
          "INSERT INTO revisions VALUES(?,?,?)",
          next.id,
          next.revision,
          JSON.stringify(next),
        );
        changed[next.id] = { before: current.revision, after: next.revision };
      }
      const seq = this.db.get<{ n: number }>(
        "SELECT coalesce(max(seq),0)+1 AS n FROM changes",
      )!.n;
      const receipt = {
        ok: true,
        committed: true,
        request_id: requestId,
        workspace_id: this.ctx.workspace_id,
        epoch: this.ctx.epoch,
        transaction_id: requestId,
        snapshot_seq: seq,
        action: action.action,
        targets: action.targets,
        coverage: exact.coverage,
        blob_cleanup:
          "Separate exact cleanup required; independent copies are outside this body operation.",
      };
      this.db.run(
        "INSERT INTO changes VALUES(?,?)",
        seq,
        JSON.stringify({
          seq,
          transaction_id: requestId,
          changed,
          actor: this.ctx.principal,
          reason: "Exact bound storage operation",
          recorded_at: now,
        }),
      );
      this.db.run(
        "INSERT INTO intents VALUES(?,?,?)",
        requestId,
        hash(exact),
        JSON.stringify({
          request_id: requestId,
          kind: "storage",
          status: "committed",
          epoch: this.ctx.epoch,
          payload: { action: action.action, targets: action.targets },
          receipt,
        }),
      );
      this.db.run(
        "INSERT INTO receipts VALUES(?,?,?,?)",
        requestId,
        hash(exact),
        JSON.stringify(receipt),
        "{}",
      );
      refreshMemory(this.db, true);
      this.db.exec("COMMIT");
      return receipt;
    } catch (err) {
      this.db.exec("ROLLBACK");
      throw err;
    }
  }
}

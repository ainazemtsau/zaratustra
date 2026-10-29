import { createHash, randomUUID } from "node:crypto";
import { z } from "zod";
import type { AddressedRow, StoragePort } from "./contracts.ts";

export const SEMANTIC_FILE_BYTES = 256 * 1024;
export const TRANSIENT_MAX_BYTES = 20 * 1024 * 1024;
export const TRANSIENT_MAX_AGE_MS = 7 * 24 * 60 * 60 * 1000;
export const SOURCE_FRAGMENT_MAX_BYTES = 4096;

const id = z.string().min(1).max(4000);
const ref = z.strictObject({
  id,
  revision: z.number().int().positive().optional(),
  content_version: z.number().int().positive().optional(),
});
export const DurablePurposeSchema = z.enum([
  "continuation",
  "obligation",
  "constraint",
  "decision",
  "reusable_experience",
  "selected_source",
]);
export type DurablePurpose = z.infer<typeof DurablePurposeSchema>;
export const RetentionSchema = z
  .strictObject({
    class: z.enum(["transient", "working", "durable"]),
    purpose: DurablePurposeSchema.optional(),
    reason: z.string().min(1).max(4000).optional(),
  })
  .refine((v) => v.class === "transient" || !!v.purpose, {
    message: "Working or durable memory needs an explicit future purpose.",
  });
export type Retention = z.infer<typeof RetentionSchema>;

/** Optional ActivityData.contract. Metadata is agent-maintained, never a questionnaire. */
export const ActivityContractSchema = z.strictObject({
  summary: z.string().min(1).max(4000),
  boundaries: z.string().max(4000).optional(),
  current_context: z.string().max(4000).optional(),
  context_refs: z.array(ref).max(100).default([]),
  document_refs: z.array(ref).max(100).default([]),
  procedure_refs: z.array(ref).max(30).default([]),
  memory_scope: z.enum(["activity", "shared"]).default("activity"),
});
export type ActivityContract = z.infer<typeof ActivityContractSchema>;

export const SourceFragmentSchema = z
  .strictObject({
    start: z.number().int().nonnegative(),
    end: z.number().int().nonnegative(),
  })
  .refine((v) => v.end > v.start, {
    message: "Source fragment must be a nonempty Unicode-code-point range.",
  });
export type SourceFragment = z.infer<typeof SourceFragmentSchema>;
const sha = (text: string) =>
  createHash("sha256").update(text, "utf8").digest("hex");

/** Preserve exact observed characters. A hash of omitted text is not retained evidence. */
export function exactSourceFragment(
  text: string,
  range: SourceFragment,
  maxBytes = SOURCE_FRAGMENT_MAX_BYTES,
) {
  const r = SourceFragmentSchema.parse(range);
  const characters = Array.from(text);
  z.number().int().min(r.end).parse(characters.length);
  const retained = characters.slice(r.start, r.end).join("");
  z.number().int().positive().max(SEMANTIC_FILE_BYTES).parse(maxBytes);
  z.number().max(maxBytes).parse(Buffer.byteLength(retained));
  return {
    text: retained,
    start: r.start,
    end: r.end,
    unit: "unicode_code_points" as const,
    source_characters: characters.length,
    source_hash: sha(text),
    fragment_hash: sha(retained),
    availability: "retained_fragment" as const,
  };
}

/** Caller selects purpose; no keyword classifier, success counter or extra LLM. */
export function memoryRetention(input: {
  purpose?: DurablePurpose;
  class?: Retention["class"];
  reason?: string;
}): Retention {
  return RetentionSchema.parse({
    class: input.class ?? (input.purpose ? "durable" : "transient"),
    ...(input.purpose ? { purpose: input.purpose } : {}),
    ...(input.reason ? { reason: input.reason } : {}),
  });
}

export function retainedSourceText(
  text: string,
  options: { purpose: DurablePurpose; fragment?: SourceFragment },
) {
  DurablePurposeSchema.parse(options.purpose);
  if (options.fragment) return exactSourceFragment(text, options.fragment);
  if (options.purpose === "selected_source")
    return {
      text,
      source_hash: sha(text),
      fragment_hash: sha(text),
      start: 0,
      end: Array.from(text).length,
      unit: "unicode_code_points" as const,
      source_characters: Array.from(text).length,
      availability: "retained_original" as const,
    };
  return exactSourceFragment(text, { start: 0, end: Array.from(text).length });
}

export const TransientCandidateSchema = z.strictObject({
  id,
  created_at: z.iso.datetime(),
  byte_length: z
    .number()
    .int()
    .nonnegative()
    .max(8 * 1024 * 1024),
  pins: z
    .array(
      z.enum([
        "open_work",
        "active_constraint",
        "selected_source",
        "unknown_effect",
        "pending_change",
      ]),
    )
    .max(5)
    .default([]),
});
export type TransientCandidate = z.infer<typeof TransientCandidateSchema>;

/** Pure plan: storage applies removals only after checking current refs/pins again. */
export function planTransientCleanup(
  entries: TransientCandidate[],
  now = Date.now(),
  incomingBytes = 0,
) {
  const rows = z.array(TransientCandidateSchema).max(10000).parse(entries);
  z.literal(rows.length).parse(new Set(rows.map((r) => r.id)).size);
  z.number().finite().nonnegative().parse(now);
  z.number().int().nonnegative().max(TRANSIENT_MAX_BYTES).parse(incomingBytes);
  const protectedRows = rows.filter((r) => r.pins.length > 0);
  const removable = rows
    .filter((r) => r.pins.length === 0)
    .sort(
      (a, b) =>
        Date.parse(a.created_at) - Date.parse(b.created_at) ||
        a.id.localeCompare(b.id),
    );
  let remaining = rows.reduce((n, r) => n + r.byte_length, 0);
  const remove: string[] = [];
  for (const row of removable) {
    if (
      Date.parse(row.created_at) <= now - TRANSIENT_MAX_AGE_MS ||
      remaining + incomingBytes > TRANSIENT_MAX_BYTES
    ) {
      remove.push(row.id);
      remaining -= row.byte_length;
    }
  }
  return {
    remove,
    retained_bytes: remaining,
    protected_bytes: protectedRows.reduce((n, r) => n + r.byte_length, 0),
    admission_blocked: remaining + incomingBytes > TRANSIENT_MAX_BYTES,
    over_budget_bytes: Math.max(
      0,
      remaining + incomingBytes - TRANSIENT_MAX_BYTES,
    ),
  };
}

/** Missing metadata remains active for compatibility; direct reads never use this filter. */
export function activeCorpusSQL(
  db: {
    get<T>(sql: string, ...params: (string | number | null)[]): T | undefined;
  },
  recordIdSQL: string,
  revisionSQL: string,
): string {
  if (
    !db.get(
      "SELECT name FROM sqlite_schema WHERE type='table' AND name='corpus_entries'",
    )
  )
    return "1";
  return `NOT EXISTS(SELECT 1 FROM corpus_entries ce WHERE ce.id=${recordIdSQL} AND ce.revision=${revisionSQL} AND ce.contour='legacy')`;
}

export const CandidateInputSchema = z.strictObject({
  kind: z.enum(["deferred_candidate", "diagnostic"]),
  summary: z.string().min(1).max(4000),
  content: z.string().min(1).max(SEMANTIC_FILE_BYTES),
  related_refs: z.array(ref).max(20).default([]),
  visibility: z.enum(["workspace", "restricted"]).default("workspace"),
});
export type CandidateInput = z.input<typeof CandidateInputSchema>;
export const MemoryCandidatesSchemaSQL = `CREATE TABLE IF NOT EXISTS memory_candidates(id TEXT PRIMARY KEY,json TEXT NOT NULL);`;
type CandidatePin = TransientCandidate["pins"][number];
type Candidate = z.infer<typeof CandidateInputSchema> &
  TransientCandidate & {
    schema_version: 1;
    pinned: boolean;
    basis: "unverified_candidate";
  };
export class MemoryPolicyError extends Error {
  constructor(
    public code: string,
    message: string,
  ) {
    super(message);
  }
}
export interface CandidateAuthority {
  authorize(write: boolean): void;
  canReadRef(ref: { id: string; revision?: number }): boolean;
  isRestrictedRef(ref: { id: string; revision?: number }): boolean;
  canReadRestricted(): boolean;
  canWriteRestricted(): boolean;
}
/** Explicit temporary questions/diagnostics, never automatic per-tool logging.
 * Only pinned rows are portable canonical working state; unpinned rows are cache.
 */
export class TransientMemory {
  constructor(
    private db: StoragePort,
    private authority: CandidateAuthority,
  ) {}
  private phase<T>(write: boolean, callback: () => T): T {
    const action = () => {
      this.authority.authorize(write);
      return callback();
    };
    return this.db.withCommandSync
      ? this.db.withCommandSync(action, write ? "mutate" : "read")
      : action();
  }
  private rows(): Candidate[] {
    if (
      !this.db.get(
        "SELECT name FROM sqlite_schema WHERE name='memory_candidates'",
      )
    )
      return [];
    return this.db
      .all<{ json: string }>("SELECT json FROM memory_candidates")
      .map((r) => JSON.parse(r.json) as Candidate);
  }
  private permitted(row: Candidate, write = false) {
    if (!row.related_refs.every((r) => this.authority.canReadRef(r)))
      return false;
    const restricted =
      row.visibility === "restricted" ||
      row.related_refs.some((r) => this.authority.isRestrictedRef(r));
    return (
      !restricted ||
      (write
        ? this.authority.canWriteRestricted()
        : this.authority.canReadRestricted())
    );
  }
  private pins(row: Candidate): CandidatePin[] {
    const pins = new Set<CandidatePin>();
    for (const ref of row.related_refs) {
      const stored = this.db.get<{ json: string }>(
        "SELECT json FROM addressed_current WHERE id=?",
        ref.id,
      );
      if (!stored) {
        pins.add("pending_change");
        continue;
      }
      const r = JSON.parse(stored.json) as AddressedRow;
      if (
        r.kind === "work" &&
        !["done", "cancelled"].includes(String(r.data.status))
      )
        pins.add("open_work");
      if (
        r.kind === "knowledge" &&
        r.data.state === "current" &&
        r.data.knowledge_kind === "constraint"
      )
        pins.add("active_constraint");
      if (r.kind === "evidence" && r.data.durable_purpose === "selected_source")
        pins.add("selected_source");
      if (r.kind === "run" && r.data.execution === "running")
        pins.add("pending_change");
      if (
        this.db.get(
          "SELECT name FROM sqlite_schema WHERE name='recovery_barriers'",
        ) &&
        this.db.get(
          "SELECT 1 FROM recovery_barriers WHERE work_id=? AND json_extract(json,'$.status')='required' LIMIT 1",
          ref.id,
        )
      )
        pins.add("unknown_effect");
    }
    return [...pins];
  }
  private encoded(row: Candidate): string {
    // The cap covers persisted bytes, including metadata and JSON escaping.
    let json = JSON.stringify(row);
    while (row.byte_length !== Buffer.byteLength(json)) {
      row.byte_length = Buffer.byteLength(json);
      json = JSON.stringify(row);
    }
    return json;
  }
  private alive(row: Candidate, now: number) {
    return (
      this.pins(row).length > 0 ||
      Date.parse(row.created_at) > now - TRANSIENT_MAX_AGE_MS
    );
  }
  private cleanup(now: number, incomingBytes: number) {
    const rows = this.rows();
    const metadata = rows.map((row) => {
      if (!this.permitted(row, true))
        return {
          id: row.id,
          created_at: row.created_at,
          byte_length: row.byte_length,
          pins: ["pending_change" as const],
        };
      const pins = this.pins(row),
        pinned = pins.length > 0;
      if (
        pinned !== row.pinned ||
        JSON.stringify(pins) !== JSON.stringify(row.pins)
      ) {
        row.pinned = pinned;
        row.pins = pins;
        this.db.run(
          "UPDATE memory_candidates SET json=? WHERE id=?",
          this.encoded(row),
          row.id,
        );
      }
      return {
        id: row.id,
        created_at: row.created_at,
        byte_length: row.byte_length,
        pins,
      };
    });
    const plan = planTransientCleanup(metadata, now, incomingBytes);
    for (const id of plan.remove)
      this.db.run("DELETE FROM memory_candidates WHERE id=?", id);
    return plan;
  }
  put(input: CandidateInput, now = Date.now()) {
    return this.phase(true, () => {
      const v = CandidateInputSchema.parse(input);
      if (v.related_refs.some((r) => !this.authority.canReadRef(r)))
        throw new MemoryPolicyError(
          "REFERENCE_NOT_FOUND",
          "Candidate grounds are unavailable.",
        );
      const visibility =
        v.visibility === "restricted" ||
        v.related_refs.some((r) => this.authority.isRestrictedRef(r))
          ? ("restricted" as const)
          : ("workspace" as const);
      if (visibility === "restricted" && !this.authority.canWriteRestricted())
        throw new MemoryPolicyError(
          "PERMISSION_DENIED",
          "Restricted candidate needs trusted write scope.",
        );
      this.db.exec(MemoryCandidatesSchemaSQL);
      const row: Candidate = {
        ...v,
        visibility,
        id: "candidate-" + randomUUID(),
        schema_version: 1,
        created_at: new Date(now).toISOString(),
        byte_length: Buffer.byteLength(v.content),
        pins: [],
        pinned: false,
        basis: "unverified_candidate",
      };
      row.pins = this.pins(row);
      row.pinned = row.pins.length > 0;
      if (
        Buffer.byteLength(v.content) > SEMANTIC_FILE_BYTES ||
        Buffer.byteLength(v.content) > SOURCE_FRAGMENT_MAX_BYTES
      )
        throw new MemoryPolicyError(
          "SOURCE_FRAGMENT_REQUIRED",
          "Keep only the sufficient candidate fragment; selected originals belong in Sources.",
        );
      const encoded = this.encoded(row);
      if (row.byte_length > SEMANTIC_FILE_BYTES)
        throw new MemoryPolicyError(
          "SOURCE_FRAGMENT_REQUIRED",
          "Split or shorten the candidate, including its metadata.",
        );
      this.db.exec("SAVEPOINT candidate_put");
      try {
        const plan = this.cleanup(now, row.byte_length);
        if (plan.admission_blocked)
          throw new MemoryPolicyError(
            "TRANSIENT_MEMORY_FULL",
            "Protected temporary material needs consolidation before accepting more; nothing protected was deleted.",
          );
        this.db.run(
          "INSERT INTO memory_candidates VALUES(?,?)",
          row.id,
          encoded,
        );
        this.db.exec("RELEASE candidate_put");
      } catch (e) {
        this.db.exec("ROLLBACK TO candidate_put; RELEASE candidate_put;");
        throw e;
      }
      return {
        id: row.id,
        pinned: row.pinned,
        visibility: row.visibility,
        basis: row.basis,
      };
    });
  }
  list(now = Date.now()) {
    return this.phase(false, () =>
      this.rows()
        .filter((r) => this.permitted(r) && this.alive(r, now))
        .map((r) => ({
          id: r.id,
          kind: r.kind,
          summary: r.summary,
          created_at: r.created_at,
          pinned: this.pins(r).length > 0,
          related_refs: r.related_refs,
          basis: r.basis,
        })),
    );
  }
  read(id: string, now = Date.now()) {
    return this.phase(false, () => {
      const row = this.rows().find((r) => r.id === id);
      if (!row || !this.permitted(row) || !this.alive(row, now))
        throw new MemoryPolicyError(
          "REFERENCE_NOT_FOUND",
          "Candidate is unavailable.",
        );
      const pins = this.pins(row);
      return { ...row, pins, pinned: pins.length > 0 };
    });
  }
  remove(id: string) {
    return this.phase(true, () => {
      const row = this.rows().find((r) => r.id === id);
      if (!row || !this.permitted(row, true))
        throw new MemoryPolicyError(
          "REFERENCE_NOT_FOUND",
          "Candidate is unavailable.",
        );
      if (this.pins(row).length)
        throw new MemoryPolicyError(
          "CONTENT_IN_USE",
          "Candidate grounds are still tied to an open obligation or protected material.",
        );
      this.db.run("DELETE FROM memory_candidates WHERE id=?", id);
      return { removed: true };
    });
  }
  sweep(now = Date.now()) {
    return this.phase(true, () => ({ removed: this.cleanup(now, 0).remove }));
  }
}
export function candidateGrounds(db: StoragePort) {
  if (!db.get("SELECT name FROM sqlite_schema WHERE name='memory_candidates'"))
    return [];
  return db
    .all<{
      json: string;
    }>(
      "SELECT json FROM memory_candidates WHERE json_extract(json,'$.pinned')=1",
    )
    .flatMap(({ json }) => (JSON.parse(json) as Candidate).related_refs);
}

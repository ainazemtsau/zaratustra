import { createHash, randomUUID } from "node:crypto";
import { z } from "zod";
import {
  ConceptData,
  EntityData,
  KnowledgeData,
  CoreError,
  requireThat,
  canonical,
} from "./contracts.ts";
import type {
  CallContext,
  JsonObject,
  RecordRow,
  StoragePort,
  AddressedRow,
} from "./contracts.ts";

const hash = (v: unknown) =>
  createHash("sha256").update(canonical(v)).digest("hex");
export const MemorySchemaSQL = `
 CREATE TABLE memory_meta(seq INTEGER NOT NULL, build INTEGER NOT NULL);
 INSERT INTO memory_meta VALUES(0,1);
 CREATE TABLE memory_docs(docid INTEGER PRIMARY KEY,id TEXT NOT NULL,revision INTEGER NOT NULL,restricted INTEGER NOT NULL,UNIQUE(id,revision));
 CREATE INDEX memory_access ON memory_docs(id,revision,restricted);
 CREATE VIRTUAL TABLE memory_text USING fts5(text,tokenize='porter unicode61');
 CREATE VIRTUAL TABLE memory_names USING fts5(names,tokenize='unicode61 remove_diacritics 0');
 CREATE TABLE memberships(record_id TEXT NOT NULL,concept_id TEXT NOT NULL,PRIMARY KEY(record_id,concept_id));
 CREATE INDEX membership_concept ON memberships(concept_id,record_id);
 CREATE TABLE concept_parents(child_id TEXT NOT NULL,parent_id TEXT NOT NULL,PRIMARY KEY(child_id,parent_id));
 CREATE INDEX parent_children ON concept_parents(parent_id,child_id);
 CREATE TABLE relations(id TEXT PRIMARY KEY,json TEXT NOT NULL);
 CREATE TABLE relation_history(id TEXT NOT NULL,seq INTEGER NOT NULL,json TEXT NOT NULL,PRIMARY KEY(id,seq));
 CREATE TABLE retrieval_trace(seq INTEGER PRIMARY KEY,access_key TEXT NOT NULL,json TEXT NOT NULL);
 CREATE INDEX trace_access ON retrieval_trace(access_key,seq);
 CREATE INDEX knowledge_predicate ON records(json_extract(json,'$.data.predicate'));
 CREATE INDEX knowledge_subject ON records(json_extract(json,'$.data.subject_ref.id'));
 CREATE INDEX knowledge_object ON records(json_extract(json,'$.data.object_ref.id'));`;

export function addressedIds(value: unknown): string[] {
  const found = new Set<string>();
  const walk = (v: unknown) => {
    // Match the existing JSON-tree technical classifier at every depth,
    // including string-ID arrays in redacted metadata such as affected_ids.
    if (typeof v === "string") found.add(v);
    else if (Array.isArray(v)) v.forEach(walk);
    else if (v && typeof v === "object") {
      const o = v as JsonObject;
      if (typeof o.id === "string") found.add(o.id);
      if (
        o.changed &&
        typeof o.changed === "object" &&
        !Array.isArray(o.changed)
      )
        Object.keys(o.changed).forEach((id) => found.add(id));
      // Technical rows also carry string IDs outside typed Ref objects.
      for (const [k, child] of Object.entries(o)) {
        if (
          ["work_id", "record_id", "relation_id"].includes(k) &&
          typeof child === "string"
        )
          found.add(child);
        if (typeof child === "string") found.add(child);
        walk(child);
      }
    }
  };
  walk(value);
  return [...found];
}
export function addressedRefs(
  value: unknown,
): { id: string; revision?: number; content_version?: number }[] {
  const refs: { id: string; revision?: number; content_version?: number }[] =
    [];
  const walk = (v: unknown) => {
    if (Array.isArray(v)) v.forEach(walk);
    else if (v && typeof v === "object") {
      const o = v as JsonObject;
      if (
        typeof o.id === "string" &&
        Object.keys(o).every((k) =>
          ["id", "revision", "content_version"].includes(k),
        )
      )
        refs.push(
          o as { id: string; revision?: number; content_version?: number },
        );
      Object.values(o).forEach(walk);
    }
  };
  walk(value);
  return refs;
}
export function validateMemory(
  final: RecordRow[],
  get: (ref: unknown, kind?: string) => RecordRow,
) {
  const concepts = new Map<string, string[]>();
  for (const r of final) {
    if (r.storage === "tombstone") continue;
    for (const c of r.concept_ids) get(c, "concept");
    if (r.origin_activity_id) get(r.origin_activity_id, "activity");
    if (r.kind === "concept") {
      const c = ConceptData.parse(r.data);
      requireThat(
        new Set(c.aliases).size === c.aliases.length,
        "VALIDATION_ERROR",
        "Duplicate aliases.",
      );
      const parents = c.broader_ids.map((ref) => {
        requireThat(
          "id" in ref && ref.revision === undefined,
          "VALIDATION_ERROR",
          "Category parents use current refs.",
        );
        return get(ref, "concept").id;
      });
      requireThat(
        new Set(parents).size === parents.length,
        "VALIDATION_ERROR",
        "Duplicate broader parents.",
      );
      concepts.set(r.id, parents);
    }
    if (["concept", "entity", "activity"].includes(r.kind)) {
      if (r.kind === "entity") EntityData.parse(r.data);
      requireThat(
        (r.data.status === "merged") === !!r.data.redirect_to,
        "VALIDATION_ERROR",
        "Only merged identities have a redirect.",
      );
      const seen = new Set<string>([r.id]);
      let next = r.data.redirect_to;
      while (next) {
        const target = get(next, r.kind);
        requireThat(
          !seen.has(target.id),
          "GRAPH_CYCLE",
          "Identity redirect cycle.",
        );
        seen.add(target.id);
        next = target.data.redirect_to;
      }
    }
    if (r.kind === "knowledge") {
      const k = KnowledgeData.parse(r.data);
      requireThat(
        k.state !== "current" || k.evidence_refs.length > 0,
        "SOURCE_MISSING",
        "Current Knowledge needs resolvable retained grounds; use tentative for unsupported inference.",
      );
      requireThat(
        !k.valid_from ||
          !k.valid_to ||
          Date.parse(k.valid_from) <= Date.parse(k.valid_to),
        "VALIDATION_ERROR",
        "Validity interval is reversed.",
      );
      for (const ref of k.evidence_refs) {
        const e = get(ref, "evidence");
        requireThat(
          e.data.availability === "retained",
          "SOURCE_MISSING",
          "Knowledge grounds are not retained.",
        );
      }
      if (k.representation) get(k.representation.source_ref, "evidence");
      if (k.subject_ref) get(k.subject_ref, "entity");
      if (k.object_ref) get(k.object_ref, "entity");
      requireThat(
        !(k.object_ref && k.value),
        "VALIDATION_ERROR",
        "Use object_ref or value, not both.",
      );
      for (const ref of k.supersedes_refs ?? []) {
        const old = get(ref, "knowledge");
        requireThat(
          old.id !== r.id,
          "GRAPH_CYCLE",
          "A claim cannot supersede itself.",
        );
        const current = get({ id: old.id }, "knowledge");
        requireThat(
          ["superseded", "retracted"].includes(current.data.state as string),
          "INVALID_TRANSITION",
          "A replaced claim must cease being current in the same transaction.",
        );
      }
    }
  }
  const visited = new Set<string>(),
    visiting = new Set<string>();
  const visit = (id: string) => {
    requireThat(
      !visiting.has(id),
      "GRAPH_CYCLE",
      "Concept broader graph contains a cycle.",
    );
    if (visited.has(id)) return;
    visiting.add(id);
    for (const parent of concepts.get(id) ?? []) visit(parent);
    visiting.delete(id);
    visited.add(id);
  };
  concepts.forEach((_, id) => visit(id));
}

/** Derived indexes only. Caller owns the short SQLite transaction. */
export function refreshMemory(
  storage: StoragePort,
  rebuild = false,
  rewrittenIds: readonly string[] = [],
) {
  const experience = !!storage.get(
    "SELECT name FROM sqlite_master WHERE type='view' AND name='addressed_current'",
  );
  const current = storage
    .all<{
      json: string;
    }>("SELECT json FROM " + (experience ? "addressed_current" : "records"))
    .map((r) => JSON.parse(r.json) as AddressedRow);
  const byId = new Map(current.map((r) => [r.id, r]));
  const versions = storage
    .all<{
      json: string;
    }>(
      "SELECT json FROM " +
        (experience ? "addressed_versions" : "revisions") +
        " ORDER BY id,revision",
    )
    .map((row) => JSON.parse(row.json) as AddressedRow);
  const versionKey = (r: AddressedRow) => r.id + ":" + r.revision;
  const versionRestrictions = new Map(
    versions.map((r) => [versionKey(r), r.visibility === "restricted"]),
  );
  const versionRefs = new Map(
    versions.map((r) => [
      versionKey(r),
      addressedRefs(r).map((ref) => {
        if (ref.revision !== undefined) return ref.id + ":" + ref.revision;
        if (ref.content_version !== undefined) {
          const target = versions.find(
            (v) =>
              v.id === ref.id &&
              v.kind === "method" &&
              v.data.content_version === ref.content_version,
          );
          return target ? versionKey(target) : "";
        }
        const target = byId.get(ref.id);
        return target ? versionKey(target) : "";
      }),
    ]),
  );
  const restrictions = new Map<string, boolean>();
  // Monotone fixed point handles legitimate cyclic reference graphs without recursive leakage.
  current.forEach((r) => restrictions.set(r.id, r.visibility === "restricted"));
  let changed = true;
  while (changed) {
    changed = false;
    for (const r of current)
      if (
        !restrictions.get(r.id) &&
        addressedIds(r).some((id) => restrictions.get(id))
      ) {
        restrictions.set(r.id, true);
        changed = true;
      }
    for (const r of versions) {
      const key = versionKey(r);
      if (
        !versionRestrictions.get(key) &&
        (restrictions.get(r.id) ||
          addressedIds(r).some((id) => restrictions.get(id)) ||
          versionRefs.get(key)!.some((key) => versionRestrictions.get(key)))
      ) {
        versionRestrictions.set(key, true);
        changed = true;
        if (byId.get(r.id)?.revision === r.revision)
          restrictions.set(r.id, true);
      }
    }
  }
  if (rebuild) {
    storage.exec(
      "DELETE FROM memory_text; DELETE FROM memory_names; DELETE FROM memory_docs;",
    );
  } else
    for (const id of new Set(rewrittenIds)) {
      // Rewritten retained bodies need fresh text, but unrelated docids/cursors
      // must remain stable, including for observers unable to see this target.
      for (const { docid } of storage.all<{ docid: number }>(
        "SELECT docid FROM memory_docs WHERE id=?",
        id,
      )) {
        storage.run("DELETE FROM memory_text WHERE rowid=?", docid);
        storage.run("DELETE FROM memory_names WHERE rowid=?", docid);
      }
      storage.run("DELETE FROM memory_docs WHERE id=?", id);
    }
  for (const r of versions) {
    const restricted =
      r.visibility === "restricted" ||
      restrictions.get(r.id) ||
      addressedIds(r).some((id) => restrictions.get(id));
    const effectiveRestricted =
      restricted || versionRestrictions.get(versionKey(r));
    const exists = storage.get<{ docid: number }>(
      "SELECT docid FROM memory_docs WHERE id=? AND revision=?",
      r.id,
      r.revision,
    );
    if (exists)
      storage.run(
        "UPDATE memory_docs SET restricted=? WHERE docid=?",
        effectiveRestricted ? 1 : 0,
        exists.docid,
      );
    else {
      storage.run(
        "INSERT INTO memory_docs(id,revision,restricted) VALUES(?,?,?)",
        r.id,
        r.revision,
        effectiveRestricted ? 1 : 0,
      );
      const doc = storage.get<{ docid: number }>(
        "SELECT docid FROM memory_docs WHERE id=? AND revision=?",
        r.id,
        r.revision,
      )!;
      const names = [
        r.title,
        ...((r.data.aliases as string[] | undefined) ?? []),
        ...Object.values((r.data.external_ids as JsonObject | undefined) ?? {}),
      ].join("\n");
      // Never index whole originals or parser bodies as if translated working prose.
      const working = [
        r.title,
        r.body ?? "",
        r.data.statement,
        r.data.definition,
        r.data.disambiguation,
        r.data.purpose,
        r.data.objective,
        r.data.current_state,
        r.data.next_action,
        r.data.applicability,
        r.data.instructions,
        r.data.input_contract,
        r.data.expected_output,
        r.data.limitations,
        r.data.summary,
        r.data.context_requirements
          ? canonical(r.data.context_requirements)
          : null,
        r.data.tool_requirements ? canonical(r.data.tool_requirements) : null,
        r.data.conditions ? canonical(r.data.conditions) : "",
      ]
        .filter((v) => typeof v === "string")
        .join("\n");
      storage.run(
        "INSERT INTO memory_text(rowid,text) VALUES(?,?)",
        doc.docid,
        working,
      );
      storage.run(
        "INSERT INTO memory_names(rowid,names) VALUES(?,?)",
        doc.docid,
        names,
      );
    }
  }
  storage.exec("DELETE FROM memberships; DELETE FROM concept_parents;");
  for (const r of byId.values()) {
    if (r.storage === "tombstone") continue;
    for (const c of r.concept_ids)
      storage.run("INSERT OR IGNORE INTO memberships VALUES(?,?)", r.id, c.id);
    if (r.kind === "concept")
      for (const p of r.data.broader_ids as { id: string }[])
        storage.run(
          "INSERT OR IGNORE INTO concept_parents VALUES(?,?)",
          r.id,
          p.id,
        );
  }
  storage.run(
    "UPDATE memory_meta SET seq=(SELECT coalesce(max(seq),0) FROM changes),build=build+?",
    rebuild ? 1 : 0,
  );
}

const kinds = z.enum([
  "activity",
  "work",
  "knowledge",
  "evidence",
  "concept",
  "entity",
  "method",
  "run",
]);
export const SearchSchema = z.strictObject({
  query: z.string().min(1).max(512).optional(),
  match: z.enum(["all", "any", "phrase"]).optional(),
  channel: z.enum(["working", "names", "both"]).optional(),
  exact_name: z.boolean().optional(),
  kinds: z.array(kinds).min(1).max(8).optional(),
  concept_ids: z.array(z.string().min(1).max(160)).min(1).max(10).optional(),
  descendants: z.boolean().optional(),
  subject_id: z.string().min(1).max(160).optional(),
  object_id: z.string().min(1).max(160).optional(),
  predicate: KnowledgeData.shape.predicate,
  activity_id: z.string().min(1).max(160).optional(),
  states: z
    .array(
      z.enum([
        "current",
        "tentative",
        "contested",
        "superseded",
        "retracted",
        "active",
        "retired",
        "paused",
        "closed",
        "draft",
        "waiting",
        "blocked",
        "done",
        "cancelled",
        "candidate",
        "deprecated",
        "running",
        "completed",
        "failed",
        "interrupted",
      ]),
    )
    .min(1)
    .max(15)
    .optional(),
  storage: z.enum(["live", "archive", "tombstone"]).optional(),
  history: z.boolean().optional(),
  valid_at: z.iso.datetime({ offset: true }).optional(),
  observed_after: z.iso.datetime({ offset: true }).optional(),
  source_kind: z
    .enum([
      "observed_input",
      "imported_file",
      "extracted_text",
      "generated_artifact",
      "external_reply",
      "direct_statement",
      "quotation",
      "agent_reply",
      "tool_result",
    ])
    .optional(),
  limit: z.number().int().min(1).max(50).optional(),
  cursor: z.string().max(4096).optional(),
});
export type SearchRequest = z.infer<typeof SearchSchema>;
export function literalFTS(query: string, mode: "all" | "any" | "phrase") {
  const terms = query
    .trim()
    .split(/\s+/u)
    .filter((t) => /[\p{L}\p{N}]/u.test(t));
  requireThat(
    terms.length > 0 && terms.length <= 32,
    "VALIDATION_ERROR",
    "Use 1..32 literal terms within 512 characters; tokenless queries are not scans.",
  );
  const quote = (s: string) => '"' + s.replaceAll('"', '""') + '"';
  return mode === "phrase"
    ? quote(query.trim())
    : terms.map(quote).join(mode === "any" ? " OR " : " AND ");
}

export interface CursorState {
  query: string;
  generation: string;
  access: string;
  last: number;
}
export class Memory {
  constructor(
    private db: StoragePort,
    private ctx: CallContext,
    private cursors: Map<string, CursorState>,
  ) {}
  visibleSequence(through = Number.MAX_SAFE_INTEGER) {
    return this.db.get<{ n: number }>(
      `SELECT count(*) AS n FROM changes t WHERE t.seq<=? AND ${this.technicalSQL("t")}`,
      through,
    )!.n;
  }
  sanitizeTechnical<T>(value: T): T {
    if (this.restricted) return value;
    const walk = (v: unknown): unknown => {
      if (Array.isArray(v)) return v.map(walk);
      if (v && typeof v === "object")
        return Object.fromEntries(
          Object.entries(v).map(([k, item]) => [
            k,
            ["snapshot_seq", "change_seq"].includes(k) &&
            typeof item === "number"
              ? this.visibleSequence(item)
              : walk(item),
          ]),
        );
      return v;
    };
    return walk(value) as T;
  }
  get restricted() {
    return this.ctx.scopes?.includes("restricted:read") ? 1 : 0;
  }
  get accessKey() {
    return hash([
      this.ctx.workspace_id,
      this.ctx.epoch,
      this.ctx.principal,
      [...(this.ctx.scopes ?? [])].sort(),
    ]);
  }
  allowed(id: string, revision?: number) {
    const r = this.db.get<{ restricted: number }>(
      "SELECT d.restricted FROM memory_docs d JOIN addressed_current r ON r.id=d.id WHERE d.id=? AND d.revision=coalesce(?,json_extract(r.json,'$.revision'))",
      id,
      revision ?? null,
    );
    return !!r && (!r.restricted || !!this.restricted);
  }
  visibleSQL(alias: string) {
    return `EXISTS(SELECT 1 FROM memory_docs access JOIN records ar ON ar.id=access.id WHERE access.id=${alias}.id AND access.revision=json_extract(ar.json,'$.revision') AND (access.restricted=0 OR ${this.restricted}=1))`;
  }
  technicalSQL(alias: string) {
    if (this.restricted) return "1";
    const denied = `(secret.key='visibility' AND secret.atom='restricted') OR secret.atom IN (SELECT d.id FROM memory_docs d WHERE d.restricted=1) OR (secret.path LIKE '%.changed' AND secret.key IN (SELECT d.id FROM memory_docs d WHERE d.restricted=1))`;
    // Legacy lifecycle Changes can have an empty changed map. Their existing
    // transaction intent still carries exact targets; retain that classification
    // without rewriting historical rows or exposing a protected-only count.
    return `NOT EXISTS(SELECT 1 FROM json_tree(${alias}.json) secret WHERE ${denied}) AND NOT EXISTS(SELECT 1 FROM intents linked,json_tree(linked.json) secret WHERE linked.request_id=json_extract(${alias}.json,'$.transaction_id') AND (${denied}))`;
  }
  technical(value: unknown) {
    if (this.restricted) return true;
    const transaction =
        value && typeof value === "object"
          ? (value as JsonObject).transaction_id
          : undefined,
      linked =
        typeof transaction === "string"
          ? this.db.get<{ json: string }>(
              "SELECT json FROM intents WHERE request_id=?",
              transaction,
            )
          : undefined;
    return [value, ...(linked ? [JSON.parse(linked.json)] : [])].every(
      (item) => {
        if (/"visibility"\s*:\s*"restricted"/.test(JSON.stringify(item)))
          return false;
        return addressedIds(item).every(
          (id) =>
            !this.db.get("SELECT id FROM addressed_current WHERE id=?", id) ||
            !this.db.get(
              "SELECT id FROM memory_docs WHERE id=? AND restricted=1 LIMIT 1",
              id,
            ),
        );
      },
    );
  }
  generation() {
    const visible = this.db.all<{ id: string; revision: number }>(
      "SELECT d.id,d.revision FROM memory_docs d JOIN addressed_current r ON r.id=d.id AND json_extract(r.json,'$.revision')=d.revision WHERE (d.restricted=0 OR ?=1) ORDER BY d.id",
      this.restricted,
    );
    const technical = ["intents", "claims", "handoffs", "relations"].map(
      (table) =>
        this.db
          .all<{
            json: string;
          }>(
            `SELECT t.json FROM ${table} t WHERE ${this.technicalSQL("t")} ORDER BY t.rowid`,
          )
          .map((r) => hash(r.json)),
    );
    return hash([
      this.accessKey,
      visible,
      technical,
      this.db.get("SELECT build FROM memory_meta"),
    ]);
  }
  barrier() {
    try {
      requireThat(
        this.db.get<{ seq: number }>("SELECT seq FROM memory_meta")?.seq ===
          this.db.get<{ seq: number }>(
            "SELECT coalesce(max(seq),0) AS seq FROM changes",
          )?.seq,
        "INDEX_UNAVAILABLE",
        "Search generation is unchecked; navigate/read directly or rebuild the index.",
      );
      this.db.get("SELECT rowid FROM memory_text LIMIT 1");
      this.db.get("SELECT rowid FROM memory_names LIMIT 1");
    } catch {
      throw new CoreError(
        "INDEX_UNAVAILABLE",
        "Search index unavailable or behind committed state; direct navigation/read remains available.",
      );
    }
  }
  cursor(cursor: string | undefined, query: unknown, generation: string) {
    if (!cursor) return 0;
    try {
      const c = this.cursors.get(cursor);
      requireThat(
        c &&
          c.query === hash(query) &&
          c.generation === generation &&
          c.access === this.accessKey &&
          Number.isSafeInteger(c.last) &&
          c.last >= 0,
        "CURSOR_INVALIDATED",
        "Restart the bounded query; query, access or generation changed.",
      );
      return c.last as number;
    } catch {
      throw new CoreError(
        "CURSOR_INVALIDATED",
        "Restart the bounded query; continuation is invalid.",
      );
    }
  }
  page<T>(
    rows: T[],
    limit: number,
    query: unknown,
    generation: string,
    key: (r: T) => number,
  ) {
    const cards = rows.slice(0, limit),
      has_more = rows.length > limit;
    const payload = {
      query: hash(query),
      generation,
      access: this.accessKey,
      last: has_more ? key(cards.at(-1)!) : 0,
    };
    let next_cursor: string | null = null;
    if (has_more) {
      next_cursor = "cursor-" + randomUUID();
      this.cursors.set(next_cursor, payload);
      if (this.cursors.size > 256)
        this.cursors.delete(this.cursors.keys().next().value!);
    }
    return {
      cards,
      applied_filters: query,
      generation,
      has_more,
      next_cursor,
      warnings: [
        "Empty or incomplete results do not establish absence. Read selected records and conditions before use.",
      ],
    };
  }
  card(r: AddressedRow, reasons: string[] = []) {
    return {
      id: r.id,
      kind: r.kind,
      title: r.title,
      revision: r.revision,
      storage: r.storage,
      state:
        r.data.state ??
        r.data.status ??
        r.data.execution ??
        r.data.problem_state ??
        null,
      ...(r.kind === "method"
        ? { content_version: r.data.content_version }
        : {}),
      // Cards route discovery; a short statement would lose qualifications and contaminate retrieval tests.
      description: null,
      selector: { record_id: r.id },
      must_read: [{ id: r.id, revision: r.revision }],
      match_reasons: reasons,
    };
  }
  browse(
    view: string,
    recordId?: string,
    limit = 20,
    cursor?: string,
    mode?: string,
  ) {
    requireThat(
      Number.isInteger(limit) && limit >= 1 && limit <= 50,
      "VALIDATION_ERROR",
      "Page limit must be 1..50.",
    );
    if (recordId)
      requireThat(
        this.allowed(recordId),
        "REFERENCE_NOT_FOUND",
        "Requested record/version is unavailable.",
      );
    const generation = this.generation(),
      filters = {
        view,
        record_id: recordId ?? null,
        limit,
        mode: mode ?? null,
      },
      last = this.cursor(cursor, filters, generation);
    const technical: Record<string, { table: string; key: string }> = {
      operations: { table: "intents", key: "rowid" },
      changes: { table: "changes", key: "seq" },
      handoffs: { table: "handoffs", key: "rowid" },
      claims: { table: "claims", key: "rowid" },
      relations: { table: "relations", key: "rowid" },
      evaluations: { table: "experience_rows", key: "rowid" },
      signals: { table: "experience_rows", key: "rowid" },
      signal_reviews: { table: "experience_rows", key: "rowid" },
      invocations: { table: "experience_rows", key: "rowid" },
      environments: { table: "experience_rows", key: "rowid" },
      history: { table: "addressed_versions", key: "revision" },
    };
    if (technical[view] && mode !== "current_claims") {
      const { table, key } = technical[view];
      requireThat(
        view !== "history" || recordId,
        "VALIDATION_ERROR",
        "History needs a record id.",
      );
      const supportKinds: Record<string, string> = {
        evaluations: "evaluation",
        signals: "signal",
        signal_reviews: "signal_review",
        invocations: "invocation",
        environments: "environment",
      };
      const kindFilter = supportKinds[view]
        ? ` AND t.kind='${supportKinds[view]}'`
        : "";
      const rows = this.db.all<{ key: number; json: string }>(
        `SELECT t.${key} AS key,t.json FROM ${table} t WHERE t.${key}>? ${kindFilter} AND ${this.technicalSQL("t")} AND (? IS NULL OR ${view === "history" ? "t.id=?" : "EXISTS(SELECT 1 FROM json_tree(t.json) WHERE atom=?)"}) ORDER BY t.${key} LIMIT ?`,
        last,
        recordId ?? null,
        recordId ?? null,
        limit + 1,
      );
      const page = this.page(rows, limit, filters, generation, (r) => r.key);
      return {
        ...page,
        cards: page.cards.map((r) => {
          const value = this.sanitizeTechnical(
            JSON.parse(r.json),
          ) as JsonObject;
          if (supportKinds[view] || view === "history")
            return {
              ...this.card(value as unknown as AddressedRow),
              ...(supportKinds[view]
                ? {
                    assessment: (value.data as JsonObject)?.assessment ?? null,
                    basis: (value.data as JsonObject)?.basis ?? null,
                  }
                : {}),
              untrusted_data: true,
            };
          if (view === "operations") {
            if (value.payload_not_retained)
              return {
                request_id: value.request_id,
                kind: value.kind,
                status: value.status,
                operation_digest: value.operation_digest,
                payload_not_retained: true,
                receipt: value.receipt ?? null,
                must_read_operation: value.request_id,
              };
            const { payload, ...header } = value;
            if (value.kind === "managed_file") {
              const p = payload as JsonObject;
              return {
                request_id: value.request_id,
                kind: value.kind,
                status: value.status,
                target: p.target,
                action: p.tool,
                work_ref: p.work_ref,
                step_id: p.step_id,
                receipt_id:
                  (value.receipt as JsonObject | null)?.receipt_id ?? null,
                observation_count: (value.observations as unknown[]).length,
                payload_omitted: true,
                must_read_operation: value.request_id,
              };
            }
            if (value.kind === "preview") {
              const p = payload as JsonObject;
              return {
                request_id: value.request_id,
                kind: value.kind,
                status: value.status,
                action: p.action,
                consequence: String(p.consequence).slice(0, 400),
                explanation_truncated: String(p.consequence).length > 400,
                expires_at: p.expires_at,
                payload_omitted: true,
                must_read_operation: value.request_id,
              };
            }
            return {
              ...header,
              payload_omitted: !!payload,
              must_read_operation: value.request_id,
            };
          }
          return value;
        }),
      };
    }
    const where = ["r.rowid>?", this.visibleSQL("r")],
      params: (string | number | null)[] = [last];
    const kind: Record<string, string> = {
      activities: "activity",
      work: "work",
      knowledge: "knowledge",
      materials: "evidence",
      topics: "concept",
      concepts: "concept",
      entities: "entity",
      methods: "method",
      runs: "run",
    };
    if (mode === "current_claims") {
      requireThat(
        recordId,
        "VALIDATION_ERROR",
        "current_claims needs an addressed record.",
      );
      where.push(
        "r.kind='knowledge' AND json_extract(r.json,'$.data.state') IN ('current','tentative','contested') AND (json_extract(r.json,'$.data.subject_ref.id') IN (WITH RECURSIVE aliases(id) AS (SELECT ? UNION SELECT a.id FROM records a JOIN aliases b ON json_extract(a.json,'$.data.redirect_to.id')=b.id) SELECT id FROM aliases) OR json_extract(r.json,'$.data.object_ref.id') IN (WITH RECURSIVE aliases(id) AS (SELECT ? UNION SELECT a.id FROM records a JOIN aliases b ON json_extract(a.json,'$.data.redirect_to.id')=b.id) SELECT id FROM aliases))",
      );
      params.push(recordId, recordId);
    } else if (
      recordId &&
      ["topics", "concepts", "entities", "records"].includes(view)
    ) {
      const selectedRow = this.db.get<{ json: string }>(
        "SELECT json FROM records WHERE id=?",
        recordId,
      );
      requireThat(
        selectedRow,
        "VALIDATION_ERROR",
        "Supporting rows use addressed read or their registered experience view, not primary-record neighborhood expansion.",
      );
      const selected = JSON.parse(selectedRow.json) as RecordRow;
      if (selected.kind === "concept") {
        where.push(
          "(EXISTS(SELECT 1 FROM concept_parents p WHERE p.parent_id IN (WITH RECURSIVE aliases(id) AS (SELECT ? UNION SELECT a.id FROM records a JOIN aliases b ON json_extract(a.json,'$.data.redirect_to.id')=b.id) SELECT id FROM aliases) AND p.child_id=r.id) OR EXISTS(SELECT 1 FROM memberships m WHERE m.concept_id IN (WITH RECURSIVE aliases(id) AS (SELECT ? UNION SELECT a.id FROM records a JOIN aliases b ON json_extract(a.json,'$.data.redirect_to.id')=b.id) SELECT id FROM aliases) AND m.record_id=r.id))",
        );
        params.push(recordId, recordId);
      } else {
        where.push(
          "(EXISTS(SELECT 1 FROM memberships a JOIN memberships b ON a.concept_id=b.concept_id WHERE a.record_id=? AND b.record_id=r.id) AND r.id<>?)",
        );
        params.push(recordId, recordId);
      }
    } else if (view === "resources")
      where.push(
        "r.kind='entity' AND json_extract(r.json,'$.data.entity_kind') IN ('resource','device','item','place')",
      );
    else if (view === "people")
      where.push(
        "r.kind='entity' AND json_extract(r.json,'$.data.entity_kind')='person'",
      );
    else if (view === "unfiled")
      where.push(
        "r.kind IN ('knowledge','entity','evidence') AND NOT EXISTS(SELECT 1 FROM memberships m WHERE m.record_id=r.id)",
      );
    else if (kind[view]) {
      where.push("r.kind=?");
      params.push(kind[view]);
      if (recordId) {
        where.push(
          "(r.activity_id=? OR json_extract(r.json,'$.data.parent_work_id.id')=?)",
        );
        params.push(recordId, recordId);
      }
      if (["topics", "concepts"].includes(view) && !recordId)
        where.push(
          "NOT EXISTS(SELECT 1 FROM concept_parents p JOIN records pr ON pr.id=p.parent_id WHERE p.child_id=r.id AND " +
            this.visibleSQL("pr") +
            ")",
        );
    } else throw new CoreError("VALIDATION_ERROR", "Unsupported catalog view.");
    const rows = this.db.all<{ key: number; json: string }>(
      `SELECT r.rowid AS key,r.json FROM records r WHERE ${where.join(" AND ")} ORDER BY r.rowid LIMIT ?`,
      ...params,
      limit + 1,
    );
    const page = this.page(rows, limit, filters, generation, (r) => r.key);
    return {
      ...page,
      cards: page.cards.map((r) => this.card(JSON.parse(r.json))),
    };
  }
  trace(
    operation: string,
    input: unknown,
    result: unknown,
    started: number,
    error?: unknown,
  ) {
    if (this.db.readonly) return;
    const data = result as {
      id?: string;
      revision?: number;
      ref?: { id: string; revision: number };
      cards?: { id?: string; revision?: number }[];
      generation?: string;
      has_more?: boolean;
      data?: { has_more?: boolean; excerpt_truncated?: boolean };
    };
    const serialized = JSON.stringify(input),
      bounded =
        Buffer.byteLength(serialized) <= 2048
          ? input
          : {
              input_sha256: hash(input),
              input_bytes: Buffer.byteLength(serialized),
              truncated: true,
            };
    const refs = data?.id
      ? [{ id: data.id, revision: data.revision }]
      : data?.ref
        ? [data.ref]
        : (data?.cards
            ?.filter((c) => c.id)
            .map((c) => ({ id: c.id, revision: c.revision })) ?? []);
    const row = {
      operation,
      input: bounded,
      refs,
      generation: data?.generation ?? this.generation(),
      bytes: Buffer.byteLength(JSON.stringify(result ?? null)),
      has_more:
        data?.has_more ??
        data?.data?.has_more ??
        data?.data?.excerpt_truncated ??
        false,
      elapsed_ms: performance.now() - started,
      error:
        error instanceof CoreError
          ? error.code
          : error
            ? "STORE_UNAVAILABLE"
            : null,
    };
    this.db.run(
      "INSERT INTO retrieval_trace(access_key,json) VALUES(?,?)",
      this.accessKey,
      JSON.stringify(row),
    );
    this.db.exec(
      "DELETE FROM retrieval_trace WHERE seq <= (SELECT coalesce(max(seq),0)-512 FROM retrieval_trace)",
    );
  }
  search(input: unknown) {
    const p = SearchSchema.parse(input),
      { cursor, ...filters } = p;
    requireThat(
      p.query ||
        p.kinds ||
        p.concept_ids ||
        p.subject_id ||
        p.object_id ||
        p.predicate ||
        p.activity_id ||
        p.states ||
        p.valid_at ||
        p.observed_after ||
        p.source_kind,
      "VALIDATION_ERROR",
      "Search requires text or a meaningful typed filter.",
    );
    requireThat(
      !p.query || p.match,
      "VALIDATION_ERROR",
      "Text search requires an explicit all/any/phrase match mode.",
    );
    const expression = p.query ? literalFTS(p.query, p.match!) : null;
    requireThat(
      !p.exact_name || (p.query && p.channel === "names"),
      "VALIDATION_ERROR",
      "Exact authentic name matching requires query and names channel.",
    );
    for (const id of [
      ...(p.concept_ids ?? []),
      p.subject_id,
      p.object_id,
      p.activity_id,
    ].filter(Boolean) as string[])
      requireThat(
        this.allowed(id),
        "REFERENCE_NOT_FOUND",
        "Requested record/version is unavailable.",
      );
    this.barrier();
    const generation = this.generation(),
      last = this.cursor(cursor, filters, generation),
      limit = p.limit ?? 20;
    const where = [
        "d.docid>?",
        "(d.restricted=0 OR ?=1)",
        p.history ? "1" : "d.revision=json_extract(r.json,'$.revision')",
      ],
      params: (string | number | null)[] = [last, this.restricted];
    let hits = "";
    if (expression) {
      const queries: string[] = [];
      if (p.channel !== "names")
        queries.push(
          "SELECT rowid AS docid,'English working text' AS reason FROM memory_text WHERE memory_text MATCH ?",
        );
      if (p.channel !== "working")
        queries.push(
          "SELECT rowid AS docid,'Authentic name/identifier/alias (unicode61 literal tokens)' AS reason FROM memory_names WHERE memory_names MATCH ?",
        );
      hits = `WITH hits AS (${queries.join(" UNION ALL ")}) `;
      params.unshift(...queries.map(() => expression));
      where.push("d.docid IN (SELECT docid FROM hits)");
    }
    const j = "v.json";
    if (p.exact_name) {
      where.push(
        `(json_extract(${j},'$.title')=? OR EXISTS(SELECT 1 FROM json_each(${j},'$.data.aliases') WHERE value=?) OR EXISTS(SELECT 1 FROM json_each(${j},'$.data.external_ids') WHERE value=?))`,
      );
      params.push(p.query!, p.query!, p.query!);
    }
    const list = (path: string, values: string[]) => {
      where.push(`${path} IN (${values.map(() => "?").join(",")})`);
      params.push(...values);
    };
    if (p.kinds) list("r.kind", p.kinds);
    if (p.states)
      list(
        `coalesce(json_extract(${j},'$.data.state'),json_extract(${j},'$.data.status'),json_extract(${j},'$.data.execution'))`,
        p.states,
      );
    for (const [field, value] of [
      ["subject_ref.id", p.subject_id],
      ["object_ref.id", p.object_id],
      ["predicate", p.predicate],
    ] as const)
      if (value) {
        where.push(`json_extract(${j},'$.data.${field}')=?`);
        params.push(value);
      }
    if (p.activity_id) {
      where.push(
        `(json_extract(${j},'$.origin_activity_id.id')=? OR json_extract(${j},'$.data.activity_id.id')=?)`,
      );
      params.push(p.activity_id, p.activity_id);
    }
    if (p.source_kind) {
      where.push(
        `(json_extract(${j},'$.data.source_kind')=? OR EXISTS(SELECT 1 FROM json_each(${j},'$.data.evidence_refs') e JOIN records source ON source.id=json_extract(e.value,'$.id') JOIN memory_docs a ON a.id=source.id AND a.revision=json_extract(source.json,'$.revision') WHERE (a.restricted=0 OR ?=1) AND json_extract(source.json,'$.data.source_kind')=?))`,
      );
      params.push(p.source_kind, this.restricted, p.source_kind);
    }
    if (p.valid_at) {
      where.push(
        `(json_extract(${j},'$.data.valid_from') IS NULL OR julianday(json_extract(${j},'$.data.valid_from'))<=julianday(?)) AND (json_extract(${j},'$.data.valid_to') IS NULL OR julianday(json_extract(${j},'$.data.valid_to'))>julianday(?))`,
      );
      params.push(p.valid_at, p.valid_at);
    }
    if (p.observed_after) {
      where.push(
        `julianday(json_extract(${j},'$.data.observed_at'))>=julianday(?)`,
      );
      params.push(p.observed_after);
    }
    if (p.concept_ids) {
      // Historical membership uses that revision's addressed fields. Descendant expansion never crosses inaccessible Concepts.
      const expanded = new Set(p.concept_ids);
      if (p.descendants)
        for (const id of p.concept_ids)
          for (const c of this.db.all<{ id: string }>(
            "WITH RECURSIVE c(id) AS (SELECT ? UNION SELECT p.child_id FROM concept_parents p JOIN c ON p.parent_id=c.id JOIN records r ON r.id=p.child_id JOIN memory_docs d ON d.id=r.id AND d.revision=json_extract(r.json,'$.revision') WHERE (d.restricted=0 OR ?=1)) SELECT id FROM c",
            id,
            this.restricted,
          ))
            expanded.add(c.id);
      const ids = [...expanded];
      where.push(
        `EXISTS(SELECT 1 FROM json_each(${j},'$.concept_ids') m WHERE json_extract(m.value,'$.id') IN (${ids.map(() => "?").join(",")}))`,
      );
      params.push(...ids);
    }
    try {
      const rows = this.db.all<{
        docid: number;
        json: string;
        reasons: string | null;
      }>(
        `${hits} SELECT d.docid,v.json,${expression ? "(SELECT group_concat(DISTINCT reason) FROM hits WHERE hits.docid=d.docid)" : "NULL"} AS reasons FROM memory_docs d JOIN records r ON r.id=d.id JOIN revisions v ON v.id=d.id AND v.revision=d.revision WHERE ${where.join(" AND ")} ORDER BY d.docid LIMIT ?`,
        ...params,
        limit + 1,
      );
      const page = this.page(rows, limit, filters, generation, (r) => r.docid);
      return {
        ...page,
        cards: page.cards.map((r) =>
          this.card(
            JSON.parse(r.json),
            r.reasons?.split(",") ?? ["Typed filters"],
          ),
        ),
        order: "stable document id",
        validity_note: p.valid_at
          ? "Unknown validity remains unknown; residual conditions require reading."
          : "No applicability time inferred from write time.",
      };
    } catch {
      throw new CoreError(
        "INDEX_UNAVAILABLE",
        "Search could not check the current index; no absence conclusion is supported.",
      );
    }
  }
}

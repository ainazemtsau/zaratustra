import { createHash, randomUUID } from "node:crypto";
import { canonical, MethodData, RunData, requireThat } from "./contracts.ts";
import type {
  AddressedRow,
  CallContext,
  CommitRequest,
  JsonObject,
  RecordRow,
  StoragePort,
  SupportingRow,
} from "./contracts.ts";

export const ExperienceSchemaSQL = `
 CREATE TABLE experience_rows(id TEXT PRIMARY KEY,kind TEXT NOT NULL CHECK(kind IN ('evaluation','signal','signal_review','invocation','environment')),owner_id TEXT,json TEXT NOT NULL);
 CREATE TABLE experience_versions(id TEXT NOT NULL,revision INTEGER NOT NULL,json TEXT NOT NULL,PRIMARY KEY(id,revision));
 CREATE INDEX experience_kind_owner ON experience_rows(kind,owner_id);
 CREATE UNIQUE INDEX invocation_key ON experience_rows(owner_id,json_extract(json,'$.data.invocation_key')) WHERE kind='invocation';
 CREATE UNIQUE INDEX run_episode_key ON records(json_extract(json,'$.data.episode_key')) WHERE kind='run';
 CREATE INDEX method_content_version ON revisions(id,json_extract(json,'$.data.content_version'),revision);
 CREATE VIEW addressed_current AS SELECT id,kind,json FROM records UNION ALL SELECT id,kind,json FROM experience_rows;
 CREATE VIEW addressed_versions AS SELECT id,revision,json FROM revisions UNION ALL SELECT id,revision,json FROM experience_versions;`;

type Get = (ref: unknown, kind?: string) => RecordRow;
const hash = (value: unknown) =>
  createHash("sha256").update(canonical(value)).digest("hex");
const object = (ref: unknown) =>
  ref as { id: string; revision?: number; content_version?: number };
export function exactRef(r: AddressedRow) {
  return {
    id: r.id,
    revision: r.revision,
    ...(r.kind === "method"
      ? { content_version: r.data.content_version as number }
      : {}),
  };
}
export function methodUpdate(
  old: RecordRow,
  data: unknown,
  body: string | null = old.body,
) {
  const prior = MethodData.parse(old.data),
    next = MethodData.parse(data);
  requireThat(
    next.content_version === prior.content_version,
    "REVISION_CONFLICT",
    "Core assigns content_version; supply the current version.",
  );
  const behavior = (m: typeof prior) => {
    const { state, content_version, ...rest } = m;
    void state;
    void content_version;
    return rest;
  };
  next.content_version +=
    canonical([behavior(prior), old.body]) === canonical([behavior(next), body])
      ? 0
      : 1;
  return next;
}

/** A finite selected DAG, not a method executor. Exact declared refs cannot be overridden. */
export function methodClosure(root: unknown, get: Get, selected?: unknown[]) {
  const result = new Map<string, RecordRow>();
  const selectedRows = selected?.map((ref) => {
    const p = object(ref);
    requireThat(
      p.revision !== undefined || p.content_version !== undefined,
      "VALIDATION_ERROR",
      "Selected versions must be exact.",
    );
    return get(ref, "method");
  });
  const pick = (ref: unknown) => {
    const p = object(ref);
    if (
      !selectedRows ||
      p.revision !== undefined ||
      p.content_version !== undefined
    )
      return get(ref, "method");
    const candidates = selectedRows.filter((r) => r.id === p.id);
    requireThat(
      candidates.length === 1,
      "VALIDATION_ERROR",
      "A current dependency needs one unambiguous selected exact version.",
    );
    return candidates[0];
  };
  const visit = (r: RecordRow, path: Set<string>) => {
    requireThat(
      !path.has(r.id),
      "GRAPH_CYCLE",
      "Method dependencies contain a cycle.",
    );
    const key = r.id + ":" + r.revision;
    if (result.has(key)) return;
    requireThat(
      result.size < 256,
      "LIMIT_EXCEEDED",
      "Method closure exceeds 256 versions; narrow the composition before applying.",
    );
    result.set(key, r);
    const next = new Set(path).add(r.id);
    for (const ref of MethodData.parse(r.data).dependencies)
      visit(pick(ref), next);
  };
  visit(get(root, "method"), new Set());
  if (selectedRows) {
    requireThat(
      new Set(selectedRows.map((r) => r.id + ":" + r.revision)).size ===
        selectedRows.length &&
        canonical([...result.keys()].sort()) ===
          canonical(selectedRows.map((r) => r.id + ":" + r.revision).sort()),
      "VALIDATION_ERROR",
      "Selected versions must be the entire closure, with no missing, duplicate or extra member.",
    );
  }
  return [...result.values()];
}
export function validateMethods(rows: RecordRow[], get: Get) {
  for (const r of rows.filter((r) => r.kind === "method")) {
    const m = MethodData.parse(r.data);
    for (const ref of m.derived_from) get(ref, "method");
    for (const requirement of m.context_requirements)
      for (const ref of requirement.refs) get(ref);
    methodClosure({ id: r.id }, get);
  }
}

/** One participant in the existing Core transaction; it never commits on its own. */
export class ExperienceTransaction {
  readonly changed = new Map<string, SupportingRow>();
  readonly before: Record<string, number | null> = {};
  constructor(
    private db: StoragePort,
    private ctx: CallContext,
    private request: CommitRequest,
    private created: Record<string, string>,
    private primary: Map<string, RecordRow>,
    private get: Get,
    private stage: (r: RecordRow, data: JsonObject) => void,
    private now: string,
  ) {}
  private support(ref: unknown, kind?: SupportingRow["kind"]): SupportingRow {
    const p = object(ref),
      staged = this.changed.get(p.id);
    const row =
      staged && (p.revision === undefined || staged.revision === p.revision)
        ? staged
        : this.db.get<{ json: string }>(
            p.revision === undefined
              ? "SELECT json FROM experience_rows WHERE id=?"
              : "SELECT json FROM experience_versions WHERE id=? AND revision=?",
            p.id,
            ...(p.revision === undefined ? [] : [p.revision]),
          );
    requireThat(
      row,
      "REFERENCE_NOT_FOUND",
      "Requested supporting record/version is unavailable.",
    );
    const r = "json" in row ? (JSON.parse(row.json) as SupportingRow) : row;
    requireThat(
      !kind || r.kind === kind,
      "REFERENCE_TYPE_MISMATCH",
      "Supporting reference has the wrong kind.",
    );
    requireThat(
      p.content_version === undefined,
      "REFERENCE_TYPE_MISMATCH",
      "Only Method refs have content_version.",
    );
    return r;
  }
  address(ref: unknown, kind?: string): AddressedRow {
    const p = object(ref);
    if (
      this.changed.has(p.id) ||
      this.db.get("SELECT id FROM experience_rows WHERE id=?", p.id)
    ) {
      const r = this.support(ref);
      requireThat(
        !kind || r.kind === kind,
        "REFERENCE_TYPE_MISMATCH",
        "Reference has the wrong kind.",
      );
      return r;
    }
    return this.get(ref, kind);
  }
  private pin(ref: unknown, kind?: string) {
    return exactRef(this.address(ref, kind));
  }
  private evidence(ref: unknown) {
    const e = this.get(ref, "evidence");
    requireThat(
      e.data.availability === "retained" &&
        (typeof e.data.retained_excerpt === "string" ||
          typeof e.data.blob_ref === "string"),
      "SOURCE_MISSING",
      "Minimal original grounds must remain retained.",
    );
    if (typeof e.data.blob_ref === "string" && !e.data.extraction)
      this.db.readMaterial(e.data.blob_ref);
    return exactRef(e);
  }
  private guarded(ref: unknown): AddressedRow {
    const p = object(ref);
    const r = this.address({ id: p.id });
    const original = this.changed.has(r.id)
      ? this.before[r.id]
      : this.primary.has(r.id)
        ? this.db.get<{ json: string }>(
            "SELECT json FROM records WHERE id=?",
            r.id,
          )
        : undefined;
    const revision =
      typeof original === "number"
        ? original
        : original && typeof original === "object"
          ? JSON.parse(original.json).revision
          : r.revision;
    requireThat(
      this.request.guards.some(
        (g) => g.ref.id === r.id && g.expected_revision === revision,
      ),
      "REVISION_CONFLICT",
      "Changed experience requires the exact current revision guard.",
    );
    return r;
  }
  private put(
    id: string,
    kind: SupportingRow["kind"],
    data: JsonObject,
    title: string,
    visibility: "workspace" | "restricted" = "workspace",
    owner_id: string | null = null,
  ) {
    const prior =
      this.changed.get(id) ??
      this.db.get<{ json: string }>(
        "SELECT json FROM experience_rows WHERE id=?",
        id,
      );
    const old = prior
      ? "json" in prior
        ? (JSON.parse(prior.json) as SupportingRow)
        : prior
      : undefined;
    if (!(id in this.before)) this.before[id] = old?.revision ?? null;
    const row: SupportingRow = {
      id,
      kind,
      title,
      body: null,
      revision: (this.before[id] ?? 0) + 1,
      created_at: old?.created_at ?? this.now,
      updated_at: this.now,
      storage: "live",
      visibility: old?.visibility ?? visibility,
      concept_ids: [],
      origin_activity_id: null,
      data,
    };
    requireThat(
      Buffer.byteLength(JSON.stringify(row)) <= 64000,
      "VALIDATION_ERROR",
      "Supporting record exceeds its 64,000-byte read bound.",
    );
    this.changed.set(id, row);
    void owner_id;
    return row;
  }
  private run(ref: unknown) {
    const p = object(ref),
      r = this.get({ id: p.id }, "run");
    requireThat(
      r.data.execution === "running",
      "INVALID_TRANSITION",
      "Only a running Run accepts applications/results; late feedback targets the old result directly.",
    );
    requireThat(
      p.revision === undefined || p.revision === r.revision,
      "REVISION_CONFLICT",
      "Run revision changed.",
    );
    return r;
  }
  apply(op: CommitRequest["ops"][number]): boolean {
    if (op.op === "revise_method" || op.op === "set_method_state") {
      if (op.op === "revise_method")
        requireThat(
          !this.primary.has(op.ref.id),
          "VALIDATION_ERROR",
          "Revise a Method once per transaction so every content version is retained.",
        );
      const r = this.guarded(op.ref) as RecordRow;
      requireThat(
        r.kind === "method",
        "REFERENCE_TYPE_MISMATCH",
        "Expected Method.",
      );
      this.stage(
        r,
        op.op === "revise_method"
          ? methodUpdate(r, op.data)
          : { ...r.data, state: op.state },
      );
      return true;
    }
    if (op.op === "start_run") {
      requireThat(
        !this.db.get(
          "SELECT id FROM records WHERE kind='run' AND json_extract(json,'$.data.episode_key')=?",
          op.episode_key,
        ) &&
          ![...this.primary.values()].some(
            (r) => r.kind === "run" && r.data.episode_key === op.episode_key,
          ),
        "IDEMPOTENCY_CONFLICT",
        "Episode key already exists; read and continue its Run instead of creating a duplicate.",
      );
      const prior = op.continuation_of
        ? this.get(op.continuation_of, "run")
        : null;
      const environment = this.ctx.environment ?? {
        package: null,
        bootstrap: null,
        skills: null,
        provider: null,
        model: null,
        settings: null,
      };
      const eid = "environment-" + hash(environment);
      if (
        !this.db.get("SELECT id FROM experience_rows WHERE id=?", eid) &&
        !this.changed.has(eid)
      )
        this.put(
          eid,
          "environment",
          environment,
          "Observed runtime environment",
        );
      const rid = this.created[op.client_ref];
      const data = RunData.parse({
        work_ref: op.work_ref ? this.pin(op.work_ref, "work") : null,
        mode: op.mode,
        episode_key: op.episode_key,
        case_id: prior?.data.case_id ?? "case-" + randomUUID(),
        continuation_of: prior ? exactRef(prior) : null,
        execution: "running",
        started_at: this.now,
        ended_at: null,
        summary: op.summary,
        result_refs: [],
        starting_refs: op.starting_refs.map((ref) => this.pin(ref)),
        environment_ref: { id: eid, revision: 1 },
        local_metrics: [],
      });
      const row: RecordRow = {
        id: rid,
        kind: "run",
        title: op.title,
        body: null,
        revision: 1,
        created_at: this.now,
        updated_at: this.now,
        storage: "live",
        visibility: op.visibility,
        concept_ids: [],
        origin_activity_id: null,
        data,
      };
      this.primary.set(rid, row);
      return true;
    }
    if (op.op === "finish_run") {
      const r = this.guarded(op.ref) as RecordRow;
      this.run(op.ref);
      const invocations = [
        ...new Map(
          [
            ...this.db
              .all<{
                json: string;
              }>(
                "SELECT json FROM experience_rows WHERE kind='invocation' AND owner_id=?",
                r.id,
              )
              .map((v) => JSON.parse(v.json) as SupportingRow),
            ...this.changed.values(),
          ]
            .filter(
              (v) =>
                v.kind === "invocation" && object(v.data.run_ref).id === r.id,
            )
            .map((r) => [r.id, r]),
        ).values(),
      ];
      if (op.execution === "completed")
        requireThat(
          invocations.every((v) => v.data.reported_application !== null),
          "INVALID_TRANSITION",
          "A selected invocation still lacks an application/deviation report; report it or interrupt the episode.",
        );
      this.stage(
        r,
        RunData.parse({
          ...r.data,
          execution: op.execution,
          summary: op.summary,
          result_refs: op.result_refs.map((ref) =>
            this.address(ref).kind === "evidence"
              ? this.evidence(ref)
              : this.pin(ref),
          ),
          ended_at: this.now,
          local_metrics: op.local_metrics ?? [],
        }),
      );
      return true;
    }
    if (op.op === "invoke_method") {
      const run = this.run(op.run_ref),
        selected = methodClosure(op.method_ref, this.get, op.selected_versions);
      const root = this.get(op.method_ref, "method");
      requireThat(
        this.get({ id: root.id }, "method").data.state !== "deprecated",
        "INVALID_TRANSITION",
        "Do not select a deprecated Method for a new application.",
      );
      requireThat(
        !this.db.get(
          "SELECT id FROM experience_rows WHERE kind='invocation' AND owner_id=? AND json_extract(json,'$.data.invocation_key')=?",
          run.id,
          op.invocation_key,
        ) &&
          ![...this.changed.values()].some(
            (v) =>
              v.kind === "invocation" &&
              object(v.data.run_ref).id === run.id &&
              v.data.invocation_key === op.invocation_key,
          ),
        "IDEMPOTENCY_CONFLICT",
        "Invocation key already exists for this Run.",
      );
      const parent = op.parent_invocation_ref
        ? this.support(op.parent_invocation_ref, "invocation")
        : null;
      if (parent) {
        requireThat(
          object(parent.data.run_ref).id === run.id,
          "REFERENCE_TYPE_MISMATCH",
          "Dynamic submethod must belong to the same Run.",
        );
        let ancestor: SupportingRow | null = parent;
        const seen = new Set<string>();
        while (ancestor) {
          requireThat(
            !seen.has(ancestor.id),
            "GRAPH_CYCLE",
            "Invocation ancestry contains a cycle.",
          );
          seen.add(ancestor.id);
          const ancestorMethod = object(ancestor.data.method_ref).id;
          requireThat(
            !selected.some((m) => m.id === ancestorMethod),
            "GRAPH_CYCLE",
            "Dynamic submethod selection recurses into an ancestor Method.",
          );
          ancestor = ancestor.data.parent_invocation_ref
            ? this.support(ancestor.data.parent_invocation_ref, "invocation")
            : null;
        }
      }
      const inputs = op.input_refs.map((ref) => {
        const input = this.address(ref);
        requireThat(
          ["evidence", "knowledge", "work", "entity", "activity"].includes(
            input.kind,
          ),
          "REFERENCE_TYPE_MISMATCH",
          "Invocation inputs must address task/source data, not a Method, Run or supporting row.",
        );
        if (input.kind === "evidence") this.evidence(ref);
        return exactRef(input);
      });
      this.put(
        this.created[op.client_ref],
        "invocation",
        {
          run_ref: exactRef(run),
          invocation_key: op.invocation_key,
          method_ref: exactRef(root),
          selected_versions: selected.map(exactRef),
          input_refs: inputs,
          context_refs: op.context_refs.map((ref) => this.pin(ref)),
          bindings: op.bindings,
          parent_invocation_ref: parent ? exactRef(parent) : null,
          selected_at: this.now,
          reported_application: null,
          output_refs: [],
          observation_refs: [],
          reported_at: null,
        },
        "Selected Method application",
      );
      return true;
    }
    if (op.op === "report_application") {
      const r = this.guarded(op.ref);
      requireThat(
        r.kind === "invocation",
        "REFERENCE_TYPE_MISMATCH",
        "Expected invocation.",
      );
      this.run({ id: object(r.data.run_ref).id });
      requireThat(
        r.data.reported_application === null,
        "INVALID_TRANSITION",
        "Application report is immutable; retain corrections as addressed Evaluations/Signals.",
      );
      requireThat(
        !op.reported_application.applied || op.output_refs.length > 0,
        "VALIDATION_ERROR",
        "Reported application needs retained outputs; reading alone is not application.",
      );
      const observations = op.observation_refs.map((ref) => {
        const e = this.get(ref, "evidence");
        requireThat(
          e.data.source_kind === "tool_result" &&
            (e.data.provenance as JsonObject)?.observation,
          "REFERENCE_TYPE_MISMATCH",
          "Technical observations must come from captured tool results, never a model claim.",
        );
        return this.evidence(ref);
      });
      this.put(
        r.id,
        "invocation",
        {
          ...r.data,
          reported_application: op.reported_application,
          output_refs: op.output_refs.map((ref) => this.evidence(ref)),
          observation_refs: observations,
          reported_at: this.now,
        },
        r.title,
      );
      return true;
    }
    if (op.op === "record_evaluation") {
      const target = this.address(op.target_ref),
        target_ref = exactRef(target);
      requireThat(
        object(op.target_ref).revision !== undefined ||
          object(op.target_ref).content_version !== undefined ||
          !this.db.get(
            "SELECT id FROM addressed_current WHERE id=?",
            target.id,
          ),
        "VALIDATION_ERROR",
        "Evaluation target must name an exact result/version.",
      );
      const grounds = op.evidence_refs.map((ref) => this.evidence(ref));
      const sources = grounds.map((ref) => this.get(ref, "evidence"));
      let owner_feedback = false;
      if (op.basis === "user_feedback") {
        owner_feedback = sources.some((e) => {
          const p = e.data.provenance as JsonObject;
          return (
            e.data.source_kind === "direct_statement" &&
            p?.transport === "interactive" &&
            p.owner_channel_eligible === true &&
            p.input_integrity === "trusted_first_untransformed"
          );
        });
        requireThat(
          owner_feedback,
          "SOURCE_MISSING",
          "Owner feedback requires retained direct input from the trusted first/untransformed interactive contract; RPC, quotations and role=user are insufficient.",
        );
      }
      if (["observed_criterion", "test_result"].includes(op.basis))
        requireThat(
          sources.some(
            (e) =>
              e.data.source_kind === "tool_result" &&
              (e.data.provenance as JsonObject)?.observation,
          ),
          "SOURCE_MISSING",
          "Observed/test assessment needs an actual retained tool observation; interpretation remains separate.",
        );
      const old = op.supersedes_evaluation_ref
        ? this.support(op.supersedes_evaluation_ref, "evaluation")
        : null;
      if (old) {
        requireThat(
          canonical(old.data.target_ref) === canonical(target_ref) &&
            old.data.dimension === op.dimension &&
            old.data.dimension_name === op.dimension_name,
          "REFERENCE_TYPE_MISMATCH",
          "Corrected Evaluation must keep its exact target/version and dimension.",
        );
        requireThat(
          !this.db.get(
            "SELECT id FROM experience_rows WHERE kind='evaluation' AND json_extract(json,'$.data.supersedes_evaluation_ref.id')=?",
            old.id,
          ) &&
            ![...this.changed.values()].some(
              (e) =>
                object(e.data.supersedes_evaluation_ref ?? {}).id === old.id,
            ),
          "REVISION_CONFLICT",
          "Supersede the current Evaluation, not an already superseded assessment.",
        );
      }
      this.put(
        this.created[op.client_ref],
        "evaluation",
        {
          target_ref,
          run_ref: op.run_ref ? this.pin(op.run_ref, "run") : null,
          assessment: op.assessment,
          dimension: op.dimension,
          dimension_name: op.dimension_name,
          basis: op.basis,
          evidence_refs: grounds,
          event_time: op.event_time,
          recorded_at: this.now,
          supersedes_evaluation_ref: old ? exactRef(old) : null,
          explanation: op.explanation,
          provenance: {
            owner_feedback,
            claim: owner_feedback
              ? "trusted-desktop-direct-input; semantic attribution remains model judgment"
              : "not-certified-owner-feedback",
          },
        },
        "Addressed assessment",
      );
      return true;
    }
    if (op.op === "open_signal") {
      this.put(
        this.created[op.client_ref],
        "signal",
        {
          kind: op.kind,
          subject_refs: op.subject_refs.map((ref) => this.pin(ref)),
          evidence_refs: op.evidence_refs.map((ref) => this.evidence(ref)),
          description: op.description,
          problem_state: "open",
          next_check: op.next_check,
          applied_change_ref: null,
          grounds: null,
          dismissal_reason: null,
        },
        op.description,
        op.visibility,
      );
      return true;
    }
    if (op.op === "review_signal") {
      const r = this.guarded(op.ref);
      requireThat(
        r.kind === "signal",
        "REFERENCE_TYPE_MISMATCH",
        "Expected Signal.",
      );
      requireThat(
        op.problem_state !== "observing" ||
          (op.applied_change_ref && op.next_check),
        "VALIDATION_ERROR",
        "Observing needs the applied change and a future check condition.",
      );
      requireThat(
        op.problem_state !== "resolved" || op.grounds,
        "VALIDATION_ERROR",
        "Resolved needs explicit grounds; a method edit/application alone does not resolve a problem.",
      );
      requireThat(
        op.problem_state !== "dismissed" || op.dismissal_reason,
        "VALIDATION_ERROR",
        "Dismissed needs a reason.",
      );
      const applied = op.applied_change_ref
        ? this.pin(op.applied_change_ref)
        : null;
      if (applied)
        requireThat(
          ["method", "knowledge", "work", "concept", "entity"].includes(
            this.address(applied).kind,
          ),
          "REFERENCE_TYPE_MISMATCH",
          "Applied change must address changed domain content, not an observation or claim of execution.",
        );
      if (applied)
        requireThat(
          object(op.applied_change_ref).revision !== undefined ||
            object(op.applied_change_ref).content_version !== undefined,
          "VALIDATION_ERROR",
          "Applied change must name an exact committed/staged version.",
        );
      const grounds = op.evidence_refs.map((ref) => this.evidence(ref));
      this.put(
        this.created[op.client_ref],
        "signal_review",
        {
          signal_ref: exactRef(r),
          assessment: op.assessment,
          evidence_refs: grounds,
          problem_state: op.problem_state,
          applied_change_ref: applied,
          next_check: op.next_check,
          grounds: op.grounds,
          dismissal_reason: op.dismissal_reason,
          recorded_at: this.now,
        },
        "Signal consideration",
        r.visibility,
      );
      this.put(
        r.id,
        "signal",
        {
          ...r.data,
          problem_state: op.problem_state,
          next_check: op.next_check,
          applied_change_ref: applied,
          grounds: op.grounds,
          dismissal_reason: op.dismissal_reason,
        },
        r.title,
      );
      return true;
    }
    return false;
  }
  write() {
    for (const r of this.changed.values()) {
      const owner =
        r.kind === "invocation"
          ? object(r.data.run_ref).id
          : r.kind === "signal_review"
            ? object(r.data.signal_ref).id
            : null;
      this.db.run(
        "INSERT INTO experience_rows(id,kind,owner_id,json) VALUES(?,?,?,?) ON CONFLICT(id) DO UPDATE SET json=excluded.json",
        r.id,
        r.kind,
        owner,
        JSON.stringify(r),
      );
      this.db.run(
        "INSERT INTO experience_versions VALUES(?,?,?)",
        r.id,
        r.revision,
        JSON.stringify(r),
      );
    }
  }
}

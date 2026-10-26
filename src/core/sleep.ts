import { createHash, randomUUID } from "node:crypto";
import { z } from "zod";
import { canonical, requireThat } from "./contracts.ts";
import type {
  AddressedRow,
  CallContext,
  CommitRequest,
  StoragePort,
} from "./contracts.ts";
import { exactRef } from "./experience.ts";

/** Supporting coverage, frozen membership and dispositions, in the existing store. */
export const SleepSchemaSQL = `
CREATE TABLE sleep_reviews(id TEXT PRIMARY KEY,work_id TEXT NOT NULL,profile TEXT NOT NULL,scope TEXT NOT NULL,epoch TEXT NOT NULL,high_watermark INTEGER NOT NULL,status TEXT NOT NULL,batch_id TEXT NOT NULL,episode_id TEXT NOT NULL,FOREIGN KEY(id) REFERENCES records(id) DEFERRABLE INITIALLY DEFERRED,FOREIGN KEY(work_id) REFERENCES records(id) DEFERRABLE INITIALLY DEFERRED,FOREIGN KEY(episode_id) REFERENCES records(id) DEFERRABLE INITIALLY DEFERRED);
CREATE INDEX sleep_active ON sleep_reviews(profile,scope,epoch,status);
CREATE TABLE sleep_items(id TEXT PRIMARY KEY,review_id TEXT NOT NULL,position INTEGER NOT NULL,batch_id TEXT,json TEXT NOT NULL,FOREIGN KEY(review_id) REFERENCES sleep_reviews(id),UNIQUE(review_id,position));
CREATE INDEX sleep_members ON sleep_items(review_id,batch_id,position);
CREATE TABLE sleep_coverage(profile TEXT NOT NULL,scope TEXT NOT NULL,epoch TEXT NOT NULL,through_seq INTEGER NOT NULL,PRIMARY KEY(profile,scope,epoch));`;

const exact = z.strictObject({
  id: z.string().min(1),
  revision: z.number().int().positive(),
  content_version: z.number().int().positive().optional(),
});
export const SleepItem = z.strictObject({
  ref: exact,
  input: z.enum(["change", "open_problem", "deferred"]),
  prior_item_id: z.string().nullable(),
  disposition: z.enum(["considered", "changed", "deferred"]).nullable(),
  reason: z.string().nullable(),
  continuation: z.string().nullable(),
  evidence_refs: z.array(exact),
  change_refs: z.array(exact),
  expected_benefit: z.string().nullable(),
  limits: z.string().nullable(),
  next_check: z.string().nullable(),
  check_signal_ref: exact.nullable(),
});
type Item = z.infer<typeof SleepItem>;
type Review = {
  id: string;
  work_id: string;
  profile: string;
  scope: string;
  epoch: string;
  high_watermark: number;
  status: string;
  batch_id: string;
  episode_id: string;
};
type Member = {
  id: string;
  json: string;
  position: number;
  batch_id: string | null;
};
type Op = Extract<
  CommitRequest["ops"][number],
  { op: "start_sleep" | "sleep_checkpoint" }
>;
const key = (v: unknown) =>
  createHash("sha256").update(canonical(v)).digest("hex");
const refid = (v: unknown) => (v as { id?: string } | null)?.id;
// Prospective refs are compared only during preflight; Core resolves real IDs before storage.
const scopeid = (v: unknown) =>
  refid(v) ??
  ((v as { client_ref?: string } | null)?.client_ref
    ? "staged-activity:" + (v as { client_ref: string }).client_ref
    : undefined);

/** A repeated unresolved deferral inherits exact grounds, including pre-fix rows. */
function inherited(db: StoragePort, item: Item) {
  const evidence = new Map(item.evidence_refs.map((p) => [canonical(p), p])),
    changes = new Map(item.change_refs.map((p) => [canonical(p), p])),
    seen = new Set<string>();
  let prior = item.prior_item_id,
    check = item.check_signal_ref;
  while (prior) {
    requireThat(
      !seen.has(prior),
      "STORE_UNAVAILABLE",
      "Cyclic deferred ancestry.",
    );
    seen.add(prior);
    const row = db.get<{ json: string }>(
      "SELECT json FROM sleep_items WHERE id=?",
      prior,
    );
    requireThat(row, "STORE_UNAVAILABLE", "Deferred grounds are missing.");
    const p = SleepItem.parse(JSON.parse(row.json));
    for (const ref of p.evidence_refs) evidence.set(canonical(ref), ref);
    for (const ref of p.change_refs) changes.set(canonical(ref), ref);
    check ??= p.check_signal_ref;
    prior = p.prior_item_id;
  }
  return {
    evidence_refs: [...evidence.values()],
    change_refs: [...changes.values()],
    check_signal_ref: check,
  };
}

/** Access edges, not retention pins: reconstruct from existing typed schema-7 rows.
 * Review progress depends on its frozen inputs. A correction depends on the exact
 * member and declared grounds, even when the canonical Method has older context.
 */
export function sleepAccessRefs(db: StoragePort, itemIds?: readonly string[]) {
  const edges = new Map<string, Item["evidence_refs"]>();
  if (!db.get("SELECT name FROM sqlite_master WHERE name='sleep_items'"))
    return edges;
  const add = (key: string, refs: Item["evidence_refs"]) =>
    edges.set(key, [...(edges.get(key) ?? []), ...refs]);
  for (const row of db.all<{
    json: string;
    work_id: string;
    review_id: string;
    episode_id: string;
  }>(
    `SELECT i.json,r.work_id,r.id AS review_id,r.episode_id FROM sleep_items i JOIN sleep_reviews r ON r.id=i.review_id${itemIds ? " WHERE i.id IN (" + itemIds.map(() => "?").join(",") + ")" : ""}`,
    ...(itemIds ?? []),
  )) {
    const item = SleepItem.parse(JSON.parse(row.json)),
      grounds = inherited(db, item);
    const refs = [
      item.ref,
      ...grounds.evidence_refs,
      ...grounds.change_refs,
      ...(grounds.check_signal_ref ? [grounds.check_signal_ref] : []),
    ];
    for (const id of [row.work_id, row.review_id, row.episode_id])
      add(id, refs);
    // Existing managed access conservatively classifies the identity, including
    // later revisions that can carry forward the derived text. Exact versions
    // remain in the disposition; this edge does not retain any extra version.
    for (const ref of [
      ...item.change_refs,
      ...(item.check_signal_ref ? [item.check_signal_ref] : []),
    ])
      add(ref.id, [item.ref, ...grounds.evidence_refs]);
  }
  return edges;
}

/** No independent commit path: mutations are called only inside Core.commit's transaction. */
export class Sleep {
  constructor(
    private db: StoragePort,
    private ctx: CallContext,
    private address: (id: string, revision?: number) => AddressedRow,
    private allowed: (id: string, revision?: number) => boolean,
  ) {}
  private get profile() {
    return key([
      this.ctx.workspace_id,
      this.ctx.principal,
      [...(this.ctx.scopes ?? [])].sort(),
      this.ctx.can_write,
      this.ctx.policy_revision ?? null,
    ]);
  }
  private review(id: string) {
    const r = this.db.get<Review>(
      "SELECT * FROM sleep_reviews WHERE id=? AND profile=?",
      id,
      this.profile,
    );
    requireThat(
      r && this.allowed(r.id) && this.allowed(r.work_id),
      "REFERENCE_NOT_FOUND",
      "Sleep review unavailable for this access profile.",
    );
    requireThat(
      r.epoch === this.ctx.epoch,
      "RESTORE_RECONCILIATION_REQUIRED",
      "Historical Sleep progress belongs to an old epoch. Explicitly start a new review over restored retained history.",
    );
    const work = this.address(r.work_id);
    requireThat(
      r.status !== "active" ||
        (refid(work.data.activity_id) ?? "global") === r.scope,
      "REVISION_CONFLICT",
      "Review Work scope changed; abort and explicitly request a new review.",
    );
    return r;
  }
  /** No raw sequence, restricted gap, total history count or global generation is exposed. */
  batch(runId?: string, cursor?: string) {
    if (!runId) {
      let after = Number.MAX_SAFE_INTEGER;
      if (cursor) {
        const last = this.db.get<Review & { rowid: number }>(
          "SELECT rowid,* FROM sleep_reviews WHERE id=? AND profile=? AND epoch=?",
          cursor,
          this.profile,
          this.ctx.epoch,
        );
        requireThat(
          last && this.allowed(last.id) && this.allowed(last.work_id),
          "CURSOR_INVALIDATED",
          "Sleep list continuation is unavailable under this profile.",
        );
        after = last.rowid;
      }
      const reviews: Review[] = [];
      while (reviews.length <= 10) {
        const page = this.db.all<Review & { rowid: number }>(
          "SELECT rowid,* FROM sleep_reviews WHERE profile=? AND epoch=? AND status='active' AND rowid<? ORDER BY rowid DESC LIMIT 100",
          this.profile,
          this.ctx.epoch,
          after,
        );
        if (!page.length) break;
        for (const r of page) {
          after = r.rowid;
          if (this.allowed(r.id) && this.allowed(r.work_id)) reviews.push(r);
          if (reviews.length > 10) break;
        }
      }
      return {
        reviews: reviews.slice(0, 10).map((r) => ({
          run_ref: { id: r.id },
          episode_ref: { id: r.episode_id },
          work_ref: { id: r.work_id },
          scope:
            r.scope === "global"
              ? { mode: "global" }
              : { activity_ref: { id: r.scope } },
          status: r.status,
        })),
        has_more: reviews.length > 10,
        next_cursor: reviews.length > 10 ? reviews[9].id : null,
        instruction:
          "Read an addressed review's prepared batch; paginate this list with next_cursor if needed. Other access profiles have independent coverage. Historical restored progress requires an explicitly requested new current-epoch review. Starting another cycle requires an explicit request.",
      };
    }
    const r = this.review(runId);
    const members = this.db.all<Member>(
      "SELECT * FROM sleep_items WHERE review_id=? AND batch_id=? ORDER BY position",
      r.id,
      r.batch_id,
    );
    const cards = members.map((m) => {
      const item = SleepItem.parse(JSON.parse(m.json));
      requireThat(
        this.allowed(item.ref.id, item.ref.revision) &&
          this.allowed(item.ref.id),
        "REFERENCE_NOT_FOUND",
        "Prepared material is no longer available under this profile; coverage has not advanced.",
      );
      const source = this.address(item.ref.id, item.ref.revision),
        current = this.address(item.ref.id);
      return {
        item_id: m.id,
        ref: item.ref,
        input: item.input,
        kind: source.kind,
        title: source.title,
        current_revision: current.revision,
        prior_disposition: item.prior_item_id
          ? this.prior(item.prior_item_id)
          : null,
        description: String(
          source.data.summary ??
            source.data.description ??
            source.data.explanation ??
            source.data.statement ??
            source.body ??
            "Read exact addressed body and grounds",
        ).slice(0, 240),
      };
    });
    return {
      run_ref: { id: r.id },
      episode_ref: { id: r.episode_id },
      work_ref: { id: r.work_id },
      scope:
        r.scope === "global"
          ? { mode: "global" }
          : { activity_ref: { id: r.scope } },
      status: r.status,
      batch_id: r.batch_id,
      cards,
      has_more: !!this.db.get(
        "SELECT id FROM sleep_items WHERE review_id=? AND batch_id IS NULL AND json_extract(json,'$.disposition') IS NULL LIMIT 1",
        r.id,
      ),
      frozen_input: true,
      next:
        r.status === "active"
          ? "Read bodies/grounds, then atomically checkpoint every member with current revision guards."
          : "This cycle ended. New arrivals require an explicitly requested new cycle.",
    };
  }
  private prior(id: string) {
    const row = this.db.get<{ json: string }>(
      "SELECT json FROM sleep_items WHERE id=?",
      id,
    );
    requireThat(row, "STORE_UNAVAILABLE", "Deferred anchor is missing.");
    const p = SleepItem.parse(JSON.parse(row.json)),
      grounds = inherited(this.db, p);
    requireThat(
      [
        p.ref,
        ...grounds.evidence_refs,
        ...grounds.change_refs,
        ...(grounds.check_signal_ref ? [grounds.check_signal_ref] : []),
      ].every(
        (ref) => this.allowed(ref.id, ref.revision) && this.allowed(ref.id),
      ),
      "REFERENCE_NOT_FOUND",
      "Deferred material unavailable.",
    );
    return {
      ref: p.ref,
      reason: p.reason,
      continuation: p.continuation,
      next_check: p.next_check,
      ...grounds,
    };
  }
  private local(
    r: Pick<AddressedRow, "kind" | "data">,
    scope: string,
    read: (ref: unknown) => Pick<AddressedRow, "kind" | "data"> = (p) =>
      this.address(refid(p)!, (p as { revision?: number }).revision),
  ): boolean {
    if (r.kind === "work") return scopeid(r.data.activity_id) === scope;
    if (r.kind === "run") {
      const w = r.data.work_ref;
      return !!w && this.local(read(w), scope, read);
    }
    if (["invocation", "evaluation"].includes(r.kind)) {
      const run = r.data.run_ref,
        target = r.data.target_ref;
      return (
        !!run &&
        this.local(read(run), scope, read) &&
        (!target || this.local(read(target), scope, read))
      );
    }
    if (r.kind === "signal") {
      const refs = r.data.subject_refs as { id: string }[];
      return (
        refs.length > 0 &&
        refs.every(
          (p) =>
            ["work", "run"].includes(read(p).kind) &&
            this.local(read(p), scope, read),
        )
      );
    }
    if (r.kind === "signal_review") {
      const s = r.data.signal_ref;
      return !!s && this.local(read(s), scope, read);
    }
    if (r.kind === "evidence") {
      const w = r.data.work_ref,
        run = r.data.run_ref;
      return (
        !!(w || run) &&
        (!w || this.local(read(w), scope, read)) &&
        (!run || this.local(read(run), scope, read))
      );
    }
    // Origin, classification, focus and natural language never establish local ownership.
    return false;
  }
  private relevant(r: AddressedRow, scope: string) {
    if (this.local(r, scope) || ["knowledge", "method"].includes(r.kind))
      return true;
    const refs =
      r.kind === "signal"
        ? (r.data.subject_refs as { id: string; revision?: number }[])
        : ([r.data.run_ref, r.data.work_ref].filter(Boolean) as {
            id: string;
            revision?: number;
          }[]);
    // Mixed records can be relevant context; relevance never establishes write ownership.
    return refs.some((p) => this.local(this.address(p.id, p.revision), scope));
  }
  /** An active binding cannot be moved, even by an approved ordinary update. Abort first. */
  assertBindings(changed: AddressedRow[]) {
    for (const row of changed.filter((r) => r.kind === "work"))
      for (const review of this.db.all<Review>(
        "SELECT * FROM sleep_reviews WHERE work_id=? AND epoch=? AND status='active'",
        row.id,
        this.ctx.epoch,
      ))
        requireThat(
          (refid(row.data.activity_id) ?? "global") === review.scope,
          "INVALID_TRANSITION",
          "Active Sleep scope is immutable. Abort the review before moving its Work.",
        );
  }
  needsApproval(request: CommitRequest) {
    const read = (p: unknown): Pick<AddressedRow, "kind" | "data"> => {
      const ref = p as { id?: string; revision?: number; client_ref?: string };
      if (ref.client_ref) {
        const staged = request.ops.find(
          (o) => "client_ref" in o && o.client_ref === ref.client_ref,
        );
        requireThat(
          staged,
          "REFERENCE_NOT_FOUND",
          "Staged ownership anchor is missing.",
        );
        if (staged.op === "create_record")
          return { kind: staged.kind, data: staged.data };
        if (staged.op === "start_run")
          return { kind: "run", data: { work_ref: staged.work_ref } };
        if (staged.op === "record_result")
          return {
            kind: "evidence",
            data: {
              work_ref: staged.work_ref ?? null,
              run_ref: staged.run_ref ?? null,
            },
          };
        if (staged.op === "record_evaluation")
          return {
            kind: "evaluation",
            data: {
              target_ref: staged.target_ref,
              run_ref: staged.run_ref ?? null,
            },
          };
        if (staged.op === "open_signal")
          return {
            kind: "signal",
            data: { subject_refs: staged.subject_refs },
          };
        return { kind: "knowledge", data: {} }; // Unknown ownership stays shared.
      }
      const row = this.address(ref.id!, ref.revision);
      const update = request.ops.find(
        (o) => o.op === "update_record" && o.ref.id === row.id,
      );
      return update?.op === "update_record"
        ? { ...row, data: update.data }
        : row;
    };
    const op = request.ops.find(
      (o): o is Extract<Op, { op: "sleep_checkpoint" }> =>
        o.op === "sleep_checkpoint",
    );
    const start = request.ops.find(
      (o): o is Extract<Op, { op: "start_sleep" }> => o.op === "start_sleep",
    );
    let reviews: Pick<Review, "status" | "scope">[];
    if (op && "id" in op.run_ref) reviews = [this.review(op.run_ref.id)];
    else if (start) {
      if ("id" in start.work_ref)
        requireThat(
          this.allowed(start.work_ref.id),
          "REFERENCE_NOT_FOUND",
          "Sleep binding Work is unavailable.",
        );
      // apply(start_sleep) binds the final current Work, never its optional historical selector.
      const work = read(
        "id" in start.work_ref ? { id: start.work_ref.id } : start.work_ref,
      );
      requireThat(
        work.kind === "work",
        "REFERENCE_TYPE_MISMATCH",
        "Sleep binds ordinary Work.",
      );
      reviews = [
        { status: "active", scope: scopeid(work.data.activity_id) ?? "global" },
      ];
    } else {
      reviews = this.db
        .all<Review>(
          "SELECT * FROM sleep_reviews WHERE profile=? AND epoch=? AND status='active'",
          this.profile,
          this.ctx.epoch,
        )
        .filter((r) => this.allowed(r.id) && this.allowed(r.work_id));
      const focus = this.db.get<{ json: string }>(
        "SELECT json FROM focus WHERE session_id=?",
        this.ctx.session_id,
      );
      const work = focus && refid(JSON.parse(focus.json).work_ref);
      // Existing explicit Work focus selects ordinary work outside a review. It grants
      // no access or local ownership, and cannot change a checkpoint's fixed scope.
      if (
        work &&
        this.allowed(work) &&
        !this.db.get("SELECT id FROM sleep_reviews WHERE work_id=?", work)
      )
        return false;
    }
    return reviews.some(
      (r) =>
        r.status === "active" &&
        r.scope !== "global" &&
        request.ops.some((o) => {
          const local = (p: unknown) => this.local(read(p), r.scope, read);
          if (
            [
              "start_sleep",
              "sleep_checkpoint",
              "set_focus",
              "import_evidence",
            ].includes(o.op)
          )
            return false;
          if ("ref" in o) return !local(o.ref);
          if (o.op === "create_record")
            return (
              !["work", "run"].includes(o.kind) ||
              (o.kind === "work" && scopeid(o.data.activity_id) !== r.scope)
            );
          if (o.op === "record_result")
            return ![o.work_ref, o.run_ref].filter(Boolean).every(local);
          if (o.op === "record_evaluation")
            return ![o.target_ref, o.run_ref].filter(Boolean).every(local);
          if (o.op === "start_run") return !local({ client_ref: o.client_ref });
          if (o.op === "open_signal") return !o.subject_refs.every(local);
          return true;
        }),
    );
  }
  private technical(r: AddressedRow, seen = new Set<string>()): boolean {
    if (seen.has(r.id)) return false;
    seen.add(r.id);
    if (["signal_review", "environment"].includes(r.kind)) return true;
    if (r.kind === "run" && r.data.mode === "sleep") return true;
    if (
      this.db.get(
        "SELECT id FROM sleep_reviews WHERE id=? OR work_id=?",
        r.id,
        r.id,
      )
    )
      return true;
    const anchor =
      refid(r.data.run_ref) ??
      refid(r.data.work_ref) ??
      refid(r.data.target_ref);
    if (
      anchor &&
      this.db.get(
        "SELECT id FROM sleep_reviews WHERE id=? OR work_id=?",
        anchor,
        anchor,
      )
    )
      return true;
    const targets = [
      refid(r.data.run_ref),
      refid(r.data.work_ref),
      refid(r.data.target_ref),
    ].filter((id): id is string => !!id);
    const related = (id: string) => {
      const row = this.db.get<{ json: string }>(
        "SELECT json FROM addressed_current WHERE id=?",
        id,
      );
      return !!row && this.technical(JSON.parse(row.json), new Set(seen));
    };
    if (targets.some(related)) return true;
    if (r.kind === "signal") {
      const subjects = r.data.subject_refs as { id: string }[];
      if (subjects.length && subjects.every((p) => related(p.id))) return true;
    }
    return false;
  }
  apply(
    op: Op,
    request: CommitRequest,
    read: (id: string, revision?: number) => AddressedRow,
    changed: AddressedRow[],
  ) {
    requireThat(
      "id" in op.run_ref,
      "VALIDATION_ERROR",
      "Resolved Run required.",
    );
    if (op.op === "start_sleep") {
      requireThat(
        "id" in op.work_ref,
        "VALIDATION_ERROR",
        "Resolved Work required.",
      );
      const work = read(op.work_ref.id),
        run = read(op.run_ref.id),
        scope = refid(work.data.activity_id) ?? "global";
      requireThat(
        work.kind === "work" &&
          run.kind === "run" &&
          run.data.mode === "sleep" &&
          run.data.execution === "running" &&
          refid(run.data.work_ref) === work.id,
        "REFERENCE_TYPE_MISMATCH",
        "Sleep requires its ordinary Work and running Sleep episode.",
      );
      requireThat(
        !this.db.get("SELECT id FROM sleep_reviews WHERE id=?", run.id),
        "IDEMPOTENCY_CONFLICT",
        "Run already has a frozen review; read its batch.",
      );
      const guard = (row: AddressedRow) => {
        const persisted = this.db.get<{ json: string }>(
          "SELECT json FROM addressed_current WHERE id=?",
          row.id,
        );
        if (persisted)
          requireThat(
            request.guards.some(
              (g) =>
                g.ref.id === row.id &&
                g.expected_revision === JSON.parse(persisted.json).revision,
            ),
            "REVISION_CONFLICT",
            "Sleep binding requires current Work/Run/previous-episode guards.",
          );
      };
      guard(work);
      guard(run);
      this.db.run(
        "INSERT OR REPLACE INTO focus(session_id,json) VALUES(?,?)",
        this.ctx.session_id,
        JSON.stringify({
          activity_ref: scope === "global" ? null : { id: scope },
          work_ref: { id: work.id },
        }),
      );
      const active = this.db.get<Review>(
        "SELECT id FROM sleep_reviews WHERE profile=? AND scope=? AND epoch=? AND status='active'",
        this.profile,
        scope,
        this.ctx.epoch,
      );
      if (active) {
        const existing = this.review(active.id),
          prior = read(existing.episode_id);
        requireThat(
          existing.work_id === work.id &&
            refid(run.data.continuation_of) === prior.id &&
            prior.data.execution === "interrupted" &&
            run.data.case_id === prior.data.case_id,
          "WORK_IN_USE",
          "Resume/abort the existing review; a new episode must explicitly continue its interrupted case and Work.",
        );
        guard(prior);
        this.db.run(
          "UPDATE sleep_reviews SET episode_id=? WHERE id=?",
          run.id,
          existing.id,
        );
        return;
      }
      const high = this.db.get<{ seq: number }>(
        "SELECT coalesce(max(seq),0) AS seq FROM changes",
      )!.seq;
      const through =
        this.db.get<{ through_seq: number }>(
          "SELECT through_seq FROM sleep_coverage WHERE profile=? AND scope=? AND epoch=?",
          this.profile,
          scope,
          this.ctx.epoch,
        )?.through_seq ?? 0;
      this.db.run(
        "INSERT INTO sleep_reviews VALUES(?,?,?,?,?,?,?,?,?)",
        run.id,
        work.id,
        this.profile,
        scope,
        this.ctx.epoch,
        high,
        "active",
        "preparing",
        run.id,
      );
      const seen = new Set<string>();
      let position = 0;
      const add = (
        r: AddressedRow,
        input: Item["input"],
        prior_item_id: string | null = null,
      ) => {
        const ref = exactRef(r),
          identity = canonical(ref);
        if (seen.has(identity) && prior_item_id) {
          const previous = this.db.get<{ id: string; json: string }>(
            "SELECT id,json FROM sleep_items WHERE review_id=? AND json_extract(json,'$.ref.id')=? AND json_extract(json,'$.ref.revision')=?",
            run.id,
            ref.id,
            ref.revision,
          )!;
          this.db.run(
            "UPDATE sleep_items SET json=? WHERE id=?",
            JSON.stringify({
              ...JSON.parse(previous.json),
              input,
              prior_item_id,
            }),
            previous.id,
          );
        }
        if (
          seen.has(identity) ||
          r.storage === "tombstone" ||
          this.technical(r) ||
          !this.allowed(r.id, r.revision) ||
          !this.allowed(r.id)
        )
          return;
        if (scope !== "global" && !this.relevant(r, scope)) return;
        seen.add(identity);
        const item: Item = {
          ref,
          input,
          prior_item_id,
          disposition: null,
          reason: null,
          continuation: null,
          evidence_refs: [],
          change_refs: [],
          expected_benefit: null,
          limits: null,
          next_check: null,
          check_signal_ref: null,
        };
        if (prior_item_id) Object.assign(item, inherited(this.db, item));
        this.db.run(
          "INSERT INTO sleep_items VALUES(?,?,?,?,?)",
          "sleep-item-" + randomUUID(),
          run.id,
          ++position,
          null,
          JSON.stringify(item),
        );
      };
      // Keyset pages bound each technical read, never the total review.
      let after = through;
      for (;;) {
        const page = this.db.all<{ seq: number; json: string }>(
          "SELECT seq,json FROM changes WHERE seq>? AND seq<=? ORDER BY seq LIMIT 100",
          after,
          high,
        );
        if (!page.length) break;
        for (const event of page) {
          after = event.seq;
          const change = JSON.parse(event.json);
          if (change.sleep_review_ref) continue;
          for (const ref of change.changed_refs ?? []) {
            if (
              !ref.id ||
              !ref.after_revision ||
              !this.allowed(ref.id, ref.after_revision)
            )
              continue;
            add(this.address(ref.id, ref.after_revision), "change");
          }
        }
      }
      for (const row of this.db.all<{ json: string }>(
        "SELECT json FROM experience_rows WHERE kind='signal' AND json_extract(json,'$.data.problem_state') IN ('open','observing') ORDER BY id",
      ))
        add(JSON.parse(row.json), "open_problem");
      for (const row of this.db.all<{ id: string; json: string }>(
        "SELECT i.id,i.json FROM sleep_items i JOIN sleep_reviews r ON r.id=i.review_id WHERE r.profile=? AND r.scope=? AND r.id<>? AND json_extract(i.json,'$.disposition')='deferred' AND NOT EXISTS(SELECT 1 FROM sleep_items n WHERE json_extract(n.json,'$.prior_item_id')=i.id AND json_extract(n.json,'$.disposition') IS NOT NULL) ORDER BY i.rowid",
        this.profile,
        scope,
        run.id,
      )) {
        const item = SleepItem.parse(JSON.parse(row.json));
        if (this.allowed(item.ref.id, item.ref.revision))
          add(this.address(item.ref.id, item.ref.revision), "deferred", row.id);
      }
      this.prepare(run.id);
      return;
    }
    const review = this.review(op.run_ref.id);
    requireThat(
      (refid(read(review.work_id).data.activity_id) ?? "global") ===
        review.scope,
      "REVISION_CONFLICT",
      "Checkpoint cannot change the bound review scope.",
    );
    requireThat(
      this.address(review.episode_id).data.execution === "running",
      "INVALID_TRANSITION",
      "Continue the running Sleep episode or explicitly restart after interruption.",
    );
    requireThat(
      review.status === "active" && review.batch_id === op.batch_id,
      "REVISION_CONFLICT",
      "Prepared batch changed; re-read without advancing progress.",
    );
    const members = this.db.all<Member>(
      "SELECT * FROM sleep_items WHERE review_id=? AND batch_id=? ORDER BY position",
      review.id,
      review.batch_id,
    );
    requireThat(
      canonical(members.map((m) => m.id).sort()) ===
        canonical(op.dispositions.map((d) => d.item_id).sort()),
      "VALIDATION_ERROR",
      "Checkpoint must dispose every exact prepared member once.",
    );
    const changedRefs = new Set<string>();
    for (const member of members) {
      const item = SleepItem.parse(JSON.parse(member.json)),
        d = op.dispositions.find((d) => d.item_id === member.id)!;
      const current = this.address(item.ref.id);
      requireThat(
        this.allowed(item.ref.id, item.ref.revision) &&
          request.guards.some(
            (g) =>
              g.ref.id === current.id &&
              g.expected_revision === current.revision,
          ),
        "REVISION_CONFLICT",
        "Read every batch member's current revision and guard it; no progress was committed.",
      );
      requireThat(
        d.disposition !== "deferred" || (d.continuation && d.next_check),
        "VALIDATION_ERROR",
        "Deferred requires an addressed continuation and check condition.",
      );
      requireThat(
        d.disposition !== "changed" ||
          (d.change_refs.length &&
            d.evidence_refs.length &&
            d.expected_benefit &&
            d.limits &&
            d.next_check &&
            d.check_signal_ref),
        "VALIDATION_ERROR",
        "Correction needs exact changed refs, grounds, expected benefit, risk/limits and an ordinary open/observing Signal for the later real check.",
      );
      const pin = (p: unknown) => {
        const id = refid(p);
        requireThat(id, "REFERENCE_NOT_FOUND", "Exact grounds required.");
        const r = read(id, (p as { revision?: number }).revision);
        requireThat(
          (p as { content_version?: number }).content_version === undefined ||
            (p as { content_version?: number }).content_version ===
              r.data.content_version,
          "REVISION_CONFLICT",
          "Exact Method content version changed.",
        );
        requireThat(
          r.storage !== "tombstone",
          "CONTENT_NOT_RETAINED",
          "Required grounds not retained.",
        );
        return exactRef(r);
      };
      const changes = d.change_refs.map(pin),
        prior = d.disposition === "deferred" ? inherited(this.db, item) : null,
        evidence = [
          ...new Map(
            [
              ...d.evidence_refs.map(pin),
              ...(prior?.evidence_refs.map(pin) ?? []),
            ].map((p) => [canonical(p), p]),
          ).values(),
        ];
      const checkRef = d.check_signal_ref ?? prior?.check_signal_ref;
      const check = checkRef ? pin(checkRef) : null;
      if (check)
        requireThat(
          read(check.id).kind === "signal" &&
            ["open", "observing"].includes(
              String(read(check.id).data.problem_state),
            ),
          "VALIDATION_ERROR",
          "Later verification must remain an ordinary open/observing Signal.",
        );
      for (const p of evidence)
        requireThat(
          read(p.id, p.revision).kind === "evidence",
          "REFERENCE_TYPE_MISMATCH",
          "Correction grounds must include retained source Evidence.",
        );
      for (const p of changes) {
        requireThat(
          changed.some((r) => r.id === p.id && r.revision === p.revision),
          "REVISION_CONFLICT",
          "Changed disposition must name a change in this atomic checkpoint.",
        );
        changedRefs.add(p.id);
      }
      this.db.run(
        "UPDATE sleep_items SET json=? WHERE id=?",
        JSON.stringify({
          ...item,
          ...d,
          item_id: undefined,
          evidence_refs: evidence,
          change_refs: [
            ...new Map(
              [...changes, ...(prior?.change_refs.map(pin) ?? [])].map((p) => [
                canonical(p),
                p,
              ]),
            ).values(),
          ],
          check_signal_ref: check,
        }),
        member.id,
      );
    }
    for (const r of changed)
      if (["knowledge", "method"].includes(r.kind))
        requireThat(
          changedRefs.has(r.id),
          "VALIDATION_ERROR",
          "Every Sleep knowledge/method correction needs an addressed changed disposition.",
        );
    if (op.abort)
      this.db.run(
        "UPDATE sleep_reviews SET status='aborted' WHERE id=?",
        review.id,
      );
    else this.prepare(review.id);
  }
  private prepare(id: string) {
    const batch = "sleep-batch-" + randomUUID();
    const members = this.db.all<{ id: string }>(
      "SELECT id FROM sleep_items WHERE review_id=? AND batch_id IS NULL ORDER BY position LIMIT 10",
      id,
    );
    for (const m of members)
      this.db.run("UPDATE sleep_items SET batch_id=? WHERE id=?", batch, m.id);
    this.db.run(
      "UPDATE sleep_reviews SET batch_id=?,status=? WHERE id=?",
      batch,
      members.length ? "active" : "completed",
      id,
    );
    if (!members.length) {
      const r = this.db.get<Review>(
        "SELECT * FROM sleep_reviews WHERE id=?",
        id,
      )!;
      this.db.run(
        "INSERT INTO sleep_coverage VALUES(?,?,?,?) ON CONFLICT(profile,scope,epoch) DO UPDATE SET through_seq=max(through_seq,excluded.through_seq)",
        r.profile,
        r.scope,
        r.epoch,
        r.high_watermark,
      );
    }
  }
}

/** Bundle verification and retention share the same typed exact grounds. */
export function sleepGrounds(db: StoragePort) {
  const bindings = db
    .all<{
      id: string;
      work_id: string;
      episode_id: string;
    }>(
      "SELECT id,work_id,episode_id FROM sleep_reviews WHERE status='active' AND epoch=?",
      db.workspace.epoch,
    )
    .flatMap((r) => [r.id, r.work_id, r.episode_id].map((id) => ({ id })));
  return [
    ...bindings,
    ...db
      .all<{
        id: string;
        json: string;
      }>(
        `SELECT i.id,i.json FROM sleep_items i JOIN sleep_reviews r ON r.id=i.review_id WHERE (r.status='active' AND r.epoch=? AND json_extract(i.json,'$.disposition') IS NULL) OR json_extract(i.json,'$.disposition') IN ('deferred','changed')`,
        db.workspace.epoch,
      )
      .flatMap(({ id, json }) => {
        const item = SleepItem.parse(JSON.parse(json));
        if (item.disposition === "changed" && item.check_signal_ref) {
          const signal = db.get<{ json: string }>(
            "SELECT json FROM experience_rows WHERE id=?",
            item.check_signal_ref.id,
          );
          if (
            signal &&
            ["resolved", "dismissed"].includes(
              JSON.parse(signal.json).data.problem_state,
            )
          )
            return [];
        }
        if (
          item.disposition === "deferred" &&
          db.get(
            "SELECT id FROM sleep_items WHERE json_extract(json,'$.prior_item_id')=? AND json_extract(json,'$.disposition') IS NOT NULL",
            id,
          )
        )
          return [];
        const grounds =
          item.disposition === "deferred" || item.disposition === null
            ? inherited(db, item)
            : item;
        return [
          item.ref,
          ...grounds.evidence_refs,
          ...grounds.change_refs,
          ...(grounds.check_signal_ref ? [grounds.check_signal_ref] : []),
        ];
      }),
  ];
}

export function validateSleep(
  db: StoragePort,
  get: (ref: unknown, kind?: string) => AddressedRow,
) {
  const high = db.get<{ n: number }>(
    "SELECT coalesce(max(seq),0) AS n FROM changes",
  )!.n;
  for (const r of db.all<Review>("SELECT * FROM sleep_reviews")) {
    const run = get({ id: r.id }, "run"),
      work = get({ id: r.work_id }, "work"),
      episode = get({ id: r.episode_id }, "run");
    const active = r.status === "active" && r.epoch === db.workspace.epoch;
    requireThat(
      ["active", "completed", "aborted"].includes(r.status) &&
        Number.isSafeInteger(r.high_watermark) &&
        r.high_watermark >= 0 &&
        r.high_watermark <= high &&
        /^[0-9a-f]{64}$/.test(r.profile),
      "STORE_UNAVAILABLE",
      "Invalid Sleep state/profile/frontier.",
    );
    if (active || run.storage !== "tombstone")
      requireThat(
        run.data.mode === "sleep" && refid(run.data.work_ref) === r.work_id,
        "STORE_UNAVAILABLE",
        "Invalid Sleep binding.",
      );
    if (active)
      requireThat(
        work.storage !== "tombstone" &&
          (refid(work.data.activity_id) ?? "global") === r.scope &&
          episode.data.mode === "sleep" &&
          refid(episode.data.work_ref) === r.work_id &&
          episode.data.case_id === run.data.case_id,
        "STORE_UNAVAILABLE",
        "Invalid active Sleep episode.",
      );
    if (r.scope !== "global") get({ id: r.scope }, "activity");
    const members = db.all<Member>(
      "SELECT * FROM sleep_items WHERE review_id=? ORDER BY position",
      r.id,
    );
    const prepared = members.filter((m) => m.batch_id === r.batch_id),
      pending = members.filter(
        (m) => SleepItem.parse(JSON.parse(m.json)).disposition === null,
      );
    requireThat(
      members.every((m, i) => m.position === i + 1),
      "STORE_UNAVAILABLE",
      "Frozen Sleep membership has a gap.",
    );
    requireThat(
      r.status !== "completed" || pending.length === 0,
      "STORE_UNAVAILABLE",
      "Completed review has undisposed members.",
    );
    requireThat(
      r.status !== "active" ||
        (prepared.length > 0 &&
          prepared.length <= 10 &&
          prepared.every(
            (m) => SleepItem.parse(JSON.parse(m.json)).disposition === null,
          ) &&
          canonical(prepared.map((m) => m.id)) ===
            canonical(pending.slice(0, 10).map((m) => m.id))),
      "STORE_UNAVAILABLE",
      "Invalid prepared Sleep membership.",
    );
    for (const member of members) {
      const item = SleepItem.parse(JSON.parse(member.json));
      requireThat(
        member.batch_id !== null || item.disposition === null,
        "STORE_UNAVAILABLE",
        "Unprepared Sleep disposition.",
      );
      requireThat(
        item.disposition !== "deferred" ||
          (item.reason && item.continuation && item.next_check),
        "STORE_UNAVAILABLE",
        "Deferred Sleep anchor lacks continuation.",
      );
      requireThat(
        item.disposition !== "changed" ||
          (item.reason &&
            item.change_refs.length &&
            item.evidence_refs.length &&
            item.expected_benefit &&
            item.limits &&
            item.next_check &&
            item.check_signal_ref),
        "STORE_UNAVAILABLE",
        "Sleep correction lacks exact grounds/check.",
      );
      if (item.prior_item_id) {
        const prior = db.get<{ json: string; profile: string; scope: string }>(
          "SELECT i.json,r.profile,r.scope FROM sleep_items i JOIN sleep_reviews r ON r.id=i.review_id WHERE i.id=?",
          item.prior_item_id,
        );
        requireThat(
          prior &&
            prior.profile === r.profile &&
            prior.scope === r.scope &&
            canonical(SleepItem.parse(JSON.parse(prior.json)).ref) ===
              canonical(item.ref),
          "STORE_UNAVAILABLE",
          "Invalid deferred Sleep ancestry.",
        );
      }
    }
  }
  for (const c of db.all<{
    profile: string;
    scope: string;
    epoch: string;
    through_seq: number;
  }>("SELECT * FROM sleep_coverage")) {
    const completed = db.get<{ n: number | null }>(
      "SELECT max(high_watermark) AS n FROM sleep_reviews WHERE profile=? AND scope=? AND epoch=? AND status='completed'",
      c.profile,
      c.scope,
      c.epoch,
    );
    requireThat(
      completed?.n === c.through_seq,
      "STORE_UNAVAILABLE",
      "Sleep coverage lacks completed frozen membership.",
    );
  }
  for (const ref of sleepGrounds(db))
    requireThat(
      get(ref).storage !== "tombstone",
      "STORE_UNAVAILABLE",
      "Sleep check lost exact retained grounds.",
    );
}

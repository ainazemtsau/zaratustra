import { canonical, requireThat, WorkData } from "./contracts.ts";
import type { CommitRequest, RecordRow, Work } from "./contracts.ts";

export const terminal = (s: string) => s === "done" || s === "cancelled";
export const refId = (r: unknown) => (r as { id?: string } | null)?.id ?? "";
export const plan = (w: Work) => ({
  objective: w.objective,
  acceptance: w.acceptance,
  parent_work_id: w.parent_work_id,
  required_for_parent: w.required_for_parent ?? true,
  steps: w.steps.map((s) => ({
    step_id: s.step_id,
    intent: s.intent,
    depends_on: s.depends_on,
    child_work_id: s.child_work_id ?? null,
    required: s.required ?? true,
  })),
  waits: w.waits.map((w) => ({
    wait_id: w.wait_id,
    kind: w.kind,
    target: w.target,
    subject: w.subject,
    satisfied_by: w.satisfied_by,
    due_at: w.due_at,
    timezone: w.timezone,
  })),
});

// Structural validation only. The model judges meaning and matching grounds.
export function validateWorks(
  rows: RecordRow[],
  get: (ref: unknown, kind?: string) => RecordRow,
) {
  const works = new Map(
    rows
      .filter((r) => r.kind === "work")
      .map((r) => [r.id, WorkData.parse(r.data)]),
  );
  const edges = new Map<string, string[]>();
  const node = (
    workId: string,
    kind: "parent" | "complete" | "step",
    stepId?: string,
  ) => JSON.stringify([workId, kind, stepId ?? null]);
  const add = (a: string, b: string) =>
    edges.set(a, [...(edges.get(a) ?? []), b]);
  for (const [id, w] of works) {
    if (w.activity_id) get(w.activity_id, "activity");
    if (w.parent_work_id) {
      const p = get(w.parent_work_id, "work");
      requireThat(
        !("revision" in w.parent_work_id),
        "VALIDATION_ERROR",
        "Parent must be a current Work reference.",
      );
      add(node(id, "parent"), node(p.id, "parent"));
    }
    const unique = (values: string[]) =>
      requireThat(
        new Set(values).size === values.length,
        "VALIDATION_ERROR",
        "Step, criterion and wait IDs must each be unique.",
      );
    unique(w.steps.map((s) => s.step_id));
    unique(w.waits.map((s) => s.wait_id));
    unique(w.acceptance.map((s) => s.criterion_id));
    for (const ref of w.context_refs) get(ref);
    for (const s of w.steps) {
      for (const ref of s.result_refs) get(ref);
      if (s.child_work_id) {
        requireThat(
          !("revision" in s.child_work_id),
          "VALIDATION_ERROR",
          "Step child must be a current Work reference.",
        );
        const child = get(s.child_work_id, "work");
        requireThat(
          refId(child.data.parent_work_id) === id,
          "REFERENCE_TYPE_MISMATCH",
          "A step's child must have this Work as its single direct parent.",
        );
        add(node(id, "step", s.step_id), node(child.id, "complete"));
        if (s.status === "done")
          requireThat(
            child.data.status === "done",
            "DEPENDENCY_UNSATISFIED",
            "The child is not successfully completed.",
          );
      }
      for (const d of s.depends_on) {
        const target =
          "work_ref" in d
            ? get(d.work_ref, "work")
            : rows.find((r) => r.id === id)!;
        if ("work_ref" in d)
          requireThat(
            !("revision" in d.work_ref),
            "VALIDATION_ERROR",
            "Execution dependencies must reference current Work.",
          );
        const dw = works.get(target.id)!;
        const ds = d.step_id
          ? dw.steps.find((x) => x.step_id === d.step_id)
          : undefined;
        requireThat(
          !d.step_id || ds,
          "REFERENCE_NOT_FOUND",
          "Dependency step does not exist.",
        );
        if ("criterion_id" in d && d.criterion_id)
          requireThat(
            dw.acceptance.some((c) => c.criterion_id === d.criterion_id),
            "REFERENCE_NOT_FOUND",
            "Dependency criterion does not exist.",
          );
        add(
          node(id, "step", s.step_id),
          d.step_id
            ? node(target.id, "step", d.step_id)
            : node(target.id, "complete"),
        );
        if (s.status === "running" || s.status === "done")
          requireThat(
            ds ? ds.status === "done" : dw.status === "done",
            "DEPENDENCY_UNSATISFIED",
            "A completion dependency is not satisfied; cancelled/skipped is not success.",
          );
      }
      if (s.required !== false)
        add(node(id, "complete"), node(id, "step", s.step_id));
      if (s.status === "done")
        requireThat(
          s.result_refs.length > 0,
          "SOURCE_MISSING",
          "Done step needs addressed result grounds.",
        );
      if (["running", "done"].includes(s.status))
        requireThat(
          !w.waits.some(
            (wait) =>
              typeof wait.target !== "string" &&
              wait.target.step_id === s.step_id &&
              !["satisfied", "withdrawn"].includes(wait.status ?? "pending"),
          ),
          "DEPENDENCY_UNSATISFIED",
          "Step still has an unsatisfied input wait.",
        );
    }
    for (const wait of w.waits) {
      if (typeof wait.target !== "string")
        requireThat(
          w.steps.some(
            (s) => s.step_id === (wait.target as { step_id: string }).step_id,
          ),
          "REFERENCE_NOT_FOUND",
          "Wait step does not exist.",
        );
      for (const ref of wait.received_refs) get(ref, "evidence");
      if (wait.kind === "time") {
        requireThat(
          wait.due_at && wait.timezone,
          "VALIDATION_ERROR",
          "Time wait needs an exact instant and IANA timezone.",
        );
        try {
          new Intl.DateTimeFormat("en", { timeZone: wait.timezone }).format();
        } catch {
          requireThat(false, "VALIDATION_ERROR", "Invalid IANA timezone.");
        }
      }
      if (wait.status === "satisfied")
        requireThat(
          wait.resolution &&
            (wait.kind === "time"
              ? Date.parse(wait.due_at!) <= Date.now()
              : wait.received_refs.length > 0),
          "DEPENDENCY_UNSATISFIED",
          "Satisfied wait needs received grounds or an elapsed exact instant, and a resolution.",
        );
      if (wait.status === "withdrawn")
        requireThat(
          wait.resolution,
          "SOURCE_MISSING",
          "Withdrawing a wait needs a reason.",
        );
    }
    const pending = w.waits.filter(
      (x) => !["satisfied", "withdrawn"].includes(x.status ?? "pending"),
    );
    requireThat(
      w.status !== "active" || w.next_action,
      "INVALID_TRANSITION",
      "Active Work needs a meaningful next action.",
    );
    if (w.status === "waiting") {
      requireThat(
        pending.length > 0,
        "INVALID_TRANSITION",
        "Waiting Work needs an addressed pending wait.",
      );
      const independent = w.steps.some(
        (s) =>
          ["todo", "running"].includes(s.status) &&
          (!s.child_work_id ||
            works.get(refId(s.child_work_id))?.status === "done") &&
          !pending.some(
            (x) =>
              typeof x.target !== "string" && x.target.step_id === s.step_id,
          ) &&
          s.depends_on.every((d) => {
            const dw = "work_ref" in d ? works.get(refId(d.work_ref))! : w;
            return d.step_id
              ? dw.steps.find((x) => x.step_id === d.step_id)?.status === "done"
              : dw.status === "done";
          }),
      );
      const activeChild = [...works.values()].some(
        (child) =>
          child.parent_work_id &&
          refId(child.parent_work_id) === id &&
          child.status === "active",
      );
      requireThat(
        !independent && !activeChild,
        "INVALID_TRANSITION",
        "An independent step is available; the whole Work cannot be waiting.",
      );
    }
    if (w.status === "done") {
      requireThat(
        w.completion,
        "SOURCE_MISSING",
        "Done Work needs completion grounds.",
      );
      requireThat(
        pending.length === 0 &&
          w.steps.every((s) => s.required === false || s.status === "done"),
        "DEPENDENCY_UNSATISFIED",
        "Required steps and pending waits block completion; explicitly revise the plan first.",
      );
      for (const c of w.acceptance.filter((c) => c.required)) {
        const grounds = w.completion.grounds.filter(
          (g) => g.criterion_id === c.criterion_id,
        );
        requireThat(
          grounds.length > 0,
          "SOURCE_MISSING",
          "Each required criterion needs matching grounds.",
        );
      }
      for (const g of w.completion.grounds) {
        requireThat(
          w.acceptance.some((c) => c.criterion_id === g.criterion_id),
          "REFERENCE_NOT_FOUND",
          "Unknown completion criterion.",
        );
        for (const ref of g.evidence_refs) {
          const r = get(ref);
          requireThat(
            r.id !== id && (r.kind !== "work" || r.data.status === "done"),
            "DEPENDENCY_UNSATISFIED",
            "Completion cannot be supported by itself or unsuccessful Work.",
          );
        }
      }
    } else
      requireThat(
        w.completion === null,
        "INVALID_TRANSITION",
        "Only done Work has current completion; older completion stays in revision history.",
      );
    if (w.status === "cancelled")
      requireThat(
        w.cancellation?.reason && w.cancellation.consequences,
        "SOURCE_MISSING",
        "Cancellation needs reason and downstream consequences.",
      );
  }
  for (const [id, w] of works)
    if (w.parent_work_id && w.required_for_parent !== false) {
      const p = works.get(refId(w.parent_work_id))!;
      add(node(refId(w.parent_work_id), "complete"), node(id, "complete"));
      if (p.status === "done")
        requireThat(
          w.status === "done",
          "DEPENDENCY_UNSATISFIED",
          "An unfinished required child blocks parent completion.",
        );
    }
  const visiting = new Set<string>(),
    seen = new Set<string>();
  const visit = (key: string) => {
    requireThat(
      !visiting.has(key),
      "GRAPH_CYCLE",
      "Work parent/dependency graph contains a cycle.",
    );
    if (seen.has(key)) return;
    visiting.add(key);
    for (const next of edges.get(key) ?? []) visit(next);
    visiting.delete(key);
    seen.add(key);
  };
  for (const key of edges.keys()) visit(key);
}

export function protectWorkUpdate(
  before: Work,
  after: Work,
  op: Extract<CommitRequest["ops"][number], { op: "update_record" }>,
  decision: (handle?: string) => void,
) {
  requireThat(
    before.status === after.status &&
      canonical(before.completion) === canonical(after.completion) &&
      canonical(before.cancellation ?? null) ===
        canonical(after.cancellation ?? null),
    "INVALID_TRANSITION",
    "Use transition_work for lifecycle changes.",
  );
  for (const s of after.steps) {
    const old = before.steps.find((x) => x.step_id === s.step_id);
    requireThat(
      old
        ? s.status === old.status &&
            canonical(s.result_refs) === canonical(old.result_refs)
        : s.status === "todo" && s.result_refs.length === 0,
      "INVALID_TRANSITION",
      "Use transition_step for step lifecycle/results.",
    );
  }
  if (
    after.waits.some(
      (w) =>
        w.status === "withdrawn" &&
        before.waits.find((x) => x.wait_id === w.wait_id)?.status !==
          "withdrawn",
    )
  )
    decision(op.decision_source_handle);
  if (canonical(plan(before)) !== canonical(plan(after))) {
    requireThat(
      !terminal(before.status),
      "INVALID_TRANSITION",
      "Use a new Work for a new goal or explicitly reopen before revising a terminal plan.",
    );
    requireThat(
      op.plan_change_reason,
      "SOURCE_MISSING",
      "Plan revision needs an explicit reason and current decision source.",
    );
    decision(op.decision_source_handle);
  }
}

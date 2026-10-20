import test from "node:test";
import assert from "node:assert/strict";
import { mkdtempSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { Core, type Work, type RecordRow } from "../src/core/index.ts";
import { DiskStorage } from "../src/storage/index.ts";

function setup() {
  const home = mkdtempSync(
    join(process.env.ZARATUSTRA_TEST_ROOT ?? tmpdir(), "zara-work-"),
  );
  const disk = new DiskStorage(home),
    core = new Core(disk, {
      ...disk.workspace,
      principal: "trusted-personal",
      session_id: "controller",
      runtime_id: "runtime",
      can_write: true,
      processing_allowed: true,
    });
  const source = core.capture(
    "Synthetic explicit plan/lifecycle decision and useful result.",
    "rpc",
    "trusted-synthetic-controller",
  ).source_handle;
  let n = 0;
  const row = (id: string) => core.read(id).data as RecordRow;
  const work = (id: string) => row(id).data as Work;
  const send = (
    ops: unknown[],
    ids: string[] = [],
    claim_tokens: string[] = [],
  ) =>
    core.commit({
      request_id: "operation-" + ++n,
      reason: "Synthetic invariant test.",
      source_handles: [source],
      guards: ids.map((id) => ({
        ref: { id },
        expected_revision: row(id).revision,
      })),
      ops,
      claim_tokens,
    });
  const evidence = send([
    {
      op: "import_evidence",
      client_ref: "e",
      source_handle: source,
      title: "Synthetic grounds",
      source_language: "en",
    },
  ]).created.e;
  const create = (client_ref: string, data = base()) => ({
    op: "create_record",
    client_ref,
    kind: "work",
    title: client_ref,
    visibility: "workspace",
    data,
  });
  const update = (id: string, data: Work) => ({
    op: "update_record",
    ref: { id },
    data,
    plan_change_reason: "Explicit synthetic plan revision",
    decision_source_handle: source,
  });
  const claim = (
    id: string,
    purpose: "work" | "step" | "handoff" = "work",
    step_id?: string,
  ) =>
    core.claim({
      action: "acquire",
      work_id: id,
      expected_revision: row(id).revision,
      purpose,
      step_id,
      reason: "Perform supported local recording.",
    }).data.token as string;
  const finish = (id: string) =>
    send(
      [
        {
          op: "transition_work",
          ref: { id },
          status: "done",
          reason: "Criterion verified from retained synthetic result.",
          grounds: [
            {
              criterion_id: "result",
              explanation: "Grounded result retained",
              evidence_refs: [{ id: evidence }],
            },
          ],
        },
      ],
      [id, evidence],
      [claim(id)],
    );
  return {
    disk,
    core,
    source,
    row,
    work,
    send,
    evidence,
    create,
    update,
    claim,
    finish,
  };
}
function base(): Work {
  return {
    activity_id: null,
    parent_work_id: null,
    objective: "Produce a grounded synthetic result.",
    acceptance: [
      {
        criterion_id: "result",
        description: "Result retained",
        verification: "Inspect addressed result",
        required: true,
      },
    ],
    status: "active",
    current_state: "Ready for independent action",
    next_action: "Produce result",
    steps: [],
    waits: [],
    context_refs: [],
    completion: null,
  };
}
const step = (step_id: string) => ({
  step_id,
  intent: "Produce " + step_id,
  status: "todo" as const,
  depends_on: [],
  result_refs: [],
});

test("a saved handoff is reusable preparation-step grounds without a duplicate message record", () => {
  const f = setup();
  try {
    const id = f.send([
      f.create("preparation", { ...base(), steps: [step("prepare")] }),
    ]).created.preparation;
    const h = f.send(
      [
        {
          op: "prepare_handoff",
          client_ref: "h",
          work_ref: { id },
          step_id: "prepare",
          objective: "Review the card",
          conditions: "Do not send",
          expected_result: "Clarity and title comments",
          context_refs: [],
          message: "Please review this card's clarity and propose a title.",
        },
      ],
      [id],
      [f.claim(id, "handoff", "prepare")],
    ).created.h;
    const records = f.disk.all("SELECT * FROM records");
    const artifact = f.core.handoff(h).data;
    f.send(
      [
        {
          op: "transition_step",
          ref: { id },
          step_id: "prepare",
          status: "done",
          reason: "The requested manual message is durably prepared, not sent.",
          result_refs: [{ id: h }],
        },
      ],
      [id],
      [f.claim(id, "step", "prepare")],
    );
    assert.equal(f.work(id).steps[0].status, "done");
    assert.deepEqual(f.work(id).steps[0].result_refs, [{ id: h }]);
    assert.deepEqual(f.core.handoff(h).data, artifact);
    assert.equal(f.disk.all("SELECT * FROM records").length, records.length);
    assert.equal(artifact.transport_state, "prepared_not_sent");
  } finally {
    f.disk.close();
  }
});

test("preparation grounds retain claims and ref guards, external waits stay separate, and reopen waits for new input", () => {
  const f = setup();
  const snapshot = () =>
    JSON.stringify(
      ["records", "revisions", "changes", "receipts", "claims", "handoffs"].map(
        (t) => f.disk.all("SELECT * FROM " + t + " ORDER BY rowid"),
      ),
    );
  try {
    const id = f.send([
      f.create("card", {
        ...base(),
        steps: [{ ...step("prepare"), required: false }, step("review")],
        waits: [
          {
            wait_id: "review-reply",
            kind: "external_result",
            target: { step_id: "review" },
            subject: "Clarity and title",
            satisfied_by: "Both review sections received",
            received_refs: [],
            question: "Return both sections",
            status: "pending",
          },
        ],
      }),
    ]).created.card;
    f.send(
      [
        {
          op: "transition_step",
          ref: { id },
          step_id: "review",
          status: "waiting",
          reason: "Await the actual external review",
        },
      ],
      [id],
    );
    const h = f.send(
      [
        {
          op: "prepare_handoff",
          client_ref: "h",
          work_ref: { id },
          step_id: "review",
          objective: "Review card",
          conditions: "Prepare only",
          expected_result: "Clarity and title",
          context_refs: [],
          message: "Check clarity and suggest a title.",
        },
      ],
      [id],
      [f.claim(id, "handoff", "review")],
    ).created.h;
    assert.equal(f.work(id).steps[0].status, "todo");
    assert.equal(f.work(id).steps[1].status, "waiting");
    const done = (ref: unknown) => ({
      op: "transition_step",
      ref: { id },
      step_id: "prepare",
      status: "done",
      reason: "Saved preparation, not external review",
      result_refs: [ref],
    });
    let before = snapshot();
    assert.throws(() => f.send([done({ id: h })], [id]), /claim/);
    assert.equal(snapshot(), before);
    const token = f.claim(id, "step", "prepare");
    before = snapshot();
    for (const ref of [{ id: h, revision: 2 }, { id: "missing-result" }]) {
      assert.throws(
        () => f.send([done(ref)], [id], [token]),
        /revision 1|unavailable/,
      );
      assert.equal(snapshot(), before);
    }
    assert.throws(
      () =>
        f.core.commit({
          request_id: "stale-link",
          reason: "Rejected stale premise",
          source_handles: [f.source],
          guards: [{ ref: { id }, expected_revision: 3 }],
          claim_tokens: [token],
          ops: [done({ id: h })],
        }),
      /guarded premise changed/,
    );
    assert.equal(snapshot(), before);
    f.send([done({ id: h, revision: 1 })], [id], [token]);
    assert.equal(f.work(id).steps[0].required, false);
    assert.equal(f.work(id).steps[1].status, "waiting");
    assert.equal(f.work(id).waits[0].status, "pending");
    f.send(
      [
        {
          op: "transition_work",
          ref: { id },
          status: "waiting",
          reason: "No independent action remains",
        },
      ],
      [id],
    );
    const externalToken = f.claim(id, "step", "review"),
      unchanged = snapshot();
    assert.throws(
      () =>
        f.send(
          [{ ...done({ id: h }), step_id: "review" }],
          [id],
          [externalToken],
        ),
      /unsatisfied input wait/,
    );
    assert.equal(snapshot(), unchanged);
    f.send(
      [
        f.update(id, {
          ...f.work(id),
          waits: f.work(id).waits.map((w) => ({
            ...w,
            status: "satisfied",
            received_refs: [{ id: f.evidence }],
            resolution: "Both sections received",
          })),
        }),
        { ...done({ id: f.evidence }), step_id: "review" },
        {
          op: "transition_work",
          ref: { id },
          status: "active",
          reason: "Review received; inspect grounds",
          next_action: "Check criterion",
        },
      ],
      [id],
      [externalToken],
    );
    const complete = f.finish(id),
      historical = f.row(id);
    const oldResults = structuredClone(
      f.work(id).steps.map((s) => s.result_refs),
    );
    f.send(
      [
        {
          op: "transition_work",
          ref: { id },
          status: "active",
          reason: "Explicit reopen for a future clarification",
          decision_source_handle: f.source,
          next_action: "Record the upcoming clarification wait",
        },
      ],
      [id],
    );
    f.send(
      [
        f.update(id, {
          ...f.work(id),
          waits: [
            ...f.work(id).waits,
            {
              wait_id: "clarification",
              kind: "user",
              target: "work",
              subject: "Card's future clarification",
              satisfied_by: "The requested clarification arrives",
              received_refs: [],
              question: "Send the clarification",
              status: "pending",
            },
          ],
        }),
        {
          op: "transition_work",
          ref: { id },
          status: "waiting",
          reason: "Only the new clarification is missing",
        },
      ],
      [id],
    );
    assert.equal(f.work(id).waits[0].status, "satisfied");
    assert.equal(f.work(id).waits[1].status, "pending");
    assert.deepEqual(
      f.work(id).steps.map((s) => s.result_refs),
      oldResults,
    );
    assert.deepEqual(
      f.core.read(id, complete.new_revisions[id]).data,
      historical,
    );
    before = snapshot();
    f.core.read(id);
    f.core.handoff(h);
    assert.equal(snapshot(), before);
    f.send(
      [
        {
          op: "import_evidence",
          client_ref: "clarification",
          source_handle: f.source,
          title: "Actual later clarification",
          source_language: "en",
        },
        f.update(id, {
          ...f.work(id),
          waits: f.work(id).waits.map((w) =>
            w.wait_id === "clarification"
              ? {
                  ...w,
                  status: "satisfied",
                  received_refs: [{ client_ref: "clarification" }],
                  resolution: "The new input arrived",
                }
              : w,
          ),
        }),
        {
          op: "transition_work",
          ref: { id },
          status: "active",
          reason: "Now use the actual clarification",
          next_action: "Revise using retained input",
        },
      ],
      [id],
    );
    assert.equal(f.work(id).waits[1].status, "satisfied");
    assert.deepEqual(
      f.work(id).steps.map((s) => s.result_refs),
      oldResults,
    );
    const other = f.send([
      f.create("other", { ...base(), steps: [step("prepare")] }),
    ]).created.other;
    assert.throws(
      () =>
        f.send(
          [{ ...done({ id: h }), ref: { id: other } }],
          [other],
          [f.claim(other, "step", "prepare")],
        ),
      /for this Work/,
    );
    const optional = f.send([
      f.create("optional", {
        ...base(),
        steps: [{ ...step("unused"), required: false }],
      }),
    ]).created.optional;
    f.finish(optional);
    assert.equal(f.work(optional).steps[0].status, "todo");
    const independent = f.send([
      f.create("independent", {
        ...base(),
        steps: [step("independent")],
        waits: [
          {
            wait_id: "input",
            kind: "user",
            target: "work",
            subject: "Other input",
            satisfied_by: "Input received",
            received_refs: [],
            question: "Provide input",
            status: "pending",
          },
        ],
      }),
    ]).created.independent;
    assert.equal(f.work(independent).status, "active");
    assert.throws(
      () =>
        f.send(
          [
            {
              op: "transition_work",
              ref: { id: independent },
              status: "waiting",
              reason: "Wrongly stop independent action",
            },
          ],
          [independent],
        ),
      /independent step/,
    );
  } finally {
    f.disk.close();
  }
});

test("linking an immutable preparation result is atomic with claim, revision, Change and receipt", () => {
  for (const point of ["after_records", "before_commit", "after_commit"]) {
    const f = setup();
    try {
      const id = f.send([
        f.create("w", { ...base(), steps: [step("prepare")] }),
      ]).created.w;
      const h = f.send(
        [
          {
            op: "prepare_handoff",
            client_ref: "h",
            work_ref: { id },
            objective: "Review card",
            conditions: "Do not send",
            expected_result: "Comments",
            context_refs: [],
            message: "Please review this card.",
          },
        ],
        [id],
        [f.claim(id, "handoff")],
      ).created.h;
      const artifact = f.core.handoff(h).data,
        token = f.claim(id, "step", "prepare");
      const c = new Core(f.disk, f.core.context, (p) => {
        if (p === point) throw new Error("synthetic link fault");
      });
      const source = c.capture(
        "Record the saved preparation",
        "rpc",
        "trusted-controller",
      );
      assert.throws(
        () =>
          c.commit({
            request_id: "link-fault",
            reason: "Link existing preparation",
            source_handles: [source.source_handle],
            guards: [{ ref: { id }, expected_revision: 1 }],
            claim_tokens: [token],
            ops: [
              {
                op: "transition_step",
                ref: { id },
                step_id: "prepare",
                status: "done",
                reason: "Prepared only",
                result_refs: [{ id: h }],
              },
            ],
          }),
        /synthetic link fault/,
      );
      const committed = point === "after_commit";
      assert.equal(f.row(id).revision, committed ? 2 : 1);
      assert.equal(f.work(id).steps[0].status, committed ? "done" : "todo");
      assert.equal(
        !!f.disk.get("SELECT * FROM receipts WHERE request_id='link-fault'"),
        committed,
      );
      assert.equal(
        JSON.parse(
          f.disk.get<{ json: string }>(
            "SELECT json FROM claims WHERE token=?",
            token,
          )!.json,
        ).state,
        committed ? "consumed" : "active",
      );
      assert.deepEqual(f.core.handoff(h).data, artifact);
    } finally {
      f.disk.close();
    }
  }
});

test("nested graph and final-batch cycles, wrong references and update lifecycle bypass are rejected atomically", () => {
  const f = setup();
  const seq = f.core.sequence();
  assert.throws(
    () =>
      f.send([
        f.create("a", { ...base(), parent_work_id: { client_ref: "b" } }),
        f.create("b", { ...base(), parent_work_id: { client_ref: "a" } }),
      ]),
    /cycle/,
  );
  assert.equal(f.core.sequence(), seq);
  assert.throws(
    () =>
      f.send([
        f.create("wrong", { ...base(), parent_work_id: { id: f.evidence } }),
      ]),
    /wrong kind/,
  );
  assert.throws(
    () =>
      f.send([
        f.create("steps", {
          ...base(),
          steps: [
            { ...step("a"), depends_on: [{ step_id: "b" }] },
            { ...step("b"), depends_on: [{ step_id: "a" }] },
          ],
        }),
      ]),
    /cycle/,
  );
  const id = f.send([f.create("work")]).created.work;
  assert.throws(
    () => f.send([f.update(id, { ...f.work(id), status: "done" })], [id]),
    /transition_work/,
  );
  assert.throws(
    () =>
      f.send(
        [
          f.update(id, {
            ...f.work(id),
            steps: [
              {
                ...step("forged"),
                status: "done",
                result_refs: [{ id: f.evidence }],
              },
            ],
          }),
        ],
        [id],
      ),
    /transition_step/,
  );
  assert.throws(
    () =>
      f.send(
        [
          {
            op: "transition_work",
            ref: { id },
            status: "done",
            reason: "Unsupported assertion",
          },
        ],
        [id],
      ),
    /claim/,
  );
  const token = f.claim(id);
  assert.throws(
    () =>
      f.send(
        [
          {
            op: "transition_work",
            ref: { id },
            status: "done",
            reason: "No criterion grounds",
          },
        ],
        [id],
        [token],
      ),
    /matching grounds/,
  );
  f.disk.close();
});

test("required child/step conditions, grounded completion, cancellation is not success, reopening retains history", () => {
  const f = setup();
  const r = f.send([
    f.create("p"),
    f.create("c", { ...base(), parent_work_id: { client_ref: "p" } }),
  ]);
  const p = r.created.p,
    c = r.created.c;
  const token = f.claim(p);
  assert.throws(
    () =>
      f.send(
        [
          {
            op: "transition_work",
            ref: { id: p },
            status: "done",
            reason: "Premature",
            grounds: [
              {
                criterion_id: "result",
                explanation: "Insufficient",
                evidence_refs: [{ id: f.evidence }],
              },
            ],
          },
        ],
        [p, f.evidence],
        [token],
      ),
    /required child/,
  );
  f.core.claim({
    action: "release",
    work_id: p,
    expected_revision: 1,
    token,
    reason: "Test rejected premature close",
  });
  f.finish(c);
  assert.equal(f.work(p).status, "active");
  f.finish(p);
  const completed = f.row(p);
  assert.equal(
    (
      (completed.data as Work).completion!.grounds[0].evidence_refs[0] as {
        revision: number;
      }
    ).revision,
    1,
  );
  f.send(
    [
      {
        op: "transition_work",
        ref: { id: p },
        status: "active",
        next_action: "Inspect the correction",
        reason: "Explicitly reopen same case for a correction",
        decision_source_handle: f.source,
      },
      f.update(c, { ...f.work(c), context_refs: [{ id: f.evidence }] }),
    ],
    [p, c],
  );
  assert.equal(f.work(p).completion, null);
  assert.equal(
    ((f.core.read(p, completed.revision).data as RecordRow).data as Work)
      .status,
    "done",
  );
  f.send(
    [
      {
        op: "transition_work",
        ref: { id: c },
        status: "active",
        next_action: "Inspect correction",
        reason: "Explicit correction to child",
        decision_source_handle: f.source,
      },
    ],
    [c],
  );
  f.send(
    [
      {
        op: "transition_work",
        ref: { id: c },
        status: "cancelled",
        reason: "User abandoned child",
        consequences: "Parent cannot complete until plan explicitly revised",
        decision_source_handle: f.source,
      },
    ],
    [c],
  );
  assert.equal(f.work(c).status, "cancelled");
  const t = f.claim(p);
  assert.throws(
    () =>
      f.send(
        [
          {
            op: "transition_work",
            ref: { id: p },
            status: "done",
            reason: "Cancellation is not success",
            grounds: [
              {
                criterion_id: "result",
                explanation: "Invalid",
                evidence_refs: [{ id: c }],
              },
            ],
          },
        ],
        [p, c],
        [t],
      ),
    /unsuccessful|unfinished/,
  );
  f.disk.close();
});

test("dependencies and parent pause suppress execution without changing child facts; independent steps continue", () => {
  const f = setup();
  const r = f.send([
    f.create("p"),
    f.create("c", {
      ...base(),
      parent_work_id: { client_ref: "p" },
      steps: [
        step("one"),
        { ...step("two"), depends_on: [{ step_id: "one" }] },
      ],
    }),
  ]);
  const p = r.created.p,
    c = r.created.c;
  const t = f.claim(c, "step", "two");
  assert.throws(
    () =>
      f.send(
        [
          {
            op: "transition_step",
            ref: { id: c },
            step_id: "two",
            status: "done",
            reason: "Too soon",
            result_refs: [{ id: f.evidence }],
          },
        ],
        [c],
        [t],
      ),
    /dependency/,
  );
  f.core.claim({
    action: "release",
    work_id: c,
    expected_revision: 1,
    token: t,
    reason: "Blocked by dependency",
  });
  f.send(
    [
      {
        op: "transition_work",
        ref: { id: p },
        status: "paused",
        reason: "Explicit parent pause",
        decision_source_handle: f.source,
      },
    ],
    [p],
  );
  assert.equal(f.work(c).status, "active");
  assert.throws(() => f.claim(c, "step", "one"), /suppresses/);
  f.send(
    [
      {
        op: "transition_work",
        ref: { id: p },
        status: "active",
        reason: "Explicit resume",
        decision_source_handle: f.source,
      },
    ],
    [p],
  );
  f.send(
    [
      {
        op: "transition_step",
        ref: { id: c },
        step_id: "one",
        status: "done",
        reason: "Grounded result",
        result_refs: [{ id: f.evidence }],
      },
    ],
    [c],
    [f.claim(c, "step", "one")],
  );
  f.send(
    [
      {
        op: "transition_step",
        ref: { id: c },
        step_id: "two",
        status: "done",
        reason: "Dependency now met",
        result_refs: [{ id: f.evidence }],
      },
    ],
    [c],
    [f.claim(c, "step", "two")],
  );
  f.finish(c);
  const active = f.send([
    f.create("partial", {
      ...base(),
      steps: [step("waiting"), step("independent")],
      waits: [
        {
          wait_id: "parts",
          kind: "user",
          target: { step_id: "waiting" },
          subject: "Two report parts",
          satisfied_by: "Both parts received",
          received_refs: [],
          question: "Send remaining part",
          status: "pending",
        },
      ],
    }),
  ]).created.partial;
  f.send(
    [
      f.update(active, {
        ...f.work(active),
        waits: f.work(active).waits.map((w) => ({
          ...w,
          status: "partial",
          received_refs: [{ id: f.evidence }],
        })),
      }),
    ],
    [active],
  );
  assert.throws(
    () =>
      f.send(
        [
          {
            op: "transition_work",
            ref: { id: active },
            status: "waiting",
            reason: "Incorrect whole-Work wait",
          },
        ],
        [active],
      ),
    /independent step/,
  );
  f.send(
    [
      {
        op: "transition_step",
        ref: { id: active },
        step_id: "independent",
        status: "done",
        reason: "Useful independent action",
        result_refs: [{ id: f.evidence }],
      },
    ],
    [active],
    [f.claim(active, "step", "independent")],
  );
  assert.equal(f.work(active).waits[0].status, "partial");
  f.disk.close();
});

test("claims are independent of writer lease and bind revisions/runtime/epoch; expired unresolved claims need reconciliation", () => {
  const f = setup(),
    id = f.send([f.create("w")]).created.w;
  const t = f.claim(id);
  assert.throws(() => f.claim(id), /Unresolved managed claim/);
  f.send(
    [
      f.update(id, {
        ...f.work(id),
        current_state: "A new observed condition",
      }),
    ],
    [id],
  );
  assert.throws(
    () =>
      f.send(
        [
          {
            op: "transition_work",
            ref: { id },
            status: "done",
            reason: "Stale claim",
            grounds: [
              {
                criterion_id: "result",
                explanation: "Grounds",
                evidence_refs: [{ id: f.evidence }],
              },
            ],
          },
        ],
        [id, f.evidence],
        [t],
      ),
    /claim/,
  );
  const raw = JSON.parse(
    f.disk.get<{ json: string }>("SELECT json FROM claims WHERE token=?", t)!
      .json,
  );
  raw.expires_at = "2000-01-01T00:00:00Z";
  f.disk.run("UPDATE claims SET json=? WHERE token=?", JSON.stringify(raw), t);
  f.core.context.runtime_id = "fresh-runtime";
  assert.throws(() => f.claim(id), /Unresolved/);
  assert.throws(
    () =>
      f.core.claim({
        action: "release",
        work_id: id,
        expected_revision: 2,
        token: t,
        reason: "Unsafe release",
      }),
    /different runtime/,
  );
  f.core.capture(
    "Reconcile the abandoned local recording",
    "rpc",
    "trusted-controller",
  );
  const current = f.core.capture(
    "Explicit reconciliation after inspection",
    "rpc",
    "trusted-controller",
  );
  f.core.claim({
    action: "reconcile",
    work_id: id,
    expected_revision: 2,
    token: t,
    reason:
      "No external dispatch in supported action; inspected retained local state",
    source_handle: current.source_handle,
  });
  assert.ok(f.claim(id));
  f.disk.close();
});

test("manual handoff retains original plan and external authorship; partial/late events never auto-resume cancelled plan", () => {
  const f = setup();
  const id = f.send([
    f.create("w", {
      ...base(),
      waits: [
        {
          wait_id: "report",
          kind: "external_result",
          target: "work",
          subject: "Complete report",
          satisfied_by: "Both sections",
          received_refs: [],
          question: "Send report",
        },
      ],
    }),
  ]).created.w;
  const handoff = f.send(
    [
      {
        op: "prepare_handoff",
        client_ref: "h",
        work_ref: { id },
        objective: "Assess two sections",
        conditions: "Synthetic source only",
        expected_result: "Two addressed sections",
        context_refs: [{ id: f.evidence }],
        message: "Please assess the two sections; return both findings.",
      },
    ],
    [id],
    [f.claim(id, "handoff")],
  ).created.h;
  assert.equal(
    f.core.handoff(handoff).data.transport_state,
    "prepared_not_sent",
  );
  const receive = (client_ref: string, disposition: string) => ({
    op: "receive_handoff",
    client_ref,
    handoff_id: handoff,
    source_handle: f.source,
    title: "External partial report",
    source_language: "en",
    comparison: "Only first section received; remaining section missing",
    disposition,
    useful_content: "Useful first-section analysis",
    accepted_wait_ids: ["report"],
  });
  f.send(
    [
      receive("reply", "partial"),
      f.update(id, {
        ...f.work(id),
        waits: f.work(id).waits.map((w) => ({
          ...w,
          status: "partial",
          received_refs: [{ client_ref: "reply" }],
        })),
      }),
    ],
    [id],
  );
  assert.equal(f.work(id).waits[0].status, "partial");
  f.send(
    [
      f.update(id, {
        ...f.work(id),
        objective: "Changed goal; keep useful old analysis",
      }),
      {
        op: "transition_work",
        ref: { id },
        status: "paused",
        reason: "Explicit pause",
        decision_source_handle: f.source,
      },
    ],
    [id],
  );
  assert.equal(f.work(id).plan_version, 2);
  assert.throws(
    () => f.send([receive("bad", "accepted")], [id]),
    /late\/unrelated/,
  );
  f.send(
    [
      {
        op: "transition_work",
        ref: { id },
        status: "cancelled",
        reason: "Explicit cancel",
        consequences: "Keep late analysis; no obsolete execution",
        decision_source_handle: f.source,
      },
    ],
    [id],
  );
  const op = receive("late", "late");
  const one = f.send(
    [
      op,
      f.update(id, {
        ...f.work(id),
        waits: f.work(id).waits.map((w) => ({
          ...w,
          received_refs: [...w.received_refs, { client_ref: "late" }],
        })),
      }),
    ],
    [id],
  );
  const row = f.row(one.created.late);
  assert.equal(row.data.source_kind, "external_reply");
  assert.equal((row.data.provenance as { transport: string }).transport, "rpc");
  assert.equal(f.work(id).status, "cancelled");
  const two = f.send([{ ...op, accepted_wait_ids: [] }], [id]);
  assert.notEqual(one.created.late, two.created.late);
  assert.equal(
    f.row(one.created.late).data.content_hash,
    f.row(two.created.late).data.content_hash,
  );
  assert.throws(
    () =>
      f.send(
        [
          {
            op: "transition_work",
            ref: { id },
            status: "active",
            reason: "External reply is not resume authority",
          },
        ],
        [id],
      ),
    /current observed/,
  );
  f.disk.close();
});

test("time waits retain exact offsets/timezone and cannot be satisfied early", () => {
  const f = setup();
  const id = f.send([
    f.create("clock", {
      ...base(),
      status: "waiting",
      waits: [
        {
          wait_id: "time",
          kind: "time",
          target: "work",
          subject: "Scheduled review",
          satisfied_by: "Due instant",
          received_refs: [],
          question: "Wait until agreed time",
          due_at: "2099-11-01T09:30:00+03:00",
          timezone: "Europe/Minsk",
        },
      ],
    }),
  ]).created.clock;
  assert.equal(f.work(id).waits[0].due_at, "2099-11-01T09:30:00+03:00");
  assert.throws(
    () =>
      f.send(
        [
          f.update(id, {
            ...f.work(id),
            waits: f.work(id).waits.map((w) => ({
              ...w,
              status: "satisfied",
              resolution: "Too early",
            })),
          }),
        ],
        [id],
      ),
    /elapsed exact instant/,
  );
  assert.throws(
    () =>
      f.send(
        [
          f.update(id, {
            ...f.work(id),
            waits: f
              .work(id)
              .waits.map((w) => ({ ...w, timezone: "Invalid/Clock" })),
          }),
        ],
        [id],
      ),
    /IANA timezone/,
  );
  f.disk.close();
});

test("addressed generated results and handoff/claim transaction recovery preserve all-or-none state", () => {
  const f = setup(),
    id = f.send([
      f.create("result-work", { ...base(), steps: [step("write")] }),
    ]).created["result-work"];
  const receipt = f.send(
    [
      {
        op: "record_result",
        client_ref: "result",
        work_ref: { id },
        step_id: "write",
        title: "Written result",
        content: "A durable generated invitation. 🦉",
        source_language: "en",
      },
      {
        op: "transition_step",
        ref: { id },
        step_id: "write",
        status: "done",
        reason: "Text is durably addressed",
        result_refs: [{ client_ref: "result" }],
      },
    ],
    [id],
    [f.claim(id, "step", "write")],
  );
  assert.equal(
    f.row(receipt.created.result).data.source_kind,
    "generated_artifact",
  );
  assert.equal(
    (
      f.core.read(receipt.created.result, 1, { start: 0, length: 8000 })
        .data as unknown as { text: string }
    ).text,
    "A durable generated invitation. 🦉",
  );
  f.disk.close();
  for (const point of [
    "after_prepare",
    "after_records",
    "before_commit",
    "after_commit",
  ]) {
    const t = setup(),
      w = t.send([t.create("fault-work")]).created["fault-work"],
      token = t.claim(w, "handoff");
    const c = new Core(t.disk, t.core.context, (p) => {
      if (p === point) throw new Error("synthetic handoff fault");
    });
    const s = c.capture(
      "Prepare this synthetic manual handoff",
      "rpc",
      "trusted-controller",
    );
    assert.throws(
      () =>
        c.commit({
          request_id: "handoff-fault",
          reason: "Atomic handoff preparation",
          source_handles: [s.source_handle],
          guards: [{ ref: { id: w }, expected_revision: 1 }],
          claim_tokens: [token],
          ops: [
            {
              op: "prepare_handoff",
              client_ref: "h",
              work_ref: { id: w },
              objective: "Inspect local text",
              conditions: "No sending",
              expected_result: "A textual report",
              context_refs: [],
              message: "Please inspect the local text and return a report.",
            },
            {
              op: "update_record",
              ref: { id: w },
              data: {
                ...t.work(w),
                current_state: "Handoff prepared, not sent",
              },
            },
          ],
        }),
      /fault/,
    );
    const committed = point === "after_commit";
    assert.equal(
      t.disk.get<{ n: number }>("SELECT count(*) AS n FROM handoffs")!.n,
      committed ? 1 : 0,
    );
    assert.equal(
      JSON.parse(
        t.disk.get<{ json: string }>(
          "SELECT json FROM claims WHERE token=?",
          token,
        )!.json,
      ).state,
      committed ? "consumed" : "active",
    );
    assert.equal(t.row(w).revision, committed ? 2 : 1);
    t.disk.close();
  }
});

test("ancestor revisions invalidate child claims and parent-goal changes make replies late in the final transaction", () => {
  const f = setup(),
    r = f.send([
      f.create("parent"),
      f.create("child", {
        ...base(),
        parent_work_id: { client_ref: "parent" },
      }),
    ]),
    p = r.created.parent,
    c = r.created.child;
  const token = f.claim(c, "handoff");
  const h = f.send(
    [
      {
        op: "prepare_handoff",
        client_ref: "h",
        work_ref: { id: c },
        objective: "Inspect the child under the parent goal",
        conditions: "Current parent plan",
        expected_result: "One useful comment",
        context_refs: [],
        message: "Please inspect the synthetic child.",
      },
    ],
    [c, p],
    [token],
  ).created.h;
  assert.equal(f.core.handoff(h).data.plan_snapshot.length, 2);
  const stale = f.claim(c);
  f.send([f.update(p, { ...f.work(p), objective: "New parent goal" })], [p]);
  assert.throws(
    () =>
      f.send(
        [
          {
            op: "record_result",
            client_ref: "x",
            work_ref: { id: c },
            title: "Stale execution",
            content: "Old goal result",
            source_language: "en",
          },
        ],
        [c],
        [stale],
      ),
    /claim/,
  );
  f.core.claim({
    action: "release",
    work_id: c,
    expected_revision: 1,
    token: stale,
    reason: "Parent goal changed; no local result committed",
  });
  const reply = {
    op: "receive_handoff",
    client_ref: "reply",
    handoff_id: h,
    source_handle: f.source,
    title: "External reply",
    source_language: "en",
    comparison: "Original and current parent goals differ",
    disposition: "accepted",
    useful_content: "Retain useful analysis",
    accepted_wait_ids: [],
  };
  assert.throws(() => f.send([reply], [c]), /late\/unrelated/);
  const receipt = f.send([{ ...reply, disposition: "late" }], [c]);
  assert.equal(
    (f.row(receipt.created.reply).data.handoff_reply as { stale: boolean })
      .stale,
    true,
  );
  const fresh = f.claim(c);
  assert.throws(
    () =>
      f.send(
        [
          {
            op: "record_result",
            client_ref: "x",
            work_ref: { id: c },
            title: "Suppressed execution",
            content: "No execution under final parent pause",
            source_language: "en",
          },
          {
            op: "transition_work",
            ref: { id: p },
            status: "paused",
            reason: "Pause in same linked batch",
            decision_source_handle: f.source,
          },
        ],
        [c, p],
        [fresh],
      ),
    /final linked plan/,
  );
  f.disk.close();
});

test("step addresses cannot collide with internal parent/completion graph nodes", () => {
  const f = setup();
  const id = f.send([
    f.create("address-test", {
      ...base(),
      steps: [step("complete"), step("parent"), step("a:complete")],
    }),
  ]).created["address-test"];
  assert.equal(f.work(id).steps.length, 3);
  f.disk.close();
});

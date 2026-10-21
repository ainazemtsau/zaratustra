import test from "node:test";
import assert from "node:assert/strict";
import { mkdtempSync, readFileSync, writeFileSync, readdirSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { DatabaseSync } from "node:sqlite";
import { Core, CoreError, digest, canonical } from "../src/core/index.ts";
import type { AddressedRow, RecordRow, JsonObject } from "../src/core/index.ts";
import { DiskStorage } from "../src/storage/index.ts";

const ref = (client_ref: string) => ({ client_ref });
const error = (f: () => unknown, code: string) =>
  assert.throws(f, (e: unknown) => e instanceof CoreError && e.code === code);
function fixture(scopes: string[] = []) {
  const home = mkdtempSync(
    join(process.env.ZARATUSTRA_TEST_ROOT ?? tmpdir(), "zara-E1-"),
  );
  const disk = new DiskStorage(home);
  const core = new Core(disk, {
    ...disk.workspace,
    principal: "trusted-personal",
    session_id: "E1",
    runtime_id: "E1",
    processing_allowed: true,
    can_write: true,
    scopes,
  });
  let serial = 0;
  const source = core.capture(
    "Synthetic instruction, not Anton's feedback.",
    "rpc",
    "synthetic-E1",
  );
  const request = (ops: unknown[], ids: string[] = []) => ({
    request_id: "E1-" + ++serial,
    reason: "Synthetic experience contract test",
    source_handles: [source.source_handle],
    guards: ids.map((id) => ({
      ref: { id },
      expected_revision: read(id).revision,
    })),
    ops,
  });
  const commit = (ops: unknown[], ids: string[] = []) =>
    core.commit(request(ops, ids));
  const read = (id: string, revision?: number) =>
    core.read(id, revision).data as AddressedRow;
  const origin = commit([
    {
      op: "import_evidence",
      client_ref: "origin",
      source_handle: source.source_handle,
      title: "Original",
      source_language: "en",
    },
  ]).created.origin;
  const result = (run: string, text = "Exact result") =>
    commit([
      {
        op: "record_result",
        client_ref: "output",
        run_ref: { id: run },
        title: "Saved result",
        content: text,
        source_language: "en",
      },
    ]).created.output;
  const run = (key = "episode-" + ++serial, continuation_of: unknown = null) =>
    commit([
      {
        op: "start_run",
        client_ref: "run",
        title: "Meaningful synthetic episode",
        visibility: "workspace",
        episode_key: key,
        work_ref: null,
        mode: "conversation",
        continuation_of,
        summary: "Compute a concrete result",
        starting_refs: [{ id: origin }],
      },
    ]).created.run;
  return {
    home,
    disk,
    core,
    source,
    origin,
    request,
    commit,
    read,
    result,
    run,
  };
}
function method(client_ref: string, extra: JsonObject = {}) {
  return {
    op: "create_record",
    client_ref,
    kind: "method",
    title: "Lossless batch reconciliation",
    visibility: "workspace",
    data: {
      applicability: "Small synthetic line-item batches requiring exact totals",
      instructions:
        "Read each source row; preserve identifiers; calculate totals; report limitations.",
      input_contract: "Retained source rows",
      expected_output: "Addressed item list and checked total",
      context_requirements: [],
      dependencies: [],
      tool_requirements: ["read", "bash"],
      content_version: 1,
      state: "candidate",
      derived_from: [],
      limitations: "No proof of usefulness or causality",
      ...extra,
    },
  };
}
function invoke(
  f: ReturnType<typeof fixture>,
  run: string,
  methodId: string,
  key = "selected",
  extra: JsonObject = {},
) {
  const bundle = f.core.methodBundle(methodId).data;
  return f.commit([
    {
      op: "invoke_method",
      client_ref: "invocation",
      run_ref: { id: run },
      invocation_key: key,
      method_ref: bundle.root_ref,
      selected_versions: bundle.selected_versions,
      input_refs: [{ id: f.origin }],
      context_refs: [],
      bindings: { path: "synthetic/one" },
      parent_invocation_ref: null,
      ...extra,
    },
  ]).created.invocation;
}
const evaluation = (
  target: unknown,
  evidence: unknown,
  extra: JsonObject = {},
) => ({
  op: "record_evaluation",
  client_ref: "evaluation",
  target_ref: target,
  run_ref: null,
  assessment: "unhelpful",
  dimension: "usefulness",
  dimension_name: "Use of delivered text",
  basis: "reported_feedback",
  evidence_refs: [evidence],
  event_time: null,
  supersedes_evaluation_ref: null,
  explanation: "A synthetic controller reports a limitation; cause unknown",
  ...extra,
});
const domain = (d: DiskStorage) =>
  canonical(
    [
      "records",
      "revisions",
      "experience_rows",
      "experience_versions",
      "changes",
      "receipts",
      "memory_docs",
      "memory_text",
      "memory_names",
      "memory_meta",
    ].map((t) => d.all("SELECT * FROM " + t + " ORDER BY rowid")),
  );

test("E1 Method revision/content versions cannot be bypassed through ordinary updates; local variants and bindings stay independent", (t) => {
  const f = fixture();
  t.after(() => f.disk.close());
  const mid = f.commit([method("method")]).created.method;
  const update = (data: JsonObject, title?: string, body?: string) =>
    f.commit(
      [{ op: "update_record", ref: { id: mid }, data, title, body }],
      [mid],
    );
  update(f.read(mid).data, "Renamed method");
  assert.equal(f.read(mid).revision, 2);
  assert.equal(f.read(mid).data.content_version, 1);
  f.commit(
    [{ op: "set_method_state", ref: { id: mid }, state: "active" }],
    [mid],
  );
  assert.equal(f.read(mid).data.content_version, 1);
  const local = f.commit([method("local", { derived_from: [{ id: mid }] })])
    .created.local;
  const localBefore = canonical(f.read(local));
  for (const field of [
    "instructions",
    "applicability",
    "input_contract",
    "expected_output",
    "limitations",
  ]) {
    const old = f.read(mid);
    update({ ...old.data, [field]: "Changed " + field });
    assert.equal(
      f.read(mid).data.content_version,
      (old.data.content_version as number) + 1,
    );
  }
  let old = f.read(mid);
  update({ ...old.data, tool_requirements: ["read"] });
  assert.equal(
    f.read(mid).data.content_version,
    (old.data.content_version as number) + 1,
  );
  old = f.read(mid);
  update(old.data, undefined, "A changed safety qualification");
  assert.equal(
    f.read(mid).data.content_version,
    (old.data.content_version as number) + 1,
  );
  error(
    () => update({ ...f.read(mid).data, content_version: 1 }),
    "REVISION_CONFLICT",
  );
  assert.equal(canonical(f.read(local)), localBefore);
  assert.equal(
    (f.read(local).data.derived_from as { revision: number }[])[0].revision,
    3,
  );
  const r = f.run(),
    before = canonical(f.read(mid));
  invoke(f, r, mid, "one");
  invoke(f, r, mid, "two", { bindings: { path: "synthetic/two" } });
  assert.equal(canonical(f.read(mid)), before);
  assert.equal(
    (f.core.read(mid, undefined, undefined, undefined, 1).data as RecordRow)
      .data.content_version,
    1,
  );
  error(
    () => f.core.read(mid, 1, undefined, undefined, 2),
    "REFERENCE_TYPE_MISMATCH",
  );
  assert.ok(
    f.core
      .search({
        query: "safety qualification",
        match: "all",
        kinds: ["method"],
      })
      .data.cards.some((c) => c.id === mid),
  );
});

test("E1 full exact dependency closure survives updates; missing/extra/wrong selected versions and direct/final-batch cycles fail atomically", (t) => {
  const f = fixture();
  t.after(() => f.disk.close());
  const ids = f.commit([
    method("leaf"),
    method("middle", { dependencies: [ref("leaf")] }),
    method("root", { dependencies: [ref("middle")] }),
  ]).created;
  const bundle = f.core.methodBundle(ids.root).data;
  assert.equal(bundle.selected_versions.length, 3);
  const run = f.run();
  const invocation = invoke(f, run, ids.root);
  const initial = canonical(f.read(invocation));
  f.commit(
    [
      {
        op: "revise_method",
        ref: { id: ids.leaf },
        data: {
          ...f.read(ids.leaf).data,
          instructions: "Corrected leaf behavior",
        },
      },
    ],
    [ids.leaf],
  );
  assert.equal(canonical(f.read(invocation)), initial);
  assert.equal(
    (
      f.read(invocation).data.selected_versions as {
        id: string;
        content_version: number;
      }[]
    ).find((v) => v.id === ids.leaf)!.content_version,
    1,
  );
  const next = invoke(f, run, ids.root, "next");
  assert.equal(
    (
      f.read(next).data.selected_versions as {
        id: string;
        content_version: number;
      }[]
    ).find((v) => v.id === ids.leaf)!.content_version,
    2,
  );
  const before = domain(f.disk);
  error(
    () =>
      invoke(f, run, ids.root, "missing", {
        selected_versions: [bundle.root_ref],
      }),
    "VALIDATION_ERROR",
  );
  error(
    () => invoke(f, run, ids.root, "wrong", { input_refs: [{ id: ids.root }] }),
    "REFERENCE_TYPE_MISMATCH",
  );
  error(
    () => f.commit([method("self", { dependencies: [ref("self")] })]),
    "GRAPH_CYCLE",
  );
  error(
    () =>
      f.commit([
        method("a", { dependencies: [ref("b")] }),
        method("b", { dependencies: [ref("a")] }),
      ]),
    "GRAPH_CYCLE",
  );
  error(
    () =>
      f.commit(
        [
          {
            op: "update_record",
            ref: { id: ids.leaf },
            data: {
              ...f.read(ids.leaf).data,
              dependencies: [{ id: ids.root }],
            },
          },
        ],
        [ids.leaf],
      ),
    "GRAPH_CYCLE",
  );
  assert.equal(domain(f.disk), before);
  const page = f.core.methodBundle(ids.root, undefined, undefined, 1).data;
  assert.equal(page.cards.length, 1);
  assert.equal(page.has_more, true);
  const p2 = f.core.methodBundle(
    ids.root,
    undefined,
    undefined,
    1,
    page.next_cursor!,
  ).data;
  assert.notEqual(p2.cards[0].id, page.cards[0].id);
  const sub = invoke(f, run, ids.leaf, "dynamic", {
    parent_invocation_ref: { id: invocation },
  });
  assert.ok(f.read(sub));
  error(
    () =>
      invoke(f, run, ids.root, "recursive", {
        parent_invocation_ref: { id: sub },
      }),
    "GRAPH_CYCLE",
  );
});

test("E1 reading, selecting, reporting, observations, episode completion and Work acceptance remain distinct; retries share case identity", (t) => {
  const f = fixture();
  t.after(() => f.disk.close());
  const mid = f.commit([method("m")]).created.m;
  f.core.read(mid);
  assert.equal(f.core.browse("invocations").data.cards.length, 0);
  const r = f.run("same-key"),
    inv = invoke(f, r, mid);
  assert.equal(f.read(inv).data.reported_application, null);
  error(
    () =>
      f.commit(
        [
          {
            op: "finish_run",
            ref: { id: r },
            execution: "completed",
            summary: "Ended",
            result_refs: [],
          },
        ],
        [r],
      ),
    "INVALID_TRANSITION",
  );
  error(
    () =>
      f.commit(
        [
          {
            op: "report_application",
            ref: { id: inv },
            output_refs: [],
            observation_refs: [],
            reported_application: {
              applied: true,
              summary: "Read it",
              deviations: [],
            },
          },
        ],
        [inv],
      ),
    "VALIDATION_ERROR",
  );
  const output = f.result(r);
  f.commit(
    [
      {
        op: "report_application",
        ref: { id: inv },
        output_refs: [{ id: output }],
        observation_refs: [],
        reported_application: {
          applied: true,
          summary: "Model reports following it",
          deviations: [],
        },
      },
    ],
    [inv],
  );
  assert.deepEqual(f.read(inv).data.observation_refs, []);
  f.commit(
    [
      {
        op: "finish_run",
        ref: { id: r },
        execution: "completed",
        summary: "Episode ended, usefulness unknown",
        result_refs: [{ id: output }],
      },
    ],
    [r],
  );
  error(() => f.run("same-key"), "IDEMPOTENCY_CONFLICT");
  error(() => invoke(f, r, mid, "after-end"), "INVALID_TRANSITION");
  error(
    () =>
      f.commit(
        [
          {
            op: "update_record",
            ref: { id: r },
            data: { ...f.read(r).data, execution: "running" },
          },
        ],
        [r],
      ),
    "INVALID_TRANSITION",
  );
  const continuation = f.run("continued", { id: r, revision: 2 });
  assert.equal(f.read(continuation).data.case_id, f.read(r).data.case_id);
  assert.equal(f.core.browse("evaluations").data.cards.length, 0);
  const env = f.core.read((f.read(r).data.environment_ref as { id: string }).id)
    .data as AddressedRow;
  assert.equal(env.data.model, null);
});

test("E1 late and corrected Evaluations retain old result/version and history, never create a new case or automatic causal claim", (t) => {
  const f = fixture();
  t.after(() => f.disk.close());
  const r = f.run(),
    output = f.result(r),
    mid = f.commit([method("m")]).created.m;
  f.commit(
    [
      {
        op: "finish_run",
        ref: { id: r },
        execution: "failed",
        summary: "Known result did not meet a condition",
        result_refs: [{ id: output }],
      },
    ],
    [r],
  );
  f.commit(
    [
      {
        op: "revise_method",
        ref: { id: mid },
        data: { ...f.read(mid).data, instructions: "Revised after a failure" },
      },
    ],
    [mid],
  );
  const beforeRuns = f.core.browse("runs").data.cards.length;
  const e = f.commit([
    evaluation(
      { id: output, revision: 1 },
      { id: f.origin },
      { run_ref: { id: r, revision: 2 }, event_time: "2026-10-01T09:00:00Z" },
    ),
  ]).created.evaluation;
  const old = canonical(f.read(e));
  const correction = f.commit([
    evaluation(
      { id: output, revision: 1 },
      { id: f.origin },
      {
        assessment: "mixed",
        supersedes_evaluation_ref: { id: e, revision: 1 },
      },
    ),
  ]).created.evaluation;
  assert.equal(canonical(f.read(e)), old);
  assert.equal(
    (f.read(correction).data.target_ref as { id: string }).id,
    output,
  );
  assert.equal(f.core.browse("runs").data.cards.length, beforeRuns);
  error(
    () =>
      f.commit([
        evaluation(
          { id: mid, content_version: 2 },
          { id: f.origin },
          { supersedes_evaluation_ref: { id: correction } },
        ),
      ]),
    "REFERENCE_TYPE_MISMATCH",
  );
  error(
    () => f.commit([evaluation({ id: output }, { id: f.origin })]),
    "VALIDATION_ERROR",
  );
  error(
    () =>
      f.commit([
        evaluation(
          { id: output, revision: 1 },
          { id: f.origin },
          { basis: "test_result" },
        ),
      ]),
    "SOURCE_MISSING",
  );
  const observation = f.core.capture(
    "Synthetic check: failed condition",
    "tool",
    null,
    undefined,
    {
      tool_name: "bash",
      tool_call_id: "test-call",
      is_error: true,
      full_content_hash: digest("Synthetic check: failed condition"),
      truncated: false,
    },
  );
  const grounds = f.core.commit({
    ...f.request([]),
    source_handles: [observation.source_handle],
    ops: [
      {
        op: "import_evidence",
        client_ref: "tool",
        source_handle: observation.source_handle,
        title: "Observed check failure",
        source_language: "en",
      },
    ],
  }).created.tool;
  f.commit([
    evaluation(
      { id: output, revision: 1 },
      { id: grounds },
      {
        basis: "test_result",
        dimension: "technical_operation",
        dimension_name: "Exit outcome",
      },
    ),
  ]);
  assert.equal(f.read(r).data.execution, "failed");
});

test("E1 Signals keep independent reviews; consideration/edit/application never silently resolves a failure", (t) => {
  const f = fixture();
  t.after(() => f.disk.close());
  const mid = f.commit([method("m")]).created.m;
  const signal = f.commit([
    {
      op: "open_signal",
      client_ref: "signal",
      kind: "problem",
      subject_refs: [{ id: mid, content_version: 1 }],
      evidence_refs: [{ id: f.origin }],
      description: "A condition was missed; cause not established",
      next_check: null,
      visibility: "workspace",
    },
  ]).created.signal;
  const review = (extra: JsonObject) => ({
    op: "review_signal",
    client_ref: "review",
    ref: { id: signal },
    problem_state: "open",
    assessment: "Considered; diagnosis is a hypothesis",
    evidence_refs: [{ id: f.origin }],
    applied_change_ref: null,
    next_check: null,
    grounds: null,
    dismissal_reason: null,
    ...extra,
  });
  f.commit([review({})], [signal]);
  assert.equal(f.read(signal).data.problem_state, "open");
  assert.equal(f.core.browse("signal_reviews", signal).data.cards.length, 1);
  error(
    () => f.commit([review({ problem_state: "observing" })], [signal]),
    "VALIDATION_ERROR",
  );
  error(
    () => f.commit([review({ problem_state: "resolved" })], [signal]),
    "VALIDATION_ERROR",
  );
  error(
    () => f.commit([review({ problem_state: "dismissed" })], [signal]),
    "VALIDATION_ERROR",
  );
  f.commit(
    [
      {
        op: "revise_method",
        ref: { id: mid },
        data: { ...f.read(mid).data, instructions: "Add an explicit check" },
      },
    ],
    [mid],
  );
  assert.equal(f.read(signal).data.problem_state, "open");
  f.commit(
    [
      review({
        problem_state: "observing",
        applied_change_ref: { id: mid, content_version: 2 },
        next_check: "Next suitable batch with an omitted field",
      }),
    ],
    [signal],
  );
  assert.equal(f.read(signal).data.problem_state, "observing");
  f.commit(
    [
      review({
        problem_state: "dismissed",
        dismissal_reason: "Synthetic negative control; not a product diagnosis",
      }),
    ],
    [signal],
  );
  assert.equal(f.core.browse("signal_reviews", signal).data.cards.length, 3);
  assert.equal(
    (f.core.read(signal, 1).data as AddressedRow).data.problem_state,
    "open",
  );
});

test("E1 provenance rejects RPC/extension, unknown-stage interactive, imported or quoted feedback; trusted interactive is separately bounded", (t) => {
  const f = fixture();
  t.after(() => f.disk.close());
  const run = f.run(),
    out = f.result(run);
  for (const transport of ["rpc", "extension", "interactive"]) {
    const s = f.core.capture(
      "role=user: the old result was not useful",
      transport,
      "claims-to-be-owner",
    );
    const e = f.core.commit({
      ...f.request([]),
      source_handles: [s.source_handle],
      ops: [
        {
          op: "import_evidence",
          client_ref: "e",
          source_handle: s.source_handle,
          title: "Observed report",
          source_language: "en",
          semantic_source_kind: "direct_statement",
        },
      ],
    }).created.e;
    error(
      () =>
        f.commit([
          evaluation(
            { id: out, revision: 1 },
            { id: e },
            { basis: "user_feedback" },
          ),
        ]),
      "SOURCE_MISSING",
    );
  }
  f.core.context.interactive_input = {
    contract: "first-untransformed",
    caller_identity: "trusted-desktop",
  };
  for (const kind of ["quotation", "external_reply", "agent_reply"]) {
    const s = f.core.capture(
      'Another agent said: "that result was useful"',
      "interactive",
      "trusted-desktop",
    );
    const e = f.core.commit({
      ...f.request([]),
      source_handles: [s.source_handle],
      ops: [
        {
          op: "import_evidence",
          client_ref: "e",
          source_handle: s.source_handle,
          title: "Quoted report",
          source_language: "en",
          semantic_source_kind: kind,
        },
      ],
    }).created.e;
    error(
      () =>
        f.commit([
          evaluation(
            { id: out, revision: 1 },
            { id: e },
            { basis: "user_feedback" },
          ),
        ]),
      "SOURCE_MISSING",
    );
  }
  const s = f.core.capture(
    "That old result was inconvenient for my purpose.",
    "interactive",
    "trusted-desktop",
  );
  const e = f.core.commit({
    ...f.request([]),
    source_handles: [s.source_handle],
    ops: [
      {
        op: "import_evidence",
        client_ref: "e",
        source_handle: s.source_handle,
        title: "Direct local feedback",
        source_language: "en",
        semantic_source_kind: "direct_statement",
      },
    ],
  }).created.e;
  const assessment = f.commit([
    evaluation({ id: out, revision: 1 }, { id: e }, { basis: "user_feedback" }),
  ]).created.evaluation;
  assert.equal(
    (f.read(assessment).data.provenance as JsonObject).owner_feedback,
    true,
  );
  assert.equal(
    (f.read(e).data.provenance as JsonObject).original_keystrokes,
    false,
  );
});

test("E1 access covers primary/support/history/bundle/technical counts, guessed IDs and derived restriction without generation leaks", (t) => {
  const f = fixture(["restricted:read", "restricted:write"]);
  t.after(() => f.disk.close());
  const low = new Core(f.disk, {
    ...f.core.context,
    scopes: [],
    session_id: "low",
  });
  const before = JSON.stringify([
    low.map(),
    low.browse("evaluations"),
    low.browse("signals"),
    low.browse("invocations"),
    low.browse("history", f.origin),
    low.diagnostics(),
  ]);
  const secret = f.commit([{ ...method("secret"), visibility: "restricted" }])
    .created.secret;
  const r = f.run(),
    out = f.result(r),
    inv = invoke(f, r, secret);
  const e = f.commit([
    evaluation({ id: secret, content_version: 1 }, { id: f.origin }),
  ]).created.evaluation;
  const signal = f.commit([
    {
      op: "open_signal",
      client_ref: "s",
      kind: "problem",
      subject_refs: [{ id: e, revision: 1 }],
      evidence_refs: [{ id: f.origin }],
      description: "Hidden report",
      next_check: null,
      visibility: "workspace",
    },
  ]).created.s;
  for (const id of [secret, inv, e, signal]) {
    error(() => low.read(id), "REFERENCE_NOT_FOUND");
    error(() => low.read(id, 1), "REFERENCE_NOT_FOUND");
    error(() => low.browse("history", id), "REFERENCE_NOT_FOUND");
  }
  error(() => low.methodBundle(secret), "REFERENCE_NOT_FOUND");
  assert.equal(low.browse("evaluations").data.cards.length, 0);
  assert.equal(low.browse("signals").data.cards.length, 0);
  assert.equal(low.browse("invocations").data.cards.length, 0);
  const c = low.capture("A lower-scope report", "rpc", "synthetic-low");
  error(
    () =>
      low.commit({
        request_id: "guessed",
        reason: "Must not read hidden target",
        source_handles: [c.source_handle],
        guards: [],
        ops: [evaluation({ id: e, revision: 1 }, { id: f.origin })],
      }),
    "REFERENCE_NOT_FOUND",
  );
  assert.ok(!JSON.stringify(low.map()).includes(secret));
  assert.ok(!JSON.stringify(low.diagnostics()).includes(secret));
  // Public Run/result writes legitimately affect the public generation; hidden-only writes do not.
  assert.notEqual(JSON.stringify(low.map()), before);
  const generation = low.map().data.generation,
    seq = low.sequence();
  f.commit(
    [{ op: "set_method_state", ref: { id: secret }, state: "active" }],
    [secret],
  );
  assert.equal(low.map().data.generation, generation);
  assert.equal(low.sequence(), seq);
  assert.ok(out);
});

test("E1 linked records/support/versions/index/Change/receipt rollback together; stale guards and exact replay never duplicate", (t) => {
  for (const point of [
    "after_records",
    "after_index",
    "before_commit",
    "after_commit",
  ]) {
    const f = fixture();
    t.after(() => f.disk.close());
    const r = f.run(),
      out = f.result(r);
    const request = f.request([
      evaluation({ id: out, revision: 1 }, { id: f.origin }),
      {
        op: "open_signal",
        client_ref: "signal",
        kind: "problem",
        subject_refs: [ref("evaluation")],
        evidence_refs: [{ id: f.origin }],
        description: "Retained failure",
        next_check: null,
        visibility: "workspace",
      },
    ]);
    const before = domain(f.disk),
      c = new Core(f.disk, f.core.context, (p) => {
        if (p === point) throw new Error("injected " + point);
      });
    const source = c.capture("Exact request", "rpc", "synthetic-fault");
    request.source_handles = [source.source_handle];
    assert.throws(() => c.commit(request), /injected/);
    if (point !== "after_commit") assert.equal(domain(f.disk), before);
    const recovered = new Core(f.disk, c.context); // Replay after commit uses persisted source bindings despite expiry.
    if (point === "after_commit") {
      const replay = recovered.commit(request);
      assert.equal(replay.committed, true);
      assert.equal(
        f.disk.all("SELECT id FROM experience_rows WHERE kind='evaluation'")
          .length,
        1,
      );
      assert.deepEqual(recovered.commit(request), replay);
      error(
        () => recovered.commit({ ...request, reason: "Different intention" }),
        "IDEMPOTENCY_CONFLICT",
      );
    }
  }
});

test("E1 supporting history pages invalidate after change", (t) => {
  const f = fixture();
  t.after(() => f.disk.close());
  const r = f.run(),
    out = f.result(r);
  const e = f.commit([evaluation({ id: out, revision: 1 }, { id: f.origin })])
    .created.evaluation;
  for (let i = 0; i < 3; i++)
    f.commit([
      evaluation(
        { id: out, revision: 1 },
        { id: f.origin },
        { dimension_name: "Check " + i },
      ),
    ]);
  const page = f.core.browse("evaluations", undefined, 1);
  assert.equal(page.data.has_more, true);
  f.commit([
    evaluation(
      { id: out, revision: 1 },
      { id: f.origin },
      { dimension_name: "Newest" },
    ),
  ]);
  error(
    () => f.core.browse("evaluations", undefined, 1, page.data.next_cursor!),
    "CURSOR_INVALIDATED",
  );
  assert.equal((f.core.read(e).data as AddressedRow).revision, 1);
});

test("E1 open-Signal snapshot routes a bounded prefix with an explicit catalog continuation", (t) => {
  const f = fixture();
  t.after(() => f.disk.close());
  f.commit(
    Array.from({ length: 8 }, (_, i) => ({
      op: "open_signal",
      client_ref: "signal-" + i,
      kind: "problem",
      subject_refs: [{ id: f.origin }],
      evidence_refs: [{ id: f.origin }],
      description: "Unresolved synthetic issue " + i,
      next_check: null,
      visibility: "workspace",
    })),
  );
  const snapshot = f.core.snapshot();
  assert.equal(snapshot.open_signals.length, 5);
  assert.equal(snapshot.open_signals_has_more, true);
  assert.equal(snapshot.incomplete, true);
  assert.deepEqual(snapshot.open_signals_selector, { view: "signals" });
  assert.ok(Buffer.byteLength(JSON.stringify(snapshot)) <= 12288);
  const ids: string[] = [];
  let cursor: string | undefined;
  do {
    const page = f.core.browse("signals", undefined, 3, cursor).data;
    ids.push(...page.cards.map((row) => (row as { id: string }).id));
    cursor = page.next_cursor ?? undefined;
  } while (cursor);
  assert.equal(new Set(ids).size, 8);
});

test("E1 correction Run outcomes can pin changed Method and review versions; invocation outputs remain Evidence", (t) => {
  const f = fixture();
  t.after(() => f.disk.close());
  const mid = f.commit([method("m")]).created.m,
    run = f.run();
  const signal = f.commit([
    {
      op: "open_signal",
      client_ref: "signal",
      kind: "correction",
      subject_refs: [{ id: mid, content_version: 1 }],
      evidence_refs: [{ id: f.origin }],
      description: "A bounded textual correction",
      next_check: null,
      visibility: "workspace",
    },
  ]).created.signal;
  const review = f.commit(
    [
      {
        op: "revise_method",
        ref: { id: mid },
        data: {
          ...f.read(mid).data,
          instructions: "Clarified preflight without evidence of improvement",
        },
      },
      {
        op: "review_signal",
        client_ref: "review",
        ref: { id: signal },
        problem_state: "observing",
        assessment: "Changed content; verification still pending",
        evidence_refs: [{ id: f.origin }],
        applied_change_ref: { id: mid, content_version: 2 },
        next_check: "Next relevant case",
        grounds: null,
        dismissal_reason: null,
      },
    ],
    [mid, signal],
  ).created.review;
  f.commit(
    [
      {
        op: "finish_run",
        ref: { id: run },
        execution: "completed",
        summary: "Correction episode ended; no application or benefit asserted",
        result_refs: [
          { id: mid, content_version: 2 },
          { id: review, revision: 1 },
        ],
      },
    ],
    [run],
  );
  const refs = f.read(run).data.result_refs as {
    id: string;
    revision: number;
    content_version?: number;
  }[];
  assert.equal(refs[0].content_version, 2);
  assert.equal(refs[1].id, review);
  assert.equal(f.read(signal).data.problem_state, "observing");
  error(() => f.core.browse("records", review), "VALIDATION_ERROR");
  assert.equal(f.read(review).kind, "signal_review");
});

test("E1 navigation links resolve exact Method and supporting review refs with guards and access; typed derivation is not duplicated", (t) => {
  const f = fixture();
  t.after(() => f.disk.close());
  const mid = f.commit([method("m")]).created.m,
    run = f.run(),
    out = f.result(run);
  const signal = f.commit([
    {
      op: "open_signal",
      client_ref: "signal",
      kind: "problem",
      subject_refs: [{ id: out }],
      evidence_refs: [{ id: f.origin }],
      description: "A grounded open issue",
      next_check: null,
      visibility: "workspace",
    },
  ]).created.signal;
  const review = f.commit(
    [
      {
        op: "review_signal",
        client_ref: "review",
        ref: { id: signal },
        problem_state: "open",
        assessment: "Considered, still open",
        evidence_refs: [{ id: f.origin }],
        applied_change_ref: null,
        next_check: "Await actual grounds",
        grounds: null,
        dismissal_reason: null,
      },
    ],
    [signal],
  ).created.review;
  const receipt = f.commit(
    [
      {
        op: "put_relation",
        client_ref: "method",
        relation: "derived_from",
        from_ref: { id: out },
        to_ref: { id: mid, content_version: 1 },
        reason: "Summary cites the exact recipe, not an application claim",
      },
      {
        op: "put_relation",
        client_ref: "review",
        relation: "related",
        from_ref: { id: out },
        to_ref: { id: review, revision: 1 },
        reason: "Directly open the existing consideration",
      },
    ],
    [out, mid, review],
  );
  const links = f.core.browse("relations", out).data.cards as unknown as {
    to_ref: { id: string; revision: number; content_version?: number };
  }[];
  assert.equal(links.length, 2);
  assert.equal(
    links.find((v) => v.to_ref.id === mid)!.to_ref.content_version,
    1,
  );
  assert.equal(links.find((v) => v.to_ref.id === review)!.to_ref.revision, 1);
  f.commit(
    [
      { op: "remove_relation", relation_id: receipt.created.method },
      { op: "remove_relation", relation_id: receipt.created.review },
    ],
    [out, mid, review],
  );
  assert.equal(f.core.browse("relations", out).data.cards.length, 0);
  const local = f.commit([method("local", { derived_from: [{ id: mid }] })])
    .created.local;
  error(
    () =>
      f.commit(
        [
          {
            op: "put_relation",
            client_ref: "duplicate",
            relation: "derived_from",
            from_ref: { id: local },
            to_ref: { id: mid },
            reason: "Must not duplicate canonical lineage",
          },
        ],
        [local, mid],
      ),
    "VALIDATION_ERROR",
  );
});

test("E1 request-local Work premises route current Method versions without rewriting the historical context", (t) => {
  const f = fixture();
  t.after(() => f.disk.close());
  const mid = f.commit([method("m")]).created.m;
  const work = f.commit([
    {
      op: "create_record",
      client_ref: "work",
      kind: "work",
      title: "Waiting for source",
      visibility: "workspace",
      data: {
        activity_id: null,
        parent_work_id: null,
        objective: "Inspect a future supported source",
        acceptance: [
          {
            criterion_id: "result",
            description: "Grounded result",
            verification: "Inspect actual output",
            required: true,
          },
        ],
        status: "waiting",
        current_state: "Source awaited",
        next_action: null,
        steps: [],
        waits: [
          {
            wait_id: "source",
            kind: "user",
            target: "work",
            subject: "Source",
            satisfied_by: "Readable source received",
            received_refs: [],
            question: "Send the source",
          },
        ],
        context_refs: [{ id: mid, revision: 1, content_version: 1 }],
        completion: null,
      },
    },
  ]).created.work;
  f.commit(
    [
      {
        op: "revise_method",
        ref: { id: mid },
        data: {
          ...f.read(mid).data,
          instructions: "Current corrected instructions",
        },
      },
    ],
    [mid],
  );
  const snapshot = f.core.snapshot(),
    premise = snapshot.context_current.find((ref) => ref.id === mid)!;
  assert.equal(premise.content_version, 2);
  assert.equal(premise.historical_content_version, 1);
  assert.equal(premise.must_read, true);
  assert.equal(
    (f.read(work).data.context_refs as { content_version: number }[])[0]
      .content_version,
    1,
  );
});

test("E1 stale guards, invocation output types, complete selection and start replay are enforced", (t) => {
  const f = fixture();
  t.after(() => f.disk.close());
  const ids = f.commit([method("m"), method("other")]).created;
  const start = f.request([
    {
      op: "start_run",
      client_ref: "run",
      title: "Replay target",
      visibility: "workspace",
      episode_key: "replay-key",
      work_ref: null,
      mode: "conversation",
      continuation_of: null,
      summary: "One substantive episode",
      starting_refs: [{ id: f.origin }],
    },
  ]);
  const receipt = f.core.commit(start);
  assert.deepEqual(f.core.commit(start), receipt);
  const run = receipt.created.run,
    inv = invoke(f, run, ids.m);
  error(() => invoke(f, run, ids.m), "IDEMPOTENCY_CONFLICT");
  const bundle = f.core.methodBundle(ids.m).data,
    other = f.core.methodBundle(ids.other).data;
  error(
    () =>
      invoke(f, run, ids.m, "extra", {
        selected_versions: [
          ...bundle.selected_versions,
          ...other.selected_versions,
        ],
      }),
    "VALIDATION_ERROR",
  );
  const stale = f.request(
    [{ op: "set_method_state", ref: { id: ids.m }, state: "active" }],
    [ids.m],
  );
  f.commit(
    [{ op: "set_method_state", ref: { id: ids.m }, state: "deprecated" }],
    [ids.m],
  );
  const before = domain(f.disk);
  error(() => f.core.commit(stale), "REVISION_CONFLICT");
  assert.equal(domain(f.disk), before);
  error(
    () =>
      f.commit(
        [
          {
            op: "report_application",
            ref: { id: inv },
            output_refs: [{ id: ids.m }],
            observation_refs: [],
            reported_application: {
              applied: true,
              summary: "Invalid output type",
              deviations: [],
            },
          },
        ],
        [inv],
      ),
    "REFERENCE_TYPE_MISMATCH",
  );
  error(
    () =>
      f.commit(
        [
          {
            op: "report_application",
            ref: { id: inv },
            output_refs: [{ id: f.origin }],
            observation_refs: [{ id: f.origin }],
            reported_application: {
              applied: true,
              summary: "A quoted claim is not a technical receipt",
              deviations: [],
            },
          },
        ],
        [inv],
      ),
    "REFERENCE_TYPE_MISMATCH",
  );
});

test("E1 a new result and its exact Evaluation/application/Signal commit atomically through client refs", (t) => {
  for (const point of [
    "after_records",
    "after_index",
    "before_commit",
    "after_commit",
  ]) {
    const f = fixture();
    t.after(() => f.disk.close());
    const mid = f.commit([method("m")]).created.m,
      run = f.run(),
      inv = invoke(f, run, mid);
    const source = f.core.capture(
      "Arithmetic tool observed a concrete check",
      "tool",
      null,
      undefined,
      {
        tool_name: "bash",
        tool_call_id: "observed-atomic",
        is_error: false,
        full_content_hash: digest("Arithmetic tool observed a concrete check"),
        truncated: false,
      },
    );
    const obs = f.core.commit({
      ...f.request([]),
      source_handles: [source.source_handle],
      ops: [
        {
          op: "import_evidence",
          client_ref: "obs",
          source_handle: source.source_handle,
          title: "Actual hook fixture",
          source_language: "en",
        },
      ],
    }).created.obs;
    const request = f.request(
      [
        {
          op: "record_result",
          client_ref: "output",
          run_ref: { id: run },
          title: "Atomic output",
          content: "Checked output",
          source_language: "en",
        },
        {
          op: "report_application",
          ref: { id: inv },
          output_refs: [ref("output")],
          observation_refs: [{ id: obs }],
          reported_application: {
            applied: true,
            summary: "Reported with observed grounds",
            deviations: [],
          },
        },
        {
          op: "finish_run",
          ref: { id: run },
          execution: "completed",
          summary: "Ended with addressed output",
          result_refs: [ref("output")],
        },
        evaluation(
          ref("output"),
          { id: obs },
          {
            basis: "test_result",
            dimension: "criterion",
            dimension_name: "Local check",
            run_ref: { id: run, revision: 2 },
          },
        ),
        {
          op: "open_signal",
          client_ref: "signal",
          kind: "useful_result",
          subject_refs: [ref("evaluation")],
          evidence_refs: [{ id: obs }],
          description: "A local check, no general usefulness claim",
          next_check: null,
          visibility: "workspace",
        },
      ],
      [run, inv],
    );
    const c = new Core(f.disk, f.core.context, (p) => {
      if (p === point) throw new Error("atomic E1 fault");
    });
    const s = c.capture("Atomic result save", "rpc", "synthetic");
    request.source_handles = [s.source_handle];
    const before = domain(f.disk);
    assert.throws(() => c.commit(request), /atomic E1 fault/);
    if (point !== "after_commit") assert.equal(domain(f.disk), before);
    else {
      const replay = new Core(f.disk, c.context).commit(request);
      const e = f.read(replay.created.evaluation);
      assert.deepEqual(e.data.target_ref, {
        id: replay.created.output,
        revision: 1,
      });
      assert.equal(f.read(run).data.execution, "completed");
      assert.equal(
        (f.read(inv).data.output_refs as { id: string }[])[0].id,
        replay.created.output,
      );
    }
  }
});

test("E1 historical protected refs cannot be selected through a currently public Method", (t) => {
  const f = fixture(["restricted:read", "restricted:write"]);
  t.after(() => f.disk.close());
  const secret = f.commit([{ ...method("secret"), visibility: "restricted" }])
    .created.secret;
  const methodId = f.commit([
    method("history", {
      context_requirements: [
        {
          description: "Protected premise",
          refs: [{ id: secret }],
          selector: null,
          retrieval: "Read the exact premise",
        },
      ],
    }),
  ]).created.history;
  f.commit(
    [
      {
        op: "revise_method",
        ref: { id: methodId },
        data: { ...f.read(methodId).data, context_requirements: [] },
      },
    ],
    [methodId],
  );
  const low = new Core(f.disk, {
    ...f.core.context,
    scopes: [],
    session_id: "lower",
  });
  assert.equal((low.read(methodId).data as RecordRow).data.content_version, 2);
  error(() => low.read(methodId, 1), "REFERENCE_NOT_FOUND");
  error(() => low.methodBundle(methodId, 1), "REFERENCE_NOT_FOUND");
  const r = f.run();
  const source = low.capture(
    "Programmatic old-version selection",
    "rpc",
    "test",
  );
  error(
    () =>
      low.commit({
        request_id: "historical-selection",
        reason: "Must not bypass protected history",
        source_handles: [source.source_handle],
        guards: [],
        ops: [
          {
            op: "invoke_method",
            client_ref: "inv",
            run_ref: { id: r },
            invocation_key: "old",
            method_ref: { id: methodId, content_version: 1 },
            selected_versions: [{ id: methodId, content_version: 1 }],
            input_refs: [{ id: f.origin }],
            context_refs: [],
            bindings: {},
            parent_invocation_ref: null,
          },
        ],
      }),
    "PERMISSION_DENIED",
  );
  assert.equal(low.browse("invocations").data.cards.length, 0);
});

test("E1 schema-3 upgrade faults preserve filled canonical rows and material bytes with a verified backup", (t) => {
  for (const point of [
    "experience_after_backup",
    "experience_before_schema_commit",
    "experience_after_schema_commit",
  ]) {
    const f = fixture();
    const path = join(f.home, "original.md"),
      bytes = Buffer.from(
        "\ufeff# Original 🦉\r\nRetain exact material bytes.\r\n",
      );
    writeFileSync(path, bytes);
    const material = f.disk.importFile(path, [f.home]),
      source = f.core.capture(material.text, "file", null, material);
    f.core.commit({
      ...f.request([]),
      source_handles: [source.source_handle],
      ops: [
        {
          op: "import_evidence",
          client_ref: "material",
          source_handle: source.source_handle,
          title: "Original material",
          source_language: "en",
        },
      ],
    });
    const tables = [
      "records",
      "revisions",
      "changes",
      "receipts",
      "intents",
      "claims",
      "handoffs",
      "focus",
    ];
    const before = canonical(
      tables.map((table) =>
        f.disk.all("SELECT * FROM " + table + " ORDER BY rowid"),
      ),
    );
    f.disk.exec(
      "DROP INDEX intent_kind; DROP VIEW addressed_current; DROP VIEW addressed_versions; DROP INDEX run_episode_key; DROP INDEX method_content_version; DROP TABLE experience_rows; DROP TABLE experience_versions; PRAGMA user_version=3",
    );
    f.disk.workspace.schema_version = 3;
    f.disk.run("UPDATE meta SET json=?", JSON.stringify(f.disk.workspace));
    writeFileSync(
      join(f.home, "workspace.json"),
      JSON.stringify(f.disk.workspace),
    );
    f.disk.close();
    assert.throws(
      () =>
        new DiskStorage(f.home, (p) => {
          if (p === point) throw new Error("E1 migration interruption");
        }),
      /interruption/,
    );
    const recovered = new DiskStorage(f.home);
    t.after(() => recovered.close());
    assert.equal(recovered.workspace.schema_version, 6);
    assert.equal(
      canonical(
        tables.map((table) =>
          recovered.all("SELECT * FROM " + table + " ORDER BY rowid"),
        ),
      ),
      before,
    );
    assert.deepEqual(
      readFileSync(join(f.home, "materials", material.blob_ref)),
      bytes,
    );
    const receipt = JSON.parse(
      recovered.get<{ json: string }>(
        "SELECT json FROM migrations WHERE version=4",
      )!.json,
    );
    assert.equal(digest(readFileSync(receipt.backup)), receipt.backup_sha256);
    assert.ok(
      readdirSync(f.home).some((name) => name.startsWith("pre-schema-4-")),
    );
    const old = new DatabaseSync(receipt.backup, { readOnly: true });
    assert.equal(
      (old.prepare("PRAGMA user_version").get() as { user_version: number })
        .user_version,
      3,
    );
    old.close();
  }
});

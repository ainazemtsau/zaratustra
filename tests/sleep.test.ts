import test from "node:test";
import assert from "node:assert/strict";
import {
  mkdtempSync,
  readFileSync,
  writeFileSync,
  readdirSync,
  renameSync,
} from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { Core, CoreError, canonical, digest } from "../src/core/index.ts";
import type {
  AddressedRow,
  CallContext,
  JsonObject,
} from "../src/core/index.ts";
import {
  Administration,
  DiskStorage,
  activeLocation,
} from "../src/storage/index.ts";
import { DatabaseSync } from "node:sqlite";

const ref = (client_ref: string) => ({ client_ref });
const fail = (f: () => unknown, code: string) =>
  assert.throws(f, (e: unknown) => e instanceof CoreError && e.code === code);
const work = (client_ref: string, activity: string | null = null) => ({
  op: "create_record",
  kind: "work",
  client_ref,
  title: "Synthetic review",
  visibility: "workspace",
  data: {
    activity_id: activity ? { id: activity } : null,
    parent_work_id: null,
    objective: "Review retained grounds",
    acceptance: [
      {
        criterion_id: "review",
        description: "Frozen inputs considered or deferred",
        verification: "Inspect committed dispositions",
        required: true,
      },
    ],
    status: "active",
    current_state: "Review requested",
    next_action: "Read prepared batch",
    steps: [],
    waits: [],
    context_refs: [],
    completion: null,
  },
});
function fixture(scopes: string[] = ["restricted:read", "restricted:write"]) {
  const root = mkdtempSync(
      join(
        process.env.ZARATUSTRA_TEST_ROOT ?? tmpdir(),
        "zara-synthetic-sleep-",
      ),
    ),
    home = join(root, "home"),
    backups = join(root, "backups");
  const disk = new DiskStorage(home);
  const ctx: CallContext = {
    ...disk.workspace,
    principal: "trusted-personal",
    session_id: "sleep-test",
    runtime_id: "A",
    can_write: true,
    processing_allowed: true,
    scopes,
    approval_principal: "synthetic-controller:sleep",
  };
  let core = new Core(disk, ctx),
    serial = 0;
  let source = core.capture(
    "Synthetic review and feedback. Not owner testimony.",
    "rpc",
    "registered-synthetic-controller",
  );
  const read = (id: string, revision?: number) =>
    core.read(id, revision).data as AddressedRow;
  const request = (ops: unknown[], ids: string[] = []) => ({
    request_id: "sleep-test-" + ++serial,
    reason: "Synthetic Sleep qualification",
    source_handles: [source.source_handle],
    guards: [...new Set(ids)].map((id) => ({
      ref: { id },
      expected_revision: read(id).revision,
    })),
    ops,
  });
  const commit = (ops: unknown[], ids: string[] = []) =>
    core.commit(request(ops, ids));
  const evidence = (
    title = "Retained synthetic grounds",
    visibility = "workspace",
  ) =>
    commit([
      {
        op: "import_evidence",
        client_ref: "e",
        source_handle: source.source_handle,
        title,
        source_language: "en",
        visibility,
      },
    ]).created.e;
  const start = (activity: string | null = null) =>
    commit([
      work("w", activity),
      {
        op: "start_run",
        client_ref: "r",
        title: "Explicit synthetic Sleep episode",
        visibility: "workspace",
        episode_key: "review-" + ++serial,
        work_ref: ref("w"),
        mode: "sleep",
        continuation_of: null,
        summary: "Review frozen retained inputs; no success claimed",
        starting_refs: [],
      },
      { op: "start_sleep", work_ref: ref("w"), run_ref: ref("r") },
    ]).created.r;
  const batch = (id: string) =>
    core.sleepBatch(id) as {
      status: string;
      batch_id: string;
      cards: {
        item_id: string;
        ref: { id: string; revision: number };
        input: string;
        current_revision: number;
        prior_disposition: unknown;
      }[];
      has_more: boolean;
    };
  const checkpoint = (
    id: string,
    changes: unknown[] = [],
    disposition: JsonObject = {},
  ) => {
    const b = batch(id);
    return request(
      [
        ...changes,
        {
          op: "sleep_checkpoint",
          run_ref: { id },
          batch_id: b.batch_id,
          dispositions: b.cards.map((c, i) => ({
            item_id: c.item_id,
            disposition: "considered",
            reason: "Original grounds inspected; no supported improvement",
            continuation: null,
            evidence_refs: [],
            change_refs: [],
            expected_benefit: null,
            limits: null,
            next_check: null,
            check_signal_ref: null,
            ...(i === 0 ? disposition : {}),
          })),
        },
      ],
      b.cards.map((c) => c.ref.id),
    );
  };
  const finish = (id: string) => {
    const seen: string[] = [];
    while (batch(id).status === "active") {
      seen.push(...batch(id).cards.map((c) => c.ref.id));
      core.commit(checkpoint(id));
    }
    return seen;
  };
  return {
    root,
    home,
    backups,
    disk,
    ctx,
    get core() {
      return core;
    },
    request,
    commit,
    read,
    evidence,
    start,
    batch,
    checkpoint,
    finish,
    rebind: (newCore: Core) => {
      core = newCore;
      source = core.capture(
        "Synthetic continuation, no old transcript.",
        "rpc",
        "registered-synthetic-controller",
      );
    },
  };
}
const evaluation = (target: string, revision: number, e: string) => ({
  op: "record_evaluation",
  client_ref: "evaluation",
  target_ref: { id: target, revision },
  run_ref: null,
  assessment: "unhelpful",
  dimension: "usefulness",
  dimension_name: "Synthetic reported limitation",
  basis: "reported_feedback",
  evidence_refs: [{ id: e }],
  event_time: "2020-01-01T00:00:00Z",
  supersedes_evaluation_ref: null,
  explanation:
    "Late feedback on an old exact result; causal explanation unknown",
});
const method = (e: string) => ({
  op: "create_record",
  kind: "method",
  client_ref: "m",
  title: "Synthetic source check",
  visibility: "workspace",
  data: {
    applicability: "Synthetic line items",
    instructions: "Read retained source items",
    input_contract: "Addressed sources",
    expected_output: "Grounded answer",
    context_requirements: [
      {
        description: "Read source",
        refs: [{ id: e }],
        selector: null,
        retrieval: "Read exact retained grounds",
      },
    ],
    dependencies: [],
    tool_requirements: [],
    content_version: 1,
    state: "candidate",
    derived_from: [],
    limitations: "Usefulness unverified",
  },
});
const signal = (e: string, target: unknown) => ({
  op: "open_signal",
  client_ref: "s",
  kind: "problem",
  subject_refs: [target],
  evidence_refs: [{ id: e }],
  description: "Synthetic omission; cause unknown",
  next_check: "Next suitable real case",
  visibility: "workspace",
});
function grant(core: Core, ref: string) {
  const p = core.approvals.present(ref);
  core.approvals.answer(p.token, true, {
    source_ref: "synthetic-decision",
    transport: "native-dialog",
    channel_identity: "registered-synthetic-controller",
    stage: "pi-confirm-return",
  });
}

test("Sleep disk frozen membership includes late old-case feedback, open Signals and deferrals behind separate progress; no bookkeeping recursion or automatic new cycle", (t) => {
  const f = fixture();
  t.after(() => f.disk.close());
  const e = f.evidence(),
    m = f.commit([method(e)]).created.m;
  const s = f.commit([signal(e, { id: m })]).created.s;
  const first = f.start();
  assert.equal(f.batch(first).cards.length, 3);
  const deferred = f.checkpoint(first, [], {
    disposition: "deferred",
    reason: "Await addressed external evidence",
    continuation: "Read exact original source when revised",
    next_check: "New source revision",
  });
  f.core.commit(deferred);
  assert.equal(f.batch(first).status, "completed");
  const late = f.commit([evaluation(m, 1, e)]).created.evaluation;
  const second = f.start();
  const cards = f.batch(second).cards;
  assert.ok(cards.some((c) => c.ref.id === late));
  assert.ok(cards.some((c) => c.ref.id === s));
  assert.ok(
    cards.some(
      (c) => c.ref.id === e && c.input === "deferred" && c.prior_disposition,
    ),
  );
  const arrival = f.evidence("Arrived after frozen membership");
  assert.ok(!f.finish(second).includes(arrival));
  assert.equal(f.read(s).data.problem_state, "open");
  const third = f.start();
  assert.ok(f.finish(third).includes(arrival));
  const fourth = f.start();
  const fourthIds = f.finish(fourth);
  assert.deepEqual(fourthIds, [s]);
  assert.equal(f.disk.all("SELECT * FROM sleep_reviews").length, 4);
});

test("Sleep disk exact batch membership, stale guards, fault atomicity, replay and changed-payload conflict", (t) => {
  const f = fixture();
  t.after(() => f.disk.close());
  const e = f.evidence(),
    m = f.commit([method(e)]).created.m,
    run = f.start();
  const original = f.batch(run),
    request = f.checkpoint(run);
  f.commit(
    [
      {
        op: "update_record",
        ref: { id: m },
        title: "New relevant revision",
        data: f.read(m).data,
      },
    ],
    [m],
  );
  fail(() => f.core.commit(request), "REVISION_CONFLICT");
  assert.equal(f.batch(run).batch_id, original.batch_id);
  const invalid = f.checkpoint(run);
  (invalid.ops.at(-1) as { dispositions: unknown[] }).dispositions.pop();
  fail(() => f.core.commit(invalid), "VALIDATION_ERROR");
  const data = {
    ...f.read(m).data,
    instructions: "Read retained source items and verify omissions",
  };
  const correction = f.checkpoint(
    run,
    [
      { op: "revise_method", ref: { id: m }, data },
      signal(e, { id: m, revision: 3 }),
    ],
    {
      disposition: "changed",
      evidence_refs: [{ id: e, revision: 1 }],
      change_refs: [{ id: m, revision: 3 }],
      expected_benefit: "Fewer omissions",
      limits: "May over-read; causal hypothesis unproven",
      next_check: "Next suitable line-item case",
      check_signal_ref: ref("s"),
    },
  );
  // Batch guard includes m's current revision even though its reviewed input is old.
  const before = canonical([
    f.disk.all("SELECT * FROM sleep_items"),
    f.read(m),
    f.disk.all("SELECT * FROM receipts"),
  ]);
  const faulty = new Core(f.disk, f.ctx, (p) => {
    if (p === "after_index") throw Error("Synthetic all-or-none fault");
  });
  f.rebind(faulty);
  const retry = { ...correction, source_handles: f.request([]).source_handles };
  assert.throws(() => f.core.commit(retry), /Synthetic all-or-none/);
  assert.equal(
    canonical([
      f.disk.all("SELECT * FROM sleep_items"),
      f.read(m),
      f.disk.all("SELECT * FROM receipts"),
    ]),
    before,
  );
  f.rebind(new Core(f.disk, f.ctx));
  const valid = {
    ...correction,
    request_id: "after-fault-new-source",
    source_handles: f.request([]).source_handles,
  };
  const receipt = f.core.commit(valid);
  assert.equal(f.read(m).data.content_version, 2);
  assert.deepEqual(f.core.commit(valid), receipt);
  fail(
    () => f.core.commit({ ...valid, reason: "Changed payload" }),
    "IDEMPOTENCY_CONFLICT",
  );
  assert.ok(f.core.browse("operations").data);
  assert.equal(f.batch(run).status, "completed");
});

test("Sleep disk fresh-process read-only continuation, empty review and explicit abort preserve finite remainder", (t) => {
  const f = fixture();
  t.after(() => f.disk.close());
  const empty = f.start();
  assert.equal(f.batch(empty).status, "completed");
  for (let i = 0; i < 13; i++) f.evidence("Synthetic event " + i);
  const run = f.start(),
    batch = f.batch(run);
  assert.equal(batch.cards.length, 10);
  assert.equal(batch.has_more, true);
  const readonly = new DiskStorage(f.home);
  const observer = new Core(readonly, { ...f.ctx, runtime_id: "read-only" });
  assert.deepEqual(observer.sleepBatch(run), f.core.sleepBatch(run));
  fail(() => observer.commit(f.checkpoint(run)), "READ_ONLY");
  readonly.close();
  f.disk.close();
  const nextDisk = new DiskStorage(f.home);
  t.after(() => nextDisk.close());
  f.rebind(new Core(nextDisk, { ...f.ctx, runtime_id: "fresh-no-transcript" }));
  assert.deepEqual(f.batch(run), batch);
  const request = f.checkpoint(run);
  (request.ops.at(-1) as JsonObject).abort = true;
  f.core.commit(request);
  assert.equal(f.batch(run).status, "aborted");
  const restarted = f.start();
  assert.equal(f.finish(restarted).length, 13);
  assert.equal(nextDisk.all("SELECT * FROM sleep_coverage").length, 1);
});

test("Sleep disk Activity/global coverage independent; origin never owns shared Knowledge/Method; exact approved atomic checkpoint works", (t) => {
  const f = fixture();
  t.after(() => f.disk.close());
  const activity = f.commit([
    {
      op: "create_record",
      kind: "activity",
      client_ref: "a",
      title: "Synthetic Activity",
      visibility: "workspace",
      data: { purpose: "Synthetic scope", status: "active" },
    },
  ]).created.a;
  const e = f.evidence(),
    m = f.commit([{ ...method(e), origin_activity_id: { id: activity } }])
      .created.m;
  const run = f.start(activity);
  const req = f.checkpoint(
    run,
    [
      {
        op: "revise_method",
        ref: { id: m },
        data: {
          ...f.read(m).data,
          instructions: "Verify each synthetic source",
        },
      },
      signal(e, { id: m, revision: 2 }),
    ],
    {
      disposition: "changed",
      evidence_refs: [{ id: e }],
      change_refs: [{ id: m, revision: 2 }],
      expected_benefit: "Avoid missing sources",
      limits: "Unproven, may add effort",
      next_check: "Suitable real case",
      check_signal_ref: ref("s"),
    },
  );
  fail(() => f.core.commit(req), "APPROVAL_REQUIRED");
  assert.equal(f.read(m).revision, 1);
  const p = f.core.prepareCommit(
    req,
    "Change the shared Method during Activity review",
    "Defer the shared change",
  );
  grant(f.core, p.request_id);
  f.core.commit({ ...req, preview_ref: p.request_id });
  assert.equal(f.read(m).data.content_version, 2);
  const global = f.start();
  const reviewed = f.finish(global);
  assert.ok(reviewed.includes(e));
  assert.equal(f.disk.all("SELECT * FROM sleep_coverage").length, 2);
});

test("Sleep disk restricted profiles, inherited restrictions and guessed review IDs do not leak counts, cursors or raw sequences", (t) => {
  const f = fixture();
  t.after(() => f.disk.close());
  const hidden = f.evidence("Restricted synthetic secret", "restricted");
  const protectedRun = f.start();
  const low = new Core(f.disk, { ...f.ctx, scopes: [], runtime_id: "low" });
  fail(() => low.sleepBatch(protectedRun), "REFERENCE_NOT_FOUND");
  const before = low.sleepBatch();
  f.evidence("Another hidden-only arrival", "restricted");
  assert.deepEqual(low.sleepBatch(), before);
  f.rebind(low);
  const lowRun = f.start();
  assert.equal(f.batch(lowRun).status, "completed");
  assert.ok(!JSON.stringify(low.sleepBatch(lowRun)).includes(hidden));
  assert.ok(!JSON.stringify(low.sleepBatch(lowRun)).includes("watermark"));
  f.rebind(
    new Core(f.disk, {
      ...f.ctx,
      scopes: ["restricted:read"],
      runtime_id: "read-profile",
    }),
  );
  const newlyPermitted = f.start();
  assert.ok(f.batch(newlyPermitted).cards.some((c) => c.ref.id === hidden));
});

test("Sleep disk schema-6 migration faults retain canonical bytes and verified backup; manifest repair is repeatable", (t) => {
  for (const point of [
    "sleep_after_backup",
    "sleep_before_schema_commit",
    "sleep_after_schema_commit",
  ]) {
    const f = fixture(),
      e = f.evidence();
    const rows = f.disk.all("SELECT * FROM records"),
      receipts = f.disk.all("SELECT * FROM receipts");
    f.disk.close();
    // Mechanical preparation of an exact schema-6 predecessor shape; no Sleep rows exist.
    const db = new DatabaseSync(join(f.home, "zara.sqlite"));
    const metadata = { ...f.ctx, schema_version: 6 };
    const workspace = {
      workspace_id: metadata.workspace_id,
      epoch: metadata.epoch,
      schema_version: 6,
    };
    db.exec(
      "DROP TABLE sleep_items; DROP TABLE sleep_reviews; DROP TABLE sleep_coverage; PRAGMA user_version=6;",
    );
    db.prepare("UPDATE meta SET json=?").run(JSON.stringify(workspace));
    db.close();
    writeFileSync(join(f.home, "workspace.json"), JSON.stringify(workspace));
    assert.throws(
      () =>
        new DiskStorage(f.home, (p) => {
          if (p === point) throw Error(point);
        }),
      new RegExp(point),
    );
    assert.ok(readdirSync(f.home).some((p) => p.startsWith("pre-schema-7-")));
    const migrated = new DiskStorage(f.home);
    t.after(() => migrated.close());
    assert.equal(migrated.workspace.schema_version, 7);
    assert.deepEqual(migrated.all("SELECT * FROM records"), rows);
    assert.deepEqual(migrated.all("SELECT * FROM receipts"), receipts);
    assert.ok(migrated.get("SELECT id FROM records WHERE id=?", e));
    migrated.close();
    const reopened = new DiskStorage(f.home);
    reopened.close();
  }
});

test("Sleep disk schema-7 backup progress/deferred roundtrip, retention pin, new epoch invalidation and E3 barriers stay intact", async (t) => {
  const f = fixture();
  t.after(() => f.disk.close());
  const e = f.evidence(),
    run = f.start();
  f.core.commit(
    f.checkpoint(run, [], {
      disposition: "deferred",
      reason: "Await a named source check",
      continuation: "Re-read this exact source",
      next_check: "Next requested review",
    }),
  );
  const pending = f.start();
  const itemCount = f.disk.all("SELECT * FROM sleep_items").length;
  fail(
    () =>
      f.core.storagePreview(
        { action: "tombstone", targets: [{ id: e, revision: 1 }] },
        "Delete source",
        "Keep",
      ),
    "DEPENDENCY_UNSATISFIED",
  );
  const admin = new Administration(f.home, f.backups, f.ctx);
  const backup = await admin.backup(f.disk);
  assert.equal(backup.complete, true);
  const preview = admin.restorePreview(
    backup.backup,
    "Restore isolated fixture",
    "Keep active fixture",
  );
  const p = admin.approvals.present(preview.preview.request_id);
  admin.approvals.answer(p.token, true, {
    source_ref: "synthetic",
    transport: "native-dialog",
    channel_identity: "registered-synthetic-controller",
    stage: "pi-confirm-return",
  });
  admin.restore(preview.preview.request_id, f.disk);
  f.disk.close();
  const next = new DiskStorage(f.home);
  t.after(() => next.close());
  const core = new Core(next, {
    ...f.ctx,
    epoch: next.workspace.epoch,
    runtime_id: "restored",
  });
  fail(() => core.sleepBatch(pending), "RESTORE_RECONCILIATION_REQUIRED");
  assert.equal(next.all("SELECT * FROM sleep_items").length, itemCount);
  assert.ok(next.all("SELECT * FROM recovery_barriers").length);
  f.rebind(core);
  const restarted = f.start();
  assert.ok(f.batch(restarted).cards.some((c) => c.ref.id === e));
  assert.ok(
    f
      .batch(restarted)
      .cards.some((c) => c.input === "deferred" && c.prior_disposition),
  );
  assert.ok(next.all("SELECT * FROM recovery_barriers").length);
  assert.notEqual(activeLocation(f.home), f.home);
});

test("Sleep disk schema-6 bundles verify unchanged and migrate only in quarantine", async (t) => {
  const f = fixture();
  t.after(() => f.disk.close());
  f.evidence();
  const admin = new Administration(f.home, f.backups, f.ctx),
    backup = await admin.backup(f.disk);
  const path = backup.backup,
    db = new DatabaseSync(join(path, "database.sqlite"));
  const ws = { ...f.disk.workspace, schema_version: 6 };
  db.exec(
    "DROP TABLE sleep_items; DROP TABLE sleep_reviews; DROP TABLE sleep_coverage; PRAGMA user_version=6;",
  );
  db.prepare("UPDATE meta SET json=?").run(JSON.stringify(ws));
  db.close();
  const exported = JSON.parse(readFileSync(join(path, "export.json"), "utf8"));
  for (const t of ["sleep_items", "sleep_reviews", "sleep_coverage"])
    delete exported.tables[t];
  exported.schema = 6;
  writeFileSync(join(path, "export.json"), JSON.stringify(exported));
  const manifest = JSON.parse(
    readFileSync(join(path, "manifest.json"), "utf8"),
  );
  manifest.schema = 6;
  manifest.components = manifest.components.map((c: { path: string }) => {
    const bytes = readFileSync(join(path, c.path));
    return { path: c.path, length: bytes.length, sha256: digest(bytes) };
  });
  writeFileSync(join(path, "manifest.json"), JSON.stringify(manifest));
  const original = digest(readFileSync(join(path, "database.sqlite")));
  assert.equal(admin.verify(path).manifest.schema, 6);
  const preview = admin.restorePreview(
    path,
    "Quarantine schema-6 bundle",
    "Keep",
  );
  assert.equal(digest(readFileSync(join(path, "database.sqlite"))), original);
  const q = new DatabaseSync(join(preview.destination, "zara.sqlite"), {
    readOnly: true,
  });
  assert.equal(q.prepare("PRAGMA user_version").get()!.user_version, 7);
  assert.ok(q.prepare("SELECT * FROM migrations WHERE version=7").get());
  q.close();
  assert.ok(f.disk.get("SELECT json FROM meta"));
});

test("Sleep disk interrupted episode continuation preserves frozen review, case and prepared batch; lost commit reply is discoverable", (t) => {
  const f = fixture();
  t.after(() => f.disk.close());
  f.evidence();
  const run = f.start(),
    original = f.batch(run),
    prior = f.read(run);
  f.commit(
    [
      {
        op: "finish_run",
        ref: { id: run },
        execution: "interrupted",
        summary: "Interrupted review, exact pending batch retained",
        result_refs: [],
      },
    ],
    [run],
  );
  const continued = f.commit(
    [
      {
        op: "start_run",
        client_ref: "next",
        title: "Continue the same frozen review",
        visibility: "workspace",
        episode_key: "continued-review",
        work_ref: prior.data.work_ref,
        mode: "sleep",
        continuation_of: { id: run },
        summary: "Continue without old transcript",
        starting_refs: [],
      },
      {
        op: "start_sleep",
        run_ref: ref("next"),
        work_ref: prior.data.work_ref,
      },
    ],
    [(prior.data.work_ref as { id: string }).id, run],
  );
  assert.equal(f.read(continued.created.next).data.case_id, prior.data.case_id);
  assert.equal(f.batch(run).batch_id, original.batch_id);
  const request = f.checkpoint(run),
    faulty = new Core(f.disk, f.ctx, (p) => {
      if (p === "after_commit") throw Error("Synthetic lost committed reply");
    });
  f.rebind(faulty);
  const lost = { ...request, source_handles: f.request([]).source_handles };
  assert.throws(() => f.core.commit(lost), /Synthetic lost committed reply/);
  assert.equal(f.batch(run).status, "completed");
  f.rebind(
    new Core(f.disk, { ...f.ctx, runtime_id: "discover-without-transcript" }),
  );
  assert.deepEqual(
    f.core.commit(lost),
    JSON.parse(
      f.disk.get<{ json: string }>(
        "SELECT json FROM receipts WHERE request_id=?",
        lost.request_id,
      )!.json,
    ),
  );
  assert.ok(f.core.browse("operations").data);
});

test("Sleep disk observing check remains independent; review results and evaluations of bookkeeping never create fresh experience", (t) => {
  const f = fixture();
  t.after(() => f.disk.close());
  const e = f.evidence(),
    m = f.commit([method(e)]).created.m,
    s = f.commit([signal(e, { id: m })]).created.s,
    run = f.start();
  f.finish(run);
  const bundle = f.core.methodBundle(m).data;
  fail(
    () =>
      f.commit([
        {
          op: "invoke_method",
          client_ref: "fake",
          run_ref: { id: run },
          invocation_key: "review-is-not-application",
          method_ref: bundle.root_ref,
          selected_versions: bundle.selected_versions,
          input_refs: [{ id: e }],
          context_refs: [],
          bindings: {},
          parent_invocation_ref: null,
        },
      ]),
    "INVALID_TRANSITION",
  );
  const summary = f.commit([
    {
      op: "record_result",
      client_ref: "summary",
      run_ref: { id: run },
      title: "Review summary",
      content: "Technical review summary; not a new independent result",
      source_language: "en",
    },
  ]).created.summary;
  f.commit([evaluation(summary, 1, e)]);
  f.commit(
    [
      {
        op: "review_signal",
        client_ref: "review",
        ref: { id: s },
        problem_state: "observing",
        assessment: "Correction remains unverified",
        evidence_refs: [{ id: e }],
        applied_change_ref: { id: m, revision: 1 },
        next_check: "Suitable real work",
        grounds: null,
        dismissal_reason: null,
      },
    ],
    [s],
  );
  const next = f.start();
  const ids = f.finish(next);
  assert.ok(ids.includes(s));
  assert.ok(!ids.includes(summary));
  assert.ok(!ids.some((id) => f.read(id).kind === "evaluation"));
  assert.equal(f.read(s).data.problem_state, "observing");
});

test("Sleep disk Activity shared-write approval cannot be bypassed by omitting checkpoint after review activation", (t) => {
  const f = fixture();
  t.after(() => f.disk.close());
  const a = f.commit([
    {
      op: "create_record",
      kind: "activity",
      client_ref: "a",
      title: "Local synthetic review",
      visibility: "workspace",
      data: { purpose: "Scope check", status: "active" },
    },
  ]).created.a;
  const e = f.evidence(),
    m = f.commit([method(e)]).created.m;
  f.start(a);
  const req = f.request(
    [
      {
        op: "revise_method",
        ref: { id: m },
        data: {
          ...f.read(m).data,
          instructions: "An unapproved shared rewrite",
        },
      },
    ],
    [m],
  );
  fail(() => f.core.commit(req), "APPROVAL_REQUIRED");
  assert.equal(f.read(m).revision, 1);
});

test("Sleep disk missing/corrupt stores preserve failure state rather than creating empty replacement memory", (t) => {
  for (const corrupt of [false, true]) {
    const f = fixture();
    const run = f.start();
    f.disk.close();
    if (corrupt)
      writeFileSync(join(f.home, "zara.sqlite"), "Synthetic corrupt SQLite");
    else {
      renameSync(
        join(f.home, "zara.sqlite"),
        join(f.home, "preserved-missing.sqlite"),
      );
    }
    const bytes = corrupt ? readFileSync(join(f.home, "zara.sqlite")) : null;
    assert.throws(() => new DiskStorage(f.home));
    if (bytes)
      assert.deepEqual(readFileSync(join(f.home, "zara.sqlite")), bytes);
    assert.ok(run);
    t.after(() => f.disk.close());
  }
});

test("Sleep disk Activity reads mixed-scope Signals as context without treating shared subjects as local write ownership", (t) => {
  const f = fixture();
  t.after(() => f.disk.close());
  const a = f.commit([
    {
      op: "create_record",
      kind: "activity",
      client_ref: "a",
      title: "Mixed-scope synthetic Activity",
      visibility: "workspace",
      data: { purpose: "Review bound local work", status: "active" },
    },
  ]).created.a;
  const e = f.evidence(),
    m = f.commit([method(e)]).created.m,
    w = f.commit([work("w", a)]).created.w;
  const s = f.commit([
    { ...signal(e, { id: w }), subject_refs: [{ id: w }, { id: m }] },
  ]).created.s;
  const run = f.start(a);
  assert.ok(f.batch(run).cards.some((c) => c.ref.id === s));
  const req = f.request(
    [
      {
        op: "review_signal",
        client_ref: "review",
        ref: { id: s },
        problem_state: "open",
        assessment: "Mixed ownership needs confirmation",
        evidence_refs: [{ id: e }],
        applied_change_ref: null,
        next_check: "New exact approval",
        grounds: null,
        dismissal_reason: null,
      },
    ],
    [s],
  );
  fail(() => f.core.commit(req), "APPROVAL_REQUIRED");
  assert.equal(f.read(s).revision, 1);
});

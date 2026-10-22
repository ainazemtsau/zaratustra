import test from "node:test";
import assert from "node:assert/strict";
import {
  mkdtempSync,
  mkdirSync,
  writeFileSync,
  readFileSync,
  symlinkSync,
  linkSync,
  readdirSync,
} from "node:fs";
import { join } from "node:path";
import { tmpdir } from "node:os";
import { DatabaseSync } from "node:sqlite";
import {
  createEditTool,
  createWriteTool,
} from "@earendil-works/pi-coding-agent";
import { Core, CoreError, canonical, digest } from "../src/core/index.ts";
import type { RecordRow, FileEffect, JsonObject } from "../src/core/index.ts";
import { DiskStorage, OutputBoundary } from "../src/storage/index.ts";
import { renderApproval } from "../src/extension/preview.ts";
import { simulateNative } from "../src/extension/managed.ts";

const rejects = (f: () => unknown, code: string) =>
  assert.throws(f, (e: unknown) => e instanceof CoreError && e.code === code);
const dialog = {
  source_ref: "synthetic-native-answer",
  transport: "native-dialog" as const,
  channel_identity: "registered-synthetic-controller",
  stage: "pi-confirm-return" as const,
};
function fixture(scopes: string[] = []) {
  const root = mkdtempSync(
    join(process.env.ZARATUSTRA_TEST_ROOT ?? tmpdir(), "zara-E2-"),
  );
  const home = join(root, "home"),
    output = join(root, "output");
  mkdirSync(output);
  const disk = new DiskStorage(home);
  const core = new Core(disk, {
    ...disk.workspace,
    principal: "trusted-personal",
    session_id: "session",
    runtime_id: "runtime",
    can_write: true,
    processing_allowed: true,
    scopes,
  });
  const source = core.capture(
    "Synthetic proposal, not owner experience",
    "rpc",
    "registered-synthetic-controller",
  );
  let n = 0;
  const read = (id: string, revision?: number) =>
    core.read(id, revision).data as RecordRow;
  const request = (ops: unknown[], ids: string[] = []) => ({
    request_id: "domain-" + ++n,
    reason: "Synthetic exact domain change",
    source_handles: [source.source_handle],
    guards: ids.map((id) => ({
      ref: { id },
      expected_revision: read(id).revision,
    })),
    ops,
  });
  const commit = (ops: unknown[], ids: string[] = []) =>
    core.commit(request(ops, ids));
  const approve = (ref: string, yes = true) => {
    const shown = core.approvals.present(ref);
    return core.approvals.answer(shown.token, yes, dialog);
  };
  const node = (name: string, kind = "entity", visibility = "workspace") =>
    commit([
      {
        op: "create_record",
        client_ref: "node",
        kind,
        title: name,
        visibility,
        data:
          kind === "entity"
            ? {
                entity_kind: "item",
                aliases: [],
                disambiguation: "Synthetic distinct identity",
                status: "active",
              }
            : kind === "activity"
              ? { purpose: name, status: "active" }
              : {
                  definition: name,
                  aliases: [],
                  broader_ids: [],
                  status: "active",
                },
      },
    ]).created.node;
  const bound = (req: ReturnType<typeof request>) => {
    const p = core.prepareCommit(
      req,
      "Объединить указанные объекты с сохранением истории",
      "Оставить их раздельными",
    );
    approve(p.request_id);
    return { ...req, preview_ref: p.request_id };
  };
  const boundary = new OutputBoundary(output);
  const effect = async (name = "report.txt", content = "exact\r\n🦉") => ({
    request_id: "file-" + ++n,
    tool: "write" as const,
    ...(await simulateNative(boundary, root, {
      tool: "write",
      arguments: { path: join(output, name), content },
    })),
    work_ref: null,
    step_id: null,
    independent_basis: "Independent new synthetic file action",
    method_export: null,
    retry_of: null,
    retry_risk: null,
  });
  const fileApproval = (e: FileEffect) => {
    const p = core.prepareFile(
      e,
      "Записать точный текст в указанный файл",
      "Сохранить текущее состояние",
    );
    Object.assign(e, p.payload.exact);
    approve(p.request_id);
    return p.request_id;
  };
  return {
    root,
    home,
    output,
    disk,
    core,
    source,
    read,
    request,
    commit,
    approve,
    node,
    bound,
    boundary,
    effect,
    fileApproval,
  };
}

test("E2 disk exact merge permission: old yes/new target or values refused; unrelated mutation positive; atomic receipt replay and historical navigation", (t) => {
  const f = fixture();
  t.after(() => f.disk.close());
  const a = f.node("Орбита Ω"),
    b = f.node("Orbit item"),
    other = f.node("Other");
  const req = f.request(
    [{ op: "merge_identity", from_ref: { id: a }, to_ref: { id: b } }],
    [a, b],
  );
  rejects(() => f.core.commit(req), "APPROVAL_REQUIRED");
  const prepared = f.bound(req);
  rejects(
    () =>
      f.core.commit({
        ...prepared,
        ops: [
          { op: "merge_identity", from_ref: { id: a }, to_ref: { id: other } },
        ],
        guards: [
          ...prepared.guards,
          { ref: { id: other }, expected_revision: 1 },
        ],
      }),
    "APPROVAL_STALE",
  );
  f.commit(
    [
      {
        op: "update_record",
        ref: { id: other },
        title: "Unrelated rename",
        data: f.read(other).data,
      },
    ],
    [other],
  );
  const receipt = f.core.commit(prepared);
  assert.deepEqual(f.core.commit(prepared), receipt);
  assert.equal(f.read(a).data.status, "merged");
  assert.deepEqual(f.read(a).data.redirect_to, { id: b });
  assert.equal(f.read(a, 1).title, "Орбита Ω");
  assert.equal(f.read(a, 1).data.redirect_to, undefined);
  assert.ok((f.read(b).data.aliases as string[]).includes("Орбита Ω"));
  assert.equal(
    f.core.search({ query: "Орбита", match: "all" }).data.cards.length,
    2,
  );
  assert.equal(f.core.approvals.read(prepared.preview_ref).status, "consumed");
  rejects(
    () => f.core.commit({ ...prepared, request_id: "another" }),
    "APPROVAL_STALE",
  );
});

test("E2 disk approval invalidation: material revision, scopes, policy, epoch, runtime, expiry, revoked/expired source, refused/cancelled/forged reply", (t) => {
  for (const change of [
    "material",
    "scope",
    "policy",
    "epoch",
    "runtime",
    "expiry",
    "revoke",
    "source",
    "refusal",
    "forged",
    "tamper",
  ]) {
    const f = fixture();
    t.after(() => f.disk.close());
    const a = f.node("A"),
      b = f.node("B");
    const req = f.request(
      [{ op: "merge_identity", from_ref: { id: a }, to_ref: { id: b } }],
      [a, b],
    );
    const p = f.core.prepareCommit(req, "Exact merge", "Leave separate", 900);
    if (change === "forged") {
      const s = f.core.capture("yes", "extension", null);
      rejects(
        () => f.core.approvals.answer(s.source_handle, true, dialog),
        "APPROVAL_REQUIRED",
      );
    } else f.approve(p.request_id, change !== "refusal");
    if (change === "material")
      f.commit(
        [
          {
            op: "update_record",
            ref: { id: a },
            title: "Changed material title",
            data: f.read(a).data,
          },
        ],
        [a],
      );
    if (change === "scope") f.core.context.scopes = ["restricted:read"];
    if (change === "policy") f.core.context.policy_revision = "next-policy";
    if (change === "epoch") f.core.context.epoch = "different-epoch";
    if (change === "runtime") f.core.context.runtime_id = "replacement";
    if (change === "revoke") f.core.approvals.revoke(p.request_id);
    if (change === "source") f.core.expireSources();
    if (change === "tamper") {
      const row = f.core.approvals.read(p.request_id);
      row.payload.exact.reason = "rewritten";
      f.disk.run(
        "UPDATE intents SET json=? WHERE request_id=?",
        JSON.stringify(row),
        p.request_id,
      );
    }
    const realNow = Date.now;
    // Expire AFTER the native grant without racing a one-second filesystem/UI
    // round trip under concurrent disk-test load. Keep real production TTLs.
    if (change === "expiry") Date.now = () => realNow() + 900001;
    try {
      assert.throws(
        () => f.core.commit({ ...req, preview_ref: p.request_id }),
        /changed|mismatch|expired|approval|Preview|source/i,
        change,
      );
    } finally {
      Date.now = realNow;
    }
    f.core.context.epoch = f.disk.workspace.epoch;
    assert.equal(f.read(a).data.status, "active");
  }
});

test("E2 disk failed domain commit rolls back consumption, versions, Changes and index; persisted draft never reattaches transient authority", (t) => {
  const f = fixture();
  t.after(() => f.disk.close());
  const a = f.node("A"),
    b = f.node("B");
  const req = f.request(
    [{ op: "merge_identity", from_ref: { id: a }, to_ref: { id: b } }],
    [a, b],
  );
  const prepared = f.bound(req);
  const failed = new Core(f.disk, f.core.context, (p) => {
    if (p === "before_commit") throw Error("Injected domain interruption");
  });
  // A new Core instance does not inherit even an identical runtime's transient permission.
  rejects(() => failed.commit(prepared), "SOURCE_EXPIRED");
  const freshSource = failed.capture(
    "Current synthetic source",
    "rpc",
    "registered-synthetic-controller",
  );
  const newRequest = {
    ...req,
    request_id: "fault-exact",
    source_handles: [freshSource.source_handle],
  };
  const snapshot = canonical(f.disk.all("SELECT * FROM records"));
  const p = failed.prepareCommit(newRequest, "Exact merge", "Keep separate"),
    shown = failed.approvals.present(p.request_id);
  failed.approvals.answer(shown.token, true, dialog);
  assert.throws(
    () => failed.commit({ ...newRequest, preview_ref: p.request_id }),
    /interruption/,
  );
  assert.equal(canonical(f.disk.all("SELECT * FROM records")), snapshot);
  assert.equal(
    failed.approvals.read(p.request_id).status,
    "approved-transient",
  );
  const reopened = new Core(f.disk, {
    ...f.core.context,
    runtime_id: "new-process",
    session_id: "new-session",
  });
  rejects(() => reopened.approvals.present(p.request_id), "APPROVAL_STALE");
});

test("E2 disk preview/support access and bounded operations/history hide guessed protected identities and restricted drafts", (t) => {
  const f = fixture(["restricted:read", "restricted:write"]);
  t.after(() => f.disk.close());
  const a = f.node("SECRET Ω", "entity", "restricted"),
    b = f.node("Target");
  const p = f.core.prepareCommit(
    f.request(
      [{ op: "merge_identity", from_ref: { id: a }, to_ref: { id: b } }],
      [a, b],
    ),
    "Protected merge",
    "Keep separate",
  );
  const low = new Core(f.disk, { ...f.core.context, scopes: [] });
  rejects(() => low.approvals.read(p.request_id), "REFERENCE_NOT_FOUND");
  rejects(() => low.operation(p.request_id), "REFERENCE_NOT_FOUND");
  const listing = JSON.stringify(low.browse("operations", undefined, 1));
  assert.ok(!listing.includes("SECRET") && !listing.includes(p.request_id));
  assert.ok(!JSON.stringify(low.snapshot()).includes("SECRET"));
  const page = f.core.browse("operations", undefined, 1).data;
  assert.equal(page.cards.length, 1);
  assert.equal(page.has_more, true);
});

test("E2 disk finite Concept merge/reorg preserves IDs, aliases, memberships and exact historical refs; final cycle and bypass refused atomically", (t) => {
  const f = fixture();
  t.after(() => f.disk.close());
  const a = f.node("Source section", "concept"),
    b = f.node("Destination section", "concept"),
    item = f.node("Classified item");
  f.commit(
    [
      {
        op: "update_record",
        ref: { id: item },
        data: f.read(item).data,
        concept_ids: [{ id: a }],
      },
    ],
    [item],
  );
  const merge = f.bound(
    f.request(
      [{ op: "merge_identity", from_ref: { id: a }, to_ref: { id: b } }],
      [a, b],
    ),
  );
  f.core.commit(merge);
  assert.ok(
    f.core
      .browse("records", b)
      .data.cards.some((c: JsonObject) => c.id === item),
  );
  assert.deepEqual(f.read(item).concept_ids, [{ id: a }]);
  assert.equal(f.read(a, 1).data.status, "active");
  rejects(
    () =>
      f.commit(
        [
          {
            op: "update_record",
            ref: { id: b },
            data: {
              ...f.read(b).data,
              status: "merged",
              redirect_to: { id: a },
            },
          },
        ],
        [b],
      ),
    "APPROVAL_REQUIRED",
  );
  const c = f.node("Other section", "concept");
  const cycle = f.bound(
    f.request(
      [
        {
          op: "reorganize_catalog",
          changes: [
            { ref: { id: b }, broader_ids: [{ id: c }] },
            { ref: { id: c }, broader_ids: [{ id: b }] },
          ],
        },
      ],
      [b, c],
    ),
  );
  rejects(() => f.core.commit(cycle), "GRAPH_CYCLE");
  assert.deepEqual(f.read(b).data.broader_ids, []);
  assert.equal(
    f.core.approvals.read(cycle.preview_ref).status,
    "approved-transient",
  );
  const move = f.bound(
    f.request(
      [
        {
          op: "reorganize_catalog",
          changes: [
            { ref: { id: item }, concept_ids: [{ id: c }] },
            { ref: { id: c }, title: "New catalog entry" },
          ],
        },
      ],
      [item, c],
    ),
  );
  f.core.commit(move);
  assert.equal(f.read(item, 2).concept_ids[0].id, a);
  assert.equal(f.read(item).concept_ids[0].id, c);
});

test("E2 disk native write/edit round-trip exact BOM/CRLF/Unicode and public fuzzy semantics, dispatch replay and readback separate from native success prose", async (t) => {
  const f = fixture();
  t.after(() => f.disk.close());
  const e = await f.effect(
    "exact.txt",
    "\ufeffHeading\r\nQuoted “value”\r\n🦉\r\n",
  );
  const p = f.fileApproval(e);
  f.core.dispatchFile(e, p, "call-write");
  await createWriteTool(f.root).execute(
    "call-write",
    e.arguments as { path: string; content: string },
  );
  assert.deepEqual(readFileSync(e.target), Buffer.from(e.final_text));
  const receipt = f.core.observeFile(
    e.request_id,
    {
      hash: digest(readFileSync(e.target)),
      byte_length: readFileSync(e.target).length,
    },
    {
      id: "call-write",
      runtime_id: f.core.context.runtime_id,
      is_error: false,
    },
  );
  assert.equal(receipt.status, "confirmed");
  assert.equal(receipt.receipt!.writer_attribution, "unknown");
  assert.deepEqual(
    f.core.fileReplay(e.request_id, "write", e.arguments)?.receipt,
    receipt.receipt,
  );
  rejects(() => f.core.dispatchFile(e, p, "replay"), "UNKNOWN_EFFECT");
  rejects(
    () =>
      f.core.fileReplay(e.request_id, e.tool, e.arguments, {
        work_ref: { id: "changed-target-work", revision: 1 },
      }),
    "IDEMPOTENCY_CONFLICT",
  );
  const args = {
    path: e.target,
    edits: [{ oldText: 'Quoted "value"', newText: "Changed\nvalue" }],
  };
  const edit: FileEffect = {
    ...e,
    request_id: "native-edit",
    tool: "edit",
    ...(await simulateNative(f.boundary, f.root, {
      tool: "edit",
      arguments: args,
    })),
  };
  f.core.dispatchFile(edit, f.fileApproval(edit), "call-edit");
  await createEditTool(f.root).execute("call-edit", args);
  assert.deepEqual(readFileSync(e.target), Buffer.from(edit.final_text));
  assert.ok(edit.final_text.startsWith("\ufeff"));
  assert.ok(edit.final_text.includes("Changed\r\nvalue"));
  const bad = await f.effect("not-written.txt", "expected");
  f.core.dispatchFile(bad, f.fileApproval(bad), "false-success");
  const observed = f.core.observeFile(
    bad.request_id,
    { hash: null, byte_length: 0 },
    {
      id: "false-success",
      runtime_id: f.core.context.runtime_id,
      is_error: false,
    },
  );
  assert.equal(observed.status, "unknown");
  rejects(
    () =>
      f.core.observeFile(
        bad.request_id,
        { hash: bad.final_hash, byte_length: bad.final_length },
        { id: "forged-call", runtime_id: "other", is_error: false },
      ),
    "UNKNOWN_EFFECT",
  );
});

test("E2 disk lost result/new process without ID discovers requested attempt and inspects bytes without redispatch; prior unknown blocks a new request ID", async (t) => {
  const f = fixture();
  t.after(() => f.disk.close());
  const e = await f.effect();
  f.core.dispatchFile(e, f.fileApproval(e), "lost-result");
  await createWriteTool(f.root).execute(
    "lost-result",
    e.arguments as { path: string; content: string },
  );
  const fresh = new Core(f.disk, {
    ...f.core.context,
    session_id: "fresh",
    runtime_id: "fresh",
  });
  const page = fresh.browse("operations").data.cards as JsonObject[];
  const discovered = page.find((r) => r.kind === "managed_file")!;
  assert.equal(discovered.request_id, e.request_id);
  const before = fresh.inspectFile(discovered.request_id as string);
  assert.equal(before.status, "requested");
  const obs = f.boundary.inspect(before.payload.target, f.root);
  const reconciled = fresh.observeFile(before.request_id, {
    hash: obs.hash,
    byte_length: obs.byte_length,
  });
  assert.equal(reconciled.status, "confirmed");
  assert.equal(reconciled.receipt!.writer_attribution, "unknown");
  assert.deepEqual(readFileSync(e.target), Buffer.from(e.final_text));
  const lost = await f.effect("before-dispatch.txt");
  f.core.dispatchFile(lost, f.fileApproval(lost), "before-dispatch");
  const again = { ...lost, request_id: "guessed-new-id" };
  const p = f.fileApproval(again);
  rejects(
    () => f.core.dispatchFile(again, p, "blind-repeat"),
    "UNKNOWN_EFFECT",
  );
  assert.equal(
    f.core.observeFile(lost.request_id, { hash: null, byte_length: 0 }).status,
    "unknown",
  );
  const risky = {
    ...again,
    retry_of: lost.request_id,
    retry_risk:
      "May repeat a possibly dispatched write; current absence does not prove non-execution",
  };
  const approved = f.fileApproval(risky);
  f.core.dispatchFile(risky, approved, "separate-risky-decision");
  assert.equal(
    f.core.inspectFile(risky.request_id).payload.retry_of,
    lost.request_id,
  );
});

test("E2 disk confirmed receipt survives later drift, repeated inspection and addressed historical replay", async (t) => {
  const f = fixture();
  t.after(() => f.disk.close());
  const e = await f.effect();
  f.core.dispatchFile(e, f.fileApproval(e), "receipt-history");
  const unknown = f.core.observeFile(e.request_id, {
    hash: null,
    byte_length: 0,
  });
  const originalUnknown = structuredClone(unknown.receipt);
  await createWriteTool(f.root).execute(
    "receipt-history",
    e.arguments as { path: string; content: string },
  );
  const confirmed = f.core.observeFile(e.request_id, {
    hash: e.final_hash,
    byte_length: e.final_length,
  });
  const original = structuredClone(confirmed.receipt);
  writeFileSync(e.target, "Later external drift");
  const now = f.core.observeFile(e.request_id, {
    hash: digest(readFileSync(e.target)),
    byte_length: readFileSync(e.target).length,
  });
  assert.equal(now.status, "confirmed");
  assert.equal(now.current_observation!.postcondition_matches, false);
  assert.equal(now.current_observation!.drift_from_confirmed, true);
  assert.deepEqual(now.receipt, original);
  assert.deepEqual(now.receipt_history, [originalUnknown, original]);
  assert.deepEqual(
    f.core.fileReplay(e.request_id, e.tool, e.arguments)!.receipt,
    original,
  );
  assert.deepEqual(
    (
      f.core.operation(originalUnknown!.receipt_id as string)
        .data as unknown as { receipt_history: JsonObject[] }
    ).receipt_history[0],
    originalUnknown,
  );
});

test("E2 disk Activity merge and split move only explicitly bound Work; historical origins, goals and priorities require new permission", (t) => {
  const f = fixture();
  t.after(() => f.disk.close());
  const a = f.node("Source Activity", "activity"),
    b = f.node("Target Activity", "activity");
  const workData = {
    activity_id: { id: a },
    parent_work_id: null,
    objective: "Retain a report",
    priority: "Normal priority",
    acceptance: [
      {
        criterion_id: "report",
        description: "Report retained",
        verification: "Read the result",
        required: true,
      },
    ],
    status: "active",
    current_state: "Ready",
    next_action: "Read the source",
    steps: [],
    waits: [],
    context_refs: [],
    completion: null,
  };
  const w = f.commit([
    {
      op: "create_record",
      client_ref: "w",
      kind: "work",
      title: "Report Work",
      visibility: "workspace",
      data: workData,
    },
  ]).created.w;
  const move = f.request(
    [
      {
        op: "merge_activity",
        from_ref: { id: a },
        to_ref: { id: b },
        moved_work_refs: [{ id: w }],
      },
    ],
    [a, b, w],
  );
  rejects(() => f.core.commit(move), "APPROVAL_REQUIRED");
  f.core.commit(f.bound(move));
  assert.deepEqual(f.read(w).data.activity_id, { id: b });
  assert.deepEqual(f.read(w, 1).data.activity_id, { id: a });
  assert.equal(f.read(a).data.status, "merged");
  const split = f.request(
    [
      {
        op: "create_record",
        client_ref: "split",
        kind: "activity",
        title: "Explicit new split",
        visibility: "workspace",
        data: { purpose: "Independent report area", status: "active" },
      },
      {
        op: "update_record",
        ref: { id: w },
        data: { ...f.read(w).data, activity_id: { client_ref: "split" } },
        plan_change_reason: "Explicit finite split",
      },
    ],
    [w],
  );
  rejects(() => f.core.commit(split), "APPROVAL_REQUIRED");
  const divided = f.core.commit(f.bound(split));
  assert.deepEqual(f.read(w).data.activity_id, { id: divided.created.split });
  const priority = f.request(
    [
      {
        op: "update_record",
        ref: { id: w },
        data: { ...f.read(w).data, priority: "High priority" },
        plan_change_reason: "Substantive priority decision",
      },
    ],
    [w],
  );
  rejects(() => f.core.commit(priority), "APPROVAL_REQUIRED");
  f.core.commit(f.bound(priority));
  assert.equal(f.read(w).data.priority, "High priority");
});

test("E2 disk output containment, hardlinks/junctions/control aliases, changed before bytes/identity and native UTF-8 limits", async (t) => {
  const f = fixture();
  t.after(() => f.disk.close());
  for (const path of [
    join(f.root, "escape.txt"),
    join(f.output, "..", "escape.txt"),
    join(f.output, "NUL.txt"),
    join(f.output, "stream:secret"),
    join(f.output, "trailing."),
    join(f.output, "bad\nname"),
  ])
    rejects(() => f.boundary.inspect(path, f.root), "PERMISSION_DENIED");
  const outside = join(f.root, "outside");
  mkdirSync(outside);
  symlinkSync(outside, join(f.output, "junction"), "junction");
  rejects(
    () => f.boundary.inspect(join(f.output, "junction", "escape.txt"), f.root),
    "PERMISSION_DENIED",
  );
  const a = join(f.output, "a.txt");
  writeFileSync(a, "same");
  linkSync(a, join(f.output, "hardlink.txt"));
  rejects(() => f.boundary.inspect(a, f.root), "PERMISSION_DENIED");
  const e = await f.effect("changed.txt");
  const approved = f.fileApproval(e);
  writeFileSync(e.target, "outside changed");
  rejects(() => f.boundary.check(e, f.root), "APPROVAL_STALE");
  assert.equal(f.core.approvals.read(approved).status, "approved-transient");
  const invalid = join(f.output, "invalid.txt");
  writeFileSync(invalid, Buffer.from([0xff]));
  await assert.rejects(
    simulateNative(f.boundary, f.root, {
      tool: "edit",
      arguments: { path: invalid, edits: [{ oldText: "x", newText: "y" }] },
    }),
    /UTF-8/,
  );
  await assert.rejects(
    simulateNative(f.boundary, f.root, {
      tool: "write",
      arguments: { path: join(f.output, "large"), content: "🦉".repeat(20000) },
    }),
    /bound/,
  );
});

test("E2 disk textual export binds exact canonical version/content/export hashes; external edit is drift, regeneration needs new permission", async (t) => {
  const f = fixture();
  t.after(() => f.disk.close());
  const mid = f.commit([
    {
      op: "create_record",
      client_ref: "m",
      kind: "method",
      title: "Inspect a report",
      visibility: "workspace",
      data: {
        applicability: "Synthetic reports",
        instructions: "Read all lines and report missing fields",
        input_contract: "Text report",
        expected_output: "Addressed checked result",
        context_requirements: [],
        dependencies: [],
        tool_requirements: ["read"],
        content_version: 1,
        state: "candidate",
        derived_from: [],
        limitations: "Text only",
      },
    },
  ]).created.m;
  const exported = f.core.methodExport(mid, 1);
  const e: FileEffect = {
    ...(await f.effect("SKILL.md", exported.text)),
    method_export: {
      method_ref: exported.method_ref,
      content_hash: exported.content_hash,
      export_hash: exported.export_hash,
    },
  };
  f.core.dispatchFile(e, f.fileApproval(e), "export");
  await createWriteTool(f.root).execute(
    "export",
    e.arguments as { path: string; content: string },
  );
  f.core.observeFile(e.request_id, {
    hash: exported.export_hash,
    byte_length: e.final_length,
  });
  assert.equal(
    f.core.skillExportStatus(e.target, exported.export_hash).drift,
    false,
  );
  writeFileSync(e.target, exported.text + "\nExternal proposal only\n");
  assert.equal(
    f.core.skillExportStatus(e.target, digest(readFileSync(e.target))).drift,
    true,
  );
  assert.equal(f.read(mid).data.content_version, 1);
  const regeneration = {
    ...e,
    request_id: "regenerate",
    ...(await simulateNative(f.boundary, f.root, {
      tool: "write",
      arguments: e.arguments,
    })),
  };
  rejects(
    () =>
      f.core.dispatchFile(
        regeneration,
        f.core.approvals.read(f.core.inspectFile(e.request_id).preview_ref)
          .request_id,
        "old-permission",
      ),
    "APPROVAL_STALE",
  );
  const newPermission = f.fileApproval(regeneration);
  f.core.dispatchFile(regeneration, newPermission, "fresh-regeneration");
  assert.equal(
    f.core.inspectFile(e.request_id).payload.method_export!.method_ref
      .content_version,
    1,
  );
});

test("E2 disk schema-4 filled migration: all canonical rows preserved, verified backup/transaction/manifest faults and old-schema guard", (t) => {
  for (const point of [
    "approval_after_backup",
    "approval_before_schema_commit",
    "approval_after_schema_commit",
  ]) {
    const f = fixture();
    const id = f.node("Persisted predecessor");
    const before = canonical(f.disk.all("SELECT * FROM records"));
    f.disk.exec(
      "DROP TABLE sleep_items; DROP TABLE sleep_reviews; DROP TABLE sleep_coverage; DROP INDEX intent_kind; PRAGMA user_version=4",
    );
    f.disk.workspace.schema_version = 4;
    f.disk.run("UPDATE meta SET json=?", JSON.stringify(f.disk.workspace));
    writeFileSync(
      join(f.home, "workspace.json"),
      JSON.stringify(f.disk.workspace),
    );
    f.disk.close();
    assert.throws(
      () =>
        new DiskStorage(f.home, (p) => {
          if (p === point) throw Error("E2 migration interruption");
        }),
      /interruption/,
    );
    const recovered = new DiskStorage(f.home);
    t.after(() => recovered.close());
    assert.equal(recovered.workspace.schema_version, 7);
    assert.equal(canonical(recovered.all("SELECT * FROM records")), before);
    assert.ok(recovered.get("SELECT id FROM records WHERE id=?", id));
    const m = JSON.parse(
      recovered.get<{ json: string }>(
        "SELECT json FROM migrations WHERE version=5",
      )!.json,
    );
    assert.equal(digest(readFileSync(m.backup)), m.backup_sha256);
    const backup = new DatabaseSync(m.backup, { readOnly: true });
    assert.equal(
      (backup.prepare("PRAGMA user_version").get() as { user_version: number })
        .user_version,
      4,
    );
    backup.close();
    assert.ok(readdirSync(f.home).some((p) => p.startsWith("pre-schema-5-")));
  }
});

test("E2 disk merged destination discovers original current claims and cannot expose protected aliases/history", (t) => {
  const f = fixture(["restricted:read", "restricted:write"]);
  t.after(() => f.disk.close());
  const a = f.node("Protected physical label", "entity", "restricted"),
    b = f.node("Public prior label");
  const origin = f.commit([
    {
      op: "import_evidence",
      client_ref: "e",
      source_handle: f.source.source_handle,
      title: "Exact synthetic source",
      source_language: "en",
    },
  ]).created.e;
  const k = f.commit([
    {
      op: "create_record",
      client_ref: "k",
      kind: "knowledge",
      title: "Synthetic resource access",
      visibility: "restricted",
      data: {
        knowledge_kind: "fact",
        statement: "The synthetic user reports access to this item",
        state: "current",
        basis: "user_statement",
        evidence_refs: [{ id: origin }],
        object_ref: { id: a },
        predicate: "has_access_to",
        conditions: "Synthetic lab only",
      },
    },
  ]).created.k;
  const req = f.bound(
    f.request(
      [{ op: "merge_identity", from_ref: { id: a }, to_ref: { id: b } }],
      [a, b],
    ),
  );
  f.core.commit(req);
  assert.equal(f.read(b).visibility, "restricted");
  assert.ok(
    f.core
      .browse("records", b, 20, undefined, "current_claims")
      .data.cards.some((c: JsonObject) => c.id === k),
  );
  assert.deepEqual(f.read(k).data.object_ref, { id: a });
  const low = new Core(f.disk, { ...f.core.context, scopes: [] });
  rejects(() => low.read(b), "REFERENCE_NOT_FOUND");
  assert.ok(
    !JSON.stringify(low.browse("entities")).includes(
      "Protected physical label",
    ),
  );
});

test("E2 disk native Work/step association binds actual plan and context revisions; unrelated data remains independent", async (t) => {
  const f = fixture();
  t.after(() => f.disk.close());
  const premise = f.node("Material condition");
  const w = f.commit([
    {
      op: "create_record",
      client_ref: "w",
      kind: "work",
      title: "Exact artifact Work",
      visibility: "workspace",
      data: {
        activity_id: null,
        parent_work_id: null,
        objective: "Prepare one exact artifact",
        acceptance: [
          {
            criterion_id: "file",
            description: "Exact file inspected",
            verification: "Actual readback",
            required: true,
          },
        ],
        status: "active",
        current_state: "Ready",
        next_action: "Prepare the artifact",
        steps: [],
        waits: [],
        context_refs: [{ id: premise }],
        completion: null,
      },
    },
  ]).created.w;
  const e = {
    ...(await f.effect()),
    work_ref: { id: w, revision: 1 },
    independent_basis: null,
  };
  const p = f.core.prepareFile(
    e,
    "Write the artifact for this exact Work",
    "Leave it unchanged",
  );
  assert.equal(
    (p.payload.exact.work_snapshot as JsonObject).title,
    "Exact artifact Work",
  );
  f.approve(p.request_id);
  f.commit(
    [
      {
        op: "update_record",
        ref: { id: premise },
        title: "Changed material condition",
        data: f.read(premise).data,
      },
    ],
    [premise],
  );
  rejects(
    () =>
      f.core.dispatchFile(
        p.payload.exact as FileEffect,
        p.request_id,
        "stale-context",
      ),
    "APPROVAL_STALE",
  );
  const fresh = f.core.prepareFile(
    e,
    "Write under the current material condition",
    "Leave unchanged",
  );
  f.approve(fresh.request_id);
  f.node("Unrelated independent item");
  const attempt = f.core.dispatchFile(
    fresh.payload.exact as FileEffect,
    fresh.request_id,
    "actual-associated-call",
  );
  assert.deepEqual(attempt.payload.work_ref, { id: w, revision: 1 });
  assert.equal(
    attempt.payload.work_snapshot!.objective,
    "Prepare one exact artifact",
  );
});

test("E2 disk old source cannot authorize a new write after an active epoch change even in the same Core instance", (t) => {
  const f = fixture();
  t.after(() => f.disk.close());
  f.disk.workspace.epoch = "new-active-epoch";
  f.core.context.epoch = "new-active-epoch";
  // Advance authoritative control as well; cached mutation alone is rejected by E3.
  const control = JSON.parse(readFileSync(join(f.home, "active.json"), "utf8"));
  writeFileSync(
    join(f.home, "active.json"),
    JSON.stringify({ ...control, epoch: "new-active-epoch" }),
  );
  rejects(
    () => f.node("Must not be written from old source"),
    "SOURCE_EXPIRED",
  );
  const current = f.core.capture(
    "New epoch source",
    "rpc",
    "registered-synthetic-controller",
  );
  const r = f.core.commit({
    request_id: "fresh-epoch",
    reason: "New current epoch input",
    source_handles: [current.source_handle],
    guards: [],
    ops: [
      {
        op: "create_record",
        client_ref: "a",
        kind: "activity",
        title: "New epoch independent activity",
        visibility: "workspace",
        data: { purpose: "New current input", status: "active" },
      },
    ],
  });
  assert.equal(r.committed, true);
});

test("E2 disk connected corrected identities merge from current staged values with exact sequential preview, history, access and replay", (t) => {
  for (const kind of ["entity", "concept", "activity"]) {
    for (const protectedSource of [false, true]) {
      const f = fixture(
        protectedSource ? ["restricted:read", "restricted:write"] : [],
      );
      t.after(() => f.disk.close());
      const a = f.node(
          "Old source",
          kind,
          protectedSource ? "restricted" : "workspace",
        ),
        b = f.node("Old target", kind);
      const data = (id: string, name: string) => ({
        ...f.read(id).data,
        ...(kind === "entity"
          ? { disambiguation: name, external_ids: { serial: "E2-B62" } }
          : kind === "activity"
            ? { purpose: name }
            : { definition: name }),
        aliases: [name + " alias"],
      });
      const req = f.request(
        [
          {
            op: "update_record",
            ref: { id: a },
            title: "Corrected source",
            body: "Source correction",
            data: data(a, "Corrected source"),
          },
          {
            op: "update_record",
            ref: { id: b },
            title: "Corrected target",
            body: "Target correction",
            data: data(b, "Corrected target"),
          },
          {
            op: kind === "activity" ? "merge_activity" : "merge_identity",
            from_ref: { id: a },
            to_ref: { id: b },
            ...(kind === "activity" ? { moved_work_refs: [] } : {}),
          },
        ],
        [a, b],
      );
      const preview = f.core.prepareCommit(
        req,
        "Correct both identities and merge the corrected source into the corrected target",
        "Keep them separate",
      );
      const shown = renderApproval(preview.payload);
      assert.match(
        shown,
        /Merge (entity|concept|activity) “Corrected source” into “Corrected target”/,
      );
      assert.match(
        shown,
        /Destination aliases will include: Corrected target alias; Corrected source; Corrected source alias/,
      );
      f.approve(preview.request_id);
      const approved = { ...req, preview_ref: preview.request_id },
        receipt = f.core.commit(approved),
        target = f.read(b),
        source = f.read(a);
      assert.equal(target.title, "Corrected target");
      assert.equal(target.body, "Target correction");
      assert.equal(source.title, "Corrected source");
      assert.equal(source.body, "Source correction");
      assert.equal(source.data.status, "merged");
      assert.deepEqual(source.data.redirect_to, { id: b });
      assert.deepEqual(target.data.aliases, [
        "Corrected target alias",
        "Corrected source",
        "Corrected source alias",
      ]);
      if (kind === "entity")
        assert.equal((target.data.external_ids as JsonObject).serial, "E2-B62");
      assert.equal(
        target.visibility,
        protectedSource ? "restricted" : "workspace",
      );
      assert.equal(target.revision, 2);
      assert.equal(f.read(b, 1).title, "Old target");
      assert.equal(f.read(a, 1).data.status, "active");
      const seq = f.core.snapshot().snapshot_seq;
      assert.deepEqual(f.core.commit(approved), receipt);
      assert.equal(f.core.snapshot().snapshot_seq, seq);
    }
  }
});

test("E2 disk connected merge/catalog order retains staged aliases and catalog changes or rejects atomically; late writes cannot leave Work in merged Activity", (t) => {
  const f = fixture();
  t.after(() => f.disk.close());
  const a = f.node("First source"),
    b = f.node("Destination"),
    c = f.node("Second source");
  const req = f.request(
    [
      {
        op: "reorganize_catalog",
        changes: [{ ref: { id: b }, title: "Renamed destination" }],
      },
      { op: "merge_identity", from_ref: { id: a }, to_ref: { id: b } },
      { op: "merge_identity", from_ref: { id: c }, to_ref: { id: b } },
    ],
    [a, b, c],
  );
  f.core.commit(f.bound(req));
  assert.equal(f.read(b).title, "Renamed destination");
  assert.deepEqual(f.read(b).data.aliases, ["First source", "Second source"]);
  const x = f.node("Reverse source"),
    y = f.node("Reverse target");
  for (const last of [
    {
      op: "update_record",
      ref: { id: y },
      title: "Too late correction",
      data: f.read(y).data,
    },
    {
      op: "reorganize_catalog",
      changes: [{ ref: { id: y }, title: "Too late catalog" }],
    },
  ]) {
    const invalid = f.request(
      [{ op: "merge_identity", from_ref: { id: x }, to_ref: { id: y } }, last],
      [x, y],
    );
    const approved = f.bound(invalid),
      before = f.read(y),
      seq = f.core.snapshot().snapshot_seq;
    rejects(() => f.core.commit(approved), "VALIDATION_ERROR");
    assert.deepEqual(f.read(y), before);
    assert.equal(f.read(x).data.status, "active");
    assert.equal(f.core.snapshot().snapshot_seq, seq);
    assert.equal(
      f.disk.get(
        "SELECT request_id FROM receipts WHERE request_id=?",
        invalid.request_id,
      ),
      undefined,
    );
  }
  const activity = f.node("Source area", "activity"),
    target = f.node("Target area", "activity");
  const work = {
    op: "create_record",
    client_ref: "lateWork",
    kind: "work",
    title: "Explicit late member",
    visibility: "workspace",
    data: {
      activity_id: { id: activity },
      parent_work_id: null,
      objective: "Retain note",
      acceptance: [
        {
          criterion_id: "note",
          description: "Note retained",
          verification: "Read note",
          required: true,
        },
      ],
      status: "active",
      current_state: "Ready",
      next_action: "Read",
      steps: [],
      waits: [],
      context_refs: [],
      completion: null,
    },
  };
  for (const beforeMerge of [true, false]) {
    const merge = {
      op: "merge_activity",
      from_ref: { id: activity },
      to_ref: { id: target },
      moved_work_refs: [],
    };
    const invalid = f.request(beforeMerge ? [work, merge] : [merge, work], [
      activity,
      target,
    ]);
    const approved = f.bound(invalid),
      seq = f.core.snapshot().snapshot_seq;
    rejects(() => f.core.commit(approved), "VALIDATION_ERROR");
    assert.equal(f.read(activity).data.status, "active");
    assert.equal(f.core.snapshot().snapshot_seq, seq);
  }
});

test("E2 disk sequential merges propagate staged protected identity to final destination without losing intermediate aliases", (t) => {
  for (const kind of ["entity", "concept", "activity"]) {
    const f = fixture(["restricted:read", "restricted:write"]);
    t.after(() => f.disk.close());
    const a = f.node("Protected original", kind, "restricted"),
      b = f.node("Intermediate", kind),
      c = f.node("Final target", kind);
    const merge = (from: string, to: string) => ({
      op: kind === "activity" ? "merge_activity" : "merge_identity",
      from_ref: { id: from },
      to_ref: { id: to },
      ...(kind === "activity" ? { moved_work_refs: [] } : {}),
    });
    const req = f.request([merge(a, b), merge(b, c)], [a, b, c]);
    const preview = f.core.prepareCommit(
      req,
      "Merge the exact chain and retain protection throughout",
      "Keep original identities separate",
    );
    assert.equal(
      (
        renderApproval(preview.payload).match(
          /Destination visibility: restricted/g,
        ) ?? []
      ).length,
      2,
    );
    f.approve(preview.request_id);
    f.core.commit({ ...req, preview_ref: preview.request_id });
    assert.equal(f.read(c).visibility, "restricted");
    assert.deepEqual(f.read(c).data.aliases, [
      "Intermediate",
      "Protected original",
    ]);
    const low = new Core(f.disk, {
      ...f.core.context,
      scopes: [],
      runtime_id: "fresh-low",
      session_id: "fresh-low",
    });
    rejects(() => low.read(c), "REFERENCE_NOT_FOUND");
    assert.equal(
      low.search({ query: "Protected original", match: "all", channel: "both" })
        .data.cards.length,
      0,
    );
    assert.equal(
      low.browse(
        kind === "activity"
          ? "activities"
          : kind === "entity"
            ? "entities"
            : "concepts",
      ).data.cards.length,
      0,
    );
    assert.ok(!JSON.stringify(low.map()).includes("Protected original"));
  }
});

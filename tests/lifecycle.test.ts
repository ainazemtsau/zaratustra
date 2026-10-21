import test from "node:test";
import assert from "node:assert/strict";
import {
  mkdtempSync,
  mkdirSync,
  readFileSync,
  writeFileSync,
  existsSync,
} from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { DatabaseSync } from "node:sqlite";
import { Core, digest } from "../src/core/index.ts";
import type { CallContext, RecordRow } from "../src/core/index.ts";
import type { FileEffect } from "../src/core/index.ts";
import {
  Administration,
  DiskStorage,
  OutputBoundary,
  activeLocation,
} from "../src/storage/index.ts";
import { removeOwned } from "../src/storage/control.ts";

function fixture(steps: unknown[] = []) {
  const root = mkdtempSync(
      join(process.env.ZARATUSTRA_TEST_ROOT ?? tmpdir(), "e3-"),
    ),
    home = join(root, "home"),
    backups = join(root, "backups"),
    output = join(root, "output");
  mkdirSync(output);
  const disk = new DiskStorage(home);
  const context: CallContext = {
    workspace_id: disk.workspace.workspace_id,
    epoch: disk.workspace.epoch,
    principal: "trusted-personal",
    session_id: "synthetic",
    runtime_id: "runtime-A",
    can_write: true,
    processing_allowed: true,
    scopes: ["restricted:read", "restricted:write"],
    approval_principal: "synthetic-controller:E3",
  };
  const core = new Core(disk, context);
  const admin = new Administration(home, backups, context);
  const source = core.capture(
    "Synthetic durable report work, no original effect yet.",
    "rpc",
    "E3-fixture",
  );
  const receipt = core.commit({
    request_id: "initial-work",
    source_handles: [source.source_handle],
    guards: [],
    reason: "Create synthetic report continuation",
    ops: [
      {
        op: "create_record",
        kind: "work",
        client_ref: "w",
        title: "Report for the observatory",
        visibility: "workspace",
        data: {
          activity_id: null,
          parent_work_id: null,
          objective: "Write the approved observatory report",
          acceptance: [
            {
              criterion_id: "file",
              description: "Report exists",
              verification: "Inspect current file bytes",
              required: true,
            },
          ],
          status: "active",
          current_state: "Report is planned",
          next_action: "Write the report",
          steps,
          waits: [],
          context_refs: [],
          completion: null,
        },
      },
    ],
  });
  return {
    root,
    home,
    backups,
    output,
    disk,
    context,
    core,
    admin,
    work: receipt.created.w,
  };
}
function grant(approvals: Core["approvals"], ref: string) {
  const p = approvals.present(ref);
  approvals.answer(p.token, true, {
    source_ref: "synthetic-decision",
    transport: "native-dialog",
    channel_identity: "registered-synthetic-controller",
    stage: "pi-confirm-return",
  });
}
function restored(f: ReturnType<typeof fixture>) {
  const disk = new DiskStorage(f.home),
    context = {
      ...f.context,
      epoch: disk.workspace.epoch,
      runtime_id: "runtime-B",
    };
  return { disk, core: new Core(disk, context) };
}
test("E3 disk finished snapshot is the sole manifest/JSON source, exact raw bytes independent of later live mutations", async (t) => {
  const f = fixture();
  t.after(() => f.disk.close());
  const material = join(f.root, "opaque.pdf");
  writeFileSync(material, Buffer.from([0, 255, 128, 37, 80, 68, 70]));
  const m = await f.disk.importMaterial(material, [f.root], () =>
    f.core.authorizeImport(),
  );
  const src = f.core.capture(m.text, "file", null, m);
  f.core.commit({
    request_id: "material",
    reason: "Retain exact opaque test bytes",
    source_handles: [src.source_handle],
    guards: [],
    ops: [
      {
        op: "import_evidence",
        client_ref: "e",
        source_handle: src.source_handle,
        title: "Opaque original",
        source_language: "unknown",
      },
    ],
  });
  const expected = f.disk.all("SELECT * FROM records ORDER BY id");
  const admin = new Administration(f.home, f.backups, f.context, (point) => {
    if (point === "after_snapshot") {
      const s = f.core.capture("Later live fact", "rpc", "E3-fixture");
      f.core.commit({
        request_id: "later",
        reason: "Post-snapshot live mutation",
        source_handles: [s.source_handle],
        guards: [],
        ops: [
          {
            op: "create_record",
            client_ref: "a",
            kind: "activity",
            title: "Later activity",
            visibility: "workspace",
            data: { purpose: "Not part of snapshot", status: "active" },
          },
        ],
      });
    }
  });
  const b = await admin.backup(f.disk),
    verified = admin.verify(b.backup);
  const db = new DatabaseSync(join(b.backup, "database.sqlite"), {
    readOnly: true,
  });
  try {
    assert.deepEqual(
      db.prepare("SELECT * FROM records ORDER BY id").all(),
      expected,
    );
  } finally {
    db.close();
  }
  assert.equal(verified.manifest.captured_seq, 2);
  assert.equal(f.core.snapshot().snapshot_seq, 3);
  assert.deepEqual(
    readFileSync(join(b.backup, "materials", m.blob_ref)),
    readFileSync(material),
  );
  removeOwned(f.home, join(f.home, "materials", m.blob_ref));
  assert.equal(
    admin.verify(b.backup).manifest.complete,
    true,
    "Independent backup survives loss of the live blob",
  );
});
test("E3 disk health restore preserves old generation and receipts, changes authoritative epoch and blocks a no-receipt Work before current bytes inspection", async (t) => {
  const f = fixture();
  t.after(() => f.disk.close());
  const b = await f.admin.backup(f.disk);
  assert.equal(
    f.disk.all(
      "SELECT * FROM intents WHERE json_extract(json,'$.kind')='managed_file'",
    ).length,
    0,
  );
  const path = join(f.output, "report.txt"),
    text = "Report already written after snapshot.\n";
  writeFileSync(path, text);
  const p = f.admin.restorePreview(
    b.backup,
    "Restore older report memory; external report remains",
    "Keep current memory",
  );
  grant(f.admin.approvals, p.preview.request_id);
  f.admin.restore(p.preview.request_id, f.disk);
  assert.equal(existsSync(join(f.home, "zara.sqlite")), true);
  assert.notEqual(activeLocation(f.home), f.home);
  assert.throws(() => f.core.read(f.work), {
    code: "RESTORE_RECONCILIATION_REQUIRED",
  });
  const next = restored(f);
  t.after(() => next.disk.close());
  assert.notEqual(next.disk.workspace.epoch, f.context.epoch);
  assert.equal(next.core.operation("initial-work").ok, true);
  assert.throws(
    () =>
      next.core.claim({
        action: "acquire",
        work_id: f.work,
        expected_revision: 1,
        reason: "Must not repeat restored next action",
      }),
    { code: "RESTORE_RECONCILIATION_REQUIRED" },
  );
  const boundary = new OutputBoundary(f.output),
    o = boundary.inspect(path, f.output),
    obs = {
      target: o.target,
      hash: o.hash,
      byte_length: o.byte_length,
      boundary: o.boundary,
    };
  next.core.recoveryInspect(f.work, null, obs);
  const r = next.core.prepareReconciliation(
    f.work,
    null,
    "observed_satisfied",
    digest(text),
    "Actual bytes satisfy current report; author unknown",
    "Accept only observed current report state",
    "Keep unknown barrier",
  );
  grant(next.core.approvals, r.request_id);
  const receipt = next.core.finishReconciliation(r.request_id, obs);
  assert.equal(receipt.ok, true);
  assert.equal(next.core.snapshot().recovery_required.length, 0);
  assert.equal(readFileSync(path, "utf8"), text);
});
test("E3 disk real missing current DB recovers via control metadata without empty replacement or old receipt", async (t) => {
  const f = fixture(),
    b = await f.admin.backup(f.disk);
  f.disk.close();
  removeOwned(f.home, join(f.home, "zara.sqlite"));
  assert.throws(() => new DiskStorage(f.home), { code: "STORE_UNAVAILABLE" });
  assert.equal(existsSync(join(f.home, "zara.sqlite")), false);
  const p = f.admin.restorePreview(
    b.backup,
    "Restore missing memory; later DB history lost",
    "Keep unavailable state",
  );
  grant(f.admin.approvals, p.preview.request_id);
  f.admin.restore(p.preview.request_id);
  assert.equal(existsSync(join(f.home, "zara.sqlite")), false);
  const next = restored(f);
  t.after(() => next.disk.close());
  assert.equal((next.core.read(f.work).data as RecordRow).id, f.work);
  assert.equal(next.core.snapshot().recovery_required[0].work_id, f.work);
});
test("E3 disk fixed full-read policy refuses before inspecting hidden data or bundle paths", async (t) => {
  const f = fixture();
  t.after(() => f.disk.close());
  const low = new Administration(f.home, "Z:/unavailable-secret-path", {
    ...f.context,
    scopes: [],
  });
  assert.throws(() => low.list(), { code: "PERMISSION_DENIED" });
  assert.throws(() => low.verify("guessed"), { code: "PERMISSION_DENIED" });
  await assert.rejects(low.backup(f.disk), { code: "PERMISSION_DENIED" });
  assert.throws(() => low.restorePreview("guessed", "Restore", "Cancel"), {
    code: "PERMISSION_DENIED",
  });
});
test("E3 disk missing/corrupt materials and modified hash/length/JSON/schema never verify complete", async (t) => {
  const f = fixture();
  t.after(() => f.disk.close());
  const b = await f.admin.backup(f.disk),
    p = join(b.backup, "export.json"),
    original = readFileSync(p);
  writeFileSync(p, "{}");
  assert.throws(() => f.admin.verify(b.backup), { code: "STORE_UNAVAILABLE" });
  writeFileSync(p, original);
  const m = JSON.parse(readFileSync(join(b.backup, "manifest.json"), "utf8"));
  m.components[0].length++;
  writeFileSync(join(b.backup, "manifest.json"), JSON.stringify(m));
  assert.throws(() => f.admin.verify(b.backup), { code: "STORE_UNAVAILABLE" });
});
test("E3 disk archive remains discoverable, all retained tombstone versions/technical payloads/index/export stop exposing old body", async (t) => {
  const f = fixture();
  t.after(() => f.disk.close());
  const s = f.core.capture("Unpinned synthetic note", "rpc", "E3-fixture"),
    secret = "UNIQUE_REMOVABLE_BODY_4729";
  const first = f.core.commit({
    request_id: "removable",
    reason: "Create removable synthetic entity",
    source_handles: [s.source_handle],
    guards: [],
    ops: [
      {
        op: "create_record",
        client_ref: "e",
        kind: "entity",
        title: "Rare optical adapter",
        body: secret,
        visibility: "workspace",
        data: {
          entity_kind: "item",
          aliases: [],
          disambiguation: secret,
          status: "active",
        },
      },
    ],
  }).created.e;
  const original = f.core.read(first).data as RecordRow;
  f.core.commit({
    request_id: "removable-v2",
    reason: "Update unpinned note",
    source_handles: [s.source_handle],
    guards: [{ ref: { id: first }, expected_revision: 1 }],
    ops: [
      {
        op: "update_record",
        ref: { id: first },
        body: secret + " v2",
        data: { ...original.data, disambiguation: secret + " v2" },
      },
    ],
  });
  const arc = f.core.storagePreview(
    { action: "archive", targets: [{ id: first, revision: 2 }] },
    "Archive adapter card; retain body",
    "Leave live",
  );
  grant(f.core.approvals, arc.request_id);
  f.core.applyStorage(arc.request_id);
  const cards = f.core.search({ query: "optical", match: "all" }).data as {
    cards: { id: string; storage: string }[];
  };
  assert.equal(cards.cards.find((c) => c.id === first)?.storage, "archive");
  const del = f.core.storagePreview(
    { action: "tombstone", targets: [{ id: first, revision: 3 }] },
    "Remove all retained adapter versions and managed payload copies",
    "Keep archived body",
  );
  grant(f.core.approvals, del.request_id);
  f.core.applyStorage(del.request_id);
  const tomb = f.core.read(first).data as RecordRow;
  assert.equal(tomb.storage, "tombstone");
  assert.equal(tomb.body, null);
  assert.equal(tomb.data.content_not_retained, true);
  for (const revision of [1, 2, 3])
    assert.throws(() => f.core.read(first, revision), {
      code: "CONTENT_NOT_RETAINED",
    });
  assert.equal(
    JSON.stringify(f.core.operation("removable")).includes(secret),
    false,
  );
  assert.equal(
    JSON.stringify(f.core.browse("history", first)).includes(secret),
    false,
  );
  assert.equal(
    JSON.stringify(
      f.core.search({
        query: "UNIQUE_REMOVABLE_BODY_4729",
        match: "all",
        history: true,
      }),
    ).includes(first),
    false,
  );
  for (const table of ["records", "revisions", "intents", "changes"])
    assert.equal(
      JSON.stringify(f.disk.all(`SELECT * FROM ${table}`)).includes(secret),
      false,
      table,
    );
  const b = await f.admin.backup(f.disk);
  assert.equal(
    readFileSync(join(b.backup, "export.json"), "utf8").includes(secret),
    false,
  );
});
test("E3 disk retained reverse dependency and explicit library pin refuse precise destructive preview; unrelated new work remains permitted", (t) => {
  const f = fixture();
  t.after(() => f.disk.close());
  const s = f.core.capture("Retain a source", "rpc", "E3-fixture");
  const e = f.core.commit({
    request_id: "pin-source",
    reason: "Keep current grounded claim",
    source_handles: [s.source_handle],
    guards: [],
    ops: [
      {
        op: "import_evidence",
        client_ref: "e",
        source_handle: s.source_handle,
        title: "Grounds",
        source_language: "en",
      },
      {
        op: "create_record",
        client_ref: "k",
        kind: "knowledge",
        title: "Grounded observation",
        visibility: "workspace",
        data: {
          knowledge_kind: "observation",
          statement: "A synthetic source was supplied",
          state: "current",
          basis: "user_statement",
          evidence_refs: [{ client_ref: "e" }],
          conditions: "Fixture",
        },
      },
    ],
  }).created.e;
  assert.throws(
    () =>
      f.core.storagePreview(
        { action: "tombstone", targets: [{ id: e, revision: 1 }] },
        "Delete source",
        "Keep",
      ),
    (err: unknown) =>
      err instanceof Error &&
      "code" in err &&
      err.code === "DEPENDENCY_UNSATISFIED" &&
      err.message.includes("knowledge-"),
  );
  assert.throws(
    () =>
      f.core.storagePreview(
        { action: "tombstone", targets: [{ id: f.work, revision: 1 }] },
        "Delete open work",
        "Keep",
      ),
    { code: "DEPENDENCY_UNSATISFIED" },
  );
  const p = f.core.storagePreview(
    { action: "retain", targets: [{ id: e, revision: 1 }] },
    "Retain library source indefinitely independent of reads",
    "Do not pin",
  );
  grant(f.core.approvals, p.request_id);
  f.core.applyStorage(p.request_id);
  assert.throws(
    () =>
      f.core.storagePreview(
        { action: "tombstone", targets: [{ id: e, revision: 1 }] },
        "Delete",
        "Keep",
      ),
    /library retention/,
  );
});
test("E3 disk cleanup protects pending sources/shared blob/history/held backup and removes only expired orphan files", async (t) => {
  const f = fixture();
  t.after(() => f.disk.close());
  const path = join(f.root, "source.md");
  writeFileSync(path, "Shared immutable source");
  const material = await f.disk.importMaterial(path, [f.root], () =>
      f.core.authorizeImport(),
    ),
    source = f.core.capture(material.text, "file", null, material);
  const before = f.admin.cleanupPreview(
    f.disk,
    "Clean only unreferenced files",
    "Keep",
  );
  assert.equal((before.payload.exact.candidates as unknown[]).length, 0);
  const r = f.core.commit({
    request_id: "shared",
    reason: "Two distinct provenance rows may share bytes",
    source_handles: [source.source_handle],
    guards: [],
    ops: [
      {
        op: "import_evidence",
        client_ref: "a",
        source_handle: source.source_handle,
        title: "Source one",
        source_language: "en",
      },
      {
        op: "import_evidence",
        client_ref: "b",
        source_handle: source.source_handle,
        title: "Source two",
        source_language: "en",
      },
    ],
  });
  const b = await f.admin.backup(f.disk, true);
  assert.ok(b.live_pin);
  const after = f.admin.cleanupPreview(
    f.disk,
    "Clean only unreferenced files",
    "Keep",
  );
  assert.equal((after.payload.exact.candidates as unknown[]).length, 0);
  const data = f.core.read(r.created.a).data as RecordRow;
  assert.equal(data.data.blob_ref, material.blob_ref);
  assert.equal(
    (f.core.read(r.created.b).data as RecordRow).data.blob_ref,
    material.blob_ref,
  );
  const orphan = join(f.disk.home, "materials", digest("orphan"));
  writeFileSync(orphan, "orphan");
  const gc = f.admin.cleanupPreview(
    f.disk,
    "Remove the one orphan",
    "Keep orphan",
  );
  assert.equal(
    (gc.payload.exact.candidates as { path: string }[])[0].path,
    orphan,
  );
  grant(f.admin.approvals, gc.request_id);
  f.admin.cleanup(gc.request_id, f.disk);
  assert.equal(existsSync(orphan), false);
  assert.equal(
    existsSync(join(f.disk.home, "materials", material.blob_ref)),
    true,
  );
  assert.equal(f.admin.verify(b.backup).manifest.complete, true);
});
test("E3 disk interrupted restore copy/verify/control switch leaves old active or a verified new generation with barriers", async (t) => {
  for (const point of [
    "restore_after_copy",
    "restore_after_verify",
    "restore_before_switch",
    "restore_after_switch",
  ]) {
    const f = fixture(),
      b = await f.admin.backup(f.disk),
      admin = new Administration(f.home, f.backups, f.context, (p) => {
        if (p === point) throw new Error("fault:" + p);
      });
    try {
      if (point === "restore_after_copy" || point === "restore_after_verify")
        assert.throws(
          () => admin.restorePreview(b.backup, "Restore test", "Keep"),
          /fault:/,
        );
      else {
        const p = admin.restorePreview(b.backup, "Restore test", "Keep");
        grant(admin.approvals, p.preview.request_id);
        assert.throws(
          () => admin.restore(p.preview.request_id, f.disk),
          /fault:/,
        );
      }
      f.disk.close();
      const next = restored(f);
      t.after(() => next.disk.close());
      assert.equal((next.core.read(f.work).data as RecordRow).id, f.work);
      assert.equal(
        next.core.snapshot().recovery_required.length,
        point === "restore_after_switch" ? 1 : 0,
      );
    } finally {
      f.disk.close();
    }
  }
});
test("E3 disk actual corrupt current DB recovers; stale bound approval and old callback cannot cross authoritative switch", async (t) => {
  const f = fixture(),
    b = await f.admin.backup(f.disk);
  f.disk.close();
  writeFileSync(join(f.home, "zara.sqlite"), "not a SQLite database");
  assert.throws(() => new DiskStorage(f.home));
  assert.equal(
    readFileSync(join(f.home, "zara.sqlite"), "utf8"),
    "not a SQLite database",
  );
  const p = f.admin.restorePreview(
    b.backup,
    "Restore corrupt memory",
    "Keep corrupt bytes",
  );
  grant(f.admin.approvals, p.preview.request_id);
  f.admin.restore(p.preview.request_id);
  assert.throws(
    () =>
      f.admin.approvals.verify(
        p.preview.request_id,
        "restore",
        p.preview.payload.exact,
      ),
    { code: "RESTORE_RECONCILIATION_REQUIRED" },
  );
  const next = restored(f);
  t.after(() => next.disk.close());
  assert.equal(next.core.snapshot().recovery_required.length, 1);
  assert.equal(
    readFileSync(join(f.home, "zara.sqlite"), "utf8"),
    "not a SQLite database",
  );
});

test("E3 disk old still-open cached reader and delayed callback reject authoritative switched control; writer conflict never switches", async (t) => {
  const f = fixture(),
    b = await f.admin.backup(f.disk),
    observer = new DiskStorage(f.home);
  t.after(() => observer.close());
  assert.equal(observer.readonly, true);
  const old = new Core(observer, {
      ...f.context,
      can_write: false,
      runtime_id: "old-reader",
    }),
    callback = () => old.read(f.work);
  const p = f.admin.restorePreview(
    b.backup,
    "Restore exact snapshot",
    "Keep current",
  );
  grant(f.admin.approvals, p.preview.request_id);
  assert.throws(() => f.admin.restore(p.preview.request_id), {
    code: "WORK_IN_USE",
  });
  assert.equal(activeLocation(f.home), f.home);
  f.admin.restore(p.preview.request_id, f.disk);
  assert.equal(
    observer.workspace.epoch,
    f.context.epoch,
    "Both old cached copies remain unchanged",
  );
  await assert.rejects(Promise.resolve().then(callback), {
    code: "RESTORE_RECONCILIATION_REQUIRED",
  });
  const next = restored(f);
  t.after(() => next.disk.close());
  assert.equal(next.core.snapshot().recovery_required.length, 1);
});
test("E3 disk per-step reconciliation does not clear another restored action, and absent output stays unknown", async (t) => {
  const f = fixture(
      ["report", "mail"].map((step_id) => ({
        step_id,
        intent: "Write " + step_id,
        status: "todo",
        depends_on: [],
        result_refs: [],
      })),
    ),
    b = await f.admin.backup(f.disk);
  const p = f.admin.restorePreview(b.backup, "Restore planned steps", "Keep");
  grant(f.admin.approvals, p.preview.request_id);
  f.admin.restore(p.preview.request_id, f.disk);
  const next = restored(f);
  t.after(() => next.disk.close());
  const boundary = new OutputBoundary(f.output),
    path = join(f.output, "report.txt");
  const missing = boundary.inspect(path, f.output);
  next.core.recoveryInspect(f.work, "report", {
    target: path,
    hash: missing.hash,
    byte_length: 0,
    boundary: missing.boundary,
  });
  assert.throws(
    () =>
      next.core.prepareReconciliation(
        f.work,
        "report",
        "observed_satisfied",
        null,
        "Missing does not prove non-execution",
        "Accept",
        "Keep unknown",
      ),
    { code: "UNKNOWN_EFFECT" },
  );
  writeFileSync(path, "Already done");
  const o = boundary.inspect(path, f.output),
    obs = {
      target: path,
      hash: o.hash,
      byte_length: o.byte_length,
      boundary: o.boundary,
    };
  next.core.recoveryInspect(f.work, "report", obs);
  const r = next.core.prepareReconciliation(
    f.work,
    "report",
    "observed_satisfied",
    digest("Already done"),
    "Observed report matches; author unknown",
    "Accept named report",
    "Keep barrier",
  );
  grant(next.core.approvals, r.request_id);
  next.core.finishReconciliation(r.request_id, obs);
  assert.throws(
    () =>
      next.core.claim({
        action: "acquire",
        work_id: f.work,
        expected_revision: 1,
        step_id: "mail",
        reason: "Uninspected second action",
      }),
    { code: "RESTORE_RECONCILIATION_REQUIRED" },
  );
  assert.equal(
    next.core.snapshot().recovery_required.some((r) => r.step_id === "mail"),
    true,
  );
});
test("E3 disk prepared quarantine byte tamper and changed current memory invalidate exact restore permission", async (t) => {
  const f = fixture();
  t.after(() => f.disk.close());
  const b = await f.admin.backup(f.disk),
    p = f.admin.restorePreview(b.backup, "Restore", "Keep");
  grant(f.admin.approvals, p.preview.request_id);
  const dir = p.destination;
  writeFileSync(join(dir, "workspace.json"), "{}");
  assert.throws(() => f.admin.restore(p.preview.request_id, f.disk), {
    code: "APPROVAL_STALE",
  });
  const next = restored(f);
  next.disk.close();
  const d = new DiskStorage(f.home),
    c = new Core(d, { ...f.context, runtime_id: "replacement" });
  t.after(() => d.close());
  const a = new Administration(f.home, f.backups, c.context),
    q = a.restorePreview(b.backup, "Restore unchanged snapshot", "Keep");
  grant(a.approvals, q.preview.request_id);
  c.capture("No domain mutation is merely a source", "rpc", "synthetic");
  const source = c.capture("New current memory", "rpc", "synthetic");
  c.commit({
    request_id: "after-preview",
    reason: "Invalidate restore loss preview",
    source_handles: [source.source_handle],
    guards: [],
    ops: [
      {
        op: "create_record",
        client_ref: "a",
        kind: "activity",
        title: "Later fact",
        visibility: "workspace",
        data: { purpose: "Current after preview", status: "active" },
      },
    ],
  });
  assert.throws(() => a.restore(q.preview.request_id, d), {
    code: "APPROVAL_STALE",
  });
});
test("E3 disk lifecycle migration faults retain filled schema5 data and consistent backup; missing both known active files never creates empty memory", (t) => {
  for (const point of [
    "lifecycle_after_backup",
    "lifecycle_before_schema_commit",
    "lifecycle_after_schema_commit",
  ]) {
    const f = fixture();
    const rows = f.disk.all("SELECT * FROM records");
    f.disk.exec(
      "DROP TABLE lifecycle_pins; DROP TABLE lifecycle_events; DROP TABLE recovery_barriers; PRAGMA user_version=5;",
    );
    f.disk.workspace.schema_version = 5;
    f.disk.run("UPDATE meta SET json=?", JSON.stringify(f.disk.workspace));
    writeFileSync(
      join(f.home, "workspace.json"),
      JSON.stringify(f.disk.workspace),
    );
    f.disk.close();
    assert.throws(
      () =>
        new DiskStorage(f.home, (p) => {
          if (p === point) throw new Error("migration fault");
        }),
      /migration fault/,
    );
    const next = new DiskStorage(f.home);
    t.after(() => next.close());
    assert.equal(next.workspace.schema_version, 6);
    assert.deepEqual(next.all("SELECT * FROM records"), rows);
    const receipt = JSON.parse(
      next.get<{ json: string }>("SELECT json FROM migrations WHERE version=6")!
        .json,
    );
    assert.equal(digest(readFileSync(receipt.backup)), receipt.backup_sha256);
  }
  const f = fixture();
  f.disk.close();
  removeOwned(f.home, join(f.home, "zara.sqlite"));
  removeOwned(f.home, join(f.home, "workspace.json"));
  assert.throws(() => new DiskStorage(f.home), { code: "STORE_UNAVAILABLE" });
  assert.equal(existsSync(join(f.home, "zara.sqlite")), false);
});
test("E3 disk import expiry/crash orphan staging and fresh pin changes are respected by exact cleanup", async (t) => {
  const f = fixture();
  t.after(() => f.disk.close());
  const path = join(f.root, "pending.md");
  writeFileSync(path, "Pending until commit or expiry");
  const m = await f.disk.importMaterial(path, [f.root], () =>
      f.core.authorizeImport(),
    ),
    s = f.core.capture(m.text, "file", null, m);
  const now = Date.now;
  try {
    Date.now = () => now() + 1800001;
    assert.throws(
      () =>
        f.core.commit({
          request_id: "expired",
          source_handles: [s.source_handle],
          guards: [],
          reason: "Expired source must not commit",
          ops: [
            {
              op: "import_evidence",
              client_ref: "e",
              source_handle: s.source_handle,
              title: "Expired",
              source_language: "en",
            },
          ],
        }),
      { code: "SOURCE_EXPIRED" },
    );
    const gc = f.admin.cleanupPreview(
      f.disk,
      "Remove expired pending orphan",
      "Keep",
    );
    assert.ok((gc.payload.exact.candidates as unknown[]).length > 0);
    grant(f.admin.approvals, gc.request_id);
    f.disk.pinSource("new-pending-operation", [m.blob_ref]);
    assert.throws(() => f.admin.cleanup(gc.request_id, f.disk), {
      code: "APPROVAL_STALE",
    });
    assert.equal(existsSync(join(f.home, "materials", m.blob_ref)), true);
  } finally {
    Date.now = now;
  }
});
test("E3 disk known restored requested attempt is unknown until actual readback, and its receipt alone does not clear the Work barrier", async (t) => {
  const f = fixture(),
    path = join(f.output, "known.txt"),
    text = "Known interrupted file\n",
    boundary = new OutputBoundary(f.output),
    before = boundary.inspect(path, f.output);
  const effect: FileEffect = {
    request_id: "known-attempt",
    tool: "write",
    arguments: { path, content: text },
    target: path,
    boundary: before.boundary,
    before_hash: null,
    before_length: 0,
    final_hash: digest(text),
    final_length: Buffer.byteLength(text),
    final_text: text,
    work_ref: { id: f.work, revision: 1 },
    step_id: null,
    independent_basis: null,
    method_export: null,
    retry_of: null,
    retry_risk: null,
  };
  const p = f.core.prepareFile(effect, "Write synthetic report", "Keep absent");
  grant(f.core.approvals, p.request_id);
  f.core.dispatchFile(
    p.payload.exact as FileEffect,
    p.request_id,
    "native-fixture-call",
  );
  writeFileSync(path, text);
  const b = await f.admin.backup(f.disk),
    q = f.admin.restorePreview(
      b.backup,
      "Restore known interrupted action",
      "Keep current",
    );
  grant(f.admin.approvals, q.preview.request_id);
  f.admin.restore(q.preview.request_id, f.disk);
  const next = restored(f);
  t.after(() => next.disk.close());
  next.core.interruptFiles("new restored process", true);
  assert.equal(next.core.inspectFile("known-attempt").status, "unknown");
  const o = boundary.inspect(path, f.output);
  next.core.observeFile("known-attempt", {
    hash: o.hash,
    byte_length: o.byte_length,
    boundary: o.boundary,
  });
  assert.equal(
    next.core.inspectFile("known-attempt").receipt?.writer_attribution,
    "unknown",
  );
  assert.throws(
    () =>
      next.core.claim({
        action: "acquire",
        work_id: f.work,
        expected_revision: 1,
        reason: "Receipt cannot globally clear restored work",
      }),
    { code: "RESTORE_RECONCILIATION_REQUIRED" },
  );
});
test("E3 disk actual missing/corrupt source blobs refuse backup; actual ref/schema/SQLite faults refuse digest-correct bundles", async (t) => {
  for (const fault of ["missing", "corrupt"]) {
    const f = fixture();
    t.after(() => f.disk.close());
    const path = join(f.root, "source.md");
    writeFileSync(path, "Required exact material");
    const m = f.disk.importFile(path, [f.root]),
      s = f.core.capture(m.text, "file", null, m);
    f.core.commit({
      request_id: "retain",
      reason: "Retain required material",
      source_handles: [s.source_handle],
      guards: [],
      ops: [
        {
          op: "import_evidence",
          client_ref: "e",
          source_handle: s.source_handle,
          title: "Required material",
          source_language: "en",
        },
      ],
    });
    const blob = join(f.disk.home, "materials", m.blob_ref);
    if (fault === "missing") removeOwned(f.disk.home, blob);
    else writeFileSync(blob, "Changed corrupt bytes");
    await assert.rejects(f.admin.backup(f.disk));
  }
  for (const fault of ["ref", "schema", "sqlite"]) {
    const f = fixture();
    t.after(() => f.disk.close());
    const b = await f.admin.backup(f.disk),
      path = join(b.backup, "database.sqlite");
    if (fault === "sqlite") writeFileSync(path, Buffer.alloc(400, 65));
    else {
      const db = new DatabaseSync(path);
      db.exec("PRAGMA journal_mode=DELETE;");
      if (fault === "schema") db.exec("PRAGMA user_version=999;");
      else {
        const row = JSON.parse(
          String(
            db.prepare("SELECT json FROM records WHERE id=?").get(f.work)!.json,
          ),
        );
        row.data.context_refs = [{ id: "nonexistent-ref" }];
        db.prepare("UPDATE records SET json=? WHERE id=?").run(
          JSON.stringify(row),
          f.work,
        );
      }
      db.close();
    }
    const manifestPath = join(b.backup, "manifest.json"),
      manifest = JSON.parse(readFileSync(manifestPath, "utf8")),
      bytes = readFileSync(path);
    Object.assign(
      manifest.components.find(
        (c: { path: string }) => c.path === "database.sqlite",
      ),
      { length: bytes.length, sha256: digest(bytes) },
    );
    writeFileSync(manifestPath, JSON.stringify(manifest));
    assert.throws(() => f.admin.verify(b.backup));
  }
});

test("E3 disk actual PDF/EPUB raw originals and extracted derivatives bundle independently and selected body deletion covers both versions", async (t) => {
  for (const format of ["pdf", "epub"]) {
    const f = fixture();
    t.after(() => f.disk.close());
    const path = join(f.root, "book." + format),
      bytes = readFileSync(
        join(process.cwd(), "tests/fixtures/c/book." + format),
      );
    writeFileSync(path, bytes);
    const m = await f.disk.importMaterial(path, [f.root], () =>
        f.core.authorizeImport(),
      ),
      s = f.core.capture(m.text, "file", null, m),
      r = f.core.commit({
        request_id: "book",
        reason: "Preserve exact managed raw and extracted bytes",
        source_handles: [s.source_handle],
        guards: [],
        ops: [
          {
            op: "import_evidence",
            client_ref: "e",
            source_handle: s.source_handle,
            title: "Synthetic " + format,
            source_language: "en",
          },
        ],
      });
    assert.ok(r.created.e_text);
    const b = await f.admin.backup(f.disk);
    assert.deepEqual(
      readFileSync(join(b.backup, "materials", m.blob_ref)),
      bytes,
    );
    const hash = m.extraction!.text_blob_ref!;
    assert.deepEqual(
      readFileSync(join(b.backup, "materials", hash)),
      f.disk.readBlob(hash),
    );
    const p = f.core.storagePreview(
      {
        action: "tombstone",
        targets: [r.created.e, r.created.e_text].map((id) => ({
          id,
          revision: 1,
        })),
      },
      "Remove both unpinned retained bodies; independent earlier bundle remains separate",
      "Keep bodies",
    );
    grant(f.core.approvals, p.request_id);
    f.core.applyStorage(p.request_id);
    for (const id of [r.created.e, r.created.e_text])
      assert.throws(() => f.core.read(id, 1, { start: 0, length: 100 }), {
        code: "CONTENT_NOT_RETAINED",
      });
    const after = await f.admin.backup(f.disk);
    assert.equal(
      f.admin
        .verify(after.backup)
        .manifest.components.some((c) => c.path.startsWith("materials/")),
      false,
    );
    assert.equal(f.admin.verify(b.backup).manifest.complete, true);
    const cleanup = f.admin.cleanupPreview(
      f.disk,
      "Only now-unreferenced managed raw/derivative copies",
      "Keep",
    );
    assert.ok((cleanup.payload.exact.candidates as unknown[]).length > 0);
  }
});

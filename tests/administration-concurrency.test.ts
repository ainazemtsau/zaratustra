import test from "node:test";
import assert from "node:assert/strict";
import { randomUUID } from "node:crypto";
import {
  existsSync,
  mkdtempSync,
  mkdirSync,
  readFileSync,
  readdirSync,
  rmSync,
  writeFileSync,
} from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { DatabaseSync } from "node:sqlite";
import { Core } from "../src/core/index.ts";
import type { CallContext } from "../src/core/index.ts";
import {
  Administration,
  DiskStorage,
  activeLocation,
  readControl,
} from "../src/storage/index.ts";
import { Coordination } from "../src/storage/coordination.ts";
import { bytesHash } from "../src/storage/control.ts";

function fixture() {
  const root = mkdtempSync(
    join(
      process.env.ZARATUSTRA_TEST_ROOT ?? tmpdir(),
      "administration-concurrent-",
    ),
  );
  const home = join(root, "home"),
    backups = join(root, "backups"),
    disk = new DiskStorage(home);
  const context: CallContext = {
    workspace_id: disk.workspace.workspace_id,
    epoch: disk.workspace.epoch,
    principal: "trusted-personal",
    session_id: "synthetic-administration",
    runtime_id: disk.coordination.runtimeId,
    can_write: true,
    processing_allowed: true,
    scopes: ["restricted:read", "restricted:write"],
    approval_principal: "synthetic-controller",
  };
  const core = new Core(disk, context),
    admin = new Administration(home, backups, context);
  return { root, home, backups, disk, context, core, admin };
}
function createActivity(f: ReturnType<typeof fixture>, suffix: string) {
  const source = f.core.capture(
    "Synthetic administration test " + suffix,
    "rpc",
    "synthetic-controller",
  );
  return f.core.commit({
    request_id: "activity-" + suffix,
    source_handles: [source.source_handle],
    guards: [],
    reason: "Create synthetic committed state",
    ops: [
      {
        op: "create_record",
        client_ref: "activity",
        kind: "activity",
        title: "Activity " + suffix,
        visibility: "workspace",
        data: {
          purpose: "Administration concurrency fixture",
          status: "active",
        },
      },
    ],
  }).created.activity;
}
function grant(admin: Administration, ref: string) {
  const presentation = admin.approvals.present(ref);
  admin.approvals.answer(presentation.token, true, {
    source_ref: "synthetic-decision",
    transport: "native-dialog",
    channel_identity: "synthetic-controller",
    stage: "pi-confirm-return",
  });
}
function unknown(f: ReturnType<typeof fixture>, resource: string) {
  const foreign = new Coordination(f.home, "test-" + randomUUID(), {
    expectedId: f.disk.coordination.identity,
  });
  const operation_id = "document-" + randomUUID();
  foreign.sync("mutate", () => {
    foreign.reserve({
      operation_id,
      epoch: f.context.epoch,
      kind: "document",
      digest: resource,
      resources: [resource],
      metadata: { target: resource, independent_document: true },
    });
    foreign.phase(operation_id, "dispatching");
  });
  foreign.close({ poisonUnknown: true });
  return operation_id;
}

test("restore preview ignores retrieval traces and physical WAL changes, but a committed domain change requires fresh confirmation", async (t) => {
  const f = fixture();
  t.after(() => f.disk.close());
  const id = createActivity(f, "before"),
    saved = await f.admin.backup(f.disk);
  const preview = f.admin.restorePreview(
    saved.backup,
    "Restore synthetic snapshot",
    "Keep current synthetic state",
  );
  grant(f.admin, preview.preview.request_id);
  const before = f.disk.get<{ state_revision: number }>(
    "SELECT state_revision FROM concurrency_meta",
  )!.state_revision;
  f.core.read(id);
  f.core.map();
  assert.ok(f.disk.all("SELECT * FROM retrieval_trace").length > 0);
  assert.equal(
    f.disk.get<{ state_revision: number }>(
      "SELECT state_revision FROM concurrency_meta",
    )!.state_revision,
    before,
  );
  assert.equal(
    f.admin.restore(preview.preview.request_id, f.disk).switched,
    true,
  );

  const current = new DiskStorage(f.home);
  t.after(() => current.close());
  const context = {
    ...f.context,
    epoch: current.workspace.epoch,
    runtime_id: current.coordination.runtimeId,
  };
  const next = {
    ...f,
    disk: current,
    context,
    core: new Core(current, context),
    admin: new Administration(f.home, f.backups, context),
  };
  const pending = next.admin.restorePreview(
    saved.backup,
    "Restore again",
    "Keep later commits",
  );
  grant(next.admin, pending.preview.request_id);
  createActivity(next, "later");
  assert.throws(() => next.admin.restore(pending.preview.request_id, current), {
    code: "APPROVAL_STALE",
  });
  assert.equal(current.connectionClosed, false);
});

test("backup metadata and restore retain historical plus current unknown independent-document resources", async (t) => {
  const f = fixture();
  t.after(() => f.disk.close());
  createActivity(f, "unknown");
  const historical = unknown(f, "document:historical-independent");
  const saved = await f.admin.backup(f.disk);
  const verified = f.admin.verify(saved.backup);
  assert.equal(verified.manifest.schema, 9);
  assert.ok(
    verified.manifest.coordination?.pending.some(
      (operation) => operation.operation_id === historical,
    ),
  );
  assert.ok(
    !readdirSync(saved.backup).some((name) =>
      /coordination|runtime|lease/.test(name),
    ),
  );
  f.disk.coordination.sync("mutate", () => {
    f.disk.coordination.adopt(historical);
    f.disk.coordination.release(historical);
  });
  const current = unknown(f, "document:current-independent");
  const preview = f.admin.restorePreview(
    saved.backup,
    "Restore with retained unknown resources",
    "Keep current state",
  );
  grant(f.admin, preview.preview.request_id);
  f.admin.restore(preview.preview.request_id, f.disk);
  const next = new DiskStorage(f.home);
  t.after(() => next.close());
  assert.equal(
    next.coordination.identity,
    verified.manifest.coordination
      ? readControl(f.home)?.coordination_id
      : "missing",
  );
  const pending = next.coordination.sync("read", () =>
    next.coordination.pending(),
  );
  for (const operation_id of [historical, current])
    assert.equal(
      pending.find((operation) => operation.operation_id === operation_id)
        ?.status,
      "unknown",
    );
  for (const resource of [
    "document:historical-independent",
    "document:current-independent",
  ])
    assert.throws(
      () =>
        next.coordination.sync("mutate", () =>
          next.coordination.reserve({
            operation_id: "repeat-" + randomUUID(),
            epoch: next.workspace.epoch,
            kind: "document",
            digest: resource,
            resources: [resource],
          }),
        ),
      { code: "STORE_BUSY" },
    );
});

test("restore draining admits an existing settler and rejects new mutation before the generation switch", async (t) => {
  const f = fixture();
  t.after(() => f.disk.close());
  const saved = await f.admin.backup(f.disk);
  const preview = f.admin.restorePreview(
    saved.backup,
    "Restore after native action settles",
    "Keep current state",
  );
  grant(f.admin, preview.preview.request_id);
  const worker = new Coordination(f.home, "test-" + randomUUID(), {
    expectedId: f.disk.coordination.identity,
  });
  t.after(() => worker.close({ poisonUnknown: true }));
  const id = "live-" + randomUUID();
  worker.sync("mutate", () =>
    worker.reserve({
      operation_id: id,
      epoch: f.context.epoch,
      kind: "document",
      digest: "live-document",
      resources: ["document:live"],
    }),
  );
  let fenced = false;
  const settle = new Promise<void>((resolve, reject) =>
    setTimeout(() => {
      try {
        assert.throws(() => worker.sync("mutate", () => undefined), {
          code: "STORE_BUSY",
        });
        fenced = true;
        worker.sync("settle", () => worker.release(id), { operationId: id });
        resolve();
      } catch (error) {
        reject(error);
      }
    }, 20),
  );
  const result = await f.admin.restoreWhenDrained(
    preview.preview.request_id,
    f.disk,
    1000,
  );
  await settle;
  assert.equal(fenced, true);
  assert.equal(result.switched, true);
});

test("restore returns bounded STORE_BUSY for a live reservation and leaves its generation and permission intact", async (t) => {
  const f = fixture();
  t.after(() => f.disk.close());
  const saved = await f.admin.backup(f.disk),
    preview = f.admin.restorePreview(saved.backup, "Restore", "Keep");
  grant(f.admin, preview.preview.request_id);
  const worker = new Coordination(f.home, "test-" + randomUUID(), {
    expectedId: f.disk.coordination.identity,
  });
  const id = "live-" + randomUUID();
  worker.sync("mutate", () =>
    worker.reserve({
      operation_id: id,
      epoch: f.context.epoch,
      kind: "document",
      digest: "busy",
      resources: ["document:busy"],
    }),
  );
  try {
    await assert.rejects(
      f.admin.restoreWhenDrained(preview.preview.request_id, f.disk, 30),
      { code: "STORE_BUSY" },
    );
    assert.equal(activeLocation(f.home), f.home);
    assert.equal(
      f.admin.approvals.read(preview.preview.request_id).status,
      "approved-transient",
    );
    worker.sync("settle", () => worker.release(id), { operationId: id });
    assert.equal(
      f.admin.restore(preview.preview.request_id, f.disk).switched,
      true,
    );
  } finally {
    worker.close({ poisonUnknown: true });
  }
});

for (const damage of ["missing", "corrupt"] as const)
  test(
    "stable coordination permits verified restore with " +
      damage +
      " current DB",
    async (t) => {
      const f = fixture();
      createActivity(f, damage);
      const saved = await f.admin.backup(f.disk),
        identity = f.disk.coordination.identity;
      f.disk.close();
      if (damage === "missing") rmSync(join(f.home, "zara.sqlite"));
      else
        writeFileSync(
          join(f.home, "zara.sqlite"),
          "synthetic corrupt database",
        );
      const preview = f.admin.restorePreview(
        saved.backup,
        "Recover synthetic damaged DB",
        "Preserve unavailable state",
      );
      grant(f.admin, preview.preview.request_id);
      assert.equal(f.admin.restore(preview.preview.request_id).switched, true);
      const next = new DiskStorage(f.home);
      t.after(() => next.close());
      assert.equal(next.coordination.identity, identity);
      assert.equal(next.workspace.schema_version, 9);
      assert.equal(next.all("SELECT id FROM records").length, 1);
      assert.equal(
        existsSync(join(f.home, "zara.sqlite")),
        damage !== "missing",
      );
    },
  );

test("schema-8 immutable bundles remain verifiable and quarantine upgrades them to schema 9", async (t) => {
  const f = fixture();
  t.after(() => f.disk.close());
  createActivity(f, "legacy");
  const saved = await f.admin.backup(f.disk),
    path = join(saved.backup, "database.sqlite"),
    db = new DatabaseSync(path);
  const derived = [
    "concurrency_meta",
    "memory_index_meta",
    "memory_ordinals",
    "memory_nodes",
    "memory_edges",
    "memory_dirty",
    "memory_technical",
    "memory_pending",
  ];
  try {
    for (const row of db
      .prepare("SELECT name FROM sqlite_schema WHERE type='trigger'")
      .all())
      if (/^(concurrency_|memory_dirty_)/.test(String(row.name)))
        db.exec(
          'DROP TRIGGER "' + String(row.name).replaceAll('"', '""') + '"',
        );
    db.exec(
      "DROP INDEX IF EXISTS memory_access_restricted; DROP INDEX IF EXISTS sleep_prior_item;",
    );
    db.prepare("DELETE FROM migrations WHERE version>8").run();
    for (const table of derived) db.exec("DROP TABLE " + table);
    const workspace = JSON.parse(
      String(db.prepare("SELECT json FROM meta").get()!.json),
    );
    db.prepare("UPDATE meta SET json=?").run(
      JSON.stringify({ ...workspace, schema_version: 8 }),
    );
    db.exec("PRAGMA user_version=8");
  } finally {
    db.close();
  }
  const exported = JSON.parse(
    readFileSync(join(saved.backup, "export.json"), "utf8"),
  );
  exported.schema = 8;
  exported.tables.migrations = exported.tables.migrations.filter(
    (row: { version: number }) => row.version <= 8,
  );
  for (const table of derived) delete exported.tables[table];
  writeFileSync(join(saved.backup, "export.json"), JSON.stringify(exported));
  const manifest = JSON.parse(
    readFileSync(join(saved.backup, "manifest.json"), "utf8"),
  );
  manifest.schema = 8;
  delete manifest.coordination;
  for (const component of manifest.components) {
    const bytes = readFileSync(join(saved.backup, component.path));
    component.length = bytes.length;
    component.sha256 = bytesHash(bytes);
  }
  writeFileSync(join(saved.backup, "manifest.json"), JSON.stringify(manifest));
  assert.equal(f.admin.verify(saved.backup).manifest.schema, 8);
  const preview = f.admin.restorePreview(
    saved.backup,
    "Restore old synthetic schema",
    "Keep current schema",
  );
  const quarantine = new DatabaseSync(
    join(preview.destination, "zara.sqlite"),
    { readOnly: true },
  );
  try {
    assert.equal(
      quarantine.prepare("PRAGMA user_version").get()!.user_version,
      9,
    );
  } finally {
    quarantine.close();
  }
  grant(f.admin, preview.preview.request_id);
  f.admin.restore(preview.preview.request_id, f.disk);
  const next = new DiskStorage(f.home);
  t.after(() => next.close());
  assert.equal(next.workspace.schema_version, 9);
  assert.equal(next.all("SELECT id FROM records").length, 1);
});

test("backup records an operation created and settled inside the snapshot window without copying live coordination files", async (t) => {
  const f = fixture();
  t.after(() => f.disk.close());
  const foreign = new Coordination(f.home, "test-" + randomUUID(), {
    expectedId: f.disk.coordination.identity,
  });
  t.after(() => foreign.close({ poisonUnknown: true }));
  const id = "snapshot-window-" + randomUUID();
  const admin = new Administration(f.home, f.backups, f.context, (point) => {
    if (point !== "after_snapshot") return;
    foreign.sync("mutate", () => {
      foreign.reserve({
        operation_id: id,
        epoch: f.context.epoch,
        kind: "document",
        digest: "window",
        resources: ["document:snapshot-window-independent"],
      });
      foreign.phase(id, "dispatching");
      foreign.release(id);
    });
  });
  const saved = await admin.backup(f.disk),
    verified = admin.verify(saved.backup);
  assert.equal(
    verified.manifest.coordination?.pending.find(
      (operation) => operation.operation_id === id,
    )?.status,
    "settled",
  );
  const snapshot = new DatabaseSync(join(saved.backup, "database.sqlite"), {
    readOnly: true,
  });
  try {
    assert.equal(
      snapshot
        .prepare(
          "SELECT count(*) AS n FROM lifecycle_pins WHERE json_extract(json,'$.kind')='backup-all'",
        )
        .get()!.n,
      0,
    );
  } finally {
    snapshot.close();
  }
  const preview = admin.restorePreview(
    saved.backup,
    "Restore captured pending interval",
    "Keep current state",
  );
  grant(admin, preview.preview.request_id);
  admin.restore(preview.preview.request_id, f.disk);
  const next = new DiskStorage(f.home);
  t.after(() => next.close());
  assert.equal(
    next.coordination.sync("read", () => next.coordination.operation(id))
      ?.status,
    "unknown",
  );
});

test("cleanup cancels only an abandoned all-materials backup pin after proof of dead runtime and keeps completed retention pins", async (t) => {
  const f = fixture();
  t.after(() => f.disk.close());
  const held = await f.admin.backup(f.disk, true);
  const foreign = new Coordination(f.home, "test-" + randomUUID(), {
    expectedId: f.disk.coordination.identity,
  });
  const id = "abandoned-backup-" + randomUUID(),
    candidate = join(f.backups, "backup-" + randomUUID());
  mkdirSync(candidate);
  writeFileSync(
    join(candidate, "database.sqlite"),
    "unsealed synthetic candidate",
  );
  foreign.sync("mutate", () =>
    foreign.reserve({
      operation_id: id,
      epoch: f.context.epoch,
      kind: "backup",
      digest: bytesHash(candidate),
      resources: ["backup:" + candidate],
    }),
  );
  f.disk.run(
    "INSERT INTO lifecycle_pins VALUES(?,?)",
    id,
    JSON.stringify({
      kind: "backup-all",
      operation_id: id,
      bundle: candidate,
      expires_at: null,
    }),
  );
  assert.throws(
    () => f.admin.cleanupPreview(f.disk, "Clean synthetic files", "Keep"),
    { code: "WORK_IN_USE" },
  );
  assert.ok(f.disk.get("SELECT key FROM lifecycle_pins WHERE key=?", id));
  foreign.close({ poisonUnknown: true });
  f.admin.cleanupPreview(f.disk, "Clean after dead backup capture", "Keep");
  assert.equal(
    f.disk.get("SELECT key FROM lifecycle_pins WHERE key=?", id),
    undefined,
  );
  assert.ok(
    f.disk.get("SELECT key FROM lifecycle_pins WHERE key=?", held.live_pin),
  );
  assert.equal(
    f.disk.coordination.sync("read", () => f.disk.coordination.operation(id))
      ?.status,
    "settled",
  );
  assert.equal(
    JSON.parse(readFileSync(join(candidate, "INCOMPLETE.json"), "utf8"))
      .complete,
    false,
  );
  assert.equal(
    readFileSync(join(candidate, "database.sqlite"), "utf8"),
    "unsealed synthetic candidate",
  );
});

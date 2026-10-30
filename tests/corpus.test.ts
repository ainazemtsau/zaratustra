import test from "node:test";
import assert from "node:assert/strict";
import { DatabaseSync } from "node:sqlite";
import { spawnSync } from "node:child_process";
import {
  mkdtempSync,
  mkdirSync,
  readFileSync,
  writeFileSync,
  readdirSync,
  unlinkSync,
  cpSync,
  renameSync,
  symlinkSync,
  existsSync,
} from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { FileCorpus, DiskStorage, readControl } from "../src/storage/index.ts";
import { bytesHash } from "../src/storage/control.ts";

function fixture() {
  const root = mkdtempSync(join(tmpdir(), "zara-corpus-v1-"));
  const home = join(root, "runtime");
  mkdirSync(home);
  const db = new DatabaseSync(":memory:");
  db.exec(
    "CREATE TABLE meta(json TEXT NOT NULL); CREATE TABLE records(id TEXT PRIMARY KEY,kind TEXT,activity_id TEXT,json TEXT); CREATE TABLE revisions(id TEXT,revision INTEGER,json TEXT,PRIMARY KEY(id,revision));",
  );
  db.prepare("INSERT INTO meta VALUES(?)").run(
    JSON.stringify({
      workspace_id: "synthetic-workspace",
      epoch: "synthetic-epoch",
      schema_version: 10,
    }),
  );
  const corpus = new FileCorpus(join(root, "memory"));
  corpus.publish(db, home, true);
  return { root, home, db, corpus };
}
function put(
  f: ReturnType<typeof fixture>,
  id: string,
  text: string,
  revision = 1,
) {
  const json = JSON.stringify({
    id,
    revision,
    kind: "evidence",
    data: { retained_excerpt: text },
  });
  f.db
    .prepare(
      "INSERT INTO records VALUES(?,'evidence',NULL,?) ON CONFLICT(id) DO UPDATE SET json=excluded.json",
    )
    .run(id, json);
  f.db.prepare("INSERT INTO revisions VALUES(?,?,?)").run(id, revision, json);
}

test("canonical rows retain exact prior revisions and rebuild without original SQLite", () => {
  const f = fixture();
  try {
    put(f, "source", "русский🙂\r\n".repeat(40000));
    f.corpus.publish(f.db, f.home);
    const old = String(f.db.prepare("SELECT json FROM revisions").get()!.json);
    put(f, "source", "new text", 2);
    f.corpus.publish(f.db, f.home);
    const restored = new DatabaseSync(":memory:");
    restored.exec(
      "CREATE TABLE meta(json TEXT); CREATE TABLE records(id TEXT PRIMARY KEY,kind TEXT,activity_id TEXT,json TEXT); CREATE TABLE revisions(id TEXT,revision INTEGER,json TEXT,PRIMARY KEY(id,revision)); CREATE TABLE corpus_projection(singleton INTEGER PRIMARY KEY,revision INTEGER); INSERT INTO corpus_projection VALUES(1,0); CREATE TABLE corpus_dirty(collection TEXT,identity TEXT);",
    );
    f.corpus.restoreRows(restored);
    assert.equal(
      restored.prepare("SELECT json FROM revisions WHERE revision=1").get()!
        .json,
      old,
    );
    assert.equal(
      restored.prepare("SELECT count(*) AS n FROM revisions").get()!.n,
      2,
    );
    const inventory = f.corpus.checkpoint();
    assert.ok(inventory.files.every((x) => x.length <= 8 * 1024 * 1024));
    assert.ok(
      inventory.files
        .filter((x) => x.path.startsWith("objects/"))
        .every((x) => x.length <= 256 * 1024),
    );
    restored.close();
  } finally {
    f.db.close();
  }
});

for (const point of [
  "corpus_after_file",
  "corpus_before_marker",
  "corpus_after_marker",
  "corpus_after_retire",
  "corpus_during_cleanup",
]) {
  test("filesystem recovery after " + point, () => {
    const f = fixture();
    try {
      const before = f.corpus.status().revision;
      put(f, "case", "retained bytes");
      let fired = false;
      const interrupted = new FileCorpus(f.corpus.root, (p) => {
        if (!fired && p === point) {
          fired = true;
          throw new Error("synthetic crash");
        }
      });
      assert.throws(() => interrupted.publish(f.db, f.home), /synthetic crash/);
      assert.equal(fired, true);
      const recovered = new FileCorpus(f.corpus.root);
      recovered.recover();
      const committed = [
        "corpus_after_marker",
        "corpus_after_retire",
        "corpus_during_cleanup",
      ].includes(point);
      assert.equal(recovered.status().revision, before + (committed ? 1 : 0));
      assert.equal(recovered.rows().get("records")!.length, committed ? 1 : 0);
      recovered.checkpoint();
    } finally {
      f.db.close();
    }
  });
}

test("missing canonical row fails membership verification rather than rebuilding partial data", () => {
  const f = fixture();
  try {
    put(f, "selected", "original");
    f.corpus.publish(f.db, f.home);
    const folder = join(f.corpus.root, "objects", "records");
    unlinkSync(join(folder, readdirSync(folder)[0]));
    assert.throws(() => f.corpus.rows());
  } finally {
    f.db.close();
  }
});

test("referenced raw material survives a fresh local projection", () => {
  const f = fixture();
  try {
    const bytes = Buffer.from("exact\r\noriginal 🙂"),
      hash = bytesHash(bytes);
    mkdirSync(join(f.home, "materials"));
    writeFileSync(join(f.home, "materials", hash), bytes);
    const json = JSON.stringify({ data: { blob_ref: hash } });
    f.db
      .prepare("INSERT INTO records VALUES('material','evidence',NULL,?)")
      .run(json);
    f.corpus.publish(f.db, f.home);
    const target = join(f.root, "rebuilt");
    mkdirSync(target);
    f.corpus.restoreMaterials(target);
    assert.deepEqual(readFileSync(join(target, "materials", hash)), bytes);
  } finally {
    f.db.close();
  }
});

test("fresh clone opens corpus with new local control and a new reconciliation epoch", () => {
  const root = mkdtempSync(join(tmpdir(), "zara-clone-")),
    firstRoot = join(root, "first"),
    secondRoot = join(root, "second");
  mkdirSync(firstRoot);
  mkdirSync(secondRoot);
  const disk = new DiskStorage(join(firstRoot, "runtime"), undefined, {
    projectRoot: firstRoot,
  });
  const prior = { ...disk.workspace };
  disk.close();
  cpSync(join(firstRoot, "memory"), join(secondRoot, "memory"), {
    recursive: true,
  });
  const clone = new DiskStorage(join(secondRoot, "runtime"), undefined, {
    projectRoot: secondRoot,
  });
  try {
    assert.equal(clone.workspace.workspace_id, prior.workspace_id);
    assert.notEqual(clone.workspace.epoch, prior.epoch);
    assert.equal(readControl(clone.controlHome)?.format, 3);
    assert.equal(clone.workspace.schema_version, 10);
    clone.corpusCheckpoint();
  } finally {
    clone.close();
  }
});

for (const point of [
  "corpus_activation_prepared",
  "corpus_activation_sql_committed",
  "corpus_before_marker",
  "corpus_after_marker",
]) {
  test("activation restarts after " + point, () => {
    const root = mkdtempSync(join(tmpdir(), "zara-activation-")),
      home = join(root, "runtime");
    let fired = false;
    assert.throws(
      () =>
        new DiskStorage(home, undefined, {
          projectRoot: root,
          corpusFault: (p) => {
            if (p === point && !fired) {
              fired = true;
              throw new Error("activation crash");
            }
          },
        }),
      /activation crash/,
    );
    const reopened = new DiskStorage(home, undefined, { projectRoot: root });
    try {
      assert.equal(reopened.workspace.schema_version, 10);
      assert.equal(readControl(home)?.format, 3);
      reopened.corpusCheckpoint();
    } finally {
      reopened.close();
    }
  });
}

test("edited canonical row is rejected before SQL can overwrite the source", () => {
  const f = fixture();
  try {
    put(f, "drift", "original");
    f.corpus.publish(f.db, f.home);
    f.corpus.checkpoint();
    const folder = join(f.corpus.root, "objects", "records"),
      path = join(folder, readdirSync(folder)[0]);
    writeFileSync(path, "external unaccepted edit");
    f.db.prepare("UPDATE records SET json=?").run(
      JSON.stringify({
        id: "drift",
        revision: 2,
        data: { retained_excerpt: "overwrite" },
      }),
    );
    assert.throws(() => f.corpus.publish(f.db, f.home));
    assert.equal(readFileSync(path, "utf8"), "external unaccepted edit");
  } finally {
    f.corpus.close();
    f.db.close();
  }
});

test("foreign projection with equal revision is rebuilt using corpus identity", () => {
  const root = mkdtempSync(join(tmpdir(), "zara-projection-identity-")),
    home = join(root, "runtime");
  const first = new DiskStorage(home, undefined, { projectRoot: root });
  const identity = { ...first.workspace };
  first.close();
  const db = new DatabaseSync(join(home, "zara.sqlite"));
  db.prepare("UPDATE meta SET json=?").run(
    JSON.stringify({ ...identity, workspace_id: "foreign-workspace" }),
  );
  db.close();
  const repaired = new DiskStorage(home, undefined, { projectRoot: root });
  try {
    assert.equal(
      JSON.parse(repaired.get<{ json: string }>("SELECT json FROM meta")!.json)
        .workspace_id,
      identity.workspace_id,
    );
  } finally {
    repaired.close();
  }
});

async function administrativeFixture() {
  const { Administration } = await import("../src/storage/index.ts");
  const root = mkdtempSync(join(tmpdir(), "zara-corpus-admin-")),
    home = join(root, "runtime"),
    backups = join(root, "backups");
  mkdirSync(backups);
  const disk = new DiskStorage(home, undefined, { projectRoot: root });
  const context = {
    ...disk.workspace,
    principal: "trusted-personal",
    session_id: "synthetic-admin",
    runtime_id: "synthetic-admin",
    can_write: true,
    processing_allowed: true,
    scopes: ["restricted:read", "restricted:write"],
    approval_principal: "synthetic-controller",
  };
  const admin = new Administration(
    home,
    backups,
    context,
    undefined,
    disk.coordination,
  );
  return { root, home, backups, disk, context, admin };
}
function grantAdministrative(
  admin: Awaited<ReturnType<typeof administrativeFixture>>["admin"],
  ref: string,
) {
  const dialog = admin.approvals.present(ref);
  admin.approvals.answer(dialog.token, true, {
    source_ref: "synthetic-decision",
    transport: "native-dialog",
    channel_identity: "registered-synthetic-controller",
    stage: "pi-confirm-return",
  });
}

test("file-primary backup restores from corpus without a bundled SQLite and preserves preview authority", async () => {
  const f = await administrativeFixture();
  try {
    const backup = await f.admin.backup(f.disk);
    const manifest = JSON.parse(
      readFileSync(join(backup.backup, "manifest.json"), "utf8"),
    );
    assert.equal(manifest.format, "zaratustra.corpus.bundle.v1");
    assert.ok(
      manifest.components.every((c: { path: string }) =>
        c.path.startsWith("corpus/"),
      ),
    );
    const preview = f.admin.restorePreview(
      backup.backup,
      "Restore this exact synthetic snapshot",
      "Keep current",
    );
    grantAdministrative(f.admin, preview.preview.request_id);
    const canonical = new FileCorpus(join(f.root, "memory"));
    assert.ok(canonical.readAuxiliary(preview.preview.request_id + ".json"));
    canonical.close();
    const result = f.admin.restore(preview.preview.request_id, f.disk);
    assert.equal(result.switched, true);
    const reopened = new DiskStorage(f.home, undefined, {
      projectRoot: f.root,
    });
    try {
      assert.notEqual(reopened.workspace.epoch, f.context.epoch);
      assert.equal(readControl(f.home)?.format, 3);
      reopened.corpusCheckpoint();
    } finally {
      reopened.close();
    }
  } finally {
    f.disk.close();
  }
});

test("runtime Git exclusions are precise directories and never exclude the canonical corpus", () => {
  const root = mkdtempSync(join(tmpdir(), "zara-exclusions-")),
    home = join(root, "runtime"),
    disk = new DiskStorage(home, undefined, { projectRoot: root });
  try {
    const paths = disk.runtimeGitExclusions();
    assert.ok(paths.includes("runtime/materials/"));
    assert.ok(paths.includes("memory/.pending/"));
    assert.ok(!paths.includes("memory/"));
    assert.ok(!paths.some((p) => p.startsWith("memory/objects")));
  } finally {
    disk.close();
  }
});

// These controls stay mechanical: no model calls or private workspaces.
test("read-only open refuses pending filesystem repair without touching its bytes", () => {
  const root = mkdtempSync(join(tmpdir(), "zara-ro-corpus-")),
    home = join(root, "runtime");
  const disk = new DiskStorage(home, undefined, { projectRoot: root });
  disk.close();
  const db = new DatabaseSync(join(home, "zara.sqlite"));
  db.prepare("INSERT INTO focus VALUES('synthetic',?)").run("{}");
  let fired = false;
  const interrupted = new FileCorpus(join(root, "memory"), (point) => {
    if (point === "corpus_before_marker" && !fired) {
      fired = true;
      throw new Error("pending");
    }
  });
  assert.throws(() => interrupted.publish(db, home), /pending/);
  db.close();
  interrupted.close();
  const rawBefore = readFileSync(join(root, "memory", "corpus.json"));
  const pendingBefore = readdirSync(join(root, "memory", ".pending"));
  assert.throws(
    () =>
      new DiskStorage(home, undefined, { projectRoot: root, readOnly: true }),
    { code: "INDEX_UNAVAILABLE" },
  );
  assert.deepEqual(
    readFileSync(join(root, "memory", "corpus.json")),
    rawBefore,
  );
  assert.deepEqual(
    readdirSync(join(root, "memory", ".pending")),
    pendingBefore,
  );
});

test("restore preview ignores retrieval traces but rejects meaningful saved change", async () => {
  const f = await administrativeFixture();
  try {
    const backup = await f.admin.backup(f.disk);
    const first = f.admin.restorePreview(
      backup.backup,
      "Restore trace-only control",
      "Keep",
    );
    grantAdministrative(f.admin, first.preview.request_id);
    f.disk.run(
      "INSERT INTO retrieval_trace(access_key,json) VALUES('synthetic','{}')",
    );
    const canonical = new FileCorpus(join(f.root, "memory"));
    assert.equal(
      canonical.contentFingerprint(),
      first.preview.payload.exact.current_fingerprint,
    );
    canonical.close();
    const second = f.admin.restorePreview(
      backup.backup,
      "Restore semantic control",
      "Keep",
    );
    grantAdministrative(f.admin, second.preview.request_id);
    f.disk.run("INSERT INTO focus VALUES('synthetic','{}')");
    assert.throws(() => f.admin.restore(second.preview.request_id, f.disk), {
      code: "APPROVAL_STALE",
    });
  } finally {
    f.disk.close();
  }
});

test("explicit quarantine migration preserves old rows and rebuilds solely from file authority", async () => {
  const { migrateQuarantinedStore } = await import("../src/storage/index.ts");
  const root = mkdtempSync(join(tmpdir(), "zara-migration-copy-")),
    home = join(root, "runtime");
  const legacy = new DiskStorage(home, undefined, {
    projectRoot: root,
    corpus: "legacy",
  });
  try {
    assert.equal(legacy.workspace.schema_version, 9);
    const sourcePath = join(root, "legacy-source.txt");
    writeFileSync(sourcePath, "exact legacy source bytes");
    const legacyMaterial = legacy.importFile(sourcePath, [root]);
    legacy.run(
      "INSERT INTO focus VALUES('retained-session','{\"note\":\"exact legacy metadata\"}')",
    );
    const report = migrateQuarantinedStore(legacy, {
      quarantineRoot: root,
      source: "verified-quarantine-copy",
    });
    assert.equal(report.exact_preserved, true);
    assert.equal(report.rebuilt_without_source_sqlite, true);
    assert.ok(report.prior_metadata.source_pins.length > 0);
    const legacyCorpus = new FileCorpus(report.corpus_root);
    assert.equal(
      legacyCorpus.material(legacyMaterial.blob_ref).toString("utf8"),
      "exact legacy source bytes",
    );
    legacyCorpus.close();
    assert.equal(legacy.workspace.schema_version, 10);
    assert.equal(
      legacy.get<{ json: string }>(
        "SELECT json FROM focus WHERE session_id='retained-session'",
      )!.json,
      '{"note":"exact legacy metadata"}',
    );
  } finally {
    legacy.close();
  }
});

test("hard process exit after SQL commit cannot resurrect an unpublished save", () => {
  const root = mkdtempSync(join(tmpdir(), "zara-before-file-marker-")),
    home = join(root, "runtime");
  const disk = new DiskStorage(home, undefined, { projectRoot: root });
  const before = disk.corpusStatus()!.revision;
  disk.close();
  const source = `import {DatabaseSync} from 'node:sqlite'; const db=new DatabaseSync(process.argv[1]);db.exec("BEGIN IMMEDIATE; INSERT INTO focus VALUES('not-file-committed','{}'); COMMIT;");process.exit(23);`;
  const crash = spawnSync(
    process.execPath,
    ["--input-type=module", "-e", source, join(home, "zara.sqlite")],
    { encoding: "utf8" },
  );
  assert.equal(crash.status, 23, crash.stderr);
  const reopened = new DiskStorage(home, undefined, { projectRoot: root });
  try {
    assert.equal(
      reopened.get(
        "SELECT json FROM focus WHERE session_id='not-file-committed'",
      ),
      undefined,
    );
    assert.equal(reopened.corpusStatus()!.revision, before);
  } finally {
    reopened.close();
  }
});

test("canonical restore works with a corrupt primary projection", async () => {
  const f = await administrativeFixture();
  const backup = await f.admin.backup(f.disk);
  f.disk.close();
  writeFileSync(join(f.home, "zara.sqlite"), "synthetic projection damage");
  const { Administration } = await import("../src/storage/index.ts");
  const admin = new Administration(f.home, f.backups, f.context);
  const preview = admin.restorePreview(
    backup.backup,
    "Restore verified corpus despite damaged projection",
    "Keep damaged projection",
  );
  grantAdministrative(admin, preview.preview.request_id);
  assert.equal(admin.restore(preview.preview.request_id).switched, true);
  const reopened = new DiskStorage(f.home, undefined, { projectRoot: f.root });
  try {
    assert.equal(reopened.workspace.schema_version, 10);
    assert.notEqual(reopened.workspace.epoch, f.context.epoch);
    reopened.corpusCheckpoint();
  } finally {
    reopened.close();
  }
});

test("canonical inventory uses verified hashes and falls back for empty or stale state", () => {
  const f = fixture();
  const probe = new FileCorpus(f.corpus.root);
  const rows = probe.rows;
  let scans = 0;
  probe.rows = function () {
    scans++;
    return rows.call(this);
  };
  try {
    const first = probe.inventory();
    assert.equal(
      scans,
      1,
      "uninitialized inventory requires full verification",
    );
    assert.deepEqual(
      first.files,
      f.corpus.checkpoint().files.map(({ path, sha256 }) => ({ path, sha256 })),
    );
    first.files[0].sha256 = "caller mutation";
    assert.notEqual(probe.inventory().files[0].sha256, "caller mutation");
    assert.equal(scans, 1, "same verified revision does not rescan history");
    put(f, "inventory-change", "new exact bytes");
    f.corpus.publish(f.db, f.home);
    const next = probe.inventory();
    assert.equal(
      scans,
      1,
      "managed publication updates the verified inventory",
    );
    assert.equal(next.revision, f.corpus.status().revision);
    assert.ok(
      next.files.every(
        (file) =>
          bytesHash(readFileSync(join(next.root, file.path))) === file.sha256,
      ),
    );
    probe.close(); // Stop observing the next publication to exercise guarded stale fallback.
    put(f, "inventory-change", "later exact bytes", 2);
    f.corpus.publish(f.db, f.home);
    const stale = probe.inventory();
    assert.equal(scans, 2, "stale inventory requires a verified checkpoint");
    assert.equal(stale.revision, f.corpus.status().revision);
  } finally {
    probe.close();
    f.corpus.close();
    f.db.close();
  }
});

test("canonical inventory rejects changed manifest and verifies offline source on first use", () => {
  const f = fixture();
  try {
    put(f, "inventory-source", "retained exact source");
    f.corpus.publish(f.db, f.home);
    const inventory = f.corpus.checkpoint();
    const manifestPath = join(f.corpus.root, "corpus.json");
    const manifest = readFileSync(manifestPath);
    writeFileSync(manifestPath, Buffer.concat([manifest, Buffer.from(" ")]));
    assert.throws(() => f.corpus.inventory(), { code: "STORE_UNAVAILABLE" });
    writeFileSync(manifestPath, manifest);
    const source = inventory.files.find((file) =>
      file.path.startsWith("objects/records/"),
    )!;
    writeFileSync(join(f.corpus.root, source.path), "damaged offline source");
    const fresh = new FileCorpus(f.corpus.root);
    try {
      assert.throws(() => fresh.inventory(), { code: "STORE_UNAVAILABLE" });
    } finally {
      fresh.close();
    }
  } finally {
    f.corpus.close();
    f.db.close();
  }
});

test("cached canonical inventory immediately rejects a byte-identical nested junction", () => {
  const f = fixture();
  try {
    put(f, "junction-source", "exact bytes outside authority");
    f.corpus.publish(f.db, f.home);
    const inventory = f.corpus.inventory();
    const records = join(f.corpus.root, "objects", "records");
    const outside = join(f.root, "outside-records");
    cpSync(records, outside, { recursive: true });
    renameSync(records, join(f.root, "preserved-records"));
    symlinkSync(outside, records, "junction");
    assert.ok(
      inventory.files.every(
        (file) =>
          bytesHash(readFileSync(join(inventory.root, file.path))) ===
          file.sha256,
      ),
    );
    // No await/event-loop turn: the watcher has not invalidated cached parents.
    assert.throws(() => f.corpus.inventory(), { code: "PERMISSION_DENIED" });
  } finally {
    f.corpus.close();
    f.db.close();
  }
});

test("peer publication verifies only changed canonical files rather than rescanning history", () => {
  const root = mkdtempSync(join(tmpdir(), "zara-peer-delta-")),
    home = join(root, "runtime");
  const a = new DiskStorage(home, undefined, { projectRoot: root }),
    b = new DiskStorage(home, undefined, { projectRoot: root });
  a.corpusCheckpoint();
  b.corpusCheckpoint();
  const rows = FileCorpus.prototype.rows;
  try {
    FileCorpus.prototype.rows = function () {
      throw new Error("unexpected full-history scan");
    };
    a.run(
      "INSERT INTO focus VALUES('parallel-peer','{\"value\":\"retained\"}')",
    );
    assert.equal(
      b.get<{ json: string }>(
        "SELECT json FROM focus WHERE session_id='parallel-peer'",
      )!.json,
      '{"value":"retained"}',
    );
  } finally {
    FileCorpus.prototype.rows = rows;
    a.close();
    b.close();
  }
});

test("canonical body verification rejects an equal-version projection with different content", () => {
  const f = fixture();
  try {
    put(f, "checked", "canonical source");
    f.corpus.publish(f.db, f.home);
    f.corpus.checkpoint();
    assert.throws(
      () =>
        f.corpus.verifyReadRows("SELECT json FROM records", [
          {
            json: JSON.stringify({
              id: "checked",
              revision: 1,
              kind: "evidence",
              data: { retained_excerpt: "foreign SQL body" },
            }),
          },
        ]),
      { code: "STORE_UNAVAILABLE" },
    );
  } finally {
    f.corpus.close();
    f.db.close();
  }
});

test("restore recovery completes canonical commit before local control switch", async () => {
  const f = await administrativeFixture();
  const backup = await f.admin.backup(f.disk);
  const { Administration } = await import("../src/storage/index.ts");
  const admin = new Administration(
    f.home,
    f.backups,
    f.context,
    (point) => {
      if (point === "restore_after_corpus_commit")
        throw new Error("switch interrupted");
    },
    f.disk.coordination,
  );
  const preview = admin.restorePreview(
    backup.backup,
    "Restore with interrupted local control switch",
    "Keep",
  );
  grantAdministrative(admin, preview.preview.request_id);
  assert.throws(
    () => admin.restore(preview.preview.request_id, f.disk),
    /switch interrupted/,
  );
  const reopened = new DiskStorage(f.home, undefined, { projectRoot: f.root });
  try {
    assert.notEqual(reopened.workspace.epoch, f.context.epoch);
    assert.equal(readControl(f.home)?.epoch, reopened.workspace.epoch);
    const corpus = new FileCorpus(join(f.root, "memory"));
    assert.equal(
      corpus.readAuxiliary(preview.preview.request_id + ".json").status,
      "consumed",
    );
    corpus.close();
  } finally {
    reopened.close();
    f.disk.close();
  }
});

test("cross-process publication consumes bounded deltas without a full corpus scan", () => {
  const root = mkdtempSync(join(tmpdir(), "zara-cross-process-delta-")),
    home = join(root, "runtime"),
    disk = new DiskStorage(home, undefined, { projectRoot: root });
  disk.corpusCheckpoint();
  const moduleURL = new URL("../src/storage/index.ts", import.meta.url).href;
  const script = `import {DiskStorage} from ${JSON.stringify(moduleURL)};const disk=new DiskStorage(process.argv[1],undefined,{projectRoot:process.argv[2]});disk.run("INSERT INTO focus VALUES('cross-process','{}')");disk.close();`;
  const child = spawnSync(
    process.execPath,
    ["--import", "tsx", "--input-type=module", "-e", script, home, root],
    { encoding: "utf8" },
  );
  assert.equal(child.status, 0, child.stderr);
  const rows = FileCorpus.prototype.rows;
  try {
    FileCorpus.prototype.rows = function () {
      throw new Error("unexpected full corpus scan");
    };
    const inventory = disk.corpusInventory()!;
    assert.equal(inventory.revision, disk.corpusStatus()!.revision);
    assert.ok(
      inventory.files.every(
        (file) =>
          bytesHash(readFileSync(join(inventory.root, file.path))) ===
          file.sha256,
      ),
    );
    assert.equal(
      disk.get<{ json: string }>(
        "SELECT json FROM focus WHERE session_id='cross-process'",
      )!.json,
      "{}",
    );
  } finally {
    FileCorpus.prototype.rows = rows;
    disk.close();
  }
});

test("transient imported source and its pin do not grow portable memory before selection", () => {
  const root = mkdtempSync(join(tmpdir(), "zara-transient-import-")),
    home = join(root, "runtime"),
    disk = new DiskStorage(home, undefined, { projectRoot: root });
  try {
    const before = disk.corpusCheckpoint()!,
      path = join(root, "source.txt");
    writeFileSync(path, "temporary import bytes");
    const material = disk.importFile(path, [root]);
    disk.pinSource("transient-source", [material.blob_ref]);
    disk.unpinSource("transient-source");
    const after = disk.corpusCheckpoint()!;
    assert.equal(after.revision, before.revision);
    assert.deepEqual(after.files, before.files);
    const f = fixture();
    try {
      mkdirSync(join(f.home, "materials"));
      writeFileSync(
        join(f.home, "materials", material.blob_ref),
        "temporary import bytes",
      );
      f.db
        .prepare(
          "INSERT INTO records VALUES('selected-source','evidence',NULL,?)",
        )
        .run(JSON.stringify({ data: { blob_ref: material.blob_ref } }));
      f.corpus.publish(f.db, f.home);
      assert.equal(
        f.corpus.material(material.blob_ref).toString("utf8"),
        "temporary import bytes",
      );
    } finally {
      f.corpus.close();
      f.db.close();
    }
  } finally {
    disk.close();
  }
});

test("expired transient imports are reclaimed while live pins and selected canonical originals survive", () => {
  const root = mkdtempSync(join(tmpdir(), "zara-transient-expiry-")),
    home = join(root, "runtime"),
    disk = new DiskStorage(home, undefined, { projectRoot: root });
  try {
    const path = join(root, "input.txt");
    writeFileSync(path, "unselected expiring bytes");
    const material = disk.importFile(path, [root]);
    const future = Date.now() + 1800001;
    disk.withCommandSync(() => {
      disk.coordination.reserve({
        operation_id: material.pending_key,
        epoch: disk.workspace.epoch,
        kind: "import",
        digest: material.blob_ref,
        resources: ["import:" + material.pending_key],
      });
    });
    const protectedResult = disk.withCommandSync(() =>
      disk.reclaimTransientImports(future),
    );
    assert.ok(protectedResult.protected > 0);
    assert.ok(existsSync(join(home, "materials", material.blob_ref)));
    disk.withCommandSync(() => disk.coordination.release(material.pending_key));
    disk.unpinSource(material.pending_key);
    const removed = disk.withCommandSync(() =>
      disk.reclaimTransientImports(future + 300001),
    );
    assert.ok(removed.removed > 0);
    assert.ok(!existsSync(join(home, "materials", material.blob_ref)));
    assert.equal(disk.all("SELECT id FROM records").length, 0);
  } finally {
    disk.close();
  }
});

for (const point of ["corpus_clone_fenced", "corpus_after_marker"])
  test(
    "hard clone death resumes exact epoch and unknown barriers at " + point,
    () => {
      const root = mkdtempSync(join(tmpdir(), "zara-clone-crash-")),
        first = join(root, "source"),
        cloneRoot = join(root, "clone"),
        sourceHome = join(first, "runtime"),
        cloneHome = join(cloneRoot, "runtime");
      mkdirSync(first);
      mkdirSync(cloneRoot);
      const original = new DiskStorage(sourceHome, undefined, {
        projectRoot: first,
      });
      original.withCommandSync(() =>
        original.coordination.reserve({
          operation_id: "independent-document",
          epoch: original.workspace.epoch,
          kind: "file",
          digest: "synthetic-exact-payload",
          resources: ["document:protected-path"],
        }),
      );
      original.close();
      cpSync(join(first, "memory"), join(cloneRoot, "memory"), {
        recursive: true,
      });
      const moduleURL = new URL("../src/storage/index.ts", import.meta.url)
          .href,
        script = `import {DiskStorage} from ${JSON.stringify(moduleURL)};new DiskStorage(process.argv[1],undefined,{projectRoot:process.argv[2],corpusFault(point){if(point===process.argv[3])process.exit(37);}});`;
      const child = spawnSync(
        process.execPath,
        [
          "--import",
          "tsx",
          "--input-type=module",
          "-e",
          script,
          cloneHome,
          cloneRoot,
          point,
        ],
        { encoding: "utf8" },
      );
      assert.equal(child.status, 37, child.stderr);
      const intention = JSON.parse(
        readFileSync(join(cloneHome, "corpus-bootstrap.json"), "utf8"),
      );
      const recovered = new DiskStorage(cloneHome, undefined, {
        projectRoot: cloneRoot,
      });
      try {
        assert.equal(recovered.workspace.epoch, intention.epoch);
        assert.equal(readControl(cloneHome)?.format, 3);
        recovered.withCommandSync(() => {
          assert.equal(
            recovered.coordination.operation("independent-document")?.status,
            "unknown",
          );
          assert.throws(
            () =>
              recovered.coordination.reserve({
                operation_id: "must-not-repeat",
                epoch: recovered.workspace.epoch,
                kind: "file",
                digest: "different",
                resources: ["document:protected-path"],
              }),
            { code: "STORE_BUSY" },
          );
        });
      } finally {
        recovered.close();
      }
    },
  );

test("file-marker before coordination COMMIT restores a missing independent effect as UNKNOWN", () => {
  const root = mkdtempSync(join(tmpdir(), "zara-two-db-gap-")),
    home = join(root, "runtime"),
    counter = join(root, "dispatch.txt"),
    initial = new DiskStorage(home, undefined, { projectRoot: root });
  initial.close();
  const moduleURL = new URL("../src/storage/index.ts", import.meta.url).href,
    script = `import {DiskStorage} from ${JSON.stringify(moduleURL)};import {writeFileSync}from 'node:fs';let armed=false;const disk=new DiskStorage(process.argv[1],undefined,{projectRoot:process.argv[2],corpusFault(point){if(armed&&point==='corpus_after_marker')process.exit(39);}});armed=true;disk.withCommandSync(()=>{disk.coordination.reserve({operation_id:'admitted-effect',epoch:disk.workspace.epoch,kind:'file',digest:'exact',resources:['document:one']});disk.run("INSERT INTO intents VALUES('admitted-effect','exact','{}')");});writeFileSync(process.argv[3],'DISPATCHED');`;
  const child = spawnSync(
    process.execPath,
    [
      "--import",
      "tsx",
      "--input-type=module",
      "-e",
      script,
      home,
      root,
      counter,
    ],
    { encoding: "utf8" },
  );
  assert.equal(child.status, 39, child.stderr);
  assert.equal(existsSync(counter), false);
  const reopened = new DiskStorage(home, undefined, { projectRoot: root });
  try {
    reopened.withCommandSync(() => {
      assert.equal(
        reopened.coordination.operation("admitted-effect")?.status,
        "unknown",
      );
      assert.throws(
        () =>
          reopened.coordination.reserve({
            operation_id: "different-id",
            epoch: reopened.workspace.epoch,
            kind: "file",
            digest: "exact",
            resources: ["document:one"],
          }),
        { code: "STORE_BUSY" },
      );
    });
    assert.equal(existsSync(counter), false);
  } finally {
    reopened.close();
  }
});

test("legacy bundle restore cannot switch a file-primary workspace back to control2", async () => {
  const f = await administrativeFixture();
  const { Administration } = await import("../src/storage/index.ts");
  const legacy = new DiskStorage(join(f.root, "old-home"), undefined, {
    projectRoot: join(f.root, "old-project"),
    corpus: "legacy",
  });
  try {
    const context = {
      ...f.context,
      workspace_id: legacy.workspace.workspace_id,
      epoch: legacy.workspace.epoch,
    };
    const oldAdmin = new Administration(
        legacy.controlHome,
        f.backups,
        context,
        undefined,
        legacy.coordination,
      ),
      backup = await oldAdmin.backup(legacy);
    const before = f.disk.corpusCheckpoint()!;
    assert.throws(
      () => f.admin.restorePreview(backup.backup, "Restore legacy", "Keep"),
      { code: "MIGRATION_REQUIRED" },
    );
    assert.equal(readControl(f.home)?.format, 3);
    assert.equal(f.disk.connectionClosed, false);
    assert.equal(f.disk.corpusCheckpoint()!.revision, before.revision);
  } finally {
    legacy.close();
    f.disk.close();
  }
});

test("verified corpus recovery uses a local exact preview when the current canonical manifest is corrupt", async () => {
  const f = await administrativeFixture(),
    backup = await f.admin.backup(f.disk);
  f.disk.close();
  writeFileSync(
    join(f.root, "memory", "corpus.json"),
    "damaged canonical manifest",
  );
  const { Administration } = await import("../src/storage/index.ts");
  const admin = new Administration(f.home, f.backups, f.context);
  const preview = admin.restorePreview(
    backup.backup,
    "Restore verified corpus over damaged canonical state",
    "Preserve damaged state",
  );
  assert.equal(preview.preview.payload.exact.damaged_canonical, true);
  const local = JSON.parse(
    readFileSync(
      join(f.home, "administration", preview.preview.request_id + ".json"),
      "utf8",
    ),
  );
  assert.equal(local.format, "zara.local-recovery-preview.v1");
  grantAdministrative(admin, preview.preview.request_id);
  assert.equal(admin.restore(preview.preview.request_id).switched, true);
  const reopened = new DiskStorage(f.home, undefined, { projectRoot: f.root });
  try {
    reopened.corpusCheckpoint();
    const canonical = new FileCorpus(join(f.root, "memory"));
    assert.equal(
      canonical.readAuxiliary(preview.preview.request_id + ".json").status,
      "consumed",
    );
    canonical.close();
  } finally {
    reopened.close();
  }
});

test("portable UNKNOWN collision preserves a live owner and remains a barrier after settlement", async () => {
  const { Coordination } = await import("../src/storage/index.ts"),
    home = mkdtempSync(join(tmpdir(), "zara-unknown-collision-")),
    a = new Coordination(home, "live-runtime"),
    b = new Coordination(home, "recover-runtime");
  try {
    a.sync("mutate", () =>
      a.reserve({
        operation_id: "live-effect",
        epoch: "epoch",
        kind: "file",
        digest: "live-digest",
        resources: ["document:shared"],
      }),
    );
    b.sync("mutate", () => {
      b.importMissingUnknown([
        {
          operation_id: "historical-effect",
          epoch: "epoch",
          kind: "file",
          digest: "old-digest",
          resources: ["document:shared"],
          runtime_id: "proven-historical",
          phase: "admitted",
          status: "active",
          created_at: new Date().toISOString(),
          updated_at: new Date().toISOString(),
        },
      ]);
      assert.equal(b.operation("live-effect")?.runtime_id, "live-runtime");
      assert.equal(b.operation("live-effect")?.status, "active");
      assert.equal(b.operation("historical-effect")?.status, "unknown");
    });
    a.sync("settle", () => a.release("live-effect"), {
      operationId: "live-effect",
    });
    b.sync("mutate", () =>
      assert.throws(
        () =>
          b.reserve({
            operation_id: "new-repeat",
            epoch: "epoch",
            kind: "file",
            digest: "new",
            resources: ["document:shared"],
          }),
        { code: "STORE_BUSY" },
      ),
    );
  } finally {
    a.close({ poisonUnknown: true });
    b.close({ poisonUnknown: true });
  }
});

for (const [importedId, liveId] of [
  ["a-imported-self", "z-live-foreign"],
  ["z-imported-self", "a-live-foreign"],
])
  test(
    "recovery adoption rejects every foreign reservation regardless of row order: " +
      importedId,
    async () => {
      const { Coordination } = await import("../src/storage/index.ts"),
        home = mkdtempSync(join(tmpdir(), "zara-adopt-reservation-order-")),
        live = new Coordination(home, "live-owner"),
        recover = new Coordination(home, "recovery-owner"),
        dead = new Coordination(home, "historical-dead-owner");
      dead.sync("read", () => {});
      dead.close();
      try {
        live.sync("mutate", () =>
          live.reserve({
            operation_id: liveId,
            epoch: "epoch",
            kind: "file",
            digest: "live",
            resources: ["document:collision"],
          }),
        );
        recover.sync("mutate", () => {
          recover.importMissingUnknown([
            {
              operation_id: importedId,
              epoch: "epoch",
              kind: "file",
              digest: "historical",
              resources: ["document:collision"],
              runtime_id: "historical-dead-owner",
              phase: "admitted",
              status: "active",
              created_at: new Date().toISOString(),
              updated_at: new Date().toISOString(),
            },
          ]);
          assert.equal(recover.runtimeStatus("historical-dead-owner"), "dead");
        });
        const inspection = new DatabaseSync(recover.path, { readOnly: true });
        try {
          assert.equal(
            inspection
              .prepare(
                "SELECT count(*) AS n FROM resource_reservations WHERE resource='document:collision'",
              )
              .get()!.n,
            2,
          );
        } finally {
          inspection.close();
        }
        recover.sync("mutate", () => {
          assert.throws(() => recover.adopt(importedId), {
            code: "STORE_BUSY",
          });
          assert.equal(recover.operation(importedId)?.status, "unknown");
          assert.equal(
            recover.operation(importedId)?.runtime_id,
            "historical-dead-owner",
          );
          assert.equal(recover.operation(liveId)?.status, "active");
          assert.equal(recover.operation(liveId)?.runtime_id, "live-owner");
        });
        live.sync("settle", () => live.release(liveId), {
          operationId: liveId,
        });
        recover.sync("mutate", () => {
          assert.equal(recover.adopt(importedId).runtime_id, "recovery-owner");
          recover.release(importedId);
        });
      } finally {
        live.close({ poisonUnknown: true });
        recover.close({ poisonUnknown: true });
      }
    },
  );

// Mechanical qualification only: immutable predecessor writer, current reader.
// No model replies, owner data, auth inspection or production runtime behavior.
import assert from "node:assert/strict";
import { createHash, randomUUID } from "node:crypto";
import { createRequire } from "node:module";
import { readFileSync, writeFileSync, mkdirSync, readdirSync } from "node:fs";
import { join, resolve } from "node:path";
import { pathToFileURL } from "node:url";

const [pkg, oldPkg, output] = process.argv.slice(2).map((p) => resolve(p));
assert(
  output
    .replaceAll("\\", "/")
    .toLowerCase()
    .startsWith("c:/projects/zaratustra-v1-sleep-evidence-20261022/"),
);
mkdirSync(output, { recursive: true });
const { createJiti } = createRequire(pathToFileURL(process.env.ZARA_PI_SDK))(
  "jiti",
);
const jiti = createJiti(import.meta.url);
const { Core } = await jiti.import(join(pkg, "src/core/index.ts"));
const { DiskStorage, Administration } = await jiti.import(
  join(pkg, "src/storage/index.ts"),
);
const { Core: OldCore } = await jiti.import(join(oldPkg, "src/core/index.ts"));
const { DiskStorage: OldDisk, Administration: OldAdmin } = await jiti.import(
  join(oldPkg, "src/storage/index.ts"),
);
const sha = (b) => createHash("sha256").update(b).digest("hex");
const inventory = (dir, prefix = "") =>
  readdirSync(dir, { withFileTypes: true }).flatMap((e) =>
    e.isDirectory()
      ? inventory(join(dir, e.name), prefix + e.name + "/")
      : [
          {
            path: prefix + e.name,
            sha256: sha(readFileSync(join(dir, e.name))),
          },
        ],
  );
const ctx = (disk, scopes = ["restricted:read", "restricted:write"]) => ({
  ...disk.workspace,
  principal: "trusted-personal",
  session_id: "synthetic-legacy-pending",
  runtime_id: "mechanical",
  can_write: true,
  processing_allowed: true,
  scopes,
  approval_principal: "synthetic-controller:sleep",
});
const fail = (fn) => assert.throws(fn, (e) => e.code === "REFERENCE_NOT_FOUND");
const work = (state) => ({
  op: "create_record",
  kind: "work",
  client_ref: "w",
  title: "Synthetic pending review",
  visibility: "workspace",
  data: {
    activity_id: null,
    parent_work_id: null,
    objective: "Review permitted retained grounds",
    acceptance: [
      {
        criterion_id: "review",
        description: "Consider frozen inputs",
        verification: "Inspect dispositions",
        required: true,
      },
    ],
    status: "active",
    current_state: state,
    next_action: "Read prepared batch",
    steps: [],
    waits: [],
    context_refs: [],
    completion: null,
  },
});
const start = (state, episode) => [
  work(state),
  {
    op: "start_run",
    client_ref: "r",
    title: "Synthetic pending Sleep",
    visibility: "workspace",
    episode_key: episode,
    work_ref: { client_ref: "w" },
    mode: "sleep",
    continuation_of: null,
    summary: "Explicit finite review requested",
    starting_refs: [],
  },
  {
    op: "start_sleep",
    work_ref: { client_ref: "w" },
    run_ref: { client_ref: "r" },
  },
];
const capture = (core, text) =>
  core.capture(text, "rpc", "registered-synthetic-controller");
const request = (
  core,
  id,
  ops,
  text = "Synthetic mechanical qualification; not owner testimony",
) => ({
  request_id: id,
  reason: "Synthetic pending-intent qualification",
  source_handles: [capture(core, text).source_handle],
  guards: [],
  ops,
});
const seed = (core, id, text, visibility) => {
  const s = capture(core, text);
  return core.commit({
    request_id: id,
    reason: "Synthetic retained control",
    source_handles: [s.source_handle],
    guards: [],
    ops: [
      {
        op: "import_evidence",
        client_ref: "e",
        source_handle: s.source_handle,
        title: "Synthetic retained " + visibility + " control",
        source_language: "en",
        visibility,
      },
    ],
  }).created.e;
};
const reports = [];
for (const point of ["after_prepare", "after_records"]) {
  const root = join(output, point),
    home = join(root, "home"),
    backups = join(root, "backups");
  mkdirSync(root, { recursive: true });
  assert.equal(
    readdirSync(root).length,
    0,
    "Never reuse a prior or partial qualification fixture",
  );
  let disk = new OldDisk(home);
  const original = new OldCore(disk, ctx(disk));
  const permitted = "PERMITTED-LEGACY-HISTORY-348110-" + point;
  const pub = seed(original, "permitted-history-one", permitted, "workspace");
  seed(
    original,
    "permitted-history-two",
    "Another permitted control",
    "workspace",
  );
  const ordinaryWork = original.commit(
    request(original, "permitted-ordinary-work", [
      work("Permitted ordinary restore-barrier control"),
    ]),
  ).created.w;
  const secret = "SYNTHETIC-PRIVATE-LEGACY-" + randomUUID();
  const e = seed(original, "restricted-original", secret, "restricted");
  const actual = original.read(e).data.data.retained_excerpt;
  assert.equal(actual, secret);
  const lowBefore = new Core(disk, ctx(disk, []));
  const before = {
    snapshot: lowBefore.snapshot(),
    operations: lowBefore.browse("operations"),
    changes: lowBefore.browse("changes"),
    sequence: lowBefore.sequence(),
  };
  const old = new OldCore(disk, ctx(disk), (p) => {
    if (p === point) throw Error("Synthetic old-writer interruption");
  });
  const privateRequest = "legacy-pending-" + point;
  const input = request(old, privateRequest, start(actual, "legacy-" + point));
  assert.throws(() => old.commit(input), /Synthetic old-writer interruption/);
  const pending = disk.get(
    "SELECT json FROM intents WHERE request_id=?",
    privateRequest,
  ).json;
  assert.equal(JSON.parse(pending).status, "prepared");
  assert.equal(JSON.parse(pending).visibility, undefined);
  assert.equal(disk.all("SELECT * FROM sleep_reviews").length, 0);
  assert.equal(disk.all("SELECT * FROM records WHERE kind='work'").length, 1);
  assert.equal(disk.all("SELECT * FROM records WHERE kind='run'").length, 0);
  const bundle = await new OldAdmin(home, backups, ctx(disk)).backup(disk);
  assert(bundle.complete);
  const bundleInventory = inventory(bundle.backup);
  const assertPrivate = (observerDisk, sameSnapshot = false) => {
    const low = new Core(observerDisk, ctx(observerDisk, [])),
      high = new Core(observerDisk, ctx(observerDisk));
    fail(() => low.read(e));
    fail(() => low.operation(privateRequest));
    if (observerDisk.readonly)
      assert.throws(
        () => low.commit(input),
        (e) => e.code === "READ_ONLY",
      );
    else fail(() => low.commit(input));
    assert(JSON.stringify(high.operation(privateRequest)).includes(secret));
    assert.equal(
      observerDisk.get(
        "SELECT json FROM intents WHERE request_id=?",
        privateRequest,
      ).json,
      pending,
    );
    assert(JSON.stringify(low.read(pub)).includes(permitted));
    assert.equal(
      low.operation("permitted-history-one").data.status,
      "committed",
    );
    for (const result of [
      low.snapshot(),
      low.browse("operations"),
      low.browse("changes"),
      low.browse("history", pub),
      low.diagnostics(),
    ]) {
      for (const hidden of [
        secret,
        e,
        privateRequest,
        JSON.parse(pending).source_refs[0],
      ])
        assert(!JSON.stringify(result).includes(hidden));
    }
    if (sameSnapshot) {
      assert.deepEqual(low.snapshot(), {
        ...before.snapshot,
        write_mode: observerDisk.readonly ? "read-only" : "single-writer",
      });
      assert.deepEqual(low.browse("operations"), before.operations);
      assert.deepEqual(low.browse("changes"), before.changes);
      assert.equal(low.sequence(), before.sequence);
    }
    return low;
  };
  const observer = assertPrivate(disk, true);
  const first = observer.browse("operations", undefined, 1).data;
  const next = observer.browse("operations", undefined, 1, first.next_cursor);
  assert(next.data.cards.length > 0);
  disk.close();
  disk = new DiskStorage(home);
  assertPrivate(disk, true);
  const ro = new DiskStorage(home);
  assert.equal(ro.readonly, true);
  assertPrivate(ro, true);
  ro.close();
  new Core(disk, ctx(disk)).rebuildIndex();
  const rebuilt = assertPrivate(disk);
  assert.throws(
    () => rebuilt.browse("operations", undefined, 1, first.next_cursor),
    (e) => e.code === "CURSOR_INVALIDATED",
  );
  // Current permitted-only preparation: an explicit trusted classification,
  // not inferred from the absence of private IDs in a shortened routing card.
  const publicPending = "current-permitted-pending-" + point;
  const publicMarker = "PERMITTED-PENDING-POSITIVE-760193-" + point;
  const current = new Core(disk, ctx(disk, []), (p) => {
    if (p === point) throw Error("Synthetic current permitted interruption");
  });
  assert.throws(
    () =>
      current.commit(
        request(current, publicPending, start(publicMarker, "public-" + point)),
      ),
    /Synthetic current permitted interruption/,
  );
  assert.equal(
    JSON.parse(
      disk.get("SELECT json FROM intents WHERE request_id=?", publicPending)
        .json,
    ).visibility,
    "workspace",
  );
  const low = assertPrivate(disk);
  assert(JSON.stringify(low.browse("operations")).includes(publicPending));
  assert(JSON.stringify(low.operation(publicPending)).includes(publicMarker));
  disk.close();
  // Real old7 source bundle remains untouched; restore activates a copied,
  // verified quarantine over a filled target, retaining E3 epoch barriers.
  const target = join(root, "restore-target");
  let targetDisk = new DiskStorage(target);
  seed(
    new Core(targetDisk, ctx(targetDisk)),
    "filled-target",
    "Synthetic restore target",
    "workspace",
  );
  const admin = new Administration(target, backups, ctx(targetDisk));
  const preview = admin.restorePreview(
    bundle.backup,
    "Restore genuine old pending schema7 bundle",
    "Keep filled target",
  );
  const approval = admin.approvals.present(preview.preview.request_id);
  admin.approvals.answer(approval.token, true, {
    source_ref: "synthetic",
    transport: "native-dialog",
    channel_identity: "registered-synthetic-controller",
    stage: "pi-confirm-return",
  });
  admin.restore(preview.preview.request_id, targetDisk);
  targetDisk.close();
  targetDisk = new DiskStorage(target);
  assertPrivate(targetDisk);
  assert(targetDisk.all("SELECT * FROM recovery_barriers").length > 0);
  targetDisk.close();
  assert.deepEqual(inventory(bundle.backup), bundleInventory);
  const report = {
    mechanical_only: true,
    provider_dispatches: 0,
    old_writer_sha: "372db2bd0179af35c7bb0896351298651bc9bad4",
    reader_package: pkg,
    point,
    old_status: "prepared",
    old_review_rows: 0,
    home,
    backups,
    source_bundle: bundle.backup,
    source_bundle_inventory: bundleInventory,
    private_request: privateRequest,
    public_pending_request: publicPending,
    secret,
    restricted_evidence: e,
    public_evidence: pub,
    ordinary_work: ordinaryWork,
    permitted,
    public_marker: publicMarker,
    original_pending_sha256: sha(pending),
    full_low_read_denied: true,
    hidden_only_snapshot_sequence_generation_stable: true,
    discovery_no_hidden_ids_or_text: true,
    authorized_original_readable: true,
    genuine_readonly: true,
    reopen_rebuild_restore: true,
    source_bundle_and_old_payload_unchanged: true,
    current_public_pending_fully_visible: true,
    committed_public_history_visible: true,
    synthetic_restore_approval: true,
  };
  writeFileSync(
    join(root, "fixture.json"),
    JSON.stringify(report, null, 2) + "\n",
  );
  reports.push(report);
  console.log(
    JSON.stringify({
      point,
      status: "prepared",
      full_low_read_denied: true,
      public_pending_visible: true,
      old7_bundle_restore: true,
    }),
  );
}
writeFileSync(
  join(output, "mechanical.json"),
  JSON.stringify(reports, null, 2) + "\n",
);

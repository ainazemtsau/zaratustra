// Synthetic mechanical qualification. Existing native runner supplies real L.
import assert from "node:assert/strict";
import { createHash, randomUUID } from "node:crypto";
import { createRequire } from "node:module";
import { mkdirSync, readFileSync, readdirSync, writeFileSync } from "node:fs";
import { join, resolve } from "node:path";
import { pathToFileURL } from "node:url";

const [pkg, oldPkg, root] = process.argv.slice(2).map((p) => resolve(p));
assert(
  root
    .replaceAll("\\", "/")
    .toLowerCase()
    .startsWith(
      "c:/projects/zaratustra-v1-sleep-evidence-20261022/preview-continuation-20261022/",
    ),
);
mkdirSync(root, { recursive: true });
assert.equal(
  readdirSync(root).length,
  0,
  "Never reuse a partial or prior fixture",
);
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
const ctx = (d, scopes = ["restricted:read", "restricted:write"]) => ({
  ...d.workspace,
  principal: "trusted-personal",
  session_id: "synthetic-preview",
  runtime_id: "mechanical",
  can_write: true,
  processing_allowed: true,
  scopes,
  approval_principal: "synthetic-controller:sleep-preview",
});
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
const fail = (fn) => assert.throws(fn, (e) => e.code === "REFERENCE_NOT_FOUND");
const work = (state) => ({
  op: "create_record",
  kind: "work",
  client_ref: "w",
  title: "Synthetic review proposal",
  visibility: "workspace",
  data: {
    activity_id: null,
    parent_work_id: null,
    objective: "Review frozen permitted inputs",
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
const proposal = (core, id, state) => ({
  request_id: id,
  reason: "Synthetic finite review proposal",
  source_handles: [
    core.capture(
      "Synthetic review request, not owner testimony",
      "rpc",
      "registered-synthetic-controller",
    ).source_handle,
  ],
  guards: [],
  ops: [
    work(state),
    {
      op: "start_run",
      client_ref: "r",
      title: "Synthetic Sleep proposal",
      visibility: "workspace",
      episode_key: id,
      work_ref: { client_ref: "w" },
      mode: "sleep",
      continuation_of: null,
      summary: "Explicit finite review",
      starting_refs: [],
    },
    {
      op: "start_sleep",
      work_ref: { client_ref: "w" },
      run_ref: { client_ref: "r" },
    },
  ],
});
const home = join(root, "home"),
  backups = join(root, "backups");
let disk = new OldDisk(home);
const high = new OldCore(disk, ctx(disk)),
  oldLow = new OldCore(disk, ctx(disk, []));
const seed = (id, text, visibility) => {
  const s = high.capture(text, "rpc", "registered-synthetic-controller");
  return high.commit({
    request_id: id,
    reason: "Synthetic retained control",
    source_handles: [s.source_handle],
    guards: [],
    ops: [
      {
        op: "import_evidence",
        client_ref: "e",
        source_handle: s.source_handle,
        title: "Synthetic " + visibility + " original",
        source_language: "en",
        visibility,
      },
    ],
  }).created.e;
};
const permitted = "PERMITTED-PREVIEW-HISTORY-762591",
  secret = "SYNTHETIC-PRIVATE-PREVIEW-" + randomUUID(),
  publicEvidence = seed("public-history", permitted, "workspace"),
  privateEvidence = seed("private-history", secret, "restricted");
assert.equal(high.read(privateEvidence).data.data.retained_excerpt, secret);
const publicPreview = oldLow.prepareCommit(
  proposal(oldLow, "public-proposed-review", permitted),
  "Review public history",
  "Keep",
);
const low = new Core(disk, ctx(disk, [])),
  before = {
    snapshot: low.snapshot(),
    operations: low.browse("operations"),
    changes: low.browse("changes"),
    sequence: low.sequence(),
  };
const first = low.browse("operations", undefined, 1).data,
  next = low.browse("operations", undefined, 1, first.next_cursor);
const privateRequest = proposal(high, "private-proposed-review", secret);
assert(!JSON.stringify(privateRequest).includes(privateEvidence));
const privatePreview = high.prepareCommit(
    privateRequest,
    "Review permitted history",
    "Keep",
  ),
  highPublicPreview = high.prepareCommit(
    proposal(high, "high-public-proposal", permitted),
    "Review permitted history",
    "Keep",
  );
const payloads = [privatePreview, publicPreview, highPublicPreview].map(
  (p) => ({
    request_id: p.request_id,
    json: disk.get("SELECT json FROM intents WHERE request_id=?", p.request_id)
      .json,
  }),
);
assert.equal(
  disk.all("SELECT * FROM records WHERE kind IN ('work','run')").length,
  0,
);
assert.equal(disk.all("SELECT * FROM sleep_reviews").length, 0);
assert.equal(
  disk.get(
    "SELECT count(*) AS n FROM receipts WHERE request_id IN (?,?)",
    privateRequest.request_id,
    "public-proposed-review",
  ).n,
  0,
);
const inspect = (d, compare = false) => {
  const l = new Core(d, ctx(d, [])),
    h = new Core(d, ctx(d));
  fail(() => l.read(privateEvidence));
  for (const p of [privatePreview, highPublicPreview]) {
    fail(() => l.operation(p.request_id));
    fail(() => l.approvals.read(p.request_id));
  }
  assert(
    JSON.stringify(h.operation(privatePreview.request_id)).includes(secret),
  );
  assert.deepEqual(
    h.approvals.read(privatePreview.request_id).payload,
    privatePreview.payload,
  );
  assert(
    JSON.stringify(l.operation(publicPreview.request_id)).includes(permitted),
  );
  assert(JSON.stringify(l.read(publicEvidence)).includes(permitted));
  assert.equal(l.operation("public-history").data.status, "committed");
  for (const value of [
    l.snapshot(),
    l.browse("operations"),
    l.browse("changes"),
    l.browse("history", publicEvidence),
    l.diagnostics(),
  ])
    for (const hidden of [
      secret,
      privateEvidence,
      privatePreview.request_id,
      highPublicPreview.request_id,
    ])
      assert(!JSON.stringify(value).includes(hidden));
  for (const row of payloads)
    assert.equal(
      d.get("SELECT json FROM intents WHERE request_id=?", row.request_id).json,
      row.json,
    );
  if (compare) {
    assert.deepEqual(l.snapshot(), {
      ...before.snapshot,
      write_mode: d.readonly ? "read-only" : "single-writer",
    });
    assert.deepEqual(l.browse("operations"), before.operations);
    assert.deepEqual(l.browse("changes"), before.changes);
    assert.equal(l.sequence(), before.sequence);
  }
};
inspect(disk, true);
assert.deepEqual(
  low.browse("operations", undefined, 1, first.next_cursor),
  next,
);
// This old writer generated the actual source bundle, including the exact draft
// metadata. No mutation of its scope or payload is needed for the upgraded read.
const bundle = await new OldAdmin(home, backups, ctx(disk)).backup(disk),
  bundleInventory = inventory(bundle.backup);
assert(bundle.complete);
disk.close();
disk = new DiskStorage(home);
inspect(disk, true);
const ro = new DiskStorage(home);
assert.equal(ro.readonly, true);
inspect(ro, true);
ro.close();
new Core(disk, ctx(disk)).rebuildIndex();
inspect(disk);
disk.close();
const target = join(root, "restore-target");
let targetDisk = new DiskStorage(target);
const targetCore = new Core(targetDisk, ctx(targetDisk)),
  source = targetCore.capture(
    "Synthetic filled restore target",
    "rpc",
    "registered-synthetic-controller",
  );
targetCore.commit({
  request_id: "filled-restore-target",
  reason: "Synthetic restoration control",
  source_handles: [source.source_handle],
  guards: [],
  ops: [work("Existing target retained until activation")],
});
const admin = new Administration(target, backups, ctx(targetDisk)),
  restore = admin.restorePreview(
    bundle.backup,
    "Restore genuine old preview metadata",
    "Keep filled target",
  ),
  a = admin.approvals.present(restore.preview.request_id);
admin.approvals.answer(a.token, true, {
  source_ref: "synthetic",
  transport: "native-dialog",
  channel_identity: "registered-synthetic-controller",
  stage: "pi-confirm-return",
});
admin.restore(restore.preview.request_id, targetDisk);
targetDisk.close();
targetDisk = new DiskStorage(target);
inspect(targetDisk);
assert.throws(
  () =>
    new Core(targetDisk, ctx(targetDisk)).approvals.present(
      privatePreview.request_id,
    ),
  (e) => e.code === "APPROVAL_STALE",
);
targetDisk.close();
assert.deepEqual(inventory(bundle.backup), bundleInventory);
const report = {
  mechanical_only: true,
  provider_dispatches: 0,
  old_writer_public_sha: "676f438dd960eb60f2c19e8e972afbee00b59f14",
  old_writer_runtime_sha: "f5be04bdcab34c1159613a4e431b959bd8d3d9ea",
  reader_package: pkg,
  old_writer_package: oldPkg,
  home,
  backups,
  secret,
  permitted,
  private_evidence: privateEvidence,
  public_evidence: publicEvidence,
  private_preview: privatePreview.request_id,
  public_preview: publicPreview.request_id,
  unknown_high_public_preview: highPublicPreview.request_id,
  original_preview_rows: payloads,
  source_bundle: bundle.backup,
  source_bundle_inventory: bundleInventory,
  proposed_review_domain_rows: 0,
  proposed_commit_receipts: 0,
  protected_id_absent_from_request: true,
  full_low_private_read_denied: true,
  high_full_original_and_approval_read: true,
  public_preparation_and_committed_source_visible: true,
  hidden_only_snapshot_sequence_generation_cursor_stable: true,
  reopen_genuine_readonly_rebuild_restore: true,
  canonical_preview_payloads_and_source_bundle_unchanged: true,
  synthetic_restore_approval: true,
  policy:
    "High-authority Sleep preparation is unknown even when copied body happens to be public; trusted restricted-read-free preview is positive control.",
};
writeFileSync(
  join(root, "fixture.json"),
  JSON.stringify(report, null, 2) + "\n",
);
console.log(
  JSON.stringify({
    old_writer_public_sha: report.old_writer_public_sha,
    full_low_private_read_denied: true,
    public_positive: true,
    authorized_positive: true,
    real_old7_restore: true,
    provider_dispatches: 0,
  }),
);

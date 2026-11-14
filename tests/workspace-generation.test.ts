import test from "node:test";
import assert from "node:assert/strict";
import { randomUUID } from "node:crypto";
import {
  cpSync,
  existsSync,
  mkdirSync,
  mkdtempSync,
  readFileSync,
  renameSync,
  unlinkSync,
  writeFileSync,
} from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { Core, validateSkills, type AddressedRow } from "../src/core/index.ts";
import {
  Administration,
  DiskStorage,
  FileCorpus,
  SkillBundleFiles,
  migratePortableWorkspace,
  readControl,
} from "../src/storage/index.ts";

function project(prefix: string) {
  return mkdtempSync(
    join(process.env.ZARATUSTRA_TEST_ROOT ?? tmpdir(), prefix),
  );
}
function open(
  root: string,
  generation: 10 | 11 = 11,
  fault?: (point: string) => void,
) {
  return new DiskStorage(join(root, ".local", "memory"), undefined, {
    projectRoot: root,
    generation,
    corpusFault: fault,
  });
}
function coreFor(disk: DiskStorage) {
  return new Core(disk, {
    ...disk.workspace,
    principal: "trusted-personal",
    session_id: "synthetic-generation",
    runtime_id: disk.coordination.runtimeId,
    processing_allowed: true,
    can_write: true,
    scopes: ["restricted:read", "restricted:write"],
  });
}
function seed(disk: DiskStorage) {
  const core = coreFor(disk);
  const source = core.capture(
    "Keep exact synthetic Health source 😀 and its existing reading path.",
    "rpc",
    null,
  );
  return core.commit({
    request_id: "synthetic-seed",
    reason: "Preserve synthetic transition grounds",
    source_handles: [source.source_handle],
    guards: [],
    ops: [
      {
        op: "create_record",
        client_ref: "activity",
        kind: "activity",
        title: "Synthetic Health",
        visibility: "restricted",
        data: {
          purpose: "Prepare an ordinary synthetic summary",
          status: "active",
        },
      },
      {
        op: "import_evidence",
        client_ref: "source",
        source_handle: source.source_handle,
        title: "Selected synthetic original",
        source_language: "en",
        durable_purpose: "selected_source",
      },
    ],
  });
}

test("fresh managed generation is schema11/control4 and rebuilds from its corpus", (t) => {
  const root = project("zara-generation-new-");
  let disk = open(root);
  const receipt = seed(disk);
  const original = coreFor(disk).read(receipt.created.source).data;
  const identity = disk.workspace.workspace_id;
  assert.equal(disk.workspace.schema_version, 11);
  assert.equal(disk.corpusStatus()!.schema, 11);
  assert.equal(readControl(disk.controlHome)!.format, 4);
  disk.close();
  const path = join(root, ".local", "memory", "zara.sqlite");
  renameSync(path, path + ".preserved");
  disk = open(root);
  t.after(() => disk.close());
  assert.equal(disk.workspace.workspace_id, identity);
  assert.deepEqual(coreFor(disk).read(receipt.created.source).data, original);
  assert.equal(
    disk.get<{ n: number }>("SELECT count(*) n FROM skill_versions")!.n,
    0,
  );
});

test("ordinary open refuses a populated schema10 corpus without changing canonical bytes", () => {
  const root = project("zara-generation-old-");
  const disk = open(root, 10);
  seed(disk);
  disk.close();
  const manifest = join(root, "memory", "corpus.json");
  const control = join(root, ".local", "memory", "active.json");
  const before = readFileSync(manifest);
  const beforeControl = readFileSync(control);
  assert.throws(
    () => open(root),
    (error: unknown) =>
      (error as { code?: string }).code === "MIGRATION_REQUIRED",
  );
  assert.deepEqual(readFileSync(manifest), before);
  assert.deepEqual(readFileSync(control), beforeControl);
});

test("ordinary document hash inventories remain hash-only data during publication and rebuild", (t) => {
  const root = project("zara-generation-inventory-");
  let disk = open(root);
  const inventory = {
    files: [
      {
        path: "external-original.bin",
        role: "support",
        sha256: "c".repeat(64),
      },
    ],
  };
  const core = new Core(disk, {
    ...coreFor(disk).context,
    environment: { document: inventory },
  });
  const source = core.capture(
    "Record an external hash-only source inventory",
    "rpc",
    null,
  );
  const created = core.commit({
    request_id: "hash-only-inventory",
    reason: "Preserve external inventory without claiming retained bytes",
    source_handles: [source.source_handle],
    guards: [],
    ops: [
      {
        op: "start_run",
        client_ref: "inventory",
        title: "External source inventory observation",
        visibility: "workspace",
        episode_key: "external-source-inventory",
        work_ref: null,
        mode: "conversation",
        continuation_of: null,
        summary: "Retain a hash-only source inventory in runtime metadata",
        starting_refs: [],
      },
    ],
  });
  const run = core.read(created.created.inventory).data as AddressedRow;
  const environmentId = (run.data.environment_ref as { id: string }).id;
  assert.deepEqual(
    (core.read(environmentId).data as AddressedRow).data.document,
    inventory,
  );
  assert.equal(
    existsSync(join(root, "memory/materials", "c".repeat(64) + ".json")),
    false,
  );
  disk.close();
  const database = join(root, ".local/memory/zara.sqlite");
  renameSync(database, database + ".preserved");
  disk = open(root);
  t.after(() => disk.close());
  assert.deepEqual(
    (coreFor(disk).read(environmentId).data as AddressedRow).data.document,
    inventory,
  );
});

test("explicit quarantined transition preserves sources, paths and unknown effects", (t) => {
  const sourceRoot = project("zara-generation-source-");
  const source = open(sourceRoot, 10);
  const receipt = seed(source);
  const rows = source.all(
    "SELECT rowid AS position,* FROM records ORDER BY rowid",
  );
  const original = coreFor(source).read(receipt.created.source).data;
  source.withCommandSync(() => {
    source.coordination.reserve({
      operation_id: "synthetic-unknown",
      epoch: source.workspace.epoch,
      kind: "opaque-shell",
      digest: "synthetic-digest",
      resources: ["synthetic-output"],
    });
    source.coordination.unknown("synthetic-unknown");
  });
  mkdirSync(join(sourceRoot, "activities", "existing"), { recursive: true });
  const document = Buffer.from(
    "# Synthetic Health\r\n\r\nExisting ChatGPT Web path example.\r\n",
  );
  writeFileSync(
    join(sourceRoot, "activities", "existing", "summary.md"),
    document,
  );
  source.close();
  const sourceManifest = readFileSync(
    join(sourceRoot, "memory", "corpus.json"),
  );
  const quarantineRoot = project("zara-generation-quarantine-");
  cpSync(sourceRoot, quarantineRoot, { recursive: true });
  const quarantine = open(quarantineRoot, 10);
  t.after(() => quarantine.close());
  const report = migratePortableWorkspace(quarantine, {
    quarantineRoot,
    source: "verified-quarantine-copy",
  });
  assert.equal(report.exact_preserved, true);
  assert.equal(report.rebuilt_without_source_sqlite, true);
  assert.equal(report.after.schema_version, 11);
  assert.notEqual(report.after.epoch, report.before.epoch);
  assert.deepEqual(
    quarantine.all("SELECT rowid AS position,* FROM records ORDER BY rowid"),
    rows,
  );
  assert.deepEqual(
    coreFor(quarantine).read(receipt.created.source).data,
    original,
  );
  assert.deepEqual(
    readFileSync(join(quarantineRoot, "activities", "existing", "summary.md")),
    document,
  );
  assert.equal(
    quarantine.withCommandSync(
      () =>
        quarantine.coordination
          .pending()
          .find((entry) => entry.operation_id === "synthetic-unknown")!.status,
      "read",
    ),
    "unknown",
  );
  assert.deepEqual(
    readFileSync(join(sourceRoot, "memory", "corpus.json")),
    sourceManifest,
  );
  assert.equal(readControl(quarantine.controlHome)!.format, 4);
});

test("portable generation resumes a journaled SQL-to-file interruption under its exact fence", (t) => {
  const root = project("zara-generation-recovery-");
  let disk = open(root, 10);
  const receipt = seed(disk);
  const record = coreFor(disk).read(receipt.created.activity).data;
  disk.close();
  disk = open(root, 10, (point) => {
    if (point === "portable_generation_sql_committed")
      throw new Error("synthetic power interruption");
  });
  assert.throws(
    () =>
      migratePortableWorkspace(disk, {
        quarantineRoot: root,
        source: "verified-quarantine-copy",
      }),
    /synthetic power interruption/,
  );
  disk.close();
  disk = open(root);
  t.after(() => disk.close());
  assert.equal(disk.workspace.schema_version, 11);
  assert.equal(readControl(disk.controlHome)!.format, 4);
  assert.deepEqual(coreFor(disk).read(receipt.created.activity).data, record);
  assert.equal(
    existsSync(join(disk.controlHome, "portable-generation.json")),
    false,
  );
});

test("complete binary skill material survives backup and independent corpus-only reconstruction", async (t) => {
  const root = project("zara-generation-binary-");
  let disk = open(root);
  const core = coreFor(disk);
  const path = "skills/personal/synthetic";
  const skillId = randomUUID();
  mkdirSync(join(root, path, "scripts"), { recursive: true });
  writeFileSync(
    join(root, path, "bundle.json"),
    JSON.stringify({
      format: 1,
      skill_id: skillId,
      name: "Synthetic complete skill",
      entry: "SKILL.md",
    }),
  );
  writeFileSync(
    join(root, path, "SKILL.md"),
    "# Synthetic\r\nUse the retained supporting material.\r\n",
  );
  const binary = Buffer.from([0, 255, 128, 13, 10, 42]);
  writeFileSync(join(root, path, "scripts", "original.bin"), binary);
  const snapshot = new SkillBundleFiles(root).snapshot(path);
  for (const bytes of Object.values(snapshot.bytes))
    disk.writeMaterialBytes(bytes);
  const prepared = core.skills.prepare(
    {
      operation_id: "synthetic-skill",
      path,
      metadata: snapshot.metadata,
      manifest: snapshot.manifest,
      visibility: "restricted",
      activity_ids: [],
      general_exposure: false,
      before_revision: null,
      expected_working_hash: null,
    },
    "Register complete synthetic bytes",
    "Keep the bundle unregistered",
  );
  const shown = core.approvals.present(prepared.preview.request_id);
  core.approvals.answer(shown.token, true, {
    source_ref: "synthetic-controller",
    transport: "native-dialog",
    channel_identity: "synthetic-controller",
    stage: "pi-confirm-return",
  });
  core.skills.begin(prepared.request, prepared.preview.request_id);
  core.skills.complete("synthetic-skill", snapshot.manifest);
  const source = core.capture(
    "Apply the retained binary bundle in a synthetic episode",
    "rpc",
    null,
  );
  let serial = 0;
  const commit = (ops: unknown[]) =>
    core.commit({
      request_id: "binary-invocation-" + ++serial,
      reason: "Verify exact retained skill selections",
      source_handles: [source.source_handle],
      guards: [],
      ops,
    });
  const methodId = commit([
    {
      op: "create_record",
      client_ref: "method",
      kind: "method",
      title: "Synthetic complete bundle use",
      visibility: "restricted",
      data: {
        applicability: "Synthetic notes",
        instructions: "Read the selected complete bundle",
        input_contract: "Synthetic notes",
        expected_output: "Synthetic summary",
        context_requirements: [],
        dependencies: [],
        skill_refs: [{ skill_id: skillId }],
        tool_requirements: ["read"],
        content_version: 1,
        state: "candidate",
        derived_from: [],
        limitations: "No usefulness claim",
      },
    },
  ]).created.method;
  const uninvokedMethodId = commit([
    {
      op: "create_record",
      client_ref: "method",
      kind: "method",
      title: "Synthetic uninvoked pinned bundle use",
      visibility: "restricted",
      data: {
        ...(core.read(methodId).data as AddressedRow).data,
        skill_refs: [{ skill_id: skillId, revision: 1 }],
      },
    },
  ]).created.method;
  const runId = commit([
    {
      op: "start_run",
      client_ref: "run",
      title: "Synthetic selected version episode",
      visibility: "restricted",
      episode_key: "generation-binary-selection",
      work_ref: null,
      mode: "conversation",
      continuation_of: null,
      summary: "Select the registered complete skill",
      starting_refs: [{ id: methodId }],
    },
  ]).created.run;
  const method = core.methodBundle(methodId).data;
  const invocationId = commit([
    {
      op: "invoke_method",
      client_ref: "invocation",
      run_ref: { id: runId },
      invocation_key: "generation-binary-selection",
      method_ref: method.root_ref,
      selected_versions: method.selected_versions,
      input_refs: [],
      context_refs: [],
      bindings: {},
      parent_invocation_ref: null,
    },
  ]).created.invocation;
  for (const corrupt of [
    () =>
      disk.run(
        "UPDATE records SET json=json_set(json,'$.data.skill_refs[0].skill_id',?) WHERE id=?",
        randomUUID(),
        uninvokedMethodId,
      ),
    () =>
      disk.run(
        "UPDATE records SET json=json_set(json,'$.data.skill_refs[0].revision',999) WHERE id=?",
        uninvokedMethodId,
      ),
    () =>
      disk.run(
        "UPDATE revisions SET json=json_set(json,'$.data.skill_refs[0].revision',999) WHERE id=? AND revision=1",
        uninvokedMethodId,
      ),
    () =>
      disk.run(
        "UPDATE skill_bundles SET json=json_set(json,'$.revision',999) WHERE skill_id=?",
        skillId,
      ),
    () =>
      disk.run(
        "UPDATE experience_rows SET json=json_set(json,'$.data.selected_skill_versions[0].revision',999) WHERE id=?",
        invocationId,
      ),
    () =>
      disk.run(
        "INSERT INTO skill_reservations VALUES(?,?)",
        skillId,
        JSON.stringify({
          operation_id: "missing-operation",
          epoch: disk.workspace.epoch,
        }),
      ),
  ])
    disk.withCommandSync(() => {
      disk.exec("BEGIN IMMEDIATE");
      try {
        corrupt();
        assert.throws(() => validateSkills(disk, false), {
          code: "STORE_UNAVAILABLE",
        });
      } finally {
        disk.exec("ROLLBACK");
      }
    });
  const admin = new Administration(
    disk.controlHome,
    join(root, ".local", "backups"),
    core.context,
    undefined,
    disk.coordination,
  );
  const backup = await admin.backup(disk);
  const verified = admin.verify(backup.backup);
  assert.equal(verified.manifest.schema, 11);
  const hash = snapshot.manifest.files.find(
    (file) => file.path === "scripts/original.bin",
  )!.sha256;
  const corpus = new FileCorpus(join(backup.backup, "corpus"));
  try {
    assert.deepEqual(corpus.material(hash), binary);
  } finally {
    corpus.close();
  }
  disk.close();
  const restored = project("zara-generation-binary-restored-");
  cpSync(join(backup.backup, "corpus"), join(restored, "memory"), {
    recursive: true,
  });
  disk = open(restored);
  t.after(() => disk.close());
  assert.deepEqual(Buffer.from(disk.readMaterialBytes(hash)), binary);
  assert.deepEqual(
    coreFor(disk).skills.version(skillId).manifest,
    snapshot.manifest,
  );
});

test("pending skill effects retain dirty before bytes through cleanup and backup", async (t) => {
  const root = project("zara-generation-pending-");
  const disk = open(root);
  t.after(() => disk.close());
  const core = coreFor(disk);
  const path = "skills/personal/pending";
  const skillId = randomUUID();
  mkdirSync(join(root, path), { recursive: true });
  writeFileSync(
    join(root, path, "bundle.json"),
    JSON.stringify({
      format: 1,
      skill_id: skillId,
      name: "Pending synthetic bytes",
      entry: "SKILL.md",
    }),
  );
  writeFileSync(join(root, path, "SKILL.md"), "# Registered original\n");
  const files = new SkillBundleFiles(root);
  const registered = files.snapshot(path);
  for (const bytes of Object.values(registered.bytes))
    disk.writeMaterialBytes(bytes);
  const registration = core.skills.prepare(
    {
      operation_id: "pending-registration",
      path,
      metadata: registered.metadata,
      manifest: registered.manifest,
      visibility: "workspace",
      activity_ids: [],
      general_exposure: false,
      before_revision: null,
      expected_working_hash: registered.manifest.content_hash,
    },
    "Register the synthetic original",
    "Keep file-only",
  );
  let shown = core.approvals.present(registration.preview.request_id);
  core.approvals.answer(shown.token, true, {
    source_ref: "synthetic-controller",
    transport: "native-dialog",
    channel_identity: "synthetic-controller",
    stage: "pi-confirm-return",
  });
  core.skills.begin(registration.request, registration.preview.request_id);
  core.skills.complete(registration.request.operation_id, registered.manifest);
  writeFileSync(
    join(root, path, "SKILL.md"),
    "# Dirty owner draft retained for compensation\n",
  );
  const before = files.snapshot(path);
  writeFileSync(
    join(root, path, "SKILL.md"),
    "# Proposed owner-accepted result\n",
  );
  const after = files.snapshot(path);
  writeFileSync(join(root, path, "SKILL.md"), before.bytes["SKILL.md"]);
  for (const snapshot of [before, after])
    for (const bytes of Object.values(snapshot.bytes))
      disk.writeMaterialBytes(bytes);
  const proposal = core.skills.prepare(
    {
      operation_id: "pending-dirty-effect",
      path,
      metadata: after.metadata,
      manifest: after.manifest,
      before_manifest: before.manifest,
      visibility: "workspace",
      activity_ids: [],
      general_exposure: false,
      before_revision: 1,
      expected_working_hash: before.manifest.content_hash,
    },
    "Publish the exact proposed result",
    "Preserve the dirty draft",
  );
  shown = core.approvals.present(proposal.preview.request_id);
  core.approvals.answer(shown.token, true, {
    source_ref: "synthetic-controller",
    transport: "native-dialog",
    channel_identity: "synthetic-controller",
    stage: "pi-confirm-return",
  });
  core.skills.begin(proposal.request, proposal.preview.request_id);
  core.skills.unknown(proposal.request.operation_id);
  const admin = new Administration(
    disk.controlHome,
    join(root, ".local/backups"),
    core.context,
    undefined,
    disk.coordination,
  );
  const cleanup = admin.cleanupPreview(
    disk,
    "Inspect synthetic cleanup",
    "Keep all runtime cache",
  );
  const candidates = cleanup.payload.exact.candidates as { hash: string }[];
  const beforeHash = before.manifest.files.find(
    (file) => file.path === "SKILL.md",
  )!.sha256;
  const afterHash = after.manifest.files.find(
    (file) => file.path === "SKILL.md",
  )!.sha256;
  assert.equal(
    candidates.some((file) => [beforeHash, afterHash].includes(file.hash)),
    false,
  );
  const backup = await admin.backup(disk);
  const corpus = new FileCorpus(join(backup.backup, "corpus"));
  try {
    assert.deepEqual(
      corpus.material(beforeHash),
      Buffer.from(before.bytes["SKILL.md"]),
    );
    assert.deepEqual(
      corpus.material(afterHash),
      Buffer.from(after.bytes["SKILL.md"]),
    );
    unlinkSync(join(backup.backup, "corpus/materials", beforeHash + ".json"));
    assert.throws(() => corpus.checkpoint());
  } finally {
    corpus.close();
  }
});

import test from "node:test";
import assert from "node:assert/strict";
import { randomUUID } from "node:crypto";
import { mkdtempSync, mkdirSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import {
  BundleManifestSchema,
  Core,
  CoreError,
  MethodData,
  canonical,
  digest,
  type JsonObject,
  type RecordRow,
  type SkillActivation,
} from "../src/core/index.ts";
import {
  DiskStorage,
  SkillBundleFiles,
  skillBundleSnapshot,
} from "../src/storage/index.ts";

const fails = (action: () => unknown, code: string) =>
  assert.throws(
    action,
    (error: unknown) => error instanceof CoreError && error.code === code,
  );

function fixture() {
  const project = mkdtempSync(
    join(process.env.ZARATUSTRA_TEST_ROOT ?? tmpdir(), "zara-skill-core-"),
  );
  const disk = new DiskStorage(join(project, ".local/memory"), undefined, {
    projectRoot: project,
  });
  const core = new Core(disk, {
    ...disk.workspace,
    principal: "trusted-personal",
    session_id: "skill-test",
    runtime_id: "skill-test",
    can_write: true,
    processing_allowed: true,
    scopes: ["restricted:read", "restricted:write"],
  });
  const source = core.capture(
    "Synthetic skill maintenance scope",
    "rpc",
    "synthetic-controller",
  );
  let serial = 0;
  const read = (id: string) => core.read(id).data as RecordRow;
  const commit = (ops: unknown[], ids: string[] = []) =>
    core.commit({
      request_id: "domain-" + ++serial,
      reason: "Synthetic bundle contract",
      source_handles: [source.source_handle],
      guards: ids.map((id) => ({
        ref: { id },
        expected_revision: read(id).revision,
      })),
      ops,
    });
  const approve = (ref: string) => {
    const presentation = core.approvals.present(ref);
    core.approvals.answer(presentation.token, true, {
      source_ref: "synthetic-native-dialog",
      transport: "native-dialog",
      channel_identity: "registered-synthetic-controller",
      stage: "pi-confirm-return",
    });
  };
  const activity = commit([
    {
      op: "create_record",
      client_ref: "activity",
      kind: "activity",
      title: "Synthetic Health",
      visibility: "workspace",
      data: { purpose: "Prepare synthetic summaries", status: "active" },
    },
  ]).created.activity;
  const skillId = randomUUID();
  const path = "skills/personal/summary";
  const metadata = {
    format: 1 as const,
    skill_id: skillId,
    name: "Synthetic summary",
    entry: "SKILL.md" as const,
  };
  const bytes = {
    "bundle.json": Buffer.from(JSON.stringify(metadata)),
    "SKILL.md": Buffer.from("# Summary\r\n\r\nPreserve synthetic dates.\r\n"),
    "references/check.md": Buffer.from("Check dates\n"),
    "scripts/check.js": Buffer.from("export const check = true\n"),
  };
  mkdirSync(join(project, path, "references"), { recursive: true });
  mkdirSync(join(project, path, "scripts"));
  for (const [file, content] of Object.entries(bytes))
    writeFileSync(join(project, path, file), content);
  const snapshot = skillBundleSnapshot(bytes);
  const retain = (value: ReturnType<typeof skillBundleSnapshot>) => {
    for (const file of value.manifest.files)
      disk.writeMaterialBytes(value.bytes[file.path]);
  };
  retain(snapshot);
  const request = (
    value = snapshot,
    before: number | null = null,
  ): SkillActivation => ({
    operation_id: "skill-operation-" + ++serial,
    path,
    metadata: value.metadata,
    manifest: value.manifest,
    visibility: "workspace",
    activity_ids: [activity],
    general_exposure: false,
    before_revision: before,
    expected_working_hash: before
      ? core.skills.inspect(skillId).content_hash
      : value.manifest.content_hash,
  });
  const activate = (value = snapshot, before: number | null = null) => {
    retain(value);
    const prepared = core.skills.prepare(
      request(value, before),
      "Register these complete skill bytes",
      "Keep the prior registration",
    );
    approve(prepared.preview.request_id);
    core.skills.begin(prepared.request, prepared.preview.request_id);
    return core.skills.complete(prepared.request.operation_id, value.manifest);
  };
  const method = (name = "summary", pinned?: number) =>
    commit([
      {
        op: "create_record",
        client_ref: "method",
        kind: "method",
        title: name,
        visibility: "workspace",
        data: {
          applicability: "Synthetic summaries",
          instructions: "Use the referenced summary skill",
          input_contract: "Synthetic records",
          expected_output: "A checked summary",
          context_requirements: [],
          dependencies: [],
          skill_refs: [
            { skill_id: skillId, ...(pinned ? { revision: pinned } : {}) },
          ],
          tool_requirements: ["read"],
          content_version: 1,
          state: "candidate",
          derived_from: [],
          limitations: "Synthetic only",
        },
      },
    ]).created.method;
  const bind = (methodId: string) => {
    const old = read(activity);
    commit(
      [
        {
          op: "update_record",
          ref: { id: activity },
          data: {
            ...old.data,
            contract: {
              summary: "Synthetic skill",
              procedure_refs: [{ id: methodId }],
            },
          },
        },
      ],
      [activity],
    );
  };
  const delegate = () => {
    const prepared = core.skills.prepareDelegation(
      {
        request_id: "delegation-" + ++serial,
        skill_id: skillId,
        activity_id: activity,
        allowed_paths: ["SKILL.md", "references/check.md"],
        max_bytes: 64000,
        enabled: true,
        expected_revision: 0,
      },
      "Delegate bounded local text maintenance",
      "Keep manual review",
    );
    approve(prepared.preview.request_id);
    return core.skills.delegate(prepared.request, prepared.preview.request_id);
  };
  return {
    project,
    disk,
    core,
    activity,
    skillId,
    metadata,
    path,
    bytes,
    snapshot,
    retain,
    request,
    activate,
    approve,
    commit,
    read,
    method,
    bind,
    delegate,
  };
}

test("complete skill registration is exact, replayable and retains old versions", (t) => {
  const f = fixture();
  t.after(() => f.disk.close());
  const prepared = f.core.skills.prepare(
    f.request(),
    "Register source files",
    "Keep unregistered",
  );
  fails(
    () => f.core.skills.begin(prepared.request, prepared.preview.request_id),
    "APPROVAL_STALE",
  );
  f.approve(prepared.preview.request_id);
  f.core.skills.begin(prepared.request, prepared.preview.request_id);
  const first = f.core.skills.complete(
    prepared.request.operation_id,
    f.snapshot.manifest,
  );
  assert.deepEqual(
    f.core.skills.begin(prepared.request, prepared.preview.request_id).receipt,
    first,
  );
  assert.equal(f.core.skills.version(f.skillId).revision, 1);
  const changed = skillBundleSnapshot({
    ...f.bytes,
    "references/check.md": Buffer.from("Check dates and periods\n"),
  });
  f.activate(changed, 1);
  assert.equal(f.core.skills.version(f.skillId).revision, 2);
  assert.equal(
    f.core.skills.version(f.skillId, 1).content_hash,
    f.snapshot.manifest.content_hash,
  );
  assert.equal(
    f.core.skills.version(f.skillId, 2).content_hash,
    changed.manifest.content_hash,
  );
  const originalVersion = f.disk.get<{ json: string }>(
    "SELECT json FROM skill_versions WHERE skill_id=? AND revision=1",
    f.skillId,
  )!.json;
  f.disk.run(
    "UPDATE skill_versions SET json=? WHERE skill_id=? AND revision=1",
    JSON.stringify({ ...JSON.parse(originalVersion), skill_id: randomUUID() }),
    f.skillId,
  );
  fails(() => f.core.skills.version(f.skillId, 1), "STORE_UNAVAILABLE");
  f.disk.run(
    "UPDATE skill_versions SET json=? WHERE skill_id=? AND revision=1",
    JSON.stringify({
      ...JSON.parse(originalVersion),
      content_hash: "0".repeat(64),
    }),
    f.skillId,
  );
  fails(() => f.core.skills.version(f.skillId, 1), "STORE_UNAVAILABLE");
  f.disk.run(
    "UPDATE skill_versions SET json=? WHERE skill_id=? AND revision=1",
    originalVersion,
    f.skillId,
  );
  const originalBundle = f.disk.get<{ json: string }>(
    "SELECT json FROM skill_bundles WHERE skill_id=?",
    f.skillId,
  )!.json;
  f.disk.run(
    "UPDATE skill_bundles SET json=? WHERE skill_id=?",
    JSON.stringify({ ...JSON.parse(originalBundle), skill_id: randomUUID() }),
    f.skillId,
  );
  fails(() => f.core.skills.inspect(f.skillId), "STORE_UNAVAILABLE");
  f.disk.run(
    "UPDATE skill_bundles SET json=? WHERE skill_id=?",
    originalBundle,
    f.skillId,
  );
});

test("Methods select complete versions and current drift cannot substitute historical files", (t) => {
  const f = fixture();
  t.after(() => f.disk.close());
  f.activate();
  const currentId = f.method();
  const current = f.read(currentId);
  assert.equal(f.core.skills.select([current])[0].revision, 1);
  writeFileSync(
    join(f.project, f.path, "scripts/check.js"),
    "export const check = false\n",
  );
  fails(() => f.core.skills.select([current]), "REVISION_CONFLICT");
  const pinned = f.read(f.method("Pinned", 1));
  assert.equal(
    f.core.skills
      .select([pinned])[0]
      .manifest.files.find((file) => file.path === "scripts/check.js")?.sha256,
    f.snapshot.manifest.files.find((file) => file.path === "scripts/check.js")
      ?.sha256,
  );
  const files = new SkillBundleFiles(f.project, {
    retain: (bytes) => f.disk.writeMaterialBytes(bytes),
    readRetained: (hash) => f.disk.readMaterialBytes(hash),
  });
  const view = files.materialize("selected-invocation", f.snapshot.manifest);
  assert.deepEqual(files.verifyView(view), f.snapshot.manifest);
});

test("managed invocations retain skill selections while legacy Method data keeps its bytes", (t) => {
  const f = fixture();
  t.after(() => f.disk.close());
  f.activate();
  const methodId = f.method();
  const method = f.read(methodId);
  const legacy = { ...method.data };
  delete legacy.skill_refs;
  assert.equal("skill_refs" in MethodData.parse(legacy), false);
  const origin = f.commit([
    {
      op: "create_record",
      client_ref: "input",
      kind: "knowledge",
      title: "Synthetic input",
      visibility: "workspace",
      data: {
        knowledge_kind: "observation",
        statement: "Synthetic dates",
        state: "tentative",
        basis: "inference",
        evidence_refs: [],
        conditions: "Synthetic only",
      },
    },
  ]).created.input;
  const run = f.commit([
    {
      op: "start_run",
      client_ref: "run",
      title: "Summary episode",
      visibility: "workspace",
      episode_key: "summary-episode",
      work_ref: null,
      mode: "conversation",
      continuation_of: null,
      summary: "Prepare a synthetic summary",
      starting_refs: [{ id: origin }],
    },
  ]).created.run;
  const selected = f.core.methodBundle(methodId).data;
  const invocation = f.commit([
    {
      op: "invoke_method",
      client_ref: "invocation",
      run_ref: { id: run },
      invocation_key: "summary",
      method_ref: selected.root_ref,
      selected_versions: selected.selected_versions,
      input_refs: [{ id: origin }],
      context_refs: [],
      bindings: {},
      parent_invocation_ref: null,
    },
  ]).created.invocation;
  const original = f.core.read(invocation).data as RecordRow;
  assert.equal(
    (original.data.selected_skill_versions as { revision: number }[])[0]
      .revision,
    1,
  );
  const changed = skillBundleSnapshot({
    ...f.bytes,
    "SKILL.md": Buffer.from("# Summary\n\nCheck the period.\n"),
  });
  f.activate(changed, 1);
  assert.equal(
    canonical(
      (f.core.read(invocation).data as RecordRow).data.selected_skill_versions,
    ),
    canonical(original.data.selected_skill_versions),
  );
});

test("delegated local permits bind consumers and exclude scripts and metadata", (t) => {
  const f = fixture();
  t.after(() => f.disk.close());
  f.activate();
  const methodId = f.method();
  f.bind(methodId);
  f.delegate();
  const guard = f.core.skills.localGuard(f.skillId, f.activity);
  const scriptChange = skillBundleSnapshot({
    ...f.bytes,
    "scripts/check.js": Buffer.from("export const check = false\n"),
  });
  fails(
    () => f.core.skills.validateLocalChange(guard, scriptChange.manifest),
    "APPROVAL_REQUIRED",
  );
  const changed = skillBundleSnapshot({
    ...f.bytes,
    "SKILL.md": Buffer.from("# Summary\n\nCheck periods and dates.\n"),
  });
  f.retain(changed);
  const permit = f.core.skills.validateLocalChange(guard, changed.manifest);
  f.method("Shared consumer");
  fails(
    () => f.core.skills.beginLocal(f.request(changed, 1), guard, permit),
    "APPROVAL_REQUIRED",
  );
  assert.equal(f.core.skills.consumers(f.skillId).shared, true);
});

test("scope reservation blocks Core binding mutations through activation and rollback makes a new revision", (t) => {
  const f = fixture();
  t.after(() => f.disk.close());
  f.activate();
  const methodId = f.method();
  f.bind(methodId);
  f.delegate();
  const archive = f.core.storagePreview(
    {
      action: "archive",
      targets: [{ id: methodId, revision: f.read(methodId).revision }],
    },
    "Archive this synthetic Method",
    "Keep the current Method",
  );
  f.approve(archive.request_id);
  const guard = f.core.skills.localGuard(f.skillId, f.activity);
  const changed = skillBundleSnapshot({
    ...f.bytes,
    "SKILL.md": Buffer.from("# Summary\n\nCheck period boundaries.\n"),
  });
  f.retain(changed);
  const request = f.request(changed, 1);
  const operation = f.core.skills.beginLocal(
    request,
    guard,
    f.core.skills.validateLocalChange(guard, changed.manifest),
  );
  const beforeArchive = canonical(f.read(methodId));
  fails(() => f.core.applyStorage(archive.request_id), "STORE_BUSY");
  assert.equal(canonical(f.read(methodId)), beforeArchive);
  fails(() => f.method("Racing shared consumer"), "STORE_BUSY");
  const current = f.read(methodId);
  fails(
    () =>
      f.commit(
        [
          {
            op: "revise_method",
            ref: { id: methodId },
            data: { ...current.data, instructions: "Different instructions" },
          },
        ],
        [methodId],
      ),
    "STORE_BUSY",
  );
  f.core.skills.complete(operation.operation_id, changed.manifest);
  const rollback = f.activate(f.snapshot, 2);
  assert.equal(rollback.revision, 3);
  assert.equal(rollback.content_hash, f.snapshot.manifest.content_hash);
});

test("unknown publication blocks new requests and exact compensation releases scope", (t) => {
  const f = fixture();
  t.after(() => f.disk.close());
  f.activate();
  const changed = skillBundleSnapshot({
    ...f.bytes,
    "SKILL.md": Buffer.from("# Changed\n"),
  });
  f.retain(changed);
  const prepared = f.core.skills.prepare(
    f.request(changed, 1),
    "Publish exact changed files",
    "Keep prior files",
  );
  f.approve(prepared.preview.request_id);
  f.core.skills.begin(prepared.request, prepared.preview.request_id);
  f.core.skills.unknown(prepared.request.operation_id);
  fails(
    () => f.core.skills.prepare(f.request(changed, 1), "Retry", "Keep"),
    "STORE_BUSY",
  );
  const compensation = f.core.skills.prepareCompensation(
    prepared.request.operation_id,
    "Restore the exact prior working files",
    "Inspect further",
  );
  f.approve(compensation.preview.request_id);
  fails(
    () =>
      f.core.skills.compensate(
        prepared.request.operation_id,
        changed.manifest.content_hash,
        compensation.preview.request_id,
      ),
    "REVISION_CONFLICT",
  );
  assert.equal(
    f.core.skills.compensate(
      prepared.request.operation_id,
      f.snapshot.manifest.content_hash,
      compensation.preview.request_id,
    ).status,
    "compensated",
  );
  assert.equal(f.core.skills.inspect(f.skillId).revision, 1);
});

test("restricted registration and hidden consumers cannot leak through lower-scope reads", (t) => {
  const f = fixture();
  t.after(() => f.disk.close());
  const request = { ...f.request(), visibility: "restricted" as const };
  const prepared = f.core.skills.prepare(
    request,
    "Register a protected synthetic skill",
    "Keep unregistered",
  );
  f.approve(prepared.preview.request_id);
  f.core.skills.begin(prepared.request, prepared.preview.request_id);
  f.core.skills.complete(request.operation_id, f.snapshot.manifest);
  const lower = new Core(f.disk, {
    ...f.core.context,
    session_id: "lower",
    runtime_id: "lower",
    scopes: [],
  });
  fails(() => lower.skills.inspect(f.skillId), "REFERENCE_NOT_FOUND");
  fails(() => lower.skills.version(f.skillId), "REFERENCE_NOT_FOUND");
  fails(
    () => lower.skills.operation(request.operation_id),
    "REFERENCE_NOT_FOUND",
  );
});

test("manifest schema rejects role relabeling and Windows prefix collisions", () => {
  const skillId = randomUUID();
  const data = {
    format: 1,
    skill_id: skillId,
    files: [
      { path: "SKILL.md", length: 1, sha256: "a".repeat(64), role: "text" },
      { path: "bundle.json", length: 1, sha256: "b".repeat(64), role: "text" },
      { path: "script.py", length: 1, sha256: "c".repeat(64), role: "support" },
    ],
    content_hash: "d".repeat(64),
  };
  assert.equal(BundleManifestSchema.safeParse(data).success, false);
});

test("pending registration enforces its Activity access before exposing operation or path", (t) => {
  const f = fixture();
  t.after(() => f.disk.close());
  const secret = f.commit([
    {
      op: "create_record",
      client_ref: "secret",
      kind: "knowledge",
      title: "Protected synthetic constraint",
      visibility: "restricted",
      data: {
        knowledge_kind: "constraint",
        statement: "Synthetic protected guidance",
        state: "tentative",
        basis: "inference",
        evidence_refs: [],
        conditions: "Synthetic only",
      },
    },
  ]).created.secret;
  const activity = f.read(f.activity);
  f.commit(
    [
      {
        op: "update_record",
        ref: { id: f.activity },
        data: {
          ...activity.data,
          contract: {
            summary: "Protected Activity",
            context_refs: [{ id: secret }],
          },
        },
      },
    ],
    [f.activity],
  );
  const prepared = f.core.skills.prepare(
    f.request(),
    "Register Activity-bound skill",
    "Keep unregistered",
  );
  f.approve(prepared.preview.request_id);
  f.core.skills.begin(prepared.request, prepared.preview.request_id);
  const compensation = f.core.skills.prepareCompensation(
    prepared.request.operation_id,
    "Review exact original state",
    "Leave publication unresolved",
  );
  const lower = new Core(f.disk, {
    ...f.core.context,
    scopes: [],
    session_id: "lower-pending",
    runtime_id: "lower-pending",
  });
  fails(
    () => lower.skills.operation(prepared.request.operation_id),
    "REFERENCE_NOT_FOUND",
  );
  fails(() => lower.skills.inspectCandidate(f.path), "REFERENCE_NOT_FOUND");
  fails(
    () => lower.approvals.read(prepared.preview.request_id),
    "REFERENCE_NOT_FOUND",
  );
  fails(
    () => lower.approvals.read(compensation.preview.request_id),
    "REFERENCE_NOT_FOUND",
  );
  f.core.skills.complete(prepared.request.operation_id, f.snapshot.manifest);
  const changed = skillBundleSnapshot({
    ...f.bytes,
    "SKILL.md": Buffer.from("# Pending private edit\n"),
  });
  f.retain(changed);
  const pending = f.core.skills.prepare(
    f.request(changed, 1),
    "Propose a private version",
    "Keep old files",
  );
  f.approve(pending.preview.request_id);
  f.core.skills.begin(pending.request, pending.preview.request_id);
  const undo = f.core.skills.prepareCompensation(
    pending.request.operation_id,
    "Keep the original private working bytes",
    "Inspect further",
  );
  f.approve(undo.preview.request_id);
  f.core.skills.compensate(
    pending.request.operation_id,
    f.snapshot.manifest.content_hash,
    undo.preview.request_id,
  );
  const currentActivity = f.read(f.activity);
  f.commit(
    [
      {
        op: "update_record",
        ref: { id: f.activity },
        data: {
          ...currentActivity.data,
          contract: { summary: "Current public Activity", context_refs: [] },
        },
      },
    ],
    [f.activity],
  );
  const released = f.core.skills.prepare(
    { ...f.request(f.snapshot, 1), activity_ids: [] },
    "Activate a separately reviewed public version",
    "Keep the private binding",
  );
  f.approve(released.preview.request_id);
  f.core.skills.begin(released.request, released.preview.request_id);
  f.core.skills.complete(released.request.operation_id, f.snapshot.manifest);
  assert.equal(lower.skills.version(f.skillId, 2).revision, 2);
  fails(
    () => lower.skills.operation(prepared.request.operation_id),
    "REFERENCE_NOT_FOUND",
  );
  fails(
    () => lower.skills.operation(pending.request.operation_id),
    "REFERENCE_NOT_FOUND",
  );
});

test("later Activity restriction filters skill Methods and native previews through the derived graph", (t) => {
  const f = fixture();
  t.after(() => f.disk.close());
  f.activate();
  const methodId = f.method();
  const lower = new Core(f.disk, {
    ...f.core.context,
    scopes: [],
    session_id: "lower-graph",
    runtime_id: "lower-graph",
  });
  assert.equal((lower.read(methodId).data as RecordRow).id, methodId);
  const pending = f.core.skills.prepare(
    f.request(f.snapshot, 1),
    "Keep reviewed Activity skill",
    "Keep prior version",
  );
  assert.equal(
    lower.approvals.read(pending.preview.request_id).request_id,
    pending.preview.request_id,
  );
  const secret = f.commit([
    {
      op: "create_record",
      client_ref: "secret",
      kind: "knowledge",
      title: "Private synthetic material",
      visibility: "restricted",
      data: {
        knowledge_kind: "constraint",
        statement: "Private synthetic constraint",
        state: "tentative",
        basis: "inference",
        evidence_refs: [],
        conditions: "Synthetic only",
      },
    },
  ]).created.secret;
  const activity = f.read(f.activity);
  f.commit(
    [
      {
        op: "update_record",
        ref: { id: f.activity },
        data: {
          ...activity.data,
          contract: {
            summary: "Now protected",
            context_refs: [{ id: secret }],
          },
        },
      },
    ],
    [f.activity],
  );
  fails(() => lower.read(methodId), "REFERENCE_NOT_FOUND");
  fails(() => lower.skills.inspect(f.skillId), "REFERENCE_NOT_FOUND");
  fails(
    () => lower.approvals.read(pending.preview.request_id),
    "REFERENCE_NOT_FOUND",
  );
  assert.equal(
    lower.browse("methods").data.cards.some((card) => card.id === methodId),
    false,
  );
  assert.equal(
    lower
      .search({ query: "summary", match: "all", kinds: ["method"] })
      .data.cards.some((card) => card.id === methodId),
    false,
  );
  const rebind = { ...f.request(f.snapshot, 1), activity_ids: [] };
  const released = f.core.skills.prepare(
    rebind,
    "Activate a new version without the previous Activity binding",
    "Keep the Activity restriction",
  );
  f.approve(released.preview.request_id);
  f.core.skills.begin(released.request, released.preview.request_id);
  f.core.skills.complete(released.request.operation_id, f.snapshot.manifest);
  assert.deepEqual(lower.skills.inspect(f.skillId).activity_ids, []);
  assert.equal(lower.skills.version(f.skillId, 2).revision, 2);
  fails(() => lower.skills.version(f.skillId, 1), "REFERENCE_NOT_FOUND");
});

test("large complete manifests use compact invocation refs and a bounded exact native preview", (t) => {
  const f = fixture();
  t.after(() => f.disk.close());
  const extra: Record<string, Uint8Array> = {};
  const fileRoles: Record<string, "support"> = {};
  for (let index = 0; index < 124; index++) {
    const path =
      "references/" +
      "a".repeat(440) +
      index.toString().padStart(3, "0") +
      ".md";
    extra[path] = Buffer.from("x");
    fileRoles[path] = "support";
  }
  const large = skillBundleSnapshot({
    ...f.bytes,
    ...extra,
    "bundle.json": Buffer.from(
      JSON.stringify({ ...f.metadata, file_roles: fileRoles }),
    ),
  });
  f.retain(large);
  const request = { ...f.request(large), before_manifest: large.manifest };
  const preview = f.core.skills.prepare(
    request,
    "Register the complete large manifest",
    "Keep unregistered",
  );
  assert.ok(
    Buffer.byteLength(canonical(preview.preview.payload.exact)) <= 256000,
  );
  f.approve(preview.preview.request_id);
  f.core.skills.begin(preview.request, preview.preview.request_id);
  f.core.skills.complete(request.operation_id, large.manifest);
  const method = f.method("Large pinned manifest", 1);
  const run = f.commit([
    {
      op: "start_run",
      client_ref: "run",
      title: "Large skill selection",
      visibility: "workspace",
      episode_key: "large-selection",
      work_ref: null,
      mode: "conversation",
      continuation_of: null,
      summary: "Read the selected version",
      starting_refs: [{ id: f.activity }],
    },
  ]).created.run;
  const methodBundle = f.core.methodBundle(method).data;
  const invocation = f.commit([
    {
      op: "invoke_method",
      client_ref: "invocation",
      run_ref: { id: run },
      invocation_key: "large",
      method_ref: methodBundle.root_ref,
      selected_versions: methodBundle.selected_versions,
      input_refs: [{ id: f.activity }],
      context_refs: [],
      bindings: {},
      parent_invocation_ref: null,
    },
  ]).created.invocation;
  const data = f.core.read(invocation).data as RecordRow;
  const selected = data.data.selected_skill_versions as JsonObject[];
  assert.deepEqual(Object.keys(selected[0]).sort(), [
    "content_hash",
    "revision",
    "skill_id",
  ]);
  assert.ok(Buffer.byteLength(JSON.stringify(data)) < 64000);
  assert.equal(f.core.skills.version(f.skillId, 1).manifest.files.length, 128);
});

test("adoption preserves separate export authority and requires exact same-path retirement", (t) => {
  const f = fixture();
  t.after(() => f.disk.close());
  const originalMethod = f.commit([
    {
      op: "create_record",
      client_ref: "legacy",
      kind: "method",
      title: "Legacy textual procedure",
      visibility: "workspace",
      data: {
        applicability: "Synthetic text",
        instructions: "Keep original instructions",
        input_contract: "Synthetic input",
        expected_output: "Synthetic output",
        context_requirements: [],
        dependencies: [],
        tool_requirements: ["read"],
        content_version: 1,
        state: "candidate",
        derived_from: [],
        limitations: "Text only",
      },
    },
  ]).created.legacy;
  const exported = f.core.methodExport(originalMethod);
  const target = join(f.project, "exports", "SKILL.md");
  const effect = {
    request_id: "original-export",
    kind: "managed_file",
    status: "confirmed",
    payload: {
      target,
      arguments: { path: target, content: exported.text },
      final_hash: digest(exported.text),
      method_export: {
        method_ref: exported.method_ref,
        content_hash: exported.content_hash,
        export_hash: exported.export_hash,
      },
    },
  };
  f.disk.run(
    "INSERT INTO intents VALUES(?,?,?)",
    effect.request_id,
    digest(JSON.stringify(effect)),
    JSON.stringify(effect),
  );
  const request = {
    ...f.request(),
    adopt_export: {
      path: target,
      export_request_id: effect.request_id,
      method_ref: exported.method_ref,
    },
  };
  const prepared = f.core.skills.prepare(
    request,
    "Adopt the original as a separate personal skill",
    "Keep the export alone",
  );
  f.approve(prepared.preview.request_id);
  f.core.skills.begin(prepared.request, prepared.preview.request_id);
  f.core.skills.complete(request.operation_id, f.snapshot.manifest);
  assert.equal(
    f.core.skillExportStatus(target, exported.export_hash).export_current,
    true,
  );
  assert.equal(
    (f.core.read(originalMethod).data as RecordRow).data.instructions,
    "Keep original instructions",
  );
  const sameTarget = join(f.project, f.path, "SKILL.md");
  const sameEffect = {
    ...effect,
    request_id: "same-path-export",
    payload: { ...effect.payload, target: sameTarget },
  };
  f.disk.run(
    "INSERT INTO intents VALUES(?,?,?)",
    sameEffect.request_id,
    digest(JSON.stringify(sameEffect)),
    JSON.stringify(sameEffect),
  );
  const sameRequest = {
    ...f.request(f.snapshot, 1),
    adopt_export: {
      path: sameTarget,
      export_request_id: sameEffect.request_id,
      method_ref: exported.method_ref,
    },
  };
  fails(
    () => f.core.skills.prepare(sameRequest, "Adopt in place", "Keep export"),
    "APPROVAL_REQUIRED",
  );
  const reviewed = f.core.skills.prepare(
    {
      ...sameRequest,
      adopt_export: { ...sameRequest.adopt_export, retire_original: true },
    },
    "Retire this same-path export writer and activate the personal bundle",
    "Keep the Core-canonical export",
  );
  f.approve(reviewed.preview.request_id);
  f.core.skills.begin(reviewed.request, reviewed.preview.request_id);
  f.core.skills.complete(reviewed.request.operation_id, f.snapshot.manifest);
  fails(
    () => f.core.skills.assertExportTarget(sameTarget),
    "PERMISSION_DENIED",
  );
  assert.equal(
    f.core.skillExportStatus(sameTarget, exported.export_hash).export_current,
    false,
  );
});

function compose(
  f: ReturnType<typeof fixture>,
  dependency: { id: string; revision?: number; content_version?: number },
  visibility: "workspace" | "restricted" = "workspace",
) {
  const { skill_refs, ...inline } = f.read(dependency.id).data;
  void skill_refs;
  return f.commit([
    {
      op: "create_record",
      client_ref: "composed",
      kind: "method",
      title: "Composed synthetic summary",
      visibility,
      data: {
        ...inline,
        instructions: "Use the explicitly selected dependency",
        dependencies: [dependency],
      },
    },
  ]).created.composed;
}

test("indirect consumer admission is blocked while a bundle publication reserves its scope", (t) => {
  const f = fixture();
  t.after(() => f.disk.close());
  f.activate();
  const local = f.method();
  f.bind(local);
  f.delegate();
  const guard = f.core.skills.localGuard(f.skillId, f.activity);
  const changed = skillBundleSnapshot({
    ...f.bytes,
    "SKILL.md": Buffer.from(
      "# Summary\n\nCheck the complete synthetic period.\n",
    ),
  });
  f.retain(changed);
  const request = f.request(changed, 1);
  f.core.skills.beginLocal(
    request,
    guard,
    f.core.skills.validateLocalChange(guard, changed.manifest),
  );
  fails(() => compose(f, { id: local }), "STORE_BUSY");
  f.core.skills.complete(request.operation_id, changed.manifest);
  writeFileSync(join(f.project, f.path, "SKILL.md"), changed.bytes["SKILL.md"]);
  const shared = compose(f, { id: local }, "restricted");
  f.commit([
    {
      op: "create_record",
      client_ref: "other",
      kind: "activity",
      title: "Other synthetic Activity",
      visibility: "workspace",
      data: {
        purpose: "Use a composed procedure",
        status: "active",
        contract: {
          summary: "Other consumer",
          procedure_refs: [{ id: shared }],
        },
      },
    },
  ]);
  assert.equal(f.core.skills.consumers(f.skillId).shared, true);
  fails(
    () => f.core.skills.localGuard(f.skillId, f.activity),
    "APPROVAL_REQUIRED",
  );
  const lower = new Core(f.disk, {
    ...f.core.context,
    session_id: "lower-indirect",
    runtime_id: "lower-indirect",
    scopes: [],
  });
  assert.equal(lower.skills.consumers(f.skillId).shared, true);
  fails(
    () =>
      lower.skills.prepare(
        f.request(changed, 2),
        "Update visible skill",
        "Keep current",
      ),
    "REFERENCE_NOT_FOUND",
  );
});

test("transitive skill consumers resolve retained Method revisions and content versions", (t) => {
  const f = fixture();
  t.after(() => f.disk.close());
  f.activate();
  const local = f.method();
  f.bind(local);
  f.delegate();
  compose(f, { id: local, revision: 1 });
  compose(f, { id: local, content_version: 1 });
  const current = f.read(local);
  f.commit(
    [
      {
        op: "revise_method",
        ref: { id: local },
        data: { ...current.data, skill_refs: [] },
      },
    ],
    [local],
  );
  assert.equal(f.read(local).data.content_version, 2);
  assert.equal((f.read(local).data.skill_refs as unknown[]).length, 0);
  assert.equal(f.core.skills.consumers(f.skillId).shared, true);
  assert.equal(f.core.skills.consumers(f.skillId).coverage, "complete");
  fails(
    () => f.core.skills.localGuard(f.skillId, f.activity),
    "APPROVAL_REQUIRED",
  );
});

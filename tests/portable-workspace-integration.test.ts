import test from "node:test";
import assert from "node:assert/strict";
import { randomUUID } from "node:crypto";
import {
  cpSync,
  mkdirSync,
  mkdtempSync,
  readFileSync,
  writeFileSync,
} from "node:fs";
import { join, relative, resolve } from "node:path";
import {
  Core,
  SelectedSkillRefSchema,
  type AddressedRow,
  type RecordRow,
} from "../src/core/index.ts";
import { DiskStorage, SkillBundleFiles } from "../src/storage/index.ts";
import {
  WorkspaceInstaller,
  loadWorkspaceGuidance,
  readWorkspaceManifest,
} from "../src/workspace/index.ts";

const scratch = resolve("_scratch/portable-workspace-integration");
const bundlePath = "skills/personal/synthetic-health-summary";
const product = { version: "0.7.7", revision: "synthetic-integration-product" };

function context(disk: DiskStorage) {
  return {
    ...disk.workspace,
    principal: "trusted-personal",
    session_id: "synthetic-portable-integration",
    runtime_id: disk.coordination.runtimeId,
    processing_allowed: true,
    can_write: true,
    scopes: ["restricted:read", "restricted:write"],
  };
}

test("portable files join managed Method selection and rebuild with exact bundle history", (t) => {
  mkdirSync(scratch, { recursive: true });
  const project = mkdtempSync(join(scratch, "workspace-"));
  new WorkspaceInstaller(project, { product }).initialize();
  const manifest = readWorkspaceManifest(project)!;
  const activityPath = "activities/retained-layout/AGENTS.md";
  const sourcePath = "activities/retained-layout/source.md";
  const sourceBytes = Buffer.from(
    "# Synthetic Health\r\n\r\n" +
      "2026-11-01 | 20 minutes\r\n2026-11-02 | 25 minutes\r\n" +
      "Web reference https://example.invalid/synthetic/health/source.md\r\n",
  );
  mkdirSync(join(project, "activities/retained-layout"), { recursive: true });
  writeFileSync(join(project, sourcePath), sourceBytes);
  writeFileSync(
    join(project, activityPath),
    "# Synthetic Health\n\nUse synthetic-health-summary. Preserve the source path.\n",
  );
  manifest.activities.push({
    key: "synthetic-health",
    label: "Synthetic Health",
    guidance_path: activityPath,
  });
  writeFileSync(join(project, "zaratustra.json"), JSON.stringify(manifest));

  const guidance = loadWorkspaceGuidance(project, {
    activity_id: "synthetic-health",
    product_revision: product.revision,
  })!;
  assert.equal(guidance.activity?.path, activityPath);
  assert.equal(guidance.warnings.length, 0);
  const skillId = randomUUID();
  mkdirSync(join(project, bundlePath, "references"), { recursive: true });
  mkdirSync(join(project, bundlePath, "scripts"), { recursive: true });
  writeFileSync(
    join(project, bundlePath, "bundle.json"),
    JSON.stringify({
      format: 1,
      skill_id: skillId,
      name: "Synthetic Health summary",
      entry: "SKILL.md",
      file_roles: { "references/rules.md": "text" },
    }),
  );
  writeFileSync(
    join(project, bundlePath, "SKILL.md"),
    "# Synthetic Health summary\n\nRead references/rules.md and preserve source dates.\n",
  );
  writeFileSync(
    join(project, bundlePath, "references/rules.md"),
    "Keep all dates and source paths. This is an isolated synthetic fixture.\n",
  );
  const script = Buffer.from("Write-Output 'synthetic-version-one'\r\n");
  writeFileSync(join(project, bundlePath, "scripts/check.ps1"), script);

  const disk = new DiskStorage(join(project, ".local/memory"), undefined, {
    projectRoot: project,
  });
  let diskOpen = true;
  t.after(() => {
    if (diskOpen) disk.close();
  });
  const core = new Core(disk, context(disk));
  const source = core.capture(
    "Isolated synthetic portable workflow",
    "rpc",
    null,
  );
  let serial = 0;
  const commit = (ops: unknown[]) =>
    core.commit({
      request_id: "portable-integration-" + ++serial,
      reason: "Verify the isolated portable workflow",
      source_handles: [source.source_handle],
      guards: [],
      ops,
    });
  const activityId = commit([
    {
      op: "create_record",
      client_ref: "activity",
      kind: "activity",
      title: "Synthetic Health",
      visibility: "workspace",
      data: { purpose: "Inspect synthetic dated notes", status: "active" },
    },
  ]).created.activity;
  manifest.activities[0].core_ref = { id: activityId };
  writeFileSync(join(project, "zaratustra.json"), JSON.stringify(manifest));
  assert.equal(
    loadWorkspaceGuidance(project, { core_activity_id: activityId })?.activity
      ?.key,
    "synthetic-health",
  );

  const files = new SkillBundleFiles(project, {
    retain: (bytes) => disk.writeMaterialBytes(bytes),
    readRetained: (hash) => disk.readMaterialBytes(hash),
  });
  const snapshot = files.snapshot(bundlePath);
  for (const bytes of Object.values(snapshot.bytes))
    disk.writeMaterialBytes(bytes);
  const activation = core.skills.prepare(
    {
      operation_id: "synthetic-registration",
      path: bundlePath,
      metadata: snapshot.metadata,
      manifest: snapshot.manifest,
      visibility: "workspace",
      activity_ids: [activityId],
      general_exposure: false,
      before_revision: null,
      expected_working_hash: snapshot.manifest.content_hash,
    },
    "Register this exact synthetic bundle",
    "Keep the fixture file-only",
  );
  const shown = core.approvals.present(activation.preview.request_id);
  core.approvals.answer(shown.token, true, {
    source_ref: "synthetic-controller",
    transport: "native-dialog",
    channel_identity: "synthetic-controller",
    stage: "pi-confirm-return",
  });
  core.skills.begin(activation.request, activation.preview.request_id);
  core.skills.complete(
    activation.request.operation_id,
    files.snapshot(bundlePath).manifest,
  );

  const methodId = commit([
    {
      op: "create_record",
      client_ref: "method",
      kind: "method",
      title: "Summarize synthetic dated notes",
      visibility: "workspace",
      data: {
        applicability: "Synthetic dated notes",
        instructions: "Apply the selected Health summary skill.",
        input_contract: "Dated source notes",
        expected_output: "Summary with source paths and dates",
        context_requirements: [],
        dependencies: [],
        skill_refs: [{ skill_id: skillId }],
        tool_requirements: ["read"],
        content_version: 1,
        state: "candidate",
        derived_from: [],
        limitations: "Synthetic fixture without usefulness evidence",
      },
    },
  ]).created.method;
  const runId = commit([
    {
      op: "start_run",
      client_ref: "run",
      title: "Synthetic portable episode",
      visibility: "workspace",
      episode_key: "synthetic-portable-episode",
      work_ref: null,
      mode: "conversation",
      continuation_of: null,
      summary: "Select the complete synthetic bundle",
      starting_refs: [{ id: methodId }],
    },
  ]).created.run;
  const method = core.methodBundle(methodId).data;
  const invocationId = commit([
    {
      op: "invoke_method",
      client_ref: "invocation",
      run_ref: { id: runId },
      invocation_key: "synthetic-selection",
      method_ref: method.root_ref,
      selected_versions: method.selected_versions,
      input_refs: [],
      context_refs: [],
      bindings: {},
      parent_invocation_ref: null,
    },
  ]).created.invocation;
  const invocation = core.read(invocationId).data as AddressedRow;
  const selected = (invocation.data.selected_skill_versions as unknown[]).map(
    (version) => SelectedSkillRefSchema.parse(version),
  );
  assert.equal(selected.length, 1);
  assert.equal(selected[0].content_hash, snapshot.manifest.content_hash);
  const selectedVersion = core.skills.version(
    selected[0].skill_id,
    selected[0].revision,
  );
  const view = files.materialize(invocationId, selectedVersion.manifest);
  writeFileSync(
    join(project, bundlePath, "scripts/check.ps1"),
    "Write-Output 'synthetic-working-edit'\r\n",
  );
  assert.deepEqual(readFileSync(join(view.path, "scripts/check.ps1")), script);
  assert.throws(
    () => core.skills.select([core.read(methodId).data as RecordRow]),
    {
      code: "REVISION_CONFLICT",
    },
  );
  const originalIdentity = disk.workspace.workspace_id;
  disk.close();
  diskOpen = false;

  const clone = mkdtempSync(join(scratch, "rebuilt-"));
  cpSync(project, clone, {
    recursive: true,
    filter: (path) => {
      const relativePath = relative(project, path);
      return (
        relativePath !== ".local" &&
        !relativePath.startsWith(".local\\") &&
        !relativePath.startsWith(".local/")
      );
    },
  });
  const rebuilt = new DiskStorage(join(clone, ".local/memory"), undefined, {
    projectRoot: clone,
  });
  t.after(() => rebuilt.close());
  const rebuiltCore = new Core(rebuilt, context(rebuilt));
  assert.equal(rebuilt.workspace.workspace_id, originalIdentity);
  assert.deepEqual(readFileSync(join(clone, sourcePath)), sourceBytes);
  assert.equal(
    readWorkspaceManifest(clone)?.installation_id,
    manifest.installation_id,
  );
  const retained = rebuiltCore.skills.version(skillId, 1);
  assert.equal(retained.content_hash, selected[0].content_hash);
  const rebuiltFiles = new SkillBundleFiles(clone, {
    readRetained: (hash) => rebuilt.readMaterialBytes(hash),
  });
  const rebuiltView = rebuiltFiles.materialize(invocationId, retained.manifest);
  assert.deepEqual(
    readFileSync(join(rebuiltView.path, "scripts/check.ps1")),
    script,
  );
});

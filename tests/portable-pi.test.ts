import test from "node:test";
import assert from "node:assert/strict";
import { randomUUID } from "node:crypto";
import { mkdirSync, mkdtempSync, readFileSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import type { ExtensionContext } from "@earendil-works/pi-coding-agent";
import { SessionManager } from "@earendil-works/pi-coding-agent";
import type {
  ExtensionAPI,
  ExtensionToolContext,
} from "@earendil-works/pi-coding-agent";
import { z } from "zod";
import {
  Core,
  SleepV2,
  canonical,
  type AddressedRow,
  type RecordRow,
  type SleepSkillChange,
  type SleepState,
} from "../src/core/index.ts";
import { DiskStorage, SkillBundleFiles } from "../src/storage/index.ts";
import {
  WorkspaceInstaller,
  readWorkspaceManifest,
} from "../src/workspace/index.ts";
import {
  assertPortableRevision,
  portableGuidance,
  replacePortableGuidance,
} from "../src/extension/workspace.ts";
import {
  registerSkillBundles,
  workspaceDiscoveryHash,
} from "../src/extension/skill-bundles.ts";
import { renderApproval } from "../src/extension/preview.ts";
import extension from "../src/extension/index.ts";

const fails = (code: string) => (error: unknown) =>
  (error as { code?: string }).code === code;

function directory() {
  return mkdtempSync(
    join(process.env.ZARATUSTRA_TEST_ROOT ?? tmpdir(), "zara-portable-pi-"),
  );
}

test("portable guidance switches mapped Activity from the root and preserves foreign system sections", () => {
  const project = directory();
  new WorkspaceInstaller(project, {
    product: { version: "test", revision: "portable-test" },
  }).initialize();
  const manifest = readWorkspaceManifest(project)!;
  mkdirSync(join(project, "activities/old-health-path"), { recursive: true });
  mkdirSync(join(project, "activities/other"));
  writeFileSync(
    join(project, "activities/old-health-path/AGENTS.md"),
    "Health current guidance",
  );
  writeFileSync(
    join(project, "activities/other/AGENTS.md"),
    "Other current guidance",
  );
  manifest.activities = [
    {
      key: "health",
      label: "Synthetic Health",
      guidance_path: "activities/old-health-path/AGENTS.md",
      core_ref: { id: "health-core", revision: 1 },
    },
    {
      key: "other",
      label: "Other",
      guidance_path: "activities/other/AGENTS.md",
      core_ref: { id: "other-core", revision: 1 },
    },
  ];
  writeFileSync(join(project, "zaratustra.json"), JSON.stringify(manifest));
  const ctx = { cwd: project, isProjectTrusted: () => true };
  const health = portableGuidance(ctx, "portable-test", "health-core");
  assert.match(health.sections.zaratustra_activity, /Health current guidance/);
  const foreign = {
    role: "system",
    content: "Host instructions",
    sections: { foreign: "Foreign extension" },
    timestamp: 1,
  };
  const data = { role: "custom", content: "Historical DATA" };
  const first = replacePortableGuidance([foreign, data], health.sections);
  const other = portableGuidance(ctx, "portable-test", "other-core");
  const second = replacePortableGuidance(first, other.sections);
  assert.equal(second[0], foreign);
  assert.equal(second[1], data);
  const replay: Record<string, string | null> = {};
  for (const message of second)
    if ("sections" in message) Object.assign(replay, message.sections);
  assert.equal(replay.foreign, "Foreign extension");
  assert.match(replay.zaratustra_activity!, /Other current guidance/);
  assert.doesNotMatch(replay.zaratustra_activity!, /Health current guidance/);
  assert.equal(
    portableGuidance(
      { cwd: project, isProjectTrusted: () => false },
      "portable-test",
      "health-core",
    ).files.length,
    0,
  );
  const missing = portableGuidance(ctx, "portable-test", "missing-core");
  assert.match(missing.sections.zaratustra_activity, /unresolved/);
  assert.throws(
    () => assertPortableRevision(project, "different-runtime"),
    fails("PRODUCT_VERSION_MISMATCH"),
  );
  writeFileSync(
    join(project, "instructions/system.md"),
    "Unreviewed system edit",
  );
  assert.throws(
    () => assertPortableRevision(project, "portable-test"),
    fails("REVISION_CONFLICT"),
  );
});

test("native Pi hooks reload session focus guidance before each request and block a mismatched product", async (t) => {
  const project = mkdtempSync(join(tmpdir(), "zara-portable-hooks-")),
    agent = directory();
  new WorkspaceInstaller(project).initialize();
  const environmentKeys = [
    "ZARATUSTRA_HOME",
    "ZARATUSTRA_OUTPUT_ROOT",
    "ZARATUSTRA_BACKUP_ROOT",
    "ZARATUSTRA_IMPORT_ROOTS",
    "PI_CODING_AGENT_DIR",
    "ZARATUSTRA_TEST_CONTROLLER",
  ];
  const previous = Object.fromEntries(
    environmentKeys.map((key) => [key, process.env[key]]),
  );
  for (const key of environmentKeys) delete process.env[key];
  process.env.PI_CODING_AGENT_DIR = agent;
  process.env.ZARATUSTRA_TEST_CONTROLLER = "portable-hook-fixture";
  type Hook = (
    event: Record<string, unknown>,
    ctx: ExtensionContext,
  ) => unknown;
  type Tool = Parameters<ExtensionAPI["registerTool"]>[0];
  const hooks = new Map<string, Hook>(),
    tools = new Map<string, Tool>();
  const sessionManager = SessionManager.inMemory(project);
  const ctx = {
    cwd: project,
    mode: "sdk",
    hasUI: true,
    model: { provider: "synthetic", id: "no-model-dispatch" },
    sessionManager,
    isProjectTrusted: () => true,
    ui: {
      notify() {},
      async confirm() {
        return true;
      },
    },
    abort() {},
  } as unknown as ExtensionToolContext;
  extension({
    on: (name: string, handler: Hook) => {
      hooks.set(name, handler);
    },
    registerTool: (tool: Tool) => {
      tools.set(tool.name, tool);
    },
    registerCommand() {},
    sendMessage() {},
    getThinkingLevel: () => "off",
  } as unknown as ExtensionAPI);
  const emit = async (name: string, event: Record<string, unknown> = {}) =>
    await hooks.get(name)?.(event, ctx);
  const call = async (name: string, input: Record<string, unknown>) => {
    const result = await tools
      .get(name)!
      .execute("fixture-" + randomUUID(), input, undefined, undefined, ctx);
    return result.details as Record<string, unknown>;
  };
  t.after(async () => {
    await emit("session_shutdown");
    for (const [key, value] of Object.entries(previous)) {
      if (value === undefined) delete process.env[key];
      else process.env[key] = value;
    }
  });
  await emit("session_start");
  await emit("input", {
    text: "Continue the selected synthetic Activity.",
    source: "rpc",
  });
  const snapshot = (await emit("context", { messages: [] })) as {
    messages: { content: string }[];
  };
  const data = JSON.parse(snapshot.messages[0].content) as {
    captured_sources: { source_handle: string }[];
  };
  assert.ok(data.captured_sources?.length, JSON.stringify(data));
  const created = await call("zara_commit", {
    request_id: "hook-activities",
    reason: "Create synthetic Activities",
    source_handles: [data.captured_sources[0].source_handle],
    guards: [],
    ops: [
      {
        op: "create_record",
        kind: "activity",
        client_ref: "health",
        title: "Synthetic Health",
        visibility: "workspace",
        data: { purpose: "Synthetic dates", status: "active" },
      },
      {
        op: "create_record",
        kind: "activity",
        client_ref: "other",
        title: "Other Activity",
        visibility: "workspace",
        data: { purpose: "Synthetic notes", status: "active" },
      },
      {
        op: "set_focus",
        activity_ref: { client_ref: "health" },
        work_ref: null,
      },
    ],
  });
  assert.equal(created.committed, true, JSON.stringify(created));
  const ids = created.created as Record<string, string>;
  const manifest = readWorkspaceManifest(project)!;
  mkdirSync(join(project, "activities/existing"), { recursive: true });
  writeFileSync(
    join(project, "activities/existing/health.md"),
    "Hook Health guidance",
  );
  writeFileSync(
    join(project, "activities/existing/other.md"),
    "Hook Other guidance",
  );
  manifest.activities = [
    {
      key: "health",
      label: "Health",
      guidance_path: "activities/existing/health.md",
      core_ref: { id: ids.health },
    },
    {
      key: "other",
      label: "Other",
      guidance_path: "activities/existing/other.md",
      core_ref: { id: ids.other },
    },
  ];
  writeFileSync(join(project, "zaratustra.json"), JSON.stringify(manifest));
  const options = {
    sections: { foreign: "Unrelated extension instructions" },
    skills: [],
  };
  await emit("before_agent_start", { systemPromptOptions: options });
  assert.match(
    (options.sections as Record<string, string>).zaratustra_activity,
    /Hook Health guidance/,
  );
  assert.equal(options.sections.foreign, "Unrelated extension instructions");
  const moved = await call("zara_commit", {
    request_id: "hook-other-focus",
    reason: "Select the second Activity",
    source_handles: [data.captured_sources[0].source_handle],
    guards: [],
    ops: [{ op: "set_focus", activity_ref: { id: ids.other }, work_ref: null }],
  });
  assert.equal(moved.committed, true, JSON.stringify(moved));
  const host = {
    role: "system",
    content: "Host prompt",
    sections: { foreign: "Foreign extension" },
    timestamp: 1,
  };
  const request = (await emit("context_with_system", { messages: [host] })) as {
    messages: { sections?: Record<string, string | null> }[];
  };
  assert.equal(request.messages[0], host);
  assert.match(
    request.messages.at(-1)!.sections!.zaratustra_activity!,
    /Hook Other guidance/,
  );
  manifest.product.revision = "different-installed-package";
  writeFileSync(join(project, "zaratustra.json"), JSON.stringify(manifest));
  assert.equal((await call("zara_map", {})).code, "PRODUCT_VERSION_MISMATCH");
});

function fixture(t: test.TestContext) {
  const project = directory(),
    runtimeId = "portable-pi-" + randomUUID();
  const disk = new DiskStorage(join(project, ".local/memory"), undefined, {
    projectRoot: project,
    runtimeId,
  });
  const core = new Core(disk, {
    ...disk.workspace,
    principal: "trusted-personal",
    session_id: runtimeId,
    runtime_id: runtimeId,
    can_write: true,
    processing_allowed: true,
    scopes: ["restricted:read", "restricted:write"],
  });
  t.after(() => disk.close());
  let serial = 0;
  const source = core.capture(
    "Synthetic local bundle workflow",
    "rpc",
    "synthetic-controller",
  );
  const read = (id: string) => core.read(id).data as RecordRow;
  const commit = (ops: unknown[], ids: string[] = []) =>
    core.commit({
      request_id: "fixture-" + ++serial,
      reason: "Synthetic adapter acceptance",
      source_handles: [source.source_handle],
      guards: ids.map((id) => ({
        ref: { id },
        expected_revision: read(id).revision,
      })),
      ops,
    });
  const activity = commit([
    {
      op: "create_record",
      client_ref: "activity",
      kind: "activity",
      title: "Synthetic Health",
      visibility: "workspace",
      data: { purpose: "Synthetic local procedure", status: "active" },
    },
  ]).created.activity;
  const path = "skills/personal/summary",
    skillId = randomUUID();
  mkdirSync(join(project, path, "references"), { recursive: true });
  mkdirSync(join(project, path, "scripts"));
  writeFileSync(
    join(project, path, "bundle.json"),
    JSON.stringify({
      format: 1,
      skill_id: skillId,
      name: "Synthetic summary",
      entry: "SKILL.md",
    }),
  );
  writeFileSync(join(project, path, "SKILL.md"), "Before entry\r\n");
  writeFileSync(
    join(project, path, "references/check.md"),
    "Before reference\n",
  );
  writeFileSync(
    join(project, path, "scripts/check.js"),
    "export const check=1;\n",
  );
  const ctx = {
    cwd: project,
    isProjectTrusted: () => true,
  } as ExtensionContext;
  const tools = new Map<
    string,
    {
      schema: z.ZodType;
      action: (
        input: Record<string, unknown>,
        ctx: ExtensionContext,
      ) => unknown;
    }
  >();
  const adapter = registerSkillBundles(
    (name, _description, schema, action) => tools.set(name, { schema, action }),
    { core: () => core, disk: () => disk, begin: () => () => {} },
  );
  adapter.bind(ctx);
  const call = async (name: string, input: unknown) => {
    const tool = tools.get(name)!;
    return (await tool.action(
      tool.schema.parse(input) as Record<string, unknown>,
      ctx,
    )) as Record<string, unknown>;
  };
  const approve = (ref: string) => {
    const shown = core.approvals.present(ref);
    core.approvals.answer(shown.token, true, {
      source_ref: "synthetic-dialog",
      transport: "native-dialog",
      channel_identity: "registered-synthetic-controller",
      stage: "pi-confirm-return",
    });
  };
  const preview = async (
    changes?: { path: string; content: string | null }[],
    restore_revision?: number,
  ) =>
    (await call("zara_skill_bundle_preview", {
      operation_id: "bundle-" + ++serial,
      path,
      activity_ids: [activity],
      general_exposure: false,
      ...(changes ? { changes } : {}),
      ...(restore_revision ? { restore_revision } : {}),
      consequence: "Activate exact synthetic instructions",
      alternatives: "Keep current instructions",
    })) as unknown as {
      request: Parameters<Core["skills"]["begin"]>[0];
      preview: {
        request_id: string;
        payload: Parameters<typeof renderApproval>[0];
      };
    };
  const activate = async (
    changes?: { path: string; content: string | null }[],
    restore_revision?: number,
  ) => {
    const prepared = await preview(changes, restore_revision);
    approve(prepared.preview.request_id);
    return (await call("zara_skill_bundle_apply", {
      request: prepared.request,
      preview_ref: prepared.preview.request_id,
    })) as unknown as {
      receipt: { operation_id: string; revision: number; content_hash: string };
    };
  };
  const method = () =>
    commit([
      {
        op: "create_record",
        client_ref: "method",
        kind: "method",
        title: "Synthetic summary Method",
        visibility: "workspace",
        data: {
          applicability: "Synthetic dates",
          instructions: "Use summary skill",
          input_contract: "Synthetic records",
          expected_output: "Summary",
          context_requirements: [],
          dependencies: [],
          skill_refs: [{ skill_id: skillId }],
          tool_requirements: ["read"],
          content_version: 1,
          state: "candidate",
          derived_from: [],
          limitations: "Synthetic fixture",
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
              summary: "Synthetic local skill",
              procedure_refs: [{ id: methodId }],
            },
          },
        },
      ],
      [activity],
    );
  };
  return {
    project,
    disk,
    core,
    adapter,
    ctx,
    call,
    approve,
    preview,
    activate,
    activity,
    skillId,
    path,
    read,
    commit,
    method,
    bind,
  };
}

test("bundle adapter applies natively confirmed exact text and script previews and creates a guarded rollback revision", async (t) => {
  const f = fixture(t);
  const first = await f.activate();
  assert.equal(first.receipt.revision, 1);
  const prepared = await f.preview([
    { path: "SKILL.md", content: "After entry\n" },
    { path: "scripts/check.js", content: "export const check=2;\n" },
  ]);
  const rendered = renderApproval(prepared.preview.payload);
  assert.match(rendered, /After entry/);
  assert.match(rendered, /export const check=2/);
  assert.match(rendered, /scripts\/check\.js/);
  assert.doesNotMatch(rendered, /SOURCE PREVIEW INCOMPLETE/);
  const pendingSource = await f.call("zara_skill_bundle_read", {
    preview_ref: prepared.preview.request_id,
    path: "scripts/check.js",
  });
  assert.equal(pendingSource.text, "export const check=2;\n");
  assert.equal(pendingSource.pending_activation, true);
  await assert.rejects(
    f.call("zara_skill_bundle_apply", {
      request: prepared.request,
      preview_ref: prepared.preview.request_id,
    }),
    fails("APPROVAL_STALE"),
  );
  f.approve(prepared.preview.request_id);
  const second = (await f.call("zara_skill_bundle_apply", {
    request: prepared.request,
    preview_ref: prepared.preview.request_id,
  })) as { receipt: { revision: number } };
  assert.equal(second.receipt.revision, 2);
  const rolledBack = await f.activate(undefined, 1);
  assert.equal(rolledBack.receipt.revision, 3);
  assert.equal(rolledBack.receipt.content_hash, first.receipt.content_hash);
  assert.equal(
    readFileSync(join(f.project, f.path, "SKILL.md"), "utf8"),
    "Before entry\r\n",
  );
  assert.equal(f.core.skills.version(f.skillId, 2).revision, 2);
});

test("bundle adapter rejects a changed working source and tracks discovery edits separately", async (t) => {
  const f = fixture(t);
  await f.activate();
  const prepared = await f.preview([
    { path: "SKILL.md", content: "Proposed entry\n" },
  ]);
  f.approve(prepared.preview.request_id);
  writeFileSync(join(f.project, f.path, "SKILL.md"), "Later owner work\n");
  await assert.rejects(
    f.call("zara_skill_bundle_apply", {
      request: prepared.request,
      preview_ref: prepared.preview.request_id,
    }),
    fails("APPROVAL_STALE"),
  );
  assert.equal(
    readFileSync(join(f.project, f.path, "SKILL.md"), "utf8"),
    "Later owner work\n",
  );
  const before = workspaceDiscoveryHash(f.project);
  writeFileSync(
    join(f.project, f.path, "references/check.md"),
    "Canonical reference edit",
  );
  assert.equal(workspaceDiscoveryHash(f.project), before);
  mkdirSync(join(f.project, ".agents/skills/owner-wrapper"), {
    recursive: true,
  });
  writeFileSync(
    join(f.project, ".agents/skills/owner-wrapper/SKILL.md"),
    "General skill route",
  );
  assert.notEqual(workspaceDiscoveryHash(f.project), before);
});

test("registered restricted bundles stay opaque to path inspection and preview", async (t) => {
  const f = fixture(t);
  const prepared = (await f.call("zara_skill_bundle_preview", {
    operation_id: "restricted-registration",
    path: f.path,
    activity_ids: [f.activity],
    general_exposure: false,
    visibility: "restricted",
    consequence: "Register a synthetic restricted procedure",
    alternatives: "Keep it unregistered",
  })) as { request: unknown; preview: { request_id: string } };
  f.approve(prepared.preview.request_id);
  await f.call("zara_skill_bundle_apply", {
    request: prepared.request,
    preview_ref: prepared.preview.request_id,
  });
  f.core.context.scopes = [];
  await assert.rejects(
    f.call("zara_skill_bundle_inspect", { path: f.path }),
    fails("REFERENCE_NOT_FOUND"),
  );
  await assert.rejects(
    f.call("zara_skill_bundle_preview", {
      operation_id: "denied-path-preview",
      path: f.path,
      consequence: "Untrusted proposed registration",
      alternatives: "Leave it",
    }),
    fails("REFERENCE_NOT_FOUND"),
  );
});

test("a proved refusal before filesystem dispatch releases only its prepared bundle scope", async (t) => {
  const f = fixture(t);
  await f.activate();
  const prepared = await f.preview([
    { path: "SKILL.md", content: "Never published\n" },
  ]);
  f.approve(prepared.preview.request_id);
  const originalPublish = SkillBundleFiles.prototype.publish;
  SkillBundleFiles.prototype.publish = function (id, hooks) {
    return originalPublish.call(this, id, {
      ...hooks,
      beforePublish: (operation) => {
        mkdirSync(join(f.project, ".agents/skills/added-before-admission"), {
          recursive: true,
        });
        writeFileSync(
          join(f.project, ".agents/skills/added-before-admission/SKILL.md"),
          "Changed discovery",
        );
        hooks?.beforePublish?.(operation);
      },
    });
  };
  try {
    await assert.rejects(
      f.call("zara_skill_bundle_apply", {
        request: prepared.request,
        preview_ref: prepared.preview.request_id,
      }),
      fails("REVISION_CONFLICT"),
    );
  } finally {
    SkillBundleFiles.prototype.publish = originalPublish;
  }
  const operationId = (prepared.request as { operation_id: string })
    .operation_id;
  assert.equal(f.core.skills.operation(operationId).status, "compensated");
  assert.equal(f.core.skills.inspect(f.skillId).revision, 1);
  assert.equal(
    readFileSync(join(f.project, f.path, "SKILL.md"), "utf8"),
    "Before entry\r\n",
  );
  assert.doesNotThrow(() => f.method());
});

test("a lost completed bundle reply settles its original barriers while preserving later owner drift", async (t) => {
  const f = fixture(t);
  await f.activate();
  const prepared = await f.preview([
    { path: "SKILL.md", content: "Written before the lost reply\n" },
  ]);
  f.approve(prepared.preview.request_id);
  const originalPublish = SkillBundleFiles.prototype.publish;
  SkillBundleFiles.prototype.publish = function (id, hooks) {
    originalPublish.call(this, id, hooks);
    throw new Error("Synthetic lost publication reply");
  };
  try {
    await assert.rejects(
      f.call("zara_skill_bundle_apply", {
        request: prepared.request,
        preview_ref: prepared.preview.request_id,
      }),
      /Synthetic lost publication reply/,
    );
  } finally {
    SkillBundleFiles.prototype.publish = originalPublish;
  }
  writeFileSync(join(f.project, f.path, "SKILL.md"), "Later owner work\n");
  const operationId = (prepared.request as { operation_id: string })
    .operation_id;
  const inspected = (await f.call("zara_skill_bundle_apply", {
    operation_id: operationId,
  })) as { receipt: { revision: number } };
  assert.equal(inspected.receipt.revision, 2);
  assert.equal(
    readFileSync(join(f.project, f.path, "SKILL.md"), "utf8"),
    "Later owner work\n",
  );
  const next = await f.activate([
    { path: "SKILL.md", content: "Later reviewed instructions\n" },
  ]);
  assert.equal(next.receipt.revision, 3);
});

test("native compensation restores an unresolved bundle's exact before bytes and releases its scope", async (t) => {
  const f = fixture(t);
  await f.activate();
  const prepared = await f.preview([
    { path: "SKILL.md", content: "Unregistered native result\n" },
  ]);
  f.approve(prepared.preview.request_id);
  const originalPublish = SkillBundleFiles.prototype.publish;
  SkillBundleFiles.prototype.publish = function (id, hooks) {
    return originalPublish.call(this, id, {
      ...hooks,
      beforeCommit: () => {
        throw new Error("Synthetic interruption before registration");
      },
    });
  };
  try {
    await assert.rejects(
      f.call("zara_skill_bundle_apply", {
        request: prepared.request,
        preview_ref: prepared.preview.request_id,
      }),
      /Synthetic interruption before registration/,
    );
  } finally {
    SkillBundleFiles.prototype.publish = originalPublish;
  }
  const operationId = (prepared.request as { operation_id: string })
    .operation_id;
  assert.equal(f.core.skills.operation(operationId).status, "unknown");
  assert.equal(
    readFileSync(join(f.project, f.path, "SKILL.md"), "utf8"),
    "Unregistered native result\n",
  );
  const compensation = (await f.call("zara_skill_bundle_compensation_preview", {
    operation_id: operationId,
    consequence: "Restore the retained original working instructions",
    alternatives: "Inspect the unresolved result",
  })) as {
    request: Record<string, unknown>;
    preview: { request_id: string };
  };
  const wrong = f.core.approvals.draft(
    "skill_compensation",
    { ...compensation.request, operation_id: "another-operation" },
    [],
    "Restore another synthetic operation",
    "Inspect its original operation first",
  );
  f.approve(wrong.request_id);
  const originalCompensate = SkillBundleFiles.prototype.compensate;
  let nativeDispatches = 0;
  SkillBundleFiles.prototype.compensate = function (id) {
    nativeDispatches++;
    return originalCompensate.call(this, id);
  };
  try {
    await assert.rejects(
      f.call("zara_skill_bundle_compensation_apply", {
        operation_id: operationId,
        preview_ref: wrong.request_id,
      }),
      fails("APPROVAL_STALE"),
    );
    assert.equal(nativeDispatches, 0);
    assert.equal(f.core.skills.operation(operationId).status, "unknown");
    assert.equal(
      readFileSync(join(f.project, f.path, "SKILL.md"), "utf8"),
      "Unregistered native result\n",
    );
    f.approve(compensation.preview.request_id);
    await f.call("zara_skill_bundle_compensation_apply", {
      operation_id: operationId,
      preview_ref: compensation.preview.request_id,
    });
    assert.equal(nativeDispatches, 1);
  } finally {
    SkillBundleFiles.prototype.compensate = originalCompensate;
  }
  assert.equal(f.core.skills.operation(operationId).status, "compensated");
  assert.equal(f.core.skills.inspect(f.skillId).revision, 1);
  assert.equal(
    readFileSync(join(f.project, f.path, "SKILL.md"), "utf8"),
    "Before entry\r\n",
  );
  const next = await f.activate([
    { path: "SKILL.md", content: "Reviewed retry\n" },
  ]);
  assert.equal(next.receipt.revision, 2);
});

test("real registry and bundle callback keep consumer scope reserved through delegated Sleep publication", async (t) => {
  const f = fixture(t);
  await f.activate();
  const method = f.method();
  f.bind(method);
  const delegation = {
    request_id: "delegate",
    skill_id: f.skillId,
    activity_id: f.activity,
    allowed_paths: ["SKILL.md"],
    max_bytes: 64000,
    enabled: true,
    expected_revision: 0,
  };
  const prepared = (await f.call("zara_skill_delegation_preview", {
    request: delegation,
    consequence: "Delegate local text maintenance",
    alternatives: "Review each edit",
  })) as { preview: { request_id: string } };
  f.approve(prepared.preview.request_id);
  await f.call("zara_skill_delegation_apply", {
    request: delegation,
    preview_ref: prepared.preview.request_id,
  });
  const sourceRow = f.read(f.activity) as AddressedRow;
  const candidate = {
    ...sourceRow,
    id: "synthetic-knowledge",
    kind: "knowledge" as const,
    data: { state: "current", knowledge_kind: "fact" },
  };
  const controller = new SleepV2(f.disk, f.core.context, {
    read: (ref) =>
      ref.id === candidate.id
        ? candidate
        : (f.core.read(ref.id, "revision" in ref ? ref.revision : undefined)
            .data as AddressedRow),
    candidates: () => [candidate],
    runtimeState: () => "dead",
    readSkill: (input) => f.adapter.readSleep(input, f.ctx),
    validateSkillChange: (change, state) =>
      f.adapter.validateSleep(change, state),
    skillReceipt: (id) => f.adapter.receipt(id),
  });
  const cycle = controller.start(f.activity, {
    provider: "synthetic",
    id: "no-model-dispatch",
    thinking: "off",
  });
  controller.read(cycle.id, { id: f.activity });
  const selected = controller.readSkill(cycle.id, { skill_id: f.skillId });
  assert.ok(selected.data.guard);
  controller.analyze(cycle.id, {
    question: "Clarify local procedure?",
    observations: "Synthetic wording is ambiguous.",
    hypothesis: null,
    counterexamples: [],
    grounds: [{ id: f.activity, revision: sourceRow.revision }],
  });
  const files = new SkillBundleFiles(f.project);
  const before = files.snapshot(f.path);
  const after = files.withChanges(before, {
    "SKILL.md": Buffer.from("Clarified entry\n"),
  });
  const change: SleepSkillChange = {
    guard: f.core.skills.localGuard(f.skillId, f.activity),
    after_manifest: after.manifest,
    changes: [{ path: "SKILL.md", content: "Clarified entry\n" }],
  };
  const proposal = controller.propose(cycle.id, {
    reason: "Clarify wording",
    expected_benefit: "Next ordinary use follows procedure",
    limits: "Local text only",
    premises: [{ id: f.activity, revision: sourceRow.revision }],
    request: null,
    document_change: null,
    skill_change: change,
    future_check: {
      trigger: "Next ordinary use",
      expected_observation: "Correct summary",
    },
  });
  assert.equal(controller.validate(cycle.id, proposal.id).status, "validated");
  controller.beginApply(cycle.id, proposal.id);
  const originalPublish = SkillBundleFiles.prototype.publish;
  let observedReservation = false;
  SkillBundleFiles.prototype.publish = function (id, hooks) {
    return originalPublish.call(this, id, {
      ...hooks,
      beforePublish: (operation) => {
        hooks?.beforePublish?.(operation);
        assert.throws(
          () => f.core.skills.assertConsumerMutation([f.read(method)]),
          fails("STORE_BUSY"),
        );
        observedReservation = true;
      },
    });
  };
  t.after(() => {
    SkillBundleFiles.prototype.publish = originalPublish;
  });
  const result = await controller.withApplyPermit(cycle.id, proposal.id, () =>
    f.adapter.applySleep(
      change,
      proposal,
      controller.status(cycle.id) as SleepState,
      f.ctx,
    ),
  );
  assert.equal(observedReservation, true);
  assert.equal(result.revision, 2);
  const settled = controller.settleSkill(cycle.id, proposal.id, result);
  assert.equal(settled.improvements, 1);
  assert.equal(settled.phase, "future_check");
  assert.equal(
    readFileSync(join(f.project, f.path, "SKILL.md"), "utf8"),
    "Clarified entry\n",
  );
  assert.equal(
    f.core.skills.version(f.skillId, 1).manifest.content_hash,
    before.manifest.content_hash,
  );
  assert.equal(
    canonical(f.core.skills.inspect(f.skillId).metadata),
    canonical(before.metadata),
  );
});

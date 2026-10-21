// Native package discovery + real SDK tool calls. No prompt/provider dispatch.
import assert from "node:assert/strict";
import { existsSync, readFileSync, writeFileSync } from "node:fs";
import { join, resolve } from "node:path";
import { pathToFileURL } from "node:url";

const [sdkPath, expectedPackage, action, reportPath] = process.argv.slice(2);
const sdk = await import(pathToFileURL(resolve(sdkPath)).href);
const cwd = process.cwd(),
  agentDir = sdk.getAgentDir(),
  calls = [],
  notices = [];
const settingsManager = sdk.SettingsManager.create(cwd, agentDir);
const loader = new sdk.DefaultResourceLoader({
  cwd,
  agentDir,
  settingsManager,
});
await loader.reload({
  resolveProjectTrust: async () => action !== "untrusted",
});
assert.deepEqual(loader.getExtensions().errors, []);
const extensions = loader.getExtensions().extensions.map((ext) => ext.path);
const productExtension = join(
  resolve(expectedPackage),
  "src/extension/index.ts",
);
assert.equal(
  extensions.filter((p) => resolve(p) === productExtension).length,
  1,
);
const skills = loader
  .getSkills()
  .skills.filter((s) => s.name.startsWith("zaratustra-"));
assert.deepEqual(skills.map((s) => s.name).sort(), [
  "zaratustra-memory",
  "zaratustra-work",
]);
assert.ok(
  skills.every((s) => resolve(s.filePath).startsWith(resolve(expectedPackage))),
);
// Empty test auth location is standard isolated host storage. No credentials copied.
const runtime = await sdk.ModelRuntime.create({
  modelsPath: null,
  modelsStorePath: join(agentDir, "models.json"),
  allowModelNetwork: false,
});
const model = runtime.getModel("openai-codex", "gpt-6.1-sol");
assert.ok(model);
const { session } = await sdk.createAgentSession({
  cwd,
  agentDir,
  settingsManager,
  resourceLoader: loader,
  modelRuntime: runtime,
  model,
  thinkingLevel: "medium",
  sessionManager: sdk.SessionManager.inMemory(),
});
await session.bindExtensions({});
const runner = session.extensionRunner;
runner.setUIContext(
  {
    ...runner.getUIContext(),
    notify: (message) => notices.push(message),
    confirm: async () => true,
  },
  "rpc",
);
const run = async (name, args) => {
  const id = "startup-" + (calls.length + 1);
  const result = await runner
    .getToolDefinition(name)
    .execute(id, args, undefined, undefined, runner.createToolContext(id));
  calls.push({ name, args, result });
  return result.details;
};
let contextTypes = [];
const snap = async () => {
  const messages = await runner.emitContext([]);
  contextTypes = messages.map((m) => m.customType).filter(Boolean);
  return JSON.parse(
    messages.find((m) => m.customType === "zaratustra.snapshot.v1").content,
  );
};
let snapshot;
try {
  snapshot = await snap();
  if (action === "inspect" || action === "untrusted") {
    // Parent checks failure details and filesystem preservation, including no writes.
  } else {
    assert.notEqual(snapshot.available, false, JSON.stringify(snapshot));
    const paths = snapshot.workspace_paths;
    assert.ok(paths);
    if (paths.profile === "project-local") {
      assert.equal(paths.memory, join(cwd, ".local/memory"));
      for (const name of ["memory", "imports", "output", "backups"])
        assert.ok(existsSync(join(cwd, ".local", name)));
      assert.equal(readFileSync(join(cwd, ".local/.gitignore"), "utf8"), "*\n");
    }
    const health = await run("zara_doctor", {});
    assert.notEqual(health.ok, false, JSON.stringify(health));
    if (action === "integrity") {
      await runner.emitInput(
        "Synthetic explicitly configured ingress.",
        undefined,
        "interactive",
      );
      const source = (await snap()).captured_sources.at(-1);
      assert.equal(source.input_integrity, "trusted_first_untransformed");
      assert.equal(source.owner_channel_eligible, true);
    } else if (action === "init") {
      await runner.emitInput(
        "Synthetic ordinary startup statement.",
        undefined,
        "interactive",
      );
      const source = (await snap()).captured_sources.at(-1);
      assert.equal(source.input_integrity, "observed_stage_only");
      assert.equal(source.owner_channel_eligible, false);
      assert.equal(source.channel_identity, null);
      const result = await run("zara_commit", {
        request_id: "startup-once",
        reason: "Save synthetic ordinary memory",
        source_handles: [source.source_handle],
        guards: [],
        ops: [
          {
            op: "import_evidence",
            client_ref: "origin",
            source_handle: source.source_handle,
            title: "Observed statement",
            source_language: "en",
          },
          {
            op: "create_record",
            client_ref: "activity",
            kind: "activity",
            title: "Startup synthetic continuity",
            visibility: "workspace",
            data: {
              purpose: "Verify persistent ordinary startup",
              status: "active",
            },
          },
          {
            op: "create_record",
            client_ref: "knowledge",
            kind: "knowledge",
            title: "Synthetic observed preference",
            visibility: "workspace",
            data: {
              knowledge_kind: "preference",
              statement: "The synthetic speaker prefers concise notes.",
              state: "current",
              basis: "user_statement",
              evidence_refs: [{ client_ref: "origin" }],
              conditions: {},
              valid_from: null,
              valid_to: null,
              observed_at: null,
              supersedes_refs: [],
              representation: {
                kind: "English paraphrase",
                source_ref: { client_ref: "origin" },
                source_language: "en",
              },
            },
          },
        ],
      });
      assert.equal(result.committed, true, JSON.stringify(result));
      const evidence = (await run("zara_read", { id: result.created.origin }))
        .data;
      assert.equal(
        evidence.data.provenance.input_integrity,
        "observed_stage_only",
      );
      assert.equal(evidence.data.provenance.original_keystrokes, false);
      assert.equal(evidence.data.provenance.owner_channel_eligible, false);
      const feedback = await run("zara_commit", {
        request_id: "startup-not-owner-feedback",
        reason: "Verify observed-stage authority limit",
        source_handles: [source.source_handle],
        guards: [],
        ops: [
          {
            op: "record_evaluation",
            client_ref: "feedback",
            target_ref: { id: result.created.knowledge, revision: 1 },
            run_ref: null,
            assessment: "unhelpful",
            dimension: "usefulness",
            dimension_name: "Synthetic preference result",
            basis: "user_feedback",
            evidence_refs: [{ id: result.created.origin }],
            event_time: null,
            supersedes_evaluation_ref: null,
            explanation:
              "A synthetic observed stage cannot certify owner feedback",
          },
        ],
      });
      assert.equal(feedback.code, "SOURCE_MISSING", JSON.stringify(feedback));
      assert.equal((await run("zara_backup", {})).code, "PERMISSION_DENIED");
      const imported = await run("zara_import", {
        path: join(paths.imports[0], "fixture.md"),
      });
      assert.equal(imported.ok, true, JSON.stringify(imported));
      const material = await run("zara_commit", {
        request_id: "startup-material",
        reason: "Retain synthetic local import",
        source_handles: [imported.source_handle],
        guards: [],
        ops: [
          {
            op: "import_evidence",
            client_ref: "material",
            source_handle: imported.source_handle,
            title: "Startup material",
            source_language: "en",
          },
        ],
      });
      assert.equal(material.committed, true, JSON.stringify(material));
      const args = {
        path: join(paths.output, "report.txt"),
        content: "Synthetic controlled startup output.\n",
      };
      const proposal = await run("zara_file_preview", {
        request_id: "startup-output",
        tool: "write",
        arguments: args,
        consequence: "Write the synthetic output",
        alternatives: "Keep output absent",
        independent_basis: "New isolated startup test artifact",
      });
      assert.ok(proposal.request_id, JSON.stringify(proposal));
      assert.equal(
        (await run("zara_confirm", { preview_ref: proposal.request_id })).code,
        "APPROVAL_REQUIRED",
      );
      // Mechanical TUI mode injection, never owner testimony. RPC hasUI above is insufficient.
      runner.setUIContext(
        { ...runner.getUIContext(), confirm: async () => true },
        "tui",
      );
      assert.equal(
        (await run("zara_confirm", { preview_ref: proposal.request_id }))
          .status,
        "approved-transient",
      );
      const id = "startup-native-write";
      const block = await runner.emitToolCall({
        type: "tool_call",
        toolName: "write",
        toolCallId: id,
        input: args,
      });
      assert.ok(!block?.block, JSON.stringify(block));
      const written = await sdk.createWriteTool(cwd).execute(id, args);
      await runner.emitToolResult({
        type: "tool_result",
        toolName: "write",
        toolCallId: id,
        input: args,
        ...written,
        isError: false,
      });
      assert.equal(readFileSync(args.path, "utf8"), args.content);
    } else if (action === "read") {
      const result = await run("zara_search", {
        query: "Startup synthetic continuity",
        match: "phrase",
      });
      assert.ok(
        JSON.stringify(result).includes("Startup synthetic continuity"),
        JSON.stringify(result),
      );
    } else if (action === "backup") {
      const backup = await run("zara_backup", {});
      assert.notEqual(backup.ok, false, JSON.stringify(backup));
      assert.equal(backup.complete, true, JSON.stringify(backup));
      assert.ok(existsSync(join(backup.backup, "manifest.json")));
    }
    snapshot = await snap();
  }
} finally {
  await runner.emit({ type: "session_shutdown", reason: "exit" });
  session.dispose();
  writeFileSync(
    reportPath,
    JSON.stringify(
      {
        cwd,
        expectedPackage,
        extensions,
        skills,
        action,
        snapshot,
        calls,
        notices,
        node: process.version,
        pi: sdk.VERSION,
        provider_dispatches: 0,
        mechanical_only: true,
        contextTypes,
      },
      null,
      2,
    ),
  );
}

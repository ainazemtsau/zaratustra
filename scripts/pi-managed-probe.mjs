// Exercise installed Pi and the packaged adapter with synthetic UI and model replies.
import assert from "node:assert/strict";
import { randomUUID } from "node:crypto";
import { mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { findPackageJSON } from "node:module";
import { dirname, join, resolve } from "node:path";
import { pathToFileURL } from "node:url";
import { setTimeout as delay } from "node:timers/promises";

const [sdkRoot, project, agentDir, reportPath] = process.argv.slice(2);
assert.equal(resolve(process.env.PI_CODING_AGENT_DIR), agentDir);
process.env.ZARATUSTRA_TEST_CONTROLLER = "isolated-managed-probe";
globalThis.fetch = () => {
  throw new Error("Network access is disabled for this fixture");
};
const sdkVersion = JSON.parse(
  readFileSync(join(sdkRoot, "package.json"), "utf8"),
).version;
const sdkEntry = pathToFileURL(join(sdkRoot, "dist/index.js"));
const sdk = await import(sdkEntry);
const piAI = findPackageJSON("@earendil-works/pi-ai", sdkEntry);
assert.ok(piAI);
const { createAssistantMessageEventStream, getCurrentTools } = await import(
  pathToFileURL(join(dirname(piAI), "dist/index.js"))
);
const runtime = await sdk.ModelRuntime.create({
  authPath: join(agentDir, "auth.json"),
  modelsPath: null,
  modelsStorePath: join(agentDir, "models-store.json"),
  allowModelNetwork: false,
  refreshOnCreate: false,
});
const model = runtime.getModel("openai", "gpt-4.1");
assert.ok(model);
const settings = sdk.SettingsManager.create(project, agentDir, {
  projectTrusted: true,
});
const loader = new sdk.DefaultResourceLoader({
  cwd: project,
  agentDir,
  settingsManager: settings,
  noContextFiles: true,
});
await loader.reload();
assert.deepEqual(loader.getExtensions().errors, []);
const { session } = await sdk.createAgentSession({
  cwd: project,
  agentDir,
  modelRuntime: runtime,
  model,
  thinkingLevel: "off",
  settingsManager: settings,
  resourceLoader: loader,
  sessionManager: sdk.SessionManager.inMemory(project),
});

let serial = 0;
const dialogs = [];
const answers = [];
let generations = 0;
const toolResults = [];
const sleepSteps = [];
let streamError;
const modelRuntimeCreate = sdk.ModelRuntime.create;
sdk.ModelRuntime.create = async () => runtime;
runtime.streamSimple = (_model, context) => {
  assert.equal(_model.id, model.id);
  assert.equal(_model.provider, model.provider);
  generations++;
  try {
    const tools = context.tools ?? getCurrentTools?.(context.messages) ?? [];
    assert.deepEqual(tools.map((tool) => tool.name).sort(), [
      "sleep_analyze",
      "sleep_apply",
      "sleep_finish",
      "sleep_propose",
      "sleep_read",
    ]);
  } catch (error) {
    streamError = error;
    throw error;
  }
  for (const message of context.messages.filter((m) => m.role === "toolResult"))
    toolResults.push({
      name: message.toolName,
      isError: message.isError,
      content: message.content,
    });
  const step = sleepSteps.shift();
  assert.ok(
    step !== undefined || generations === 4,
    "Unexpected Sleep generation",
  );
  const stream = createAssistantMessageEventStream();
  const message = {
    role: "assistant",
    content: step
      ? [{ type: "toolCall", id: "sleep-" + generations, ...step }]
      : [],
    provider: model.provider,
    api: model.api,
    model: model.id,
    usage: {
      input: 0,
      output: 0,
      cacheRead: 0,
      cacheWrite: 0,
      totalTokens: 0,
      cost: { input: 0, output: 0, cacheRead: 0, cacheWrite: 0, total: 0 },
    },
    stopReason: step ? "toolUse" : "stop",
    timestamp: Date.now(),
  };
  stream.push({ type: "start", partial: message });
  stream.push({ type: "done", reason: message.stopReason, message });
  stream.end(message);
  return stream;
};

try {
  await session.bindExtensions({ mode: "sdk" });
  const runner = session.extensionRunner;
  const ui = {
    ...runner.getUIContext(),
    confirm: async (title, message) => {
      assert.ok(answers.length, "Unexpected native confirmation");
      const answer = answers.shift();
      dialogs.push({ title, message, answer });
      return answer;
    },
  };
  runner.setUIContext(ui, "sdk");
  async function call(name, args, expectedError) {
    const id = `pi-managed-${++serial}`;
    const tool = runner.getToolDefinition(name);
    assert.ok(tool, name);
    const result = await tool.execute(
      id,
      args,
      undefined,
      undefined,
      runner.createToolContext(id),
    );
    if (expectedError) {
      assert.equal(result.isError, true, JSON.stringify(result));
      assert.equal(result.details.code, expectedError, JSON.stringify(result));
    } else {
      assert.ok(!result.isError, `${name}: ${JSON.stringify(result.details)}`);
    }
    return result.details;
  }
  assert.equal((await call("zara_map", {})).schema_version, 11);
  const bundle = "skills/personal/managed-probe";
  const entry = join(project, bundle, "SKILL.md");
  mkdirSync(dirname(entry), { recursive: true });
  writeFileSync(
    join(dirname(entry), "bundle.json"),
    JSON.stringify({
      format: 1,
      skill_id: randomUUID(),
      name: "Managed probe",
      entry: "SKILL.md",
    }),
  );
  const original = "Original synthetic instructions.\r\n";
  const updated = "Updated synthetic instructions.\n";
  writeFileSync(entry, original);
  const preview = (options = {}) =>
    call("zara_skill_bundle_preview", {
      operation_id: randomUUID(),
      path: bundle,
      consequence: "Apply exact synthetic changes",
      alternatives: "Keep the current bytes",
      ...options,
    });
  const confirm = (prepared, answer) => {
    answers.push(answer);
    return call("zara_confirm", { preview_ref: prepared.preview.request_id });
  };
  const apply = (prepared, expectedError) =>
    call(
      "zara_skill_bundle_apply",
      {
        request: prepared.request,
        preview_ref: prepared.preview.request_id,
      },
      expectedError,
    );
  const registration = await preview();
  await confirm(registration, true);
  const first = (await apply(registration)).receipt;
  assert.equal(first.revision, 1);
  const changes = [{ path: "SKILL.md", content: updated }];
  const declined = await preview({ changes });
  await confirm(declined, false);
  await apply(declined, "APPROVAL_STALE");
  assert.equal(readFileSync(entry, "utf8"), original);
  const edit = await preview({ changes });
  await confirm(edit, true);
  assert.match(dialogs.at(-1).message, /Updated synthetic instructions/);
  assert.equal((await apply(edit)).receipt.revision, 2);
  assert.equal(readFileSync(entry, "utf8"), updated);
  const restore = await preview({ restore_revision: 1 });
  await confirm(restore, true);
  const rollback = (await apply(restore)).receipt;
  assert.equal(rollback.revision, 3);
  assert.equal(rollback.content_hash, first.content_hash);
  assert.equal(readFileSync(entry, "utf8"), original);

  const source = "The synthetic reviewer prefers concise notes.";
  await runner.emitInput(source, undefined, "rpc");
  const snapshot = (await runner.emitContext([])).find(
    (message) => message.customType === "zaratustra.snapshot.v1",
  );
  const handle = JSON.parse(snapshot.content).captured_sources.at(
    -1,
  ).source_handle;
  const request = {
    request_id: randomUUID(),
    reason: "Create a synthetic Sleep review candidate",
    source_handles: [handle],
    guards: [],
    ops: [
      {
        op: "import_evidence",
        client_ref: "origin",
        source_handle: handle,
        title: "Synthetic statement",
        source_language: "en",
      },
      {
        op: "create_record",
        client_ref: "note",
        kind: "knowledge",
        title: "Synthetic review candidate",
        visibility: "workspace",
        data: {
          knowledge_kind: "preference",
          statement: source,
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
  };
  const seed = await call("zara_preview", {
    request,
    consequence: "Save one synthetic note",
    alternatives: "Keep the fixture empty",
  });
  assert.ok(seed.request_id, JSON.stringify(seed));
  await confirm({ preview: seed }, true);
  const saved = await call("zara_commit", {
    ...request,
    preview_ref: seed.request_id,
  });
  assert.equal(saved.committed, true);
  await session.bindExtensions({
    mode: "tui",
    uiContext: {
      ...ui,
      select: async (_title, options) => {
        assert.ok(options.includes("Confirm"));
        return "Confirm";
      },
    },
  });
  const tui = await preview({ changes });
  const tuiRef = tui.preview.request_id;
  assert.equal(
    (await call("zara_confirm", { preview_ref: tuiRef })).status,
    "review_in_chat",
  );
  assert.ok(
    session.sessionManager
      .getBranch()
      .some(
        (entry) =>
          entry.type === "custom_message" &&
          entry.customType === "zaratustra.proposal" &&
          entry.details?.preview === tuiRef &&
          entry.content.includes(updated.trim()),
      ),
  );
  assert.equal((await confirm(tui, false)).status, "declined");
  await apply(tui, "APPROVAL_STALE");
  assert.equal(readFileSync(entry, "utf8"), original);
  runner.setUIContext(ui, "sdk");
  const ref = { id: saved.created.note, revision: 1 };
  sleepSteps.push(
    { name: "sleep_read", arguments: { ref } },
    {
      name: "sleep_analyze",
      arguments: {
        question: "Does the recorded preference need a correction?",
        observations: source,
        hypothesis: null,
        grounds: [ref],
        counterexamples: [],
      },
    },
    {
      name: "sleep_finish",
      arguments: {
        outcome: "no_change",
        summary: "The recorded preference has no conflicting evidence.",
        continuation: null,
      },
    },
  );

  // Exercise the actual child AgentSession with scripted transport responses.
  const started = await call("zara_sleep", { action: "start" });
  assert.equal(started.background, true);
  const id = started.review.id;
  let review;
  for (let i = 0; i < 200; i++) {
    ({ review } = await call("zara_sleep", { action: "status", run_id: id }));
    if (review.status !== "running") break;
    await delay(25);
  }
  if (streamError) throw streamError;
  assert.equal(
    review.status,
    "completed",
    JSON.stringify({ review, generations, toolResults }),
  );
  assert.equal(review.outcome, "no_change");
  assert.equal(review.generations, 3);
  assert.deepEqual(review.read_refs, [ref]);
  assert.deepEqual(review.analysis.grounds, [ref]);
  assert.equal(answers.length, 0);
  assert.deepEqual(
    dialogs.map(({ answer }) => answer),
    [true, false, true, true, true, false],
  );
  writeFileSync(
    reportPath,
    JSON.stringify(
      {
        sdk_version: sdkVersion,
        confirmation: "approved exact request; refusal blocked publication",
        tui_confirmation:
          "delivered exact preview before scripted native refusal",
        rollback_revision: rollback.revision,
        rollback_restored_exact_bytes: true,
        sleep: {
          status: review.status,
          outcome: review.outcome,
          generations: review.generations,
        },
        synthetic_provider_turns: generations,
        provider_network_calls: 0,
      },
      null,
      2,
    ) + "\n",
  );
} finally {
  await session.extensionRunner.emit({
    type: "session_shutdown",
    reason: "exit",
  });
  session.dispose();
  sdk.ModelRuntime.create = modelRuntimeCreate;
}

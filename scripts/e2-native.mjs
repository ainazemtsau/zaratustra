// Mechanical SDK qualification only. Real native tools/UI event runner; zero provider network requests.
import assert from "node:assert/strict";
import {
  mkdirSync,
  existsSync,
  readFileSync,
  writeFileSync,
  statSync,
} from "node:fs";
import { join, resolve } from "node:path";
import { pathToFileURL } from "node:url";
import { DatabaseSync } from "node:sqlite";
const [pkgArg, outArg] = process.argv.slice(2),
  pkg = resolve(pkgArg),
  out = resolve(outArg);
assert.equal(existsSync(out), false, "New synthetic output required");
mkdirSync(out, { recursive: true });
const sdk = await import(pathToFileURL(process.env.ZARA_PI_SDK).href);
const dialogs = [],
  calls = [],
  checks = [];
let serial = 0,
  choices = [],
  throwsObserver = false,
  dispatches = 0;
const log = (name, value) =>
  writeFileSync(join(out, name + ".json"), JSON.stringify(value, null, 2));
process.on("exit", () => {
  log("dialogs", dialogs);
  log("calls", calls);
});
async function start(profile, homeName = "home", cwdName = "cwd") {
  const base = join(out, profile),
    agentDir = join(base, "agent"),
    cwd = join(base, cwdName),
    home = join(base, homeName),
    output = join(base, "output");
  for (const p of [agentDir, cwd, output]) mkdirSync(p, { recursive: true });
  process.env.PI_CODING_AGENT_DIR = agentDir;
  process.env.ZARATUSTRA_HOME = home;
  process.env.ZARATUSTRA_SCOPES =
    profile === "protected" ? '["restricted:read","restricted:write"]' : "[]";
  process.env.ZARATUSTRA_TEST_CONTROLLER = "registered-synthetic-native-E2";
  process.env.ZARATUSTRA_OUTPUT_ROOT = output;
  const runtime = await sdk.ModelRuntime.create({
    authPath: process.env.ZARA_AUTH_PATH,
    modelsPath: null,
    modelsStorePath: join(agentDir, "models.json"),
    allowModelNetwork: false,
  });
  const model = runtime.getModel("openai-codex", "gpt-6.1-sol");
  assert.ok(model);
  const settingsManager = sdk.SettingsManager.create(cwd, agentDir);
  const loader = new sdk.DefaultResourceLoader({
    cwd,
    agentDir,
    settingsManager,
    noExtensions: true,
    additionalExtensionPaths: [join(pkg, "src/extension/index.ts")],
    extensionFactories: [
      (pi) => {
        pi.on("before_provider_request", () => {
          if (throwsObserver)
            throw Error("Synthetic throwing observer is NOT a veto");
          dispatches++;
          throw Error(
            "No real provider request permitted in mechanical script",
          );
        });
      },
    ],
  });
  await loader.reload();
  assert.deepEqual(loader.getExtensions().errors, []);
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
      confirm: async (title, message) => {
        assert.ok(
          choices.length,
          "Every synthetic dialog reply is predeclared",
        );
        const choice = choices.shift();
        dialogs.push({ profile, title, message, choice, synthetic: true });
        return choice;
      },
      notify: (text, type) => calls.push({ notification: text, type }),
    },
    "rpc",
  );
  const custom = async (name, args) => {
    const callId = "sdk-custom-" + ++serial;
    const result = await runner
      .getToolDefinition(name)
      .execute(
        callId,
        args,
        undefined,
        undefined,
        runner.createToolContext(callId, undefined),
      );
    calls.push({ profile, name, args, result });
    return result.details;
  };
  const snap = async () =>
    JSON.parse(
      (await runner.emitContext([])).find(
        (m) => m.customType === "zaratustra.snapshot.v1",
      ).content,
    );
  await runner.emitInput(
    "Synthetic direct instruction. Prior word: да. This is programmatic, not Anton.",
    undefined,
    "rpc",
  );
  const source = (await snap()).captured_sources.at(-1).source_handle;
  const req = (ops) => ({
    request_id: "sdk-domain-" + ++serial,
    reason: "Synthetic SDK exact proposal",
    source_handles: [source],
    guards: [],
    ops,
  });
  const native = async (name, args, dropResult = false) => {
    const callId = "sdk-native-" + ++serial;
    const block = await runner.emitToolCall({
      type: "tool_call",
      toolName: name,
      toolCallId: callId,
      input: args,
    });
    calls.push({ profile, name, args, callId, block });
    if (block?.block) return { block };
    const tool =
      name === "write"
        ? sdk.createWriteTool(cwd)
        : name === "edit"
          ? sdk.createEditTool(cwd)
          : sdk.createPowerShellTool(cwd);
    const result = await tool.execute(callId, args);
    if (!dropResult)
      await runner.emitToolResult({
        type: "tool_result",
        toolName: name,
        toolCallId: callId,
        input: args,
        content: result.content,
        isError: false,
      });
    return { callId, result };
  };
  return {
    profile,
    base,
    cwd,
    home,
    output,
    session,
    runner,
    model,
    custom,
    snap,
    source,
    req,
    native,
    close: async () => {
      await runner.emit({ type: "session_shutdown", reason: "exit" });
      session.dispose();
    },
  };
}
for (const profile of ["workspace", "protected"]) {
  const f = await start(profile);
  try {
    const visibility = profile === "protected" ? "restricted" : "workspace";
    const r = await f.custom(
      "zara_commit",
      f.req(
        ["A", "B"].map((client_ref) => ({
          op: "create_record",
          client_ref,
          kind: "entity",
          title: client_ref,
          visibility,
          data: {
            entity_kind: "item",
            aliases: [],
            disambiguation: "Synthetic SDK item",
            status: "active",
          },
        })),
      ),
    );
    assert.equal(r.committed, true);
    const request = f.req([
      {
        op: "merge_identity",
        from_ref: { id: r.created.A },
        to_ref: { id: r.created.B },
      },
    ]);
    request.guards = Object.values(r.created).map((id) => ({
      ref: { id },
      expected_revision: 1,
    }));
    assert.equal(
      (await f.custom("zara_commit", request)).code,
      "APPROVAL_REQUIRED",
    );
    const p = await f.custom("zara_preview", {
      request,
      consequence:
        "Объединить ровно A в B, сохранить старую identity и историю",
      alternatives: "Оставить A и B раздельными",
    });
    assert.equal(
      (
        await f.custom("zara_confirm", {
          preview_ref: p.request_id,
          approved: true,
        })
      ).code,
      "VALIDATION_ERROR",
    );
    choices.push(false);
    const refusal = await f.custom("zara_confirm", {
      preview_ref: p.request_id,
    });
    assert.equal(refusal.status, "declined");
    assert.equal(
      (await f.custom("zara_commit", { ...request, preview_ref: p.request_id }))
        .code,
      "APPROVAL_STALE",
    );
    const p2 = await f.custom("zara_preview", {
      request,
      consequence: "Объединить только A в B",
      alternatives: "Оставить раздельными",
    });
    choices.push(true);
    assert.equal(
      (await f.custom("zara_confirm", { preview_ref: p2.request_id })).status,
      "approved-transient",
    );
    const commit = await f.custom("zara_commit", {
      ...request,
      preview_ref: p2.request_id,
    });
    assert.equal(commit.committed, true);
    assert.deepEqual(
      await f.custom("zara_commit", { ...request, preview_ref: p2.request_id }),
      commit,
    );
    const args = {
      path: join(f.output, "report.txt"),
      content: "\ufeffExact SDK output\r\nΩ 🦉\r\n",
    };
    const file = await f.custom("zara_file_preview", {
      request_id: "sdk-file",
      tool: "write",
      independent_basis: "Independent new synthetic SDK file action",
      arguments: args,
      consequence: "Записать показанные точные bytes в report.txt",
      alternatives: "Не создавать файл",
    });
    choices.push(true);
    await f.custom("zara_confirm", { preview_ref: file.request_id });
    const changed = await f.native("write", { ...args, content: "different" });
    assert.equal(changed.block.block, true);
    assert.ok(!existsSync(args.path));
    await f.native("write", args);
    assert.deepEqual(readFileSync(args.path), Buffer.from(args.content));
    const state = await f.custom("zara_read", { request_id: "sdk-file" });
    assert.equal(state.data.status, "confirmed");
    assert.equal(state.data.receipt.writer_attribution, "unknown");
    const replay = await f.custom("zara_file_preview", {
      request_id: "sdk-file",
      tool: "write",
      independent_basis: "Independent new synthetic SDK file action",
      arguments: args,
      consequence: "Same request replay",
      alternatives: "Inspect",
    });
    assert.equal(replay.dispatch, false);
    assert.deepEqual(replay.receipt, state.data.receipt);
    assert.equal((await f.native("write", args)).block.block, true);
    assert.equal(
      (await f.native("write", { ...args, path: "@" + args.path })).block.block,
      true,
    );
    const lostArgs = {
      path: join(f.output, "lost.txt"),
      content: "Written before lost tool_result\n",
    };
    const lost = await f.custom("zara_file_preview", {
      request_id: "lost-native",
      tool: "write",
      independent_basis: "Independent new synthetic SDK file action",
      arguments: lostArgs,
      consequence: "Записать конечный текст",
      alternatives: "Не писать",
    });
    choices.push(true);
    await f.custom("zara_confirm", { preview_ref: lost.request_id });
    await f.native("write", lostArgs, true);
    const payload = {
      messages: [
        {
          role: "user",
          content: "Already loaded synthetic personal context Ω",
        },
        { role: "toolResult", content: "Prior memory output" },
      ],
    };
    throwsObserver = true;
    const returned = await f.runner.emitBeforeProviderRequest(payload);
    assert.equal(returned, payload);
    throwsObserver = false;
    // Same actual selected model, native API: source=set alone never becomes a new human-choice witness.
    await f.session.setModel(f.model);
    assert.equal(f.session.model.id, f.model.id);
    await f.session.sendCustomMessage(
      {
        customType: "synthetic.loaded-context",
        content:
          "Already loaded private-synthetic context; no HTTP recipient receives this script",
        display: false,
      },
      { triggerTurn: false },
    );
    const beforeTranscript = JSON.stringify(f.session.messages);
    // Inject a model_select EVENT, without changing the actual selected model or sending a request.
    choices.push(false);
    await f.runner.emit({
      type: "model_select",
      model: { ...f.model, id: "synthetic-unexplained-recipient" },
      previousModel: f.model,
      source: "set",
    });
    assert.equal((await f.custom("zara_map", {})).code, "PERMISSION_DENIED");
    assert.equal(JSON.stringify(f.session.messages), beforeTranscript);
    assert.equal(f.session.model.id, f.model.id);
    checks.push({
      profile,
      merge: true,
      refusal: true,
      forged_flag: true,
      write_readback: true,
      replay_no_dispatch: true,
      lost_after_write: true,
      throwing_observer_returns_original: true,
      unexplained_event_denies_new_reads: true,
      loaded_transcript_not_purged: true,
      actual_selected_model_unchanged: true,
    });
  } finally {
    await f.close();
  }
  const fresh = await start(profile, "home", "new-process-cwd");
  try {
    const page = await fresh.custom("zara_browse", {
      view: "operations",
      limit: 50,
    });
    const attempt = page.data.cards.find(
      (c) => c.kind === "managed_file" && c.request_id === "lost-native",
    );
    assert.ok(attempt);
    assert.equal(attempt.status, "unknown");
    const target = join(fresh.output, "lost.txt"),
      mtime = statSync(target).mtimeMs;
    const inspect = await fresh.custom("zara_file_inspect", {
      request_id: attempt.request_id,
    });
    assert.equal(inspect.status, "confirmed");
    assert.equal(statSync(target).mtimeMs, mtime);
    // Opaque native shell is outside the file protocol; no adapter fiction of deduplication.
    const opaque = join(fresh.base, "opaque-effect.txt");
    await fresh.native(
      "powershell",
      {
        command: `Add-Content -LiteralPath '${opaque.replaceAll("'", "''")}' -Value 'one actual opaque effect'`,
      },
      true,
    );
    assert.match(readFileSync(opaque, "utf8"), /one actual opaque effect/);
    const db = new DatabaseSync(join(fresh.home, "zara.sqlite"), {
      readOnly: true,
    });
    const effects = db
      .prepare(
        "SELECT json FROM intents WHERE json_extract(json,'$.kind')='managed_file'",
      )
      .all();
    db.close();
    assert.equal(effects.length, 2);
    checks.push({
      profile,
      fresh_process_inspect_without_repeat: true,
      opaque_command_has_no_managed_dedup_receipt: true,
      opaque_actual_invocations: 1,
    });
  } finally {
    await fresh.close();
  }
}
assert.equal(dispatches, 0);
assert.equal(choices.length, 0);
log("dialogs", dialogs);
log("calls", calls);
log("verification", {
  mechanical_only: true,
  provider_network_requests: 0,
  actual_selected_model_changed: false,
  checks,
});
console.log(
  JSON.stringify({
    checks: checks.length,
    dialogs: dialogs.length,
    provider_network_requests: 0,
  }),
);

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

const f = await start("workspace");
try {
  await f.session.sendCustomMessage({customType:"synthetic.loaded-context",content:"Existing synthetic transcript must remain visible when recipient authority is unresolved",display:false},{triggerTurn:false});
  const transcript = JSON.stringify(f.session.messages);
  choices.push(false);
  await f.runner.emit({type:"model_select",model:{...f.model,id:"synthetic-unexplained-recipient"},previousModel:f.model,source:"restore"});
  assert.equal((await f.custom("zara_map", {})).code, "PERMISSION_DENIED");
  assert.equal(JSON.stringify(f.session.messages), transcript);
  choices.push(true);
  await f.session.setModel(f.model);
  assert.equal(f.session.model.id, "gpt-6.1-sol");
  const result = await f.custom("zara_map", {});
  assert.equal(result.ok, true);
  const snapshot = await f.snap();
  assert.match(snapshot.recipient_authority, /^explicit-native-dialog:synthetic-controller:/);
  assert.match(dialogs.at(-1).message, /openai-codex\/gpt-6.1-sol/);
  assert.match(dialogs.at(-1).message, /already loaded conversation/);
  assert.equal(JSON.stringify(f.session.messages), transcript);
  assert.equal(dispatches, 0);
  assert.equal(choices.length, 0);
  log("verification", {mechanical_only:true,source_event_injected:true,actual_selected_model_changed:false,provider_network_requests:0,declined_unexplained_event_blocks_reads:true,explicit_registered_dialog_binds_actual_native_selected_recipient:true,loaded_transcript_scope_named:true,transcript_not_purged:true,snapshot});
} finally {await f.close();}
console.log(JSON.stringify({qualified:true,dialogs:dialogs.length,provider_network_requests:dispatches}));

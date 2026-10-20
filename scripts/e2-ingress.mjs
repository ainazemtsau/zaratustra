// Real Pi SDK contexts in RPC/TUI modes; M injection, never a human-origin trial.
import assert from "node:assert/strict";
import { mkdirSync, writeFileSync } from "node:fs";
import { join, resolve } from "node:path";
import { pathToFileURL } from "node:url";
const [pkgArg, outArg, expected = "fixed"] = process.argv.slice(2),
  pkg = resolve(pkgArg),
  out = resolve(outArg);
mkdirSync(out, { recursive: false });
const sdk = await import(pathToFileURL(process.env.ZARA_PI_SDK).href),
  results = [];
for (const [mode, controller] of [
  ["rpc", null],
  ["print", null],
  ["rpc", "registered-synthetic-native-E2"],
  ["tui", null],
]) {
  const root = join(out, mode + (controller ? "-registered" : "-unregistered")),
    agentDir = join(root, "agent"),
    cwd = join(root, "cwd");
  for (const p of [agentDir, cwd]) mkdirSync(p, { recursive: true });
  process.env.PI_CODING_AGENT_DIR = agentDir;
  process.env.ZARATUSTRA_HOME = join(root, "home");
  process.env.ZARATUSTRA_SCOPES = "[]";
  delete process.env.ZARATUSTRA_OUTPUT_ROOT;
  if (controller) process.env.ZARATUSTRA_TEST_CONTROLLER = controller;
  else delete process.env.ZARATUSTRA_TEST_CONTROLLER;
  const runtime = await sdk.ModelRuntime.create({
    authPath: process.env.ZARA_AUTH_PATH,
    modelsPath: null,
    modelsStorePath: join(agentDir, "models.json"),
    allowModelNetwork: false,
  });
  const model = runtime.getModel("openai-codex", "gpt-6.1-sol"),
    settingsManager = sdk.SettingsManager.create(cwd, agentDir);
  const loader = new sdk.DefaultResourceLoader({
    cwd,
    agentDir,
    settingsManager,
    noExtensions: true,
    additionalExtensionPaths: [join(pkg, "src/extension/index.ts")],
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
    sessionManager: sdk.SessionManager.inMemory(),
  });
  await session.bindExtensions({});
  const r = session.extensionRunner;
  let dialogCalls = 0;
  r.setUIContext(
    {
      ...r.getUIContext(),
      confirm: async () => {
        dialogCalls++;
        return true;
      },
    },
    mode,
  );
  const run = async (name, args) => {
    const id = "ingress-" + name;
    return (
      await r
        .getToolDefinition(name)
        .execute(
          id,
          args,
          undefined,
          undefined,
          r.createToolContext(id, undefined),
        )
    ).details;
  };
  try {
    await r.emitInput("yes, old programmatic word", undefined, "rpc");
    const snapshot = JSON.parse(
        (await r.emitContext([])).find(
          (m) => m.customType === "zaratustra.snapshot.v1",
        ).content,
      ),
      source = snapshot.captured_sources.at(-1).source_handle;
    const request = {
      request_id: "preview-source",
      reason: "M-only preview",
      source_handles: [source],
      guards: [],
      ops: [
        {
          op: "create_record",
          client_ref: "a",
          kind: "activity",
          title: "Synthetic native-dialog target",
          visibility: "workspace",
          data: { purpose: "Observe ingress", status: "active" },
        },
      ],
    };
    const p = await run("zara_preview", {
      request,
      consequence: "Create the named synthetic Activity",
      alternatives: "Leave memory unchanged",
    });
    const answer = await run("zara_confirm", { preview_ref: p.request_id });
    if (expected === "baseline")
      assert.equal(
        answer.answer.authority,
        controller
          ? "registered-synthetic-controller-not-owner"
          : "trusted-desktop-dialog",
      );
    else if (mode !== "tui" && !controller) {
      assert.equal(answer.code, "APPROVAL_REQUIRED");
      assert.equal(dialogCalls, 0);
    } else {
      assert.equal(answer.status, "approved-transient");
      assert.equal(
        answer.answer.authority,
        controller
          ? "registered-synthetic-controller-not-owner"
          : "trusted-desktop-dialog",
      );
    }
    results.push({
      mode,
      controller,
      hasUI: r.hasUI(),
      answer,
      dialogCalls,
      mechanical_mode_injection_not_human: true,
    });
  } finally {
    await r.emit({ type: "session_shutdown", reason: "exit" });
    session.dispose();
  }
}
writeFileSync(
  join(out, "verification.json"),
  JSON.stringify({ expected, provider_requests: 0, results }, null, 2),
);
console.log(JSON.stringify({ expected, cases: results.length }));

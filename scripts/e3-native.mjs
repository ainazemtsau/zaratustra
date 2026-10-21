// Deterministic SDK/native-tool checks only. No session.prompt/provider dispatch.
import assert from "node:assert/strict";
import { createRequire } from "node:module";
import { join, resolve } from "node:path";
import { pathToFileURL } from "node:url";
import { mkdirSync, existsSync, readFileSync, writeFileSync } from "node:fs";
import { DatabaseSync } from "node:sqlite";
const [pkgArg, outArg] = process.argv.slice(2),
  pkg = resolve(pkgArg),
  out = resolve(outArg);
assert.equal(existsSync(out), false);
mkdirSync(out, { recursive: true });
const sdk = await import(pathToFileURL(process.env.ZARA_PI_SDK).href);
const { createJiti } = createRequire(pathToFileURL(process.env.ZARA_PI_SDK))(
    "jiti",
  ),
  jiti = createJiti(import.meta.url);
const { activeLocation, removeOwned } = await jiti.import(
  join(pkg, "src/storage/index.ts"),
);
const calls = [],
  dialogs = [],
  checks = [];
let serial = 0,
  dispatches = 0;
const save = () => {
  for (const [name, value] of Object.entries({
    calls,
    dialogs,
    verification: {
      checks,
      provider_dispatches: dispatches,
      mechanical_only: true,
    },
  }))
    writeFileSync(join(out, name + ".json"), JSON.stringify(value, null, 2));
};
process.on("exit", save);
async function start(profile) {
  const base = join(out, profile),
    agentDir = join(base, "agent"),
    home = join(base, "home"),
    cwd = join(base, "cwd"),
    output = join(base, "output"),
    backups = join(base, "backups");
  for (const p of [agentDir, cwd, output, backups])
    mkdirSync(p, { recursive: true });
  Object.assign(process.env, {
    PI_CODING_AGENT_DIR: agentDir,
    ZARATUSTRA_HOME: home,
    ZARATUSTRA_OUTPUT_ROOT: output,
    ZARATUSTRA_BACKUP_ROOT: backups,
    ZARATUSTRA_SCOPES: JSON.stringify(
      profile === "protected" ? ["restricted:read", "restricted:write"] : [],
    ),
    ZARATUSTRA_TEST_CONTROLLER: "predeclared-E3-native-fixtures",
  });
  const runtime = await sdk.ModelRuntime.create({
      authPath: process.env.ZARA_AUTH_PATH,
      modelsPath: null,
      modelsStorePath: join(agentDir, "models.json"),
      allowModelNetwork: false,
    }),
    model = runtime.getModel("openai-codex", "gpt-6.1-sol");
  assert.ok(model);
  const settingsManager = sdk.SettingsManager.create(cwd, agentDir),
    loader = new sdk.DefaultResourceLoader({
      cwd,
      agentDir,
      settingsManager,
      noExtensions: true,
      additionalExtensionPaths: [join(pkg, "src/extension/index.ts")],
      extensionFactories: [
        (pi) => {
          pi.on("before_provider_request", () => {
            dispatches++;
            throw Error("Unexpected mechanical provider dispatch");
          });
        },
      ],
    });
  await loader.reload();
  assert.deepEqual(loader.getExtensions().errors, []);
  const { session } = await sdk.createAgentSession({
    cwd,
    agentDir,
    modelRuntime: runtime,
    model,
    thinkingLevel: "medium",
    settingsManager,
    resourceLoader: loader,
    sessionManager: sdk.SessionManager.inMemory(),
  });
  await session.bindExtensions({});
  const runner = session.extensionRunner;
  runner.setUIContext(
    {
      ...runner.getUIContext(),
      confirm: async (title, message) => {
        dialogs.push({
          profile,
          title,
          message,
          answer: true,
          principal: "predeclared isolated synthetic controller, not owner",
        });
        return true;
      },
      notify: (message, type) =>
        calls.push({ profile, notification: message, type }),
    },
    "rpc",
  );
  const custom = async (name, args) => {
    const id = "e3-sdk-" + ++serial,
      result = await runner
        .getToolDefinition(name)
        .execute(id, args, undefined, undefined, runner.createToolContext(id));
    calls.push({ profile, name, args, result });
    return result.details;
  };
  const snap = async () =>
    JSON.parse(
      (await runner.emitContext([])).find(
        (m) => m.customType === "zaratustra.snapshot.v1",
      ).content,
    );
  const source = async () => {
    await runner.emitInput(
      "Synthetic fixture instruction, not owner testimony.",
      undefined,
      "rpc",
    );
    return (await snap()).captured_sources.at(-1)?.source_handle;
  };
  const native = async (args) => {
    const id = "native-e3-" + ++serial,
      block = await runner.emitToolCall({
        type: "tool_call",
        toolName: "write",
        toolCallId: id,
        input: args,
      });
    calls.push({ profile, name: "write", args, id, block });
    assert.ok(!block?.block);
    const result = await sdk.createWriteTool(cwd).execute(id, args);
    calls.push({
      profile,
      native_result: result,
      dropped_before_product_result: true,
    });
  };
  return {
    home,
    cwd,
    output,
    backups,
    custom,
    snap,
    source,
    native,
    close: async () => {
      await runner.emit({ type: "session_shutdown", reason: "exit" });
      session.dispose();
    },
  };
}
const low = await start("low");
for (const [name, args] of [
  ["zara_backup", {}],
  ["zara_backups", {}],
  [
    "zara_restore_preview",
    { backup: "guessed", consequence: "Restore", alternatives: "Keep" },
  ],
])
  assert.equal((await low.custom(name, args)).code, "PERMISSION_DENIED");
await low.close();
checks.push(
  "Fixed low-scope negative before source/bundle inspection; no escalation",
);
let f = await start("protected");
const initial = await f.custom("zara_commit", {
  request_id: "e3-sdk-work",
  reason: "Create synthetic report continuation",
  source_handles: [await f.source()],
  guards: [],
  ops: [
    {
      op: "create_record",
      client_ref: "w",
      kind: "work",
      title: "Observatory report",
      visibility: "workspace",
      data: {
        activity_id: null,
        parent_work_id: null,
        objective: "Write a report file",
        acceptance: [
          {
            criterion_id: "file",
            description: "Current report bytes",
            verification: "Inspect controlled output",
            required: true,
          },
        ],
        status: "active",
        current_state: "Report planned",
        next_action: "Write the report",
        steps: [],
        waits: [],
        context_refs: [],
        completion: null,
      },
    },
  ],
});
assert.equal(initial.committed, true);
const work = initial.created.w;
const backup = await f.custom("zara_backup", {});
assert.equal(backup.complete, true);
const snapshot = new DatabaseSync(join(backup.backup, "database.sqlite"), {
  readOnly: true,
});
assert.equal(
  snapshot
    .prepare(
      "SELECT count(*) AS n FROM intents WHERE json_extract(json,'$.kind')='managed_file'",
    )
    .get().n,
  0,
);
snapshot.close();
const path = join(f.output, "report.txt"),
  text = "A real native report was written after backup A.\n",
  proposal = await f.custom("zara_file_preview", {
    request_id: "e3-sdk-effect-B",
    tool: "write",
    arguments: { path, content: text },
    work_ref: { id: work, revision: 1 },
    consequence: "Write synthetic report B",
    alternatives: "Keep report absent",
  });
assert.ok(proposal.request_id);
await f.custom("zara_confirm", { preview_ref: proposal.request_id });
await f.native({ path, content: text });
assert.equal(readFileSync(path, "utf8"), text);
await f.close();
removeOwned(f.home, join(activeLocation(f.home), "zara.sqlite"));
f = await start("protected");
assert.equal((await f.snap()).available, false);
assert.equal(existsSync(join(f.home, "zara.sqlite")), false);
const restore = await f.custom("zara_restore_preview", {
  backup: backup.backup,
  consequence:
    "Restore snapshot A; later DB history lost, real report remains and requires reconciliation",
  alternatives: "Keep unavailable memory",
});
assert.ok(restore.preview);
await f.custom("zara_confirm", { preview_ref: restore.preview.request_id });
const switched = await f.custom("zara_restore", {
  preview_ref: restore.preview.request_id,
});
assert.equal(switched.switched, true);
assert.notEqual(activeLocation(f.home), f.home);
assert.equal((await f.snap()).recovery_required[0].work_id, work);
const refused = await f.custom("zara_file_preview", {
  request_id: "must-not-repeat",
  tool: "write",
  arguments: { path, content: text },
  work_ref: { id: work, revision: 1 },
  consequence: "Repeat restored next action",
  alternatives: "Inspect",
});
assert.equal(refused.code, "RESTORE_RECONCILIATION_REQUIRED");
const observation = await f.custom("zara_recovery_inspect", {
  work_id: work,
  path,
});
assert.equal(observation.current_text, text);
const r = await f.custom("zara_reconcile_preview", {
  work_id: work,
  expected_hash: observation.data.inspection.hash,
  disposition: "observed_satisfied",
  explanation: "Current bytes match the required report; author is unknown",
  consequence:
    "Accept only this named observed report state without repeating it",
  alternatives: "Keep unknown barrier",
});
assert.ok(r.request_id);
await f.custom("zara_confirm", { preview_ref: r.request_id });
assert.equal(
  (await f.custom("zara_reconcile", { preview_ref: r.request_id })).data
    .committed,
  true,
);
assert.equal(readFileSync(path, "utf8"), text);
checks.push(
  "A-before-intent/B-real-native-write/lost-current-DB/quarantine switch/no-receipt barrier/actual readback/named decision; one native write only",
);
await f.close();
writeFileSync(
  join(activeLocation(f.home), "zara.sqlite"),
  "Synthetic corrupt current database",
);
f = await start("protected");
assert.equal((await f.snap()).available, false);
const q = await f.custom("zara_restore_preview", {
  backup: backup.backup,
  consequence: "Recover corrupt active generation; later DB changes lost",
  alternatives: "Keep corrupt generation",
});
assert.ok(q.preview);
await f.custom("zara_confirm", { preview_ref: q.preview.request_id });
assert.equal(
  (await f.custom("zara_restore", { preview_ref: q.preview.request_id }))
    .switched,
  true,
);
assert.equal((await f.snap()).recovery_required[0].work_id, work);
await f.close();
checks.push(
  "Agent-accessible native exact restore with genuinely corrupt current DB; prior generation retained",
);
assert.equal(dispatches, 0);
assert.equal(calls.filter((c) => c.name === "write").length, 1);
save();
console.log(
  JSON.stringify({
    checks: checks.length,
    dialogs: dialogs.length,
    provider_dispatches: dispatches,
  }),
);

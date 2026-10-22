// Uncapped Sleep qualification using native Pi SDK, resources and event settlement.
// Derived from the existing live runner. No scripted replies. Isolated synthetic paths only.
import {
  appendFileSync,
  existsSync,
  mkdirSync,
  readFileSync,
  writeFileSync,
} from "node:fs";
import { join, resolve } from "node:path";
import { pathToFileURL } from "node:url";
import { createRequire } from "node:module";
import { fileURLToPath } from "node:url";
import { DatabaseSync } from "node:sqlite";

const configPath = process.argv[2];
if (!configPath)
  throw new Error("Usage: node sleep-live.mjs <isolated-scenario.json>");
const config = JSON.parse(readFileSync(configPath, "utf8"));
const { agentDir, cwd, home, output, prompt, usagePath } = config;
for (const path of [agentDir, cwd, output])
  mkdirSync(path, { recursive: true });
process.env.PI_CODING_AGENT_DIR = agentDir;
process.env.ZARATUSTRA_HOME = home;
if (config.outputRoot) process.env.ZARATUSTRA_OUTPUT_ROOT = config.outputRoot;
else delete process.env.ZARATUSTRA_OUTPUT_ROOT;
process.env.ZARATUSTRA_IMPORT_ROOTS = JSON.stringify(config.importRoots ?? []);
if (config.scopes !== undefined) {
  if (
    !Array.isArray(config.scopes) ||
    config.scopes.some(
      (s) => !["restricted:read", "restricted:write"].includes(s),
    )
  )
    throw new Error("Unknown predeclared synthetic scope profile");
  process.env.ZARATUSTRA_SCOPES = JSON.stringify(config.scopes);
}
if (config.backupRoot) process.env.ZARATUSTRA_BACKUP_ROOT = config.backupRoot;
else delete process.env.ZARATUSTRA_BACKUP_ROOT;
process.env.ZARATUSTRA_TEST_CONTROLLER = "isolated-synthetic-sdk-controller";
const sdk = await import(pathToFileURL(process.env.ZARA_PI_SDK).href);
const { createJiti } = createRequire(pathToFileURL(process.env.ZARA_PI_SDK))(
  "jiti",
);
const jiti = createJiti(import.meta.url);
const { activeLocation } = await jiti.import(
  fileURLToPath(new URL("../src/storage/index.ts", import.meta.url)),
);
const activeDb = () => join(activeLocation(home), "zara.sqlite");
const {
  ModelRuntime,
  DefaultResourceLoader,
  SettingsManager,
  SessionManager,
  createAgentSession,
} = sdk;
const ledger = () => JSON.parse(readFileSync(usagePath, "utf8"));
const saveLedger = (b) => writeFileSync(usagePath, JSON.stringify(b, null, 2));
const b = ledger();
if (b.uncapped !== true)
  throw new Error("A new explicitly uncapped ledger is required");
b.attempts++;
saveLedger(b);
const piVersion = JSON.parse(
  readFileSync(
    new URL("../package.json", pathToFileURL(process.env.ZARA_PI_SDK)),
    "utf8",
  ),
).version;
const expectedPi = config.qualificationHost ?? "1.3.0";
if (
  !["1.3.0", "1.4.0"].includes(expectedPi) ||
  piVersion !== expectedPi ||
  sdk.VERSION !== piVersion
)
  throw new Error(
    `Required attributed qualification host is Pi ${expectedPi}; actual package ${piVersion}, SDK ${sdk.VERSION}. No provider call was dispatched.`,
  );
const log = (name, value) =>
  appendFileSync(join(output, name + ".jsonl"), JSON.stringify(value) + "\n");
const runtime = await ModelRuntime.create({
  authPath: process.env.ZARA_AUTH_PATH,
  modelsPath: null,
  modelsStorePath: join(agentDir, "test-model-store.json"),
  allowModelNetwork: false,
});
const model = runtime.getModel(b.provider, b.model);
if (!model)
  throw new Error(
    "The already-selected Pi model is absent; no fallback authorized",
  );
const auth = await runtime.checkAuth(b.provider);
if (!auth)
  throw new Error(
    "Native authentication is unavailable; no substitute authorized",
  );
log("identity", {
  pi: piVersion,
  sdk_version: sdk.VERSION,
  qualification_profile:
    expectedPi === "1.3.0"
      ? "pinned baseline"
      : "separate current-host compatibility",
  pid: process.pid,
  os_cwd: process.cwd(),
  sdk_cwd: cwd,
  provider: model.provider,
  model: model.id,
  node: process.version,
  platform: process.platform,
  arch: process.arch,
  auth: auth ? { available: true } : { available: false },
  source:
    "existing conscious Pi selection, supported ModelRuntime authPath (native authentication only)",
  thinking: "medium",
  prompt,
});
let dropped = false;
let materialChanged = false;
const dialogReplies = [...(config.dialogReplies ?? [])];
const observer = (pi) => {
  pi.on("context_with_system", (event) => {
    const snapshots = event.messages.filter(
      (m) => m.role === "custom" && m.customType === "zaratustra.snapshot.v1",
    );
    log("requests", {
      snapshots,
      system_count: event.messages.filter((m) => m.role === "system").length,
      system_sections: event.messages
        .filter((m) => m.role === "system")
        .map((m) => Object.keys(m.sections ?? {})),
      bootstrap_occurrences:
        JSON.stringify(event.messages.filter((m) => m.role === "system")).split(
          "You use Zaratustra's durable workspace",
        ).length - 1,
      tool_messages: event.messages.filter((m) => m.role === "toolResult")
        .length,
      user_messages: event.messages
        .filter((m) => m.role === "user")
        .map((m) => m.content),
    });
  });
  pi.on("before_provider_request", (_event) => {
    log("provider-requests", _event);
    const accounting = ledger();
    ++accounting.requests;
    saveLedger(accounting);
  });
  pi.on("tool_call", (event) => {
    if (
      config.changeFileBeforeDispatch &&
      !materialChanged &&
      ["write", "edit"].includes(event.toolName) &&
      resolve(cwd, event.input.path).toLowerCase() ===
        resolve(config.changeFileBeforeDispatch.path).toLowerCase()
    ) {
      const db = new DatabaseSync(activeDb(), {
        readOnly: true,
      });
      const pending = db
        .prepare(
          "SELECT json FROM intents WHERE json_extract(json,'$.kind')='preview' AND json_extract(json,'$.status')='approved-transient' AND json_extract(json,'$.payload.action')='managed_file'",
        )
        .all()
        .some(
          (r) =>
            resolve(JSON.parse(r.json).payload.exact.target).toLowerCase() ===
            resolve(config.changeFileBeforeDispatch.path).toLowerCase(),
        );
      db.close();
      if (!pending) return;
      const before = readFileSync(event.input.path, "utf8");
      writeFileSync(
        event.input.path,
        config.changeFileBeforeDispatch.content,
        "utf8",
      );
      materialChanged = true;
      log("faults", {
        point: "material-bytes-changed-after-confirmation-before-dispatch",
        path: event.input.path,
        before,
        after: config.changeFileBeforeDispatch.content,
      });
    }
  });
  pi.on("tool_result", (event, ctx) => {
    if (
      config.dropNativeResult &&
      !dropped &&
      ["write", "edit"].includes(event.toolName) &&
      !event.isError
    ) {
      const db = new DatabaseSync(activeDb(), {
        readOnly: true,
      });
      const attempt = db
        .prepare(
          "SELECT json FROM intents WHERE json_extract(json,'$.kind')='managed_file' AND json_extract(json,'$.tool_call_id')=?",
        )
        .get(event.toolCallId);
      db.close();
      if (attempt) {
        dropped = true;
        log("faults", {
          point: "real-native-write-before-adapter-tool-result-receipt",
          active_database: activeDb(),
          call_id: event.toolCallId,
          attempt: JSON.parse(attempt.json),
          native_result: event.content,
        });
        process.exit(86);
      }
    }
    if (
      (config.dropCommitResponse || config.dropSleepCheckpoint) &&
      !dropped &&
      event.toolName === "zara_commit" &&
      (!config.dropSleepCheckpoint ||
        JSON.stringify(event.input).includes("sleep_checkpoint")) &&
      !event.isError
    ) {
      dropped = true;
      log("faults", {
        point: "after-real-commit-before-result-delivery",
        original_result: event.content,
      });
      if (config.dropSleepCheckpoint) process.exit(86);
      ctx.abort();
      return {
        content: [
          {
            type: "text",
            text: "Synthetic transport interruption: commit response was lost. Outcome is unknown to this conversation.",
          },
        ],
        isError: true,
      };
    }
  });
};
const settingsManager = SettingsManager.create(cwd, agentDir);
const loader = new DefaultResourceLoader({
  cwd,
  agentDir,
  settingsManager,
  extensionFactories: [observer],
  // Fault observer precedes product result capture; normal tools remain native Pi tools.
  extensionsOverride: (base) =>
    config.dropNativeResult || config.changeFileBeforeDispatch
      ? {
          ...base,
          extensions: [
            ...base.extensions.filter((e) => !e.tools.has("zara_map")),
            ...base.extensions.filter((e) => e.tools.has("zara_map")),
          ],
        }
      : base,
});
await loader.reload();
const ext = loader.getExtensions();
log("resources", {
  extension_paths: ext.extensions.map((e) => e.path),
  errors: ext.errors,
  skills: loader
    .getSkills()
    .skills.map((s) => ({ name: s.name, filePath: s.filePath })),
});
if (ext.errors.length)
  throw new Error("Extension load failed; see resources log");
const requiredSkills = [
  "zaratustra-work",
  "zaratustra-memory",
  "zaratustra-sleep",
];
if (
  ext.extensions.filter(
    (e) => e.tools.has("zara_commit") && e.tools.has("zara_sleep_batch"),
  ).length !== 1 ||
  requiredSkills.some(
    (name) => !loader.getSkills().skills.some((s) => s.name === name),
  )
)
  throw new Error(
    "Required one product extension and three native skills are unavailable; no provider call was dispatched.",
  );
const { session } = await createAgentSession({
  cwd,
  agentDir,
  modelRuntime: runtime,
  model,
  thinkingLevel: "medium",
  settingsManager,
  sessionManager: SessionManager.inMemory(),
  resourceLoader: loader,
});
await session.bindExtensions({});
if (config.dialogReplies) {
  const runner = session.extensionRunner;
  runner.setUIContext(
    {
      ...runner.getUIContext(),
      confirm: async (title, message) => {
        if (!dialogReplies.length) {
          log("dialogs", {
            title,
            message,
            answer: false,
            unplanned: true,
            principal: "isolated-synthetic-sdk-controller",
          });
          return false;
        }
        const reply = dialogReplies.shift();
        const matches =
          typeof reply !== "object" ||
          (reply.expected ?? []).every((fragment) =>
            message.includes(fragment),
          );
        const answer =
          matches && (typeof reply === "boolean" ? reply : reply.answer);
        log("dialogs", {
          title,
          message,
          answer,
          note: typeof reply === "object" ? reply.note : null,
          matches_expected_consequence: matches,
          principal: "isolated-synthetic-sdk-controller",
          stage: "native-sdk-confirm-callback-not-owner",
        });
        return answer;
      },
      notify: (message, type) => log("notifications", { message, type }),
    },
    "rpc",
  );
}
log("startup", {
  messages_before_prompt: session.messages,
  active_tools: session.getActiveToolNames(),
  selected: { provider: session.model?.provider, model: session.model?.id },
});
let settled = false;
session.subscribe((event) => {
  if (event.type === "agent_settled") settled = true;
  if (
    [
      "tool_execution_start",
      "tool_execution_end",
      "message_end",
      "agent_settled",
      "auto_retry_start",
      "auto_retry_end",
    ].includes(event.type)
  )
    log("events", event);
  if (event.type === "message_end" && event.message.role === "assistant") {
    const usage = event.message.usage;
    if (usage) {
      const accounting = ledger();
      accounting.reported_usage_messages =
        (accounting.reported_usage_messages ?? 0) + 1;
      if (event.message.stopReason === "error")
        accounting.reported_error_messages =
          (accounting.reported_error_messages ?? 0) + 1;
      accounting.input +=
        (usage.input ?? 0) + (usage.cacheRead ?? 0) + (usage.cacheWrite ?? 0);
      accounting.output += usage.output ?? 0;
      accounting.cache_read += usage.cacheRead ?? 0;
      if (typeof usage.cost?.total === "number")
        accounting.estimated_usd += usage.cost.total;
      else
        accounting.unpriced_usage_messages =
          (accounting.unpriced_usage_messages ?? 0) + 1;
      if (event.message.stopReason === "error")
        accounting.errors.push({
          attempt: b.attempts,
          error:
            event.message.errorMessage ??
            "Provider/model error; see retained events",
        });
      saveLedger(accounting);
    }
  }
});
try {
  await session.prompt(prompt, { source: "rpc" });
  await session.waitForIdle();
  const response = session.getLastAssistantText();
  const ownSnapshots = session.messages.filter(
    (m) => m.role === "custom" && m.customType === "zaratustra.snapshot.v1",
  );
  const dbPath = activeDb();
  let database = null;
  if (existsSync(dbPath)) {
    const db = new DatabaseSync(dbPath, { readOnly: true });
    database = Object.fromEntries(
      [
        "records",
        "revisions",
        "changes",
        "intents",
        "receipts",
        "claims",
        "handoffs",
        "relations",
        "relation_history",
        "memory_meta",
        "retrieval_trace",
        "experience_rows",
        "experience_versions",
        "lifecycle_pins",
        "recovery_barriers",
        "lifecycle_events",
        "sleep_reviews",
        "sleep_items",
        "sleep_coverage",
      ].map((table) => [table, db.prepare(`SELECT * FROM ${table}`).all()]),
    );
    db.close();
  }
  const summary = {
    response,
    settled,
    dropped,
    materialChanged,
    remaining_dialog_replies: dialogReplies.length,
    permanent_snapshot_count: ownSnapshots.length,
    active_database: activeDb(),
    database,
    accounting: ledger(),
  };
  writeFileSync(join(output, "summary.json"), JSON.stringify(summary, null, 2));
  console.log(
    JSON.stringify(
      {
        response,
        settled,
        dropped,
        permanent_snapshot_count: ownSnapshots.length,
        accounting: ledger(),
      },
      null,
      2,
    ),
  );
} finally {
  await session.extensionRunner.emit({
    type: "session_shutdown",
    reason: "exit",
  });
  session.dispose();
}

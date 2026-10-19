// Developer-only real-model runner. No scripted replies or prepared domain mutations.
import {
  appendFileSync,
  existsSync,
  mkdirSync,
  readFileSync,
  writeFileSync,
} from "node:fs";
import { join } from "node:path";
import { pathToFileURL } from "node:url";
import { DatabaseSync } from "node:sqlite";

const configPath = process.argv[2];
if (!configPath)
  throw new Error("Usage: node live.mjs <isolated-scenario.json>");
const config = JSON.parse(readFileSync(configPath, "utf8"));
const { agentDir, cwd, home, output, prompt, budgetPath } = config;
for (const path of [agentDir, cwd, output])
  mkdirSync(path, { recursive: true });
process.env.PI_CODING_AGENT_DIR = agentDir;
process.env.ZARATUSTRA_HOME = home;
process.env.ZARATUSTRA_IMPORT_ROOTS = JSON.stringify(config.importRoots ?? []);
process.env.ZARATUSTRA_TEST_CONTROLLER = "isolated-synthetic-sdk-controller";
const sdk = await import(pathToFileURL(process.env.ZARA_PI_SDK).href);
const {
  ModelRuntime,
  DefaultResourceLoader,
  SettingsManager,
  SessionManager,
  createAgentSession,
} = sdk;
const ledger = () => JSON.parse(readFileSync(budgetPath, "utf8"));
const saveLedger = (b) => writeFileSync(budgetPath, JSON.stringify(b, null, 2));
const b = ledger();
if (
  b.prompts >= b.limits.prompts ||
  b.requests >= b.limits.requests ||
  b.estimated_usd >= b.limits.estimated_usd
)
  throw new Error(
    "Finite live budget exhausted before starting another attempt",
  );
b.prompts++;
saveLedger(b);
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
log("identity", {
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
          "You use Zaratustra's first-block durable workspace",
        ).length - 1,
      tool_messages: event.messages.filter((m) => m.role === "toolResult")
        .length,
      user_messages: event.messages
        .filter((m) => m.role === "user")
        .map((m) => m.content),
    });
  });
  pi.on("before_provider_request", (_event, ctx) => {
    const budget = ledger();
    if (
      budget.requests >= budget.limits.requests ||
      budget.input >= budget.limits.input ||
      budget.output >= budget.limits.output ||
      budget.estimated_usd >= budget.limits.estimated_usd
    ) {
      ctx.abort();
      throw new Error("Finite live request/token/cost budget exhausted");
    }
    ++budget.requests;
    saveLedger(budget);
  });
  pi.on("tool_result", (event, ctx) => {
    if (
      config.dropCommitResponse &&
      !dropped &&
      event.toolName === "zara_commit" &&
      !event.isError
    ) {
      dropped = true;
      log("faults", {
        point: "after-real-commit-before-result-delivery",
        original_result: event.content,
      });
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
      const budget = ledger();
      budget.input +=
        (usage.input ?? 0) + (usage.cacheRead ?? 0) + (usage.cacheWrite ?? 0);
      budget.output += usage.output ?? 0;
      budget.cache_read += usage.cacheRead ?? 0;
      budget.estimated_usd += usage.cost?.total ?? 0;
      saveLedger(budget);
    }
  }
});
const timer = setTimeout(() => {
  log("faults", { point: "finite-180s-scenario-timeout" });
  void session.abort();
}, 180000);
try {
  await session.prompt(prompt, { source: "rpc" });
  await session.waitForIdle();
  const response = session.getLastAssistantText();
  const ownSnapshots = session.messages.filter(
    (m) => m.role === "custom" && m.customType === "zaratustra.snapshot.v1",
  );
  const dbPath = join(home, "zara.sqlite");
  let database = null;
  if (existsSync(dbPath)) {
    const db = new DatabaseSync(dbPath, { readOnly: true });
    database = Object.fromEntries(
      ["records", "revisions", "changes", "intents", "receipts"].map(
        (table) => [table, db.prepare(`SELECT * FROM ${table}`).all()],
      ),
    );
    db.close();
  }
  const summary = {
    response,
    settled,
    dropped,
    permanent_snapshot_count: ownSnapshots.length,
    database,
    budget: ledger(),
  };
  writeFileSync(join(output, "summary.json"), JSON.stringify(summary, null, 2));
  console.log(
    JSON.stringify(
      {
        response,
        settled,
        dropped,
        permanent_snapshot_count: ownSnapshots.length,
        budget: ledger(),
      },
      null,
      2,
    ),
  );
} finally {
  clearTimeout(timer);
  await session.extensionRunner.emit({
    type: "session_shutdown",
    reason: "exit",
  });
  session.dispose();
}

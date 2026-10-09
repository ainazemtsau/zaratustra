/** Execute installed Pi renderers and hooks: no model, sockets or user workspace. */
import assert from "node:assert/strict";
import { mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { resolve, join } from "node:path";
import { pathToFileURL } from "node:url";

const [runtimeArg, extensionArg, directoryArg] = process.argv.slice(2);
assert(runtimeArg && extensionArg && directoryArg, "runtime, extension and NEW fictional directory required");
const runtime = resolve(runtimeArg);
const extensionPath = resolve(extensionArg);
const directory = resolve(directoryArg);
mkdirSync(directory);
const agentDir = join(directory, "pi-agent");
mkdirSync(agentDir);
process.argv[1] = join(runtime, "node_modules/@earendil-works/pi-coding-agent/dist/bundle/cli.js");
Object.assign(process.env, {
  PI_CODING_AGENT_DIR: agentDir, PI_OFFLINE: "1", PI_SKIP_VERSION_CHECK: "1", PI_TELEMETRY: "0",
  ZARA_CORE_ENDPOINT: "http://127.0.0.1:1", ZARA_CORE_TOKEN: "fictional-ui-only",
  ZARA_PROVIDER_ORIGIN: "http://127.0.0.1:1", ZARA_PROVIDER_BASE_URL: "http://127.0.0.1:1/v1",
  ZARA_RESERVE_UNITS: "1000", ZARA_PROVIDER_PROFILE: "local-completions",
  ZARA_LOCAL_PROVIDER_ID: "fictional-local", ZARA_LOCAL_MODEL_ID: "fictional-model",
  ZARA_LOCAL_CONTEXT_WINDOW: "16384", ZARA_LOCAL_MAX_TOKENS: "512",
});
const packageDir = join(runtime, "node_modules/@earendil-works/pi-coding-agent");
const packageMetadata = JSON.parse(readFileSync(join(packageDir, "package.json"), "utf8"));
const { discoverAndLoadExtensions } = await import(pathToFileURL(join(packageDir, "dist/index.js")).href);
const { convertToLlm } = await import(pathToFileURL(join(packageDir, "dist/core/messages.js")).href);
const loaded = await discoverAndLoadExtensions([extensionPath], directory, agentDir);
assert.deepEqual(loaded.errors, []);
const extension = loaded.extensions.find(item => item.resolvedPath === extensionPath);
assert(extension);
const tool = extension.tools.get("zara_activity").definition;
const question = "Which fictional output should the workshop prepare first?";
let item = {
  setup_id: "fictional-setup", revision: 2,
  state: { phase: "needs_input", question, stages: [], reviews_started: 0, pass_boundary: 0,
    activated_works: [], result: null },
};
let statusFails = false;
globalThis.fetch = async (url, init) => {
  assert(String(url).startsWith("http://127.0.0.1:1/"));
  if (String(url).includes("/v1/connect")) return Response.json({
    schema_version: 14, space_id: "fictional-space", execution_epoch: 1, records: [],
  });
  if (String(url).includes("/v1/context-prepare")) return Response.json({
    manifest_id: "fictional-manifest", manifest_revision: 1,
  });
  if (String(url).includes("/v1/workspace")) return Response.json({
    personal_root: directory, selected_root: directory, selected_project: "personal",
    projects: [], git: { connected: false },
  });
  assert(String(url).includes("/v1/activity-setup"));
  const body = JSON.parse(init.body);
  if (body.action === "list") return Response.json({ items: [item] });
  if (body.action === "status" && statusFails) throw new Error("fictional read failure");
  assert(["status", "question", "window_close"].includes(body.action));
  return Response.json(item);
};
let tick;
globalThis.setInterval = callback => { tick = callback; return 1; };
globalThis.clearInterval = () => {};
const notifications = [];
const widgets = new Map();
const ctx = {
  model: { id: "fictional-model", provider: "fictional-local" },
  modelRegistry: { getAll() { return []; } },
  ui: { setStatus() {}, setWidget(key, value) { widgets.set(key, value); },
    notify(message, type) { notifications.push({ message, type }); } },
  sessionManager: { getBranch() { return []; } },
};
const emit = async (name, event) => {
  let result;
  for (const handler of extension.handlers.get(name) ?? []) result = await handler(event, ctx) ?? result;
  return result;
};
await emit("session_start", { reason: "resume" });
assert.deepEqual(widgets.get("zara-setup"), [question]);
assert(!notifications.some(item => item.message === question || item.type === "warning"));

const theme = { fg(_color, text) { return text; }, bold(text) { return text; } };
const result = await tool.execute("fixture", { mode: "question", setup_id: item.setup_id, question }, undefined, undefined, ctx);
assert.equal(widgets.get("zara-setup"), undefined);
const collapsed = tool.renderResult(result, { expanded: false }, theme, {}).render(300).join("\n");
const expanded = tool.renderResult(result, { expanded: true }, theme, {}).render(300).join("\n");
assert(!collapsed.includes(question) && !collapsed.includes("setup_id"));
assert(expanded.includes("setup_id") && expanded.includes(item.setup_id));
const failure = tool.renderResult({ content: [{ type: "text", text: "fictional refusal" }] },
  { expanded: false }, theme, { isError: true }).render(300).join("\n");
assert(failure.includes("fictional refusal"));

const legacy = { role: "custom", customType: "zara-setup", content: question, timestamp: 1 };
// Identical text from the actual owner remains input; filter by provenance, not wording.
const owner = { role: "user", content: question, timestamp: 2 };
const other = { role: "custom", customType: "another-extension", content: "keep me", timestamp: 3 };
assert.equal(convertToLlm([legacy])[0].role, "user");
const context = await emit("context", { messages: [owner, legacy, other] });
assert.deepEqual(context.messages, [owner, other]);
assert.deepEqual(legacy.content, question); // history is retained, only model delivery changes
const preparation = { messagesToSummarize: [legacy, owner], turnPrefixMessages: [owner, legacy] };
await emit("session_before_compact", { preparation, branchEntries: [] });
assert.deepEqual(preparation.messagesToSummarize, [owner]);
assert.deepEqual(preparation.turnPrefixMessages, [owner]);

await extension.commands.get("zara-setup").handler("", ctx);
assert.deepEqual(widgets.get("zara-setup"), [question]);
item = { ...item, revision: 3, state: { ...item.state, phase: "ready", result: "Fictional ready result" } };
// The watcher runs asynchronously; observe its public UI effects without any provider request.
tick();
await new Promise(resolve => setImmediate(resolve));
assert(widgets.get("zara-setup").join("\n").includes("Fictional ready result"));
assert.equal(notifications.filter(item => item.message === "Activity готова к работе.").length, 1);
tick();
await new Promise(resolve => setImmediate(resolve));
assert.equal(notifications.filter(item => item.message === "Activity готова к работе.").length, 1);
statusFails = true;
tick();
await new Promise(resolve => setImmediate(resolve));
tick();
await new Promise(resolve => setImmediate(resolve));
assert.equal(notifications.filter(item => item.message.includes("fictional read failure")).length, 1);
const report = { pi: packageMetadata.version, rendered_tool: true, no_phantom_user_notice: true,
  legacy_history_filtered: true, compact_both_parts_filtered: true,
  resumed_question_visible: true, duplicate_notifications: false, actual_provider_calls: 0 };
writeFileSync(join(directory, "report.json"), JSON.stringify(report, null, 2) + "\n");
console.log(JSON.stringify(report, null, 2));

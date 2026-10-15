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
// The UI-only loader now obtains its tool contract before AgentSession starts.
globalThis.fetch = async () => Response.json({runtime_selector_schema: {
  type: "object", properties: {}, additionalProperties: false,
}});
const loaded = await discoverAndLoadExtensions([extensionPath], directory, agentDir);
assert.deepEqual(loaded.errors, []);
// The UI-only harness has no live AgentSession; supply its chosen thinking state.
loaded.runtime.getThinkingLevel = () => "off";
loaded.runtime.getActiveTools = () => [];
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
let resumeCalls = 0;
let refuseResume = false;
globalThis.fetch = async (url, init) => {
  assert(String(url).startsWith("http://127.0.0.1:1/"));
  if (String(url).includes("/v1/connect")) return Response.json({
    schema_version: 14, space_id: "fictional-space", execution_epoch: 1, records: [],
  });
  if (String(url).includes("/v1/context-prepare")) return Response.json({
    manifest_id: "fictional-manifest", manifest_revision: 1,
  });
  if (String(url).includes("/v1/conversation")) return Response.json({registered: true});
  if (String(url).includes("/v1/workspace")) return Response.json({
    personal_root: directory, selected_root: directory, selected_project: "personal",
    projects: [], git: { connected: false },
  });
  assert(String(url).includes("/v1/activity-setup"));
  const body = JSON.parse(init.body);
  if (body.action === "list") return Response.json({ items: [item] });
  if (body.action === "status" && statusFails) throw new Error("fictional read failure");
  if (body.action === "resume") {
    resumeCalls += 1;
    if (refuseResume) {
      item = {...item, execution: {...item.execution, status: "unknown", can_resume: false}};
      return Response.json({error: "unknown_effect", detail: "Fictional interrupted outcome"}, {status: 409});
    }
    return Response.json(item);
  }
  assert(["status", "question", "window_close"].includes(body.action));
  return Response.json(item);
};
let tick;
globalThis.setInterval = callback => { tick = callback; return 1; };
globalThis.clearInterval = () => {};
const notifications = [];
const widgets = new Map();
const statuses = new Map();
let aborted = 0;
const confirmations = [];
const ctx = {
  model: { id: "fictional-model", provider: "fictional-local" },
  modelRegistry: { getAll() { return []; } },
  abort() { aborted += 1; },
  ui: { setStatus(key, value) { statuses.set(key, value); },
    setWidget(key, value) { widgets.set(key, value); },
    notify(message, type) { notifications.push({ message, type }); },
    async confirm(title, message) { confirmations.push({title, message}); return false; } },
  sessionManager: { getBranch() { return []; }, getSessionId() { return "fictional-native"; } },
};
const emit = async (name, event) => {
  let result;
  for (const handler of extension.handlers.get(name) ?? []) result = await handler(event, ctx) ?? result;
  return result;
};
await emit("session_start", { reason: "resume" });
assert.equal(widgets.get("zara-setup"), undefined);
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
await assert.rejects(emit("context", { messages: [owner, legacy, other] }), /Unsupported custom/);
const context = await emit("context", { messages: [owner, legacy] });
assert.deepEqual(context.messages, [owner]);
assert.deepEqual(legacy.content, question); // history is retained, only model delivery changes
const preparation = { messagesToSummarize: [legacy, owner], turnPrefixMessages: [owner, legacy] };
await emit("session_before_compact", { preparation, branchEntries: [] });
assert.deepEqual(preparation.messagesToSummarize, [owner]);
assert.deepEqual(preparation.turnPrefixMessages, [owner]);

await extension.commands.get("zara-setup").handler("", ctx);
assert.equal(widgets.get("zara-setup"), undefined);
item = { ...item, revision: 3, state: { ...item.state, phase: "ready", result: "Fictional ready result" } };
// The watcher runs asynchronously; observe its public UI effects without any provider request.
tick();
await new Promise(resolve => setImmediate(resolve));
assert.equal(widgets.get("zara-setup"), undefined);
assert(statuses.get("zara-setup").includes("готова"));
assert.equal(notifications.filter(item => item.message === "Activity готова к работе.").length, 0);
tick();
await new Promise(resolve => setImmediate(resolve));
assert.equal(notifications.filter(item => item.message === "Activity готова к работе.").length, 0);
statusFails = true;
tick();
await new Promise(resolve => setImmediate(resolve));
tick();
await new Promise(resolve => setImmediate(resolve));
assert.equal(notifications.filter(item => item.message.includes("fictional read failure")).length, 0);
assert(statuses.get("zara-setup").includes("недоступно"));
statusFails = false;
item = {...item, revision: 4, state: {...item.state, phase: "paused"},
  execution: {status: "stopping", can_attach_sources: false, can_retry: false}};
tick();
await new Promise(resolve => setImmediate(resolve));
assert(statuses.get("zara-setup").includes("исполнитель останавливается"));
assert.equal(widgets.get("zara-setup"), undefined);
// Assignment changes may not revise ActivitySetup; the derived status must refresh.
item = {...item, execution: {status: "unknown", can_attach_sources: true, can_retry: true,
  blocking_unknown_invocations: ["fictional-invocation"]}};
tick();
await new Promise(resolve => setImmediate(resolve));
assert(statuses.get("zara-setup").includes("новую подготовку"));
assert.equal(widgets.get("zara-setup"), undefined);
const declined = await tool.execute("retry-fixture", {mode: "retry", setup_id: item.setup_id},
  undefined, undefined, ctx);
assert(declined.content[0].text.includes("not authorized"));
assert(confirmations.at(-1).message.includes("неизвестный расход сохранятся"));
assert(confirmations.at(-1).message.includes("не будет отправлен повторно"));

// A reopened window must observe derived execution before attempting continuation.
item = {...item, state: {...item.state, stages: [{kind: "draft"}], auto_resume: true},
  execution: {...item.execution, can_resume: false}};
await emit("session_start", {reason: "resume"});
assert.equal(resumeCalls, 0);
assert(statuses.get("zara-setup").includes("новую подготовку"));
assert.equal(widgets.get("zara-setup"), undefined);
// A stop can race the successful status read; refusal must not hide saved status.
item = {...item, execution: {...item.execution, status: "stopped", can_resume: true}};
refuseResume = true;
await emit("session_start", {reason: "resume"});
assert.equal(resumeCalls, 0);
assert(!notifications.some(entry => entry.message.includes("unknown_effect")));
assert.equal(widgets.get("zara-setup"), undefined);
assert.equal(aborted, 0);
assert.equal(typeof tick, "function");
tick();
await new Promise(resolve => setImmediate(resolve));
assert.equal(resumeCalls, 0);

// Known completed stages also wait for an actual owner conversation to resume.
refuseResume = false;
for (const phase of ["drafting", "reviewing", "correcting", "activating"]) {
  item = {...item, state: {...item.state, phase, auto_resume: false},
    execution: {...item.execution, status: "idle", can_resume: true}};
  const before = resumeCalls;
  await emit("session_start", {reason: "resume"});
  assert.equal(resumeCalls, before);
  assert.equal(typeof tick, "function");
}

const failureEvent = (code, setup_id = "fictional-guard-setup") => ({toolName: "zara_activity",
  toolCallId: `fixture-${code}`, input: {mode: "attach_sources", setup_id}, isError: true,
  content: [{type: "text", text: `Core ${code}: Fictional addressed refusal`}], details: {code}});
await emit("tool_result", failureEvent("setup_running"));
await emit("tool_result", {toolName: "zara_activity", toolCallId: "pause-fixture",
  input: {mode: "pause", setup_id: "fictional-guard-setup"}, isError: false,
  content: [{type: "text", text: "Saved pause; executor is stopping"}]});
await emit("tool_result", failureEvent("setup_stopping"));
assert.equal(aborted, 0); // A distinct cause has its own bounded history.
await emit("tool_result", {toolName: "zara_activity", toolCallId: "status-fixture",
  input: {mode: "status", setup_id: "fictional-guard-setup"}, isError: false});
await emit("tool_result", failureEvent("setup_stopping"));
assert.equal(aborted, 1); // Neither pause nor a read clears an unchanged failing call.

// Native command inspection never turns an assigned/composite/closed Work into
// an ordinary execution pin. An answer addresses the inspected Work explicitly.
const nativeEntries = [];
loaded.runtime.appendEntry = (customType, data) => nativeEntries.push({type: "custom", customType, data});
ctx.sessionManager.getBranch = () => nativeEntries;
const workIds = {ordinary: "ordinary-a", assigned: "assigned-b", composite: "composite-c", closed: "closed-d"};
let selectedLabel = "ordinary";
ctx.ui.select = async (title, options) => title === "Activity" ? options[0] : title === "Work"
  ? options.find(value => value.includes(`[${workIds[selectedLabel]}]`)) : options[0];
ctx.ui.input = async () => "Fictional addressed answer";
ctx.ui.confirm = async () => true;
const reads = [], transitions = [], answers = [], recoveries = [];
const coreSnapshot = id => ({execution_epoch: 1,
  work: {work_id: id, revision: 1, state: {status: id === workIds.closed ? "succeeded" : "proposed",
    linked_outputs: []}}, resources: [], attempts: [],
  assignments: id === workIds.assigned ? [{status: "waiting"}] : [],
  waits: id === workIds.assigned ? [{wait_id: "assigned-question", status: "open", question: "Continue?"}] : [],
  composition: id === workIds.composite ? {plan_revision: 1, obligations: []} : null});
globalThis.fetch = async (url, init) => {
  const address = new URL(url);
  const body = init?.body ? JSON.parse(init.body) : {};
  assert.equal(address.origin, "http://127.0.0.1:1");
  if (address.pathname === "/v1/connect") return Response.json({schema_version: 18,
    space_id: "fictional-space", execution_epoch: 1, records: [
      {kind: "activity", record_id: "fictional-activity", label: "Fictional activity"},
      ...Object.entries(workIds).map(([label, record_id]) => ({kind: "work", record_id,
        activity_id: "fictional-activity", label}))]});
  if (address.pathname === "/v1/snapshot") {
    const id = address.searchParams.get("work_id") ?? workIds.ordinary;
    reads.push(id);
    return Response.json(coreSnapshot(id));
  }
  if (address.pathname === "/v1/conversation") {
    if (body.mode === "selection_recovery") recoveries.push(body.departing);
    if (body.mode === "selection_target") return Response.json({target: {mode: "ordinary", work_id: body.work_id, work_revision: 1}});
    if (body.mode === "selection_transition") {
      transitions.push(body);
      return Response.json({selection_transition: {selection: {activity_id: "fictional-activity", work_id: workIds.ordinary},
        changed: true, preserve_attempt: false}});
    }
    return Response.json({registered: true});
  }
  if (address.pathname === "/v1/workspace") return Response.json({personal_root: directory,
    selected_root: directory, selected_project: "personal", projects: [], git: {connected: false}});
  if (address.pathname === "/v1/activity-setup") return Response.json(body.action === "list" ? {items: []} : item);
  if (address.pathname === "/v1/workflow") return Response.json({items: []});
  if (address.pathname === "/v1/answer") {
    answers.push(body);
    return Response.json({operation_id: "addressed-answer-receipt", selection_transition: {
      selection: null, changed: true, preserve_attempt: false,
      target: {mode: "assigned", work_id: body.work_id, work_revision: 1}}});
  }
  throw new Error(`Unexpected native UI endpoint ${address.pathname}`);
};
await emit("session_start", {reason: "resume"});
await extension.commands.get("zara-work").handler("", ctx);
assert.equal(transitions.length, 1);
for (const mode of ["assigned", "composite", "closed"]) {
  selectedLabel = mode;
  await extension.commands.get("zara-work").handler("", ctx);
  assert.equal(transitions.length, 1);
  const count = reads.length;
  await extension.commands.get("zara-status").handler("", ctx);
  assert.equal(reads[count], workIds[mode]);
  assert(notifications.at(-2).message.includes("просмотр"));
}
selectedLabel = "assigned";
await extension.commands.get("zara-work").handler("", ctx);
await extension.commands.get("zara-answer").handler("", ctx);
assert.equal(answers.length, 1);
assert.equal(answers[0].work_id, workIds.assigned);
assert.equal(answers[0].wait_id, "assigned-question");
assert.equal(answers[0].selection_handoff.origin, "native_ui");
assert.equal(answers[0].selection_handoff.choice.body.work_id, workIds.assigned);
assert(nativeEntries.some(entry => entry.customType === "zara-project-selection" && entry.data.detached));
const surviving = {work_id: workIds.ordinary, attempt_id: "departing-attempt", session_id: "departing-session"};
nativeEntries.push({type: "custom", customType: "zara-selection-committed", data: {
  id: "cancelled-choice", cancelled: true, recovery_obstacle: surviving}});
await emit("session_start", {reason: "resume"});
assert.deepEqual(recoveries, [surviving]);
assert.equal(transitions.length, 1); // Passive restoration never selects or interrupts.
const report = { pi: packageMetadata.version, rendered_tool: true, no_phantom_user_notice: true,
  legacy_history_filtered: true, compact_both_parts_filtered: true,
  restored_question_is_status_only: true, duplicate_notifications: false,
  observed_stop_status: true, interrupted_retry_confirmation: true,
  unknown_reopen_does_not_resume: true, resume_refusal_keeps_saved_status: true,
  known_stage_reopen_waits_for_owner: true,
  addressed_error_guard_preserved: true, assigned_composite_closed_read_focus: true,
  inspection_answer_is_addressed_transition: true, cancelled_active_work_restored_as_obstacle: true,
  actual_provider_calls: 0 };
writeFileSync(join(directory, "report.json"), JSON.stringify(report, null, 2) + "\n");
console.log(JSON.stringify(report, null, 2));

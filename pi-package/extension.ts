import { DEFAULT_MAX_BYTES, type ExtensionAPI } from "@earendil-works/pi-coding-agent";
import { Type } from "typebox";
import { open, realpath } from "node:fs/promises";
import { resolve, relative, isAbsolute } from "node:path";
import { fileURLToPath } from "node:url";
import { createHash, randomUUID } from "node:crypto";
import { bootstrap, dataRoot, run } from "./bootstrap.mjs";

// Reversible source-data view only: never parse embedded text or grant it instruction authority.
export function nativeSourceDataView(value: any, history = false) {
  const view = structuredClone(value);
  const groups: any[][] = [];
  if (history && Array.isArray(view?.sources)) groups.push(view.sources);
  for (const context of [view, view?.sleep, view?.pinned]) {
    if (Array.isArray(context?.sleep_sources)) groups.push(context.sleep_sources);
  }
  const setupSource: any = view?.current?.managed_setup && view?.pinned
    ? {material: {messages: view.pinned.messages, prior_messages: view.pinned.prior_messages}} : null;
  if (setupSource) groups.push([setupSource]);
  for (const sources of groups) for (const source of sources) {
    const material = source?.material;
    if (!material || typeof material !== "object") continue;
    const fields: any[] = [];
    const decode = (container: any, field: string, path: string) => {
      if (!container || !Object.hasOwn(container, field)) return;
      const encoded = container[field];
      const marker: any = {path, encodedField: field, decodedField: "raw_utf8"};
      let reason = "noncanonical_base64";
      try {
        if (typeof encoded !== "string" || !/^(?:[A-Za-z0-9+/]{4})*(?:[A-Za-z0-9+/]{2}==|[A-Za-z0-9+/]{3}=)?$/.test(encoded)) throw new Error();
        const raw = Buffer.from(encoded, "base64");
        if (raw.toString("base64") !== encoded) throw new Error();
        marker.rawBytes = raw.length;
        marker.rawSHA256 = createHash("sha256").update(raw).digest("hex");
        reason = "unsupported_utf8";
        const text = new TextDecoder("utf-8", {fatal: true, ignoreBOM: true}).decode(raw);
        if (!Buffer.from(text, "utf8").equals(raw)) throw new Error();
        reason = "decoded_field_collision";
        if (Object.hasOwn(container, "raw_utf8")) throw new Error();
        delete container[field];
        container.raw_utf8 = text;
        marker.status = "decoded";
      } catch {
        marker.status = "unsupported";
        marker.reason = reason;
        marker.decodedNotDelivered = true;
        if (typeof encoded === "string") {
          marker.encodedBytes = Buffer.byteLength(encoded, "utf8");
          marker.encodedSHA256 = createHash("sha256").update(encoded, "utf8").digest("hex");
        }
      }
      fields.push(marker);
    };
    decode(material.observation, "raw_base64", "material.observation.raw_base64");
    decode(material.message, "raw", "material.message.raw");
    for (const key of ["messages", "prior_messages"]) {
      if (Array.isArray(material[key])) material[key].forEach((message: any, index: number) =>
        decode(message, "raw", `material.${key}[${index}].raw`));
    }
    if (fields.length) source.native_source_data_view = {
      codec: "canonical-base64/strict-utf8-v1", kind: "source_data",
      sourceSHA256: source.source_ref?.sha256, fields,
    };
  }
  if (setupSource?.native_source_data_view) view.pinned.native_message_data_view = {
    ...setupSource.native_source_data_view, root: "pinned", attempt_id: view.current.attempt,
    source: "Exact Core pinned messages; original encoded bytes retained by Core",
  };
  return view;
}

// This is the declared initial Sleep source-data view boundary, not a provider-token estimate.
export const NATIVE_SLEEP_PRESENTATION_MAX_BYTES = 1024 * 1024;
export function nativeInitialContextView(context: any) {
  const view = nativeSourceDataView(context);
  const isSleep = [context, context?.sleep, context?.pinned].some(value => Array.isArray(value?.sleep_sources));
  const size = (value: any) => Buffer.byteLength(JSON.stringify(value), "utf8");
  const isSetup = Boolean(context?.current?.managed_setup);
  if (!(isSleep || isSetup) || size(view) <= NATIVE_SLEEP_PRESENTATION_MAX_BYTES) return view;
  const fallback = structuredClone(context);
  fallback.native_source_data_presentation = {
    status: "decoded_NOT_DELIVERED", reason: "presentation_expansion",
    representation: "original_encoded_source_data", analysisAsserted: false,
    originalContextBytes: size(context), decodedContextBytes: size(view),
    budgetBytes: NATIVE_SLEEP_PRESENTATION_MAX_BYTES,
  };
  if (size(fallback) > NATIVE_SLEEP_PRESENTATION_MAX_BYTES) {
    throw new Error(`Initial ${isSetup ? "setup" : "Sleep"} source-data presentation does not fit: original encoded fallback with metadata is ${size(fallback)} bytes; boundary ${NATIVE_SLEEP_PRESENTATION_MAX_BYTES}. No source data was removed; no provider send is admitted.`);
  }
  return fallback;
}

// Pi's public default is a presentation budget, never a Core data or model-call limit.
export function presentNativeResult(name: string, payload: any, result: any) {
  const bytes = (value: any) => Buffer.byteLength(JSON.stringify(value), "utf8");
  const coreResult = result;
  const originalBytes = bytes(coreResult);
  result = nativeSourceDataView(result, name === "read" && payload.operation === "read_history");
  const viewBytes = bytes(result);
  const envelope = (value: any) => ({
    content: [{type: "text" as const, text: JSON.stringify(value)}],
    details: {
      ...(value.state !== undefined ? {state: value.state} : {}),
      ...(value.completed !== undefined ? {completed: value.completed} : {}),
      ...(value.rejection !== undefined ? {rejection: value.rejection} : {}),
      ...(value.projection !== undefined ? {projection: value.projection} : {}),
    },
  });
  const fits = (value: any) => bytes(envelope(value)) <= DEFAULT_MAX_BYTES;
  const finish = (value: any) => fits(value) ? envelope(value) : envelope({
    state: "NOT_DELIVERED", reason: "presentation_metadata_exceeds_budget",
    original_bytes: originalBytes, view_bytes: viewBytes,
    presentation_metadata_bytes: bytes(value), metadata_not_delivered: true,
  });
  if (name === "read" && payload.operation === "read_history" && Array.isArray(result.sources)) {
    const original = result.sources;
    const inputCursor = [payload.arguments.after_sequence ?? 0, payload.arguments.after_index ?? 0];
    const coreMarkers: any = {};
    for (const key of ["query_coverage", "state", "reason", "source_ref", "source_bytes"]) {
      if (Object.hasOwn(result, key)) coreMarkers[key] = result[key];
    }
    const page = (sources: any[]) => ({
      ...coreMarkers,
      high_watermark: result.high_watermark,
      sources,
      cursor: sources.length ? [sources[sources.length - 1].source_ref.sequence,
        sources[sources.length - 1].source_ref.index] : inputCursor,
      has_more: Boolean(result.has_more || sources.length < original.length),
      projection: {kind: "whole_source_prefix", budget_bytes: DEFAULT_MAX_BYTES,
        requested: payload.arguments.limit ?? 32, core_returned: original.length,
        returned: sources.length, withheld: original.length - sources.length,
        core_cursor: result.cursor, coverage: "Not delivered by this tool call; no analysis is asserted."},
    });
    const selected: any[] = [];
    for (const source of original) {
      if (!fits(page([...selected, source]))) break;
      selected.push(source);
    }
    let presented: any = page(selected);
    if (!selected.length && original.length) {
      presented = {...presented, state: "NOT_DELIVERED", reason: "single_source_too_large",
        source_ref: original[0].source_ref, source_bytes: bytes(coreResult.sources[0]),
        source_view_bytes: bytes(original[0]),
        required_tool_result_bytes: bytes(envelope(page([original[0]]))),
        advice: "A lower limit cannot split this source. Use any already pinned sleep_sources if available; this read did not deliver or analyse it."};
    }
    return finish(presented);
  }
  if (fits(result)) return envelope(result);
  if (["route", "change", "result"].includes(name) && result.state !== "rejected") {
    const current = result.current ?? {};
    const fields: any = {};
    for (const key of ["state", "completed", "accepted", "staged", "refs"]) {
      if (Object.hasOwn(result, key)) fields[key] = result[key];
    }
    if (current.work || current.attempt || current.scope) fields.current = {
      ...(current.work ? {work: current.work} : {}),
      ...(current.attempt ? {attempt: current.attempt} : {}),
      ...(current.scope ? {scope: current.scope} : {}),
    };
    let acknowledgement: any = {presentation: "ACKNOWLEDGEMENT_ONLY", operation: name,
      context_not_delivered: true, original_bytes: originalBytes, view_bytes: viewBytes,
      omissions: ["non_acknowledgement_fields", ...Object.keys(fields)]};
    for (const [key, value] of Object.entries(fields)) {
      const candidate = {...acknowledgement, [key]: value,
        omissions: acknowledgement.omissions.filter((field: string) => field !== key)};
      if (fits(candidate)) acknowledgement = candidate;
    }
    return envelope(acknowledgement);
  }
  return finish({state: "NOT_DELIVERED", operation: payload.operation ?? name,
    original_bytes: originalBytes, view_bytes: viewBytes,
    ...(payload.operation === "read_exact" ? {ref: payload.arguments} : {}),
    ...(payload.operation === "read_page" ? {query: payload.arguments} : {}),
    reason: "presentation_budget", advice: "Request fewer whole records or supported columns. No material was truncated or analysed."});
}

export default function (pi: ExtensionAPI) {
  let active = false;
  let python = "";
  let sessionId = "";
  let failed = false;
  let startLeaf: string | null = null;
  let currentOrigin: any = null;
  let messageOrigin: any = null;
  let setupActive = false;
  const callOrigins = new Map<string, any>();
  const ownPath = resolve(fileURLToPath(import.meta.url));
  const acceptContext = (context: any) => {
    currentOrigin = context.current?.attempt ? structuredClone(context.current) : null;
    setupActive = Boolean(context.current?.managed_setup);
    return context;
  };
  const trustedSetupTool = (name: string) => {
    const tool = pi.getAllTools().find(tool => tool.name === name);
    return ["zara_context", "zara_read", "zara_route", "zara_result", "zara_read_file", "zara_exchange"].includes(name)
      && tool && resolve(tool.sourceInfo.path) === ownPath;
  };
  let skipNextInput = false;
  let beforeReviewTools: string[] | null = null;
  const observedResultCalls = new Set<string>();
  const executedResultCalls = new Set<string>();
  const profile = (ctx: any) => ({adapter: "ordinary-native-pi", provider: ctx.model?.provider, model: ctx.model?.id, api: ctx.model?.api, thinking: ctx.thinkingLevel, cwd: ctx.cwd, setup_admission: "native-setup/v1"});
  let requestQueue: Promise<void> = Promise.resolve();
  const request = (body: Record<string, unknown>) => {
    // Snapshot identity and raw facts before any await or queued session change.
    const capturedBody = JSON.parse(JSON.stringify(body));
    const capturedPython = python;
    const capturedSession = sessionId;
    const capturedRoot = dataRoot().then(value => ({value}), error => ({error}));
    const operation = requestQueue.then(async () => {
      const root = await capturedRoot;
      if ("error" in root) throw root.error;
      const result = JSON.parse(await run(capturedPython, ["-m", "zaratustra_app.pi_host"], JSON.stringify({
        data_root: root.value, session_id: capturedSession, ...capturedBody,
      })));
      if (result.state === "error") throw Object.assign(new Error(result.text), {coreRejection: result.rejection});
      return result;
    });
    // A rejected caller keeps its rejection; later admissions are not retried or poisoned.
    requestQueue = operation.then(() => undefined, () => undefined);
    return operation;
  };
  const visible = async (ctx: any, work: () => Promise<any>) => {
    try { return await work(); } catch (error) {
      failed = true;
      ctx.abort();
      ctx.ui.notify(`Zaratustra hook incomplete: ${error instanceof Error ? error.message : String(error)}`, "error");
      throw error;
    }
  };
  const applyReviewTools = (context: any) => {
    acceptContext(context);
    if (setupActive) {
      if (!beforeReviewTools) beforeReviewTools = pi.getActiveTools();
      pi.setActiveTools(pi.getAllTools().filter(tool => trustedSetupTool(tool.name)).map(tool => tool.name));
    } else if (context.current?.mode === "exchange") {
      if (!beforeReviewTools) beforeReviewTools = pi.getActiveTools();
      pi.setActiveTools(pi.getAllTools().filter(tool => ["zara_context", "zara_read", "zara_result", "zara_exchange"].includes(tool.name) && trustedSetupTool(tool.name)).map(tool => tool.name));
    } else if (context.current?.mode === "review") {
      if (!beforeReviewTools) beforeReviewTools = pi.getActiveTools();
      const permitted = new Set(["read", "grep", "find", "ls", "zara_context", "zara_read", "zara_result"]);
      pi.setActiveTools(beforeReviewTools.filter(name => permitted.has(name)));
    } else if (beforeReviewTools) {
      pi.setActiveTools(beforeReviewTools); beforeReviewTools = null;
    }
  };
  const attach = async (ctx: any) => {
    await ctx.waitForIdle();
    python = await bootstrap(); sessionId = ctx.sessionManager.getSessionId();
    let context = await request({command: "attach", profile: profile(ctx)});
    if (context.manual_exchange_recovery) {
      const accepted = await ctx.ui.confirm("Продолжить ручной обмен?", "Прежний ответ прерван. Оригиналы и предложения сохранены. Завершить прерванный запуск без повторения его действий и начать новый с текущей моделью?");
      if (accepted) context = await request({command: "exchange-recover", work_id: context.manual_exchange_recovery.work, owner_words: "Подтверждено в Pi: прекратить прерванный запуск и продолжить ручной обмен с текущей моделью.", profile: profile(ctx)});
      else { active = false; throw new Error("Оригиналы и предложения сохранены. Продолжение не запущено."); }
    }
    active = true; failed = false;
    observedResultCalls.clear(); executedResultCalls.clear();
    applyReviewTools(context);
    return context;
  };
  const scopeFor = async (ctx: any, argument = "") => {
    const list = await request({command: "activities"});
    if (argument.trim()) {
      const matches = list.activities.filter((a: any) => a.id === argument.trim() || a.label === argument.trim());
      if (matches.length !== 1) throw new Error("Выберите существующую Activity.");
      return matches[0].id;
    }
    if (!list.activities.length) throw new Error("Сначала выполните запрос в Activity.");
    if (list.activities.length === 1) return list.activities[0].id;
    const choices = list.activities.map((a: any, i: number) => ({
      id: a.id, label: `${a.id === list.current_scope ? "Текущая: " : ""}${a.label} (${i + 1})`
    }));
    const selected = await ctx.ui.select("Activity", choices.map((a: any) => a.label));
    return choices.find((a: any) => a.label === selected)?.id;
  };
  pi.registerCommand("zaratustra", {
    description: "Attach Core to this normal Pi session; optional first message",
    handler: async (args, ctx) => visible(ctx, async () => {
      const context = await attach(ctx);
      if (context.recovered_result) pi.sendMessage({customType: "zaratustra-saved-step", content: context.recovered_result.text, display: true});
      ctx.ui.notify("Core attached. Continue in normal Pi. Setup uses trusted reads and atomic checkpoints; ordinary coding retains its tools.", "info");
      if (args.trim()) pi.sendUserMessage(args);
      else if (context.current?.managed_setup && context.current.attempt && !context.current.wait) {
        skipNextInput = true;
        pi.sendUserMessage("Continue the exact retained setup step from Core; completed checkpoints are already saved.");
      }
    }),
  });
  pi.registerCommand("zara-status", {
    description: "Show local Core diagnostics without model inference",
    handler: async (_args, ctx) => visible(ctx, async () => {
      await attach(ctx);
      const result = await request({command: "diagnostics"});
      pi.sendMessage({customType: "zaratustra-diagnostics", content: result.text, display: true});
    }),
  });
  pi.registerCommand("reopen", {
    description: "Reload Core context without repeating previous tools",
    handler: async (_args, ctx) => visible(ctx, async () => {
      ctx.abort(); await ctx.waitForIdle();
      python = await bootstrap(); sessionId = ctx.sessionManager.getSessionId();
      const context = await request({ command: "reopen", profile: profile(ctx) });
      active = true; failed = false;
      observedResultCalls.clear(); executedResultCalls.clear();
      applyReviewTools(context);
      if (context.recovered_result) pi.sendMessage({customType: "zaratustra-saved-step", content: context.recovered_result.text, display: true});
      pi.sendMessage({ customType: "zaratustra-context", content: JSON.stringify(nativeInitialContextView(context)), display: false });
      ctx.ui.notify("Core context reopened from durable Work/Result/wait. Unknown ordinary effects require reconciliation.", "info");
      if (context.current?.managed_setup && context.current.attempt && !context.current.wait) {
        skipNextInput = true;
        pi.sendUserMessage("Continue the exact retained setup step from Core. Do not repeat completed checkpoints.");
      }
    }),
  });
  pi.registerCommand("zara-cancel", {
    description: "Cancel open Core Work without repeating unknown external tools",
    handler: async (_args, ctx) => visible(ctx, async () => {
      if (!active) throw new Error("Attach Core first.");
      if (!await ctx.ui.confirm("Cancel Core Work?", "Previous external effects may have happened. A new request does not repeat them.")) return;
      ctx.abort();
      await ctx.waitForIdle();
      await request({command: "cancel"});
      applyReviewTools(await request({command: "context"}));
      failed = false;
      ctx.ui.notify("Core Work cancelled. Existing external effects remain unconfirmed.", "warning");
    }),
  });
  pi.registerCommand("zara-sleep", {
    description: "Run workspace-wide Core Sleep; optional explicit existing Activity target",
    handler: async (args, ctx) => visible(ctx, async () => {
      if (!active) await attach(ctx);
      const targeted = Boolean(args.trim());
      const scope = targeted ? await scopeFor(ctx, args) : "space";
      if (!scope) return;
      await request({command: "sleep", scope, profile: profile(ctx)});
      ctx.ui.notify(targeted ? `Targeted Sleep for Activity ${scope}.` : "Global Sleep: workspace scope space; sources retain their original ownership.", "info");
      skipNextInput = true;
      pi.sendUserMessage("Run the exact pinned Sleep Method for retained sources now. Use Core tools and stage its result metadata; speak normally.");
    }),
  });
  pi.registerCommand("zara-review", {
    description: "Open a fresh Pi session for a read-only review in the same Activity",
    handler: async (args, ctx) => {
      await attach(ctx);
      const scope = await scopeFor(ctx, args);
      if (!scope) return;
      await ctx.waitForIdle();
      await ctx.newSession({withSession: async fresh => {
        await fresh.sendUserMessage("/zaratustra", {expandPromptTemplates: true});
        await fresh.sendUserMessage("/zara-review-start " + scope, {expandPromptTemplates: true});
      }});
    },
  });
  pi.registerCommand("zara-review-start", {
    description: "Start Core review in this fresh Pi session",
    handler: async (args, ctx) => visible(ctx, async () => {
      await attach(ctx);
      const scope = await scopeFor(ctx, args);
      if (!scope) return;
      await request({command: "review", scope, profile: profile(ctx)});
      const permitted = new Set(["read", "grep", "find", "ls", "zara_context", "zara_read", "zara_result"]);
      beforeReviewTools = pi.getActiveTools();
      pi.setActiveTools(beforeReviewTools.filter(name => permitted.has(name)));
      skipNextInput = true;
      pi.sendUserMessage("Independently refute the delivered task using the exact Core review basis and read-only evidence. Stage the review with zara_result; explain findings and limits normally. Do not accept on the owner's behalf.");
    }),
  });
  pi.registerCommand("zara-owner-result", {
    description: "Record your explicit verdict about the exact delivered result",
    handler: async (_args, ctx) => visible(ctx, async () => {
      await attach(ctx);
      const delivered = await request({command: "delivery"});
      pi.sendMessage({customType: "zaratustra-owner-result", content: delivered.result.text, display: true});
      if (delivered.review) pi.sendMessage({customType: "zaratustra-review", content: delivered.review.text, display: true});
      const choices: Record<string, string> = {"Принять результат": "accepted", "Нужны изменения": "revised", "Отклонить результат": "rejected"};
      const words = await ctx.ui.select("Ваш вердикт по показанному результату", Object.keys(choices));
      if (!words) return;
      const note = await ctx.ui.input("Комментарий (необязательно)");
      const result = await request({command: "owner-verdict", attempt_id: delivered.attempt_id,
        result_hash: delivered.result_hash, verdict: choices[words], owner_words: words + (note ? ": " + note : "")});
      ctx.ui.notify(result.text, "info");
    }),
  });
  pi.registerCommand("zara-reply", {
    description: "Reply to the exact currently displayed Core question",
    handler: async (args, ctx) => visible(ctx, async () => {
      if (!active || !args.trim()) throw new Error("Attach Core and provide reply text.");
      const context = await request({command: "context"});
      if (context.waiting.length !== 1) throw new Error("No unique waiting Core question.");
      const wait = context.waiting[0];
      await request({command: "reply", event_id: randomUUID(), text: args,
        reply_to: {id: wait.id, revision: wait.revision}, profile: profile(ctx)});
      skipNextInput = true;
      pi.sendUserMessage(args);
    }),
  });
  pi.on("input", async (event, ctx) => {
    if (!active) return;
    if (skipNextInput) { skipNextInput = false; return; }
    try {
      applyReviewTools(await visible(ctx, () => request({ command: "input", event_id: randomUUID(), text: event.text, profile: profile(ctx) })));
    } catch { return {action: "handled" as const}; }
  });
  pi.on("before_agent_start", async (_event, ctx) => {
    if (!active) return;
    if (failed) { ctx.abort(); return; }
    startLeaf = ctx.sessionManager.getLeafId();
    const context = await visible(ctx, () => request({ command: "verify-profile", profile: profile(ctx) }));
    applyReviewTools(context);
    if (setupActive) ctx.ui.setStatus?.("zaratustra-save", "Шаг выполняется; сохранение ещё не подтверждено Core.");
    const view = await visible(ctx, async () => nativeInitialContextView(context));
    return { message: { customType: "zaratustra-context", content: JSON.stringify(view), display: false } };
  });
  pi.on("message_start", async (event, _ctx) => {
    if (active && event.message.role === "assistant") messageOrigin = currentOrigin ? structuredClone(currentOrigin) : null;
  });
  const id = Type.String({minLength: 1, maxLength: 240});
  const exact = Type.Object({
    id, revision: Type.Integer({minimum: 1}),
    role: Type.Optional(Type.Union([Type.Literal("exact"), Type.Literal("must_be_current")])),
  }, {additionalProperties: false});
  const heads = Type.Record(Type.String(), Type.Integer({minimum: 0}));
  const cursor = Type.Integer({minimum: 0});
  const nullable = (schema: any) => Type.Union([schema, Type.Null()]);
  const change = Type.Object({
    id, kind: id, key: id, scope: Type.Optional(id), body: Type.Any(),
    source_refs: Type.Optional(Type.Array(exact)), schema_ref: Type.Optional(nullable(exact)),
    tombstone: Type.Optional(Type.Boolean()),
    application: Type.Optional(Type.Union(["active", "proposal", "withdrawn"].map(value => Type.Literal(value)))),
    artifact_refs: Type.Optional(Type.Array(Type.String({pattern: "^[0-9a-f]{64}$"}), {maxItems: 32})),
  }, {additionalProperties: false});
  const exchangeArgs = Type.Union([
    Type.Object({operation: Type.Literal("begin")}, {additionalProperties: false}),
    Type.Object({operation: Type.Literal("catalog")}, {additionalProperties: false}),
    Type.Object({operation: Type.Literal("retain_input"), arguments: Type.Optional(Type.Object({event: Type.Optional(id)}, {additionalProperties: false}))}, {additionalProperties: false}),
    Type.Object({operation: Type.Literal("retain_file"), arguments: Type.Object({path: Type.String({minLength: 1})}, {additionalProperties: false})}, {additionalProperties: false}),
    Type.Object({operation: Type.Literal("read"), arguments: Type.Object({ref: exact, offset: Type.Optional(cursor)}, {additionalProperties: false})}, {additionalProperties: false}),
    Type.Object({operation: Type.Literal("export"), arguments: Type.Object({ref: exact, path: Type.String({minLength: 1})}, {additionalProperties: false})}, {additionalProperties: false}),
    Type.Object({operation: Type.Literal("link"), arguments: Type.Object({ref: exact, previous: exact}, {additionalProperties: false})}, {additionalProperties: false}),
    Type.Object({operation: Type.Literal("prepare"), arguments: Type.Object({text: Type.String(), service: Type.String(), purpose: Type.String(), limits: Type.Optional(Type.String()), context: Type.Optional(Type.Array(exact)), activity_ref: Type.Optional(exact)}, {additionalProperties: false})}, {additionalProperties: false}),
    Type.Object({operation: Type.Literal("profile"), arguments: Type.Object({service: Type.String(), configuration: Type.Any(), capabilities: Type.Any(), sources: Type.Optional(Type.Array(exact)), activity_ref: Type.Optional(exact), owner_report: Type.Optional(Type.String()), delivery_evidence: Type.Optional(Type.String())}, {additionalProperties: false})}, {additionalProperties: false}),
    Type.Object({operation: Type.Literal("propose"), arguments: Type.Object({source_ref: exact, activity_ref: exact, changes: Type.Array(change), expected_heads: heads, explanation: Type.String({minLength: 1}), uncertainties: Type.Optional(Type.Array(Type.String())), supersedes: Type.Optional(exact)}, {additionalProperties: false})}, {additionalProperties: false}),
    Type.Object({operation: Type.Literal("confirm"), arguments: Type.Object({ref: exact, proposal_hash: Type.String({pattern: "^[0-9a-f]{64}$"})}, {additionalProperties: false})}, {additionalProperties: false}),
  ]);
  pi.registerTool({name: "zara_exchange", label: "Manual external exchange", executionMode: "sequential", parameters: Type.Object({payload: exchangeArgs}, {additionalProperties: false}),
    description: "Manual exchange with any external chat/program, no network sends. Read shipped zaratustra-external skill. begin BEFORE Activity routing; setup/retention need no Activity. Original native input is already retained mechanically by Core; retain_input saves its exact received bytes, never a model copy or summary. retain_file saves exact selected-file bytes before model analysis, maximum 16777216 bytes, no truncation. read returns reversible 16384-byte windows; follow next_offset for full coverage. prepare saves actual ready text with versions/context; profile records reported capability/setup evidence. propose saves model-selected scoped changes to an EXISTING Activity; missing dates/formats never block original retention. confirm shows exact stored proposal in human UI and applies only after affirmative owner choice. No JSON or commands required from the user. A retained original is not applied subject data.",
    async execute(callId, params, _signal, _update, ctx) {
      if (!active || failed) throw new Error("Attach Core first.");
      const origin = callOrigins.get(callId) ?? messageOrigin;
      let payload: any = structuredClone(params.payload);
      if (["retain_file", "export"].includes(payload.operation)) payload.arguments.path = resolve(ctx.cwd, payload.arguments.path);
      if (payload.operation === "confirm") {
        const checked = await request({command: "tool", name: "exchange", call_id: callId, origin, payload: {operation: "confirmation", arguments: payload.arguments}});
        if (checked.state === "applied") return presentNativeResult("exchange", payload, checked);
        const p = checked.proposal;
        const detail = `${p.explanation}\n\nНеясности: ${JSON.stringify(p.uncertainties)}\n\nТочные изменения:\n${JSON.stringify(p.changes, null, 2)}`;
        const accepted = await ctx.ui.confirm("Применить изменения из внешнего материала?", detail);
        if (!accepted) return {content: [{type: "text", text: "Оригинал сохранён; предложение ожидает решения. Предметные записи не изменены."}], details: {state: "pending", applied: false}};
        const result = await visible(ctx, () => request({command: "exchange-confirm", call_id: callId, origin, ...payload.arguments, owner_words: "Подтверждено в Pi: применить показанную точную версию предложения."}));
        return presentNativeResult("exchange", payload, result);
      }
      const result = await request({command: "tool", name: "exchange", call_id: callId, payload, origin});
      if (payload.operation === "begin") { applyReviewTools(result); messageOrigin = currentOrigin ? structuredClone(currentOrigin) : null; }
      return presentNativeResult("exchange", payload, result);
    },
  });
  const changeGuidance = " Change.body is the free record value, without a stored record wrapper. Metadata source_refs/schema_ref use record references {id,revision,role?}; history {sequence,index,sha256} references belong inside free analysis body.sources. For tagged sleep-progress/v1 or v2 bodies, follow the exact corresponding schema in context.outcome_metadata_contract.progress_schemas; required scope and version-specific fields must match. Do not add v2 predecessor_ref/range_start/transition fields to v1 or automatically change the version. Structural staging does not prove rights, current references or meaning; final Core admission still rechecks them.";
  const pageToken = Type.Object({high_watermark: cursor, sha256: Type.String({pattern: "^[0-9a-f]{64}$"})}, {additionalProperties: false});
  const readSchemas = Type.Union([
    Type.Object({operation: Type.Literal("read_exact"), arguments: Type.Object({
      id, revision: Type.Integer({minimum: 1}),
      role: Type.Optional(Type.Union([Type.Literal("exact"), Type.Literal("must_be_current")])),
    }, {additionalProperties: false})}, {additionalProperties: false}),
    Type.Object({operation: Type.Literal("read_page"), arguments: Type.Object({
      table: Type.Union(["heads", "works", "attempts", "messages", "conversations", "waits", "results", "observations", "actions", "intents", "tool_calls", "acceptance"].map(table => Type.Literal(table))),
      cursor: Type.Optional(cursor), limit: Type.Optional(Type.Integer({minimum: 1, maximum: 100})),
      snapshot_revision: Type.Optional(nullable(pageToken)),
      conversation: Type.Optional(nullable(id)), work: Type.Optional(nullable(id)), scope: Type.Optional(nullable(id)),
      columns: Type.Optional(nullable(Type.Array(id, {minItems: 1, maxItems: 8}))),
    }, {additionalProperties: false})}, {additionalProperties: false}),
    Type.Object({operation: Type.Literal("read_history"), arguments: Type.Object({
      scope: Type.Optional(id), high_watermark: Type.Optional(nullable(cursor)),
      after_sequence: Type.Optional(cursor), after_index: Type.Optional(cursor),
      limit: Type.Optional(Type.Integer({minimum: 1, maximum: 100})),
    }, {additionalProperties: false})}, {additionalProperties: false}),
  ]);
  const recoverableReadFields: Record<string, Set<string>> = {
    read_history: new Set(["history.high_watermark", "history.after"]),
    read_page: new Set(["columns", "conversation.table", "work.table", "scope.table", "snapshot_revision"]),
  };
  const schemas: Record<string, any> = {
    context: Type.Object({}, {additionalProperties: false}),
    read: readSchemas,
    route: Type.Object({changes: Type.Array(change), expected_heads: heads, outputs: Type.Array(exact), next_work: Type.Object({scope: Type.String(), goal: Type.String(), inputs: Type.Array(exact), setup: Type.Optional(Type.Boolean())}, {additionalProperties: false})}, {additionalProperties: false}),
    change: Type.Object({changes: Type.Array(change), expected_heads: heads}, {additionalProperties: false}),
    result: Type.Object({outputs: Type.Array(exact), changes: Type.Optional(Type.Array(change)), expected_heads: Type.Optional(heads), state: Type.Optional(Type.Union([Type.Literal("completed"), Type.Literal("waiting"), Type.Literal("ready")])), wait: Type.Optional(nullable(Type.Object({id, question: Type.String({minLength: 1})}, {additionalProperties: false}))), next_work: Type.Optional(nullable(Type.Object({goal: Type.String({minLength: 1}), inputs: Type.Optional(Type.Array(exact))}, {additionalProperties: false})))}, {additionalProperties: false}),
  };
  for (const name of ["context", "read", "route", "change", "result"]) {
    pi.registerTool({ executionMode: "sequential", name: `zara_${name}`, label: `Core ${name}`, parameters: Type.Object({payload: schemas[name]}, {additionalProperties: false}),
      description: (name === "route" ? "Choose Activity atomically: payload changes, expected_heads, outputs, next_work:{scope,goal,inputs,setup?:boolean}. New Activity creation always uses durable safe setup, even when setup is omitted/false. For an existing Activity choose setup:true only for explicit setup work; otherwise ordinary coding remains available. Required before useful work." : name === "result" ? "Stage Core METADATA only. In Sleep mode, stage real output refs or outputs:[]; no Activity output is required and no analysis is implied. In ordinary and review modes, required outputs include the current Activity exact reference. Optional changes/expected_heads/state/wait. ONLY in setup mode, optional next_work:{goal,inputs} atomically opens the next saved step; no intermediate zara_change. A final staged acknowledgement is not yet a saved checkpoint. NO text field and NO old JSON outcome envelope. A rejected response with staged:false has not staged this metadata; previous_metadata_cleared reports whether an older stage was cleared. If the SDK rejects arguments before execution, earlier metadata is invalidated before settlement; stage corrected metadata before your final reply. The original SDK error is unchanged and does not itself report host clearing flags. Correct structural arguments with a new tool call before writing your actual final reply normally in Pi; only that retained reply becomes result text." : name === "change" ? "Apply typed scoped Activity/data changes with expected_heads through Core CAS." : name === "read" ? "Read exact Core records, paged tables, or source history using the operation-specific arguments. read_history uses scope/high_watermark/after_sequence/after_index/limit; it has NO conversation argument. Native history queries have a fixed 51200-byte whole-result representation bound before Core persistence; whole sources may be withheld and coverage is explicit. This is not a total model-context or token guarantee. A rejected argument can be corrected with a new tool call; authorization or transport failures stop execution." : "Read authoritative Core context.") + (["route", "change", "result"].includes(name) ? changeGuidance : ""),
      async execute(callId, params, _signal, _update, ctx) {
        if (name === "result") executedResultCalls.add(callId);
        if (!active || failed) throw new Error("Attach or reopen Core; incomplete hooks require reconciliation.");
        const result = await visible(ctx, async () => {
          try { return await request({ command: "tool", name, call_id: callId, payload: params.payload, origin: callOrigins.get(callId) ?? messageOrigin }); }
          catch (error) {
            const rejection = (error as any).coreRejection;
            if (name === "read" && rejection?.code === "invalid_request" && recoverableReadFields[params.payload.operation]?.has(rejection.field)) {
              return {state: "rejected", rejection, text: "Read arguments rejected before a read result was returned. No work was completed. Issue a NEW corrected zara_read call using its operation-specific schema; read_history takes scope, not conversation. Do not repeat unknown effects."};
            }
            if (name === "result" && rejection?.code === "invalid_request" && ["native.result_metadata", "native.result_state", "native.review_activity_output"].includes(rejection.field)) {
              return {state: "rejected", rejection, text: "Metadata rejected before staging; no outcome committed. Correct the tool arguments using its schema. Do not pass text; write the actual final reply normally after staging."};
            }
            throw error;
          }
        });
        if (name === "route" && result.current) applyReviewTools(result);
        return presentNativeResult(name, params.payload, result);
      },
    });
  }
  pi.registerTool({name: "zara_read_file", label: "Setup read file", executionMode: "sequential",
    description: "Trusted UTF-8 regular-file read within the selected cwd. No shell, network, scripts or writes. Whole file only, maximum 51200 bytes; an unavailable file is not research performed.",
    parameters: Type.Object({path: Type.String({minLength: 1})}, {additionalProperties: false}),
    async execute(callId, params, _signal, _update, ctx) {
      if (!active || failed || !setupActive || !trustedSetupTool("zara_read_file")) throw new Error("Trusted setup admission required.");
      const origin = callOrigins.get(callId) ?? messageOrigin;
      await visible(ctx, () => request({command: "admit-setup-read", origin}));
      const root = await realpath(ctx.cwd), target = await realpath(resolve(root, params.path));
      const rel = relative(root, target);
      if (isAbsolute(rel) || rel === ".." || rel.startsWith(".." + (process.platform === "win32" ? String.fromCharCode(92) : "/"))) {
        return {content: [{type: "text", text: "NOT_DELIVERED: file is outside the selected repository."}], details: {delivered: false}};
      }
      const file = await open(target, "r");
      try {
        const stat = await file.stat();
        if (!stat.isFile() || stat.size > 50 * 1024) return {content: [{type: "text", text: "NOT_DELIVERED: requires a regular file of at most 51200 bytes."}], details: {delivered: false}};
        const buffer = Buffer.alloc(50 * 1024 + 1);
        const {bytesRead} = await file.read(buffer, 0, buffer.length, 0);
        const raw = buffer.subarray(0, bytesRead);
        if (raw.length > 50 * 1024) throw new Error("File changed while being read; not delivered.");
        const text = new TextDecoder("utf-8", {fatal: true, ignoreBOM: true}).decode(raw);
        return presentNativeResult("file-read", {}, {path: rel, sha256: createHash("sha256").update(raw).digest("hex"), text, source_data: true});
      } finally { await file.close(); }
    },
  });
  pi.on("user_bash", async (_event, _ctx) => {
    if (active && setupActive) return {result: {output: "NOT_EXECUTED: shell is outside the trusted setup profile. Exit setup only after a saved checkpoint; ordinary coding retains shell tools.", exitCode: 1, cancelled: false, truncated: false}};
  });
  const observe = (kind: string) => async (event: any, ctx: any) => {
    if (!active || failed) return;
    await visible(ctx, () => request({ command: "observation", event_id: randomUUID(), value: { kind, event }, origin: messageOrigin }));
  };
  pi.on("before_provider_request", async (_event, ctx) => {
    if (active && failed) ctx.abort();
    if (active && currentOrigin?.mode === "exchange") await visible(ctx, () => request({command: "verify-profile", profile: profile(ctx)}));
  });
  pi.on("tool_call", async (event, ctx) => {
    if (active && failed) return {block: true, terminate: true, reason: "Core admission failed; reconcile before execution."};
    if (active && messageOrigin?.managed_setup && !trustedSetupTool(event.toolName)) {
      return {block: true, reason: "Setup permits only this adapter's trusted reads and final Core checkpoint. This tool was NOT executed. Finish a small checkpoint or explain the unavailable tool."};
    }
    if (active && messageOrigin?.mode === "exchange" && !["zara_context", "zara_read", "zara_result", "zara_exchange"].includes(event.toolName)) {
      return {block: true, reason: "Manual exchange permits only Core exchange/read/result; no external effects."};
    }
    if (active) callOrigins.set(event.toolCallId, messageOrigin ? structuredClone(messageOrigin) : null);
    try {
      await observe("tool_call")(event, ctx);
      if (active && !failed && event.toolName === "zara_result") observedResultCalls.add(event.toolCallId);
    }
    catch { return {block: true, terminate: true, reason: "Core tool observation failed before execution."}; }
  });
  pi.on("tool_execution_end", async (event, ctx) => {
    try {
      if (!active || failed) return;
      // The installed SDK validates arguments before its tool_call hook and execute.
      // A failed result call reaching neither boundary is a known preexecution rejection.
      const sdkRejected = event.toolName === "zara_result" && event.isError === true
        && !observedResultCalls.has(event.toolCallId) && !executedResultCalls.has(event.toolCallId);
      await visible(ctx, () => request({command: "observation", event_id: randomUUID(), value: {
        kind: "tool_execution_end", event,
        ...(sdkRejected ? {sdk_preexecution_rejected: true} : {}),
      }, origin: callOrigins.get(event.toolCallId) ?? messageOrigin}));
    } finally {
      observedResultCalls.delete(event.toolCallId); executedResultCalls.delete(event.toolCallId); callOrigins.delete(event.toolCallId);
    }
  });
  pi.on("turn_end", async (event, ctx) => observe("turn_end")({
    turnIndex: event.turnIndex, messageEntryId: event.messageEntryId,
    toolResultEntryIds: event.toolResultEntryIds, message: event.message,
  }, ctx));
  pi.on("agent_settled", async (event, ctx) => {
    if (!active || failed) return;
    const branch = ctx.sessionManager.getBranch();
    const startIndex = branch.findIndex((e: any) => e.id === startLeaf);
    const entry = [...branch.slice(startIndex + 1)].reverse().find((e: any) => e.type === "message" && e.message.role === "assistant");
    const text = entry && entry.type === "message" && Array.isArray(entry.message.content)
      ? entry.message.content.filter((part: any) => part.type === "text").map((part: any) => part.text).join("\n") : "";
    const terminal = {stop_reason: entry?.message?.stopReason, error_message: entry?.message?.errorMessage};
    const result = await visible(ctx, () => request({ command: "settled", event_id: entry?.id || randomUUID(), text, aborted: event.aborted, terminal, origin: messageOrigin }));
    if (result.state === "incomplete") ctx.ui.notify(result.text, "warning");
    else {
      if (messageOrigin?.managed_setup && result.state !== "late") { ctx.ui.setStatus?.("zaratustra-save", "Шаг сохранён: Core receipt получен."); ctx.ui.notify("Шаг сохранён в Core.", "info"); }
      const context = await request({command: "context"});
      applyReviewTools(context);
      if (result.next_work_id && context.current?.managed_setup && !context.current.attempt) {
        applyReviewTools(await request({command: "reopen", profile: profile(ctx)}));
        skipNextInput = true;
        pi.sendUserMessage("Continue the exact next setup Work from Core. The previous checkpoint is already saved; do not repeat it.", {deliverAs: "followUp"});
      }
    }
  });
}





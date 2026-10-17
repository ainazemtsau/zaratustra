import type { ExtensionAPI } from "@earendil-works/pi-coding-agent";
import { Type } from "typebox";
import { randomUUID } from "node:crypto";
import { bootstrap, dataRoot, run } from "./bootstrap.mjs";

export default function (pi: ExtensionAPI) {
  let active = false;
  let python = "";
  let sessionId = "";
  let failed = false;
  let startLeaf: string | null = null;
  let skipNextInput = false;
  let beforeReviewTools: string[] | null = null;
  const profile = (ctx: any) => ({adapter: "ordinary-native-pi", provider: ctx.model?.provider, model: ctx.model?.id, api: ctx.model?.api, thinking: ctx.thinkingLevel, cwd: ctx.cwd});
  const request = async (body: Record<string, unknown>) => {
    const result = JSON.parse(await run(python, ["-m", "zaratustra_app.pi_host"], JSON.stringify({
      data_root: await dataRoot(), session_id: sessionId, ...body,
    })));
    if (result.state === "error") throw Object.assign(new Error(result.text), {coreRejection: result.rejection});
    return result;
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
    if (context.current?.mode === "review") {
      if (!beforeReviewTools) beforeReviewTools = pi.getActiveTools();
      const permitted = new Set(["read", "grep", "find", "ls", "zara_context", "zara_read", "zara_result"]);
      pi.setActiveTools(beforeReviewTools.filter(name => permitted.has(name)));
    } else if (beforeReviewTools) {
      pi.setActiveTools(beforeReviewTools); beforeReviewTools = null;
    }
  };
  const attach = async (ctx: any) => {
    python = await bootstrap(); sessionId = ctx.sessionManager.getSessionId();
    const context = await request({command: "attach"});
    active = true; failed = false;
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
      await attach(ctx);
      ctx.ui.notify("Core attached. Continue in normal Pi. Builtin tools remain available.", "info");
      if (args.trim()) pi.sendUserMessage(args);
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
      python = await bootstrap(); sessionId = ctx.sessionManager.getSessionId();
      const context = await request({ command: "reopen" });
      active = true; failed = false;
      applyReviewTools(context);
      pi.sendMessage({ customType: "zaratustra-context", content: JSON.stringify(context), display: false });
      ctx.ui.notify("Core context reopened. Unconfirmed prior tools require reconciliation.", "info");
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
      failed = false;
      ctx.ui.notify("Core Work cancelled. Existing external effects remain unconfirmed.", "warning");
    }),
  });
  pi.registerCommand("zara-sleep", {
    description: "Run Core Sleep for an explicit Activity scope in normal Pi",
    handler: async (args, ctx) => visible(ctx, async () => {
      if (!active) await attach(ctx);
      const scope = await scopeFor(ctx, args);
      if (!scope) return;
      await request({command: "sleep", scope, profile: profile(ctx)});
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
      await visible(ctx, () => request({ command: "input", event_id: randomUUID(), text: event.text, profile: profile(ctx) }));
    } catch { return {action: "handled" as const}; }
  });
  pi.on("before_agent_start", async (_event, ctx) => {
    if (!active) return;
    if (failed) { ctx.abort(); return; }
    startLeaf = ctx.sessionManager.getLeafId();
    const context = await visible(ctx, () => request({ command: "verify-profile", profile: profile(ctx) }));
    return { message: { customType: "zaratustra-context", content: JSON.stringify(context), display: false } };
  });
  const exact = Type.Object({id: Type.String(), revision: Type.Integer({minimum: 1})}, {additionalProperties: false});
  const heads = Type.Record(Type.String(), Type.Integer({minimum: 0}));
  const schemas: Record<string, any> = {
    context: Type.Object({}, {additionalProperties: false}),
    read: Type.Object({operation: Type.Union([Type.Literal("read_page"), Type.Literal("read_exact"), Type.Literal("read_history")]), arguments: Type.Any()}, {additionalProperties: false}),
    route: Type.Object({changes: Type.Array(Type.Any()), expected_heads: heads, outputs: Type.Array(exact), next_work: Type.Object({scope: Type.String(), goal: Type.String(), inputs: Type.Array(exact)}, {additionalProperties: false})}, {additionalProperties: false}),
    change: Type.Object({changes: Type.Array(Type.Any()), expected_heads: heads}, {additionalProperties: false}),
    result: Type.Object({outputs: Type.Array(exact), changes: Type.Optional(Type.Array(Type.Any())), expected_heads: Type.Optional(heads), state: Type.Optional(Type.Union([Type.Literal("completed"), Type.Literal("waiting"), Type.Literal("ready")])), wait: Type.Optional(Type.Any())}, {additionalProperties: false}),
  };
  for (const name of ["context", "read", "route", "change", "result"]) {
    pi.registerTool({ executionMode: "sequential", name: `zara_${name}`, label: `Core ${name}`, parameters: Type.Object({payload: schemas[name]}, {additionalProperties: false}),
      description: name === "route" ? "Choose Activity atomically: payload changes, expected_heads, outputs, next_work:{scope,goal,inputs}. Required before useful work." : name === "result" ? "Stage Core METADATA only. Required outputs include the current Activity exact reference. Optional changes/expected_heads/state/wait. NO text field and NO old JSON outcome envelope. After this tool, write your actual final reply normally in Pi; only that retained reply becomes result text." : name === "change" ? "Apply typed scoped Activity/data changes with expected_heads through Core CAS." : "Read authoritative Core context.",
      async execute(callId, params, _signal, _update, ctx) {
        if (!active || failed) throw new Error("Attach or reopen Core; incomplete hooks require reconciliation.");
        const result = await visible(ctx, async () => {
          try { return await request({ command: "tool", name, call_id: callId, payload: params.payload }); }
          catch (error) {
            const rejection = (error as any).coreRejection;
            if (name === "result" && rejection?.code === "invalid_request" && ["native.result_metadata", "native.result_state", "native.review_activity_output"].includes(rejection.field)) {
              return {state: "rejected", rejection, text: "Metadata rejected before staging; no outcome committed. Correct the tool arguments using its schema. Do not pass text; write the actual final reply normally after staging."};
            }
            throw error;
          }
        });
        return { content: [{ type: "text", text: JSON.stringify(result) }], details: result };
      },
    });
  }
  const observe = (kind: string) => async (event: any, ctx: any) => {
    if (!active || failed) return;
    await visible(ctx, () => request({ command: "observation", event_id: randomUUID(), value: { kind, event } }));
  };
  pi.on("before_provider_request", (_event, ctx) => {
    if (active && failed) ctx.abort();
  });
  pi.on("tool_call", async (event, ctx) => {
    if (active && failed) return {block: true, terminate: true, reason: "Core admission failed; reconcile before execution."};
    try { await observe("tool_call")(event, ctx); }
    catch { return {block: true, terminate: true, reason: "Core tool observation failed before execution."}; }
  });
  pi.on("tool_execution_end", observe("tool_execution_end"));
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
    const result = await visible(ctx, () => request({ command: "settled", event_id: entry?.id || randomUUID(), text, aborted: event.aborted, terminal }));
    if (result.state === "incomplete") ctx.ui.notify(result.text, "warning");
    else applyReviewTools(await request({command: "context"}));
  });
}





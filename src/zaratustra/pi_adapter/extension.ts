import { createHash, randomUUID } from "node:crypto";
import { createProvider, openAICompletionsApi } from "@earendil-works/pi-ai";
import { openaiCodexProvider } from "@earendil-works/pi-ai/providers/openai-codex";

const endpoint = process.env.ZARA_CORE_ENDPOINT;
const token = process.env.ZARA_CORE_TOKEN;
const allowedOrigin = process.env.ZARA_PROVIDER_ORIGIN;
const providerBaseUrl = process.env.ZARA_PROVIDER_BASE_URL;
const reserveUnits = Number(process.env.ZARA_RESERVE_UNITS);
const profile = process.env.ZARA_PROVIDER_PROFILE ?? "codex-sse";
const localProviderId = process.env.ZARA_LOCAL_PROVIDER_ID;
const localModelId = process.env.ZARA_LOCAL_MODEL_ID;
const assignedAttemptId = process.env.ZARA_ASSIGNED_ATTEMPT_ID;
const assignedSessionId = process.env.ZARA_ASSIGNED_SESSION_ID;

function digest(body: Uint8Array): string {
  return createHash("sha256").update(body).digest("hex").toUpperCase();
}

function bytes(body: unknown): Uint8Array {
  if (typeof body === "string") return Buffer.from(body, "utf8");
  if (body instanceof Uint8Array) return body;
  if (body instanceof ArrayBuffer) return new Uint8Array(body);
  throw new Error("Zaratustra cannot observe the final HTTP request body");
}

function lifecycle(current: any): string {
  const status = current?.status;
  if (!status) return "";
  const reasons = (status.reasons ?? [])
    .map((item: any) => [item.code, item.role, item.key,
      item.record_id ? `${item.record_id}${item.revision ? `@${item.revision}` : ""}` : null,
      item.premise ? `${item.premise.kind}:${item.premise.record_id}@${item.premise.revision}` +
        `→${item.premise.current ?? "unavailable"}` : null].filter(Boolean).join(":"))
    .join(", ");
  let line = `Work ${status.work_id}: ${status.status}${reasons ? ` (${reasons})` : ""}`;
  function renderPlan(plan: any, indent: string): void {
    line += `\n${indent}Plan ${plan.parent_work_id}@${plan.plan_revision}` +
      `${plan.plan_available ? "" : " (content unavailable)"}` +
      `${plan.role ? `; role ${plan.role}; issued@${plan.issued_plan_revision ?? "pending"}` : ""}` +
      `; Method ${plan.method.method_id}@${plan.method.version}`;
    for (const child of plan.children ?? []) {
      line += `\n${indent}  child ${child.role}: ${child.status.status} [${child.work_id}]` +
        `${child.issued_plan_revision ? ` issued@${child.issued_plan_revision}` : ""}` +
        `${child.revalidation ? ` revalidated@${child.revalidation}` : ""}`;
    }
    for (const child of plan.departed ?? [])
      line += `\n${indent}  departed ${child.role} ${child.work_id}: ${child.status.status}`;
    for (const item of plan.obligations ?? []) {
      line += `\n${indent}  obligation ${item.key}@${item.revision} (${item.role ?? "own Work"}):` +
        ` ${item.applicability}/${item.status}` +
        `${item.choice ? ` choice ${item.choice.decision_id}@${item.choice.revision}` : ""}` +
        `${item.exception ? ` exception ${item.exception.decision_id}@${item.exception.revision}` : ""}` +
        `${item.reopened ? ` reopened ${item.reopened}` : ""}`;
    }
    for (const node of plan.nodes ?? [])
      line += `\n${indent}  node ${node.role}: ${node.decision} ${node.work_id}` +
        `${node.replaced_work_id ? ` replaces ${node.replaced_work_id}` : ""}`;
    for (const pin of plan.pins ?? [])
      line += `\n${indent}  pin ${pin.attempt_id}: plan@${pin.plan_revision};` +
        ` Method ${pin.method.method_id}@${pin.method.version}`;
    for (const pin of plan.own_pins ?? [])
      line += `\n${indent}  own Attempt ${pin.attempt_id}: plan@${pin.plan_revision};` +
        ` Method ${pin.method.method_id}@${pin.method.version}`;
    for (const transfer of plan.transfers ?? [])
      line += `\n${indent}  transfer ${transfer.attempt_id}:` +
        ` plan@${transfer.from_plan_revision}→${transfer.plan_revision};` +
        ` Method ${transfer.method.method_id}@${transfer.method.version}`;
    if (plan.nested) renderPlan(plan.nested, `${indent}  nested `);
  }
  if (current.composition) renderPlan(current.composition, "");
  return `${line}\n`;
}

function usageUnits(usage: any): number | null {
  if (!usage || typeof usage !== "object") return null;
  const total = Number(usage.totalTokens ?? usage.total_tokens);
  if (Number.isSafeInteger(total) && total >= 0) return total;
  const input = Number(usage.input ?? usage.promptTokens);
  const output = Number(usage.output ?? usage.completionTokens);
  if (Number.isSafeInteger(input) && input >= 0 && Number.isSafeInteger(output) && output >= 0) {
    return input + output;
  }
  return null;
}

export default function (pi: any): void {
  if (!endpoint || !token || !allowedOrigin || !providerBaseUrl || !Number.isSafeInteger(reserveUnits) || reserveUnits < 1) {
    throw new Error("Zaratustra bridge requires endpoint, token, origin and positive reserve");
  }
  const sessionId = assignedSessionId ?? randomUUID();
  let connection: any = null;
  let selection: any = null;
  let attemptId: string | null = null;
  let contextReady = false;
  let nextPurpose = "content";
  let lastAnswer = "";
  let lastOutcome = "";
  const turnQueue: string[] = [];
  const compactQueue: string[] = [];
  const sent = new Set<string>();

  async function request(path: string, data?: any): Promise<any> {
    const response = await fetch(`${endpoint}${path}`, {
      method: data === undefined ? "GET" : "POST",
      headers: { Authorization: `Bearer ${token}`, "Content-Type": "application/json" },
      body: data === undefined ? undefined : JSON.stringify({ session_id: sessionId, ...data }),
    });
    const result = await response.json();
    if (!response.ok) throw new Error(`Core ${result.error ?? response.status}: ${result.detail ?? ""}`);
    return result;
  }

  async function operation(fields: any): Promise<any> {
    if (!connection) throw new Error("Pi is not connected to Core");
    const operationId = fields.operation_id ?? randomUUID();
    const intent = {
      protocol_version: 1,
      operation_id: operationId,
      space_id: connection.space_id,
      actor: connection.actor,
      ...fields,
    };
    try {
      return await request("/v1/operation", { request: intent });
    } catch (error) {
      try {
        return await request(`/v1/receipt?session_id=${sessionId}&operation_id=${operationId}`);
      } catch {
        throw error;
      }
    }
  }

  async function snapshot(): Promise<any> {
    return request(`/v1/snapshot?session_id=${sessionId}`);
  }

  async function finish(invocationId: string, outcome: "answered" | "unknown", usage: number | null,
                        httpStatus: number | null = null): Promise<void> {
    if (!attemptId) return;
    await operation({
      kind: "finish_invocation", invocation_id: invocationId, attempt_id: attemptId,
      work_id: selection.work_id, session_id: sessionId, outcome,
      usage_units: outcome === "answered" ? usage : null,
      http_status: httpStatus,
    });
    sent.delete(invocationId);
  }

  async function guardedFetch(model: any, input: any, init: any): Promise<Response> {
    if (!selection) return fetch(input, init);
    if (!attemptId || !contextReady) throw new Error("Core context or Attempt is not ready; no HTTP was sent");
    const selectedProvider = profile === "codex-sse" ? "openai-codex" : localProviderId;
    if (model.provider !== selectedProvider) throw new Error("Selected provider has no admitted transport profile");
    const url = new URL(typeof input === "string" ? input : input.url);
    if (url.origin !== allowedOrigin) throw new Error("Provider URL differs from the selected transport profile");
    const body = bytes(init?.body);
    const invocationId = randomUUID();
    const purpose = nextPurpose;
    nextPurpose = "content";
    const common = {
      invocation_id: invocationId, attempt_id: attemptId, work_id: selection.work_id,
      session_id: sessionId,
    };
    await operation({
      kind: "prepare_invocation", ...common, purpose,
      provider: model.provider, model: model.id, transport: profile === "codex-sse" ? "sse" : "http-sse",
      request_sha256: digest(body), request_bytes: body.byteLength,
      reserve_units: reserveUnits,
    });
    await operation({ kind: "admit_invocation", ...common });
    await operation({ kind: "send_invocation", ...common });
    sent.add(invocationId);
    try {
      const response = await fetch(input, init);
      if (!response.ok) {
        await finish(invocationId, "unknown", null, response.status);
      } else if (purpose === "compaction-summary") {
        compactQueue.push(invocationId);
      } else {
        turnQueue.push(invocationId);
      }
      return response;
    } catch (error) {
      try { await finish(invocationId, "unknown", null); } catch { /* sent keeps its reserve */ }
      throw error;
    }
  }

  const codex = profile === "codex-sse" ? openaiCodexProvider() : null;
  const local = profile === "local-completions" && localProviderId && localModelId
    ? createProvider({
        id: localProviderId, name: `Local ${localProviderId}`, baseUrl: providerBaseUrl,
        auth: { apiKey: { name: "Local provider", async login() {
          return { type: "api_key", key: "local" };
        }, async resolve() { return { auth: { apiKey: "local" }, source: "local provider" }; } } },
        models: [{ id: localModelId, name: localModelId, api: "openai-completions",
                   provider: localProviderId, baseUrl: providerBaseUrl, reasoning: false,
                   input: ["text"], cost: { input: 0, output: 0, cacheRead: 0, cacheWrite: 0 },
                   contextWindow: Number(process.env.ZARA_LOCAL_CONTEXT_WINDOW),
                   maxTokens: Number(process.env.ZARA_LOCAL_MAX_TOKENS) }],
        api: openAICompletionsApi(),
      }) : null;
  const base = codex ?? local;
  if (!base) throw new Error("Selected provider transport profile is unavailable");
  const observedProvider = base.id;
  const guardedStreams = new Map<string, any>();

  function guardOtherProviders(ctx: any): void {
    const seen = new Set<string>();
    for (const model of ctx.modelRegistry.getAll()) {
      const id = model.provider;
      if (id === observedProvider || seen.has(id)) continue;
      seen.add(id);
      const original = ctx.modelRegistry.getProvider(id);
      if (!original) throw new Error(`Provider ${id} cannot be guarded`);
      if (original.stream === guardedStreams.get(id)) continue;
      const guard = (method: "stream" | "streamSimple") => (...args: any[]) => {
        if (selection) throw new Error(`Provider ${id} has no admitted transport profile; no HTTP was sent`);
        return original[method](...args);
      };
      const stream = guard("stream");
      pi.registerProvider({
        ...original,
        stream,
        ...(typeof original.streamSimple === "function" ? { streamSimple: guard("streamSimple") } : {}),
      });
      guardedStreams.set(id, stream);
    }
  }
  pi.registerProvider({
    ...base,
    stream(model: any, context: any, options: any = {}) {
      return base.stream(model, context, {
        ...options, transport: "sse", maxRetries: 0,
        fetch: (input: any, init: any) => guardedFetch(model, input, init),
      });
    },
    streamSimple(model: any, context: any, options: any = {}) {
      return base.streamSimple(model, context, {
        ...options, transport: "sse", maxRetries: 0,
        fetch: (input: any, init: any) => guardedFetch(model, input, init),
      });
    },
  });

  pi.on("session_start", async (_event: any, ctx: any) => {
    selection = null;
    attemptId = null;
    contextReady = false;
    connection = await request("/v1/connect", {});
    guardOtherProviders(ctx);
    if (process.env.ZARA_INITIAL_ACTIVITY_ID && process.env.ZARA_INITIAL_WORK_ID) {
      const current = await request("/v1/select", {
        activity_id: process.env.ZARA_INITIAL_ACTIVITY_ID,
        work_id: process.env.ZARA_INITIAL_WORK_ID,
      });
      selection = { activity_id: process.env.ZARA_INITIAL_ACTIVITY_ID,
                    work_id: process.env.ZARA_INITIAL_WORK_ID };
      if (assignedAttemptId) {
        if (!current.attempts.some((x: any) => x.attempt_id === assignedAttemptId && x.status === "active")) {
          throw new Error("Assigned Attempt is unavailable");
        }
        attemptId = assignedAttemptId;
      } else if (!current.composition && current.work.state.status === "proposed" &&
          !current.work.state.linked_outputs.length &&
          !current.attempts.some((x: any) => x.status === "active")) {
        const started = await request("/v1/start-attempt", { interrupt_previous: false });
        attemptId = started.attempt_id;
      }
    }
    ctx.ui.notify(`Zaratustra Core ${connection.space_id} epoch ${connection.execution_epoch}. Use /zara-work.`, "info");
  });

  pi.on("model_select", (_event: any, ctx: any) => { guardOtherProviders(ctx); });
  pi.on("before_provider_request", (_event: any, ctx: any) => { guardOtherProviders(ctx); });

  pi.registerCommand("zara-work", {
    description: "Choose a Core Activity and Work, then start a bound Attempt",
    handler: async (_args: string, ctx: any) => {
      connection = await request("/v1/connect", {});
      const activities = connection.records.filter((row: any) => row.kind === "activity");
      const activityLabel = await ctx.ui.select("Activity", activities.map((row: any) => `${row.label} [${row.record_id}]`));
      const activity = activities.find((row: any) => `${row.label} [${row.record_id}]` === activityLabel);
      if (!activity) return;
      const works = connection.records.filter((row: any) => row.kind === "work" &&
                                                row.activity_id === activity.record_id);
      const workLabel = await ctx.ui.select("Work", works.map((row: any) => `${row.label} [${row.record_id}]`));
      const work = works.find((row: any) => `${row.label} [${row.record_id}]` === workLabel);
      if (!work) return;
      const current = await request("/v1/select", { activity_id: activity.record_id, work_id: work.record_id });
      selection = { activity_id: activity.record_id, work_id: work.record_id };
      if (current.assignments.some((x: any) => ["assigned", "waiting", "ready", "stop_requested", "unknown"].includes(x.status))) {
        ctx.ui.notify("Assigned Work loaded from Core. Use /zara-status and /zara-answer for its saved question.", "info");
        return;
      }
      if (current.work.state.status === "succeeded") {
        ctx.ui.notify("Accepted Work loaded from Core. Use /zara-status to inspect its result.", "info");
        return;
      }
      if (current.composition) {
        ctx.ui.notify(`${lifecycle(current)}Composite Work runs only through a Core-assigned Attempt. ` +
          "Use /zara-status to read its current Core state.", "info");
        return;
      }
      const prior = current.attempts.at(-1);
      let interrupt = false;
      if (prior?.status === "active") {
        interrupt = await ctx.ui.confirm("Previous Attempt is still active",
          `Mark ${prior.attempt_id} interrupted? Its sent or uncertain calls retain reserve. Continue only if the old Pi process has stopped.`);
        if (!interrupt) return;
      }
      const started = await request("/v1/start-attempt", { interrupt_previous: interrupt });
      attemptId = started.attempt_id;
      contextReady = false;
      ctx.ui.notify(`Attempt ${attemptId} selected. Enter the Work prompt.`, "info");
    },
  });

  pi.registerCommand("zara-status", {
    description: "Read the saved Core result, basis, rights and model reserve",
    handler: async (_args: string, ctx: any) => {
      const current = selection ? await snapshot() : await request("/v1/connect", {});
      ctx.ui.notify(`${lifecycle(current)}${JSON.stringify(current, null, 2)}`, "info");
    },
  });

  pi.registerCommand("zara-answer", {
    description: "Answer one saved, addressed Core question without a model call",
    handler: async (_args: string, ctx: any) => {
      if (!selection || assignedAttemptId) throw new Error("Select an assigned Work in interactive Pi");
      const current = await snapshot();
      const open = current.waits.filter((x: any) => x.status === "open");
      if (!open.length) { ctx.ui.notify("No open question for this Work.", "info"); return; }
      const labels = open.map((x: any) => `${x.question} [${x.wait_id}]`);
      const label = await ctx.ui.select("Saved Core question", labels);
      const chosen = open[labels.indexOf(label)];
      if (!chosen) return;
      const answer = await ctx.ui.input("Addressed answer", chosen.question);
      if (!answer?.trim()) return;
      const yes = await ctx.ui.confirm("Answer this exact question?", `${chosen.question}\nAnswer: ${answer}`);
      if (!yes) return;
      const receipt = await request("/v1/answer", { wait_id: chosen.wait_id, answer });
      ctx.ui.notify(`Answer saved in Core receipt ${receipt.operation_id}.`, "info");
    },
  });

  pi.registerCommand("zara-accept", {
    description: "Explicitly accept the current exact Work result",
    handler: async (_args: string, ctx: any) => {
      if (!selection) throw new Error("Select a Work first");
      const preview = await request("/v1/accept-preview", {});
      const basis = await ctx.ui.input("Acceptance basis", "Why is this exact result acceptable?");
      if (!basis?.trim()) return;
      const yes = await ctx.ui.confirm("Accept this exact Work revision?",
        `Work ${preview.work_id}@${preview.revision}\nOutputs: ${preview.outputs.map((x: any) => `${x.artifact_id}@${x.revision}`).join(", ")}\nBasis: ${basis}`);
      if (!yes) return;
      const receipt = await request("/v1/accept", { nonce: preview.nonce, basis });
      ctx.ui.notify(`Accepted by Core receipt ${receipt.operation_id}`, "info");
      attemptId = null;
      contextReady = false;
    },
  });

  pi.on("before_agent_start", async (_event: any, _ctx: any) => {
    if (!selection) return;
    contextReady = false;
    if (!attemptId) throw new Error("Select a new Attempt before prompting");
    const current = await snapshot();
    if (current.work.unavailable_refs.length || current.inputs.length !== current.work.state.inputs.length) {
      throw new Error("Required input is unavailable; no model request is permitted");
    }
    const render = (item: any) => ({
      artifact_id: item.artifact_id, revision: item.revision, media_type: item.media_type,
      content_sha256: item.content_sha256,
      content: item.media_type?.startsWith("text/") && item.content
        ? Buffer.from(item.content, "base64").toString("utf8") : null,
    });
    const context = {
      space_id: current.space_id, epoch: current.execution_epoch,
      activity_id: current.activity.activity_id, activity: current.activity.state,
      work_id: current.work.work_id, work_revision: current.work.revision,
      work: current.work.state, attempt_id: attemptId,
      inputs: current.inputs.map(render), saved_outputs: current.outputs.map(render),
      waits: current.waits.map((item: any) => ({ ...item })),
      cost: { committed_units: current.committed_units, held_units: current.held_units,
              remaining_units: current.remaining_units },
      // Addresses and pinned versions only; the plan itself stays in its Core revision.
      status: current.status ?? null, composition: current.composition ?? null,
    };
    contextReady = true;
    return { message: { customType: "zaratustra-context", content: JSON.stringify(context), display: false } };
  });

  pi.on("session_before_compact", () => { nextPurpose = "compaction-summary"; });
  pi.on("session_compact", async (event: any) => {
    const invocationId = compactQueue.shift();
    if (invocationId) {
      const units = usageUnits(event.compactionEntry?.usage);
      await finish(invocationId, units === null ? "unknown" : "answered", units);
    }
    nextPurpose = event.willRetry ? "overflow-retry" : "content";
  });
  pi.on("session_compact_failed", async () => {
    const invocationId = compactQueue.shift();
    if (invocationId) await finish(invocationId, "unknown", null);
    nextPurpose = "content";
  });
  pi.on("turn_end", async (event: any) => {
    const invocationId = turnQueue.shift();
    if (invocationId) {
      const units = usageUnits(event.message?.usage);
      await finish(invocationId, event.outcome === "completed" && units !== null ? "answered" : "unknown", units);
    }
    lastOutcome = event.outcome;
    lastAnswer = event.message?.content?.filter((x: any) => x.type === "text")
      .map((x: any) => x.text).join("\n") ?? "";
  });
  pi.on("agent_settled", async (_event: any, ctx: any) => {
    for (const invocationId of [...sent]) {
      if (!turnQueue.includes(invocationId) && !compactQueue.includes(invocationId)) {
        try { await finish(invocationId, "unknown", null); } catch { /* reserved in Core */ }
      }
    }
    if (!attemptId || !selection || lastOutcome !== "completed" || !lastAnswer.trim()) return;
    if (assignedAttemptId) {
      let result: any;
      try { result = JSON.parse(lastAnswer); }
      catch { throw new Error("Assigned RPC must return one JSON result or wait"); }
      if (result?.zara === "wait" && typeof result.partial === "string" &&
          typeof result.question === "string" && typeof result.remainder === "string") {
        await request("/v1/wait", {
          attempt_id: attemptId, wait_id: randomUUID(), partial: result.partial,
          question: result.question, remainder: result.remainder,
        });
        contextReady = false;
        return;
      }
      if (result?.zara !== "final" || typeof result.text !== "string" || !result.text.trim()) {
        throw new Error("Assigned RPC result has no valid final text");
      }
      lastAnswer = result.text;
    }
    const current = await snapshot();
    const slots = current.work.state.expected_outputs;
    if (slots.length !== 1 || !slots[0].media_type.startsWith("text/")) {
      ctx.ui.notify("Use an explicit output path for multi-slot or non-text Work.", "warning");
      return;
    }
    const published = await request("/v1/publish", {
      attempt_id: attemptId, slot: slots[0].slot,
      media_type: slots[0].media_type, content: lastAnswer,
    });
    if (!assignedAttemptId) {
      await operation({ kind: "stop_attempt", attempt_id: attemptId, work_id: selection.work_id,
                        session_id: sessionId, outcome: "completed" });
    }
    ctx.ui.notify(`Result saved as Artifact; Work remains proposed. Receipt ${published.publication.operation_id}.`, "info");
    attemptId = null;
    contextReady = false;
  });
}

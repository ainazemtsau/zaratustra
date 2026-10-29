import test from "node:test";
import assert from "node:assert/strict";
import { createHash } from "node:crypto";
import { mkdtempSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { DatabaseSync } from "node:sqlite";
import { z } from "zod";
import { createAssistantMessageEventStream } from "@earendil-works/pi-ai";
import type { AssistantMessage } from "@earendil-works/pi-ai";
import type {
  CreateAgentSessionOptions,
  ExtensionAPI,
  ExtensionContext,
  ExtensionToolContext,
} from "@earendil-works/pi-coding-agent";
import {
  SleepV2,
  assertSleepMutationAllowed,
  assertSleepDocumentAllowed,
  sleepDelegationRef,
  isSleepNotDispatched,
  defaultSleepProposalPolicy,
  selectSleepCases,
} from "../src/core/sleep-v2.ts";
import type { SleepProposal, SleepRef } from "../src/core/sleep-v2.ts";
import { CoreError, CommitSchema } from "../src/core/contracts.ts";
import type {
  AddressedRow,
  CallContext,
  Receipt,
  StoragePort,
} from "../src/core/contracts.ts";
import { FileEffectSchema } from "../src/core/effects.ts";
import { documentText } from "../src/core/documents.ts";
import type { Core } from "../src/core/index.ts";
import {
  registerSleep,
  readSleepSource,
  sleepResourceLoader,
  wrapSleepStream,
  SleepActionSchema,
} from "../src/extension/sleep.ts";

const model = {
  provider: "synthetic-provider",
  id: "synthetic-model",
  thinking: "medium",
};
function row(
  id: string,
  kind: AddressedRow["kind"] = "knowledge",
  data: Record<string, unknown> = {},
): AddressedRow {
  return {
    id,
    kind,
    title: "Synthetic retained record",
    body: null,
    revision: 1,
    created_at: "2026-10-01T00:00:00Z",
    updated_at: "2026-10-01T00:00:00Z",
    storage: "live",
    visibility: "workspace",
    data: {
      state: "current",
      knowledge_kind: "fact",
      statement: "Synthetic weekday condition.",
      ...data,
    },
    concept_ids: [],
    origin_activity_id: null,
  };
}
function fixture() {
  const home = mkdtempSync(join(tmpdir(), "zara-bounded-sleep-"));
  const db = new DatabaseSync(join(home, "projection.sqlite"));
  db.exec(
    "CREATE TABLE receipts(request_id TEXT PRIMARY KEY,json TEXT NOT NULL)",
  );
  const storage: StoragePort = {
    workspace: {
      workspace_id: "synthetic-workspace",
      epoch: "synthetic-epoch",
      schema_version: 10,
    },
    readonly: false,
    exec: (s) => db.exec(s),
    get: <T>(s: string, ...p: (string | number | null)[]) =>
      db.prepare(s).get(...p) as T | undefined,
    all: <T>(s: string, ...p: (string | number | null)[]) =>
      db.prepare(s).all(...p) as T[],
    run: (s, ...p) => {
      db.prepare(s).run(...p);
    },
    readMaterial: () => "",
    withCommandSync: (callback) => callback(),
  };
  const context: CallContext = {
    ...storage.workspace,
    principal: "trusted-personal",
    session_id: "synthetic-session",
    runtime_id: "runtime-A",
    can_write: true,
    processing_allowed: true,
    scopes: [],
  };
  const rows = new Map<string, AddressedRow>([
    ["note", row("note")],
    [
      "evidence",
      row("evidence", "evidence", {
        source_kind: "observed_input",
        retained_excerpt: "Synthetic exact input.",
        availability: "retained",
      }),
    ],
  ]);
  let now = Date.now();
  const read = (p: SleepRef | { id: string }): AddressedRow => {
    const r = rows.get(p.id);
    if (
      !r ||
      (r.visibility === "restricted" &&
        !context.scopes?.includes("restricted:read"))
    )
      throw new CoreError("REFERENCE_NOT_FOUND", "Unavailable");
    if ("revision" in p && p.revision !== r.revision)
      throw new CoreError(
        "REFERENCE_NOT_FOUND",
        "Historical fixture not retained",
      );
    return structuredClone(r);
  };
  const bind = {
    read,
    candidates: () => [...rows.values()],
    runtimeState: () => "dead" as const,
    now: () => now,
  };
  const controller = new SleepV2(storage, context, bind);
  const start = () => controller.start(null, model);
  const analyze = (id: string) => {
    controller.read(id, { id: "evidence" });
    controller.read(id, { id: "note" });
    controller.analyze(id, {
      question: "Does this condition need a clarification?",
      observations: "The retained source reports weekdays only.",
      hypothesis: null,
      counterexamples: [],
      grounds: [{ id: "evidence", revision: 1 }],
    });
  };
  const request = () =>
    CommitSchema.parse({
      request_id: "synthetic-change",
      reason: "Grounded reversible relation",
      source_handles: ["synthetic-observed-source"],
      guards: [],
      ops: [
        {
          op: "put_relation",
          client_ref: "relation",
          relation: "supports",
          from_ref: { id: "evidence" },
          to_ref: { id: "note" },
          reason: "Retained source supports the note.",
        },
      ],
    });
  const propose = (id: string) =>
    controller.propose(id, {
      reason: "Explicit support relation",
      expected_benefit: "Future readers can find grounds.",
      limits:
        "This is source attribution, not proof of universal availability.",
      premises: [
        { id: "evidence", revision: 1 },
        { id: "note", revision: 1 },
      ],
      request: request(),
      document_change: null,
      future_check: {
        trigger: "Next use of the condition",
        expected_observation: "Agent reads source and respects weekday limit.",
      },
    });
  return {
    home,
    db,
    storage,
    context,
    rows,
    bind,
    controller,
    start,
    analyze,
    propose,
    request,
    read,
    setNow: (value: number) => {
      now = value;
    },
    getNow: () => now,
  };
}
const hasCode = (fn: () => unknown, code: string) =>
  assert.throws(fn, (e: unknown) => e instanceof CoreError && e.code === code);

test("Sleep selects meaningful current cases, not every tool Evidence or technical Run", () => {
  const items = [
    row("tool", "evidence", { source_kind: "tool_result" }),
    row("review", "run", { mode: "sleep", execution: "failed" }),
    row("routine", "run", { mode: "work", execution: "completed" }),
    row("issue", "signal", { problem_state: "open" }),
    row("wait", "work", { status: "waiting" }),
    ...Array.from({ length: 15 }, (_, i) => row("note-" + i)),
  ];
  const selected = selectSleepCases(items, null);
  assert.equal(selected.length, 10);
  assert.equal(selected[0].id, "issue");
  assert.equal(selected[1].id, "wait");
  assert(!selected.some((r) => ["tool", "review", "routine"].includes(r.id)));
});

test("One active review; profile guessing is opaque and live/unknown runtime cannot be stolen", () => {
  const f = fixture();
  const first = f.start();
  assert.equal(f.start().id, first.id);
  const ctx = { ...f.context, runtime_id: "runtime-B" };
  const live = new SleepV2(f.storage, ctx, {
    ...f.bind,
    runtimeState: () => "unknown",
  });
  hasCode(() => live.resume(first.id, model), "STORE_BUSY");
  const restricted = new SleepV2(
    f.storage,
    { ...ctx, scopes: ["restricted:read"] },
    f.bind,
  );
  hasCode(() => restricted.status(first.id), "REFERENCE_NOT_FOUND");
  f.db.close();
});

test("Persisted model-generation limit survives new controller/runtime and refuses slot 21", async () => {
  const f = fixture();
  const s = f.start();
  for (let i = 0; i < 19; i++) f.controller.reserveGeneration(s.id);
  const c = new SleepV2(
    f.storage,
    { ...f.context, runtime_id: "runtime-B" },
    f.bind,
  );
  c.resume(s.id, model);
  c.reserveGeneration(s.id);
  hasCode(() => c.reserveGeneration(s.id), "SLEEP_BUDGET_EXHAUSTED");
  assert.equal(c.status(s.id)!.generations, 20);
  assert.equal(c.status(s.id)!.status, "budget_exhausted");
  hasCode(() => c.resume(s.id, model), "INVALID_TRANSITION");
  f.db.close();
});

test("Deadline and epoch prevent fresh execution, with no budget reset", () => {
  const f = fixture();
  const s = f.start();
  f.controller.reserveGeneration(s.id);
  f.setNow(s.deadline_at);
  hasCode(() => f.controller.reserveGeneration(s.id), "SLEEP_BUDGET_EXHAUSTED");
  assert.equal(f.controller.status(s.id)!.generations, 1);
  f.storage.workspace.epoch = "restored";
  hasCode(
    () => f.controller.read(s.id, { id: "note" }),
    "RESTORE_RECONCILIATION_REQUIRED",
  );
  f.db.close();
});

test("Analysis needs actually read refs; natural success or skipped phases do not complete a review", () => {
  const f = fixture();
  const s = f.start();
  hasCode(
    () => f.controller.finish(s.id, "no_change", "Looks fine"),
    "INVALID_TRANSITION",
  );
  hasCode(() => f.propose(s.id), "INVALID_TRANSITION");
  f.controller.read(s.id, { id: "note" });
  hasCode(
    () =>
      f.controller.analyze(s.id, {
        question: "Question",
        observations: "Observation",
        hypothesis: null,
        counterexamples: [],
        grounds: [{ id: "evidence", revision: 1 }],
      }),
    "SOURCE_MISSING",
  );
  f.analyze(s.id);
  const done = f.controller.finish(
    s.id,
    "no_change",
    "Current condition already matches the retained source.",
  );
  assert.equal(done.status, "completed");
  assert.equal(done.improvements, 0);
  f.db.close();
});

test("Opaque exact apply permit blocks SDK raw mutations but not ordinary concurrent work", () => {
  const f = fixture();
  const s = f.start();
  f.analyze(s.id);
  const p = f.propose(s.id);
  assert.equal(
    assertSleepMutationAllowed(f.storage, f.context, f.request()),
    false,
  );
  hasCode(
    () =>
      f.controller.inExecution(s.id, () =>
        assertSleepMutationAllowed(f.storage, f.context, f.request()),
      ),
    "PERMISSION_DENIED",
  );
  f.controller.validate(s.id, p.id);
  f.controller.beginApply(s.id, p.id);
  f.controller.withApplyPermit(s.id, p.id, () => {
    assert.equal(
      assertSleepMutationAllowed(f.storage, f.context, f.request()),
      true,
    );
    hasCode(
      () =>
        assertSleepMutationAllowed(f.storage, f.context, {
          ...f.request(),
          reason: "Changed payload",
        }),
      "PERMISSION_DENIED",
    );
  });
  const receipt: Receipt = {
    ok: true,
    committed: true,
    request_id: f.request().request_id,
    workspace_id: f.context.workspace_id,
    schema_version: 10,
    snapshot_seq: 1,
    transaction_id: "txn",
    created: {},
    new_revisions: {},
    warnings: [],
  };
  f.controller.settleApply(s.id, p.id, receipt);
  hasCode(
    () => f.controller.finish(s.id, "no_change", "Claimed no change"),
    "VALIDATION_ERROR",
  );
  const final = f.controller.finish(
    s.id,
    "applied_unverified",
    "Support relation saved; future usefulness pending.",
  );
  assert.equal(final.improvements, 1);
  assert.equal(f.controller.pendingChecks().length, 1);
  f.db.close();
});

test("Protected goals/identities and unbound documents cannot be automatically applied", () => {
  const f = fixture();
  const s = f.start();
  f.analyze(s.id);
  const p = f.propose(s.id);
  const dangerous = {
    ...p,
    request: CommitSchema.parse({
      ...f.request(),
      ops: [
        {
          op: "merge_identity",
          from_ref: { id: "note" },
          to_ref: { id: "evidence" },
        },
      ],
    }),
  };
  assert.equal(defaultSleepProposalPolicy(dangerous, s, f.read).allowed, false);
  f.rows.set(
    "document",
    row("document", "entity", { document: { state: "active" } }),
  );
  const document: SleepProposal = {
    ...p,
    request: null,
    document_change: {
      ref: { id: "document", revision: 1 },
      action: "update",
      content: "Unbound content",
    },
  };
  assert.equal(defaultSleepProposalPolicy(document, s, f.read).allowed, false);
  f.db.close();
});

test("A changed proposal guard invalidates validation; uncertain application is not replayed", () => {
  const f = fixture();
  const s = f.start();
  f.analyze(s.id);
  const request = {
    ...f.request(),
    guards: [{ ref: { id: "note" }, expected_revision: 1 }],
  };
  const p = f.controller.propose(s.id, {
    ...f.propose(s.id),
    request,
  } as Parameters<SleepV2["propose"]>[1]);
  f.rows.get("note")!.revision = 2;
  hasCode(() => f.controller.validate(s.id, p.id), "REVISION_CONFLICT");
  f.rows.get("note")!.revision = 1;
  f.controller.validate(s.id, p.id);
  f.controller.beginApply(s.id, p.id);
  f.controller.markUnknown(
    s.id,
    p.id,
    "Lost response after possible canonical commit.",
  );
  hasCode(() => f.controller.resume(s.id, model), "RECONCILIATION_REQUIRED");
  hasCode(() => f.controller.reconcile(s.id), "RECONCILIATION_REQUIRED");
  const receipt: Receipt = {
    ok: true,
    committed: true,
    request_id: request.request_id,
    workspace_id: f.context.workspace_id,
    schema_version: 10,
    snapshot_seq: 1,
    transaction_id: "txn",
    created: {},
    new_revisions: { note: 2 },
    warnings: [],
  };
  f.storage.run(
    "INSERT INTO receipts VALUES(?,?)",
    request.request_id,
    JSON.stringify(receipt),
  );
  const recovered = f.controller.reconcile(s.id);
  assert.equal(
    recovered.proposals.find((v) => v.id === p.id)!.status,
    "applied",
  );
  assert.equal(recovered.improvements, 1);
  f.db.close();
});

test("Stream wrapper returns a valid aborted stream and does not call native delegate after refusal", async () => {
  const f = fixture();
  const s = f.start();
  let calls = 0;
  const syntheticModel = {
    api: "openai-responses",
    provider: model.provider,
    id: model.id,
  } as Parameters<Parameters<typeof wrapSleepStream>[0]>[0];
  const native: Parameters<typeof wrapSleepStream>[0] = (m) => {
    calls++;
    const stream = createAssistantMessageEventStream();
    const message: AssistantMessage = {
      role: "assistant",
      content: [],
      api: m.api,
      provider: m.provider,
      model: m.id,
      usage: {
        input: 0,
        output: 0,
        cacheRead: 0,
        cacheWrite: 0,
        totalTokens: 0,
        cost: { input: 0, output: 0, cacheRead: 0, cacheWrite: 0, total: 0 },
      },
      stopReason: "stop",
      timestamp: Date.now(),
    };
    stream.push({ type: "done", reason: "stop", message });
    stream.end(message);
    return stream;
  };
  const wrapped = wrapSleepStream(native, async () => {
    f.controller.reserveGeneration(s.id);
  });
  for (let i = 0; i < 20; i++)
    assert.equal(
      (
        await (
          await wrapped(syntheticModel, {
            messages: [],
          } as unknown as Parameters<Parameters<typeof wrapSleepStream>[0]>[1])
        ).result()
      ).stopReason,
      "stop",
    );
  assert.equal(
    (
      await (
        await wrapped(syntheticModel, { messages: [] } as unknown as Parameters<
          Parameters<typeof wrapSleepStream>[0]
        >[1])
      ).result()
    ).stopReason,
    "aborted",
  );
  assert.equal(calls, 20);
  f.db.close();
});

test("SDK resource loader has no host instructions, extensions or recursive resources", async () => {
  const loader = sleepResourceLoader();
  await loader.reload();
  assert.deepEqual(loader.getExtensions().extensions, []);
  assert.deepEqual(loader.getAgentsFiles().agentsFiles, []);
  assert.deepEqual(loader.getSkills().skills, []);
  assert.match(loader.getSystemPrompt()!, /sleep_finish/);
  assert.throws(
    () => loader.extendResources({ skillPaths: [] }),
    /cannot load extra/,
  );
});

test("Native SDK configuration is bounded, same model, no tools outside allowlist and no transcript persistence", async () => {
  const f = fixture();
  const commands = new Map<string, unknown>();
  let registered:
    | ((params: Record<string, unknown>, ctx: ExtensionContext) => unknown)
    | undefined;
  let captured: CreateAgentSessionOptions | undefined,
    disposed = 0,
    nativeCalls = 0;
  const fakeCore = {
    storage: f.storage,
    context: f.context,
    read: (id: string) => ({ data: f.read({ id }) }),
  } as unknown as Core;
  const modelObject = {
    api: "openai-responses",
    provider: model.provider,
    id: model.id,
  } as ExtensionContext["model"];
  const ctx = {
    cwd: f.home,
    model: modelObject,
    thinkingLevel: "medium",
  } as ExtensionContext;
  const events: unknown[] = [];
  const pi = {
    sendMessage: (m: unknown) => events.push(m),
    registerCommand: (name: string, command: unknown) =>
      commands.set(name, command),
  } as unknown as ExtensionAPI;
  const runtime = registerSleep(
    (_n, _d, _s: z.ZodType, action) => {
      if (_n === "zara_sleep") registered = action;
    },
    pi,
    {
      core: () => fakeCore,
      withOperation: async (_kind, cb) => cb(),
      candidates: () => [...f.rows.values()],
      createSession: async (options) => {
        captured = options;
        const session = {
          model: modelObject,
          thinkingLevel: "medium",
          agent: {
            streamFunction: () => {
              nativeCalls++;
              return createAssistantMessageEventStream();
            },
            toolExecution: "parallel",
          },
          prompt: async () => {
            const tools = new Map(
              options!.customTools!.map((t) => [t.name, t]),
            );
            const invoke = async (name: string, value: unknown) =>
              tools
                .get(name)!
                .execute(
                  "synthetic-tool",
                  value as never,
                  undefined,
                  undefined,
                  ctx as ExtensionToolContext,
                );
            await invoke("sleep_read", { ref: { id: "note" } });
            await invoke("sleep_analyze", {
              question: "Any useful correction?",
              observations: "The retained condition remains applicable.",
              hypothesis: null,
              grounds: [{ id: "note", revision: 1 }],
              counterexamples: [],
            });
            await invoke("sleep_finish", {
              outcome: "no_change",
              summary: "No new grounds for a change.",
              continuation: null,
            });
          },
          abort: async () => {},
          dispose: () => {
            disposed++;
          },
        };
        return {
          session: session as never,
          extensionsResult: options!.resourceLoader!.getExtensions(),
        };
      },
    },
  );
  const result = (await registered!({ action: "start" }, ctx)) as {
    background: boolean;
  };
  assert.equal(result.background, true);
  for (let i = 0; i < 100 && runtime.activeCount(); i++)
    await new Promise<void>((r) => setImmediate(r));
  await runtime.shutdown();
  assert.equal(captured!.model, modelObject);
  assert.equal(captured!.thinkingLevel, "medium");
  assert.equal(captured!.settingsManager!.getSettings().cacheWarming, "off");
  assert.equal(captured!.settingsManager!.getCompactionEnabled(), false);
  assert.equal(captured!.settingsManager!.getSettings().retry?.enabled, false);
  assert.deepEqual(captured!.resourceLoader!.getExtensions().extensions, []);
  assert.deepEqual(captured!.tools, [
    "sleep_read",
    "sleep_analyze",
    "sleep_propose",
    "sleep_apply",
    "sleep_finish",
  ]);
  assert.equal(disposed, 1);
  assert.equal(nativeCalls, 0);
  assert(commands.has("zara-sleep"));
  assert.equal(f.controller.status()!.status, "completed");
  assert(events.length > 0);
  f.db.close();
});

function committedReceipt(
  f: ReturnType<typeof fixture>,
  requestId: string,
): Receipt {
  return {
    ok: true,
    committed: true,
    request_id: requestId,
    workspace_id: f.context.workspace_id,
    schema_version: 10,
    snapshot_seq: 1,
    transaction_id: "synthetic-txn",
    created: {},
    new_revisions: { note: 2 },
    warnings: [],
  };
}
test("Future checks require later real grounds and cannot be self-certified by the Sleep runtime", () => {
  const f = fixture(),
    s = f.start();
  f.analyze(s.id);
  const p = f.propose(s.id);
  f.controller.validate(s.id, p.id);
  f.controller.beginApply(s.id, p.id);
  f.controller.settleApply(
    s.id,
    p.id,
    committedReceipt(f, f.request().request_id),
  );
  f.controller.finish(
    s.id,
    "applied_unverified",
    "Change applied; usefulness unknown.",
  );
  assert.equal(f.controller.status(s.id)!.proposals[0].request, null);
  const evidence = {
    refs: [{ id: "note", revision: 1 }],
    verdict: "helped" as const,
    summary: "Reported outcome.",
  };
  hasCode(
    () =>
      f.controller.inExecution(s.id, () =>
        f.controller.observeCheck(s.id, p.id, evidence),
      ),
    "PERMISSION_DENIED",
  );
  hasCode(
    () => f.controller.observeCheck(s.id, p.id, evidence),
    "SOURCE_MISSING",
  );
  f.setNow(f.getNow() + 1000);
  f.rows.set("later", {
    ...row("later", "evidence", {
      source_kind: "tool_result",
      availability: "retained",
      retained_excerpt: "Observed result after applying the change.",
      captured_at: new Date(f.getNow()).toISOString(),
      provenance: {
        transport: "tool",
        observation: {
          tool_name: "synthetic_check",
          tool_call_id: "native-observation",
          is_error: false,
          full_content_hash: "a".repeat(64),
          truncated: false,
        },
      },
    }),
    created_at: new Date(f.getNow()).toISOString(),
    updated_at: new Date(f.getNow()).toISOString(),
  });
  const checked = f.controller.observeCheck(s.id, p.id, {
    ...evidence,
    refs: [{ id: "later", revision: 1 }],
  });
  assert.equal(checked.proposals[0].check_observation!.verdict, "helped");
  assert.equal(f.controller.pendingChecks().length, 0);
  f.db.close();
});
test("Paused pending proposals resume through fresh source rebuilding; no stale handle is dispatched", () => {
  const f = fixture(),
    s = f.start();
  f.analyze(s.id);
  const p = f.propose(s.id);
  f.controller.finish(
    s.id,
    "proposal_pending",
    "Await a concrete continuation.",
    "Recheck the retained source.",
  );
  const resumed = f.controller.resume(s.id, model);
  assert.equal(resumed.phase, "analyze");
  assert.equal(
    resumed.proposals.find((v) => v.id === p.id)!.status,
    "rejected",
  );
  assert.equal(resumed.proposals[0].request, null);
  f.controller.read(s.id, { id: "note" });
  const fresh = f.propose(s.id);
  assert.equal(fresh.status, "proposed");
  f.db.close();
});
test("Deterministic predispatch Core refusals do not create permanent UNKNOWN or reset budgets", () => {
  const f = fixture(),
    s = f.start();
  f.analyze(s.id);
  const p = f.propose(s.id);
  f.controller.validate(s.id, p.id);
  f.controller.beginApply(s.id, p.id);
  let refusal: unknown;
  try {
    f.controller.withApplyPermit(s.id, p.id, () => {
      throw new CoreError(
        "SOURCE_MISSING",
        "Runtime handle expired before commit.",
      );
    });
  } catch (e) {
    refusal = f.controller.classifyCoreRefusal(s.id, p.id, e);
  }
  assert(isSleepNotDispatched(refusal));
  const state = f.controller.rejectUnapplied(s.id, p.id, refusal);
  assert.equal(state.status, "running");
  assert.equal(state.phase, "analyze");
  assert.equal(state.improvements, 0);
  assert.equal(state.proposals[0].status, "rejected");
  f.db.close();
});
test("Document delegation is exact and registration can settle after deadline without another native write", () => {
  const f = fixture();
  f.db.exec(
    "CREATE TABLE intents(request_id TEXT PRIMARY KEY,json TEXT NOT NULL)",
  );
  const key = "18cd82c2-a761-4af8-8567-4b2e2db7df50",
    path = "sample/guide.md";
  const before = documentText(key, "Previous retained content."),
    after = documentText(key, "Organized retained content.");
  const sha = (v: string) => createHash("sha256").update(v).digest("hex");
  f.rows.set(
    "head",
    row("head", "evidence", {
      content_hash: sha(before),
      source_language: "en",
    }),
  );
  f.rows.set(
    "document",
    row("document", "entity", {
      document: {
        key,
        path,
        document_type: "guide",
        state: "active",
        format_ref: null,
        links: [],
        head_ref: { id: "head", revision: 1 },
        operation_id: "previous",
      },
    }),
  );
  f.rows.set(
    "activity",
    row("activity", "activity", {
      status: "active",
      contract: { document_refs: [{ id: "document" }] },
    }),
  );
  const s = f.controller.start("activity", model);
  f.analyze(s.id);
  f.controller.read(s.id, { id: "document" });
  const p = f.controller.propose(s.id, {
    reason: "Reorganize local guide",
    expected_benefit: "Find the selected rule.",
    limits: "Reversible document update only.",
    premises: [{ id: "document", revision: 1 }],
    request: null,
    document_change: {
      ref: { id: "document", revision: 1 },
      action: "update",
      content: "Organized retained content.",
    },
    future_check: {
      trigger: "Next reading",
      expected_observation: "Rule found without repeated search.",
    },
  });
  assert.equal(f.controller.validate(s.id, p.id).status, "validated");
  f.controller.beginApply(s.id, p.id);
  const effect = FileEffectSchema.parse({
    request_id: "sleep-document-request",
    tool: "write",
    arguments: { path: "C:/synthetic/activities/" + path, content: after },
    target: "C:/synthetic/activities/" + path,
    boundary: {},
    before_hash: sha(before),
    before_length: Buffer.byteLength(before),
    final_hash: sha(after),
    final_length: Buffer.byteLength(after),
    final_text: after,
    work_ref: null,
    step_id: null,
    independent_basis: "Manage selected local document",
    method_export: null,
    retry_of: null,
    retry_risk: null,
    document: {
      ref: { id: "document", revision: 1 },
      key,
      path,
      document_type: "guide",
      state: "active",
      activity_ref: { id: "activity", revision: 1 },
      format_ref: null,
      links: [],
      title: f.rows.get("document")!.title,
      visibility: "workspace",
      source_language: "en",
      previous_path: path,
      previous_hash: sha(before),
    },
  });
  assert.equal(assertSleepDocumentAllowed(f.storage, f.context, effect), false);
  f.controller.withApplyPermit(s.id, p.id, () => {
    hasCode(
      () =>
        assertSleepDocumentAllowed(f.storage, f.context, {
          ...effect,
          final_text: "different",
        }),
      "PERMISSION_DENIED",
    );
    assert.equal(
      assertSleepDocumentAllowed(f.storage, f.context, effect),
      true,
    );
    assert.equal(sleepDelegationRef(), `sleep:${s.id}:${p.id}`);
    hasCode(
      () => assertSleepDocumentAllowed(f.storage, f.context, effect),
      "PERMISSION_DENIED",
    );
    f.storage.run(
      "INSERT INTO intents VALUES(?,?)",
      effect.request_id,
      JSON.stringify({
        payload: effect,
        epoch: f.context.epoch,
        status: "confirmed",
      }),
    );
    const registration = CommitSchema.parse({
      request_id: effect.request_id + ":document",
      reason: "Register verified document",
      source_handles: ["trusted-native-source"],
      guards: [],
      ops: [
        {
          op: "commit_document",
          client_ref: "document",
          source_handle: "trusted-native-source",
          effect_request_id: effect.request_id,
        },
      ],
    });
    f.setNow(s.deadline_at);
    f.controller.pause(s.id, "Deadline", true);
    assert.equal(f.controller.status(s.id)!.status, "blocked");
    assert.equal(
      assertSleepMutationAllowed(f.storage, f.context, registration),
      true,
    );
    hasCode(
      () => assertSleepMutationAllowed(f.storage, f.context, f.request()),
      "PERMISSION_DENIED",
    );
  });
  const final = f.controller.settleDocument(s.id, p.id, [
    { id: "document", revision: 2 },
  ]);
  assert.equal(final.proposals[0].status, "applied");
  assert.equal(final.improvements, 1);
  f.db.close();
});
test("A future access restriction hides stored Sleep analysis and pending checks", () => {
  const f = fixture(),
    s = f.start();
  f.analyze(s.id);
  f.rows.get("evidence")!.visibility = "restricted";
  hasCode(() => f.controller.status(s.id), "REFERENCE_NOT_FOUND");
  hasCode(() => f.start(), "REFERENCE_NOT_FOUND");
  assert.deepEqual(f.controller.pendingChecks(), []);
  f.db.close();
});
test("Stream admission receives actual resolved model and deadline refusal has zero native delegates", async () => {
  let native = 0,
    observed: unknown;
  const m = {
    api: "openai-responses",
    provider: model.provider,
    id: model.id,
  } as Parameters<Parameters<typeof wrapSleepStream>[0]>[0];
  const transcript = { messages: [] } as unknown as Parameters<
    Parameters<typeof wrapSleepStream>[0]
  >[1];
  const stream = wrapSleepStream(
    () => {
      native++;
      return createAssistantMessageEventStream();
    },
    async (actual) => {
      observed = actual;
      throw new CoreError("SLEEP_BUDGET_EXHAUSTED", "Deadline reached");
    },
  );
  assert.equal(
    (await (await stream(m, transcript)).result()).stopReason,
    "aborted",
  );
  assert.equal(observed, m);
  assert.equal(native, 0);
});

test("Sleep actions reject irrelevant selectors before returning any active history", () => {
  assert.equal(
    SleepActionSchema.safeParse({ action: "start", run_id: "old" }).success,
    false,
  );
  assert.equal(
    SleepActionSchema.safeParse({ action: "status", activity_id: "other" })
      .success,
    false,
  );
});

test("A proven dead runtime before atomic native admission can reject and continue without replay", () => {
  const f = fixture();
  f.rows.set(
    "document",
    row("document", "entity", { document: { state: "active" } }),
  );
  f.rows.set(
    "activity",
    row("activity", "activity", {
      status: "active",
      contract: { document_refs: [{ id: "document" }] },
    }),
  );
  const s = f.controller.start("activity", model);
  f.analyze(s.id);
  f.controller.read(s.id, { id: "document" });
  const p = f.controller.propose(s.id, {
    reason: "Reversible draft",
    expected_benefit: "Clearer organization",
    limits: "Keep earlier version",
    premises: [{ id: "document", revision: 1 }],
    request: null,
    document_change: {
      ref: { id: "document", revision: 1 },
      action: "update",
      content: "Draft",
    },
    future_check: {
      trigger: "Next reading",
      expected_observation: "Improved discovery",
    },
  });
  f.controller.validate(s.id, p.id);
  f.controller.beginApply(s.id, p.id);
  const live = new SleepV2(
    f.storage,
    { ...f.context, runtime_id: "runtime-B" },
    { ...f.bind, runtimeState: () => "unknown" },
  );
  hasCode(() => live.reconcile(s.id), "RECONCILIATION_REQUIRED");
  const dead = new SleepV2(
    f.storage,
    { ...f.context, runtime_id: "runtime-B" },
    f.bind,
  );
  const recovered = dead.reconcile(s.id);
  assert.equal(recovered.proposals[0].status, "rejected");
  assert.equal(recovered.improvements, 0);
  assert.equal(dead.resume(s.id, model).phase, "analyze");
  f.db.close();
});

test("Shutdown drains queued launch admission without constructing a later SDK session", async () => {
  const f = fixture();
  let registered:
    | ((p: Record<string, unknown>, c: ExtensionContext) => unknown)
    | undefined;
  let calls = 0,
    sessions = 0,
    release!: () => void;
  const gate = new Promise<void>((resolve) => {
    release = resolve;
  });
  const ctx = {
    cwd: f.home,
    model: { api: "openai-responses", provider: model.provider, id: model.id },
    thinkingLevel: "medium",
  } as ExtensionContext;
  const core = {
    storage: f.storage,
    context: f.context,
    read: (id: string) => ({ data: f.read({ id }) }),
  } as unknown as Core;
  const pi = {
    sendMessage: () => {},
    registerCommand: () => {},
  } as unknown as ExtensionAPI;
  const runtime = registerSleep(
    (name, _description, _schema, action) => {
      if (name === "zara_sleep") registered = action;
    },
    pi,
    {
      core: () => core,
      candidates: () => [...f.rows.values()],
      withOperation: async (_kind, callback) => {
        calls++;
        if (calls === 3) await gate;
        return callback();
      },
      createSession: async () => {
        sessions++;
        throw new Error("No SDK session may launch after shutdown starts.");
      },
    },
  );
  const starting = registered!({ action: "start" }, ctx);
  for (let i = 0; i < 50 && calls < 3; i++)
    await new Promise<void>((resolve) => setImmediate(resolve));
  assert.equal(calls, 3);
  const closing = runtime.shutdown();
  release();
  const [result] = (await Promise.all([starting, closing])) as [
    { started: boolean },
    unknown,
  ];
  assert.equal(result.started, false);
  assert.equal(sessions, 0);
  assert.equal(runtime.activeCount(), 0);
  runtime.open();
  assert.equal(f.controller.status()!.status, "paused");
  await runtime.shutdown();
  f.db.close();
});

test("Paused Activity refuses new delegated admission while ordinary reads remain available", () => {
  const f = fixture();
  f.rows.set(
    "activity",
    row("activity", "activity", {
      status: "active",
      contract: { document_refs: [] },
    }),
  );
  const s = f.controller.start("activity", model);
  f.analyze(s.id);
  const p = f.propose(s.id);
  f.controller.validate(s.id, p.id);
  f.rows.get("activity")!.data.status = "paused";
  hasCode(() => f.controller.beginApply(s.id, p.id), "INVALID_TRANSITION");
  assert.equal(f.controller.read(s.id, { id: "note" }).id, "note");
  f.rows.get("activity")!.data.status = "active";
  assert.equal(f.controller.beginApply(s.id, p.id).status, "applying");
  f.db.close();
});

test("Deadline aborts immediately and failed state cleanup cannot become an unhandled host rejection", async () => {
  const f = fixture(),
    s = f.start();
  s.deadline_at = Date.now() + 50;
  f.storage.run(
    "UPDATE sleep_cycles SET json=? WHERE id=?",
    JSON.stringify(s),
    s.id,
  );
  let registered:
    | ((p: Record<string, unknown>, ctx: ExtensionContext) => unknown)
    | undefined;
  let aborts = 0,
    release: (() => void) | undefined;
  const unhandled: unknown[] = [];
  const listener = (error: unknown) => unhandled.push(error);
  process.on("unhandledRejection", listener);
  const ctx = {
    cwd: f.home,
    model: { api: "openai-responses", provider: model.provider, id: model.id },
    thinkingLevel: "medium",
  } as ExtensionContext;
  const core = {
    storage: f.storage,
    context: f.context,
    read: (id: string) => ({ data: f.read({ id }) }),
  } as unknown as Core;
  const runtime = registerSleep(
    (name, _d, _s, action) => {
      if (name === "zara_sleep") registered = action;
    },
    {
      sendMessage: () => {},
      registerCommand: () => {},
    } as unknown as ExtensionAPI,
    {
      core: () => core,
      candidates: () => [...f.rows.values()],
      withOperation: async (kind, callback) => {
        if (kind === "settle")
          throw new CoreError(
            "STORE_UNAVAILABLE",
            "Synthetic store closed before cleanup.",
          );
        return callback();
      },
      createSession: async (options) => ({
        session: {
          model: ctx.model,
          thinkingLevel: "medium",
          agent: {
            streamFunction: () => createAssistantMessageEventStream(),
            toolExecution: "sequential",
          },
          prompt: async () =>
            new Promise<void>((resolve) => {
              release = resolve;
            }),
          abort: async () => {
            aborts++;
            release?.();
          },
          dispose: () => {},
        } as never,
        extensionsResult: options!.resourceLoader!.getExtensions(),
      }),
    },
  );
  try {
    await registered!({ action: "resume", run_id: s.id }, ctx);
    for (let i = 0; i < 100 && runtime.activeCount(); i++)
      await new Promise<void>((resolve) => setTimeout(resolve, 5));
    await runtime.shutdown();
    await new Promise<void>((resolve) => setImmediate(resolve));
    assert.equal(runtime.activeCount(), 0);
    assert(aborts >= 1);
    assert.deepEqual(unhandled, []);
  } finally {
    process.off("unhandledRejection", listener);
    f.db.close();
  }
});

test("A dead precommit pure-Core application rejects without repeating while a live owner remains blocked", () => {
  const f = fixture(),
    s = f.start();
  f.analyze(s.id);
  const p = f.propose(s.id);
  f.controller.validate(s.id, p.id);
  f.controller.beginApply(s.id, p.id);
  hasCode(() => f.controller.reconcile(s.id), "RECONCILIATION_REQUIRED");
  const newer = new SleepV2(
    f.storage,
    { ...f.context, runtime_id: "runtime-B" },
    f.bind,
  );
  const recovered = newer.reconcile(s.id);
  assert.equal(recovered.proposals[0].status, "rejected");
  assert.equal(recovered.improvements, 0);
  assert.equal(newer.resume(s.id, model).phase, "analyze");
  f.db.close();
});

function finishApplied(
  f: ReturnType<typeof fixture>,
  activityId: string | null = null,
) {
  const s = f.controller.start(activityId, model);
  f.analyze(s.id);
  const p = f.propose(s.id);
  f.controller.validate(s.id, p.id);
  f.controller.beginApply(s.id, p.id);
  f.controller.settleApply(
    s.id,
    p.id,
    committedReceipt(f, f.request().request_id),
  );
  f.controller.finish(
    s.id,
    "applied_unverified",
    "A reversible change was applied; usefulness remains unknown.",
  );
  return { s, p };
}
test("Inference and generated artifacts cannot close a future check; exact direct owner feedback stays reported", () => {
  const f = fixture(),
    { s, p } = finishApplied(f);
  f.setNow(f.getNow() + 1000);
  const time = new Date(f.getNow()).toISOString();
  f.rows.set("inferred", {
    ...row("inferred", "knowledge", { basis: "inference", state: "tentative" }),
    created_at: time,
    updated_at: time,
  });
  f.rows.set("generated", {
    ...row("generated", "evidence", {
      source_kind: "generated_artifact",
      availability: "retained",
      retained_excerpt: "It improved the process.",
      captured_at: time,
      provenance: { transport: "model-generated" },
    }),
    created_at: time,
    updated_at: time,
  });
  for (const id of ["inferred", "generated"])
    hasCode(
      () =>
        f.controller.observeCheck(s.id, p.id, {
          refs: [{ id, revision: 1 }],
          verdict: "helped",
          summary: "Model claims it helped.",
        }),
      "SOURCE_MISSING",
    );
  const uncertain = f.controller.observeCheck(s.id, p.id, {
    refs: [{ id: "inferred", revision: 1 }],
    verdict: "unknown",
    summary: "A hypothesis needs actual later observations.",
  });
  assert.equal(
    uncertain.proposals[0].check_observation!.evidence_basis,
    "unverified",
  );
  assert.equal(f.controller.pendingChecks().length, 1);
  f.rows.set("owner-report", {
    ...row("owner-report", "evidence", {
      source_kind: "direct_statement",
      availability: "retained",
      retained_excerpt: "I used the new ordering and found the item faster.",
      captured_at: time,
      provenance: {
        transport: "interactive",
        owner_channel_eligible: true,
        input_integrity: "trusted_first_untransformed",
      },
    }),
    created_at: time,
    updated_at: time,
  });
  const reported = f.controller.observeCheck(s.id, p.id, {
    refs: [{ id: "owner-report", revision: 1 }],
    verdict: "helped",
    summary: "The owner reports easier discovery, without a causal claim.",
  });
  assert.equal(
    reported.proposals[0].check_observation!.evidence_basis,
    "reported",
  );
  assert.equal(f.controller.pendingChecks().length, 0);
  f.db.close();
});
test("Tightened premise access permits only metadata cancellation and a new cycle, never a retained summary leak", () => {
  const f = fixture(),
    s = f.start();
  f.analyze(s.id);
  f.controller.pause(s.id, "Await future grounds.");
  f.rows.get("evidence")!.visibility = "restricted";
  hasCode(() => f.controller.status(s.id), "REFERENCE_NOT_FOUND");
  const foreign = new SleepV2(
    f.storage,
    { ...f.context, runtime_id: "runtime-B" },
    { ...f.bind, runtimeState: () => "unknown" },
  );
  hasCode(() => foreign.cancelMetadata(s.id), "STORE_BUSY");
  const cancelled = f.controller.cancelMetadata(s.id);
  assert.deepEqual(cancelled, {
    id: s.id,
    status: "cancelled",
    content_withheld: true,
  });
  assert(!JSON.stringify(cancelled).includes("observations"));
  assert(!JSON.stringify(cancelled).includes("weekdays"));
  const next = f.start();
  assert.notEqual(next.id, s.id);
  assert.equal(next.status, "running");
  f.db.close();
});
test("Full trusted scope upgrade may cancel metadata, but cannot dismiss an unresolved native application", () => {
  const f = fixture(),
    s = f.start();
  f.analyze(s.id);
  f.rows.get("evidence")!.visibility = "restricted";
  const admin = new SleepV2(
    f.storage,
    {
      ...f.context,
      scopes: ["restricted:read", "restricted:write"],
      runtime_id: "runtime-B",
    },
    f.bind,
  );
  assert.deepEqual(admin.cancelMetadata(s.id), {
    id: s.id,
    status: "cancelled",
    content_withheld: true,
  });
  f.rows.get("evidence")!.visibility = "workspace";
  const next = f.start();
  f.analyze(next.id);
  const p = f.propose(next.id);
  f.controller.validate(next.id, p.id);
  f.controller.beginApply(next.id, p.id);
  const state = f.controller.status(next.id)!;
  state.proposals[0].request = null;
  state.proposals[0].document_change = {
    ref: { id: "note", revision: 1 },
    action: "update",
    content: "A pending actual document operation.",
  };
  state.proposals[0].native_request_id = "unknown-native";
  state.proposals[0].status = "unknown";
  state.status = "blocked";
  f.storage.run(
    "UPDATE sleep_cycles SET json=? WHERE id=?",
    JSON.stringify(state),
    state.id,
  );
  hasCode(() => admin.cancelMetadata(next.id), "RECONCILIATION_REQUIRED");
  assert.equal(f.controller.status(next.id)!.proposals[0].status, "unknown");
  f.db.close();
});
test("Pending check hints are small, recent, Activity-scoped and never initialize readonly storage", () => {
  const f = fixture();
  const global = finishApplied(f);
  f.setNow(f.getNow() + 1000);
  f.rows.set(
    "activity-A",
    row("activity-A", "activity", { status: "active", contract: {} }),
  );
  const local = finishApplied(f, "activity-A");
  const core = {
    storage: f.storage,
    context: f.context,
    read: (id: string) => ({ data: f.read({ id }) }),
  } as unknown as Core;
  const runtime = registerSleep(
    () => {},
    {
      sendMessage: () => {},
      registerCommand: () => {},
    } as unknown as ExtensionAPI,
    {
      core: () => core,
      withOperation: async (_kind, callback) => callback(),
      candidates: () => [...f.rows.values()],
    },
  );
  const a = runtime.pendingCheckHints("activity-A");
  assert.equal(a.length, 2);
  assert.equal(a[0].run_id, local.s.id);
  assert.deepEqual(Object.keys(a[0]).sort(), [
    "must_read_status",
    "proposal_id",
    "run_id",
  ]);
  assert.deepEqual(
    runtime.pendingCheckHints("activity-B").map((hint) => hint.run_id),
    [global.s.id],
  );
  let touched = 0;
  const readonlyCore = {
    ...core,
    storage: {
      ...f.storage,
      readonly: true,
      exec: () => {
        touched++;
        throw new Error("Must not initialize readonly state.");
      },
    },
  } as unknown as Core;
  const readonlyRuntime = registerSleep(
    () => {},
    {
      sendMessage: () => {},
      registerCommand: () => {},
    } as unknown as ExtensionAPI,
    {
      core: () => readonlyCore,
      withOperation: async (_kind, callback) => callback(),
    },
  );
  assert.deepEqual(readonlyRuntime.pendingCheckHints(), []);
  assert.equal(touched, 0);
  f.db.close();
});
test("Sleep source reads reach a retained Unicode tail and forward page locator without generic tools", () => {
  const f = fixture(),
    s = f.start();
  const text = "x".repeat(8000) + "\u{1f600}TAIL-OBSERVATION";
  f.rows.set(
    "long",
    row("long", "evidence", {
      retained_excerpt: text,
      availability: "retained",
    }),
  );
  const calls: unknown[] = [];
  const core = {
    read: (
      id: string,
      revision?: number,
      range?: { start: number; length: number },
      locator?: string,
      version?: number,
    ) => {
      calls.push({ id, revision, range, locator, version });
      const value = f.read({ id });
      return {
        data: range
          ? {
              ref: { id, revision: 1 },
              text: Array.from(text)
                .slice(range.start, range.start + range.length)
                .join(""),
            }
          : value,
      };
    },
  } as unknown as Core;
  const tail = readSleepSource(core, f.controller, s.id, {
    ref: { id: "long", revision: 1 },
    range: { start: 8000, length: 100 },
    locator: "chapter:2",
  }) as { text: string };
  assert.equal(tail.text, "\u{1f600}TAIL-OBSERVATION");
  assert.equal((calls.at(-1) as { locator: string }).locator, "chapter:2");
  assert(f.controller.status(s.id)!.read_refs.some((r) => r.id === "long"));
  f.db.close();
});

import test from "node:test";
import assert from "node:assert/strict";
import { randomUUID } from "node:crypto";
import { mkdirSync, mkdtempSync, readFileSync, writeFileSync } from "node:fs";
import { promises as fs } from "node:fs";
import { join } from "node:path";
import { tmpdir } from "node:os";
import { DatabaseSync } from "node:sqlite";
import { createWriteTool } from "@earendil-works/pi-coding-agent";
import type {
  ExtensionAPI,
  ExtensionContext,
  ExtensionToolContext,
} from "@earendil-works/pi-coding-agent";
import extension from "../src/extension/index.ts";
import { Coordination, readControl } from "../src/storage/index.ts";

type Hook = (
  event: Record<string, unknown>,
  context: ExtensionContext,
) => unknown | Promise<unknown>;
type Tool = Parameters<ExtensionAPI["registerTool"]>[0];
type Adapter = {
  ctx: ExtensionToolContext;
  warnings: string[];
  messages: Parameters<ExtensionAPI["sendMessage"]>[0][];
  emit: (name: string, event?: Record<string, unknown>) => Promise<unknown>;
  call: (
    name: string,
    input: Record<string, unknown>,
  ) => Promise<Record<string, unknown>>;
  snapshot: () => Promise<{ data: Record<string, unknown>; runtime: string }>;
  prepare: (
    id: string,
    path: string,
    content?: string,
  ) => Promise<{ path: string; content: string }>;
};
const tick = () => new Promise<void>((resolve) => setTimeout(resolve, 15));
function deferred<T>() {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>((done) => {
    resolve = done;
  });
  return { promise, resolve };
}
function fixture() {
  const base = mkdtempSync(
    join(
      process.env.ZARATUSTRA_TEST_ROOT ?? tmpdir(),
      "zara-native-concurrent-",
    ),
  );
  const home = join(base, "home"),
    output = join(base, "output"),
    cwd = join(base, "project"),
    agent = join(base, "agent"),
    backups = join(base, "backups");
  for (const path of [output, cwd, agent, backups]) mkdirSync(path);
  const values: NodeJS.ProcessEnv = {
    PI_CODING_AGENT_DIR: agent,
    ZARATUSTRA_HOME: home,
    ZARATUSTRA_OUTPUT_ROOT: output,
    ZARATUSTRA_BACKUP_ROOT: backups,
    ZARATUSTRA_IMPORT_ROOTS: JSON.stringify([cwd]),
    ZARATUSTRA_SCOPES: JSON.stringify(["restricted:read", "restricted:write"]),
    ZARATUSTRA_TEST_CONTROLLER: "mechanical-native-concurrency",
  };
  const previous = Object.fromEntries(
    Object.keys(values).map((key) => [key, process.env[key]]),
  );
  Object.assign(process.env, values);
  const adapters: Adapter[] = [];
  function adapter(
    confirm: () => Promise<boolean> = async () => true,
    options: { mode?: "sdk" | "tui"; choice?: string; custom?: string } = {},
  ): Adapter {
    const hooks = new Map<string, Hook>(),
      tools = new Map<string, Tool>(),
      warnings: string[] = [];
    const messages: Parameters<ExtensionAPI["sendMessage"]>[0][] = [];
    const ctx = {
      cwd,
      mode: options.mode ?? "sdk",
      hasUI: true,
      model: { provider: "mechanical", id: "no-provider-dispatch" },
      sessionManager: { getSessionId: () => "native-test-" + randomUUID() },
      isProjectTrusted: () => true,
      abort() {},
      ui: {
        confirm,
        async select() {
          return options.choice;
        },
        async input() {
          return options.custom;
        },
        notify(message: string) {
          warnings.push(message);
        },
      },
    } as unknown as ExtensionToolContext;
    extension({
      on(name: string, handler: Hook) {
        hooks.set(name, handler);
      },
      registerTool(tool: Tool) {
        tools.set(tool.name, tool);
      },
      registerCommand() {},
      sendMessage(message: Parameters<ExtensionAPI["sendMessage"]>[0]) {
        messages.push(message);
      },
      getThinkingLevel: () => "off",
    } as unknown as ExtensionAPI);
    const emit = async (name: string, event: Record<string, unknown> = {}) =>
      hooks.get(name)?.(event, ctx);
    const call = async (name: string, input: Record<string, unknown>) => {
      const result = await tools
        .get(name)!
        .execute("custom-" + randomUUID(), input, undefined, undefined, ctx);
      return result.details as Record<string, unknown>;
    };
    const snapshot = async () => {
      const result = (await emit("context", { messages: [] })) as {
        messages: { content: string; details: { runtime_id: string } }[];
      };
      return {
        data: JSON.parse(result.messages[0].content) as Record<string, unknown>,
        runtime: result.messages[0].details.runtime_id,
      };
    };
    const prepare = async (id: string, path: string, content = id) => {
      const preview = await call("zara_file_preview", {
        request_id: id,
        tool: "write",
        arguments: { path, content },
        independent_basis: "Independent mechanical native concurrency fixture",
        consequence: "Create exact fixture bytes",
        alternatives: "Leave fixture absent",
      });
      assert.equal(preview.code, undefined, JSON.stringify(preview));
      const confirmed = await call("zara_confirm", {
        preview_ref: preview.request_id,
      });
      assert.equal(confirmed.code, undefined, JSON.stringify(confirmed));
      return { path, content };
    };
    const value = { ctx, emit, call, snapshot, prepare, warnings, messages };
    adapters.push(value);
    return value;
  }
  return {
    home,
    output,
    cwd,
    adapter,
    async close() {
      for (const a of adapters) {
        await a.emit("agent_settled");
        await a.emit("session_shutdown");
      }
      for (const [key, value] of Object.entries(previous)) {
        if (value === undefined) delete process.env[key];
        else process.env[key] = value;
      }
    },
  };
}

test("TUI proposal goes to chat before a short question; custom answer never grants permission", async () => {
  const f = fixture();
  let confirmations = 0;
  const a = f.adapter(
    async () => {
      confirmations++;
      return true;
    },
    { mode: "tui", choice: "Свой ответ…", custom: "Поменяй только заголовок" },
  );
  try {
    await a.emit("session_start");
    const path = join(f.output, "not-created.md");
    const p = await a.call("zara_file_preview", {
      request_id: "chat-first-custom",
      tool: "write",
      arguments: { path, content: "FULL CONTENT MARKER" },
      independent_basis: "Mechanical independent fixture",
      consequence: "Создать только эту заметку.",
      alternatives: "Не создавать.",
    });
    assert.equal(p.code, undefined);
    const request = { preview_ref: p.request_id };
    const queued = await a.call("zara_confirm", request);
    assert.equal(queued.status, "review_in_chat");
    assert.equal(queued.permission_granted, false);
    assert.equal(a.messages.length, 1);
    assert.ok(String(a.messages[0].content).includes("FULL CONTENT MARKER"));
    assert.equal(
      (await a.call("zara_confirm", request)).status,
      "review_in_chat",
    );
    assert.equal(
      a.messages.length,
      1,
      "same-turn calls must not duplicate messages or open questions",
    );
    assert.equal(confirmations, 0);
    await a.emit("message_end", {
      message: { role: "custom", ...a.messages[0] },
    });
    const answer = await a.call("zara_confirm", request);
    assert.equal(answer.requested_changes, "Поменяй только заголовок");
    assert.equal(answer.permission_granted, false);
    assert.equal(confirmations, 0);
    const blocked = (await a.emit("tool_call", {
      toolName: "write",
      toolCallId: "not-approved",
      input: { path, content: "FULL CONTENT MARKER" },
    })) as { block?: boolean };
    assert.equal(blocked.block, true);
    assert.equal(
      (await a.call("zara_confirm", request)).code,
      "APPROVAL_STALE",
    );
    assert.equal(
      a.messages.length,
      1,
      "a declined proposal must not be re-presented",
    );
    const question = await a.call("zara_ask", {
      question: "Что изменить?",
      choices: ["Заголовок", "Текст"],
    });
    assert.equal(question.kind, "custom");
    assert.equal(question.answer, "Поменяй только заголовок");
    assert.equal(question.permission_granted, false);
  } finally {
    await f.close();
  }
});

test("TUI choosing Confirm after chat still requires the actual native affirmative answer", async () => {
  const f = fixture();
  let confirmations = 0;
  const a = f.adapter(
    async () => {
      confirmations++;
      return false;
    },
    { mode: "tui", choice: "Подтвердить" },
  );
  try {
    await a.emit("session_start");
    const p = await a.call("zara_file_preview", {
      request_id: "chat-native-no",
      tool: "write",
      arguments: { path: join(f.output, "declined.md"), content: "declined" },
      independent_basis: "Independent fixture",
      consequence: "Создать заметку.",
      alternatives: "Не создавать.",
    });
    const request = { preview_ref: p.request_id };
    assert.equal(
      (await a.call("zara_confirm", request)).status,
      "review_in_chat",
    );
    await a.emit("message_end", {
      message: { role: "custom", ...a.messages[0] },
    });
    const answer = await a.call("zara_confirm", request);
    assert.equal(answer.code, undefined);
    assert.equal(confirmations, 1);
    assert.equal(
      (await a.call("zara_confirm", request)).code,
      "APPROVAL_STALE",
    );
  } finally {
    await f.close();
  }
});

test("TUI visible chat plus actual native Yes approves only that exact proposal without executing it", async () => {
  const f = fixture();
  let confirmations = 0;
  const a = f.adapter(
    async () => {
      confirmations++;
      return true;
    },
    { mode: "tui", choice: "Подтвердить" },
  );
  try {
    await a.emit("session_start");
    const path = join(f.output, "approved-not-executed.md");
    const preview = await a.call("zara_file_preview", {
      request_id: "chat-native-yes",
      tool: "write",
      arguments: { path, content: "exact bytes" },
      independent_basis: "Independent mechanical fixture",
      consequence: "Создать заметку.",
      alternatives: "Не создавать.",
    });
    const request = { preview_ref: preview.request_id };
    assert.equal(
      (await a.call("zara_confirm", request)).status,
      "review_in_chat",
    );
    await a.emit("message_end", {
      message: { role: "custom", ...a.messages[0] },
    });
    const answer = await a.call("zara_confirm", request);
    assert.equal(answer.code, undefined);
    assert.equal(answer.status, "approved-transient");
    assert.equal((answer.answer as { affirmative: boolean }).affirmative, true);
    assert.equal(answer.request_id, preview.request_id);
    assert.equal(confirmations, 1);
    assert.throws(() => readFileSync(path), { code: "ENOENT" });
  } finally {
    await f.close();
  }
});

test("real Pi native writes use shared path reservations; another startup preserves a live dispatch", async () => {
  const f = fixture(),
    a = f.adapter(),
    b = f.adapter();
  try {
    await a.emit("session_start");
    const firstRuntime = (await a.snapshot()).runtime;
    const path = join(f.output, "same.md"),
      args = await a.prepare("native-first", path);
    assert.equal(
      await a.emit("tool_call", {
        toolName: "write",
        toolCallId: "native-call-first",
        input: args,
      }),
      undefined,
    );
    await b.emit("session_start");
    assert.notEqual((await b.snapshot()).runtime, firstRuntime);
    const db = new DatabaseSync(join(f.home, "zara.sqlite"), {
      readOnly: true,
    });
    try {
      const intent = JSON.parse(
        String(
          db
            .prepare("SELECT json FROM intents WHERE request_id='native-first'")
            .get()!.json,
        ),
      );
      assert.equal(
        intent.status,
        "requested",
        "startup must not declare another live runtime's native effect interrupted",
      );
    } finally {
      db.close();
    }
    assert.equal(
      (await b.call("zara_file_inspect", { request_id: "native-first" })).code,
      "STORE_BUSY",
    );
    const conflicting = await b.prepare("native-conflict", path);
    const blocked = (await b.emit("tool_call", {
      toolName: "write",
      toolCallId: "native-call-conflict",
      input: conflicting,
    })) as { block: boolean; reason: string };
    assert.equal(blocked.block, true);
    assert.equal(JSON.parse(blocked.reason).code, "STORE_BUSY");
    const other = await b.prepare(
      "native-disjoint",
      join(f.output, "other.md"),
    );
    assert.equal(
      await b.emit("tool_call", {
        toolName: "write",
        toolCallId: "native-call-disjoint",
        input: other,
      }),
      undefined,
    );
    const native = createWriteTool(f.cwd);
    const otherResult = await native.execute("native-call-disjoint", other);
    await b.emit("tool_result", {
      toolName: "write",
      toolCallId: "native-call-disjoint",
      content: otherResult.content,
      isError: false,
    });
    const result = await native.execute("native-call-first", args);
    await a.emit("tool_result", {
      toolName: "write",
      toolCallId: "native-call-first",
      content: result.content,
      isError: false,
    });
    assert.equal(readFileSync(path, "utf8"), "native-first");
    const control = new DatabaseSync(join(f.home, "coordination.sqlite"), {
      readOnly: true,
    });
    try {
      assert.equal(
        control
          .prepare("SELECT count(*) AS n FROM resource_reservations")
          .get()!.n,
        0,
      );
    } finally {
      control.close();
    }
    await a.emit("session_start");
    assert.notEqual(
      (await a.snapshot()).runtime,
      firstRuntime,
      "reopen must register a fresh runtime OS lease",
    );
    assert.equal(a.warnings.length + b.warnings.length, 0);
  } finally {
    await f.close();
  }
});

test("native confirmation does not hold the global phase and shutdown retains its runtime lease until the callback drains", async () => {
  const f = fixture(),
    answer = deferred<boolean>(),
    shown = deferred<void>();
  const a = f.adapter(() => {
      shown.resolve();
      return answer.promise;
    }),
    b = f.adapter();
  let shutdown: Promise<unknown> | undefined;
  try {
    await Promise.all([a.emit("session_start"), b.emit("session_start")]);
    const runtime = (await a.snapshot()).runtime;
    const preview = await a.call("zara_file_preview", {
      request_id: "delayed-dialog",
      tool: "write",
      arguments: { path: join(f.output, "dialog.md"), content: "dialog" },
      independent_basis: "Independent mechanical native dialog fixture",
      consequence: "Create fixture",
      alternatives: "Leave absent",
    });
    const confirmation = a.call("zara_confirm", {
      preview_ref: preview.request_id,
    });
    await shown.promise;
    assert.equal(
      (await b.call("zara_map", {})).code,
      undefined,
      "peer reads proceed while another dialog is pending",
    );
    let stopped = false;
    shutdown = a.emit("session_shutdown").then(() => {
      stopped = true;
    });
    await tick();
    assert.equal(stopped, false);
    const lease = new DatabaseSync(
      join(f.home, "runtimes", runtime + ".sqlite"),
    );
    try {
      assert.throws(() => lease.exec("BEGIN IMMEDIATE"), /locked|busy/i);
    } finally {
      lease.close();
    }
    answer.resolve(true);
    assert.equal((await confirmation).code, undefined);
    await shutdown;
    assert.equal(stopped, true);
  } finally {
    answer.resolve(false);
    await shutdown;
    await f.close();
  }
});

test("Pi Core phases wait asynchronously under contention and dead native attempts inspect without replay", async () => {
  const f = fixture(),
    a = f.adapter(),
    b = f.adapter();
  try {
    await Promise.all([a.emit("session_start"), b.emit("session_start")]);
    const lock = new DatabaseSync(join(f.home, "coordination.sqlite"));
    lock.exec("BEGIN IMMEDIATE");
    let completed = false;
    const read = b.call("zara_map", {}).then((result) => {
      completed = true;
      return result;
    });
    await tick();
    assert.equal(completed, false);
    lock.exec("ROLLBACK");
    lock.close();
    assert.equal((await read).code, undefined);
    const args = await a.prepare(
      "native-unknown",
      join(f.output, "unknown.md"),
    );
    await a.emit("tool_call", {
      toolName: "write",
      toolCallId: "native-call-unknown",
      input: args,
    });
    await createWriteTool(f.cwd).execute("native-call-unknown", args);
    await a.emit("agent_settled");
    await a.emit("session_shutdown");
    const inspected = await b.call("zara_file_inspect", {
      request_id: "native-unknown",
    });
    assert.equal(inspected.status, "confirmed", JSON.stringify(inspected));
    assert.equal(readFileSync(args.path, "utf8"), "native-unknown");
  } finally {
    await f.close();
  }
});

test("matching unchanged bytes cannot release a reservation while the original native write still awaits", async () => {
  const f = fixture(),
    a = f.adapter(),
    b = f.adapter();
  const begun = deferred<void>(),
    resume = deferred<void>();
  let writing: Promise<unknown> | undefined;
  try {
    await Promise.all([a.emit("session_start"), b.emit("session_start")]);
    const path = join(f.output, "unchanged.md");
    writeFileSync(path, "unchanged");
    const args = await a.prepare("native-delayed-unchanged", path, "unchanged");
    const replacement = await b.prepare(
      "native-after-delayed",
      path,
      "replacement",
    );
    await a.emit("tool_call", {
      toolName: "write",
      toolCallId: "native-call-delayed",
      input: args,
    });
    writing = createWriteTool(f.cwd, {
      operations: {
        mkdir: async () => {},
        writeFile: async (target, content) => {
          begun.resolve();
          await resume.promise;
          await fs.writeFile(target, content);
        },
      },
    }).execute("native-call-delayed", args);
    await begun.promise;
    assert.equal(
      (
        await a.call("zara_file_inspect", {
          request_id: "native-delayed-unchanged",
        })
      ).code,
      "WORK_IN_USE",
    );
    let attempted = false;
    const peerCall = b
      .emit("tool_call", {
        toolName: "write",
        toolCallId: "native-call-after-delayed",
        input: replacement,
      })
      .then((result) => {
        attempted = true;
        return result;
      });
    await tick();
    assert.equal(
      attempted,
      false,
      "native Pi's same-path queue waits outside the global Core phase",
    );
    resume.resolve();
    await writing;
    const blocked = (await peerCall) as { block: boolean; reason: string };
    assert.equal(blocked.block, true);
    assert.equal(
      JSON.parse(blocked.reason).code,
      "STORE_BUSY",
      "durable reservation remains held after native IO until its callback settles",
    );
    await a.emit("tool_result", {
      toolName: "write",
      toolCallId: "native-call-delayed",
      content: [],
      isError: false,
    });
    assert.equal(
      await b.emit("tool_call", {
        toolName: "write",
        toolCallId: "native-call-after-settle",
        input: replacement,
      }),
      undefined,
    );
    const result = await createWriteTool(f.cwd).execute(
      "native-call-after-settle",
      replacement,
    );
    await b.emit("tool_result", {
      toolName: "write",
      toolCallId: "native-call-after-settle",
      content: result.content,
      isError: false,
    });
    assert.equal(readFileSync(path, "utf8"), "replacement");
  } finally {
    resume.resolve();
    await writing;
    await f.close();
  }
});

test("an aborted queued native hook does not consume approval or create a durable intent", async () => {
  const f = fixture(),
    a = f.adapter();
  let lock: DatabaseSync | undefined;
  try {
    await a.emit("session_start");
    const args = await a.prepare(
      "native-cancelled-admission",
      join(f.output, "cancelled.md"),
    );
    const controller = new AbortController();
    a.ctx.signal = controller.signal;
    lock = new DatabaseSync(join(f.home, "coordination.sqlite"));
    lock.exec("BEGIN IMMEDIATE");
    const admission = a.emit("tool_call", {
      toolName: "write",
      toolCallId: "native-cancelled-call",
      input: args,
    });
    await tick();
    controller.abort();
    const blocked = (await admission) as { block: boolean; reason: string };
    assert.equal(blocked.block, true);
    assert.equal(JSON.parse(blocked.reason).code, "STORE_CANCELLED");
    lock.exec("ROLLBACK");
    lock.close();
    lock = undefined;
    const db = new DatabaseSync(join(f.home, "zara.sqlite"), {
      readOnly: true,
    });
    try {
      assert.equal(
        db
          .prepare(
            "SELECT request_id FROM intents WHERE request_id='native-cancelled-admission'",
          )
          .get(),
        undefined,
      );
    } finally {
      db.close();
    }
    a.ctx.signal = undefined;
    assert.equal(
      await a.emit("tool_call", {
        toolName: "write",
        toolCallId: "native-approved-after-cancel",
        input: args,
      }),
      undefined,
    );
    const written = await createWriteTool(f.cwd).execute(
      "native-approved-after-cancel",
      args,
    );
    await a.emit("tool_result", {
      toolName: "write",
      toolCallId: "native-approved-after-cancel",
      content: written.content,
      isError: false,
    });
  } finally {
    if (lock) {
      lock.exec("ROLLBACK");
      lock.close();
    }
    await f.close();
  }
});

test("an inspected separately approved risky retry transfers a dead owner's reservation and keeps its unknown history", async () => {
  const f = fixture(),
    a = f.adapter(),
    b = f.adapter();
  try {
    await Promise.all([a.emit("session_start"), b.emit("session_start")]);
    const path = join(f.output, "retry.md"),
      initial = await a.prepare("native-retry-old", path, "old");
    await a.emit("tool_call", {
      toolName: "write",
      toolCallId: "native-retry-old-call",
      input: initial,
    });
    await assert.rejects(
      createWriteTool(f.cwd, {
        operations: {
          mkdir: async () => {},
          writeFile: async () => {
            throw new Error("mechanical write failure");
          },
        },
      }).execute("native-retry-old-call", initial),
      /mechanical write failure/,
    );
    await a.emit("tool_result", {
      toolName: "write",
      toolCallId: "native-retry-old-call",
      content: [],
      isError: true,
    });
    const args = { path, content: "retry" };
    const preview = await b.call("zara_file_preview", {
      request_id: "native-retry-new",
      tool: "write",
      arguments: args,
      independent_basis: "Independent mechanical explicit risky retry",
      consequence: "Repeat after inspected failed native write",
      alternatives: "Retain unknown attempt",
      retry_of: "native-retry-old",
      retry_risk:
        "The prior native attempt may have taken effect; repeat is a separate exact decision",
    });
    assert.equal(preview.code, undefined, JSON.stringify(preview));
    assert.equal(
      (await b.call("zara_confirm", { preview_ref: preview.request_id })).code,
      undefined,
    );
    const blocked = (await b.emit("tool_call", {
      toolName: "write",
      toolCallId: "native-retry-before-owner-close",
      input: args,
    })) as { block: boolean; reason: string };
    assert.equal(blocked.block, true);
    assert.equal(
      JSON.parse(blocked.reason).code,
      "STORE_BUSY",
      "a still-live foreign owner cannot be taken over for retry",
    );
    await a.emit("session_shutdown");
    assert.equal(
      (await b.call("zara_file_inspect", { request_id: "native-retry-old" }))
        .status,
      "unknown",
    );
    assert.equal(
      await b.emit("tool_call", {
        toolName: "write",
        toolCallId: "native-retry-after-owner-close",
        input: args,
      }),
      undefined,
    );
    const result = await createWriteTool(f.cwd).execute(
      "native-retry-after-owner-close",
      args,
    );
    await b.emit("tool_result", {
      toolName: "write",
      toolCallId: "native-retry-after-owner-close",
      content: result.content,
      isError: false,
    });
    const db = new DatabaseSync(join(f.home, "zara.sqlite"), {
      readOnly: true,
    });
    try {
      const old = JSON.parse(
        String(
          db
            .prepare(
              "SELECT json FROM intents WHERE request_id='native-retry-old'",
            )
            .get()!.json,
        ),
      );
      assert.equal(old.status, "unknown");
    } finally {
      db.close();
    }
    const coordination = new DatabaseSync(join(f.home, "coordination.sqlite"), {
      readOnly: true,
    });
    try {
      const next = JSON.parse(
        String(
          coordination
            .prepare(
              "SELECT json FROM operations WHERE operation_id='file:native-retry-new'",
            )
            .get()!.json,
        ),
      );
      assert.equal(next.metadata.retry_of, "native-retry-old");
      assert.equal(next.status, "settled");
      assert.equal(
        coordination
          .prepare("SELECT count(*) AS n FROM resource_reservations")
          .get()!.n,
        0,
      );
    } finally {
      coordination.close();
    }
    assert.equal(readFileSync(path, "utf8"), "retry");
  } finally {
    await f.close();
  }
});

test("Pi restore closes the old generation and reopens with a fresh runtime lease", async () => {
  const f = fixture(),
    a = f.adapter();
  try {
    await a.emit("session_start");
    const before = await a.snapshot();
    const backup = await a.call("zara_backup", {});
    assert.equal(backup.code, undefined, JSON.stringify(backup));
    const preview = await a.call("zara_restore_preview", {
      backup: backup.backup,
      consequence: "Restore exact mechanical fixture",
      alternatives: "Keep current generation",
    });
    assert.equal(preview.code, undefined, JSON.stringify(preview));
    const draft = preview.preview as { request_id: string };
    const confirmation = await a.call("zara_confirm", {
      preview_ref: draft.request_id,
    });
    assert.equal(confirmation.code, undefined, JSON.stringify(confirmation));
    const restored = await a.call("zara_restore", {
      preview_ref: draft.request_id,
    });
    assert.equal(restored.code, undefined, JSON.stringify(restored));
    const after = await a.snapshot();
    assert.notEqual(after.runtime, before.runtime);
    assert.notEqual(after.data.available, false, JSON.stringify(after.data));
    assert.equal((await a.call("zara_map", {})).code, undefined);
    assert.equal(a.warnings.length, 0);
  } finally {
    await f.close();
  }
});

test("a committed orphan intent is recoverable only after its original runtime OS lease is dead", async () => {
  const f = fixture(),
    a = f.adapter(),
    b = f.adapter();
  try {
    await Promise.all([a.emit("session_start"), b.emit("session_start")]);
    const args = await a.prepare("native-orphan", join(f.output, "orphan.md"));
    await a.emit("tool_call", {
      toolName: "write",
      toolCallId: "native-orphan-call",
      input: args,
    });
    // Reproduce the conservative two-database crash window: Core committed its
    // intent, coordination did not commit its reservation, and native never ran.
    const brokenCommit = new DatabaseSync(join(f.home, "coordination.sqlite"));
    try {
      brokenCommit.exec("BEGIN IMMEDIATE");
      brokenCommit
        .prepare("DELETE FROM resource_reservations WHERE operation_id=?")
        .run("file:native-orphan");
      brokenCommit
        .prepare("DELETE FROM operations WHERE operation_id=?")
        .run("file:native-orphan");
      brokenCommit.exec("COMMIT");
    } finally {
      brokenCommit.close();
    }
    assert.equal(
      (await b.call("zara_file_inspect", { request_id: "native-orphan" })).code,
      "STORE_BUSY",
    );
    await a.emit("agent_settled");
    await a.emit("session_shutdown");
    const recovered = await b.call("zara_file_inspect", {
      request_id: "native-orphan",
    });
    assert.equal(recovered.status, "unknown", JSON.stringify(recovered));
    const control = new DatabaseSync(join(f.home, "coordination.sqlite"), {
      readOnly: true,
    });
    try {
      const retained = JSON.parse(
        String(
          control
            .prepare(
              "SELECT json FROM operations WHERE operation_id='file:native-orphan'",
            )
            .get()!.json,
        ),
      );
      assert.equal(retained.status, "unknown");
      assert.equal(
        control
          .prepare(
            "SELECT count(*) AS n FROM resource_reservations WHERE operation_id='file:native-orphan'",
          )
          .get()!.n,
        1,
      );
    } finally {
      control.close();
    }
    writeFileSync(args.path, args.content);
    assert.equal(
      (await b.call("zara_file_inspect", { request_id: "native-orphan" }))
        .status,
      "confirmed",
    );
  } finally {
    await f.close();
  }
});

test("settled uncertain native outcomes keep resource barriers without holding restore in the live-operation drain", async () => {
  const f = fixture(),
    a = f.adapter(),
    b = f.adapter();
  try {
    await Promise.all([a.emit("session_start"), b.emit("session_start")]);
    const args = await a.prepare(
      "native-settled-uncertain",
      join(f.output, "uncertain.md"),
    );
    await a.emit("tool_call", {
      toolName: "write",
      toolCallId: "native-settled-uncertain-call",
      input: args,
    });
    await a.emit("tool_result", {
      toolName: "write",
      toolCallId: "native-settled-uncertain-call",
      content: [],
      isError: true,
    });
    const coordination = new DatabaseSync(join(f.home, "coordination.sqlite"), {
      readOnly: true,
    });
    try {
      const operation = JSON.parse(
        String(
          coordination
            .prepare(
              "SELECT json FROM operations WHERE operation_id='file:native-settled-uncertain'",
            )
            .get()!.json,
        ),
      );
      assert.equal(operation.status, "unknown");
    } finally {
      coordination.close();
    }
    assert.equal(
      (
        await b.call("zara_file_inspect", {
          request_id: "native-settled-uncertain",
        })
      ).code,
      "STORE_BUSY",
      "a live foreign runtime's unknown barrier cannot be adopted",
    );
    const backup = await b.call("zara_backup", {});
    assert.equal(backup.code, undefined, JSON.stringify(backup));
    const proposal = await b.call("zara_restore_preview", {
      backup: backup.backup,
      consequence: "Restore while preserving unknown native resource",
      alternatives: "Keep generation",
    });
    assert.equal(proposal.code, undefined, JSON.stringify(proposal));
    const preview = proposal.preview as { request_id: string };
    assert.equal(
      (await b.call("zara_confirm", { preview_ref: preview.request_id })).code,
      undefined,
    );
    const restored = await b.call("zara_restore", {
      preview_ref: preview.request_id,
    });
    assert.equal(restored.code, undefined, JSON.stringify(restored));
    const control = new DatabaseSync(join(f.home, "coordination.sqlite"), {
      readOnly: true,
    });
    try {
      assert.equal(
        control
          .prepare(
            "SELECT count(*) AS n FROM resource_reservations WHERE operation_id='file:native-settled-uncertain'",
          )
          .get()!.n,
        1,
      );
    } finally {
      control.close();
    }
  } finally {
    await f.close();
  }
});

test("actual session startup waits for a live maintenance owner and recovers a proven-dead pre-switch fence", async () => {
  const f = fixture(),
    a = f.adapter();
  let owner: Coordination | undefined, token: string | undefined;
  try {
    await a.emit("session_start");
    await a.emit("session_shutdown");
    const control = readControl(f.home)!;
    owner = new Coordination(f.home, randomUUID(), {
      expectedId: control.coordination_id,
      create: false,
    });
    token = owner.sync("maintenance", () =>
      owner!.beginMaintenance("restore", control.epoch),
    );
    let started = false;
    const opening = a.emit("session_start").then(() => {
      started = true;
    });
    await tick();
    assert.equal(started, false);
    assert.equal(
      owner.maintenanceInfo().runtime_id,
      owner.runtimeId,
      "startup cannot take over a live administrator",
    );
    owner.sync("maintenance", () => owner!.endMaintenance(token));
    owner.close();
    owner = undefined;
    token = undefined;
    await opening;
    const runtime = (await a.snapshot()).runtime;
    await a.emit("session_shutdown");
    const abandoned = new DatabaseSync(join(f.home, "coordination.sqlite"));
    try {
      abandoned
        .prepare(
          "UPDATE maintenance SET mode='exclusive',runtime_id=?,token=?,kind='restore',expected_epoch=? WHERE singleton=1",
        )
        .run(runtime, randomUUID(), control.epoch);
    } finally {
      abandoned.close();
    }
    await a.emit("session_start");
    const recovered = await a.snapshot();
    assert.notEqual(recovered.runtime, runtime);
    assert.notEqual(
      recovered.data.available,
      false,
      JSON.stringify(recovered.data),
    );
    const verified = new DatabaseSync(join(f.home, "coordination.sqlite"), {
      readOnly: true,
    });
    try {
      assert.equal(
        verified
          .prepare("SELECT mode FROM maintenance WHERE singleton=1")
          .get()!.mode,
        "normal",
      );
    } finally {
      verified.close();
    }
    assert.equal(a.warnings.length, 0);
  } finally {
    if (owner) {
      if (token) owner.sync("maintenance", () => owner!.endMaintenance(token));
      owner.close();
    }
    await f.close();
  }
});

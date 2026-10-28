import test from "node:test";
import assert from "node:assert/strict";
import type {
  ExtensionAPI,
  ExtensionContext,
} from "@earendil-works/pi-coding-agent";
import {
  CustomMessageComponent,
  ExtensionSelectorComponent,
  initTheme,
} from "@earendil-works/pi-coding-agent";
import { stripTerminalSequences, visibleWidth } from "@earendil-works/pi-tui";
import {
  approvalDetails,
  approvalText,
  confirmApproval,
} from "../src/extension/confirmation.ts";
import { askQuestion } from "../src/extension/questions.ts";
import { chatReview, PROPOSAL_MESSAGE } from "../src/extension/chat-review.ts";
import { renderApproval } from "../src/extension/preview.ts";

type Proposal = Parameters<typeof renderApproval>[0];
const proposal = (): Proposal => ({
  action: "managed_file",
  exact: {
    target: "example.md",
    before_hash: null,
    before_length: 0,
    final_text: "FIRST\n" + "long readable text ".repeat(1000) + "\nLAST",
    independent_basis: "Mechanical example only",
  },
  consequence: "Создать заметку без изменения других файлов.",
  alternatives: "Ничего не сохранять.",
  expires_at: "2030-01-01T00:00:00Z",
});
initTheme("dark");

function fixture(choice?: string, custom?: string, affirmative = true) {
  const calls: {
    kind: string;
    title: string;
    choices?: string[];
    message?: string;
  }[] = [];
  const ctx = {
    mode: "tui",
    hasUI: true,
    ui: {
      async select(title: string, choices: string[]) {
        calls.push({ kind: "select", title, choices });
        return choice;
      },
      async input(title: string) {
        calls.push({ kind: "input", title });
        return custom;
      },
      async confirm(title: string, message: string) {
        calls.push({ kind: "confirm", title, message });
        return affirmative;
      },
    },
  } as unknown as ExtensionContext;
  return { ctx, calls };
}

test("full proposal text is retained for chat, with controls escaped and no page slicing", () => {
  const p = proposal();
  const before = structuredClone(p);
  const text = approvalDetails(p);
  assert.equal(text, approvalText(renderApproval(p)));
  assert.ok(text.includes(String(p.exact.final_text)));
  assert.ok(text.includes(p.consequence));
  assert.ok(text.includes(p.alternatives));
  assert.deepEqual(p, before);
  assert.doesNotMatch(
    approvalText("\x1b[2J\u009b\u202e\t\r"),
    /[\x1b\u009b\u202e\t\r]/,
  );
});

test("real Pi chat message renders the complete long text rather than a clipped dialog", () => {
  const text = approvalDetails(proposal());
  const message = new CustomMessageComponent(
    {
      role: "custom",
      customType: PROPOSAL_MESSAGE,
      content: text,
      display: true,
      timestamp: Date.now(),
    },
    undefined,
  );
  const lines = message.render(60).map(stripTerminalSequences);
  assert.ok(lines.length > 24);
  assert.match(lines.join("\n"), /FIRST/);
  assert.match(lines.join("\n"), /LAST/);
  assert.ok(lines.every((line) => visibleWidth(line) <= 60));
});

function chatFixture() {
  type Message = {
    customType: string;
    content: string;
    display: boolean;
    details: { preview: string; nonce: string };
  };
  const hooks = new Map<string, (event: Record<string, unknown>) => unknown>();
  const messages: Message[] = [];
  const options: { triggerTurn: boolean }[] = [];
  const gate = chatReview({
    on(name: string, handler: (event: Record<string, unknown>) => unknown) {
      hooks.set(name, handler);
    },
    sendMessage(message: Message, opts: { triggerTurn: boolean }) {
      messages.push(message);
      options.push(opts);
    },
  } as unknown as ExtensionAPI);
  const display = (message = messages.at(-1)) =>
    hooks.get("message_end")?.({ message: { role: "custom", ...message } });
  return { gate, hooks, messages, options, display };
}

test("queued sendMessage is not treated as displayed; no duplicate message before Pi emits it", () => {
  const f = chatFixture();
  const owner = {};
  assert.equal(f.gate.ensure(owner, "p1", "FULL TEXT"), false);
  assert.equal(f.gate.ensure(owner, "p1", "FULL TEXT"), false);
  assert.equal(f.messages.length, 1);
  assert.deepEqual(f.options[0], { triggerTurn: false });
  assert.equal(f.messages[0].display, true);
  f.display();
  assert.equal(f.gate.ensure(owner, "p1", "FULL TEXT"), true);
});

test("chat acknowledgement binds exact content/nonce/owner; reload and changed text require new display", () => {
  const f = chatFixture();
  const owner = {};
  f.gate.ensure(owner, "p1", "original");
  const message = f.messages[0];
  f.display({ ...message, display: false });
  assert.equal(
    f.gate.ensure(owner, "p1", "original"),
    false,
    "hidden messages are not visible review",
  );
  f.display({ ...message, content: "changed" });
  assert.equal(f.gate.ensure(owner, "p1", "original"), false);
  f.display({ ...message, details: { ...message.details, nonce: "wrong" } });
  assert.equal(f.gate.ensure(owner, "p1", "original"), false);
  f.display(message);
  assert.equal(f.gate.ensure(owner, "p1", "original"), true);
  assert.equal(f.gate.ensure({}, "p1", "original"), false);
  assert.equal(f.gate.ensure(owner, "p1", "new text"), false);
  f.display();
  f.hooks.get("session_shutdown")?.({});
  assert.equal(f.gate.ensure(owner, "p1", "new text"), false);
});

test("ordinary questions offer real selectable choices plus native custom input", async () => {
  const f = fixture("Свой ответ…", "Мой вариант без потери пробелов  ");
  assert.deepEqual(
    await askQuestion(f.ctx, "Как продолжить?", ["Сейчас", "Позже"]),
    { kind: "custom", answer: "Мой вариант без потери пробелов  " },
  );
  assert.deepEqual(f.calls[0].choices, ["Сейчас", "Позже", "Свой ответ…"]);
  assert.deepEqual(
    f.calls.map((call) => call.kind),
    ["select", "input"],
  );
});

test("choice, cancelled selector and cancelled/empty custom answers are distinct data", async () => {
  assert.deepEqual(
    await askQuestion(fixture("Now").ctx, "When?", ["Now", "Later"]),
    { kind: "choice", answer: "Now" },
  );
  for (const f of [
    fixture(),
    fixture("Other answer…"),
    fixture("Other answer…", "   "),
    fixture("forged"),
  ])
    assert.deepEqual(await askQuestion(f.ctx, "When?", ["Now", "Later"]), {
      kind: "cancelled",
    });
});

test("long explanations, unsafe controls, duplicate/reserved and wide labels cannot enter the small question", async () => {
  const f = fixture();
  for (const [title, choices] of [
    ["x".repeat(53), ["Yes"]],
    ["Question\nlarge body", ["Yes"]],
    ["Question", ["界".repeat(20)]],
    ["Question", ["Yes", "Yes"]],
    ["Question", ["Other answer…"]],
    ["Question", []],
  ] as [string, string[]][])
    await assert.rejects(() => askQuestion(f.ctx, title, choices));
  assert.equal(f.calls.length, 0);
  const tooLong = fixture("Other answer…", "x".repeat(4001));
  await assert.rejects(
    () => askQuestion(tooLong.ctx, "Question?", ["Yes"]),
    /4000/,
  );
});

test("native short choice UI includes custom option and fits 32x24", () => {
  const selector = new ExtensionSelectorComponent(
    "Что сделать?",
    ["Подтвердить", "Отмена", "Свой ответ…"],
    () => {},
    () => {},
  );
  try {
    const lines = selector.render(32).map(stripTerminalSequences);
    assert.ok(lines.length <= 24);
    assert.match(lines.join("\n"), /Свой ответ/);
  } finally {
    selector.dispose();
  }
});

test("protected custom text declines the immutable proposal and never reaches native approval", async () => {
  const f = fixture("Свой ответ…", "Измени только заголовок");
  const received: string[] = [];
  assert.equal(
    await confirmApproval(f.ctx, proposal(), (text) => received.push(text)),
    false,
  );
  assert.deepEqual(received, ["Измени только заголовок"]);
  assert.deepEqual(
    f.calls.map((call) => call.kind),
    ["select", "input"],
  );
});

test("protected cancellation never confirms; selecting Confirm alone is not authority", async () => {
  for (const f of [fixture(), fixture("Отмена"), fixture("Свой ответ…")]) {
    assert.equal(await confirmApproval(f.ctx, proposal()), false);
    assert.equal(
      f.calls.some((call) => call.kind === "confirm"),
      false,
    );
  }
  const no = fixture("Подтвердить", undefined, false);
  assert.equal(await confirmApproval(no.ctx, proposal()), false);
  assert.equal(no.calls.filter((call) => call.kind === "confirm").length, 1);
  const yes = fixture("Подтвердить");
  assert.equal(await confirmApproval(yes.ctx, proposal()), true);
  assert.equal(yes.calls[1].title, "Подтвердить?");
  assert.ok((yes.calls[1].message?.length ?? 0) < 40);
  assert.doesNotMatch(yes.calls[1].message ?? "", /FIRST|LAST|example|Create/);
});

test("native UI failure propagates so the adapter can revoke rather than infer consent", async () => {
  const f = fixture("Подтвердить");
  f.ctx.ui.confirm = async () => {
    throw new Error("native failure");
  };
  await assert.rejects(
    () => confirmApproval(f.ctx, proposal()),
    /native failure/,
  );
});

test("RPC/SDK keeps the existing full native-confirmation contract", async () => {
  const f = fixture();
  const ctx = { ...f.ctx, mode: "rpc" } as ExtensionContext;
  assert.equal(await confirmApproval(ctx, proposal()), true);
  assert.equal(f.calls.length, 1);
  assert.equal(f.calls[0].message, approvalDetails(proposal()));
});

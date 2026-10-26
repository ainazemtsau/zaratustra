import test from "node:test";
import assert from "node:assert/strict";
import {
  ExtensionSelectorComponent,
  initTheme,
} from "@earendil-works/pi-coding-agent";
import type { ExtensionContext } from "@earendil-works/pi-coding-agent";
import {
  approvalPages,
  approvalSummary,
  approvalText,
  confirmApproval,
  requiresApprovalReview,
} from "../src/extension/confirmation.ts";
import { renderApproval } from "../src/extension/preview.ts";

type Proposal = Parameters<typeof renderApproval>[0];
const proposal = (overrides: Partial<Proposal> = {}): Proposal => ({
  action: "managed_file",
  exact: {
    target: "example/notes.md",
    before_hash: null,
    before_length: 0,
    final_text: '{"private": "' + "x".repeat(64000) + '"}',
    independent_basis: "Requested document",
  },
  consequence: "Create the requested document.",
  alternatives: "Leave it unchanged.",
  expires_at: "2030-01-01T00:00:00Z",
  ...overrides,
});

test("ordinary summary excludes full bodies, JSON payload and technical identifiers", () => {
  const p = proposal();
  const before = structuredClone(p);
  const text = approvalSummary(p);
  assert.match(text, /Create file: example\/notes.md/);
  assert.match(text, /full details/);
  assert.doesNotMatch(text, /private|before_hash|64000|expires_at/);
  assert.ok(text.length < 500);
  assert.deepEqual(p, before);
  const record = proposal({
    action: "commit",
    exact: {
      ops: [
        {
          op: "create_record",
          kind: "entity",
          title: "Example resource",
          data: { internal: "SECRET-BODY" },
        },
      ],
    },
  });
  assert.match(approvalSummary(record), /create record: Example resource/);
  assert.doesNotMatch(approvalSummary(record), /SECRET-BODY|internal/);
  assert.equal(requiresApprovalReview(record), false);
});

test("scope or consequence omitted from summary requires full review; dangerous actions cannot skip it", () => {
  assert.equal(requiresApprovalReview(proposal()), false);
  for (const p of [
    proposal({ action: "storage" }),
    proposal({ action: "restore" }),
    proposal({ action: "cleanup" }),
    proposal({ consequence: "x".repeat(161) }),
    proposal({ exact: { target: "x".repeat(101) } }),
    proposal({ action: "commit", exact: { ops: [{ op: "merge_identity" }] } }),
    proposal({
      action: "commit",
      exact: {
        ops: Array.from({ length: 4 }, () => ({ op: "create_record" })),
      },
    }),
  ])
    assert.equal(requiresApprovalReview(p), true);
});

test("detail pages are bounded for long lines, many newlines, wide characters and control data", () => {
  const text =
    "  indented\n\n" +
    "界😀".repeat(500) +
    "\n".repeat(50) +
    "\x1b[2J\u202eEND";
  const pages = approvalPages(text);
  assert.ok(pages.length > 10);
  for (const page of pages) {
    assert.ok(page.split("\n").length <= 6);
    assert.ok(page.split("\n").every((line) => Array.from(line).length <= 24));
    assert.doesNotMatch(page, /[\x1b\u202e]/);
  }
  assert.equal(
    pages.join("").replaceAll("\n", ""),
    approvalText(text).replaceAll("\n", ""),
  );
  assert.match(pages[0], /^  indented/);
});

function fixture(answers: boolean[] = [true]) {
  let listener: ((data: string) => unknown) | undefined;
  let unsubscriptions = 0;
  let triggerDetails = false;
  let cancelDetails = false;
  let throwConfirm = false;
  const messages: string[] = [];
  const selections: string[] = [];
  const ctx = {
    mode: "tui",
    ui: {
      onTerminalInput(fn: typeof listener) {
        listener = fn;
        return () => {
          listener = undefined;
          unsubscriptions++;
        };
      },
      async confirm(
        _title: string,
        message: string,
        opts?: { signal?: AbortSignal },
      ) {
        messages.push(message);
        if (throwConfirm) throw new Error("native dialog failure");
        if (triggerDetails) {
          triggerDetails = false;
          assert.deepEqual(listener?.("d"), { consume: true });
          assert.equal(opts?.signal?.aborted, true);
          return true; // Even a racing yes cannot bypass requested detail review.
        }
        return answers.shift() ?? false;
      },
      async select(title: string, options: string[]) {
        selections.push(title);
        return cancelDetails ? undefined : options[0];
      },
    },
  } as unknown as ExtensionContext;
  return {
    ctx,
    messages,
    selections,
    get unsubscriptions() {
      return unsubscriptions;
    },
    get listener() {
      return listener;
    },
    details: () => {
      triggerDetails = true;
    },
    cancel: () => {
      cancelDetails = true;
    },
    fail: () => {
      throwConfirm = true;
    },
  };
}

test("actual Pi 1.4 native selector layout fits ordinary confirmation/details in 60x24", () => {
  initTheme("dark");
  const p = proposal();
  const summary = new ExtensionSelectorComponent(
    "Allow these changes?\n" + approvalSummary(p),
    ["Yes", "No"],
    () => {},
    () => {},
  );
  const before = new ExtensionSelectorComponent(
    "Confirm these exact changes?\n" + renderApproval(p),
    ["Yes", "No"],
    () => {},
    () => {},
  );
  assert.ok(before.render(60).length > 100);
  assert.ok(summary.render(60).length <= 24);
  const page = new ExtensionSelectorComponent(
    "Exact proposal details — 1/100\n" + approvalPages(renderApproval(p))[0],
    ["Next page", "Cancel proposal"],
    () => {},
    () => {},
  );
  assert.ok(page.render(60).length <= 24);
  summary.dispose();
  before.dispose();
  page.dispose();
});

test("ordinary approval uses exactly one actual native confirmation and cleans its listener", async () => {
  const f = fixture();
  assert.equal(await confirmApproval(f.ctx, proposal()), true);
  assert.equal(f.messages.length, 1);
  assert.equal(f.selections.length, 0);
  assert.equal(f.unsubscriptions, 1);
  assert.equal(f.listener, undefined);
});

test("D reviews the same full proposal through bounded pages, then asks native confirmation again", async () => {
  const f = fixture([false]);
  f.details();
  const p = proposal({
    exact: {
      ...proposal().exact,
      final_text: "first\n" + "long content".repeat(20) + "\nLAST-MARKER",
    },
  });
  const before = structuredClone(p);
  assert.equal(await confirmApproval(f.ctx, p), false);
  assert.equal(f.messages.length, 2);
  assert.ok(f.selections.length > 2);
  assert.match(f.selections.join(""), /LAST-MARKER/);
  assert.deepEqual(p, before);
  assert.equal(f.unsubscriptions, 2);
});

test("cancel from details and native No never grant; mandatory review happens before native Yes", async () => {
  const cancel = fixture();
  cancel.details();
  cancel.cancel();
  assert.equal(await confirmApproval(cancel.ctx, proposal()), false);
  assert.equal(cancel.messages.length, 1);
  const mandatory = fixture();
  mandatory.cancel();
  assert.equal(
    await confirmApproval(
      mandatory.ctx,
      proposal({
        action: "cleanup",
        exact: { candidates: [], coverage: "orphans only" },
      }),
    ),
    false,
  );
  assert.equal(mandatory.messages.length, 0);
  const no = fixture([false]);
  assert.equal(await confirmApproval(no.ctx, proposal()), false);
});

test("native failures propagate for adapter revocation and unsubscribe input handler", async () => {
  const f = fixture();
  f.fail();
  await assert.rejects(
    () => confirmApproval(f.ctx, proposal()),
    /native dialog failure/,
  );
  assert.equal(f.unsubscriptions, 1);
});

test("RPC/SDK retains existing full native presentation without terminal-only methods", async () => {
  let shown = "";
  const ctx = {
    mode: "rpc",
    ui: {
      async confirm(_title: string, text: string) {
        shown = text;
        return true;
      },
    },
  } as unknown as ExtensionContext;
  const p = proposal();
  assert.equal(await confirmApproval(ctx, p), true);
  assert.equal(shown, renderApproval(p));
});

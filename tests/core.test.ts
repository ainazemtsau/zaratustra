import test from "node:test";
import assert from "node:assert/strict";
import {
  mkdtempSync,
  mkdirSync,
  readFileSync,
  writeFileSync,
  existsSync,
} from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { Core, digest, failure } from "../src/core/index.ts";
import { DiskStorage } from "../src/storage/index.ts";

function fixture() {
  const root = mkdtempSync(
    join(process.env.ZARATUSTRA_TEST_ROOT ?? tmpdir(), "zaratustra-block1-"),
  );
  const home = join(root, "home");
  const inputs = join(root, "inputs");
  mkdirSync(inputs);
  const disk = new DiskStorage(home);
  const core = make(disk);
  return { root, home, inputs, disk, core };
}
function make(disk: DiskStorage, fault?: (point: string) => void) {
  return new Core(
    disk,
    {
      workspace_id: disk.workspace.workspace_id,
      epoch: disk.workspace.epoch,
      principal: "trusted-personal",
      session_id: "synthetic-session",
      runtime_id: "synthetic-runtime",
      can_write: true,
      processing_allowed: true,
    },
    fault,
  );
}
function payload(core: Core, request_id = "new-intention") {
  const source = core.capture(
    "Создай область «Чтение». Книгу пришлю позже. Отвечай по-русски.",
    "rpc",
    "synthetic-controller",
  );
  return {
    request_id,
    reason:
      "Create reading work and retain original source and conversation preference.",
    source_handles: [source.source_handle],
    guards: [],
    ops: [
      {
        op: "import_evidence",
        client_ref: "source",
        source_handle: source.source_handle,
        title: "Original reading request",
        source_language: "ru",
      },
      {
        op: "create_record",
        client_ref: "activity",
        kind: "activity",
        title: "Reading",
        visibility: "workspace",
        data: { purpose: "Understand supplied books.", status: "active" },
      },
      {
        op: "create_record",
        client_ref: "work",
        kind: "work",
        title: "Understand the future book",
        visibility: "workspace",
        data: {
          activity_id: { client_ref: "activity" },
          parent_work_id: null,
          objective: "Understand a supplied book.",
          acceptance: [
            {
              criterion_id: "analysis",
              description: "Grounded analysis",
              verification: "Read retained grounds",
              required: true,
            },
          ],
          status: "waiting",
          current_state: "Book not received.",
          next_action: "Ask for the book.",
          steps: [],
          waits: [
            {
              wait_id: "book",
              kind: "user",
              target: "work",
              subject: "Book material",
              satisfied_by: "Readable book received",
              received_refs: [],
              question: "Please send the book.",
            },
          ],
          context_refs: [{ client_ref: "source" }],
          completion: null,
        },
      },
      {
        op: "create_record",
        client_ref: "language",
        kind: "knowledge",
        title: "Conversation language",
        visibility: "workspace",
        data: {
          knowledge_kind: "preference",
          statement: "The user prefers Russian replies.",
          state: "current",
          basis: "user_statement",
          evidence_refs: [{ client_ref: "source" }],
          conditions: "Agent conversation",
          representation: {
            kind: "English paraphrase",
            source_ref: { client_ref: "source" },
            source_language: "ru",
          },
        },
      },
    ],
  };
}
test("disk WAL reopen preserves all linked objects, versions, Change, exact source and receipt", () => {
  const f = fixture();
  const p = payload(f.core);
  const receipt = f.core.commit(p);
  assert.equal(receipt.committed, true);
  assert.equal(f.core.sequence(), 1);
  assert.equal(
    f.disk.get<{ n: number }>("SELECT count(*) AS n FROM records")!.n,
    4,
  );
  assert.equal(
    f.disk.get<{ n: number }>("SELECT count(*) AS n FROM revisions")!.n,
    4,
  );
  const original = f.core.read(receipt.created.source).data as unknown as {
    data: {
      retained_excerpt: string;
      provenance: { transport: string; original_keystrokes: boolean };
    };
  };
  assert.equal(
    original.data.retained_excerpt,
    "Создай область «Чтение». Книгу пришлю позже. Отвечай по-русски.",
  );
  assert.equal(original.data.provenance.transport, "rpc");
  assert.equal(original.data.provenance.original_keystrokes, false);
  assert.deepEqual(f.core.commit(p), receipt);
  f.core.expireSources();
  assert.deepEqual(f.core.commit(p), receipt);
  assert.throws(
    () => f.core.commit({ ...p, reason: "Different payload" }),
    /different canonical payload/,
  );
  f.disk.close();
  const reopened = new DiskStorage(f.home);
  const next = make(reopened);
  assert.equal(
    next.snapshot().records.find((r) => r.kind === "work")!.data.current_state,
    "Book not received.",
  );
  assert.deepEqual(next.operation(p.request_id).data.receipt, receipt);
  assert.equal(
    reopened.doctor().journal &&
      (reopened.doctor().journal as { journal_mode: string }).journal_mode,
    "wal",
  );
  reopened.close();
});
test("faults on every commit boundary leave all domain state/receipt or none; lost response is recoverable without old ID", () => {
  for (const point of [
    "after_prepare",
    "after_records",
    "before_commit",
    "after_commit",
  ]) {
    const f = fixture();
    const c = make(f.disk, (p) => {
      if (p === point) throw new Error("synthetic injected fault");
    });
    const p = payload(c);
    assert.throws(() => c.commit(p), /injected/);
    f.disk.close();
    const reopened = new DiskStorage(f.home);
    const next = make(reopened);
    const n = reopened.get<{ n: number }>(
      "SELECT count(*) AS n FROM records",
    )!.n;
    assert.equal(n, point === "after_commit" ? 4 : 0);
    assert.equal(
      reopened.get<{ n: number }>("SELECT count(*) AS n FROM receipts")!.n,
      point === "after_commit" ? 1 : 0,
    );
    const operations = next.browse("operations").data.cards as {
      status: string;
      receipt: { committed: boolean; created: { work: string } };
    }[];
    assert.equal(operations.length, 1);
    assert.equal(
      operations[0].status,
      point === "after_commit" ? "committed" : "prepared",
    );
    if (point === "after_commit")
      assert.equal(
        (
          next.read(operations[0].receipt.created.work).data as unknown as {
            data: { status: string };
          }
        ).data.status,
        "waiting",
      );
    reopened.close();
  }
});
test("similar independent requests create distinct records; stale guard and invalid final links are atomic failures", () => {
  const f = fixture();
  const one = f.core.commit(payload(f.core, "one"));
  f.core.commit(payload(f.core, "two"));
  assert.equal(
    f.disk.get<{ n: number }>("SELECT count(*) AS n FROM records")!.n,
    8,
  );
  const work = f.core.read(one.created.work).data as unknown as {
    data: Record<string, unknown>;
  };
  const source = f.core.capture(
    "Correct the current state.",
    "rpc",
    "synthetic-controller",
  );
  const correction = {
    request_id: "correction",
    reason: "Correct waiting state.",
    source_handles: [source.source_handle],
    guards: [{ ref: { id: one.created.work }, expected_revision: 1 }],
    ops: [
      {
        op: "update_record",
        ref: { id: one.created.work },
        data: {
          ...work.data,
          current_state: "An excerpt is expected; full book remains missing.",
        },
      },
    ],
  };
  f.core.commit(correction);
  assert.equal(f.core.snapshot().snapshot_seq, 3);
  assert.equal(
    f.core.snapshot().records.find((r) => r.id === one.created.work)!.data
      .current_state,
    "An excerpt is expected; full book remains missing.",
  );
  assert.equal(
    (
      f.core.read(one.created.work, 1).data as unknown as {
        data: { current_state: string };
      }
    ).data.current_state,
    "Book not received.",
  );
  assert.throws(
    () => f.core.commit({ ...correction, request_id: "stale" }),
    /guarded premise changed/,
  );
  const bad = payload(f.core, "bad");
  (bad.ops[2].data as Record<string, unknown>).activity_id = {
    client_ref: "source",
  };
  assert.throws(() => f.core.commit(bad), /wrong kind/);
  assert.equal(f.core.sequence(), 3);
  assert.equal(
    f.disk.get<{ n: number }>("SELECT count(*) AS n FROM records")!.n,
    8,
  );
  f.disk.close();
});
test("source expiry, forged fields and unsupported kinds do not mutate domain state", () => {
  const f = fixture();
  const p = payload(f.core);
  f.core.expireSources();
  assert.throws(() => f.core.commit(p), /expired/);
  const forged = payload(f.core);
  assert.equal(
    failure(new Error("synthetic disk failure")).code,
    "STORE_UNAVAILABLE",
  );
  assert.throws(() => f.core.commit({ ...forged, actor: "owner" }));
  assert.throws(() =>
    f.core.commit({
      ...forged,
      ops: [{ op: "create_record", kind: "method" }],
    }),
  );
  assert.equal(f.core.sequence(), 0);
  f.disk.close();
});
test("one writing process, read-only/corrupt/missing stores never claim success or reset saved bytes", () => {
  const f = fixture();
  f.core.commit(payload(f.core));
  const second = new DiskStorage(f.home);
  assert.equal(second.readonly, true);
  assert.throws(
    () => make(second).commit(payload(make(second))),
    /writing process/,
  );
  second.close();
  f.disk.exec("PRAGMA query_only=ON");
  assert.throws(() => f.core.commit(payload(f.core, "read-only-fault")));
  f.disk.close();
  const db = join(f.home, "zara.sqlite");
  writeFileSync(db, "synthetic corrupt database");
  const before = readFileSync(db);
  assert.throws(() => new DiskStorage(f.home));
  assert.deepEqual(readFileSync(db), before);
  const missingHome = join(f.root, "missing");
  mkdirSync(missingHome);
  writeFileSync(join(missingHome, "workspace.json"), "{}");
  assert.throws(() => new DiskStorage(missingHome), /mismatch/);
  assert.equal(existsSync(join(missingHome, "zara.sqlite")), false);
});
test("retained Markdown survives source removal, exact bytes/read ranges and interrupted imports do not publish unfinished refs", () => {
  const f = fixture();
  const file = join(f.inputs, "excerpt.md");
  const bytes = Buffer.from(
    "\ufeff# Синтетическая книга\r\nНаблюдение отличается от вывода. 🦉\r\n",
  );
  writeFileSync(file, bytes);
  for (const point of ["after_stage", "after_rename"]) {
    assert.throws(
      () =>
        f.disk.importFile(file, [f.inputs], (p) => {
          if (p === point) throw new Error("import interrupted");
        }),
      /interrupted/,
    );
    assert.equal(f.core.sequence(), 0);
  }
  const m = f.disk.importFile(file, [f.inputs]);
  const s = f.core.capture(m.text, "file", null, m);
  const receipt = f.core.commit({
    request_id: "material",
    reason: "Retain exact excerpt.",
    source_handles: [s.source_handle],
    guards: [],
    ops: [
      {
        op: "import_evidence",
        client_ref: "excerpt",
        source_handle: s.source_handle,
        title: "Retained synthetic excerpt",
        source_language: "ru",
      },
    ],
  });
  writeFileSync(file, "changed outside managed storage");
  assert.deepEqual(readFileSync(join(f.home, "materials", m.blob_ref)), bytes);
  assert.equal(m.blob_ref, digest(bytes));
  const range = f.core.read(receipt.created.excerpt, undefined, {
    start: 1,
    length: 24,
  }).data as unknown as { text: string };
  assert.equal(range.text, Array.from(m.text).slice(1, 25).join(""));
  assert.throws(() => f.disk.importFile(file, [f.home]), /escapes/);
  writeFileSync(join(f.inputs, "wrong.pdf"), bytes);
  assert.throws(
    () => f.disk.importFile(join(f.inputs, "wrong.pdf"), [f.inputs]),
    /only UTF-8/,
  );
  f.disk.close();
});
test("bounded catalog cursors reject changed generation and permissions apply to reads", () => {
  const f = fixture();
  f.core.commit(payload(f.core, "first"));
  f.core.commit(payload(f.core, "second"));
  const page = f.core.browse("work", undefined, 1).data;
  assert.equal(page.has_more, true);
  assert.ok(page.next_cursor);
  f.core.commit(payload(f.core, "third"));
  assert.throws(
    () => f.core.browse("work", undefined, 1, page.next_cursor!),
    /Restart/,
  );
  f.core.context.processing_allowed = false;
  assert.throws(() => f.core.map(), /authority/);
  assert.throws(() => f.core.snapshot(), /authority/);
  f.disk.close();
});

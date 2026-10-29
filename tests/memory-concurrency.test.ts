import test from "node:test";
import assert from "node:assert/strict";
import { mkdtempSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { DatabaseSync } from "node:sqlite";
import {
  Memory,
  MemorySchemaSQL,
  fullAccessProjection,
  refreshMemory,
} from "../src/core/memory.ts";
import { ExperienceSchemaSQL } from "../src/core/experience.ts";
import { SleepSchemaSQL } from "../src/core/sleep.ts";
import type {
  AddressedRow,
  CallContext,
  JsonObject,
  StoragePort,
} from "../src/core/contracts.ts";

class Fixture implements StoragePort {
  readonly = false;
  workspace = {
    workspace_id: "synthetic-memory",
    epoch: "epoch",
    schema_version: 9,
  };
  home = mkdtempSync(join(tmpdir(), "zara-memory-concurrency-"));
  db = new DatabaseSync(join(this.home, "memory.sqlite"));
  statements: string[] = [];
  constructor() {
    this.exec(`
      CREATE TABLE records(id TEXT PRIMARY KEY,kind TEXT NOT NULL,activity_id TEXT,json TEXT NOT NULL);
      CREATE TABLE revisions(id TEXT NOT NULL,revision INTEGER NOT NULL,json TEXT NOT NULL,PRIMARY KEY(id,revision));
      CREATE TABLE changes(seq INTEGER PRIMARY KEY,json TEXT NOT NULL);
      CREATE TABLE intents(request_id TEXT PRIMARY KEY,hash TEXT NOT NULL,json TEXT NOT NULL);
      CREATE TABLE claims(token TEXT PRIMARY KEY,work_id TEXT NOT NULL,json TEXT NOT NULL);
      CREATE TABLE handoffs(id TEXT PRIMARY KEY,json TEXT NOT NULL);
      ${MemorySchemaSQL} ${ExperienceSchemaSQL} ${SleepSchemaSQL}`);
    refreshMemory(this, true);
  }
  exec(sql: string) {
    this.statements.push(sql);
    this.db.exec(sql);
  }
  get<T>(sql: string, ...params: (string | number | null)[]) {
    this.statements.push(sql);
    return this.db.prepare(sql).get(...params) as T | undefined;
  }
  all<T>(sql: string, ...params: (string | number | null)[]) {
    this.statements.push(sql);
    return this.db.prepare(sql).all(...params) as T[];
  }
  run(sql: string, ...params: (string | number | null)[]) {
    this.statements.push(sql);
    this.db.prepare(sql).run(...params);
  }
  readMaterial(): string {
    throw new Error("No synthetic materials.");
  }
  close() {
    this.db.close();
    rmSync(this.home, { recursive: true, force: true });
  }
  put(
    id: string,
    revision = 1,
    visibility = "workspace",
    data: JsonObject = {},
    kind = "entity",
  ) {
    const row = {
      id,
      revision,
      visibility,
      kind,
      title: id,
      body: "synthetic index text",
      storage: "live",
      concept_ids: [],
      origin_activity_id: null,
      data: { entity_kind: "device", status: "active", aliases: [], ...data },
    } as unknown as AddressedRow;
    this.run(
      "INSERT INTO records VALUES(?,?,NULL,?) ON CONFLICT(id) DO UPDATE SET json=excluded.json",
      id,
      kind,
      JSON.stringify(row),
    );
    this.run(
      "INSERT INTO revisions VALUES(?,?,?) ON CONFLICT(id,revision) DO UPDATE SET json=excluded.json",
      id,
      revision,
      JSON.stringify(row),
    );
    return row;
  }
  memory(scopes: string[] = []) {
    const context = {
      ...this.workspace,
      principal: "synthetic",
      scopes,
    } as unknown as CallContext;
    return new Memory(this, context, new Map());
  }
  equivalent() {
    const oracle = fullAccessProjection(this);
    for (const row of this.all<{
      id: string;
      revision: number;
      restricted: number;
    }>("SELECT * FROM memory_docs"))
      assert.equal(
        !!row.restricted,
        !!oracle.versionRestrictions.get(row.id + ":" + row.revision),
        row.id + ":" + row.revision,
      );
  }
}

test("incremental access equals full oracle through cycles, removal, current/history refs and latent IDs", (t) => {
  const f = new Fixture();
  t.after(() => f.close());
  f.put("a", 1, "workspace", { peer: { id: "b" } });
  f.put("b", 1, "workspace", { peer: { id: "a" } });
  f.put("latent", 1, "workspace", { peer: { id: "future" } });
  refreshMemory(f);
  f.equivalent();
  f.put("a", 2, "restricted", { peer: { id: "b" } });
  refreshMemory(f);
  f.equivalent();
  assert.equal(f.memory().allowed("b"), false);
  f.put("a", 3, "workspace", { peer: { id: "b" } });
  refreshMemory(f);
  f.equivalent();
  assert.equal(f.memory().allowed("b"), true);
  f.put("exact", 1, "workspace", { peer: { id: "a", revision: 2 } });
  f.put("future", 1, "restricted");
  refreshMemory(f);
  f.equivalent();
  assert.equal(f.memory().allowed("exact"), false);
  assert.equal(f.memory().allowed("latent"), false);
  f.run(
    "INSERT INTO intents VALUES('legacy','hash',?)",
    JSON.stringify({
      request_id: "legacy",
      payload: { guards: { a: 1 } },
    }),
  );
  f.run(
    "INSERT INTO changes VALUES(1,?)",
    JSON.stringify({ request_id: "legacy", changed: {} }),
  );
  refreshMemory(f);
  assert.equal(
    f.memory().visibleSequence(),
    0,
    "technical keys inherit protected old history",
  );
  assert.equal(
    f.memory().allowed("a"),
    true,
    "private old content does not hide a public current identity",
  );
});

test("ordinary deltas preserve docids and avoid full version or Sleep enumeration", (t) => {
  const f = new Fixture();
  t.after(() => f.close());
  for (let i = 0; i < 40; i++) f.put("row-" + i);
  refreshMemory(f);
  const old = f.all("SELECT id,revision,docid FROM memory_docs ORDER BY docid");
  f.statements = [];
  f.put("row-0", 2);
  refreshMemory(f, false, [], ["row-0"]);
  assert.equal(
    f.statements.some(
      (sql) =>
        /SELECT (?:json|id,revision) FROM addressed_versions(?:\s|$)/.test(
          sql,
        ) && !sql.includes("WHERE"),
    ),
    false,
  );
  assert.equal(
    f.statements.some(
      (sql) =>
        sql.includes("FROM sleep_items") &&
        !sql.includes("WHERE") &&
        !sql.includes("JOIN descendants"),
    ),
    false,
  );
  assert.deepEqual(
    f.all(
      "SELECT id,revision,docid FROM memory_docs WHERE revision=1 ORDER BY docid",
    ),
    old,
  );
  refreshMemory(f, true);
  assert.deepEqual(
    f.all(
      "SELECT id,revision,docid FROM memory_docs WHERE revision=1 ORDER BY docid",
    ),
    old,
    "rebuild preserves exact document identities",
  );
});

test("live keyset cursors survive unrelated writes and updates, cap insertions and recheck ACL", (t) => {
  const f = new Fixture();
  t.after(() => f.close());
  for (const id of ["a", "b", "c", "d"]) f.put(id);
  refreshMemory(f);
  const m = f.memory();
  const first = m.browse("entities", undefined, 1);
  assert.equal(first.cards[0].id, "a");
  assert.ok(first.next_cursor);
  f.put("a", 2);
  f.put("new-after-window");
  f.put("b", 2, "restricted");
  refreshMemory(f);
  const next = m.browse("entities", undefined, 1, first.next_cursor!);
  assert.deepEqual(
    next.cards.map((r) => r.id),
    ["c"],
  );
  const last = m.browse("entities", undefined, 1, next.next_cursor!);
  assert.deepEqual(
    last.cards.map((r) => r.id),
    ["d"],
  );
  assert.equal(last.has_more, false);
  assert.throws(
    () => m.browse("entities", undefined, 2, first.next_cursor!),
    /continuation is invalid/,
  );
  refreshMemory(f, true);
  assert.throws(
    () => m.browse("entities", undefined, 1, first.next_cursor!),
    /continuation is invalid/,
  );
});

test("current search and exact history use separate stable ordinals", (t) => {
  const f = new Fixture();
  t.after(() => f.close());
  for (const id of ["a", "b", "c"]) f.put(id);
  refreshMemory(f);
  const m = f.memory();
  const first = m.search({ kinds: ["entity"], limit: 1 });
  f.put("a", 2);
  refreshMemory(f);
  const second = m.search({
    kinds: ["entity"],
    limit: 1,
    cursor: first.next_cursor!,
  });
  assert.equal(second.cards[0].id, "b");
  const history = m.search({ kinds: ["entity"], history: true, limit: 1 });
  f.put("b", 2);
  refreshMemory(f);
  const revisions = [history.cards[0]];
  let cursor = history.next_cursor;
  while (cursor) {
    const page = m.search({
      kinds: ["entity"],
      history: true,
      limit: 1,
      cursor,
    });
    revisions.push(...page.cards);
    cursor = page.next_cursor;
  }
  assert.equal(
    new Set(revisions.map((r) => r.id + ":" + r.revision)).size,
    revisions.length,
  );
  assert.equal(
    revisions.some((r) => r.id === "b" && r.revision === 2),
    false,
  );
});

test("hidden-only writes preserve low counters and public provisional state is flushed only at finalization", (t) => {
  const f = new Fixture();
  t.after(() => f.close());
  f.put("public");
  refreshMemory(f);
  const m = f.memory(),
    before = m.generation();
  f.put("secret", 1, "restricted");
  refreshMemory(f, false, [], ["secret"], false);
  f.run(
    "INSERT INTO intents VALUES('secret-request','hash',?)",
    JSON.stringify({ request_id: "secret-request", visibility: "restricted" }),
  );
  f.run(
    "INSERT INTO changes VALUES(1,?)",
    JSON.stringify({
      request_id: "secret-request",
      changed_refs: [{ id: "secret", after_revision: 1 }],
    }),
  );
  refreshMemory(f);
  assert.equal(m.generation(), before);
  assert.equal(m.visibleSequence(), 0);
  f.run(
    "INSERT INTO intents VALUES('provisional','hash',?)",
    JSON.stringify({ request_id: "provisional", visibility: "workspace" }),
  );
  refreshMemory(f, false, [], [], false);
  f.run(
    "UPDATE intents SET json=? WHERE request_id='provisional'",
    JSON.stringify({ request_id: "provisional", visibility: "restricted" }),
  );
  refreshMemory(f);
  assert.equal(
    m.generation(),
    before,
    "intermediate public technical rows never published in final state",
  );
});

test("Sleep inherited exact grounds and resumed episode bindings equal the full oracle", (t) => {
  const f = new Fixture();
  t.after(() => f.close());
  for (const id of [
    "public",
    "work",
    "review",
    "old-review",
    "episode",
    "new-episode",
    "corrected",
  ])
    f.put(id);
  f.put("source", 1, "restricted");
  f.put("source", 2, "workspace");
  f.run(
    "INSERT INTO sleep_reviews VALUES('review','work','profile','global','epoch',0,'active','batch','episode')",
  );
  f.run(
    "INSERT INTO sleep_reviews VALUES('old-review','work','profile','global','old-epoch',0,'completed','old-batch','episode')",
  );
  const item = (
    prior: string | null,
    evidence_refs: unknown[] = [],
    change_refs: unknown[] = [],
  ) => ({
    ref: { id: "public", revision: 1 },
    input: "deferred",
    prior_item_id: prior,
    disposition: "deferred",
    reason: "synthetic",
    continuation: "later",
    evidence_refs,
    change_refs,
    expected_benefit: null,
    limits: null,
    next_check: "later",
    check_signal_ref: null,
  });
  f.run(
    "INSERT INTO sleep_items VALUES('old-item','old-review',1,'old-batch',?)",
    JSON.stringify(item(null, [{ id: "source", revision: 1 }])),
  );
  f.run(
    "INSERT INTO sleep_items VALUES('item','review',1,'batch',?)",
    JSON.stringify(item("old-item", [], [{ id: "corrected", revision: 1 }])),
  );
  refreshMemory(f);
  f.equivalent();
  assert.equal(f.memory().allowed("corrected"), false);
  assert.equal(f.memory().allowed("review"), false);
  f.run("UPDATE sleep_reviews SET episode_id='new-episode' WHERE id='review'");
  refreshMemory(f);
  f.equivalent();
  assert.equal(f.memory().allowed("new-episode"), false);
  f.run(
    "UPDATE sleep_items SET json=? WHERE id='old-item'",
    JSON.stringify(item(null)),
  );
  refreshMemory(f);
  f.equivalent();
  assert.equal(f.memory().allowed("corrected"), true);
  f.statements = [];
  f.run("UPDATE sleep_reviews SET batch_id='another-batch' WHERE id='review'");
  refreshMemory(f);
  assert.equal(
    f.statements.some((sql) => sql.startsWith("SELECT id FROM sleep_items")),
    false,
    "batch-only progress never enumerates frozen membership",
  );
});

test("deleting protected technical identities does not change public generation", (t) => {
  const f = new Fixture();
  t.after(() => f.close());
  f.put("public");
  refreshMemory(f);
  const m = f.memory(),
    before = m.generation();
  f.run(
    "INSERT INTO relations VALUES('secret-relation',?)",
    JSON.stringify({ id: "secret-relation", visibility: "restricted" }),
  );
  refreshMemory(f);
  assert.equal(m.generation(), before);
  f.run("DELETE FROM relations WHERE id='secret-relation'");
  refreshMemory(f);
  assert.equal(m.generation(), before);
  f.run(
    "INSERT INTO relations VALUES('public-relation',?)",
    JSON.stringify({ id: "public-relation", visibility: "workspace" }),
  );
  refreshMemory(f);
  const visible = m.generation();
  assert.notEqual(visible, before);
  f.run("DELETE FROM relations WHERE id='public-relation'");
  refreshMemory(f);
  assert.notEqual(m.generation(), visible);
});

test("cached technical access matches the oracle's single linked-intent hop", (t) => {
  const f = new Fixture();
  t.after(() => f.close());
  f.run(
    "INSERT INTO intents VALUES('b','hash',?)",
    JSON.stringify({ request_id: "b", transaction_id: "c" }),
  );
  f.run(
    "INSERT INTO intents VALUES('c','hash',?)",
    JSON.stringify({ request_id: "c", visibility: "restricted" }),
  );
  f.run("INSERT INTO changes VALUES(1,?)", JSON.stringify({ request_id: "b" }));
  f.run("INSERT INTO changes VALUES(2,?)", JSON.stringify({ request_id: "c" }));
  refreshMemory(f);
  const m = f.memory();
  assert.equal(m.visibleSequence(), 1);
  assert.equal(
    f.get<{ n: number }>(
      "SELECT count(*) AS n FROM changes t WHERE " + m.technicalSQL("t"),
    )!.n,
    1,
  );
  assert.equal(m.browse("changes").cards.length, 1);
});

test("readonly dirty derived access fails explicitly instead of omitting unindexed technical rows", (t) => {
  const f = new Fixture();
  t.after(() => f.close());
  f.run(
    "INSERT INTO changes VALUES(1,?)",
    JSON.stringify({ request_id: "pending" }),
  );
  f.readonly = true;
  assert.throws(() => f.memory().browse("changes"), /need recovery/);
  assert.throws(() => f.memory().visibleSequence(), /need recovery/);
  f.readonly = false;
  refreshMemory(f);
  f.readonly = true;
  assert.equal(f.memory().browse("changes").cards.length, 1);
});

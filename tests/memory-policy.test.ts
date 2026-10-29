import test from "node:test";
import assert from "node:assert/strict";
import { DatabaseSync } from "node:sqlite";
import {
  ActivityContractSchema,
  TRANSIENT_MAX_AGE_MS,
  TRANSIENT_MAX_BYTES,
  exactSourceFragment,
  memoryRetention,
  planTransientCleanup,
  retainedSourceText,
  TransientMemory,
  candidateGrounds,
} from "../src/core/memory-policy.ts";
import {
  Memory,
  MemorySchemaSQL,
  fullAccessProjection,
  refreshMemory,
  validateMemory,
} from "../src/core/memory.ts";
import { addressedIds, addressedIdsSQL } from "../src/core/memory-index.ts";
import { ExperienceSchemaSQL } from "../src/core/experience.ts";
import { SleepSchemaSQL } from "../src/core/sleep.ts";
import type {
  CallContext,
  StoragePort,
  RecordRow,
} from "../src/core/contracts.ts";
class Fixture implements StoragePort {
  readonly = false;
  workspace = { workspace_id: "synthetic", epoch: "test", schema_version: 10 };
  db = new DatabaseSync(":memory:");
  constructor() {
    this
      .exec(`CREATE TABLE records(id TEXT PRIMARY KEY,kind TEXT NOT NULL,activity_id TEXT,json TEXT NOT NULL);
      CREATE TABLE revisions(id TEXT NOT NULL,revision INTEGER NOT NULL,json TEXT NOT NULL,PRIMARY KEY(id,revision));
      CREATE TABLE changes(seq INTEGER PRIMARY KEY,json TEXT NOT NULL);
      CREATE TABLE intents(request_id TEXT PRIMARY KEY,hash TEXT NOT NULL,json TEXT NOT NULL);
      CREATE TABLE claims(token TEXT PRIMARY KEY,work_id TEXT NOT NULL,json TEXT NOT NULL);
      CREATE TABLE handoffs(id TEXT PRIMARY KEY,json TEXT NOT NULL);
      ${MemorySchemaSQL} ${ExperienceSchemaSQL} ${SleepSchemaSQL}`);
    refreshMemory(this, true);
  }
  exec(s: string) {
    this.db.exec(s);
  }
  get<T>(s: string, ...p: (string | number | null)[]) {
    return this.db.prepare(s).get(...p) as T | undefined;
  }
  all<T>(s: string, ...p: (string | number | null)[]) {
    return this.db.prepare(s).all(...p) as T[];
  }
  run(s: string, ...p: (string | number | null)[]) {
    this.db.prepare(s).run(...p);
  }
  readMaterial(): string {
    throw new Error("No materials.");
  }
  put(
    id: string,
    revision = 1,
    visibility = "workspace",
    data: Record<string, unknown> = {},
    body = "synthetic",
  ) {
    const r = {
      id,
      kind: "entity",
      revision,
      visibility,
      title: id,
      body,
      storage: "live",
      concept_ids: [],
      origin_activity_id: null,
      data: { entity_kind: "device", status: "active", ...data },
    };
    this.run(
      "INSERT INTO records VALUES(?,'entity',NULL,?) ON CONFLICT(id) DO UPDATE SET json=excluded.json",
      id,
      JSON.stringify(r),
    );
    this.run(
      "INSERT INTO revisions VALUES(?,?,?)",
      id,
      revision,
      JSON.stringify(r),
    );
  }
  memory() {
    return new Memory(
      this,
      { ...this.workspace, scopes: [] } as unknown as CallContext,
      new Map(),
    );
  }
  equivalent() {
    const expected = fullAccessProjection(this);
    for (const r of this.all<{
      id: string;
      revision: number;
      restricted: number;
    }>("SELECT * FROM memory_docs"))
      assert.equal(
        !!r.restricted,
        !!expected.versionRestrictions.get(r.id + ":" + r.revision),
        r.id + ":" + r.revision,
      );
  }
}
test("retention requires a future purpose; successful captures are transient by default", () => {
  assert.deepEqual(memoryRetention({}), { class: "transient" });
  assert.equal(memoryRetention({ purpose: "constraint" }).class, "durable");
  assert.throws(() => memoryRetention({ class: "durable" }));
  const contract = ActivityContractSchema.parse({
    summary: "Continue a real task",
  });
  assert.deepEqual(contract.document_refs, []);
  assert.equal(contract.memory_scope, "activity");
});
test("minimal source is exact Unicode code points, not a paraphrase or UTF-16 slice", () => {
  const text = "A\u{1f600}B\r\n\u0421",
    fragment = exactSourceFragment(text, { start: 1, end: 3 });
  assert.equal(fragment.text, "\u{1f600}B");
  assert.equal(fragment.unit, "unicode_code_points");
  assert.equal(fragment.source_characters, 6);
  assert.notEqual(fragment.source_hash, fragment.fragment_hash);
  assert.throws(() => exactSourceFragment(text, { start: 0, end: 100 }));
  assert.throws(() => exactSourceFragment(text, { start: 2, end: 2 }));
  assert.throws(() =>
    retainedSourceText("x".repeat(5000), { purpose: "decision" }),
  );
  assert.equal(
    retainedSourceText("x".repeat(5000), { purpose: "selected_source" }).text
      .length,
    5000,
  );
});
test("transient eviction is bounded, oldest first, and never deletes a pinned obligation", () => {
  const now = Date.parse("2026-10-29T00:00:00Z");
  const row = (
    id: string,
    age: number,
    pins: ("open_work" | "unknown_effect")[] = [],
  ) => ({
    id,
    created_at: new Date(now - age).toISOString(),
    byte_length: 8 * 1024 * 1024,
    pins,
  });
  const result = planTransientCleanup(
    [
      row("protected-old", TRANSIENT_MAX_AGE_MS * 2, ["unknown_effect"]),
      row("expired", TRANSIENT_MAX_AGE_MS + 1),
      row("older", 1000),
      row("newer", 1),
    ],
    now,
  );
  assert.deepEqual(result.remove, ["expired", "older"]);
  assert.equal(result.admission_blocked, false);
  const pinned = planTransientCleanup(
    [
      row("a", 1, ["open_work"]),
      row("b", 1, ["unknown_effect"]),
      row("c", 1, ["open_work"]),
    ],
    now,
  );
  assert.deepEqual(pinned.remove, []);
  assert.equal(pinned.admission_blocked, true);
  assert.ok(pinned.protected_bytes > TRANSIENT_MAX_BYTES);
  assert.throws(() =>
    planTransientCleanup([row("same", 1), row("same", 2, ["open_work"])], now),
  );
});
test("typed JS and SQL references agree and exclude arbitrary prose, keys and intent namespace", () => {
  const db = new DatabaseSync(":memory:");
  try {
    const value = {
      request_id: "not-domain",
      transaction_id: "another-intent",
      title: "not-an-id",
      body: "x".repeat(60000),
      payload: {
        nested: { secret: "secret" },
        guards: { "guard-id": 2, "unsafe-guard": Number.MAX_SAFE_INTEGER + 1 },
        ref: { id: "exact", revision: 3 },
        unsafe_ref: { id: "unsafe-ref", revision: Number.MAX_SAFE_INTEGER + 1 },
        changed_refs: [
          { id: "changed-id", before_revision: null, after_revision: 1 },
        ],
      },
      changed: {
        "legacy-id": { before: 1, after: 2 },
        bad: { before: "text", after: "text" },
      },
      new_revisions: { "new-id": 4 },
      created: { "client-label": "created-id" },
      claim: {
        token: "claim-token",
        work_id: "claim-work",
        step_id: "not-domain",
      },
      affected_ids: ["affected-id"],
      library: { kind: "library", record_id: "retained-id" },
    };
    const expected = [
      "affected-id",
      "changed-id",
      "claim-work",
      "created-id",
      "exact",
      "guard-id",
      "legacy-id",
      "new-id",
      "retained-id",
    ].sort();
    assert.deepEqual(addressedIds(value, true).sort(), expected);
    const sql = db
      .prepare(
        `SELECT DISTINCT id FROM (${addressedIdsSQL("$source")}) ORDER BY id`,
      )
      .all({ source: JSON.stringify(value) })
      .map((r) => r.id);
    assert.deepEqual(sql, expected);
    assert.deepEqual(
      addressedIds({
        id: "record",
        kind: "entity",
        revision: 1,
        body: "body",
        data: { aliases: ["alias"], ref: { id: "real" } },
      }).sort(),
      ["real", "record"],
    );
  } finally {
    db.close();
  }
});
test("large prose does not produce graph keys and technical access uses only declared references", (t) => {
  const f = new Fixture();
  t.after(() => f.db.close());
  f.put("secret", 1, "restricted");
  f.put(
    "ordinary",
    1,
    "workspace",
    { aliases: ["secret"], nested: { secret: "secret" } },
    "secret ".repeat(8000),
  );
  f.put("linked", 1, "workspace", {
    source_ref: { id: "secret", revision: 1 },
  });
  f.run(
    "INSERT INTO intents VALUES('raw','hash',?)",
    JSON.stringify({
      request_id: "raw",
      payload: { secret: "secret", content: "secret" },
    }),
  );
  f.run(
    "INSERT INTO intents VALUES('typed','hash',?)",
    JSON.stringify({
      request_id: "typed",
      payload: { refs: [{ id: "secret", revision: 1 }] },
    }),
  );
  f.run(
    "INSERT INTO changes VALUES(1,?)",
    JSON.stringify({ request_id: "raw" }),
  );
  f.run(
    "INSERT INTO changes VALUES(2,?)",
    JSON.stringify({ request_id: "typed" }),
  );
  refreshMemory(f);
  f.equivalent();
  const m = f.memory();
  assert.equal(m.allowed("ordinary"), true);
  assert.equal(m.allowed("linked"), false);
  assert.equal(m.visibleSequence(), 1);
  assert.equal(m.technical({ payload: { secret: "secret" } }), true);
  assert.equal(m.technical({ payload: { refs: [{ id: "secret" }] } }), false);
  assert.equal(
    f.get<{ n: number }>(
      "SELECT count(*) n FROM changes t WHERE " + m.technicalSQL("t"),
    )!.n,
    1,
  );
  assert.ok(
    f.get<{ n: number }>("SELECT count(*) n FROM memory_edges")!.n < 40,
  );
  assert.ok(
    f.get<{ n: number }>("SELECT max(length(target)) n FROM memory_edges")!.n <
      200,
  );
});
test("exact historical and latent refs retain access while active retrieval excludes legacy", (t) => {
  const f = new Fixture();
  t.after(() => f.db.close());
  f.put("source", 1, "restricted");
  f.put("source", 2, "workspace");
  f.put("historical", 1, "workspace", { ref: { id: "source", revision: 1 } });
  f.put("latent", 1, "workspace", { ref: { id: "future" } });
  f.put("active");
  f.put("legacy");
  refreshMemory(f);
  f.equivalent();
  f.put("future", 1, "restricted");
  refreshMemory(f);
  f.equivalent();
  assert.equal(f.memory().allowed("historical"), false);
  assert.equal(f.memory().allowed("latent"), false);
  f.exec(
    "CREATE TABLE corpus_entries(id TEXT,revision INTEGER,contour TEXT,PRIMARY KEY(id,revision)); INSERT INTO corpus_entries VALUES('legacy',1,'legacy');",
  );
  const m = f.memory();
  assert.equal(m.allowed("legacy"), true);
  assert.equal(
    m.browse("entities").cards.some((r) => r.id === "legacy"),
    false,
  );
  assert.deepEqual(
    m
      .browse("entities", undefined, 20, undefined, "legacy")
      .cards.map((r) => r.id),
    ["legacy"],
  );
  assert.equal(
    m.search({ kinds: ["entity"] }).cards.some((r) => r.id === "legacy"),
    false,
  );
  assert.equal(
    m
      .search({ kinds: ["entity"], include_legacy: true })
      .cards.some((r) => r.id === "legacy"),
    true,
  );
  assert.equal(m.browse("history", "legacy").cards.length, 1);
});
test("Activity contract resolves only explicit context, managed-document and procedure references", (t) => {
  const f = new Fixture();
  t.after(() => f.db.close());
  f.put("activity");
  f.put("context");
  f.put("document", 1, "workspace", {
    document: {
      key: "00000000-0000-4000-8000-000000000000",
      path: "health/current.md",
      document_type: "current",
      state: "active",
      format_ref: null,
      links: [],
      head_ref: { id: "source", revision: 1 },
      operation_id: "op",
    },
  });
  f.put("procedure");
  const rows = new Map(
    f
      .all<{ id: string; json: string }>("SELECT id,json FROM records")
      .map((r) => [r.id, JSON.parse(r.json) as RecordRow]),
  );
  rows.get("procedure")!.kind = "method";
  const activity = rows.get("activity")!;
  activity.kind = "activity";
  activity.data = {
    status: "active",
    contract: {
      summary: "Continue without a required questionnaire",
      context_refs: [{ id: "context" }],
      document_refs: [{ id: "document" }],
      procedure_refs: [{ id: "procedure" }],
    },
  };
  const resolved: string[] = [];
  const get = (value: unknown, kind?: string) => {
    const id = typeof value === "string" ? value : (value as { id: string }).id;
    const row = rows.get(id);
    assert.ok(row, "missing reference " + id);
    if (kind) assert.equal(row.kind, kind);
    resolved.push(id);
    return row;
  };
  validateMemory([activity], get);
  assert.deepEqual(resolved, ["context", "document", "procedure"]);
  (activity.data.contract as { document_refs: unknown[] }).document_refs = [
    { id: "context" },
  ];
  assert.throws(() => validateMemory([activity], get), /managed document/);
});
test("explicit deferred candidates expire, account encoded bytes, and preserve open grounds", (t) => {
  const f = new Fixture();
  t.after(() => f.db.close());
  const now = Date.parse("2026-10-29T00:00:00Z");
  f.put("work");
  const setStatus = (status: string) => {
    const row = JSON.parse(
      f.get<{ json: string }>("SELECT json FROM records WHERE id='work'")!.json,
    );
    row.kind = "work";
    row.data = { status };
    f.run(
      "UPDATE records SET kind='work',json=? WHERE id='work'",
      JSON.stringify(row),
    );
  };
  setStatus("active");
  let restricted = true;
  const policy = new TransientMemory(f, {
    authorize: () => {},
    canReadRef: (r) => !!f.get("SELECT 1 FROM records WHERE id=?", r.id),
    isRestrictedRef: (r) =>
      f.get<{ visibility: string }>(
        "SELECT json_extract(json,'$.visibility') visibility FROM records WHERE id=?",
        r.id,
      )?.visibility === "restricted",
    canReadRestricted: () => restricted,
    canWriteRestricted: () => restricted,
  });
  assert.deepEqual(
    policy.list(now),
    [],
    "no capture or tool-success logging occurs implicitly",
  );
  assert.throws(
    () =>
      policy.put(
        {
          kind: "diagnostic",
          summary: "Bulk diagnostic",
          content: "x".repeat(4097),
        },
        now,
      ),
    /sufficient candidate fragment/,
  );
  const temporary = policy.put(
    {
      kind: "diagnostic",
      summary: "One deferred question",
      content: "\u{1f600}\n",
    },
    now,
  );
  const stored = f.get<{ json: string }>(
    "SELECT json FROM memory_candidates WHERE id=?",
    temporary.id,
  )!;
  assert.equal(
    JSON.parse(stored.json).byte_length,
    Buffer.byteLength(stored.json),
  );
  const pinned = policy.put(
    {
      kind: "deferred_candidate",
      summary: "Missing context",
      content: "Exact short fragment",
      related_refs: [{ id: "work" }],
    },
    now,
  );
  assert.equal(pinned.pinned, true);
  assert.throws(() => policy.remove(pinned.id), /open obligation/);
  assert.throws(
    () =>
      policy.put(
        {
          kind: "diagnostic",
          summary: "Too much",
          content: "x".repeat(4097),
          related_refs: [{ id: "work" }],
        },
        now,
      ),
    /sufficient candidate fragment/,
  );
  assert.deepEqual(candidateGrounds(f), [{ id: "work" }]);
  const later = now + TRANSIENT_MAX_AGE_MS + 1;
  assert.equal(policy.list(later).length, 1);
  assert.throws(() => policy.read(temporary.id, later), /unavailable/);
  assert.equal(policy.read(pinned.id, later).pinned, true);
  assert.deepEqual(policy.sweep(later).removed, [temporary.id]);
  setStatus("done");
  assert.equal(policy.list(later).length, 0);
  policy.sweep(later);
  assert.deepEqual(candidateGrounds(f), []);
  const changing = policy.put(
    {
      kind: "diagnostic",
      summary: "Late restriction",
      content: "sufficient",
      related_refs: [{ id: "work" }],
    },
    now,
  );
  f.run(
    "UPDATE records SET json=json_set(json,'$.visibility','restricted') WHERE id='work'",
  );
  restricted = false;
  assert.deepEqual(policy.list(now), []);
  assert.throws(() => policy.read(changing.id, now), /unavailable/);
  assert.throws(() => policy.remove(changing.id), /unavailable/);
  policy.sweep(later);
  assert.ok(
    f.get("SELECT 1 FROM memory_candidates WHERE id=?", changing.id),
    "lower-scope sweep cannot erase newly restricted data",
  );
});

test("Sleep routes active authorized current cases before bounds, including typed subjects and completed-version exclusions", () => {
  const f = new Fixture();
  try {
    f.exec(
      "CREATE TABLE corpus_entries(id TEXT NOT NULL,revision INTEGER NOT NULL,contour TEXT NOT NULL,PRIMARY KEY(id,revision));",
    );
    const put = (
      id: string,
      kind: string,
      data: Record<string, unknown>,
      visibility = "workspace",
    ) => {
      f.put(id, 1, visibility, data);
      const row = JSON.parse(
        f.get<{ json: string }>("SELECT json FROM records WHERE id=?", id)!
          .json,
      );
      row.kind = kind;
      row.updated_at = "2026-10-29T00:00:00Z";
      const json = JSON.stringify(row);
      f.run("UPDATE records SET kind=?,json=? WHERE id=?", kind, json, id);
      f.run("UPDATE revisions SET json=? WHERE id=?", json, id);
    };
    put("activity", "activity", { purpose: "A", status: "active" });
    put("other", "activity", { purpose: "B", status: "active" });
    put("work", "work", { status: "waiting", activity_id: { id: "activity" } });
    for (let i = 0; i < 220; i++) {
      put("legacy-" + i, "run", {
        execution: "failed",
        mode: "work",
        work_ref: { id: "work", revision: 1 },
      });
      f.run("INSERT INTO corpus_entries VALUES(?,1,'legacy')", "legacy-" + i);
      put("unrelated-" + i, "work", {
        status: "waiting",
        activity_id: { id: "other" },
      });
      put("closed-" + i, "work", {
        status: "done",
        activity_id: { id: "activity" },
      });
    }
    put(
      "hidden",
      "work",
      { status: "waiting", activity_id: { id: "activity" } },
      "restricted",
    );
    put("reviewed", "work", {
      status: "waiting",
      activity_id: { id: "activity" },
    });
    const signal = {
      id: "signal",
      kind: "signal",
      revision: 1,
      visibility: "workspace",
      storage: "live",
      title: "Open question",
      body: null,
      concept_ids: [],
      origin_activity_id: null,
      updated_at: "2026-10-29T00:00:00Z",
      data: {
        problem_state: "open",
        subject_refs: [{ id: "work", revision: 1 }],
      },
    };
    f.run(
      "INSERT INTO experience_rows(id,kind,json) VALUES(?,?,?)",
      signal.id,
      signal.kind,
      JSON.stringify(signal),
    );
    f.run(
      "INSERT INTO experience_versions VALUES(?,?,?)",
      signal.id,
      1,
      JSON.stringify(signal),
    );
    refreshMemory(f, true);
    const memory = f.memory();
    const candidates = memory.sleepCandidates("activity", [
      { id: "reviewed", revision: 1 },
    ]);
    assert.deepEqual(
      candidates.map((r) => r.id),
      ["signal", "work"],
    );
    assert.ok(
      memory
        .sleepCandidates("activity", [{ id: "reviewed", revision: 2 }])
        .some((r) => r.id === "reviewed"),
    );
    const global = memory.sleepCandidates(null);
    assert.equal(global.length, 200);
    assert.ok(
      global.every(
        (r) =>
          !r.id.startsWith("legacy-") &&
          !r.id.startsWith("closed-") &&
          r.id !== "hidden",
      ),
    );
  } finally {
    f.db.close();
  }
});

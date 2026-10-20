import test from "node:test";
import assert from "node:assert/strict";
import { mkdtempSync, readFileSync, writeFileSync, readdirSync } from "node:fs";
import { join } from "node:path";
import { tmpdir } from "node:os";
import { Core, CoreError, digest } from "../src/core/index.ts";
import type { JsonObject, RecordRow } from "../src/core/index.ts";
import { DiskStorage } from "../src/storage/index.ts";

function fixture(scopes: string[] = []) {
  const home = mkdtempSync(
    join(process.env.ZARATUSTRA_TEST_ROOT ?? tmpdir(), "zara-D-"),
  );
  const disk = new DiskStorage(home);
  const core = new Core(disk, {
    ...disk.workspace,
    principal: "trusted-personal",
    session_id: "D",
    runtime_id: "D",
    processing_allowed: true,
    can_write: true,
    scopes,
  });
  let serial = 0;
  const commit = (
    ops: unknown[],
    guards: { ref: { id: string }; expected_revision: number }[] = [],
    c = core,
  ) => {
    const s = c.capture(
      "Синтетическое основание для сохранения и коррекции.",
      "rpc",
      "synthetic-D",
    );
    return c.commit({
      request_id: "D-" + ++serial,
      reason: "Synthetic connected memory change",
      source_handles: [s.source_handle],
      guards,
      ops: [
        {
          op: "import_evidence",
          client_ref: "source",
          source_handle: s.source_handle,
          title: "Observed source",
          source_language: "ru",
        },
        ...ops,
      ],
    });
  };
  const read = (id: string, revision?: number) =>
    core.read(id, revision).data as RecordRow;
  const guard = (id: string) => ({
    ref: { id },
    expected_revision: read(id).revision,
  });
  return { home, disk, core, commit, read, guard };
}
const ref = (client_ref: string) => ({ client_ref });
const concept = (client_ref: string, parents: unknown[] = []) => ({
  op: "create_record",
  kind: "concept",
  client_ref,
  title: client_ref,
  visibility: "workspace",
  data: {
    definition: "Equipment for producing physical artifacts",
    aliases: [client_ref + " alias"],
    broader_ids: parents,
    status: "active",
    boundary_notes: "Navigation, not property inheritance",
  },
});
const entity = (
  client_ref: string,
  concept_ids: unknown[] = [],
  title = client_ref,
  aliases: string[] = [],
) => ({
  op: "create_record",
  kind: "entity",
  client_ref,
  title,
  visibility: "workspace",
  concept_ids,
  data: {
    entity_kind: "device",
    aliases,
    disambiguation:
      "A separately identifiable synthetic device; ownership unknown",
    status: "active",
  },
});
const claim = (client_ref: string, extra: JsonObject = {}) => ({
  op: "create_record",
  kind: "knowledge",
  client_ref,
  title: "Resource access conditions",
  visibility: "workspace",
  data: {
    knowledge_kind: "fact",
    statement:
      "The user can use the workshop printer on weekdays with prior booking.",
    state: "current",
    basis: "user_statement",
    evidence_refs: [ref("source")],
    conditions: { access: "Weekdays only, prior booking; no ownership claim" },
    valid_from: null,
    valid_to: null,
    observed_at: null,
    supersedes_refs: [],
    representation: {
      kind: "English paraphrase",
      source_ref: ref("source"),
      source_language: "ru",
    },
    ...extra,
  },
});
function code(action: () => unknown, expected: string) {
  assert.throws(
    action,
    (e: unknown) => e instanceof CoreError && e.code === expected,
  );
}
const domain = (d: DiskStorage) =>
  JSON.stringify(
    [
      "records",
      "revisions",
      "changes",
      "receipts",
      "relations",
      "relation_history",
      "memory_docs",
      "memory_text",
      "memory_names",
      "memory_meta",
    ].map((t) => d.all("SELECT * FROM " + t + " ORDER BY rowid")),
  );

test("D final Concept graph allows multiple parents, preserves ambiguous aliases and rejects direct/batch cycles and wrong kinds atomically", (t) => {
  const f = fixture();
  t.after(() => f.disk.close());
  const a = f.commit([
    concept("root"),
    concept("other"),
    concept("child", [ref("root"), ref("other")]),
    entity("one", [ref("child")], "Argo", ["Арго"]),
    entity("two", [ref("child")], "Argo", ["Арго"]),
  ]).created;
  const before = domain(f.disk);
  code(() => f.commit([concept("loop", [ref("loop")])]), "GRAPH_CYCLE");
  code(
    () => f.commit([concept("a", [ref("b")]), concept("b", [ref("a")])]),
    "GRAPH_CYCLE",
  );
  code(
    () => f.commit([entity("wrong", [{ id: a.one }])]),
    "REFERENCE_TYPE_MISMATCH",
  );
  assert.equal(domain(f.disk), before);
  assert.equal(
    f.core.search({ query: "Арго", match: "phrase", channel: "names" }).data
      .cards.length,
    2,
  );
  assert.equal(f.core.browse("topics", a.root).data.cards[0].id, a.child);
  assert.equal(f.core.browse("topics", a.child).data.cards.length, 2);
  const root = f.read(a.root);
  code(
    () =>
      f.commit(
        [
          {
            op: "update_record",
            ref: { id: a.root },
            data: { ...root.data, broader_ids: [{ id: a.child }] },
          },
        ],
        [f.guard(a.root)],
      ),
    "GRAPH_CYCLE",
  );
  assert.equal(domain(f.disk), before);
});

test("D literal English FTS, exact authentic aliases, punctuation/metacharacters, meaningful filters and bounded cursors", (t) => {
  const f = fixture();
  t.after(() => f.disk.close());
  const a = f.commit([
    entity("aliases", [], "Running tool", [
      "O'Brien",
      "X-ray",
      "C++",
      'a "quoted" alias',
      "Принтер Ёж",
      "alpha OR beta",
    ]),
    entity("decoy", [], "Run tool", ["C"]),
    claim("k"),
  ]).created;
  assert.equal(
    f.core.search({ query: "runs", match: "all", channel: "working" }).data
      .cards.length,
    2,
  );
  assert.equal(
    f.core.search({ query: "runs", match: "all", channel: "names" }).data.cards
      .length,
    0,
  );
  for (const query of [
    "O'Brien",
    "X-ray",
    "C++",
    'a "quoted" alias',
    "Принтер Ёж",
    "alpha OR beta",
  ]) {
    const rows = f.core.search({
      query,
      match: "phrase",
      channel: "names",
      exact_name: true,
    }).data.cards;
    assert.deepEqual(
      rows.map((r) => r.id),
      [a.aliases],
    );
  }
  for (const query of [
    '" OR * NOT (x): NEAR(a b)',
    "*",
    '() : "',
    " ",
    "q".repeat(513),
  ]) {
    if (query.length > 512)
      assert.throws(() => f.core.search({ query, match: "all" }));
    else if (!/[\p{L}\p{N}]/u.test(query))
      code(() => f.core.search({ query, match: "all" }), "VALIDATION_ERROR");
    else
      assert.equal(f.core.search({ query, match: "all" }).data.cards.length, 0);
  }
  code(() => f.core.search({ limit: 1 }), "VALIDATION_ERROR");
  code(() => f.core.search({ query: "printer" }), "VALIDATION_ERROR");
  code(
    () => f.core.search({ query: Array(34).fill("x").join(" "), match: "all" }),
    "VALIDATION_ERROR",
  );
  assert.equal(
    f.core.search({
      query: "weekdays printer",
      match: "all",
      kinds: ["knowledge"],
    }).data.cards.length,
    1,
  );
  assert.equal(
    f.core.search({
      query: "unicorn printer",
      match: "any",
      kinds: ["knowledge"],
    }).data.cards.length,
    1,
  );
  assert.equal(
    f.core.search({ query: "printer weekdays", match: "phrase" }).data.cards
      .length,
    0,
  );
  const first = f.core.search({ kinds: ["entity"], limit: 1 }).data;
  const second = f.core.search({
    kinds: ["entity"],
    limit: 1,
    cursor: first.next_cursor!,
  }).data;
  const forged = JSON.parse(
    Buffer.from(first.next_cursor!, "base64url").toString(),
  );
  forged.last++;
  code(
    () =>
      f.core.search({
        kinds: ["entity"],
        limit: 1,
        cursor: Buffer.from(JSON.stringify(forged)).toString("base64url"),
      }),
    "CURSOR_INVALIDATED",
  );
  assert.notEqual(first.cards[0].id, second.cards[0].id);
  assert.equal(second.has_more, false);
  code(
    () =>
      f.core.search({
        kinds: ["knowledge"],
        limit: 1,
        cursor: first.next_cursor!,
      }),
    "CURSOR_INVALIDATED",
  );
  f.commit([entity("third")]);
  code(
    () =>
      f.core.search({
        kinds: ["entity"],
        limit: 1,
        cursor: first.next_cursor!,
      }),
    "CURSOR_INVALIDATED",
  );
  code(
    () => f.core.search({ kinds: ["entity"], cursor: "not-a-cursor" }),
    "CURSOR_INVALIDATED",
  );
});

test("D independent lexical fallback ignores wrong classification and absent predicate; typed filters retain explicit applicability limits", (t) => {
  const f = fixture();
  t.after(() => f.disk.close());
  const ops = [
    concept("Botany"),
    entity("device", [ref("Botany")], "Unfamiliar machine"),
    claim("k", {
      object_ref: ref("device"),
      valid_from: "2026-01-01T00:00:00Z",
      valid_to: "2026-12-01T00:00:00Z",
      observed_at: "2025-12-01T00:00:00Z",
    }),
  ];
  const a = f.commit(ops).created;
  assert.equal(
    f.core.search({
      query: "printing printers",
      match: "any",
      kinds: ["knowledge"],
    }).data.cards[0].id,
    a.k,
  );
  assert.equal(
    f.core.search({ predicate: "has_access_to" }).data.cards.length,
    0,
  );
  assert.equal(
    f.core.search({
      object_id: a.device,
      valid_at: "2026-05-01T03:00:00+03:00",
    }).data.cards.length,
    1,
  );
  assert.equal(
    f.core.search({ object_id: a.device, valid_at: "2026-12-01T00:00:00Z" })
      .data.cards.length,
    0,
  );
  assert.equal(
    f.core.search({ observed_after: "2026-01-01T00:00:00Z" }).data.cards.length,
    0,
  );
  assert.equal(
    f.core.browse("records", a.device, 20, undefined, "current_claims").data
      .cards[0].id,
    a.k,
  );
  const r = f.read(a.k);
  assert.equal(r.data.valid_from, "2026-01-01T00:00:00Z");
});

test("D corrections preserve exact historical truth, conditions, grounded sources, FTS and semantic states without assigning unknown times", (t) => {
  const f = fixture();
  t.after(() => f.disk.close());
  const a = f.commit([
    entity("device"),
    claim("old", { object_ref: ref("device"), predicate: "has_access_to" }),
  ]).created;
  const old = f.read(a.old, 1);
  const b = f.commit(
    [
      {
        op: "resolve_knowledge",
        ref: { id: a.old },
        state: "superseded",
        reason: "Conditions changed, not a recording error",
        evidence_refs: [ref("source")],
        replacement_refs: [ref("new")],
      },
      claim("new", {
        statement: "The workshop printer is no longer available to the user.",
        object_ref: { id: a.device },
        predicate: "has_access_to",
        conditions: "Unavailable; do not use in the plan",
        supersedes_refs: [{ id: a.old, revision: 1 }],
      }),
    ],
    [f.guard(a.old)],
  ).created;
  assert.deepEqual(f.read(a.old, 1), old);
  assert.equal(f.read(a.old).data.state, "superseded");
  assert.equal(f.read(b.new).data.valid_from, null);
  assert.equal(
    f.core.search({ query: "weekdays", match: "all", states: ["current"] }).data
      .cards.length,
    0,
  );
  assert.equal(
    f.core.search({ query: "weekdays", match: "all", history: true }).data.cards
      .length,
    2,
  );
  f.commit(
    [
      {
        op: "resolve_knowledge",
        ref: { id: b.new },
        state: "retracted",
        reason:
          "This was an example; withdraw personal interpretation, no opposite fact",
        evidence_refs: [ref("source")],
        replacement_refs: [],
      },
    ],
    [f.guard(b.new)],
  );
  assert.equal(
    f.core.browse("records", a.device, 20, undefined, "current_claims").data
      .cards.length,
    0,
  );
  assert.equal(f.read(b.new).data.state, "retracted");
  assert.equal(f.read(b.new, 1).data.state, "current");
  f.commit([
    claim("contested-a", {
      state: "contested",
      conditions: "Source A: weekdays",
    }),
    claim("contested-b", {
      state: "contested",
      conditions: "Source B: weekends",
      statement: "A conflicting source reports weekend availability.",
    }),
  ]);
  assert.equal(f.core.search({ states: ["contested"] }).data.cards.length, 2);
  code(
    () =>
      f.commit([
        claim("missing", { evidence_refs: [], representation: undefined }),
      ]),
    "SOURCE_MISSING",
  );
  f.commit([
    claim("tentative", {
      state: "tentative",
      basis: "inference",
      evidence_refs: [],
      representation: undefined,
    }),
  ]);
  code(
    () =>
      f.commit([
        claim("reversed", {
          valid_from: "2027-01-01T00:00:00Z",
          valid_to: "2026-01-01T00:00:00Z",
        }),
      ]),
    "VALIDATION_ERROR",
  );
});

test("D identity clarification changes current references without merging similar objects or rewriting historical identities", (t) => {
  const f = fixture();
  t.after(() => f.disk.close());
  const a = f.commit([
    entity("one", [], "Argo"),
    entity("two", [], "Argo"),
    claim("k", { object_ref: ref("one") }),
  ]).created;
  const k = f.read(a.k);
  f.commit(
    [
      {
        op: "update_record",
        ref: { id: a.k },
        data: {
          ...k.data,
          object_ref: { id: a.two },
          evidence_refs: [ref("source")],
          representation: {
            kind: "English paraphrase",
            source_ref: ref("source"),
            source_language: "ru",
          },
        },
      },
    ],
    [f.guard(a.k)],
  );
  assert.deepEqual(f.read(a.k, 1).data.object_ref, { id: a.one });
  assert.deepEqual(f.read(a.k).data.object_ref, { id: a.two });
  assert.throws(() =>
    f.commit([
      {
        op: "create_record",
        kind: "entity",
        client_ref: "merge",
        title: "Merged",
        visibility: "workspace",
        data: {
          entity_kind: "device",
          aliases: [],
          disambiguation: "same",
          status: "merged",
          redirect_to: { id: a.two },
          approved: true,
        },
      },
    ]),
  );
});

test("D index and correction commit faults are all-or-none; unavailable index is explicit and rebuild is lossless", (t) => {
  const f = fixture();
  t.after(() => f.disk.close());
  const a = f.commit([claim("old")]).created;
  for (const point of [
    "after_records",
    "after_index",
    "before_commit",
    "after_commit",
  ]) {
    const current = f.read(a.old),
      before = domain(f.disk);
    const c = new Core(f.disk, f.core.context, (p) => {
      if (p === point) throw new Error("injected D fault");
    });
    assert.throws(
      () =>
        f.commit(
          [
            {
              op: "resolve_knowledge",
              ref: { id: a.old },
              state: "retracted",
              reason: "Recording error",
              evidence_refs: [ref("source")],
              replacement_refs: [],
            },
          ],
          [f.guard(a.old)],
          c,
        ),
      /injected/,
    );
    if (point !== "after_commit") assert.equal(domain(f.disk), before);
    else assert.equal(f.read(a.old).revision, current.revision + 1);
    assert.equal(
      f.core.search({ query: "printer", match: "all" }).data.cards[0].revision,
      f.read(a.old).revision,
    );
  }
  const before = JSON.stringify(f.disk.all("SELECT * FROM revisions"));
  f.disk.exec("DROP TABLE memory_text");
  code(
    () => f.core.search({ query: "printer", match: "all" }),
    "INDEX_UNAVAILABLE",
  );
  assert.equal(f.core.browse("knowledge").data.cards.length, 1);
  assert.equal(f.read(a.old).data.state, "retracted");
  assert.equal(f.core.diagnostics().data.index, "INDEX_UNAVAILABLE");
  f.core.rebuildIndex();
  assert.equal(
    f.core.search({ query: "printer", match: "all" }).data.cards.length,
    1,
  );
  assert.equal(JSON.stringify(f.disk.all("SELECT * FROM revisions")), before);
  f.disk.run("UPDATE memory_meta SET seq=-1");
  code(() => f.core.search({ kinds: ["knowledge"] }), "INDEX_UNAVAILABLE");
  f.core.rebuildIndex();
});

test("D managed restrictions cover all pages, counts, links, snippets, history, guessed IDs, diagnostics, technical rows and mutations", (t) => {
  const f = fixture(["restricted:read", "restricted:write"]);
  t.after(() => f.disk.close());
  const secret = {
    ...entity("secret", [], "SECRET DEVICE", ["SECRET ALIAS"]),
    visibility: "restricted",
  };
  const a = f.commit([
    secret,
    entity("public"),
    claim("hidden-dependant", { object_ref: ref("secret") }),
  ]).created;
  const guest = new Core(f.disk, { ...f.core.context, scopes: [] });
  const stringify = (v: unknown) => JSON.stringify(v);
  for (const value of [
    guest.map(),
    guest.browse("resources"),
    guest.browse("entities"),
    guest.search({ query: "SECRET", match: "all" }),
    guest.browse("operations"),
    guest.browse("changes"),
    guest.snapshot(),
    guest.diagnostics(),
  ]) {
    assert.doesNotMatch(stringify(value), /SECRET DEVICE|SECRET ALIAS/);
    assert.ok(!stringify(value).includes(a.secret));
    assert.ok(!stringify(value).includes(a["hidden-dependant"]));
  }
  for (const action of [
    () => guest.read(a.secret),
    () => guest.read(a.secret, 1),
    () => guest.read(a["hidden-dependant"]),
    () => guest.browse("records", a.secret),
    () => guest.search({ object_id: a.secret }),
    () => guest.operation("D-1"),
  ])
    code(action, "REFERENCE_NOT_FOUND");
  assert.equal(guest.search({ kinds: ["entity"] }).data.cards.length, 1);
  const before = domain(f.disk);
  code(
    () =>
      f.commit(
        [
          {
            op: "update_record",
            ref: { id: a.secret },
            data: f.read(a.secret).data,
          },
        ],
        [f.guard(a.secret)],
        guest,
      ),
    "REFERENCE_NOT_FOUND",
  );
  assert.equal(domain(f.disk), before);
  const visibleBefore = guest.search({ kinds: ["entity"], limit: 1 }).data;
  const oldGeneration = visibleBefore.generation;
  f.commit([
    { ...entity("secret2", [], "ANOTHER SECRET"), visibility: "restricted" },
  ]);
  assert.equal(
    guest.search({ kinds: ["entity"], limit: 1 }).data.generation,
    oldGeneration,
  );
  const privileged = f.core.search({ kinds: ["entity"], limit: 1 }).data;
  code(
    () =>
      guest.search({
        kinds: ["entity"],
        limit: 1,
        cursor: privileged.next_cursor!,
      }),
    "CURSOR_INVALIDATED",
  );
  // Unrelated public writes still work in a workspace containing hidden records.
  f.commit([entity("public2")], [], guest);
});

test("D registered relations validate endpoints and reject competing copies of typed grounds", (t) => {
  const f = fixture();
  t.after(() => f.disk.close());
  const a = f.commit([entity("one"), entity("two"), claim("k")]).created;
  const r = f.commit(
    [
      {
        op: "put_relation",
        client_ref: "link",
        relation: "related",
        from_ref: { id: a.one },
        to_ref: { id: a.two },
        reason: "Nearby alternatives, not identity",
      },
    ],
    [f.guard(a.one), f.guard(a.two)],
  ).created.link;
  const links = f.core.browse("relations", a.one).data.cards as JsonObject[];
  assert.equal(links[0].symmetric, true);
  code(
    () =>
      f.commit(
        [
          {
            op: "put_relation",
            client_ref: "bad",
            relation: "supports",
            from_ref: { id: a.one },
            to_ref: { id: a.k },
            reason: "Invalid endpoint",
          },
        ],
        [f.guard(a.one), f.guard(a.k)],
      ),
    "REFERENCE_TYPE_MISMATCH",
  );
  code(
    () =>
      f.commit(
        [
          {
            op: "put_relation",
            client_ref: "bad",
            relation: "supports",
            from_ref: { id: a.source },
            to_ref: { id: a.k },
            reason: "Duplicate grounds",
          },
        ],
        [f.guard(a.source), f.guard(a.k)],
      ),
    "VALIDATION_ERROR",
  );
  f.commit(
    [{ op: "remove_relation", relation_id: r }],
    [f.guard(a.one), f.guard(a.two)],
  );
  assert.equal(f.core.browse("relations").data.cards.length, 0);
  assert.equal(f.disk.all("SELECT * FROM relation_history").length, 2);
});

test("D schema-2 migration faults preserve filled canonical rows, original materials, backup and repeatability", (t) => {
  for (const point of [
    "memory_after_backup",
    "memory_before_schema_commit",
    "memory_after_schema_commit",
  ]) {
    const f = fixture();
    const file = join(f.home, "fixture.md"),
      bytes = Buffer.from("\ufeffOriginal 🦉\r\n" + "retained ".repeat(1200));
    writeFileSync(file, bytes);
    const m = f.disk.importFile(file, [f.home]),
      s = f.core.capture(m.text, "file", null, m);
    f.core.commit({
      request_id: "material",
      reason: "Keep original",
      source_handles: [s.source_handle],
      guards: [],
      ops: [
        {
          op: "import_evidence",
          client_ref: "m",
          source_handle: s.source_handle,
          title: "Original",
          source_language: "en",
        },
      ],
    });
    const tables = [
      "records",
      "revisions",
      "changes",
      "receipts",
      "intents",
      "focus",
      "claims",
      "handoffs",
    ];
    const before = JSON.stringify(
      tables.map((t) => f.disk.all("SELECT * FROM " + t)),
    );
    f.disk.workspace.schema_version = 2;
    f.disk.run("UPDATE meta SET json=?", JSON.stringify(f.disk.workspace));
    f.disk.exec(
      "DROP TABLE memory_text; DROP TABLE memory_names; DROP TABLE memory_docs; DROP TABLE memory_meta; DROP TABLE memberships; DROP TABLE concept_parents; DROP TABLE relations; DROP TABLE relation_history; DROP TABLE retrieval_trace; DROP INDEX knowledge_predicate; DROP INDEX knowledge_subject; DROP INDEX knowledge_object; PRAGMA user_version=2;",
    );
    writeFileSync(
      join(f.home, "workspace.json"),
      JSON.stringify(f.disk.workspace),
    );
    f.disk.close();
    assert.throws(
      () =>
        new DiskStorage(f.home, (p) => {
          if (p === point) throw new Error("migration interruption");
        }),
      /interruption/,
    );
    const recovered = new DiskStorage(f.home);
    t.after(() => recovered.close());
    assert.equal(recovered.workspace.schema_version, 3);
    assert.equal(
      JSON.stringify(tables.map((t) => recovered.all("SELECT * FROM " + t))),
      before,
    );
    assert.deepEqual(
      readFileSync(join(f.home, "materials", m.blob_ref)),
      bytes,
    );
    const receipt = JSON.parse(
      recovered.get<{ json: string }>(
        "SELECT json FROM migrations WHERE version=3",
      )!.json,
    );
    assert.equal(digest(readFileSync(receipt.backup)), receipt.backup_sha256);
    assert.ok(
      readdirSync(f.home).filter((s) => s.startsWith("pre-schema-3-")).length >=
        1,
    );
    recovered.close();
    const again = new DiskStorage(f.home);
    again.close();
  }
});

test("D next request snapshot routes changed Work premises with exact revisions, no general fact injection and a measured byte budget", (t) => {
  const f = fixture();
  t.after(() => f.disk.close());
  const a = f.commit([
    claim("k"),
    {
      op: "create_record",
      client_ref: "work",
      kind: "work",
      title: "Paper cards",
      visibility: "workspace",
      data: {
        activity_id: null,
        parent_work_id: null,
        objective: "Prepare paper cards",
        acceptance: [
          {
            criterion_id: "cards",
            description: "Useful cards",
            verification: "Inspect actual cards",
            required: true,
          },
        ],
        status: "active",
        current_state: "Planning",
        next_action: "Read current resource conditions",
        steps: [],
        waits: [],
        context_refs: [ref("k")],
        completion: null,
      },
    },
  ]).created;
  const before = f.core.snapshot();
  assert.ok(!JSON.stringify(before).includes("prior booking"));
  f.commit(
    [
      {
        op: "resolve_knowledge",
        ref: { id: a.k },
        state: "retracted",
        reason: "Recorded incorrectly",
        evidence_refs: [ref("source")],
        replacement_refs: [],
      },
    ],
    [f.guard(a.k)],
  );
  const next = f.core.snapshot();
  assert.equal(next.context_current[0].revision, 2);
  assert.equal(next.context_current[0].state, "retracted");
  assert.equal(next.context_current[0].must_read, true);
  assert.notEqual(next.generation, before.generation);
  assert.equal(f.read(a.k, 1).data.state, "current");
  const traces = f.core.diagnostics().data.retrieval_trace;
  assert.ok(
    traces.some(
      (v) =>
        v.operation === "read" &&
        v.refs.some(
          (r: { id: string; revision: number }) =>
            r.id === a.k && r.revision === 1,
        ),
    ),
  );
  assert.ok(Buffer.byteLength(JSON.stringify(next)) <= next.byte_budget);
  // A full Work can exceed the snapshot budget; route it rather than dropping qualifications.
  const w = f.read(a.work);
  const large = f.commit([
    {
      op: "create_record",
      client_ref: "large",
      kind: "work",
      title: "Large current plan",
      visibility: "workspace",
      data: {
        ...w.data,
        current_state: "x".repeat(3990),
        next_action: "y".repeat(3990),
        objective: "z".repeat(3990),
      },
    },
  ]).created.large;
  const bounded = f.core.snapshot();
  assert.ok(bounded.must_read.includes(large));
  assert.equal(bounded.incomplete, true);
  assert.ok(Buffer.byteLength(JSON.stringify(bounded)) <= bounded.byte_budget);
});

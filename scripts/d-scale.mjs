// Developer-only, deterministic synthetic scale and live-discovery fixtures.
// Uses installed Pi's existing TS loader; no model, new runtime or product installer.
import assert from "node:assert/strict";
import { createRequire } from "node:module";
import { pathToFileURL } from "node:url";
import { join, resolve } from "node:path";
import { mkdirSync, writeFileSync } from "node:fs";
const [pkgArg, rootArg, mode = "scale"] = process.argv.slice(2);
const pkg = resolve(pkgArg),
  root = resolve(rootArg);
mkdirSync(root, { recursive: true });
const { createJiti } = createRequire(pathToFileURL(process.env.ZARA_PI_SDK))(
  "jiti",
);
const jiti = createJiti(import.meta.url);
const { Core } = await jiti.import(join(pkg, "src/core/index.ts"));
const { DiskStorage } = await jiti.import(join(pkg, "src/storage/index.ts"));
const home = join(root, "home"),
  disk = new DiskStorage(home);
const core = new Core(disk, {
  ...disk.workspace,
  principal: "trusted-personal",
  session_id: "synthetic-D-fixture",
  runtime_id: "synthetic-D-fixture",
  can_write: true,
  processing_allowed: true,
});
const original =
  "Синтетический каталог. В мастерской доступен резограф «Тихий берег» по будням после предварительной записи. Это доступ, а не собственность. Для бумажных тиражей карточек он подходит, но в воскресенье недоступен. В другом помещении у знакомого есть одноимённый аппарат; пользователь только хочет купить собственный.";
const source = core.capture(original, "rpc", "synthetic-mechanical-fixture");
let serial = 0;
const commit = (ops, guards = []) =>
  core.commit({
    request_id: "D-fixture-" + ++serial,
    reason: "Fixed synthetic corpus, not model-saved evidence",
    source_handles: [source.source_handle],
    guards,
    ops,
  });
const initial = commit([
  {
    op: "import_evidence",
    client_ref: "e",
    source_handle: source.source_handle,
    title: "Original synthetic catalog notes",
    source_language: "ru",
  },
]);
const evidence = { id: initial.created.e, revision: 1 };
const concepts = [],
  entities = [],
  claims = [],
  timings = [];
const run = (label, fn) => {
  const start = performance.now(),
    result = fn();
  timings.push({
    label,
    ms: performance.now() - start,
    bytes: Buffer.byteLength(JSON.stringify(result)),
  });
  return result;
};
const ccount = mode === "scale" ? 96 : 6,
  ecount = mode === "scale" ? 128 : 5,
  kcount = mode === "scale" ? 2048 : 8;
for (let n = 0; n < ccount; n++) {
  const parents =
    n === 0 || n === ccount - 1
      ? []
      : n < 12
        ? [{ id: concepts[n - 1] }]
        : [{ id: concepts[0] }, ...(n % 7 === 0 ? [{ id: concepts[1] }] : [])];
  const r = commit([
    {
      op: "create_record",
      client_ref: "c",
      kind: "concept",
      title:
        n === 0
          ? "Physical production"
          : n === 1
            ? "Printmaking"
            : n === ccount - 1
              ? "Botanical field notes"
              : "Catalog branch " + n,
      visibility: "workspace",
      data: {
        definition:
          "A bounded synthetic navigation branch, not inherited personal properties",
        aliases: ["Раздел " + n],
        broader_ids: parents,
        status: "active",
        boundary_notes: "Specific catalog grouping, not identity",
      },
    },
  ]);
  concepts.push(r.created.c);
}
for (let start = 0; start < ecount; start += 19) {
  const ops = Array.from({ length: Math.min(19, ecount - start) }, (_, i) => {
    const n = start + i;
    return {
      op: "create_record",
      client_ref: "e" + n,
      kind: "entity",
      title:
        n === 0
          ? "Quiet Shore"
          : n === 1
            ? "Quiet Shore (friend's device)"
            : n === 2
              ? "Quiet Shore (purchase candidate)"
              : "Synthetic device " + n,
      visibility: "workspace",
      concept_ids: [{ id: concepts[n % ccount] }],
      data: {
        entity_kind: mode === "fallback" && n === 0 ? "other" : "device",
        aliases: n < 3 ? ["Тихий берег"] : ["Unit-" + n],
        disambiguation:
          n === 0
            ? "Workshop duplicator mentioned in source; access only, ownership unknown"
            : n === 1
              ? "Friend's separate device; no user access established"
              : n === 2
                ? "Desired future purchase, not a currently available user resource"
                : "Distinct synthetic inventory item " + n,
        status: "active",
      },
    };
  });
  const r = commit(ops);
  for (const op of ops) entities.push(r.created[op.client_ref]);
}
for (let start = 0; start < kcount; start += 19) {
  const ops = Array.from({ length: Math.min(19, kcount - start) }, (_, i) => {
    const n = start + i,
      important = n === 0;
    return {
      op: "create_record",
      client_ref: "k" + n,
      kind: "knowledge",
      title: important
        ? "Workshop resource conditions"
        : "Synthetic observation " + n,
      visibility: "workspace",
      // Deliberately wrong classification for lexical fallback; no structural predicate.
      concept_ids: [{ id: concepts[important ? ccount - 1 : n % ccount] }],
      data: {
        knowledge_kind: "fact",
        statement: important
          ? "The user has access to a risograph duplicator named Quiet Shore for printing paper card batches at the workshop; ownership is not established."
          : n === 1
            ? "A friend has another similarly named duplicator; user access is not established."
            : n === 2
              ? "The user wishes to purchase a duplicator; this is not a currently available resource."
              : "Synthetic numbered observation " +
                n +
                " about artifact production and stored conditions.",
        state: n === 3 || n === 4 ? "contested" : "current",
        basis: "user_statement",
        object_ref: { id: entities[n % ecount] },
        evidence_refs: [evidence],
        conditions: important
          ? "Weekdays only, prior booking; unavailable on Sunday. Do not infer ownership, working condition or other unreported capabilities."
          : n === 3
            ? "Source A reports weekday-only access"
            : n === 4
              ? "Source B reports weekend-only access"
              : "Only the explicitly described synthetic case; no general availability inference",
        valid_from: null,
        valid_to: null,
        observed_at: null,
        supersedes_refs: [],
        representation: {
          kind: "English paraphrase",
          source_ref: evidence,
          source_language: "ru",
        },
      },
    };
  });
  const r = run("seed-batch-" + start, () => commit(ops));
  for (const op of ops) claims.push(r.created[op.client_ref]);
}
const before = core.read(claims[7]).data;
commit(
  [
    {
      op: "update_record",
      ref: { id: before.id },
      data: {
        ...before.data,
        conditions: "Revised synthetic condition; prior version retained",
      },
    },
  ],
  [{ ref: { id: before.id }, expected_revision: before.revision }],
);
assert.equal(
  core.read(claims[7], 1).data.data.conditions,
  "Only the explicitly described synthetic case; no general availability inference",
);
const map = run("map", () => core.map());
const branches = run("wide-branch-page", () =>
  core.browse("topics", concepts[0], 20),
);
const search = run("independent-lexical", () =>
  core.search({
    query: "risograph printing",
    match: "all",
    kinds: ["knowledge"],
    limit: 20,
  }),
);
assert.equal(search.data.cards[0].id, claims[0]);
const snapshot = run("snapshot", () => core.snapshot());
assert.ok(!JSON.stringify(snapshot).includes("risograph"));
assert.ok(!JSON.stringify(search).includes("Weekdays only"));
const exact = run("selected-claim-read", () => core.read(claims[0]));
assert.match(JSON.stringify(exact), /Weekdays only/);
let cursor,
  pages = 0,
  cardCount = 0,
  totalPageBytes = 0,
  first;
do {
  const page = run("all-claims-page-" + pages, () =>
    core.search({
      kinds: ["knowledge"],
      limit: 50,
      ...(cursor ? { cursor } : {}),
    }),
  ).data;
  first ??= page;
  cardCount += page.cards.length;
  totalPageBytes += Buffer.byteLength(JSON.stringify(page));
  pages++;
  cursor = page.next_cursor;
} while (cursor);
assert.equal(cardCount, kcount);
const trace = core.diagnostics().data;
assert.ok(trace.retrieval_trace.length <= 20);
writeFileSync(
  join(root, "observations.json"),
  JSON.stringify(
    {
      synthetic: true,
      mode,
      counts: { concepts: ccount, entities: ecount, knowledge: kcount },
      home,
      ids: { concepts, entities, claims, evidence },
      depth: 12,
      aliases: "preserved Cyrillic; ambiguous names remain separate",
      wrong_classification: claims[0],
      missing_predicate: true,
      versions: 2,
      ...(mode !== "scale"
        ? {
            corpus: disk
              .all("SELECT json FROM records")
              .map((r) => JSON.parse(r.json)),
            history: disk
              .all("SELECT json FROM revisions")
              .map((r) => JSON.parse(r.json)),
          }
        : {}),
      contested: 2,
      map,
      branches,
      search,
      snapshot,
      exact,
      pages,
      cardCount,
      totalPageBytes,
      first,
      timings,
      trace,
    },
    null,
    2,
  ),
);
disk.close();
console.log(
  JSON.stringify(
    {
      mode,
      counts: { concepts: ccount, entities: ecount, knowledge: kcount },
      pages,
      cardCount,
      totalPageBytes,
      query_ms: timings.filter((t) => !t.label.startsWith("seed")),
      home,
    },
    null,
    2,
  ),
);

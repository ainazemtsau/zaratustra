import { randomUUID } from "node:crypto";
import { canonical, requireThat } from "./contracts.ts";
import type { AddressedRow, JsonObject, StoragePort } from "./contracts.ts";
import { sleepAccessRefs } from "./sleep.ts";

export const MemoryIndexSchemaSQL = `
CREATE TABLE memory_index_meta(singleton INTEGER PRIMARY KEY CHECK(singleton=1),format INTEGER NOT NULL,incarnation TEXT NOT NULL,ready INTEGER NOT NULL,public_generation INTEGER NOT NULL,all_generation INTEGER NOT NULL);
INSERT INTO memory_index_meta VALUES(1,2,'',0,0,0);
CREATE TABLE memory_ordinals(ordinal INTEGER PRIMARY KEY AUTOINCREMENT,collection TEXT NOT NULL,identity TEXT NOT NULL,UNIQUE(collection,identity));
CREATE INDEX memory_ordinal_window ON memory_ordinals(collection,ordinal);
CREATE INDEX memory_access_restricted ON memory_docs(restricted,id,revision);
CREATE TABLE memory_nodes(node TEXT PRIMARY KEY,seed INTEGER NOT NULL,restricted INTEGER NOT NULL);
CREATE TABLE memory_edges(source TEXT NOT NULL,target TEXT NOT NULL,origin TEXT NOT NULL,PRIMARY KEY(source,target,origin));
CREATE INDEX memory_reverse_edge ON memory_edges(target,source);
CREATE INDEX memory_edge_origin ON memory_edges(origin,source);
CREATE TABLE memory_dirty(kind TEXT NOT NULL,id TEXT NOT NULL,revision INTEGER NOT NULL DEFAULT 0,PRIMARY KEY(kind,id,revision));
CREATE TABLE memory_technical(collection TEXT NOT NULL,identity TEXT NOT NULL,restricted INTEGER NOT NULL,sequence INTEGER,PRIMARY KEY(collection,identity));
CREATE INDEX memory_visible_changes ON memory_technical(collection,restricted,sequence);
CREATE INDEX memory_change_sequence ON memory_technical(collection,sequence);
CREATE TABLE memory_pending(node TEXT PRIMARY KEY,prior_restricted INTEGER,changed INTEGER NOT NULL);`;

type Ref = { id: string; revision?: number; content_version?: number };
const ckey = (id: string) => canonical(["current", id]);
const vkey = (id: string, revision: number) =>
  canonical(["version", id, revision]);
const hkey = (id: string) => canonical(["history", id]);
const tkey = (collection: string, id: string) =>
  canonical(["technical", collection, id]);
const bkey = (collection: string, id: string) =>
  canonical(["technical-body", collection, id]);
export const historyIdentity = (id: string, revision: number) =>
  canonical([id, revision]);

const refKeys = new Set(["id", "revision", "content_version"]);
const recordKinds = new Set([
  "activity",
  "work",
  "knowledge",
  "evidence",
  "concept",
  "entity",
  "method",
  "run",
  "evaluation",
  "signal",
  "signal_review",
  "invocation",
  "environment",
]);
const validId = (v: unknown): v is string =>
  typeof v === "string" && v.length > 0 && v.length <= 4000;
const revisionNumber = (v: unknown): v is number =>
  typeof v === "number" && Number.isSafeInteger(v) && v > 0;
const objectValue = (v: unknown): JsonObject | undefined =>
  v && typeof v === "object" && !Array.isArray(v)
    ? (v as JsonObject)
    : undefined;
const pureRef = (v: JsonObject): boolean =>
  validId(v.id) &&
  Object.keys(v).every((k) => refKeys.has(k)) &&
  (v.revision === undefined || revisionNumber(v.revision)) &&
  (v.content_version === undefined || revisionNumber(v.content_version));
const changedRef = (v: JsonObject): boolean =>
  validId(v.id) &&
  Object.keys(v).every((k) =>
    ["id", "before_revision", "after_revision"].includes(k),
  ) &&
  (v.before_revision === null || revisionNumber(v.before_revision)) &&
  revisionNumber(v.after_revision);
const recordIdentity = (v: JsonObject): boolean =>
  validId(v.id) &&
  typeof v.kind === "string" &&
  recordKinds.has(v.kind) &&
  revisionNumber(v.revision);
const revisionPair = (v: unknown): boolean => {
  const o = objectValue(v);
  return (
    !!o &&
    Object.keys(o).every((k) => ["before", "after"].includes(k)) &&
    (o.before === null || revisionNumber(o.before)) &&
    revisionNumber(o.after)
  );
};

/** Only declared reference shapes participate in access/retention. Prose is never an ID. */
export function addressedIds(value: unknown, technicalKeys = false): string[] {
  const found = new Set<string>();
  const add = (v: unknown) => {
    if (validId(v)) found.add(v);
  };
  const walk = (v: unknown, field?: string) => {
    if (Array.isArray(v)) {
      if (technicalKeys && field === "affected_ids") v.forEach(add);
      else v.forEach((item) => walk(item, field));
      return;
    }
    const o = objectValue(v);
    if (!o) return;
    if (
      pureRef(o) ||
      recordIdentity(o) ||
      (technicalKeys && field === "changed_refs" && changedRef(o))
    )
      add(o.id);
    if (technicalKeys) {
      if (field === "changed")
        for (const [key, item] of Object.entries(o))
          if (revisionPair(item)) add(key);
      if (["new_revisions", "guards"].includes(field ?? ""))
        for (const [key, item] of Object.entries(o))
          if (revisionNumber(item)) add(key);
      if (field === "created") Object.values(o).forEach(add);
      if (typeof o.token === "string" && validId(o.work_id)) add(o.work_id);
      if (o.kind === "library" && validId(o.record_id)) add(o.record_id);
    }
    for (const [key, item] of Object.entries(o)) walk(item, key);
  };
  walk(value);
  return [...found];
}
export function addressedRefs(value: unknown): Ref[] {
  const refs: Ref[] = [];
  const walk = (v: unknown) => {
    if (Array.isArray(v)) v.forEach(walk);
    else {
      const o = objectValue(v);
      if (!o) return;
      if (pureRef(o)) refs.push(o as Ref);
      Object.values(o).forEach(walk);
    }
  };
  walk(value);
  return refs;
}

/** SQL equivalent for legacy/read-only technical filtering; same declared shapes as JS. */
export function addressedIdsSQL(json: string): string {
  const o = "(CASE WHEN ref.type='object' THEN ref.value ELSE '{}' END)";
  const id = `json_extract(${o},'$.id')`;
  const positive = (p: string) =>
    `(json_type(${o},'$.${p}')='integer' AND json_extract(${o},'$.${p}') BETWEEN 1 AND 9007199254740991)`;
  const pure = `NOT EXISTS(SELECT 1 FROM json_each(${o}) k WHERE k.key NOT IN ('id','revision','content_version')) AND (json_type(${o},'$.revision') IS NULL OR ${positive("revision")}) AND (json_type(${o},'$.content_version') IS NULL OR ${positive("content_version")})`;
  const changed = `(ref.path LIKE '%.changed_refs' OR ref.path LIKE '%."changed_refs"') AND NOT EXISTS(SELECT 1 FROM json_each(${o}) k WHERE k.key NOT IN ('id','before_revision','after_revision')) AND (json_type(${o},'$.before_revision')='null' OR ${positive("before_revision")}) AND ${positive("after_revision")}`;
  const record = `json_extract(${o},'$.kind') IN (${[...recordKinds].map((k) => "'" + k + "'").join(",")}) AND ${positive("revision")}`;
  const map = "(CASE WHEN map.type='object' THEN map.value ELSE '{}' END)";
  const pair = "(CASE WHEN item.type='object' THEN item.value ELSE '{}' END)";
  const pairRevision = (p: string) =>
    `(json_type(${pair},'$.${p}')='integer' AND json_extract(${pair},'$.${p}') BETWEEN 1 AND 9007199254740991)`;
  return `SELECT ${id} AS id FROM json_tree(${json}) ref WHERE ref.type='object' AND json_type(${o},'$.id')='text' AND length(${id}) BETWEEN 1 AND 4000 AND ((${pure}) OR (${changed}) OR (${record}))
    UNION SELECT item.key AS id FROM json_tree(${json}) map JOIN json_each(${map}) item WHERE map.type='object' AND length(item.key) BETWEEN 1 AND 4000 AND ((map.key IN ('new_revisions','guards') AND item.type='integer' AND item.value BETWEEN 1 AND 9007199254740991) OR (map.key='changed' AND item.type='object' AND NOT EXISTS(SELECT 1 FROM json_each(${pair}) k WHERE k.key NOT IN ('before','after')) AND (json_type(${pair},'$.before')='null' OR ${pairRevision("before")}) AND ${pairRevision("after")}))
    UNION SELECT item.value AS id FROM json_tree(${json}) map JOIN json_each(CASE WHEN map.type='object' OR map.type='array' THEN map.value ELSE '{}' END) item WHERE ((map.type='object' AND map.key='created') OR (map.type='array' AND map.key='affected_ids')) AND item.type='text' AND length(item.value) BETWEEN 1 AND 4000
    UNION SELECT json_extract(${o},'$.work_id') AS id FROM json_tree(${json}) ref WHERE ref.type='object' AND json_type(${o},'$.token')='text' AND json_type(${o},'$.work_id')='text' AND length(json_extract(${o},'$.work_id')) BETWEEN 1 AND 4000
    UNION SELECT json_extract(${o},'$.record_id') AS id FROM json_tree(${json}) ref WHERE ref.type='object' AND json_extract(${o},'$.kind')='library' AND json_type(${o},'$.record_id')='text' AND length(json_extract(${o},'$.record_id')) BETWEEN 1 AND 4000`;
}
const sleepOperations = (json: string, path: string) =>
  `EXISTS(SELECT 1 FROM json_each(${json},'${path}') op WHERE json_extract(op.value,'$.op') IN ('start_sleep','sleep_checkpoint'))`;
export const unknownSleepPreparation = (json: string) =>
  `((coalesce(json_extract(${json},'$.status'),'')<>'committed' AND coalesce(json_extract(${json},'$.visibility'),'') NOT IN ('workspace','restricted') AND ${sleepOperations(json, "$.payload.ops")}) OR (coalesce(json_extract(${json},'$.kind'),'')='preview' AND coalesce(json_extract(${json},'$.payload.action'),'')='commit' AND ${sleepOperations(json, "$.payload.exact.ops")} AND (coalesce(json_type(${json},'$.payload.scopes'),'')<>'array' OR EXISTS(SELECT 1 FROM json_each(${json},'$.payload.scopes') scope WHERE scope.value='restricted:read'))))`;

const tables: Record<string, string> = {
  intents: "request_id",
  changes: "seq",
  handoffs: "id",
  claims: "token",
  relations: "id",
};
export function memoryIndexReady(db: StoragePort) {
  if (!db.get("SELECT name FROM sqlite_schema WHERE name='memory_index_meta'"))
    return false;
  const state = db.get<{ ready: number; format: number }>(
    "SELECT ready,format FROM memory_index_meta WHERE singleton=1",
  );
  return state?.ready === 1 && state.format === 2;
}
export function memoryIndexIdentity(db: StoragePort) {
  return db.get("SELECT name FROM sqlite_schema WHERE name='memory_index_meta'")
    ? (db.get<{ incarnation: string }>(
        "SELECT incarnation FROM memory_index_meta WHERE singleton=1",
      )?.incarnation ?? "legacy")
    : "legacy";
}
/** A readonly connection cannot silently trust an interrupted derived refresh. */
export function assertMemoryIndexReadable(db: StoragePort) {
  if (
    db.readonly &&
    db.get("SELECT name FROM sqlite_schema WHERE name='memory_index_meta'")
  )
    requireThat(
      !db.get("SELECT 1 FROM memory_dirty LIMIT 1"),
      "INDEX_UNAVAILABLE",
      "Derived access indexes need recovery by a writable command; preserve this read-only connection.",
    );
}
/** Install after all domain tables exist; dirty keys capture exact deltas. */
export function initializeMemoryIndex(db: StoragePort) {
  if (!db.get("SELECT name FROM sqlite_schema WHERE name='memory_index_meta'"))
    db.exec(MemoryIndexSchemaSQL);
  if (db.get("SELECT name FROM sqlite_schema WHERE name='sleep_items'"))
    db.exec(
      "CREATE INDEX IF NOT EXISTS sleep_prior_item ON sleep_items(json_extract(json,'$.prior_item_id'));",
    );
  const format = db.get<{ format: number }>(
    "SELECT format FROM memory_index_meta WHERE singleton=1",
  )?.format;
  requireThat(
    format === 1 || format === 2,
    "INDEX_UNAVAILABLE",
    "Unsupported derived access format; preserve the store.",
  );
  if (format === 1) {
    requireThat(
      !db.readonly,
      "INDEX_UNAVAILABLE",
      "Typed access index needs a writable rebuild.",
    );
    db.run("UPDATE memory_index_meta SET format=2,ready=0 WHERE singleton=1");
  }
  if (
    db.get(
      "SELECT name FROM sqlite_schema WHERE type='trigger' AND name='memory_dirty_sleep_reviews_delete'",
    )
  )
    return;
  for (const table of [
    "records",
    "experience_rows",
    "revisions",
    "experience_versions",
    "sleep_items",
    "sleep_reviews",
    ...Object.keys(tables),
  ]) {
    if (!db.get("SELECT name FROM sqlite_schema WHERE name=?", table)) continue;
    const kind = ["records", "experience_rows"].includes(table)
      ? "current"
      : ["revisions", "experience_versions"].includes(table)
        ? "version"
        : table === "sleep_items"
          ? "sleep"
          : table === "sleep_reviews"
            ? "sleep_review"
            : table;
    const id = tables[table] ?? "id";
    for (const event of ["insert", "update", "delete"]) {
      const row = event === "delete" ? "OLD" : "NEW";
      // Batch/status changes do not alter existing access contributions. A resumed
      // episode does: only that binding update must revisit the review's items.
      const when =
        table === "sleep_reviews" && event === "update"
          ? " WHEN OLD.work_id<>NEW.work_id OR OLD.episode_id<>NEW.episode_id"
          : "";
      db.exec(`CREATE TRIGGER IF NOT EXISTS memory_dirty_${table}_${event} AFTER ${event.toUpperCase()} ON ${table}${when} BEGIN
        INSERT INTO memory_dirty(kind,id,revision)
        SELECT '${kind}',cast(${row}.${id} AS TEXT),${kind === "version" ? row + ".revision" : 0}
        WHERE NOT EXISTS(SELECT 1 FROM memory_dirty WHERE kind='${kind}' AND id=cast(${row}.${id} AS TEXT) AND revision=${kind === "version" ? row + ".revision" : 0}); END;`);
    }
  }
}
function ordinal(db: StoragePort, collection: string, identity: string) {
  db.run(
    "INSERT OR IGNORE INTO memory_ordinals(collection,identity) VALUES(?,?)",
    collection,
    identity,
  );
}
function refNode(db: StoragePort, ref: Ref) {
  if (ref.revision !== undefined) return vkey(ref.id, ref.revision);
  if (ref.content_version !== undefined) {
    const row = db.get<{ revision: number }>(
      "SELECT revision FROM revisions WHERE id=? AND json_extract(json,'$.kind')='method' AND json_extract(json,'$.data.content_version')=? ORDER BY revision LIMIT 1",
      ref.id,
      ref.content_version,
    );
    return row ? vkey(ref.id, row.revision) : ckey(ref.id);
  }
  return ckey(ref.id);
}
function indexText(db: StoragePort, r: AddressedRow, rewrite: boolean) {
  let doc = db.get<{ docid: number }>(
    "SELECT docid FROM memory_docs WHERE id=? AND revision=?",
    r.id,
    r.revision,
  );
  if (doc && !rewrite) return;
  if (!doc) {
    db.run(
      "INSERT INTO memory_docs(id,revision,restricted) VALUES(?,?,?)",
      r.id,
      r.revision,
      1,
    );
    doc = db.get<{ docid: number }>(
      "SELECT docid FROM memory_docs WHERE id=? AND revision=?",
      r.id,
      r.revision,
    )!;
  } else {
    db.run("DELETE FROM memory_text WHERE rowid=?", doc.docid);
    db.run("DELETE FROM memory_names WHERE rowid=?", doc.docid);
  }
  const names = [
    r.title,
    ...((r.data.aliases as string[] | undefined) ?? []),
    ...Object.values((r.data.external_ids as JsonObject | undefined) ?? {}),
  ].join("\n");
  const working = [
    r.title,
    r.body ?? "",
    ...[
      "statement",
      "definition",
      "disambiguation",
      "purpose",
      "objective",
      "current_state",
      "next_action",
      "applicability",
      "instructions",
      "input_contract",
      "expected_output",
      "limitations",
      "summary",
    ].map((key) => r.data[key]),
    ...["context_requirements", "tool_requirements", "conditions"].map((key) =>
      r.data[key] ? canonical(r.data[key]) : null,
    ),
  ]
    .filter((v) => typeof v === "string")
    .join("\n");
  db.run("INSERT INTO memory_text(rowid,text) VALUES(?,?)", doc.docid, working);
  db.run("INSERT INTO memory_names(rowid,names) VALUES(?,?)", doc.docid, names);
}

/** Reverse closure includes old edges before replacement. Resetting the component
 * to intrinsic seeds removes restrictions correctly even inside reference cycles. */
export function refreshMemoryIndex(
  db: StoragePort,
  rebuild: boolean,
  rewrittenIds: readonly string[],
  changedIds?: readonly string[],
  finalize = true,
) {
  initializeMemoryIndex(db);
  const experience = !!db.get(
    "SELECT name FROM sqlite_schema WHERE type='view' AND name='addressed_current'",
  );
  const currentTable = experience ? "addressed_current" : "records";
  const versionsTable = experience ? "addressed_versions" : "revisions";
  const full = rebuild || !memoryIndexReady(db);
  if (full) {
    db.run(
      "UPDATE memory_index_meta SET ready=0,incarnation=? WHERE singleton=1",
      randomUUID(),
    );
    db.exec(
      "DELETE FROM memory_edges; DELETE FROM memory_nodes; DELETE FROM memory_technical;",
    );
    for (const r of db.all<{ id: string }>("SELECT id FROM " + currentTable))
      db.run("INSERT OR IGNORE INTO memory_dirty VALUES('current',?,0)", r.id);
    for (const r of db.all<{ id: string; revision: number }>(
      "SELECT id,revision FROM " + versionsTable,
    ))
      db.run(
        "INSERT OR IGNORE INTO memory_dirty VALUES('version',?,?)",
        r.id,
        r.revision,
      );
    for (const [table, key] of Object.entries(tables))
      for (const row of db.all<{ id: string }>(
        `SELECT cast(${key} AS TEXT) AS id FROM ${table}`,
      ))
        db.run(
          "INSERT OR IGNORE INTO memory_dirty VALUES(?,?,0)",
          table,
          row.id,
        );
    if (db.get("SELECT name FROM sqlite_schema WHERE name='sleep_items'"))
      for (const row of db.all<{ id: string }>("SELECT id FROM sleep_items"))
        db.run(
          "INSERT OR IGNORE INTO memory_dirty VALUES('sleep',?,0)",
          row.id,
        );
  }
  for (const id of changedIds ?? [])
    db.run("INSERT OR IGNORE INTO memory_dirty VALUES('current',?,0)", id);
  for (const id of rewrittenIds) {
    db.run("INSERT OR IGNORE INTO memory_dirty VALUES('current',?,0)", id);
    for (const r of db.all<{ revision: number }>(
      "SELECT revision FROM " + versionsTable + " WHERE id=?",
      id,
    ))
      db.run(
        "INSERT OR IGNORE INTO memory_dirty VALUES('version',?,?)",
        id,
        r.revision,
      );
  }
  const dirty = db.all<{ kind: string; id: string; revision: number }>(
    "SELECT kind,id,revision FROM memory_dirty",
  );
  const touched = new Set<string>(),
    affected = new Set<string>(),
    visibleWrites = new Set<string>();
  const baseline = (key: string, restriction: number | null) =>
    db.run(
      "INSERT OR IGNORE INTO memory_pending VALUES(?,?,0)",
      key,
      restriction,
    );
  const touch = (key: string) => {
    touched.add(key);
    for (const row of db.all<{ node: string; restricted: number | null }>(
      "WITH RECURSIVE affected(node) AS (SELECT ? UNION SELECT e.source FROM memory_edges e JOIN affected a ON e.target=a.node) SELECT a.node,n.restricted FROM affected a LEFT JOIN memory_nodes n ON n.node=a.node",
      key,
    )) {
      affected.add(row.node);
      baseline(row.node, row.restricted);
    }
  };
  const edge = (source: string, target: string, origin = "") =>
    db.run(
      "INSERT OR IGNORE INTO memory_edges VALUES(?,?,?)",
      source,
      target,
      origin,
    );
  const node = (key: string, seed: boolean) => {
    touch(key);
    db.run(
      "INSERT INTO memory_nodes VALUES(?,?,?) ON CONFLICT(node) DO UPDATE SET seed=excluded.seed",
      key,
      seed ? 1 : 0,
      seed ? 1 : 0,
    );
    db.run("DELETE FROM memory_edges WHERE source=? AND origin=''", key);
  };
  for (const d of dirty) {
    if (d.kind === "current" || d.kind === "version") {
      const current = d.kind === "current",
        key = current ? ckey(d.id) : vkey(d.id, d.revision);
      const stored = db.get<{ json: string }>(
        current
          ? "SELECT json FROM " + currentTable + " WHERE id=?"
          : "SELECT json FROM " + versionsTable + " WHERE id=? AND revision=?",
        ...(current ? [d.id] : [d.id, d.revision]),
      );
      const r = stored ? (JSON.parse(stored.json) as AddressedRow) : undefined;
      node(key, r?.visibility === "restricted");
      if (current) visibleWrites.add(key);
      if (!r) {
        db.run("DELETE FROM memory_nodes WHERE node=?", key);
        continue;
      }
      ordinal(
        db,
        current ? "current" : "history",
        current ? r.id : historyIdentity(r.id, r.revision),
      );
      for (const id of addressedIds(r)) edge(key, ckey(id));
      if (current) {
        edge(key, vkey(r.id, r.revision));
        db.run("DELETE FROM memberships WHERE record_id=?", r.id);
        db.run("DELETE FROM concept_parents WHERE child_id=?", r.id);
        if (r.storage !== "tombstone") {
          for (const ref of r.concept_ids)
            db.run(
              "INSERT OR IGNORE INTO memberships VALUES(?,?)",
              r.id,
              ref.id,
            );
          if (r.kind === "concept")
            for (const ref of r.data.broader_ids as { id: string }[])
              db.run(
                "INSERT OR IGNORE INTO concept_parents VALUES(?,?)",
                r.id,
                ref.id,
              );
        }
      } else {
        edge(key, ckey(r.id));
        for (const ref of addressedRefs(r)) edge(key, refNode(db, ref));
        const history = hkey(r.id);
        touch(history);
        db.run("INSERT OR IGNORE INTO memory_nodes VALUES(?,0,0)", history);
        edge(history, key);
        indexText(db, r, full || rewrittenIds.includes(r.id));
      }
    }
  }
  const sleepIds = new Set<string>();
  for (const d of dirty) {
    if (d.kind === "sleep_review")
      for (const row of db.all<{ id: string }>(
        "SELECT id FROM sleep_items WHERE review_id=?",
        d.id,
      ))
        sleepIds.add(row.id);
    if (d.kind === "sleep") sleepIds.add(d.id);
  }
  for (const id of [...sleepIds])
    for (const row of db.all<{ id: string }>(
      "WITH RECURSIVE descendants(id) AS (SELECT ? UNION SELECT i.id FROM sleep_items i JOIN descendants d ON json_extract(i.json,'$.prior_item_id')=d.id) SELECT id FROM descendants",
      id,
    ))
      sleepIds.add(row.id);
  for (const id of sleepIds) {
    const origin = "sleep:" + id;
    for (const row of db.all<{ source: string }>(
      "SELECT DISTINCT source FROM memory_edges WHERE origin=?",
      origin,
    ))
      touch(row.source);
    db.run("DELETE FROM memory_edges WHERE origin=?", origin);
    for (const [source, refs] of sleepAccessRefs(db, [id])) {
      touch(ckey(source));
      for (const ref of refs) edge(ckey(source), refNode(db, ref), origin);
    }
  }
  for (const d of dirty) {
    if (!(d.kind in tables)) continue;
    const key = tkey(d.kind, d.id);
    const row = db.get<{ json: string }>(
      `SELECT json FROM ${d.kind} WHERE ${tables[d.kind]}=?`,
      d.id,
    );
    const value: unknown = row ? JSON.parse(row.json) : null;
    const unknown =
      !!row &&
      !!db.get(
        `SELECT 1 FROM (SELECT ? AS json) candidate WHERE ${unknownSleepPreparation("candidate.json")}`,
        row.json,
      );
    const explicit =
      !!row &&
      !!db.get(
        "SELECT 1 FROM json_tree(?) WHERE key='visibility' AND atom='restricted' LIMIT 1",
        row.json,
      );
    const body = bkey(d.kind, d.id);
    node(body, unknown || explicit);
    node(key, false);
    edge(key, body);
    visibleWrites.add(key);
    if (!row) {
      db.run("DELETE FROM memory_nodes WHERE node IN (?,?)", key, body);
      db.run(
        "DELETE FROM memory_technical WHERE collection=? AND identity=?",
        d.kind,
        d.id,
      );
      continue;
    }
    ordinal(db, d.kind, d.id);
    for (const id of addressedIds(value, true)) edge(body, hkey(id));
    if (value && typeof value === "object") {
      for (const field of ["request_id", "transaction_id"]) {
        const id = (value as JsonObject)[field];
        if (typeof id === "string" && !(d.kind === "intents" && id === d.id))
          edge(key, bkey("intents", id));
      }
    }
    db.run(
      "INSERT INTO memory_technical VALUES(?,?,1,?) ON CONFLICT(collection,identity) DO UPDATE SET sequence=excluded.sequence",
      d.kind,
      d.id,
      d.kind === "changes" ? Number(d.id) : null,
    );
  }
  for (const key of touched) touch(key);
  db.exec(
    "UPDATE memory_nodes SET restricted=seed WHERE node IN (SELECT node FROM memory_pending)",
  );
  for (;;) {
    db.exec(
      "UPDATE memory_nodes SET restricted=1 WHERE restricted=0 AND node IN (SELECT node FROM memory_pending) AND EXISTS(SELECT 1 FROM memory_edges e JOIN memory_nodes target ON target.node=e.target WHERE e.source=memory_nodes.node AND target.restricted=1)",
    );
    if (!db.get<{ n: number }>("SELECT changes() AS n")!.n) break;
  }
  for (const key of visibleWrites)
    db.run("UPDATE memory_pending SET changed=1 WHERE node=?", key);
  for (const key of affected) {
    const restriction =
      db.get<{ restricted: number }>(
        "SELECT restricted FROM memory_nodes WHERE node=?",
        key,
      )?.restricted ?? 0;
    const parsed = JSON.parse(key) as [string, string, number | string];
    if (parsed[0] === "version")
      db.run(
        "UPDATE memory_docs SET restricted=? WHERE id=? AND revision=? AND restricted<>?",
        restriction,
        parsed[1],
        parsed[2],
        restriction,
      );
    if (parsed[0] === "technical")
      db.run(
        "UPDATE memory_technical SET restricted=? WHERE collection=? AND identity=? AND restricted<>?",
        restriction,
        parsed[1],
        parsed[2],
        restriction,
      );
  }
  db.run("UPDATE memory_index_meta SET ready=1 WHERE singleton=1");
  if (finalize) {
    const pending = db.all<{
      node: string;
      prior_restricted: number | null;
      changed: number;
      restricted: number;
      present: string | null;
    }>(
      "SELECT p.*,n.node AS present,coalesce(n.restricted,0) AS restricted FROM memory_pending p LEFT JOIN memory_nodes n ON n.node=p.node",
    );
    const publicChange =
      full ||
      pending.some((p) => {
        const type = (JSON.parse(p.node) as string[])[0];
        const priorVisible = p.prior_restricted === 0;
        const finalVisible = p.present !== null && !p.restricted;
        return (
          ["current", "technical"].includes(type) &&
          ((p.changed && (priorVisible || finalVisible)) ||
            priorVisible !== finalVisible)
        );
      });
    db.run(
      "UPDATE memory_index_meta SET public_generation=public_generation+?,all_generation=all_generation+? WHERE singleton=1",
      publicChange ? 1 : 0,
      pending.length || full ? 1 : 0,
    );
    db.exec("DELETE FROM memory_pending;");
  }
  db.exec("DELETE FROM memory_dirty;");
  db.run(
    "UPDATE memory_meta SET seq=(SELECT coalesce(max(seq),0) FROM changes),build=build+?",
    rebuild ? 1 : 0,
  );
}

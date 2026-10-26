import test from "node:test";
import { DatabaseSync } from "node:sqlite";
import assert from "node:assert/strict";
import {
  mkdtempSync,
  readFileSync,
  writeFileSync,
  existsSync,
  rmSync,
} from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import type { ExtensionContext } from "@earendil-works/pi-coding-agent";
import {
  Core,
  FileEffectSchema,
  managedDocument,
  type RecordRow,
} from "../src/core/index.ts";
import { DiskStorage, Administration } from "../src/storage/index.ts";
import { registerDocuments } from "../src/extension/documents.ts";

function fixture(fault?: (point: string) => void) {
  const project = mkdtempSync(join(tmpdir(), "zara-documents-"));
  let disk = new DiskStorage(join(project, ".local", "memory"));
  let core = new Core(
    disk,
    {
      ...disk.workspace,
      principal: "trusted-personal",
      session_id: "mechanical",
      runtime_id: "mechanical",
      processing_allowed: true,
      can_write: true,
      scopes: ["restricted:read", "restricted:write"],
    },
    fault,
  );
  const actions = new Map<string, (p: unknown) => Promise<unknown>>();
  const ctx = {
    cwd: project,
    isProjectTrusted: () => true,
  } as ExtensionContext;
  registerDocuments(
    (name, _description, schema, action) => {
      actions.set(name, async (p) =>
        action(schema.parse(p) as Record<string, unknown>, ctx),
      );
    },
    { core: () => core, disk: () => disk, clearReady: () => {} },
  );
  const call = async <T = Record<string, unknown>>(name: string, p: unknown) =>
    actions.get(name)!(p) as Promise<T>;
  let seq = 0;
  const preview = async (p: Record<string, unknown>) =>
    call<{ request_id: string }>("zara_document_preview", {
      request_id: "doc-op-" + ++seq,
      consequence: "Mechanical document operation",
      alternatives: "Leave unchanged",
      ...p,
    });
  const confirm = (ref: string) => {
    const shown = core.approvals.present(ref);
    core.approvals.answer(shown.token, true, {
      source_ref: "mechanical-confirmation",
      transport: "native-dialog",
      channel_identity: "mechanical-controller",
      stage: "pi-confirm-return",
    });
  };
  const apply = async (p: Record<string, unknown>) => {
    const draft = await preview(p);
    confirm(draft.request_id);
    return call<{
      document_ref: { id: string; revision: number };
      receipt: { created: Record<string, string> };
    }>("zara_document_apply", { preview_ref: draft.request_id });
  };
  const restart = () => {
    const context = { ...core.context, runtime_id: "restarted" };
    disk.close();
    disk = new DiskStorage(join(project, ".local", "memory"));
    core = new Core(disk, context);
  };
  return {
    project,
    get disk() {
      return disk;
    },
    get core() {
      return core;
    },
    restart,
    call,
    preview,
    confirm,
    apply,
    read: (id: string) => core.read(id).data as RecordRow,
  };
}

test("documents: native create/update, pinned history, bounded discovery and old-reply replay", async (t) => {
  const f = fixture();
  t.after(() => f.disk.close());
  const first = await f.apply({
    path: "example/menu.md",
    title: "Example menu",
    document_type: "menu",
    content: "# Monday\nSoup",
  });
  const old = managedDocument(f.read(first.document_ref.id));
  const updated = await f.apply({
    ref: first.document_ref,
    content: "# Monday\nRice",
  });
  assert.equal(updated.document_ref.id, first.document_ref.id);
  assert.equal(updated.document_ref.revision, 2);
  assert.match(
    f.disk.readMaterial(String(f.read(old.head_ref.id).data.blob_ref)),
    /Soup/,
  );
  assert.match(
    readFileSync(join(f.project, "activities/example/menu.md"), "utf8"),
    /Rice/,
  );
  assert.equal(
    (f.core.browse("documents").data as { cards: unknown[] }).cards.length,
    1,
  );
  const rows = f.disk.all("select * from records");
  await f.call("zara_document_apply", { request_id: "doc-op-1" });
  assert.deepEqual(f.disk.all("select * from records"), rows);
  await assert.rejects(
    f.preview({ ref: first.document_ref, content: "stale" }),
    /current document/,
  );
});

test("documents: external drift is visible, explicit adoption preserves content and identity", async (t) => {
  const f = fixture();
  t.after(() => f.disk.close());
  const first = await f.apply({
    path: "example/menu.md",
    title: "Menu",
    document_type: "menu",
    content: "# Original",
  });
  const path = join(f.project, "activities/example/menu.md");
  writeFileSync(
    path,
    readFileSync(path, "utf8").replace("Original", "External"),
  );
  const result = await f.call("zara_document_inspect", {
    id: first.document_ref.id,
  });
  assert.equal(result.state, "drift");
  await assert.rejects(
    f.preview({ ref: first.document_ref, content: "Overwrite" }),
    /differs from/,
  );
  const adopted = await f.apply({
    ref: first.document_ref,
    adopt_changes: true,
  });
  assert.equal(adopted.document_ref.revision, 2);
  assert.match(readFileSync(path, "utf8"), /External/);
});

test("documents: format versions validate real fields without per-Activity SQL", async (t) => {
  const f = fixture();
  t.after(() => f.disk.close());
  const format = await f.apply({
    path: "example/formats/menu.md",
    title: "Menu format",
    document_type: "format",
    content:
      '```json\n{"type":"object","properties":{"portions":{"type":"integer","minimum":1}},"required":["portions"],"additionalProperties":false}\n```',
  });
  const formatRef = managedDocument(f.read(format.document_ref.id)).head_ref;
  await assert.rejects(
    f.preview({
      path: "example/menu.md",
      title: "Menu",
      document_type: "menu",
      format_ref: formatRef,
      content: '```json\n{"portions":0}\n```',
    }),
    /does not match/,
  );
  const valid = await f.apply({
    path: "example/menu.md",
    title: "Menu",
    document_type: "menu",
    format_ref: formatRef,
    content: '```json\n{"portions":2}\n```',
  });
  assert.deepEqual(
    managedDocument(f.read(valid.document_ref.id)).format_ref,
    formatRef,
  );
});

test("documents: rename/move, archive, removal, restoration and dependency refusal", async (t) => {
  const f = fixture();
  t.after(() => f.disk.close());
  const first = await f.apply({
    path: "example/recipe.md",
    title: "Recipe",
    document_type: "recipe",
    content: "# Recipe",
  });
  const moved = await f.apply({
    ref: first.document_ref,
    path: "example/renamed.md",
    title: "Renamed recipe",
  });
  assert.equal(
    existsSync(join(f.project, "activities/example/recipe.md")),
    false,
  );
  const menu = await f.apply({
    path: "example/menu.md",
    title: "Menu",
    document_type: "menu",
    content: "# Menu",
    links: [moved.document_ref],
  });
  await assert.rejects(
    f.preview({ ref: moved.document_ref, action: "remove" }),
    /still references/,
  );
  const archived = await f.apply({ ref: menu.document_ref, action: "archive" });
  assert.equal(
    managedDocument(f.read(archived.document_ref.id)).state,
    "archived",
  );
  const removed = await f.apply({ ref: moved.document_ref, action: "remove" });
  assert.equal(
    existsSync(join(f.project, "activities/example/renamed.md")),
    false,
  );
  const restored = await f.apply({
    ref: removed.document_ref,
    content: "# Restored recipe",
  });
  assert.match(
    readFileSync(join(f.project, "activities/example/renamed.md"), "utf8"),
    /Restored/,
  );
  assert.equal(
    managedDocument(f.read(restored.document_ref.id)).state,
    "active",
  );
});

test("documents: authorization precedes filesystem writes, identity/path boundaries and generic bypass refusal", async (t) => {
  const f = fixture();
  t.after(() => f.disk.close());
  f.core.context.scopes = [];
  await assert.rejects(
    f.preview({
      path: "private/test.md",
      title: "Private",
      document_type: "note",
      content: "secret",
      visibility: "restricted",
    }),
    /read\/write/,
  );
  assert.equal(existsSync(join(f.project, "activities")), false);
  await assert.rejects(
    f.preview({
      path: "../escape.md",
      title: "Bad",
      document_type: "note",
      content: "bad",
    }),
  );
  f.core.context.processing_allowed = false;
  await assert.rejects(
    f.preview({
      path: "example/test.md",
      title: "Denied",
      document_type: "note",
      content: "bad",
    }),
  );
  assert.equal(existsSync(join(f.project, "activities")), false);
});

test("documents: crash after native write/prepared registration resumes in a fresh runtime without duplicate versions", async (t) => {
  let fail = true;
  const f = fixture((point) => {
    if (point === "after_prepare" && fail) {
      fail = false;
      throw new Error("injected registration interruption");
    }
  });
  t.after(() => f.disk.close());
  const draft = await f.preview({
    path: "example/recover.md",
    title: "Recover",
    document_type: "note",
    content: "# Retain me",
  });
  f.confirm(draft.request_id);
  await assert.rejects(
    f.call("zara_document_apply", { preview_ref: draft.request_id }),
    /injected/,
  );
  const body = readFileSync(
    join(f.project, "activities/example/recover.md"),
    "utf8",
  );
  assert.equal(f.disk.all("select * from records").length, 0);
  f.restart();
  const recovered = await f.call("zara_document_apply", {
    request_id: "doc-op-1",
  });
  assert.equal(recovered.committed, true);
  assert.equal(
    readFileSync(join(f.project, "activities/example/recover.md"), "utf8"),
    body,
  );
  const rows = f.disk.all("select * from revisions");
  await f.call("zara_document_apply", { request_id: "doc-op-1" });
  assert.deepEqual(f.disk.all("select * from revisions"), rows);
});

test("documents: missing parent restores explicitly; publication blocks drift and includes version/hash metadata", async (t) => {
  const f = fixture();
  t.after(() => f.disk.close());
  const first = await f.apply({
    path: "example/menu.md",
    title: "Menu",
    document_type: "menu",
    content: "# Registered",
  });
  const published = await f.call("zara_documents_publication", {
    refs: [first.document_ref],
    index_path: "README.md",
  });
  assert.equal(published.ready, true);
  assert.equal(published.written, false);
  const dir = join(f.project, "activities/example");
  assert.equal(dir, join(f.project, "activities", "example"));
  assert.ok(f.project.startsWith(tmpdir()));
  rmSync(dir, { recursive: true });
  const inspected = await f.call("zara_document_inspect", {
    id: first.document_ref.id,
  });
  assert.equal(inspected.state, "missing");
  const missing = await f.call("zara_documents_publication", {
    refs: [first.document_ref],
    index_path: "README.md",
  });
  assert.equal(missing.ready, false);
  await f.apply({
    ref: first.document_ref,
    content: "# Registered",
    adopt_changes: false,
  });
});

test("documents: schema7 upgrades through schema9; current backup includes retained document originals", async (t) => {
  const f = fixture();
  t.after(() => f.disk.close());
  // Make an exact empty legacy-7 fixture; no real owner workspace is accessed.
  const home = f.disk.home;
  f.disk.close();
  const db = new DatabaseSync(join(home, "zara.sqlite"));
  const meta = JSON.parse(
    String(db.prepare("select json from meta").get()!.json),
  );
  meta.schema_version = 7;
  db.exec("BEGIN IMMEDIATE");
  for (const row of db
    .prepare(
      "SELECT name FROM sqlite_master WHERE type='trigger' AND (name GLOB 'memory_dirty_*' OR name GLOB 'concurrency_*')",
    )
    .all() as { name: string }[])
    db.exec(`DROP TRIGGER "${row.name.replaceAll('"', '""')}"`);
  for (const name of [
    "memory_index_meta",
    "memory_ordinals",
    "memory_nodes",
    "memory_edges",
    "memory_dirty",
    "memory_technical",
    "memory_pending",
    "concurrency_meta",
  ])
    db.exec(`DROP TABLE IF EXISTS ${name}`);
  db.exec(
    "DROP INDEX IF EXISTS memory_access_restricted; DROP INDEX IF EXISTS sleep_prior_item;",
  );
  db.prepare("DELETE FROM migrations WHERE version>7").run();
  db.prepare("update meta set json=?").run(JSON.stringify(meta));
  db.exec("pragma user_version=7");
  db.exec("COMMIT");
  db.close();
  writeFileSync(join(home, "workspace.json"), JSON.stringify(meta));
  f.restart();
  assert.equal(f.disk.workspace.schema_version, 9);
  assert.ok(f.disk.get("select json from migrations where version=8"));
  assert.ok(f.disk.get("select json from migrations where version=9"));
  const first = await f.apply({
    path: "example/source.md",
    title: "Source",
    document_type: "note",
    content: "# Durable",
  });
  const d = managedDocument(f.read(first.document_ref.id));
  const admin = new Administration(
    home,
    join(f.project, "backups"),
    f.core.context,
  );
  const saved = await admin.backup(f.disk);
  const verified = admin.verify(saved.backup);
  assert.equal(verified.manifest.schema, 9);
  const hash = String(f.read(d.head_ref.id).data.blob_ref);
  assert.match(
    readFileSync(join(saved.backup, "materials", hash), "utf8"),
    /Durable/,
  );
});

test("documents: late dependency prevents approved removal before filesystem mutation", async (t) => {
  const f = fixture();
  t.after(() => f.disk.close());
  const recipe = await f.apply({
    path: "example/recipe.md",
    title: "Recipe",
    document_type: "recipe",
    content: "# Original",
  });
  const removal = await f.preview({
    ref: recipe.document_ref,
    action: "remove",
  });
  f.confirm(removal.request_id);
  await f.apply({
    path: "example/menu.md",
    title: "Menu",
    document_type: "menu",
    content: "# Menu",
    links: [recipe.document_ref],
  });
  await assert.rejects(
    f.call("zara_document_apply", { preview_ref: removal.request_id }),
    /still references/,
  );
  assert.match(
    readFileSync(join(f.project, "activities/example/recipe.md"), "utf8"),
    /Original/,
  );
});

test("documents: old-epoch cleanup and public registration bypass are refused", async (t) => {
  const f = fixture();
  t.after(() => f.disk.close());
  const first = await f.apply({
    path: "example/recipe.md",
    title: "Recipe",
    document_type: "recipe",
    content: "# Original",
  });
  const original = readFileSync(
    join(f.project, "activities/example/recipe.md"),
    "utf8",
  );
  await f.apply({ ref: first.document_ref, path: "example/new.md" });
  writeFileSync(join(f.project, "activities/example/recipe.md"), original);
  f.disk.run(
    "UPDATE intents SET json=json_set(json,'$.epoch','previous-epoch') WHERE request_id=?",
    "doc-op-2",
  );
  await assert.rejects(
    f.call("zara_document_apply", { request_id: "doc-op-2" }),
    /Historical document operations/,
  );
  assert.equal(
    readFileSync(join(f.project, "activities/example/recipe.md"), "utf8"),
    original,
  );
  const source = f.core.capture("mechanical source", "rpc", "mechanical");
  assert.throws(
    () =>
      f.core.commit({
        request_id: "forged-document-registration",
        reason: "mechanical negative",
        source_handles: [source.source_handle],
        guards: [],
        ops: [
          {
            op: "commit_document",
            client_ref: "doc",
            source_handle: source.source_handle,
            effect_request_id: "doc-op-1",
          },
        ],
      }),
    /trusted fresh file finalization/,
  );
});

test("documents: protected linked source snapshots stay private and Activity binding is retained", async (t) => {
  const f = fixture();
  t.after(() => f.disk.close());
  const source = f.core.capture(
    "mechanical Activity binding",
    "rpc",
    "mechanical",
  );
  const activity = f.core.commit({
    request_id: "mechanical-activity",
    reason: "Mechanical ownership check",
    source_handles: [source.source_handle],
    guards: [],
    ops: [
      {
        op: "create_record",
        client_ref: "area",
        kind: "activity",
        title: "Example",
        visibility: "workspace",
        data: { purpose: "Mechanical binding", status: "active" },
      },
    ],
  }).created.area;
  const privateDoc = await f.apply({
    path: "example/private.md",
    title: "Protected",
    document_type: "note",
    content: "# Private",
    visibility: "restricted",
  });
  const linked = await f.apply({
    path: "example/linked.md",
    title: "Linked",
    document_type: "note",
    content: "# Derived",
    links: [privateDoc.document_ref],
    activity_ref: { id: activity, revision: 1 },
  });
  const registry = f.read(linked.document_ref.id),
    head = managedDocument(registry).head_ref;
  assert.equal(registry.origin_activity_id?.id, activity);
  f.core.context.scopes = [];
  assert.throws(() => f.read(linked.document_ref.id), /unavailable/);
  assert.throws(() => f.read(head.id), /unavailable/);
});

test("documents: uncertain native failure permits a separately confirmed linked retry and retires its pending registration", async (t) => {
  const f = fixture();
  t.after(() => f.disk.close());
  const first = await f.preview({
    path: "example/retry.md",
    title: "Retry",
    document_type: "note",
    content: "# Intended",
  });
  f.confirm(first.request_id);
  const effect = FileEffectSchema.parse(
    f.core.approvals.read(first.request_id).payload.exact,
  );
  f.core.dispatchFile(
    effect,
    first.request_id,
    "mechanical-dispatch-before-interruption",
  );
  f.core.observeFile(effect.request_id, { hash: null, byte_length: 0 });
  await assert.rejects(
    f.call("zara_document_apply", { request_id: effect.request_id }),
    /does not match/,
  );
  const retry = await f.apply({
    path: "example/retry.md",
    title: "Retry",
    document_type: "note",
    content: "# Intended",
    retry_of: effect.request_id,
    retry_risk:
      "Mechanical explicit risk-taking repeat after observation; not proof of non-execution",
  });
  const published = await f.call("zara_documents_publication", {
    refs: [retry.document_ref],
    index_path: "README.md",
  });
  assert.equal(published.ready, true);
  await assert.rejects(
    f.call("zara_document_apply", { request_id: effect.request_id }),
    /explicitly superseded/,
  );
});

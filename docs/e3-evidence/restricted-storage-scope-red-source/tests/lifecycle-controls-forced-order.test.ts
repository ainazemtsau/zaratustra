import test from "node:test";
import assert from "node:assert/strict";
import { mkdtempSync, mkdirSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { Core, digest } from "../src/core/index.ts";
import type {
  CallContext,
  RecordRow,
  JsonObject,
  FileEffect,
} from "../src/core/index.ts";
import {
  Administration,
  DiskStorage,
  OutputBoundary,
  safePath,
} from "../src/storage/index.ts";
import { writeFileSync, cpSync } from "node:fs";
function setup() {
  const root = mkdtempSync(
      join(process.env.ZARATUSTRA_TEST_ROOT ?? tmpdir(), "e3-controls-"),
    ),
    home = join(root, "home"),
    backups = join(root, "backups");
  mkdirSync(backups);
  const disk = new DiskStorage(home);
  const ctx: CallContext = {
      workspace_id: disk.workspace.workspace_id,
      epoch: disk.workspace.epoch,
      principal: "trusted-personal",
      session_id: "synthetic",
      runtime_id: "controls",
      can_write: true,
      processing_allowed: true,
      scopes: ["restricted:read", "restricted:write"],
    },
    core = new Core(disk, ctx),
    admin = new Administration(home, backups, ctx);
  let serial = 0;
  const save = (
    ops: JsonObject[],
    guards: { ref: { id: string }; expected_revision: number }[] = [],
  ) => {
    const source = core.capture(
      "Synthetic control instruction " + ++serial,
      "rpc",
      "registered-controls",
    );
    return core.commit({
      request_id: "control-" + serial,
      reason: "Addressed synthetic control",
      source_handles: [source.source_handle],
      guards,
      ops: ops.map((o) =>
        o.op === "import_evidence"
          ? { ...o, source_handle: source.source_handle }
          : o,
      ),
    });
  };
  const read = (id: string) => core.read(id).data as RecordRow;
  const method = (instructions: string, dependencies: unknown[] = []) => ({
    applicability: "Synthetic control",
    instructions,
    input_contract: "Given input",
    expected_output: "Grounded result",
    context_requirements: [],
    dependencies,
    tool_requirements: [],
    content_version: 1,
    state: "candidate",
    derived_from: [],
    limitations: "Synthetic fixture only",
  });
  const work = (refs: unknown[]) =>
    save([
      {
        op: "create_record",
        client_ref: "w",
        kind: "work",
        title: "Open exact dependency obligation",
        visibility: "workspace",
        data: {
          activity_id: null,
          parent_work_id: null,
          objective: "Check supplied exact dependency",
          acceptance: [
            {
              criterion_id: "check",
              description: "Grounded result",
              verification: "Read exact dependency",
              required: true,
            },
          ],
          status: "active",
          current_state: "Awaiting check",
          next_action: "Inspect exact grounds",
          steps: [],
          waits: [],
          context_refs: refs,
          completion: null,
        },
      },
    ]).created.w;
  return {
    root,
    home,
    backups,
    disk,
    ctx,
    core,
    admin,
    save,
    read,
    method,
    work,
  };
}
function approve(core: Core, ref: string) {
  const p = core.approvals.present(ref);
  core.approvals.answer(p.token, true, {
    source_ref: "synthetic-approval",
    transport: "native-dialog",
    channel_identity: "registered-controls",
    stage: "pi-confirm-return",
  });
}
function code(action: () => unknown) {
  try {
    action();
    return "success";
  } catch (e) {
    return (e as { code?: string }).code ?? "unknown";
  }
}
test("E3 control operations cards remain readable after exact tombstone redacts a preview payload", (t) => {
  const f = setup();
  t.after(() => f.disk.close());
  const id = f.save([
    {
      op: "create_record",
      client_ref: "e",
      kind: "entity",
      title: "Removable control",
      body: "REMOVABLE_CONTROL_BODY",
      visibility: "workspace",
      data: {
        entity_kind: "item",
        aliases: [],
        disambiguation: "Synthetic removable",
        status: "active",
      },
    },
  ]).created.e;
  const p = f.core.storagePreview(
    { action: "tombstone", targets: [{ id, revision: 1 }] },
    "Delete selected body",
    "Keep",
  );
  approve(f.core, p.request_id);
  f.core.applyStorage(p.request_id);
  assert.doesNotThrow(() => f.core.browse("operations"));
  assert.equal(
    JSON.stringify(f.core.browse("operations")).includes(
      "REMOVABLE_CONTROL_BODY",
    ),
    false,
  );
  assert.equal(
    JSON.stringify(f.core.operation(p.request_id)).includes(
      "REMOVABLE_CONTROL_BODY",
    ),
    false,
  );
});
test("E3 control unreferenced Concept has a valid tombstone and its bundle verifies/restores", async (t) => {
  const f = setup();
  t.after(() => f.disk.close());
  const id = f.save([
    {
      op: "create_record",
      client_ref: "c",
      kind: "concept",
      title: "Empty optional section",
      visibility: "workspace",
      data: {
        definition: "Unused root",
        aliases: [],
        broader_ids: [],
        status: "active",
      },
    },
  ]).created.c;
  const p = f.core.storagePreview(
    { action: "tombstone", targets: [{ id, revision: 1 }] },
    "Delete unused section body",
    "Keep",
  );
  approve(f.core, p.request_id);
  f.core.applyStorage(p.request_id);
  assert.equal(f.read(id).storage, "tombstone");
  const b = await f.admin.backup(f.disk);
  assert.equal(f.admin.verify(b.backup).manifest.complete, true);
});
test("E3 control exact Method dependency pinned by open Work survives current Method revision; releasing obligation does not pin all history", (t) => {
  const f = setup();
  t.after(() => f.disk.close());
  const b = f.save([
    {
      op: "create_record",
      client_ref: "b",
      kind: "method",
      title: "Dependency B",
      visibility: "workspace",
      data: f.method("Required B v1"),
    },
  ]).created.b;
  const a = f.save([
      {
        op: "create_record",
        client_ref: "a",
        kind: "method",
        title: "Composed A",
        visibility: "workspace",
        data: f.method("A v1 needs B", [{ id: b, content_version: 1 }]),
      },
    ]).created.a,
    w = f.work([{ id: a, content_version: 1 }]);
  const a1 = f.read(a);
  f.save(
    [
      {
        op: "revise_method",
        ref: { id: a },
        data: {
          ...a1.data,
          instructions: "A v2 independent",
          dependencies: [],
        },
      },
    ],
    [{ ref: { id: a }, expected_revision: 1 }],
  );
  assert.throws(
    () =>
      f.core.storagePreview(
        { action: "tombstone", targets: [{ id: b, revision: 1 }] },
        "Delete B",
        "Keep B",
      ),
    { code: "DEPENDENCY_UNSATISFIED" },
  );
  assert.throws(
    () =>
      f.core.storagePreview(
        {
          action: "tombstone",
          targets: [
            { id: b, revision: 1 },
            { id: a, revision: 2 },
          ],
        },
        "Delete both methods",
        "Keep grounded Work",
      ),
    { code: "DEPENDENCY_UNSATISFIED" },
  );
  const old = f.read(w);
  f.save(
    [
      {
        op: "update_record",
        ref: { id: w },
        data: { ...old.data, context_refs: [] },
      },
    ],
    [{ ref: { id: w }, expected_revision: old.revision }],
  );
  assert.doesNotThrow(() =>
    f.core.storagePreview(
      { action: "tombstone", targets: [{ id: b, revision: 1 }] },
      "Delete now unpinned B",
      "Keep historical body",
    ),
  );
});
test("E3 control exact historical Knowledge grounds remain pinned by open Work after current correction", (t) => {
  const f = setup();
  t.after(() => f.disk.close());
  const e1 = f.save([
      {
        op: "import_evidence",
        client_ref: "e",
        title: "First grounds",
        source_language: "en",
      },
    ]).created.e,
    e2 = f.save([
      {
        op: "import_evidence",
        client_ref: "e",
        title: "Later grounds",
        source_language: "en",
      },
    ]).created.e;
  const k = f.save([
    {
      op: "create_record",
      client_ref: "k",
      kind: "knowledge",
      title: "Changing observation",
      visibility: "workspace",
      data: {
        knowledge_kind: "observation",
        statement: "Old synthetic observation",
        state: "current",
        basis: "user_statement",
        evidence_refs: [{ id: e1 }],
        conditions: "Synthetic",
      },
    },
  ]).created.k;
  f.work([{ id: k, revision: 1 }]);
  const prior = f.read(k);
  f.save(
    [
      {
        op: "update_record",
        ref: { id: k },
        data: {
          ...prior.data,
          statement: "New observation",
          evidence_refs: [{ id: e2 }],
        },
      },
    ],
    [{ ref: { id: k }, expected_revision: 1 }],
  );
  assert.throws(
    () =>
      f.core.storagePreview(
        { action: "tombstone", targets: [{ id: e1, revision: 1 }] },
        "Delete old grounds",
        "Keep obligation",
      ),
    { code: "DEPENDENCY_UNSATISFIED" },
  );
});
test("E3 control hidden primary guessed missing revision is indistinguishable from nonexistent ID", (t) => {
  const f = setup();
  t.after(() => f.disk.close());
  const id = f.save([
      {
        op: "create_record",
        client_ref: "e",
        kind: "entity",
        title: "Hidden synthetic identity",
        visibility: "restricted",
        data: {
          entity_kind: "item",
          aliases: [],
          disambiguation: "Private fixture",
          status: "active",
        },
      },
    ]).created.e,
    low = new Core(f.disk, { ...f.ctx, scopes: [] });
  assert.equal(
    code(() => low.read(id, 999999)),
    code(() => low.read("entity-nonexistent", 999999)),
  );
  assert.equal(
    code(() => low.read(id, 999999)),
    "REFERENCE_NOT_FOUND",
  );
  assert.equal(
    code(() => f.core.read(id, 999999)),
    "CONTENT_NOT_RETAINED",
  );
});
test("E3 control stable lease survives SQLite close; a real interleaving writer cannot commit unpreviewed data", async (t) => {
  const f = setup();
  const b = await f.admin.backup(f.disk),
    p = f.admin.restorePreview(
      b.backup,
      "Restore exact empty snapshot",
      "Keep current",
    );
  const shown = f.admin.approvals.present(p.preview.request_id);
  f.admin.approvals.answer(shown.token, true, {
    source_ref: "synthetic",
    transport: "native-dialog",
    channel_identity: "registered-controls",
    stage: "pi-confirm-return",
  });
  const optional = f.disk as unknown as { closeConnection?: () => void };
  const original = (optional.closeConnection ?? f.disk.close).bind(f.disk);
  let once = false,
    attempted = false,
    blocked = false;
  const interpose = () => {
    original();
    if (once) return;
    once = true;
    attempted = true;
    const other = new DiskStorage(f.home);
    try {
      const c = new Core(other, {
        ...f.ctx,
        runtime_id: "intervening-writer",
        can_write: true,
      });
      const s = c.capture("Intervening real writer", "rpc", "synthetic");
      blocked =
        code(() =>
          c.commit({
            request_id: "intervening",
            source_handles: [s.source_handle],
            guards: [],
            reason: "Must not be discarded by unpreviewed restore",
            ops: [
              {
                op: "create_record",
                client_ref: "a",
                kind: "activity",
                title: "Unpreviewed intervening commit",
                visibility: "workspace",
                data: { purpose: "Would be lost", status: "active" },
              },
            ],
          }),
        ) === "READ_ONLY";
    } finally {
      other.close();
    }
  };
  if (optional.closeConnection)
    Object.defineProperty(f.disk, "closeConnection", { value: interpose });
  else f.disk.close = interpose;
  f.admin.restore(p.preview.request_id, f.disk);
  assert.equal(attempted, true);
  assert.equal(
    blocked,
    true,
    "A legitimate writer must remain blocked across the connection-close/pointer gap",
  );
  const current = new DiskStorage(f.home);
  t.after(() => current.close());
});
test("E3 control pending material remains pinned after an unrelated commit using the same source handle", async (t) => {
  const f = setup();
  t.after(() => f.disk.close());
  const path = join(f.root, "pending.md");
  writeFileSync(path, "Pending source still has no Evidence commit");
  const m = await f.disk.importMaterial(path, [f.root], () =>
      f.core.authorizeImport(),
    ),
    s = f.core.capture(m.text, "file", null, m);
  f.core.commit({
    request_id: "unrelated-from-material",
    reason: "A separate entity is not the material's Evidence commit",
    source_handles: [s.source_handle],
    guards: [],
    ops: [
      {
        op: "create_record",
        client_ref: "e",
        kind: "entity",
        title: "Separate entity",
        visibility: "workspace",
        data: {
          entity_kind: "item",
          aliases: [],
          disambiguation: "Synthetic",
          status: "active",
        },
      },
    ],
  });
  const gc = f.admin.cleanupPreview(
    f.disk,
    "Only genuine orphan cleanup",
    "Keep",
  );
  assert.equal((gc.payload.exact.candidates as unknown[]).length, 0);
});
test("E3 control tombstone preserves inherited restriction without declassifying identity/count/technical headers", (t) => {
  const f = setup();
  t.after(() => f.disk.close());
  const concept = (title: string, visibility: string) =>
    f.save([
      {
        op: "create_record",
        client_ref: "c",
        kind: "concept",
        title,
        visibility,
        data: {
          definition: "Synthetic scope category",
          aliases: [],
          broader_ids: [],
          status: "active",
        },
      },
    ]).created.c;
  const target = concept("Initially public section", "workspace"),
    privateSource = concept("Protected section", "restricted");
  const entity = f.save([
    {
      op: "create_record",
      client_ref: "e",
      kind: "entity",
      title: "Untouched inherited private identity",
      visibility: "workspace",
      concept_ids: [{ id: target }],
      data: {
        entity_kind: "item",
        aliases: [],
        disambiguation: "Inherited protection fixture",
        status: "active",
      },
    },
  ]).created.e;
  const source = f.core.capture(
      "Synthetic exact protected merge",
      "rpc",
      "registered-controls",
    ),
    request = {
      request_id: "private-merge",
      reason: "Propagate protection through a real managed merge",
      source_handles: [source.source_handle],
      guards: [
        { ref: { id: privateSource }, expected_revision: 1 },
        { ref: { id: target }, expected_revision: 1 },
      ],
      ops: [
        {
          op: "merge_identity",
          from_ref: { id: privateSource },
          to_ref: { id: target },
        },
      ],
    };
  const p = f.core.prepareCommit(
    request,
    "Merge protected category into exact public section; protection propagates",
    "Keep separate",
  );
  approve(f.core, p.request_id);
  f.core.commit({ ...request, preview_ref: p.request_id });
  assert.equal(f.read(entity).visibility, "workspace");
  const low = new Core(f.disk, { ...f.ctx, scopes: [] });
  assert.equal(
    code(() => low.read(entity)),
    "REFERENCE_NOT_FOUND",
  );
  const nonexistent = "entity-control-never-existed";
  assert.equal(
    code(() => low.read(nonexistent, 777)),
    "REFERENCE_NOT_FOUND",
  );
  const d = f.core.storagePreview(
    { action: "tombstone", targets: [{ id: entity, revision: 1 }] },
    "Delete body; retain inherited privacy",
    "Keep protected body",
  );
  approve(f.core, d.request_id);
  f.core.applyStorage(d.request_id);
  assert.equal(
    code(() => low.read(entity)),
    "REFERENCE_NOT_FOUND",
  );
  assert.equal(
    JSON.stringify(
      low.search({ kinds: ["entity"], storage: "tombstone" }),
    ).includes(entity),
    false,
  );
  assert.equal(
    JSON.stringify(low.browse("operations")).includes(entity),
    false,
  );
  assert.equal(
    JSON.stringify(low.diagnostics()).includes(entity),
    false,
    "A redacted prior denied-read trace must not reveal hidden identity",
  );
  const key = f.disk.get<{ access_key: string }>(
    "SELECT access_key FROM retrieval_trace WHERE json_extract(json,'$.input.id')=? LIMIT 1",
    nonexistent,
  )!.access_key;
  for (const [marker, ids] of [
    ["nested-protected-control", [[entity]]],
    ["nested-public-control", [["ordinary-public-marker"]]],
  ] as const) {
    const seq = f.disk.get<{ n: number }>(
      "SELECT coalesce(max(seq),0)+1 AS n FROM retrieval_trace",
    )!.n;
    f.disk.run(
      "INSERT INTO retrieval_trace VALUES(?,?,?)",
      seq,
      key,
      JSON.stringify({ operation: marker, nested: ids, refs: [] }),
    );
  }
  const diagnostics = JSON.stringify(low.diagnostics());
  assert.equal(diagnostics.includes("nested-protected-control"), false);
  assert.equal(diagnostics.includes(entity), false);
  assert.equal(diagnostics.includes("nested-public-control"), true);
  assert.equal(diagnostics.includes(nonexistent), true);
  const visible = f.save([
      {
        op: "create_record",
        client_ref: "e",
        kind: "entity",
        title: "Genuinely public identity",
        visibility: "workspace",
        data: {
          entity_kind: "item",
          aliases: [],
          disambiguation: "Public fixture",
          status: "active",
        },
      },
    ]).created.e,
    q = f.core.storagePreview(
      { action: "tombstone", targets: [{ id: visible, revision: 1 }] },
      "Delete public body",
      "Keep",
    );
  approve(f.core, q.request_id);
  f.core.applyStorage(q.request_id);
  assert.equal((low.read(visible).data as RecordRow).storage, "tombstone");
});
test("E3 control backup51 is discoverable by bounded scope/generation-bound continuation", async (t) => {
  const f = setup();
  t.after(() => f.disk.close());
  const b = await f.admin.backup(f.disk);
  for (let i = 1; i <= 50; i++) {
    const dir = join(f.backups, "backup-" + i.toString(16).padStart(36, "0"));
    if (i % 2 === 0) cpSync(b.backup, dir, { recursive: true });
    else mkdirSync(dir);
  }
  type Page = {
    backups: { path: string }[];
    has_more: boolean;
    next_cursor?: string | null;
  };
  const listing = f.admin as unknown as { list: (cursor?: string) => Page },
    first = listing.list();
  assert.equal(first.backups.length, 50);
  assert.equal(first.has_more, true);
  assert.ok(first.next_cursor);
  const last = listing.list(first.next_cursor!);
  assert.equal(last.has_more, false);
  assert.equal(
    new Set([...first.backups, ...last.backups].map((x) => x.path)).size,
    51,
  );
  mkdirSync(join(f.backups, "backup-ffffffffffffffffffffffffffffffffffff"));
  assert.throws(() => listing.list(first.next_cursor!), {
    code: "CURSOR_INVALIDATED",
  });
  const low = new Administration(f.home, f.backups, {
    ...f.ctx,
    scopes: [],
  }) as unknown as { list: (cursor?: string) => Page };
  assert.throws(() => low.list(first.next_cursor!), {
    code: "PERMISSION_DENIED",
  });
});

test("E3 control truncated recovery hints have an explicit continuation through ordinary Work reads", async (t) => {
  const f = setup();
  t.after(() => f.disk.close());
  const works = Array.from({ length: 21 }, () => f.work([]));
  const b = await f.admin.backup(f.disk),
    p = f.admin.restorePreview(b.backup, "Restore all obligations", "Keep");
  const presented = f.admin.approvals.present(p.preview.request_id);
  f.admin.approvals.answer(presented.token, true, {
    source_ref: "synthetic-approval",
    transport: "native-dialog",
    channel_identity: "registered-controls",
    stage: "pi-confirm-return",
  });
  f.admin.restore(p.preview.request_id, f.disk);
  const disk = new DiskStorage(f.home),
    core = new Core(disk, { ...f.ctx, epoch: disk.workspace.epoch });
  t.after(() => disk.close());
  const snapshot = core.snapshot() as unknown as Record<string, unknown>;
  assert.equal(snapshot.recovery_required_has_more, true);
  assert.equal((snapshot.recovery_required as unknown[]).length, 20);
  for (const id of works) {
    const r = core.read(id).data as RecordRow & {
      current_runtime_recovery: {
        epoch: string;
        actions: { status: string }[];
      };
    };
    assert.equal(r.current_runtime_recovery.epoch, disk.workspace.epoch);
    assert.ok(
      r.current_runtime_recovery.actions.some((a) => a.status === "required"),
    );
  }
});

test("E3 control administrative paths reject Windows device, ADS and control aliases", (t) => {
  const f = setup();
  t.after(() => f.disk.close());
  for (const name of ["NUL.txt", "CON", "file:stream", "bad\u0001name"])
    assert.throws(() => safePath(f.home, join(f.home, name)), {
      code: "PERMISSION_DENIED",
    });
});

test("E3 control deleting an exported Method redacts managed payload copies while preserving receipt identity and disclosing external coverage", (t) => {
  const f = setup();
  t.after(() => f.disk.close());
  const secret = "METHOD_BODY_DELETE_CONTROL_4921",
    id = f.save([
      {
        op: "create_record",
        client_ref: "m",
        kind: "method",
        title: "Removable textual approach",
        body: secret,
        visibility: "workspace",
        data: f.method(secret),
      },
    ]).created.m,
    out = join(f.root, "output");
  mkdirSync(out);
  const path = join(out, "SKILL.md"),
    boundary = new OutputBoundary(out),
    before = boundary.inspect(path, out),
    exported = f.core.methodExport(id);
  const input: FileEffect = {
    request_id: "method-export-before-delete",
    tool: "write",
    arguments: { path, content: exported.text },
    target: path,
    boundary: before.boundary,
    before_hash: null,
    before_length: 0,
    final_hash: digest(exported.text),
    final_length: Buffer.byteLength(exported.text),
    final_text: exported.text,
    work_ref: null,
    step_id: null,
    independent_basis: "Separate synthetic textual export",
    method_export: {
      method_ref: exported.method_ref,
      content_hash: exported.content_hash,
      export_hash: exported.export_hash,
    },
    retry_of: null,
    retry_risk: null,
  };
  const p = f.core.prepareFile(
    input,
    "Export selected textual approach",
    "Keep canonical only",
  );
  approve(f.core, p.request_id);
  f.core.dispatchFile(
    p.payload.exact as FileEffect,
    p.request_id,
    "native-control",
  );
  writeFileSync(path, exported.text);
  const o = boundary.inspect(path, out);
  f.core.observeFile(
    input.request_id,
    { hash: o.hash, byte_length: o.byte_length, boundary: o.boundary },
    { id: "native-control", runtime_id: f.ctx.runtime_id, is_error: false },
  );
  const receipt = f.core.inspectFile(input.request_id).receipt!;
  const d = f.core.storagePreview(
    { action: "tombstone", targets: [{ id, revision: 1 }] },
    "Delete all retained canonical and managed technical body copies; external SKILL remains separate",
    "Keep",
  );
  assert.match(String(d.payload.exact.coverage), /external backups\/exports/);
  approve(f.core, d.request_id);
  f.core.applyStorage(d.request_id);
  assert.doesNotThrow(() => f.core.browse("operations"));
  const card = JSON.stringify(f.core.operation(input.request_id));
  assert.equal(card.includes(secret), false);
  assert.ok(card.includes(String(receipt.receipt_id)));
  assert.equal(
    code(() => f.core.inspectFile(input.request_id)),
    "CONTENT_NOT_RETAINED",
  );
  assert.equal(
    code(() => f.core.approvals.read(p.request_id)),
    "CONTENT_NOT_RETAINED",
  );
  assert.equal(
    code(() => f.core.methodExport(id)),
    "CONTENT_NOT_RETAINED",
  );
  assert.equal(
    code(() => f.core.skillExportStatus(path, exported.export_hash)),
    "REFERENCE_NOT_FOUND",
  );
  assert.equal(
    JSON.stringify(
      f.core.search({ query: secret, match: "all" }).data.cards,
    ).includes(secret),
    false,
  );
});

test("E3 control restricted storage operations preserve low generation, sequence, docids and complete cursor continuation", (t) => {
  const f = setup(); t.after(() => f.disk.close());
  const entity = (client_ref: string, visibility: string) => ({ op: "create_record", client_ref, kind: "entity",
    title: client_ref, body: "Synthetic scope pagination body", visibility,
    data: { entity_kind: "item", aliases: [], disambiguation: client_ref, status: "active" } });
  const publics = Object.values(f.save([entity("one", "workspace"), entity("two", "workspace"), entity("three", "workspace")]).created),
    hidden = f.save([{ op: "create_record", client_ref: "hidden", kind: "activity", title: "Protected activity before entity sort keys",
      visibility: "restricted", data: { purpose: "Force real docid displacement on a full rebuild", status: "active" } }]).created.hidden,
    low = new Core(f.disk, { ...f.ctx, scopes: [] }),
    query = { kinds: ["entity"], limit: 1 }, observations: unknown[] = [];
  const docs = () => publics.map(id => f.disk.get("SELECT id,revision,docid FROM memory_docs WHERE id=? AND revision=1", id));
  for (const action of ["archive", "retain", "release", "tombstone"]) {
    const first = low.search(query), beforeDocs = docs(), revision = f.read(hidden).revision,
      p = f.core.storagePreview({ action, targets: [{ id: hidden, revision }] }, "Only protected fixture storage", "Keep");
    approve(f.core, p.request_id); f.core.applyStorage(p.request_id);
    const after = low.search(query), ids = first.data.cards.map(c => c.id); let cursor = first.data.next_cursor, error = "";
    try { while (cursor) { const page = low.search({ ...query, cursor }); ids.push(...page.data.cards.map(c => c.id)); cursor = page.data.next_cursor; } }
    catch (e) { error = (e as { code: string }).code; }
    const result = { action, before_generation: first.data.generation, after_generation: after.data.generation,
      before_seq: first.snapshot_seq, after_seq: after.snapshot_seq, before_docids: beforeDocs, after_docids: docs(),
      continuation: ids, cursor_error: error, visible_count: low.search({ kinds: ["entity"], limit: 50 }).data.cards.length };
    observations.push(result);
  }
  console.log(JSON.stringify({ protected_storage_scope_control: observations }));
  for (const v of observations as { before_generation: string; after_generation: string; before_seq: number; after_seq: number;
    before_docids: unknown[]; after_docids: unknown[]; continuation: string[]; cursor_error: string; visible_count: number }[]) {
    assert.equal(v.after_generation, v.before_generation);
    assert.equal(v.after_seq, v.before_seq); assert.deepEqual(v.after_docids, v.before_docids);
    assert.equal(v.cursor_error, ""); assert.equal(v.visible_count, 3);
    assert.equal(new Set(v.continuation).size, 3); assert.deepEqual([...v.continuation].sort(), [...publics].sort());
  }
  const beforePublic = low.search(query);
  f.save([entity("new-public", "workspace")]);
  assert.throws(() => low.search({ ...query, cursor: beforePublic.data.next_cursor! }), { code: "CURSOR_INVALIDATED" });
  const beforeRebuild = low.search(query); f.core.rebuildIndex();
  assert.throws(() => low.search({ ...query, cursor: beforeRebuild.data.next_cursor! }), { code: "CURSOR_INVALIDATED" });
});

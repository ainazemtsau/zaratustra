import test, { type TestContext } from "node:test";
import assert from "node:assert/strict";
import { existsSync, mkdtempSync, readFileSync, writeFileSync } from "node:fs";
import fs from "node:fs/promises";
import { syncBuiltinESMExports } from "node:module";
import { tmpdir } from "node:os";
import { join } from "node:path";
import type { ExtensionContext } from "@earendil-works/pi-coding-agent";
import {
  Core,
  FileEffectSchema,
  managedDocument,
  type RecordRow,
} from "../src/core/index.ts";
import { DiskStorage, DocumentFiles } from "../src/storage/index.ts";
import { registerDocuments } from "../src/extension/documents.ts";

type Ref = { id: string; revision: number };
type Applied = { committed: boolean; document_ref: Ref };

function runtime(project: string, fault?: (point: string) => void) {
  const disk = new DiskStorage(join(project, ".local", "memory"));
  const core = new Core(
    disk,
    {
      ...disk.workspace,
      principal: "trusted-personal",
      session_id: disk.coordination.runtimeId,
      runtime_id: disk.coordination.runtimeId,
      processing_allowed: true,
      can_write: true,
      scopes: ["restricted:read", "restricted:write"],
    },
    fault,
  );
  const actions = new Map<
    string,
    (p: unknown, signal?: AbortSignal) => Promise<unknown>
  >();
  const ctx = {
    cwd: project,
    isProjectTrusted: () => true,
  } as ExtensionContext;
  registerDocuments(
    (name, _description, schema, action) => {
      actions.set(name, async (p, signal) =>
        action(schema.parse(p) as Record<string, unknown>, ctx, signal),
      );
    },
    { core: () => core, disk: () => disk, clearReady: () => {} },
  );
  const call = <T = Record<string, unknown>>(
    name: string,
    p: unknown,
    signal?: AbortSignal,
  ) => actions.get(name)!(p, signal) as Promise<T>;
  let sequence = 0;
  const preview = async (p: Record<string, unknown>) => {
    const requestId = disk.coordination.runtimeId + "-" + ++sequence;
    const prepared = await call<{ request_id: string }>(
      "zara_document_preview",
      {
        request_id: requestId,
        consequence: "Mechanical concurrency test",
        alternatives: "Leave unchanged",
        ...p,
      },
    );
    return { ...prepared, operation_request_id: requestId };
  };
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
    return call<Applied>("zara_document_apply", {
      preview_ref: draft.request_id,
    });
  };
  const operation = (id: string) =>
    disk.withOperation("read", () => disk.coordination.operation("file:" + id));
  const read = (id: string) => core.read(id).data as RecordRow;
  return { disk, core, call, preview, confirm, apply, operation, read };
}

function fixture(t: TestContext) {
  const project = mkdtempSync(join(tmpdir(), "zara-document-concurrency-"));
  const opened: ReturnType<typeof runtime>[] = [];
  const open = (fault?: (point: string) => void) => {
    const value = runtime(project, fault);
    opened.push(value);
    return value;
  };
  t.after(() => {
    for (const value of opened) value.disk.close();
  });
  return { project, open };
}

function holdNative(t: TestContext, target: string) {
  let entered!: () => void;
  let release!: () => void;
  const started = new Promise<void>((resolve) => {
    entered = resolve;
  });
  const barrier = new Promise<void>((resolve) => {
    release = resolve;
  });
  const original = fs.writeFile;
  const mock = t.mock.method(
    fs,
    "writeFile",
    async (...args: Parameters<typeof fs.writeFile>) => {
      const [path, data, options] = args;
      if (String(path) === target) {
        entered();
        await barrier;
      }
      return original(path, data, options);
    },
  );
  syncBuiltinESMExports();
  t.after(() => {
    release();
    mock.mock.restore();
    syncBuiltinESMExports();
  });
  return { started, release };
}

const document = (path: string) => ({
  path,
  title: path,
  document_type: "note",
  content: "# Mechanical fixture",
});

test(
  "documents: durable exact path reservations survive native await while another document in the same Activity progresses",
  { timeout: 15000 },
  async (t) => {
    const f = fixture(t),
      a = f.open(),
      b = f.open();
    const captured = a.core.capture("mechanical Activity", "rpc", "test");
    const activity = a.core.commit({
      request_id: "concurrent-document-activity",
      reason: "Mechanical shared Activity",
      source_handles: [captured.source_handle],
      guards: [],
      ops: [
        {
          op: "create_record",
          client_ref: "area",
          kind: "activity",
          title: "Shared",
          visibility: "workspace",
          data: { purpose: "Mechanical", status: "active" },
        },
      ],
    }).created.area;
    const binding = { activity_ref: { id: activity, revision: 1 } };
    const first = await a.preview({ ...document("shared/a.md"), ...binding });
    const conflict = await b.preview({
      ...document("shared/a.md"),
      ...binding,
    });
    a.confirm(first.request_id);
    b.confirm(conflict.request_id);
    const native = holdNative(t, join(f.project, "activities/shared/a.md"));
    const running = a.call<Applied>("zara_document_apply", {
      preview_ref: first.request_id,
    });
    void running.catch(() => {});
    await native.started;
    const held = await b.operation(first.operation_request_id);
    assert.equal(held?.phase, "dispatching");
    assert.equal(held?.status, "active");
    assert.equal(
      a.core.inspectFile(first.operation_request_id).status,
      "requested",
    );
    assert.equal(a.disk.coordination.held, false);
    assert.equal(
      held?.resources.some((r) => r.startsWith("document:")),
      true,
    );
    const absolute = join(f.project, "activities/shared/a.md");
    assert.ok(
      held?.resources.includes(
        "file:" +
          (process.platform === "win32" ? absolute.toLowerCase() : absolute),
      ),
    );
    await assert.rejects(
      b.call("zara_document_apply", { preview_ref: conflict.request_id }),
      /reserved/,
    );
    await assert.rejects(
      b.call("zara_document_apply", { request_id: first.operation_request_id }),
      /alive|proved dead/,
    );
    const independent = await b.apply({
      ...document("shared/b.md"),
      ...binding,
    });
    assert.equal(
      b.read(independent.document_ref.id).origin_activity_id?.id,
      activity,
    );
    assert.equal(
      (await a.operation(first.operation_request_id))?.status,
      "active",
    );
    native.release();
    assert.equal((await running).committed, true);
    assert.equal(
      (await b.operation(first.operation_request_id))?.status,
      "settled",
    );
  },
);

test("documents: registration before failed move cleanup retains both paths and blocks publication until dead-owner recovery", async (t) => {
  const f = fixture(t),
    a = f.open(),
    b = f.open();
  const initial = await a.apply(document("move/old.md"));
  const originalCleanup = DocumentFiles.prototype.cleanup;
  let fail = true;
  const cleanup = t.mock.method(
    DocumentFiles.prototype,
    "cleanup",
    function (
      this: DocumentFiles,
      ...args: Parameters<DocumentFiles["cleanup"]>
    ) {
      if (fail && args[0] === "move/old.md") {
        fail = false;
        throw new Error("injected cleanup interruption");
      }
      return originalCleanup.apply(this, args);
    },
  );
  const moved = await a.preview({
    ref: initial.document_ref,
    path: "move/new.md",
  });
  a.confirm(moved.request_id);
  await assert.rejects(
    a.call("zara_document_apply", { preview_ref: moved.request_id }),
    /injected cleanup/,
  );
  assert.ok(a.core.documentRegistration(moved.operation_request_id));
  assert.equal(
    (await b.operation(moved.operation_request_id))?.phase,
    "unknown",
  );
  const current = a.read(initial.document_ref.id);
  const ref = { id: current.id, revision: current.revision };
  const cleanupBypass = await a.preview({
    ref,
    content: "# Later retry",
    retry_of: moved.operation_request_id,
    retry_risk: "Mechanical separately approved retry",
  });
  a.confirm(cleanupBypass.request_id);
  await assert.rejects(
    a.call("zara_document_apply", { preview_ref: cleanupBypass.request_id }),
    /already registered document's cleanup/,
  );
  assert.equal(
    await a.operation(cleanupBypass.operation_request_id),
    undefined,
  );
  const publication = await b.call("zara_documents_publication", {
    refs: [ref],
    index_path: "README.md",
  });
  assert.equal(publication.ready, false);
  assert.equal((publication.pending_operations as unknown[]).length, 1);
  const next = await b.preview({ ref, content: "# Later" });
  b.confirm(next.request_id);
  await assert.rejects(
    b.call("zara_document_apply", { preview_ref: next.request_id }),
    /reserved/,
  );
  const reused = await b.preview(document("move/old.md"));
  b.confirm(reused.request_id);
  await assert.rejects(
    b.call("zara_document_apply", { preview_ref: reused.request_id }),
    /reserved/,
  );
  await assert.rejects(
    b.call("zara_document_apply", { request_id: moved.operation_request_id }),
    /alive|proved dead/,
  );
  a.disk.close();
  const recovered = await b.call<Applied>("zara_document_apply", {
    request_id: moved.operation_request_id,
  });
  assert.equal(recovered.committed, true);
  assert.equal(recovered.document_ref.revision, 2);
  assert.equal(existsSync(join(f.project, "activities/move/old.md")), false);
  assert.equal(
    (await b.operation(moved.operation_request_id))?.status,
    "settled",
  );
  assert.equal(
    (
      await b.call("zara_documents_publication", {
        refs: [ref],
        index_path: "README.md",
      })
    ).ready,
    true,
  );
  cleanup.mock.restore();
});

test("documents: native error after writing retains an unknown barrier and explicit inspection never redispatches", async (t) => {
  const f = fixture(t),
    a = f.open(),
    b = f.open();
  const draft = await a.preview(document("error/after-write.md"));
  a.confirm(draft.request_id);
  const original = fs.writeFile;
  let writes = 0;
  const native = t.mock.method(
    fs,
    "writeFile",
    async (...args: Parameters<typeof fs.writeFile>) => {
      const [path, data, options] = args;
      writes++;
      await original(path, data, options);
      throw new Error("injected lost native reply");
    },
  );
  syncBuiltinESMExports();
  t.after(() => {
    native.mock.restore();
    syncBuiltinESMExports();
  });
  await assert.rejects(
    a.call("zara_document_apply", { preview_ref: draft.request_id }),
    /failed or was cancelled/,
  );
  assert.equal(writes, 1);
  assert.equal(
    (await b.operation(draft.operation_request_id))?.phase,
    "unknown",
  );
  assert.equal(
    (await b.operation(draft.operation_request_id))?.status,
    "unknown",
  );
  await b.disk.withOperation("maintenance", () => {
    const token = b.disk.coordination.beginMaintenance(
      "restore",
      b.core.context.epoch,
    );
    assert.equal(b.disk.coordination.drainMaintenance().pending, 0);
    b.disk.coordination.endMaintenance(token);
  });
  assert.equal(a.core.documentRegistration(draft.operation_request_id), null);
  await assert.rejects(
    b.call("zara_document_apply", { request_id: draft.operation_request_id }),
    /alive|proved dead/,
  );
  const recovered = await a.call<Applied>("zara_document_apply", {
    request_id: draft.operation_request_id,
  });
  assert.equal(recovered.committed, true);
  assert.equal(writes, 1);
  const again = await b.call<Applied>("zara_document_apply", {
    request_id: draft.operation_request_id,
  });
  assert.deepEqual(again.document_ref, recovered.document_ref);
  assert.equal(writes, 1);
});

test("documents: missing coordination rows reconcile committed legacy attempts without native replay, and old epochs retain their barrier", async (t) => {
  const f = fixture(t),
    a = f.open();
  const draft = await a.preview(document("legacy/current.md"));
  a.confirm(draft.request_id);
  const effect = FileEffectSchema.parse(
    a.core.approvals.read(draft.request_id).payload.exact,
  );
  a.core.dispatchFile(effect, draft.request_id, "legacy-dispatch");
  writeFileSync(effect.target, effect.final_text);
  assert.equal(await a.operation(draft.operation_request_id), undefined);
  const recovered = await a.call<Applied>("zara_document_apply", {
    request_id: draft.operation_request_id,
  });
  assert.equal(recovered.committed, true);
  assert.equal(
    (await a.operation(draft.operation_request_id))?.status,
    "settled",
  );
  const old = await a.preview({
    ref: recovered.document_ref,
    path: "legacy/next.md",
  });
  a.confirm(old.request_id);
  const historical = FileEffectSchema.parse(
    a.core.approvals.read(old.request_id).payload.exact,
  );
  a.core.dispatchFile(historical, old.request_id, "legacy-old-epoch");
  writeFileSync(historical.target, historical.final_text);
  a.disk.run(
    "UPDATE intents SET json=json_set(json,'$.epoch','previous-epoch') WHERE request_id=?",
    old.operation_request_id,
  );
  const before = readFileSync(effect.target, "utf8");
  await assert.rejects(
    a.call("zara_document_apply", { request_id: old.operation_request_id }),
    /Historical document operations/,
  );
  assert.equal(readFileSync(effect.target, "utf8"), before);
  assert.equal((await a.operation(old.operation_request_id))?.phase, "unknown");
  assert.equal(
    (await a.operation(old.operation_request_id))?.epoch,
    "previous-epoch",
  );
  assert.equal(
    managedDocument(a.read(recovered.document_ref.id)).path,
    "legacy/current.md",
  );
});

test("documents: cancellation before admission writes nothing and cancellation after native admission preserves recovery", async (t) => {
  const f = fixture(t),
    a = f.open();
  const draft = await a.preview(document("cancel/document.md"));
  a.confirm(draft.request_id);
  const before = new AbortController();
  before.abort();
  await assert.rejects(
    a.call(
      "zara_document_apply",
      { preview_ref: draft.request_id },
      before.signal,
    ),
    /cancelled before admission/,
  );
  assert.equal(await a.operation(draft.operation_request_id), undefined);
  assert.equal(
    a.core.fileReplay(
      draft.operation_request_id,
      "write",
      FileEffectSchema.parse(
        a.core.approvals.read(draft.request_id).payload.exact,
      ).arguments,
    ),
    null,
  );
  const during = new AbortController();
  const native = holdNative(
    t,
    join(f.project, "activities/cancel/document.md"),
  );
  const running = a.call(
    "zara_document_apply",
    { preview_ref: draft.request_id },
    during.signal,
  );
  await native.started;
  during.abort();
  native.release();
  await assert.rejects(running, /failed or was cancelled/);
  assert.equal(
    (await a.operation(draft.operation_request_id))?.phase,
    "unknown",
  );
  assert.equal(a.core.documentRegistration(draft.operation_request_id), null);
  assert.equal(
    (
      await a.call<Applied>("zara_document_apply", {
        request_id: draft.operation_request_id,
      })
    ).committed,
    true,
  );
});

test("documents: matching preexisting bytes cannot settle the same runtime's still-running native write", async (t) => {
  const f = fixture(t),
    a = f.open();
  const created = await a.apply(document("inflight/unchanged.md"));
  const draft = await a.preview({
    ref: created.document_ref,
    action: "archive",
  });
  a.confirm(draft.request_id);
  const effect = FileEffectSchema.parse(
    a.core.approvals.read(draft.request_id).payload.exact,
  );
  assert.equal(effect.before_hash, effect.final_hash);
  const native = holdNative(t, effect.target);
  // The initial recovery read can precede native admission. Its later settle
  // phase must check the live operation again after the asynchronous boundary.
  const earlyRecovery = assert.rejects(
    a.call("zara_document_apply", { request_id: draft.operation_request_id }),
    /still in flight/,
  );
  const running = a.call<Applied>("zara_document_apply", {
    preview_ref: draft.request_id,
  });
  void running.catch(() => {});
  await native.started;
  await earlyRecovery;
  await assert.rejects(
    a.call("zara_document_apply", { request_id: draft.operation_request_id }),
    /still in flight/,
  );
  await assert.rejects(
    a.call("zara_document_apply", { preview_ref: draft.request_id }),
    /still in flight/,
  );
  assert.equal(
    (await a.operation(draft.operation_request_id))?.status,
    "active",
  );
  assert.equal(a.read(created.document_ref.id).revision, 1);
  native.release();
  assert.equal((await running).document_ref.revision, 2);
});

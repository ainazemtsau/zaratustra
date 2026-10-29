import test from "node:test";
import assert from "node:assert/strict";
import { mkdtempSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { Core, digest } from "../src/core/index.ts";
import { DiskStorage } from "../src/storage/index.ts";

function fixture() {
  const root = mkdtempSync(join(tmpdir(), "zara-memory-v2-core-"));
  const disk = new DiskStorage(join(root, ".local", "memory"), undefined, {
    projectRoot: root,
    corpus: "create",
  });
  const core = new Core(disk, {
    ...disk.workspace,
    principal: "trusted-personal",
    session_id: "synthetic",
    runtime_id: "synthetic",
    can_write: true,
    processing_allowed: true,
  });
  return { root, disk, core };
}

test("ordinary successful captures remain transient and cannot become durable without a future purpose", () => {
  const { disk, core } = fixture();
  try {
    let source: ReturnType<Core["capture"]> | undefined;
    for (let n = 0; n < 40; n++)
      source = core.capture(
        "Successful ordinary read " + n,
        "tool",
        null,
        undefined,
        {
          tool_name: "read",
          tool_call_id: "synthetic-" + n,
          is_error: false,
          full_content_hash: digest("synthetic"),
          truncated: false,
        },
      );
    assert.equal(
      disk.get<{ n: number }>("SELECT count(*) n FROM records")!.n,
      0,
    );
    const request = {
      request_id: "no-purpose",
      reason: "Synthetic source policy check",
      source_handles: [source!.source_handle],
      guards: [],
      ops: [
        {
          op: "import_evidence",
          client_ref: "source",
          source_handle: source!.source_handle,
          title: "Observation",
          source_language: "en",
        },
      ],
    };
    assert.throws(
      () => core.commit(request),
      (e: unknown) =>
        (e as { code?: string }).code === "DURABLE_PURPOSE_REQUIRED",
    );
    const saved = core.commit({
      ...request,
      request_id: "meaningful-observation",
      ops: [{ ...request.ops[0], durable_purpose: "reusable_experience" }],
    });
    assert.equal(saved.committed, true);
    assert.equal(
      disk.get<{ n: number }>("SELECT count(*) n FROM records")!.n,
      1,
    );
  } finally {
    disk.close();
  }
});

test("retained source fragments keep exact Unicode bytes and distinguish the omitted original", () => {
  const { disk, core } = fixture();
  try {
    const original = "x".repeat(9000) + "😀real constraint";
    const source = core.capture(original, "rpc", null);
    const receipt = core.commit({
      request_id: "fragment",
      reason: "Retain only the relevant reported constraint",
      source_handles: [source.source_handle],
      guards: [],
      ops: [
        {
          op: "import_evidence",
          client_ref: "fragment",
          source_handle: source.source_handle,
          title: "Constraint source",
          source_language: "en",
          durable_purpose: "constraint",
          source_fragment: { start: 9000, end: Array.from(original).length },
        },
      ],
    });
    const row = core.read(receipt.created.fragment).data as unknown as {
      data: {
        retained_excerpt: string;
        retained_capture: { source_hash: string; availability: string };
        content_hash: string;
      };
    };
    assert.equal(row.data.retained_excerpt, "😀real constraint");
    assert.equal(row.data.content_hash, digest("😀real constraint"));
    assert.equal(row.data.retained_capture.source_hash, digest(original));
    assert.equal(row.data.retained_capture.availability, "retained_fragment");
  } finally {
    disk.close();
  }
});

test("file-primary committed intentions keep exact replay hashes without duplicating successful payload prose", () => {
  const { disk, core } = fixture();
  try {
    const source = core.capture("Create the synthetic activity", "rpc", null);
    const request = {
      request_id: "compact-intention",
      reason: "Preserve a resumable activity",
      source_handles: [source.source_handle],
      guards: [],
      ops: [
        {
          op: "create_record",
          client_ref: "a",
          kind: "activity",
          title: "Synthetic",
          visibility: "workspace",
          data: { purpose: "Continue useful work", status: "active" },
        },
      ],
    };
    const receipt = core.commit(request);
    const intent = JSON.parse(
      disk.get<{ json: string }>(
        "SELECT json FROM intents WHERE request_id=?",
        request.request_id,
      )!.json,
    );
    assert.equal(intent.payload_not_retained, true);
    assert.equal(intent.payload.ops, undefined);
    assert.deepEqual(core.commit(request), receipt);
    assert.throws(
      () =>
        core.commit({ ...request, reason: "Different canonical intention" }),
      (e: unknown) => (e as { code?: string }).code === "IDEMPOTENCY_CONFLICT",
    );
    const activity = core.read(receipt.created.a).data as {
      data: { contract?: { summary: string } };
    };
    assert.equal(activity.data.contract?.summary, "Continue useful work");
  } finally {
    disk.close();
  }
});

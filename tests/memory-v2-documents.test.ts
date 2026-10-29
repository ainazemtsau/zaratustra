import test from "node:test";
import assert from "node:assert/strict";
import { mkdtempSync, readFileSync, existsSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import type { ExtensionContext } from "@earendil-works/pi-coding-agent";
import {
  Core,
  managedDocument,
  type RecordRow,
  type AddressedRow,
} from "../src/core/index.ts";
import { DiskStorage } from "../src/storage/index.ts";
import { SleepV2 } from "../src/core/sleep-v2.ts";
import { registerDocuments } from "../src/extension/documents.ts";

test("file-primary Sleep applies an exact local document through native writing and preserves its previous bytes", async (t) => {
  const project = mkdtempSync(join(tmpdir(), "zara-memory-v2-document-"));
  const disk = new DiskStorage(join(project, ".local/memory"), undefined, {
    projectRoot: project,
    corpus: "create",
  });
  t.after(() => disk.close());
  const core = new Core(disk, {
    ...disk.workspace,
    principal: "trusted-personal",
    session_id: "synthetic-doc",
    runtime_id: "synthetic-doc",
    processing_allowed: true,
    can_write: true,
    scopes: ["restricted:read", "restricted:write"],
  });
  const actions = new Map<string, (p: unknown) => Promise<unknown>>();
  const ctx = {
    cwd: project,
    isProjectTrusted: () => true,
  } as ExtensionContext;
  const documents = registerDocuments(
    (name, _description, schema, action) => {
      actions.set(name, async (p) =>
        action(schema.parse(p) as Record<string, unknown>, ctx),
      );
    },
    { core: () => core, disk: () => disk, clearReady: () => {} },
  );
  const call = async <T>(name: string, p: unknown) =>
    actions.get(name)!(p) as Promise<T>;
  const source = core.capture(
    "Maintain the current local procedure with exact previous versions",
    "rpc",
    null,
  );
  const created = core.commit({
    request_id: "activity",
    reason: "Continue the synthetic local procedure",
    source_handles: [source.source_handle],
    guards: [],
    ops: [
      {
        op: "create_record",
        client_ref: "a",
        kind: "activity",
        title: "Synthetic procedure",
        visibility: "workspace",
        data: { purpose: "Maintain the procedure", status: "active" },
      },
    ],
  });
  const activityId = created.created.a;
  const preview = await call<{ request_id: string }>("zara_document_preview", {
    request_id: "create-document",
    path: "example/procedure.md",
    title: "Local procedure",
    document_type: "procedure",
    content: "# Procedure\n\nKeep the original marker A-71.\n",
    activity_ref: { id: activityId, revision: 1 },
    consequence: "Create one local procedure",
    alternatives: "Keep no procedure",
  });
  const shown = core.approvals.present(preview.request_id);
  core.approvals.answer(shown.token, true, {
    source_ref: "synthetic-controller",
    transport: "native-dialog",
    channel_identity: "synthetic-controller",
    stage: "pi-confirm-return",
  });
  const first = await call<{ document_ref: { id: string; revision: number } }>(
    "zara_document_apply",
    { preview_ref: preview.request_id },
  );
  const oldRow = core.read(first.document_ref.id).data as RecordRow;
  const oldHead = managedDocument(oldRow).head_ref;
  const oldBytes = readFileSync(
    join(project, "activities/example/procedure.md"),
  );
  const activity = core.read(activityId).data as RecordRow;
  core.commit({
    request_id: "bind-contract",
    reason: "Declare the reversible local procedure boundary",
    source_handles: [source.source_handle],
    guards: [{ ref: { id: activityId }, expected_revision: activity.revision }],
    ops: [
      {
        op: "update_record",
        ref: { id: activityId },
        data: {
          ...activity.data,
          contract: {
            summary: "Maintain one local procedure",
            context_refs: [],
            document_refs: [first.document_ref],
            procedure_refs: [],
            memory_scope: "activity",
          },
        },
      },
    ],
  });
  const controller = new SleepV2(disk, core.context, {
    read: (ref) =>
      core.read(ref.id, "revision" in ref ? ref.revision : undefined)
        .data as AddressedRow,
    candidates: () => [],
    runtimeState: () => "dead",
  });
  const cycle = controller.start(activityId, {
    provider: "synthetic",
    id: "synthetic",
    thinking: "medium",
  });
  for (const ref of [{ id: activityId }, first.document_ref, oldHead])
    controller.read(cycle.id, ref);
  controller.analyze(cycle.id, {
    question: "Can the procedure make the next action clear?",
    observations:
      "The current retained procedure contains the original marker.",
    hypothesis: null,
    counterexamples: [],
    grounds: [oldHead],
  });
  const proposal = controller.propose(cycle.id, {
    reason: "Clarify a local procedural instruction",
    expected_benefit: "Next use reads one clear action",
    limits: "A clearer instruction is not proven usefulness",
    premises: [first.document_ref, oldHead],
    request: null,
    document_change: {
      ref: first.document_ref,
      action: "rename",
      path: "example/current-procedure.md",
      content:
        "# Procedure\n\nRead marker A-71 before choosing the next step.\n",
    },
    future_check: {
      trigger: "Next actual use",
      expected_observation: "The agent follows the clear first action",
    },
  });
  assert.equal(controller.validate(cycle.id, proposal.id).status, "validated");
  const admitted = controller.beginApply(cycle.id, proposal.id);
  assert.ok(admitted.document_change);
  const refs = await controller.withApplyPermit(cycle.id, proposal.id, () =>
    documents.applySleep(
      admitted.document_change!,
      admitted,
      controller.status(cycle.id)!,
      ctx,
    ),
  );
  assert.ok(refs.length > 0);
  controller.settleDocument(cycle.id, proposal.id, refs);
  const current = core.read(first.document_ref.id).data as RecordRow;
  const metadata = managedDocument(current);
  assert.equal(current.revision, 2);
  assert.equal(metadata.path, "example/current-procedure.md");
  assert.equal(
    existsSync(join(project, "activities/example/procedure.md")),
    false,
  );
  assert.match(
    readFileSync(
      join(project, "activities/example/current-procedure.md"),
      "utf8",
    ),
    /Read marker A-71/,
  );
  const sourceRow = core.read(oldHead.id, oldHead.revision).data as RecordRow;
  assert.deepEqual(
    Buffer.from(disk.readMaterial(String(sourceRow.data.blob_ref))),
    oldBytes,
    "the exact previous source survives before any Git checkpoint",
  );
  assert.equal(controller.status(cycle.id)!.proposals[0].status, "applied");
  assert.equal(
    controller.status(cycle.id)!.proposals[0].check_observation,
    undefined,
    "applying a change does not claim demonstrated usefulness",
  );
});

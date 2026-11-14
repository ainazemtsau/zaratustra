import test from "node:test";
import assert from "node:assert/strict";
import { createHash, randomUUID } from "node:crypto";
import { DatabaseSync } from "node:sqlite";
import {
  SleepV2,
  assertSleepSkillAllowed,
  isSleepNotDispatched,
} from "../src/core/sleep-v2.ts";
import type {
  SleepSkillChange,
  SleepSkillReceipt,
  SleepV2Bindings,
} from "../src/core/sleep-v2.ts";
import { bundleContentHash } from "../src/core/skills.ts";
import type { BundleManifest } from "../src/core/skills.ts";
import { CoreError, canonical } from "../src/core/contracts.ts";
import type {
  AddressedRow,
  CallContext,
  StoragePort,
} from "../src/core/contracts.ts";

const hash = (text: string) => createHash("sha256").update(text).digest("hex");
const model = { provider: "synthetic", id: "synthetic", thinking: "off" };
const skillId = randomUUID();
function manifest(text: string, script = "return 1;"): BundleManifest {
  const files: BundleManifest["files"] = [
    {
      path: "SKILL.md",
      role: "text",
      length: Buffer.byteLength(text),
      sha256: hash(text),
    },
    { path: "bundle.json", role: "text", length: 2, sha256: hash("{}") },
    {
      path: "scripts/check.js",
      role: "executable",
      length: Buffer.byteLength(script),
      sha256: hash(script),
    },
  ];
  const value = { format: 1 as const, skill_id: skillId, files };
  return { ...value, content_hash: bundleContentHash(value) };
}
function row(
  id: string,
  kind: AddressedRow["kind"],
  data: Record<string, unknown>,
): AddressedRow {
  return {
    id,
    kind,
    title: "Synthetic source",
    body: null,
    revision: 1,
    visibility: "workspace",
    storage: "live",
    created_at: "2026-11-04T00:00:00Z",
    updated_at: "2026-11-04T00:00:00Z",
    concept_ids: [],
    origin_activity_id: null,
    data,
  };
}
function fixture(t: test.TestContext) {
  const db = new DatabaseSync(":memory:");
  t.after(() => db.close());
  db.exec(
    "CREATE TABLE receipts(request_id TEXT PRIMARY KEY,json TEXT NOT NULL)",
  );
  const storage: StoragePort = {
    workspace: {
      workspace_id: "synthetic",
      epoch: "epoch",
      schema_version: 11,
    },
    readonly: false,
    exec: (sql) => db.exec(sql),
    get: <T>(sql: string, ...args: (string | number | null)[]) =>
      db.prepare(sql).get(...args) as T | undefined,
    all: <T>(sql: string, ...args: (string | number | null)[]) =>
      db.prepare(sql).all(...args) as T[],
    run: (sql, ...args) => {
      db.prepare(sql).run(...args);
    },
    readMaterial: () => "",
    withCommandSync: (callback) => callback(),
  };
  const context: CallContext = {
    workspace_id: "synthetic",
    epoch: "epoch",
    principal: "trusted-personal",
    session_id: "session",
    runtime_id: "runtime",
    can_write: true,
    processing_allowed: true,
    scopes: [],
  };
  const rows = new Map([
    ["activity", row("activity", "activity", { status: "active" })],
    [
      "evidence",
      row("evidence", "evidence", {
        source_kind: "observed_input",
        availability: "retained",
      }),
    ],
    [
      "note",
      row("note", "knowledge", { state: "current", knowledge_kind: "fact" }),
    ],
  ]);
  const before = manifest("Before\n"),
    after = manifest("After\n");
  const guard: SleepSkillChange["guard"] = {
    skill_id: skillId,
    activity_id: "activity",
    before_revision: 1,
    before_hash: before.content_hash,
    delegation_revision: 1,
    consumer_digest: hash("one consumer"),
    allowed_paths: ["SKILL.md"],
    max_bytes: 64000,
    activity_revision: 1,
  };
  let activeGuard = structuredClone(guard);
  let access = true;
  const versions = new Map([[1, before]]);
  const receipts = new Map<string, SleepSkillReceipt>();
  const bindings: SleepV2Bindings = {
    read: (input) => {
      const record = rows.get(input.id);
      if (!record) throw new CoreError("REFERENCE_NOT_FOUND", "Unavailable");
      return structuredClone(record);
    },
    candidates: () => [rows.get("note")!],
    runtimeState: () => "dead",
    readSkill: (input) => {
      if (!access) throw new CoreError("REFERENCE_NOT_FOUND", "Unavailable");
      const value = versions.get(input.revision ?? 1);
      if (!value) throw new CoreError("CONTENT_NOT_RETAINED", "Unavailable");
      return {
        skill_id: skillId,
        revision: input.revision ?? 1,
        manifest_hash: value.content_hash,
        visibility: "workspace",
        data: { manifest: value },
      };
    },
    validateSkillChange: (change) =>
      canonical(change.guard) === canonical(activeGuard)
        ? { allowed: true, reason: "Exact delegated text." }
        : {
            allowed: false,
            owner_review: true,
            reason: "Delegation or consumer scope changed.",
          },
    skillReceipt: (id) => receipts.get(id) ?? null,
  };
  const controller = new SleepV2(storage, context, bindings);
  const state = controller.start("activity", model);
  controller.read(state.id, { id: "evidence" });
  controller.readSkill(state.id, { skill_id: skillId, revision: 1 });
  controller.analyze(state.id, {
    question: "Clarify this local procedure?",
    observations: "The retained text is ambiguous.",
    hypothesis: null,
    counterexamples: [],
    grounds: [{ id: "evidence", revision: 1 }],
  });
  const change: SleepSkillChange = {
    guard,
    after_manifest: after,
    changes: [{ path: "SKILL.md", content: "After\n" }],
  };
  const propose = (value: SleepSkillChange = change) =>
    controller.propose(state.id, {
      reason: "Clarify local wording",
      expected_benefit: "A later task follows it correctly.",
      limits: "Text only",
      premises: [{ id: "evidence", revision: 1 }],
      request: null,
      document_change: null,
      skill_change: value,
      future_check: {
        trigger: "Next ordinary use",
        expected_observation: "Correct result",
      },
    });
  const receipt: SleepSkillReceipt = {
    operation_id: "skill-op",
    skill_id: skillId,
    revision: 2,
    manifest_hash: after.content_hash,
    result_refs: [],
  };
  return {
    storage,
    context,
    controller,
    state,
    change,
    propose,
    receipts,
    receipt,
    versions,
    bindings,
    changeGuard: (values: Partial<typeof guard>) => {
      activeGuard = { ...activeGuard, ...values };
    },
    denyAccess: () => {
      access = false;
    },
  };
}

test("Sleep skill application needs an exact private permit and verified durable receipt", (t) => {
  const f = fixture(t),
    proposal = f.propose();
  assert.equal(
    f.controller.validate(f.state.id, proposal.id).status,
    "validated",
  );
  f.controller.beginApply(f.state.id, proposal.id);
  assert.throws(
    () =>
      f.controller.inExecution(f.state.id, () =>
        assertSleepSkillAllowed(f.storage, f.context, f.change, "skill-op"),
      ),
    /no admitted|not available|unused exact/i,
  );
  f.controller.withApplyPermit(f.state.id, proposal.id, () => {
    assert.equal(
      assertSleepSkillAllowed(f.storage, f.context, f.change, "skill-op"),
      true,
    );
    assert.throws(
      () => assertSleepSkillAllowed(f.storage, f.context, f.change, "skill-op"),
      /unused exact/,
    );
  });
  assert.throws(
    () => f.controller.settleSkill(f.state.id, proposal.id, f.receipt),
    /durable activation receipt/,
  );
  f.receipts.set("skill-op", f.receipt);
  f.versions.set(2, f.change.after_manifest);
  const result = f.controller.settleSkill(f.state.id, proposal.id, f.receipt);
  assert.equal(result.improvements, 1);
  assert.equal(result.phase, "future_check");
  assert.equal(
    result.proposals[0].skill_result?.manifest_hash,
    f.change.after_manifest.content_hash,
  );
  const done = f.controller.finish(
    f.state.id,
    "applied_unverified",
    "Applied exact text; future check remains pending.",
  );
  assert.equal(done.proposals[0].check_observation, undefined);
});

test("Sleep script and undelegated text changes remain pending owner review", (t) => {
  const f = fixture(t);
  const script = manifest("Before\n", "return 2;");
  const proposal = f.propose({
    ...f.change,
    after_manifest: script,
    changes: [{ path: "scripts/check.js", content: "return 2;" }],
  });
  assert.equal(
    f.controller.validate(f.state.id, proposal.id).status,
    "pending_owner_review",
  );
  assert.throws(
    () => f.controller.beginApply(f.state.id, proposal.id),
    /not authorized/,
  );
});

test("Sleep rechecks delegation and consumers after validation and at actual dispatch", (t) => {
  const f = fixture(t),
    proposal = f.propose();
  f.controller.validate(f.state.id, proposal.id);
  f.changeGuard({ consumer_digest: hash("shared") });
  assert.throws(
    () => f.controller.beginApply(f.state.id, proposal.id),
    /scope changed/,
  );
  f.changeGuard({ consumer_digest: f.change.guard.consumer_digest });
  f.controller.beginApply(f.state.id, proposal.id);
  f.changeGuard({ delegation_revision: 2 });
  let refusal: unknown;
  try {
    f.controller.withApplyPermit(f.state.id, proposal.id, () =>
      assertSleepSkillAllowed(f.storage, f.context, f.change, "skill-op"),
    );
  } catch (error) {
    refusal = error;
  }
  assert.equal(isSleepNotDispatched(refusal), true);
  const result = f.controller.rejectUnapplied(f.state.id, proposal.id, refusal);
  assert.equal(result.improvements, 0);
  assert.equal(result.proposals[0].native_request_id, undefined);
});

test("Sleep lost skill result reconciles original receipt without dispatch replay", (t) => {
  const f = fixture(t),
    proposal = f.propose();
  f.controller.validate(f.state.id, proposal.id);
  f.controller.beginApply(f.state.id, proposal.id);
  f.controller.withApplyPermit(f.state.id, proposal.id, () =>
    assertSleepSkillAllowed(f.storage, f.context, f.change, "skill-op"),
  );
  f.controller.markUnknown(f.state.id, proposal.id, "Lost result");
  assert.throws(() => f.controller.reconcile(f.state.id), /unresolved/);
  f.receipts.set("skill-op", f.receipt);
  f.versions.set(2, f.change.after_manifest);
  assert.equal(f.controller.reconcile(f.state.id).improvements, 1);
  assert.equal(f.controller.reconcile(f.state.id).improvements, 1);
});

test("Saved Sleep skill sources retain their current access boundary", (t) => {
  const f = fixture(t);
  f.propose();
  f.denyAccess();
  assert.throws(() => f.controller.status(f.state.id), /Unavailable/);
});

test("A skill shared or undelegated from the start can produce only an owner-review candidate", (t) => {
  const f = fixture(t);
  f.bindings.validateSkillChange = () => {
    throw new Error(
      "A review-only proposal must never request a local permit.",
    );
  };
  const change: SleepSkillChange = {
    guard: null,
    selection: {
      skill_id: skillId,
      revision: 1,
      manifest_hash: f.change.guard!.before_hash,
    },
    after_manifest: f.change.after_manifest,
    changes: f.change.changes,
  };
  const proposal = f.propose(change);
  const checked = f.controller.validate(f.state.id, proposal.id);
  assert.equal(checked.status, "pending_owner_review");
  assert.throws(
    () => f.controller.beginApply(f.state.id, proposal.id),
    /not authorized/,
  );
  assert.equal(f.controller.status(f.state.id)?.improvements, 0);
  const pending = f.controller.finish(
    f.state.id,
    "proposal_pending",
    "Exact shared skill candidate awaits owner review.",
  );
  assert.equal(pending.proposals[0].skill_change?.guard, null);
});

test("Review-only skill selection is grounded and its proposed bytes must match", (t) => {
  const f = fixture(t);
  const base = {
    guard: null,
    selection: {
      skill_id: skillId,
      revision: 1,
      manifest_hash: f.change.guard!.before_hash,
    },
    after_manifest: f.change.after_manifest,
    changes: [{ path: "SKILL.md", content: "Different bytes" }],
  };
  assert.throws(
    () =>
      f.propose({
        ...base,
        selection: { ...base.selection, manifest_hash: hash("unread") },
      }),
    /exact selected bundle/,
  );
  const proposal = f.propose(base);
  assert.equal(
    f.controller.validate(f.state.id, proposal.id).status,
    "rejected",
  );
});

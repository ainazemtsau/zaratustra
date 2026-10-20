// Developer-only filled accepted D -> E1 qualification, always synthetic homes.
import assert from "node:assert/strict";
import { createRequire } from "node:module";
import { pathToFileURL } from "node:url";
import { join, resolve } from "node:path";
import { mkdirSync, writeFileSync, readFileSync, readdirSync } from "node:fs";
import { execFileSync } from "node:child_process";
const [mode, pkgArg, homeArg, outArg] = process.argv.slice(2),
  pkg = resolve(pkgArg),
  home = resolve(homeArg),
  out = resolve(outArg);
mkdirSync(out, { recursive: true });
const { createJiti } = createRequire(pathToFileURL(process.env.ZARA_PI_SDK))(
    "jiti",
  ),
  jiti = createJiti(import.meta.url);
const { Core, digest } = await jiti.import(join(pkg, "src/core/index.ts")),
  { DiskStorage } = await jiti.import(join(pkg, "src/storage/index.ts"));
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
const rows = (d) =>
  Object.fromEntries(
    tables.map((t) => [t, d.all("SELECT * FROM " + t + " ORDER BY rowid")]),
  );
const materials = () =>
  Object.fromEntries(
    readdirSync(join(home, "materials")).map((n) => [
      n,
      digest(readFileSync(join(home, "materials", n))),
    ]),
  );
const head = execFileSync("git", ["-C", pkg, "rev-parse", "HEAD"], {
  encoding: "utf8",
}).trim();
if (mode === "old-reject") {
  assert.throws(
    () => new DiskStorage(home),
    /Unknown schema|identity mismatch/,
  );
  writeFileSync(
    join(out, "old-rejection.json"),
    JSON.stringify({ head, rejected: true, no_replacement: true }),
  );
} else {
  const disk = new DiskStorage(home),
    core = new Core(disk, {
      ...disk.workspace,
      principal: "trusted-personal",
      session_id: "synthetic-upgrade-E1",
      runtime_id: "synthetic-upgrade-E1",
      processing_allowed: true,
      can_write: true,
    });
  const baseline = join(out, "before.json");
  try {
    if (mode === "seed") {
      assert.equal(head, "1b742a6e774eaa14826c036977ae2a42ff1ca46a");
      assert.equal(disk.workspace.schema_version, 3);
      const path = join(out, "original.md"),
        bytes = Buffer.from(
          "\ufeff# Preserved upgrade material\r\n" +
            "Original 🦉. ".repeat(1000) +
            "\r\nTail stays exact: V-29.\r\n",
        );
      writeFileSync(path, bytes);
      const m = disk.importFile(path, [out]),
        source = core.capture(m.text, "file", null, m),
        input = core.capture(
          "Создай работу с сохранённым материалом и черновиком передачи.",
          "rpc",
          "synthetic-upgrade-controller",
        );
      const first = {
        request_id: "upgrade-E1-initial",
        reason: "Preserve populated accepted installation",
        source_handles: [source.source_handle, input.source_handle],
        guards: [],
        ops: [
          {
            op: "import_evidence",
            client_ref: "material",
            source_handle: source.source_handle,
            title: "Original retained material",
            source_language: "en",
          },
          {
            op: "import_evidence",
            client_ref: "input",
            source_handle: input.source_handle,
            title: "Original request",
            source_language: "ru",
          },
          {
            op: "create_record",
            client_ref: "a",
            kind: "activity",
            title: "Upgrade qualification",
            visibility: "workspace",
            data: { purpose: "Keep prior accepted data", status: "active" },
          },
          {
            op: "create_record",
            client_ref: "w",
            kind: "work",
            title: "Prepare retained note",
            visibility: "workspace",
            data: {
              activity_id: { client_ref: "a" },
              parent_work_id: null,
              objective: "Prepare a grounded note",
              acceptance: [
                {
                  criterion_id: "note",
                  description: "Retained note",
                  verification: "Inspect exact generated artifact",
                  required: true,
                },
              ],
              status: "active",
              current_state: "Ready to prepare",
              next_action: "Prepare the note",
              steps: [],
              waits: [],
              context_refs: [{ client_ref: "material" }],
              completion: null,
            },
          },
          {
            op: "create_record",
            client_ref: "k",
            kind: "knowledge",
            title: "Language preference",
            visibility: "workspace",
            data: {
              knowledge_kind: "preference",
              statement: "The user prefers Russian replies.",
              state: "current",
              basis: "user_statement",
              evidence_refs: [{ client_ref: "input" }],
              conditions: "Conversation",
              representation: {
                kind: "English paraphrase",
                source_ref: { client_ref: "input" },
                source_language: "ru",
              },
            },
          },
          {
            op: "set_focus",
            activity_ref: { client_ref: "a" },
            work_ref: { client_ref: "w" },
          },
        ],
      };
      const receipt = core.commit(first),
        ids = receipt.created;
      const claim = core.claim({
        action: "acquire",
        work_id: ids.w,
        expected_revision: 1,
        purpose: "handoff",
        reason: "Prepare immutable synthetic handoff",
      }).data;
      const handoff = core.commit({
        request_id: "upgrade-E1-handoff",
        reason: "Keep original manual preparation",
        source_handles: [input.source_handle],
        guards: [{ ref: { id: ids.w }, expected_revision: 1 }],
        claim_tokens: [claim.token],
        ops: [
          {
            op: "prepare_handoff",
            client_ref: "h",
            work_ref: { id: ids.w },
            objective: "Inspect the note",
            conditions: "Synthetic preparation only",
            expected_result: "A useful review",
            context_refs: [{ id: ids.material, revision: 1 }],
            message: "Please inspect the retained note. Nothing has been sent.",
          },
        ],
      }).created.h;
      const completion = core.claim({
        action: "acquire",
        work_id: ids.w,
        expected_revision: 1,
        purpose: "work",
        reason: "Record actual synthetic result",
      }).data;
      core.commit({
        request_id: "upgrade-E1-complete",
        reason: "Retain historical completion",
        source_handles: [input.source_handle],
        guards: [{ ref: { id: ids.w }, expected_revision: 1 }],
        claim_tokens: [completion.token],
        ops: [
          {
            op: "record_result",
            client_ref: "r",
            work_ref: { id: ids.w },
            title: "Prepared synthetic note",
            content: "Exact synthetic note, grounded in the retained material.",
            source_language: "en",
          },
          {
            op: "transition_work",
            ref: { id: ids.w },
            status: "done",
            reason: "Prepared note retained",
            grounds: [
              {
                criterion_id: "note",
                explanation: "The addressed note exists",
                evidence_refs: [{ client_ref: "r" }],
              },
            ],
          },
        ],
      });
      const reopen = core.capture(
        "Возобнови эту работу: позднее пришлю уточнение.",
        "rpc",
        "synthetic-upgrade-controller",
      );
      core.commit({
        request_id: "upgrade-E1-reopen",
        reason: "Preserve explicit reopening and old completion",
        source_handles: [reopen.source_handle],
        guards: [{ ref: { id: ids.w }, expected_revision: 2 }],
        ops: [
          {
            op: "transition_work",
            ref: { id: ids.w },
            status: "active",
            reason: "Explicitly reopened for future clarification",
            decision_source_handle: reopen.source_handle,
            next_action: "Record the new clarification wait",
          },
        ],
      });
      const w = core.read(ids.w).data;
      core.commit({
        request_id: "upgrade-E1-wait",
        reason: "Keep concrete future wait",
        source_handles: [reopen.source_handle],
        guards: [{ ref: { id: ids.w }, expected_revision: 3 }],
        ops: [
          {
            op: "update_record",
            ref: { id: ids.w },
            data: {
              ...w.data,
              waits: [
                {
                  wait_id: "clarification",
                  kind: "user",
                  target: "work",
                  subject: "New clarification",
                  satisfied_by: "The specific clarification arrives",
                  received_refs: [],
                  question: "Please send the clarification.",
                  status: "pending",
                },
              ],
              next_action: null,
            },
            plan_change_reason: "New wait from explicit reopened objective",
            decision_source_handle: reopen.source_handle,
          },
          {
            op: "transition_work",
            ref: { id: ids.w },
            status: "waiting",
            reason: "No independent work before the promised clarification",
            next_action: null,
          },
        ],
      });
      writeFileSync(
        baseline,
        JSON.stringify(
          {
            head,
            workspace: disk.workspace,
            rows: rows(disk),
            materials: materials(),
            ids,
            handoff,
            first,
            receipt,
          },
          null,
          2,
        ),
      );
    } else if (mode === "verify") {
      const before = JSON.parse(readFileSync(baseline, "utf8"));
      assert.equal(disk.workspace.schema_version, 4);
      assert.equal(disk.workspace.workspace_id, before.workspace.workspace_id);
      assert.equal(disk.workspace.epoch, before.workspace.epoch);
      assert.equal(JSON.stringify(rows(disk)), JSON.stringify(before.rows));
      assert.deepEqual(materials(), before.materials);
      assert.deepEqual(core.commit(before.first), before.receipt);
      assert.equal(core.read(before.ids.w, 2).data.data.status, "done");
      assert.equal(core.read(before.ids.w).data.data.status, "waiting");
      assert.equal(
        core.handoff(before.handoff).data.transport_state,
        "prepared_not_sent",
      );
      const migration = JSON.parse(
        disk.get("SELECT json FROM migrations WHERE version=4").json,
      );
      assert.equal(
        digest(readFileSync(migration.backup)),
        migration.backup_sha256,
      );
      const search = core.search({
        query: "Russian",
        match: "all",
        kinds: ["knowledge"],
      });
      assert.equal(search.data.cards[0].id, before.ids.k);
      writeFileSync(
        join(out, "verification.json"),
        JSON.stringify(
          {
            head,
            preserved_tables: tables,
            all_rows_exact: true,
            materials_exact: true,
            workspace_identity_exact: true,
            epoch_exact: true,
            old_receipt_replay_exact: true,
            historical_completion: true,
            current_reopen_wait: true,
            immutable_handoff: true,
            migration,
            search,
            after: rows(disk),
          },
          null,
          2,
        ),
      );
    } else throw new Error("Unknown mode");
  } finally {
    disk.close();
  }
}
console.log(JSON.stringify({ mode, head, checked: true }));

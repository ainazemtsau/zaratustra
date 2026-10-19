// Developer-only synthetic fixture/readback for an actual Pi-installed predecessor.
import assert from "node:assert/strict";
import { createRequire } from "node:module";
import { pathToFileURL } from "node:url";
import { join, resolve } from "node:path";
import { mkdirSync, readFileSync, writeFileSync, readdirSync } from "node:fs";
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
const { Core, digest } = await jiti.import(join(pkg, "src/core/index.ts"));
const { DiskStorage } = await jiti.import(join(pkg, "src/storage/index.ts"));
const tables = [
  "records",
  "revisions",
  "changes",
  "intents",
  "receipts",
  "focus",
];
const snapshot = (disk) =>
  Object.fromEntries(
    tables.map((t) => [t, disk.all("SELECT * FROM " + t + " ORDER BY rowid")]),
  );
const baseline = join(out, "predecessor-state.json");
if (mode === "old-reject") {
  assert.throws(
    () => new DiskStorage(home),
    /Unknown schema|identity mismatch/,
  );
  writeFileSync(
    join(out, "old-writer-rejection.json"),
    JSON.stringify({
      old_head: execFileSync("git", ["-C", pkg, "rev-parse", "HEAD"], {
        encoding: "utf8",
      }).trim(),
      rejected: true,
    }),
  );
} else {
  const disk = new DiskStorage(home),
    core = new Core(disk, {
      ...disk.workspace,
      principal: "trusted-personal",
      session_id: "upgrade-synthetic",
      runtime_id: "upgrade-synthetic",
      can_write: true,
      processing_allowed: true,
    });
  if (mode === "seed") {
    assert.equal(disk.workspace.schema_version, 1);
    const inputs = join(out, "original-inputs");
    mkdirSync(inputs, { recursive: true });
    const path = join(inputs, "retained.md");
    const original = Buffer.from(
      "\ufeff# Pre-upgrade original\r\n" +
        "Context 🦉. ".repeat(900) +
        "\r\nTail: keep slot V-29 exactly.\r\n",
    );
    writeFileSync(path, original);
    const m = disk.importFile(path, [inputs]),
      s = core.capture(m.text, "file", null, m),
      u = core.capture(
        "Создай работу; часть материалов пришлю позже.",
        "rpc",
        "trusted-synthetic-upgrade-controller",
      );
    const payload = {
      request_id: "predecessor-create",
      reason:
        "Retain accepted first-block synthetic state before actual upgrade",
      source_handles: [s.source_handle, u.source_handle],
      guards: [],
      ops: [
        {
          op: "import_evidence",
          client_ref: "original",
          source_handle: s.source_handle,
          title: "Pre-upgrade material",
          source_language: "en",
        },
        {
          op: "import_evidence",
          client_ref: "input",
          source_handle: u.source_handle,
          title: "Original Russian request",
          source_language: "ru",
        },
        {
          op: "create_record",
          client_ref: "activity",
          kind: "activity",
          title: "Upgrade continuity",
          visibility: "workspace",
          data: {
            purpose: "Preserve exact existing state across migration",
            status: "active",
          },
        },
        {
          op: "create_record",
          client_ref: "work",
          kind: "work",
          title: "Waiting pre-upgrade Work",
          visibility: "workspace",
          data: {
            activity_id: { client_ref: "activity" },
            parent_work_id: null,
            objective: "Read the remaining material when received",
            acceptance: [
              {
                criterion_id: "review",
                description: "Grounded review",
                verification: "Retained source and result",
                required: true,
              },
            ],
            status: "waiting",
            current_state:
              "Initial excerpt received; remaining material missing",
            next_action: "Ask for remaining material",
            steps: [],
            waits: [
              {
                wait_id: "remaining",
                kind: "user",
                target: "work",
                subject: "Remaining material",
                satisfied_by: "Full remaining material received",
                received_refs: [{ client_ref: "original" }],
                question: "Send the remaining material",
              },
            ],
            context_refs: [{ client_ref: "input" }, { client_ref: "original" }],
            completion: null,
          },
        },
      ],
    };
    const receipt = core.commit(payload),
      w = core.read(receipt.created.work).data;
    core.commit({
      request_id: "predecessor-revision",
      reason: "Retain a second existing Work revision",
      source_handles: [u.source_handle],
      guards: [{ ref: { id: w.id }, expected_revision: 1 }],
      ops: [
        {
          op: "update_record",
          ref: { id: w.id },
          data: {
            ...w.data,
            current_state:
              "An exact excerpt is retained; the whole remaining material is still missing",
          },
        },
      ],
    });
    const state = {
      head: execFileSync("git", ["-C", pkg, "rev-parse", "HEAD"], {
        encoding: "utf8",
      }).trim(),
      workspace: disk.workspace,
      tables: snapshot(disk),
      materials: Object.fromEntries(
        readdirSync(join(home, "materials")).map((n) => [
          n,
          digest(readFileSync(join(home, "materials", n))),
        ]),
      ),
      payload,
      receipt,
      original_sha256: digest(original),
      text: m.text,
    };
    writeFileSync(baseline, JSON.stringify(state, null, 2));
  } else if (mode === "verify") {
    const before = JSON.parse(readFileSync(baseline, "utf8"));
    assert.equal(disk.workspace.schema_version, 2);
    assert.equal(disk.workspace.workspace_id, before.workspace.workspace_id);
    assert.equal(disk.workspace.epoch, before.workspace.epoch);
    assert.deepEqual(snapshot(disk), before.tables);
    for (const [name, hash] of Object.entries(before.materials))
      assert.equal(digest(readFileSync(join(home, "materials", name))), hash);
    assert.deepEqual(core.commit(before.payload), before.receipt);
    assert.equal(
      core.read(before.receipt.created.original, 1, {
        start: 8000,
        length: 8000,
      }).data.text,
      Array.from(before.text).slice(8000).join(""),
    );
    const migrations = disk.all("SELECT * FROM migrations");
    assert.equal(migrations.length, 1);
    writeFileSync(
      join(out, "upgrade-verification.json"),
      JSON.stringify(
        {
          head: execFileSync("git", ["-C", pkg, "rev-parse", "HEAD"], {
            encoding: "utf8",
          }).trim(),
          identity_preserved: true,
          all_original_rows_exact: true,
          material_hashes_preserved: true,
          old_receipt_replay_exact: true,
          p2_tail_exact: true,
          before_counts: Object.fromEntries(
            Object.entries(before.tables).map(([k, v]) => [k, v.length]),
          ),
          migrations,
          doctor: disk.doctor(),
        },
        null,
        2,
      ),
    );
  } else throw new Error("Unknown mode");
  disk.close();
}
console.log(JSON.stringify({ mode, passed: true }));

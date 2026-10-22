// Mechanical synthetic preparation through public Core only. No model replies.
// Can generate progressed schema-7 with the historical installed writer supplied
// as pkg; the fixed native candidate then opens that existing store normally.
import assert from "node:assert/strict";
import { createRequire } from "node:module";
import { pathToFileURL } from "node:url";
import { resolve, join, relative } from "node:path";
import { mkdirSync, writeFileSync, existsSync } from "node:fs";
import { execFileSync } from "node:child_process";

const [pkgArg, rootArg] = process.argv.slice(2);
const pkg = resolve(pkgArg),
  root = resolve(rootArg);
assert(root.toLowerCase().includes("zaratustra-v1-sleep-evidence-20261022"));
assert(relative(pkg, root).startsWith(".."));
assert(!existsSync(join(root, "home")), "Never overwrite an existing fixture");
for (const name of ["output", "backups"])
  mkdirSync(join(root, name), { recursive: true });
const { createJiti } = createRequire(pathToFileURL(process.env.ZARA_PI_SDK))(
  "jiti",
);
const jiti = createJiti(import.meta.url);
const { Core } = await jiti.import(join(pkg, "src/core/index.ts"));
const { DiskStorage } = await jiti.import(join(pkg, "src/storage/index.ts"));
const disk = new DiskStorage(join(root, "home"));
const ctx = {
  ...disk.workspace,
  principal: "trusted-personal",
  session_id: "mechanical-privacy-preparation",
  runtime_id: "fixture",
  processing_allowed: true,
  can_write: true,
  scopes: ["restricted:read", "restricted:write"],
};
const core = new Core(disk, ctx);
let serial = 0;
const source = core.capture(
  "Mechanical synthetic preparation; not owner testimony.",
  "rpc",
  "sleep-privacy-fixture",
);
const read = (id) => core.read(id).data;
const request = (ops, ids = []) => ({
  request_id: "privacy-fixture-" + ++serial,
  reason: "Mechanical synthetic preparation",
  source_handles: [source.source_handle],
  guards: [...new Set(ids)].map((id) => ({
    ref: { id },
    expected_revision: read(id).revision,
  })),
  ops,
});
const commit = (ops, ids = []) => core.commit(request(ops, ids));
const evidence = (title, text, visibility = "workspace") => {
  const s = core.capture(text, "rpc", "sleep-privacy-fixture");
  const r = request([
    {
      op: "import_evidence",
      client_ref: "e",
      source_handle: s.source_handle,
      title,
      source_language: "en",
      visibility,
    },
  ]);
  r.source_handles = [s.source_handle];
  return core.commit(r).created.e;
};
try {
  const permitted = "PERMITTED-HISTORY-POSITIVE-220961";
  const pub = evidence(
    "Permitted history positive control",
    permitted +
      ". A synthetic retained source; no improvement is justified by this routing exercise.",
  );
  const m = commit([
    {
      op: "create_record",
      kind: "method",
      client_ref: "m",
      title: "Synthetic derived guidance",
      visibility: "workspace",
      data: {
        applicability: "Synthetic routing",
        instructions: "Read retained source",
        input_contract: "Addressed source",
        expected_output: "Grounded reading",
        context_requirements: [
          {
            description: "Source",
            refs: [{ id: pub }],
            selector: null,
            retrieval: "Read exact source",
          },
        ],
        dependencies: [],
        tool_requirements: [],
        content_version: 1,
        state: "candidate",
        derived_from: [],
        limitations: "No usefulness assessed",
      },
    },
  ]).created.m;
  const secret = "SYNTHETIC-PROTECTED-SLEEP-INPUT-" + crypto.randomUUID();
  const priv = evidence("Synthetic protected input", secret, "restricted");
  for (let i = 1; i <= 12; i++)
    evidence(
      "Permitted routing sample " + i,
      "Synthetic permitted sample " +
        i +
        ". Retained for a finite routing/continuation exercise, no claimed success or required correction.",
    );
  const ids = commit([
    {
      op: "create_record",
      kind: "work",
      client_ref: "w",
      title: "Synthetic protected review progress",
      visibility: "workspace",
      data: {
        activity_id: null,
        parent_work_id: null,
        objective: "Inspect retained synthetic material",
        acceptance: [
          {
            criterion_id: "coverage",
            description: "Frozen coverage",
            verification: "Dispositions",
            required: true,
          },
        ],
        status: "active",
        current_state: "Requested",
        next_action: "Review",
        steps: [],
        waits: [],
        context_refs: [],
        completion: null,
      },
    },
    {
      op: "start_run",
      client_ref: "r",
      title: "Synthetic protected review",
      visibility: "workspace",
      episode_key: "prepared-private-review",
      work_ref: { client_ref: "w" },
      mode: "sleep",
      continuation_of: null,
      summary: "Mechanical review preparation",
      starting_refs: [],
    },
    {
      op: "start_sleep",
      work_ref: { client_ref: "w" },
      run_ref: { client_ref: "r" },
    },
  ]).created;
  let first = true,
    checkpointIds = [];
  while (core.sleepBatch(ids.r).status === "active") {
    const b = core.sleepBatch(ids.r);
    const ops = first
      ? [
          {
            op: "revise_method",
            ref: { id: m },
            data: {
              ...read(m).data,
              instructions: "Derived protected ground: " + secret,
            },
          },
          {
            op: "update_record",
            ref: { id: ids.w },
            title: read(ids.w).title,
            data: {
              ...read(ids.w).data,
              current_state: "Protected review summary: " + secret,
            },
          },
          {
            op: "open_signal",
            client_ref: "s",
            kind: "problem",
            subject_refs: [{ id: m, revision: 2 }],
            evidence_refs: [{ id: priv, revision: 1 }],
            description: "Synthetic pending verification",
            next_check: "Next suitable real case",
            visibility: "workspace",
          },
        ]
      : [];
    ops.push({
      op: "sleep_checkpoint",
      run_ref: { id: ids.r },
      batch_id: b.batch_id,
      dispositions: b.cards.map((c, i) => ({
        item_id: c.item_id,
        disposition: first && i === 0 ? "changed" : "considered",
        reason: "Read actual protected grounds: " + secret,
        continuation: null,
        evidence_refs: first && i === 0 ? [{ id: priv, revision: 1 }] : [],
        change_refs: first && i === 0 ? [{ id: m, revision: 2 }] : [],
        expected_benefit: first && i === 0 ? "Synthetic correction" : null,
        limits: first && i === 0 ? "Unverified" : null,
        next_check: first && i === 0 ? "Next suitable real case" : null,
        check_signal_ref: first && i === 0 ? { client_ref: "s" } : null,
      })),
    });
    const r = request(ops, [
      ...b.cards.map((c) => c.ref.id),
      priv,
      ...(first ? [m, ids.w] : []),
    ]);
    r.reason = "Protected checkpoint: " + secret;
    core.commit(r);
    checkpointIds.push(r.request_id);
    first = false;
  }
  const sha = execFileSync("git", ["rev-parse", "HEAD"], {
    cwd: pkg,
    encoding: "utf8",
  }).trim();
  writeFileSync(
    join(root, "fixture.json"),
    JSON.stringify(
      {
        mechanical_only: true,
        generated_by_public_installed_sha: sha,
        provider_dispatches: 0,
        secret,
        permitted,
        public_evidence: pub,
        private_evidence: priv,
        derived_method: m,
        review_work: ids.w,
        review_run: ids.r,
        checkpoint_request_ids: checkpointIds,
        canonical_before_model: {
          records: disk.all("SELECT * FROM records"),
          items: disk.all("SELECT * FROM sleep_items"),
        },
      },
      null,
      2,
    ),
  );
  console.log(
    JSON.stringify({
      mechanical_only: true,
      generated_by_public_installed_sha: sha,
      fixture: root,
      public_samples: 13,
      prepared_review_complete: true,
      provider_dispatches: 0,
    }),
  );
} finally {
  disk.close();
}

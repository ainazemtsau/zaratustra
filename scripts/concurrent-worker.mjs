import { readFileSync, writeFileSync, existsSync } from "node:fs";
import { performance } from "node:perf_hooks";
import { createHash } from "node:crypto";

let completed = false;
// Disconnect events run between synchronous phases; OS exit releases only this
// worker's lease and prevents orphan work after a controller timeout.
process.once("disconnect", () => {
  if (!completed) process.exit(2);
});
const config = JSON.parse(readFileSync(process.argv[2], "utf8"));
const backend = config.compiled ? "dist" : "src",
  extension = config.compiled ? "js" : "ts";
const [{ Core }, { DiskStorage }, { Coordination }] = await Promise.all([
  import(new URL(`../${backend}/core/index.${extension}`, import.meta.url)),
  import(new URL(`../${backend}/storage/index.${extension}`, import.meta.url)),
  import(
    new URL(`../${backend}/storage/coordination.${extension}`, import.meta.url)
  ),
]);
const wait = (ms) => new Promise((done) => setTimeout(done, ms));
const started = performance.now();
const barrierDeadline = Date.now() + (config.timeoutMs ?? 240_000);
let coordination;
let disk;
const report = {
  worker: config.worker,
  pid: process.pid,
  mode: config.mode,
  saves: [],
  receipts: [],
  startup_ms: 0,
  source_hashes: Object.fromEntries(
    [
      "core/index.ts",
      "core/memory.ts",
      "core/memory-index.ts",
      "storage/index.ts",
      "storage/coordination.ts",
    ].map((path) => [
      path,
      createHash("sha256")
        .update(readFileSync(new URL("../src/" + path, import.meta.url)))
        .digest("hex"),
    ]),
  ),
  rss_peak_bytes: process.memoryUsage().rss,
  backend,
  backend_hashes: Object.fromEntries(
    [
      "core/index",
      "core/memory",
      "core/memory-index",
      "storage/index",
      "storage/coordination",
    ].map((path) => [
      path,
      createHash("sha256")
        .update(
          readFileSync(
            new URL(`../${backend}/${path}.${extension}`, import.meta.url),
          ),
        )
        .digest("hex"),
    ]),
  ),
  model_calls: 0,
};
function sample() {
  report.rss_peak_bytes = Math.max(
    report.rss_peak_bytes,
    process.memoryUsage().rss,
  );
}
async function retry(callback) {
  const deadline = Date.now() + (config.timeoutMs ?? 180_000);
  for (;;) {
    try {
      return callback();
    } catch (error) {
      if (error.code !== "STORE_BUSY" || Date.now() >= deadline) throw error;
      await wait(5 + Math.floor(Math.random() * 20));
    }
  }
}
function workData(activity) {
  return {
    activity_id: activity,
    parent_work_id: null,
    objective: `Synthetic qualification work ${config.worker}`,
    acceptance: [
      {
        criterion_id: "persisted",
        description: "Synthetic saves retained",
        verification: "Inspect committed revisions",
        required: true,
      },
    ],
    status: "draft",
    current_state: "Synthetic initial state",
    next_action: "Continue synthetic qualification",
    steps: [],
    waits: [],
    context_refs: [],
    completion: null,
    plan_version: 1,
  };
}
async function close() {
  if (!disk || !coordination) return;
  await disk.withOperation("maintenance", () => disk.closeConnection(), {
    timeoutMs: 60_000,
  });
  disk.close();
  await retry(() => coordination.close());
}
try {
  const coordinationStarted = performance.now();
  coordination = await retry(
    () =>
      new Coordination(config.home, undefined, {
        expectedId: config.identity,
        create: false,
      }),
  );
  report.coordination_open_ms = performance.now() - coordinationStarted;
  const diskStarted = performance.now();
  // Retain this runtime lease across b0 constructor-admission retries.
  disk = await retry(
    () => new DiskStorage(config.home, undefined, { coordination }),
  );
  report.disk_open_ms = performance.now() - diskStarted;
  const core = new Core(
    disk,
    {
      ...disk.workspace,
      principal: "trusted-personal",
      session_id: `qualification-${config.worker}`,
      runtime_id: coordination.runtimeId,
      can_write: true,
      processing_allowed: true,
    },
    config.mode === "crash"
      ? (point) => {
          if (point === "after_commit") process.exit(73);
        }
      : undefined,
  );
  let target = config.target;
  let targetRow;
  if (config.mode === "conflict")
    targetRow = await disk.withOperation("read", () => core.read(target).data);
  report.startup_ms = performance.now() - started;
  sample();
  process.send?.({
    type: "ready",
    worker: config.worker,
    runtime_id: coordination.runtimeId,
    startup_ms: report.startup_ms,
    coordination_open_ms: report.coordination_open_ms,
    disk_open_ms: report.disk_open_ms,
  });
  while (!existsSync(config.start)) {
    if (Date.now() > barrierDeadline)
      throw new Error("Worker barrier timed out");
    await wait(10);
  }
  let lastPayload, lastReceipt;
  for (let save = 0; save < config.saves; save++) {
    const queued = performance.now();
    let entered, completed;
    try {
      const receipt = await disk.withOperation(
        "mutate",
        () => {
          entered = performance.now();
          const source = core.capture(
            `Synthetic concurrent save ${config.worker}/${save}. No owner data or model call.`,
            "rpc",
            "synthetic-qualification-controller",
          );
          let ops,
            guards = [];
          if (config.mode === "conflict") {
            guards = [
              { ref: { id: target }, expected_revision: targetRow.revision },
            ];
            ops = [
              {
                op: "update_record",
                ref: { id: target },
                data: {
                  ...targetRow.data,
                  current_state: `Synthetic conflicting save ${config.worker}`,
                },
              },
            ];
          } else if (!target) {
            const activity =
              config.mode === "separate" || config.mode === "crash"
                ? { client_ref: "activity" }
                : { id: config.activity };
            ops = [
              ...(activity.client_ref
                ? [
                    {
                      op: "create_record",
                      client_ref: "activity",
                      kind: "activity",
                      title: `Qualification Activity ${config.worker}`,
                      visibility: "workspace",
                      data: {
                        purpose: "Synthetic independent concurrent writes",
                        status: "active",
                      },
                    },
                  ]
                : []),
              {
                op: "create_record",
                client_ref: "work",
                kind: "work",
                title: `Qualification Work ${config.worker}`,
                visibility: "workspace",
                data: workData(activity),
              },
            ];
          } else {
            const current = core.read(target).data;
            guards = [
              { ref: { id: target }, expected_revision: current.revision },
            ];
            ops = [
              {
                op: "update_record",
                ref: { id: target },
                data: {
                  ...current.data,
                  current_state: `Synthetic saved state ${save}`,
                },
              },
            ];
          }
          lastPayload = {
            request_id: `qualification-${config.worker}-${save}`,
            reason: "Retain synthetic qualification state",
            source_handles: [source.source_handle],
            guards,
            ops,
          };
          if (config.mode === "crash")
            writeFileSync(config.payload, JSON.stringify(lastPayload));
          const value = core.commit(lastPayload);
          completed = performance.now();
          return value;
        },
        { timeoutMs: 60_000 },
      );
      lastReceipt = receipt;
      if (receipt.created.work) target = receipt.created.work;
      report.receipts.push({
        request_id: receipt.request_id,
        transaction_id: receipt.transaction_id,
        snapshot_seq: receipt.snapshot_seq,
        created: receipt.created,
        new_revisions: receipt.new_revisions,
      });
      report.saves.push({
        queue_wait_ms: entered - queued,
        core_ms: completed - entered,
        total_ms: performance.now() - queued,
      });
      sample();
    } catch (error) {
      if (config.mode === "conflict" && error.code === "REVISION_CONFLICT") {
        report.conflict = {
          code: error.code,
          expected_revision: targetRow.revision,
        };
        break;
      }
      throw error;
    }
  }
  if (lastReceipt && config.mode !== "conflict") {
    const replay = await disk.withOperation(
      "mutate",
      () => core.commit(lastPayload),
      { timeoutMs: 60_000 },
    );
    report.replay_identical =
      JSON.stringify(replay) === JSON.stringify(lastReceipt);
    try {
      await disk.withOperation(
        "mutate",
        () =>
          core.commit({
            ...lastPayload,
            reason: "Different payload must be rejected",
          }),
        { timeoutMs: 60_000 },
      );
      throw new Error("Changed payload reused an existing request id");
    } catch (error) {
      if (error.code !== "IDEMPOTENCY_CONFLICT") throw error;
      report.changed_payload_code = error.code;
    }
  }
  report.target = target;
  report.elapsed_ms = performance.now() - started;
  report.coordination = coordination.describe();
  sample();
  await close();
  writeFileSync(config.report, JSON.stringify(report, null, 2));
  process.send?.({
    type: "done",
    worker: config.worker,
    saves: report.receipts.length,
  });
  completed = true;
  process.disconnect?.();
} catch (error) {
  report.error = {
    code: error.code ?? "UNEXPECTED",
    message: error.message,
    stack: error.stack,
  };
  report.elapsed_ms = performance.now() - started;
  sample();
  writeFileSync(config.report, JSON.stringify(report, null, 2));
  console.error(JSON.stringify(report.error));
  try {
    await close();
  } catch {
    /* Failed fixtures and OS lease files are preserved. */
  }
  process.exitCode = 1;
  completed = true;
  process.disconnect?.();
}

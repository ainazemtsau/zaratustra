import { readFileSync, writeFileSync } from "node:fs";
import { performance } from "node:perf_hooks";
import { Core } from "../../src/core/index.ts";
import { DiskStorage } from "../../src/storage/index.ts";
import { Coordination } from "../../src/storage/coordination.ts";
const config = JSON.parse(readFileSync(process.argv[2], "utf8")) as {
  project: string;
  home: string;
  identity: string;
  index: number;
  activity: string;
  target: string;
  report: string;
};
const started = performance.now();
const retry = async <T>(action: () => T): Promise<T> => {
  const deadline = Date.now() + 30000;
  for (;;) {
    try {
      return action();
    } catch (e) {
      if (
        (e as { code?: string }).code !== "STORE_BUSY" ||
        Date.now() >= deadline
      )
        throw e;
      await new Promise((r) => setTimeout(r, 10));
    }
  }
};
const waitFor = (type: string) =>
  new Promise<void>((resolve) => {
    const listener = (message: unknown) => {
      if ((message as { type?: string })?.type === type) {
        process.off("message", listener);
        resolve();
      }
    };
    process.on("message", listener);
  });
let done = false;
process.once("disconnect", () => {
  if (!done) process.exit(2);
});
let disk: DiskStorage | undefined, coordination: Coordination | undefined;
const report = {
  index: config.index,
  pid: process.pid,
  open_ms: 0,
  create_ms: 0,
  conflict_ms: 0,
  total_ms: 0,
  rss_peak_bytes: process.memoryUsage().rss,
  created: "",
  replay_identical: false,
  changed_payload_rejected: false,
  conflict: "",
  error: "",
};
try {
  coordination = await retry(
    () =>
      new Coordination(config.home, undefined, {
        expectedId: config.identity,
        create: false,
      }),
  );
  disk = await retry(
    () =>
      new DiskStorage(config.home, undefined, {
        coordination,
        projectRoot: config.project,
      }),
  );
  const storage = disk,
    core = new Core(storage, {
      ...storage.workspace,
      principal: "trusted-personal",
      session_id: "file-v2-" + config.index,
      runtime_id: coordination.runtimeId,
      processing_allowed: true,
      can_write: true,
    });
  report.open_ms = performance.now() - started;
  const start = waitFor("start");
  process.send?.({ type: "ready" });
  await start;
  const createBegan = performance.now();
  await storage.withOperation("mutate", () => {
    const source = core.capture(
      "Keep one independent synthetic Work",
      "rpc",
      null,
    );
    const request = {
      request_id: "worker-create-" + config.index,
      reason: "Preserve independent Work in shared file-primary memory",
      source_handles: [source.source_handle],
      guards: [],
      ops: [
        {
          op: "create_record",
          client_ref: "w",
          kind: "work",
          title: "Independent Work " + config.index,
          visibility: "workspace",
          data: {
            activity_id: { id: config.activity },
            parent_work_id: null,
            objective: "Retain independent Work " + config.index,
            acceptance: [
              {
                criterion_id: "saved",
                description: "Work is durable",
                verification: "Inspect record and receipt",
                required: true,
              },
            ],
            status: "draft",
            current_state: "Synthetic retained state",
            next_action: "Continue independently",
            steps: [],
            waits: [],
            context_refs: [],
            completion: null,
            plan_version: 1,
          },
        },
      ],
    };
    const receipt = core.commit(request);
    report.created = receipt.created.w;
    report.replay_identical =
      JSON.stringify(core.commit(request)) === JSON.stringify(receipt);
    try {
      core.commit({ ...request, reason: "Different intent under the same ID" });
    } catch (e) {
      report.changed_payload_rejected =
        (e as { code?: string }).code === "IDEMPOTENCY_CONFLICT";
    }
  });
  report.create_ms = performance.now() - createBegan;
  report.rss_peak_bytes = Math.max(
    report.rss_peak_bytes,
    process.memoryUsage().rss,
  );
  const conflict = waitFor("conflict");
  process.send?.({ type: "created" });
  await conflict;
  const conflictBegan = performance.now();
  try {
    await storage.withOperation("mutate", () => {
      const source = core.capture(
        "Change only the original shared version",
        "rpc",
        null,
      );
      const receipt = core.commit({
        request_id: "worker-conflict-" + config.index,
        reason: "Check one-version conflict fencing",
        source_handles: [source.source_handle],
        guards: [{ ref: { id: config.target }, expected_revision: 1 }],
        ops: [
          {
            op: "update_record",
            ref: { id: config.target },
            title: "Winner " + config.index,
            data: {
              entity_kind: "other",
              aliases: [],
              disambiguation: "Synthetic shared guarded target",
              status: "active",
            },
          },
        ],
      });
      if (receipt.committed) report.conflict = "committed";
    });
  } catch (e) {
    report.conflict = (e as { code?: string }).code ?? "unexpected";
    if (report.conflict === "unexpected")
      report.error = String(e).slice(0, 2000);
  }
  report.conflict_ms = performance.now() - conflictBegan;
  report.rss_peak_bytes = Math.max(
    report.rss_peak_bytes,
    process.memoryUsage().rss,
  );
  await storage.withOperation("maintenance", () => storage.closeConnection());
  storage.close();
  await retry(() => coordination!.close());
  disk = undefined;
  coordination = undefined;
  report.total_ms = performance.now() - started;
  writeFileSync(config.report, JSON.stringify(report));
  done = true;
  process.disconnect?.();
} catch (e) {
  report.error = e instanceof Error ? (e.stack ?? e.message) : String(e);
  report.total_ms = performance.now() - started;
  writeFileSync(config.report, JSON.stringify(report));
  console.error(report.error);
  process.exitCode = 1;
  done = true;
  try {
    disk?.close();
  } catch {}
  try {
    coordination?.close();
  } catch {}
  process.disconnect?.();
}

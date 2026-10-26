import assert from "node:assert/strict";
import { createHash } from "node:crypto";
import { spawn } from "node:child_process";
import {
  createWriteStream,
  mkdirSync,
  mkdtempSync,
  readFileSync,
  writeFileSync,
} from "node:fs";
import { tmpdir, totalmem, freemem } from "node:os";
import { dirname, join, resolve } from "node:path";
import { performance } from "node:perf_hooks";
import { parseArgs } from "node:util";
import {
  Core,
  ActivityData,
  WorkData,
  EntityData,
  refreshMemory,
} from "../src/core/index.ts";
import { DiskStorage } from "../src/storage/index.ts";

const { values } = parseArgs({
  options: {
    smoke: { type: "boolean", default: false },
    compiled: { type: "boolean", default: false },
    groups: { type: "string", default: "2,10" },
    growth: { type: "boolean", default: false },
    saves: { type: "string", default: "10" },
    out: { type: "string", default: "docs/concurrency-evidence/scale.json" },
    root: { type: "string" },
  },
});
const root = values.root
  ? resolve(values.root)
  : mkdtempSync(
      join(
        process.env.ZARATUSTRA_TEST_ROOT ?? tmpdir(),
        "zara-concurrent-qualification-",
      ),
    );
mkdirSync(root, { recursive: true });
const evidence = {
  runtime: {
    node: process.version,
    sqlite: null,
    platform: process.platform,
    architecture: process.arch,
    host_total_ram_bytes: totalmem(),
    host_free_ram_at_start_bytes: freemem(),
  },
  controller_backend: "source-tsx",
  controller_source_hashes: Object.fromEntries(
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
  fixture_root: root,
  model_calls: 0,
  groups: [],
  guarded_conflict: null,
  lost_reply_recovery: null,
  started_at: new Date().toISOString(),
};
function coreFor(disk, session) {
  return new Core(disk, {
    ...disk.workspace,
    principal: "trusted-personal",
    session_id: session,
    runtime_id: disk.coordination.runtimeId,
    can_write: true,
    processing_allowed: true,
  });
}
function workData(activity) {
  return {
    activity_id: { id: activity },
    parent_work_id: null,
    objective: "Synthetic fixed-growth objective",
    acceptance: [
      {
        criterion_id: "synthetic",
        description: "Retained synthetic state",
        verification: "Inspect committed state",
        required: true,
      },
    ],
    status: "draft",
    current_state: "Synthetic fixed-growth state",
    next_action: "Continue synthetic qualification",
    steps: [],
    waits: [],
    context_refs: [],
    completion: null,
    plan_version: 1,
  };
}
async function seed(home, growth) {
  const start = performance.now(),
    disk = new DiskStorage(home),
    core = coreFor(disk, "qualification-controller");
  const sizes = growth
    ? { activities: 20, works: 80, entities: 4900, revisions: 5 }
    : { activities: 2, works: 4, entities: 10, revisions: 1 };
  const rows = [],
    stamp = "2026-10-26T00:00:00.000Z";
  function add(id, kind, title, data) {
    ({ activity: ActivityData, work: WorkData, entity: EntityData })[
      kind
    ].parse(data);
    rows.push({
      id,
      kind,
      title,
      body: null,
      revision: sizes.revisions,
      created_at: stamp,
      updated_at: stamp,
      storage: "live",
      visibility: "workspace",
      data,
      concept_ids: [],
      origin_activity_id: null,
    });
  }
  for (let i = 0; i < sizes.activities; i++)
    add(`fixture-activity-${i}`, "activity", `Synthetic Activity ${i}`, {
      purpose: "Synthetic fixed-growth activity",
      status: "active",
    });
  for (let i = 0; i < sizes.works; i++)
    add(
      `fixture-work-${i}`,
      "work",
      `Synthetic Work ${i}`,
      workData(`fixture-activity-${i % sizes.activities}`),
    );
  for (let i = 0; i < sizes.entities; i++)
    add(`fixture-entity-${i}`, "entity", `Synthetic Entity ${i}`, {
      entity_kind: "other",
      aliases: [],
      disambiguation: `Synthetic fixed-growth entity ${i}`,
      status: "active",
    });
  await disk.withOperation(
    "mutate",
    () => {
      disk.exec("BEGIN IMMEDIATE");
      try {
        for (const row of rows) {
          disk.run(
            "INSERT INTO records(id,kind,activity_id,json) VALUES(?,?,?,?)",
            row.id,
            row.kind,
            row.data.activity_id?.id ?? null,
            JSON.stringify(row),
          );
          for (let revision = 1; revision <= sizes.revisions; revision++)
            disk.run(
              "INSERT INTO revisions(id,revision,json) VALUES(?,?,?)",
              row.id,
              revision,
              JSON.stringify({ ...row, revision }),
            );
        }
        refreshMemory(disk, true);
        disk.exec("COMMIT");
      } catch (error) {
        disk.exec("ROLLBACK");
        throw error;
      }
    },
    { timeoutMs: 60_000 },
  );
  const count = rows.length,
    history = count * sizes.revisions;
  const metadata = await disk.withOperation("read", () => ({
    records: disk.get("SELECT count(*) AS n FROM records").n,
    revisions: disk.get("SELECT count(*) AS n FROM revisions").n,
    sqlite: disk.get("SELECT sqlite_version() AS version").version,
  }));
  assert.equal(metadata.records, count);
  assert.equal(metadata.revisions, history);
  evidence.runtime.sqlite = metadata.sqlite;
  return {
    home,
    disk,
    core,
    seed: {
      ...sizes,
      records: count,
      historical_revisions: history,
      seed_ms: performance.now() - start,
    },
    rows,
  };
}
function digestHistory(disk) {
  return createHash("sha256")
    .update(
      JSON.stringify(
        disk.all(
          "SELECT id,revision,json FROM revisions WHERE id LIKE 'fixture-%' ORDER BY id,revision",
        ),
      ),
    )
    .digest("hex");
}
async function workers(f, count, saves, mode = "mixed", extra = {}) {
  const children = [],
    began = performance.now(),
    group = dirname(f.home);
  const start = join(group, "start");
  let finished = 0;
  let phase = "readiness";
  let rejectEarly;
  const earlyExit = new Promise((_, reject) => {
    rejectEarly = reject;
  });
  void earlyExit.catch(() => {});
  for (let i = 0; i < count; i++) {
    const worker = `${mode}-${i}`,
      configPath = join(group, `${worker}.config.json`),
      report = join(group, `${worker}.report.json`);
    const selected =
      mode === "mixed" ? (i % 2 === 0 ? "separate" : "shared") : mode;
    writeFileSync(
      configPath,
      JSON.stringify({
        home: f.home,
        identity: f.disk.coordination.identity,
        compiled: values.compiled,
        worker,
        saves,
        mode: selected,
        activity: "fixture-activity-0",
        start,
        report,
        ...extra,
      }),
    );
    const proc = spawn(
      process.execPath,
      [
        "--max-old-space-size=192",
        ...(values.compiled ? [] : ["--import", "tsx"]),
        resolve("scripts/concurrent-worker.mjs"),
        configPath,
      ],
      { cwd: resolve("."), stdio: ["ignore", "pipe", "pipe", "ipc"] },
    );
    proc.stdout.pipe(createWriteStream(join(group, `${worker}.stdout.log`)));
    proc.stderr.pipe(createWriteStream(join(group, `${worker}.stderr.log`)));
    let markReady, failReady;
    const ready = new Promise((yes, no) => {
      markReady = yes;
      failReady = no;
    });
    const entry = { proc, ready, exited: undefined, readiness: null };
    proc.on("message", (message) => {
      if (message.type === "ready") {
        entry.readiness = message;
        markReady();
      }
    });
    const exited = new Promise((yes, no) => {
      proc.once("error", (error) => {
        failReady(error);
        no(error);
      });
      proc.once("exit", (code, signal) => {
        failReady(
          new Error(
            `Worker ${worker} exited before readiness: ${code}/${signal}; ${report}`,
          ),
        );
        if (phase === "readiness")
          rejectEarly(
            new Error(
              `Worker ${worker} exited during startup: ${code}/${signal}; ${report}`,
            ),
          );
        finished++;
        if (finished % Math.max(1, Math.floor(count / 10)) === 0)
          console.log(
            JSON.stringify({
              progress: "workers_finished",
              workers: count,
              finished,
              elapsed_ms: Math.round(performance.now() - began),
            }),
          );
        yes({ worker, code, signal, report, selected });
      });
    });
    entry.exited = exited;
    void exited.catch(() => {});
    children.push(entry);
  }
  let timer;
  try {
    await Promise.race([
      Promise.all(children.map((child) => child.ready)),
      earlyExit,
      new Promise((_, reject) => {
        timer = setTimeout(
          () =>
            reject(
              new Error(
                `Readiness timed out for ${count} workers; fixtures retained at ${group}`,
              ),
            ),
          180_000,
        );
      }),
    ]);
    clearTimeout(timer);
    const readyMs = performance.now() - began;
    console.log(
      JSON.stringify({
        progress: "all_workers_ready",
        workers: count,
        ready_ms: Math.round(readyMs),
      }),
    );
    phase = "execution";
    writeFileSync(start, "start");
    const results = await Promise.race([
      Promise.all(children.map((child) => child.exited)),
      new Promise((_, reject) => {
        timer = setTimeout(
          () =>
            reject(
              new Error(
                `Execution timed out for ${count} workers; fixtures retained at ${group}`,
              ),
            ),
          240_000,
        );
      }),
    ]);
    return {
      ready_ms: readyMs,
      execute_ms: performance.now() - began - readyMs,
      results: results.map((result) => ({
        ...result,
        data:
          result.code === 73
            ? null
            : JSON.parse(readFileSync(result.report, "utf8")),
      })),
    };
  } catch (error) {
    error.qualification = {
      phase,
      workers: count,
      ready_workers: children.filter((child) => child.readiness).length,
      elapsed_ms: performance.now() - began,
      startup_ms: quantiles(
        children
          .filter((child) => child.readiness)
          .map((child) => child.readiness.startup_ms),
      ),
      fixture: group,
    };
    throw error;
  } finally {
    clearTimeout(timer);
    for (const child of children)
      if (child.proc.exitCode === null && child.proc.signalCode === null)
        child.proc.kill();
    await Promise.allSettled(children.map((child) => child.exited));
  }
}
async function closeFixture(disk, primaryError) {
  try {
    await disk.withOperation("maintenance", () => disk.closeConnection(), {
      timeoutMs: 30_000,
    });
    disk.close();
  } catch (cleanupError) {
    if (!primaryError) throw cleanupError;
    primaryError.cleanup_error = {
      code: cleanupError.code ?? "UNEXPECTED",
      message: cleanupError.message,
    };
  }
}
function quantiles(values) {
  const sorted = [...values].sort((a, b) => a - b);
  const pick = (p) =>
    sorted[Math.min(sorted.length - 1, Math.floor(sorted.length * p))] ?? 0;
  return {
    n: sorted.length,
    min: sorted[0] ?? 0,
    p50: pick(0.5),
    p95: pick(0.95),
    p99: pick(0.99),
    max: sorted.at(-1) ?? 0,
  };
}
async function runGroup(count, saves, growth, mode = "mixed") {
  const group = join(root, `group-${count}-${mode}`);
  mkdirSync(group);
  console.log(
    JSON.stringify({ progress: "seed_start", workers: count, growth }),
  );
  const f = await seed(join(group, "home"), growth);
  let primaryError;
  try {
    const historyBefore = await f.disk.withOperation("read", () =>
      digestHistory(f.disk),
    );
    const first = await f.disk.withOperation(
      "read",
      () => f.core.browse("work", undefined, 2).data,
    );
    const measured = await workers(f, count, saves, mode);
    for (const worker of measured.results) {
      assert.equal(worker.code, 0, JSON.stringify(worker));
      assert.equal(worker.data.receipts.length, saves);
      assert.equal(worker.data.replay_identical, true);
      assert.equal(worker.data.changed_payload_code, "IDEMPOTENCY_CONFLICT");
    }
    const reports = measured.results.map((worker) => worker.data),
      receipts = reports.flatMap((report) => report.receipts);
    const sourceHashes = reports[0].source_hashes;
    assert.deepEqual(
      sourceHashes,
      evidence.controller_source_hashes,
      "Controller and workers loaded different source snapshots",
    );
    const backendHashes = reports[0].backend_hashes;
    for (const report of reports)
      assert.deepEqual(
        report.backend_hashes,
        backendHashes,
        "Compiled backend changed during qualification",
      );
    for (const report of reports)
      assert.deepEqual(
        report.source_hashes,
        sourceHashes,
        "Backend source changed during qualification",
      );
    const separate = measured.results.filter(
      (worker) => worker.selected === "separate",
    ).length;
    const expected = {
      receipts: count * saves,
      changes: count * saves,
      records: f.seed.records + count + separate,
      revisions: f.seed.historical_revisions + count * saves + separate,
    };
    const actual = await f.disk.withOperation("read", () => ({
      receipts: f.disk.get("SELECT count(*) AS n FROM receipts").n,
      changes: f.disk.get("SELECT count(*) AS n FROM changes").n,
      records: f.disk.get("SELECT count(*) AS n FROM records").n,
      revisions: f.disk.get("SELECT count(*) AS n FROM revisions").n,
    }));
    assert.deepEqual(actual, expected);
    assert.equal(
      new Set(receipts.map((receipt) => receipt.request_id)).size,
      count * saves,
    );
    assert.equal(
      new Set(receipts.map((receipt) => receipt.transaction_id)).size,
      count * saves,
    );
    assert.deepEqual(
      receipts.map((receipt) => receipt.snapshot_seq).sort((a, b) => a - b),
      Array.from({ length: count * saves }, (_, index) => index + 1),
    );
    const savedIds = receipts.flatMap((receipt) =>
      Object.values(receipt.created),
    );
    assert.equal(new Set(savedIds).size, count + separate);
    assert.deepEqual(
      await f.disk.withOperation("read", () =>
        f.disk
          .all("SELECT request_id FROM receipts ORDER BY request_id")
          .map((row) => row.request_id),
      ),
      receipts.map((receipt) => receipt.request_id).sort(),
    );
    assert.equal(
      await f.disk.withOperation("read", () => digestHistory(f.disk)),
      historyBefore,
    );
    for (const report of reports) {
      const work = await f.disk.withOperation(
        "read",
        () => f.core.read(report.target).data,
      );
      assert.equal(work.revision, saves);
      const history = await f.disk.withOperation("read", () =>
        f.disk.all(
          "SELECT revision,json FROM revisions WHERE id=? ORDER BY revision",
          report.target,
        ),
      );
      assert.deepEqual(
        history.map((row) => row.revision),
        Array.from({ length: saves }, (_, index) => index + 1),
      );
      for (let index = 0; index < saves; index++) {
        const stored = JSON.parse(history[index].json);
        assert.equal(
          report.receipts[index].new_revisions[report.target],
          index + 1,
        );
        assert.equal(stored.id, report.target);
        assert.equal(stored.revision, index + 1);
        assert.equal(
          stored.data.current_state,
          index === 0
            ? "Synthetic initial state"
            : `Synthetic saved state ${index}`,
        );
      }
      assert.equal(
        work.data.current_state,
        saves === 1
          ? "Synthetic initial state"
          : `Synthetic saved state ${saves - 1}`,
      );
    }
    const cursorIds = first.cards.map((card) => card.id);
    let next = first.next_cursor;
    while (next) {
      const page = await f.disk.withOperation(
        "read",
        () => f.core.browse("work", undefined, 2, next).data,
      );
      cursorIds.push(...page.cards.map((card) => card.id));
      next = page.next_cursor;
    }
    assert.deepEqual(
      [...cursorIds].sort(),
      f.rows
        .filter((row) => row.kind === "work")
        .map((row) => row.id)
        .sort(),
    );
    const phases = reports.flatMap((report) => report.saves);
    const result = {
      workers: count,
      saves_per_worker: saves,
      separate_activity_workers: separate,
      shared_activity_workers: count - separate,
      growth,
      seed: f.seed,
      ready_ms: measured.ready_ms,
      execute_ms: measured.execute_ms,
      actual,
      expected,
      queue_wait_ms: quantiles(phases.map((phase) => phase.queue_wait_ms)),
      core_phase_ms: quantiles(phases.map((phase) => phase.core_ms)),
      command_ms: quantiles(phases.map((phase) => phase.total_ms)),
      startup_ms: quantiles(reports.map((report) => report.startup_ms)),
      backend: values.compiled ? "compiled-dist" : "source-tsx",
      source_hashes: sourceHashes,
      backend_hashes: backendHashes,
      coordination_open_ms: quantiles(
        reports.map((report) => report.coordination_open_ms),
      ),
      disk_open_ms: quantiles(reports.map((report) => report.disk_open_ms)),
      worker_rss_peak_bytes: quantiles(
        reports.map((report) => report.rss_peak_bytes),
      ),
      sum_worker_sampled_peak_rss_bytes: reports.reduce(
        (sum, report) => sum + report.rss_peak_bytes,
        0,
      ),
      seed_history_digest: historyBefore,
      initial_cursor_rows: cursorIds.length,
      cursor_survived_unrelated_writes: true,
      receipts_unique: true,
      ids_unique: true,
      aggregate_counts_match: true,
      generated_histories_match_receipts: true,
      all_replays_identical: true,
      changed_payload_rejected: true,
      fixture: group,
      model_calls: 0,
    };
    console.log(
      JSON.stringify({
        progress: "group_passed",
        workers: count,
        receipts: actual.receipts,
        execute_ms: Math.round(result.execute_ms),
        queue_p95_ms: Math.round(result.queue_wait_ms.p95),
      }),
    );
    return result;
  } catch (error) {
    primaryError = error;
    evidence.failed_group = {
      workers: count,
      saves_per_worker: saves,
      growth,
      seed: f.seed,
      fixture: group,
      details: error.qualification,
    };
    throw error;
  } finally {
    await closeFixture(f.disk, primaryError);
  }
}
async function conflict() {
  const group = join(root, "guarded-conflict");
  mkdirSync(group);
  const f = await seed(join(group, "home"), false);
  let primaryError;
  try {
    const measured = await workers(f, 2, 1, "conflict", {
      target: "fixture-work-0",
    });
    measured.results.forEach((worker) =>
      assert.equal(worker.code, 0, JSON.stringify(worker)),
    );
    const wins = measured.results.filter(
        (worker) => worker.data.receipts.length === 1,
      ),
      conflicts = measured.results.filter(
        (worker) => worker.data.conflict?.code === "REVISION_CONFLICT",
      );
    assert.equal(wins.length, 1);
    assert.equal(conflicts.length, 1);
    const before = await f.disk.withOperation(
      "read",
      () => f.core.read("fixture-work-0").data,
    );
    assert.equal(before.revision, 2);
    const recovered = await f.disk.withOperation("mutate", () => {
      const source = f.core.capture(
        "Synthetic guarded conflict recovery after rereading committed state.",
        "rpc",
        "synthetic-qualification-controller",
      );
      return f.core.commit({
        request_id: "qualification-recovery",
        reason: "Recover with a fresh explicit revision guard",
        source_handles: [source.source_handle],
        guards: [
          { ref: { id: before.id }, expected_revision: before.revision },
        ],
        ops: [
          {
            op: "update_record",
            ref: { id: before.id },
            data: {
              ...before.data,
              current_state: "Synthetic conflict recovered",
            },
          },
        ],
      });
    });
    assert.equal(
      (await f.disk.withOperation("read", () => f.core.read(before.id).data))
        .revision,
      3,
    );
    assert.equal(
      (
        await f.disk.withOperation("read", () =>
          f.disk.get("SELECT count(*) AS n FROM receipts"),
        )
      ).n,
      2,
    );
    return {
      competing_processes: 2,
      successful_original_commits: 1,
      revision_conflicts: 1,
      recovered_revision: 3,
      recovery_request_id: recovered.request_id,
      fixture: group,
      model_calls: 0,
    };
  } catch (error) {
    primaryError = error;
    throw error;
  } finally {
    await closeFixture(f.disk, primaryError);
  }
}
async function lostReply() {
  const group = join(root, "lost-reply");
  mkdirSync(group);
  const f = await seed(join(group, "home"), false),
    payload = join(group, "payload.json");
  let primaryError;
  try {
    const measured = await workers(f, 1, 1, "crash", { payload });
    assert.equal(measured.results[0].code, 73);
    const request = JSON.parse(readFileSync(payload, "utf8"));
    const existing = await f.disk.withOperation("read", () =>
      JSON.parse(
        f.disk.get(
          "SELECT json FROM receipts WHERE request_id=?",
          request.request_id,
        ).json,
      ),
    );
    const replay = await f.disk.withOperation("mutate", () =>
      f.core.commit(request),
    );
    assert.deepEqual(replay, existing);
    assert.equal(
      (
        await f.disk.withOperation("read", () =>
          f.disk.get("SELECT count(*) AS n FROM receipts"),
        )
      ).n,
      1,
    );
    return {
      crashed_after: "data_commit_before_reply",
      worker_exit: 73,
      recovered_existing_receipt: true,
      no_duplicate_receipt: true,
      request_id: request.request_id,
      fixture: group,
      model_calls: 0,
    };
  } catch (error) {
    primaryError = error;
    throw error;
  } finally {
    await closeFixture(f.disk, primaryError);
  }
}
try {
  const counts = values.smoke ? [2] : values.groups.split(",").map(Number);
  const saves = values.smoke ? 3 : Number(values.saves);
  if (
    !counts.every((n) => Number.isSafeInteger(n) && n > 0 && n <= 100) ||
    !Number.isSafeInteger(saves) ||
    saves < 1 ||
    saves > 100
  )
    throw new Error("Qualification requires 1..100 workers and 1..100 saves");
  if (values.smoke) {
    evidence.groups.push(await runGroup(2, saves, false, "separate"));
    evidence.groups.push(await runGroup(2, saves, false, "shared"));
  } else
    for (const count of counts)
      evidence.groups.push(await runGroup(count, saves, values.growth));
  evidence.guarded_conflict = await conflict();
  evidence.lost_reply_recovery = await lostReply();
  evidence.passed = true;
} catch (error) {
  evidence.passed = false;
  evidence.failure = {
    code: error.code ?? "UNEXPECTED",
    message: error.message,
    stack: error.stack,
    cleanup_error: error.cleanup_error,
  };
  process.exitCode = 1;
} finally {
  evidence.finished_at = new Date().toISOString();
  const output = resolve(values.out);
  mkdirSync(dirname(output), { recursive: true });
  writeFileSync(output, JSON.stringify(evidence, null, 2));
  console.log(
    JSON.stringify({
      progress: "qualification_complete",
      passed: evidence.passed,
      output,
      fixture_root: root,
      failure: evidence.failure?.message,
    }),
  );
}

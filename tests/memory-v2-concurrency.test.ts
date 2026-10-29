import test from "node:test";
import assert from "node:assert/strict";
import { spawn, type ChildProcess } from "node:child_process";
import { mkdtempSync, readFileSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join, resolve } from "node:path";
import { performance } from "node:perf_hooks";
import { Core } from "../src/core/index.ts";
import { DiskStorage } from "../src/storage/index.ts";

type Report = {
  index: number;
  pid: number;
  open_ms: number;
  create_ms: number;
  conflict_ms: number;
  total_ms: number;
  rss_peak_bytes: number;
  created: string;
  replay_identical: boolean;
  changed_payload_rejected: boolean;
  conflict: string;
  error: string;
};
for (const count of [2, 10])
  test(
    `file-primary memory retains independent Work with ${count} actual processes and fences shared-version conflicts`,
    { timeout: 240000 },
    async (t) => {
      const project = mkdtempSync(
        join(
          process.env.ZARATUSTRA_TEST_ROOT ?? tmpdir(),
          `zara-memory-v2-${count}-`,
        ),
      );
      const home = join(project, ".local/memory"),
        started = performance.now();
      const seed = new DiskStorage(home, undefined, {
        projectRoot: project,
        corpus: "create",
      });
      const core = new Core(seed, {
        ...seed.workspace,
        principal: "trusted-personal",
        session_id: "seed",
        runtime_id: seed.coordination.runtimeId,
        processing_allowed: true,
        can_write: true,
      });
      const source = core.capture(
        "Create two shared Activities for independent Work",
        "rpc",
        null,
      );
      const base = core.commit({
        request_id: "seed",
        reason: "Seed the bounded synthetic parallel profile",
        source_handles: [source.source_handle],
        guards: [],
        ops: [
          ...[0, 1].map((i) => ({
            op: "create_record",
            client_ref: "a" + i,
            kind: "activity",
            title: "Shared Activity " + i,
            visibility: "workspace",
            data: { purpose: "Independent synthetic work", status: "active" },
          })),
          {
            op: "create_record",
            client_ref: "target",
            kind: "entity",
            title: "Original guarded target",
            visibility: "workspace",
            data: {
              entity_kind: "other",
              aliases: [],
              disambiguation: "Synthetic shared guarded target",
              status: "active",
            },
          },
        ],
      });
      const identity = seed.coordination.identity;
      seed.close();
      const children: ChildProcess[] = [];
      const paths: string[] = [];
      t.after(() => {
        for (const child of children)
          if (child.exitCode === null && child.signalCode === null)
            child.kill();
      });
      const entries = Array.from({ length: count }, (_, index) => {
        const config = join(project, `worker-${index}.config.json`),
          report = join(project, `worker-${index}.report.json`);
        paths.push(report);
        writeFileSync(
          config,
          JSON.stringify({
            project,
            home,
            identity,
            index,
            activity: base.created["a" + (index % 2)],
            target: base.created.target,
            report,
          }),
        );
        const child = spawn(
          process.execPath,
          [
            "--max-old-space-size=192",
            "--import",
            "tsx",
            resolve("tests/fixtures/v2-concurrent-worker.ts"),
            config,
          ],
          { cwd: resolve("."), stdio: ["ignore", "pipe", "pipe", "ipc"] },
        );
        children.push(child);
        let output = "";
        child.stdout!.on("data", (chunk) => {
          if (output.length < 8000) output += String(chunk);
        });
        child.stderr!.on("data", (chunk) => {
          if (output.length < 8000) output += String(chunk);
        });
        const phase = (type: string) =>
          new Promise<void>((yes, no) => {
            child.on("message", (message) => {
              if ((message as { type?: string })?.type === type) yes();
            });
            child.once("error", no);
            child.once("exit", (code) =>
              no(
                new Error(
                  `Worker ${index} exited before ${type}: ${code}; ${output}`,
                ),
              ),
            );
          });
        const ready = phase("ready"),
          created = phase("created");
        const exited = new Promise<void>((yes, no) => {
          child.once("error", no);
          child.once("exit", (code) =>
            code === 0
              ? yes()
              : no(new Error(`Worker ${index} failed: ${code}; ${output}`)),
          );
        });
        void ready.catch(() => {});
        void created.catch(() => {});
        void exited.catch(() => {});
        return { child, ready, created, exited };
      });
      await Promise.all(entries.map((e) => e.ready));
      const readyMs = performance.now() - started;
      entries.forEach((e) => e.child.send({ type: "start" }));
      await Promise.all(entries.map((e) => e.created));
      entries.forEach((e) => e.child.send({ type: "conflict" }));
      await Promise.all(entries.map((e) => e.exited));
      const reports = paths.map(
        (path) => JSON.parse(readFileSync(path, "utf8")) as Report,
      );
      for (const r of reports) {
        assert.equal(r.error, "");
        assert.equal(r.replay_identical, true);
        assert.equal(r.changed_payload_rejected, true);
        assert.ok(r.created);
      }
      assert.equal(new Set(reports.map((r) => r.pid)).size, count);
      assert.equal(new Set(reports.map((r) => r.created)).size, count);
      assert.equal(reports.filter((r) => r.conflict === "committed").length, 1);
      assert.equal(
        reports.filter((r) => r.conflict === "REVISION_CONFLICT").length,
        count - 1,
      );
      const checked = new DiskStorage(home, undefined, {
        projectRoot: project,
      });
      try {
        const counts = {
          records: checked.get<{ n: number }>("SELECT count(*) n FROM records")!
            .n,
          revisions: checked.get<{ n: number }>(
            "SELECT count(*) n FROM revisions",
          )!.n,
          receipts: checked.get<{ n: number }>(
            "SELECT count(*) n FROM receipts",
          )!.n,
          changes: checked.get<{ n: number }>("SELECT count(*) n FROM changes")!
            .n,
        };
        assert.deepEqual(counts, {
          records: count + 3,
          revisions: count + 4,
          receipts: count + 2,
          changes: count + 2,
        });
        const groups = checked.all<{ activity_id: string; n: number }>(
          "SELECT activity_id,count(*) n FROM records WHERE kind='work' GROUP BY activity_id ORDER BY activity_id",
        );
        assert.equal(groups.length, 2);
        assert.ok(groups.every((g) => g.n === count / 2));
        const evidence = {
          processes: count,
          model_calls: 0,
          ready_ms: readyMs,
          total_ms: performance.now() - started,
          counts,
          groups,
          workers: reports,
        };
        writeFileSync(
          join(project, "concurrency-evidence.json"),
          JSON.stringify(evidence),
        );
        t.diagnostic(
          JSON.stringify({
            fixture: project,
            processes: count,
            total_ms: Math.round(evidence.total_ms),
            ready_ms: Math.round(readyMs),
            max_worker_rss_bytes: Math.max(
              ...reports.map((r) => r.rss_peak_bytes),
            ),
            max_create_ms: Math.round(
              Math.max(...reports.map((r) => r.create_ms)),
            ),
            max_conflict_ms: Math.round(
              Math.max(...reports.map((r) => r.conflict_ms)),
            ),
            counts,
          }),
        );
      } finally {
        checked.close();
      }
    },
  );

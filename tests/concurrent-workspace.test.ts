import test from "node:test";
import assert from "node:assert/strict";
import { spawn } from "node:child_process";
import { mkdtempSync, readFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join, resolve } from "node:path";

test(
  "real Core processes keep independent Work writes, replay identity, guard conflicts and lost-reply recovery correct",
  { timeout: 120_000 },
  async () => {
    const root = mkdtempSync(
      join(
        process.env.ZARATUSTRA_TEST_ROOT ?? tmpdir(),
        "zara-concurrent-test-",
      ),
    );
    const output = join(root, "evidence.json");
    const child = spawn(
      process.execPath,
      [
        "--import",
        "tsx",
        resolve("scripts/concurrent-scale.mjs"),
        "--smoke",
        "--out",
        output,
        "--root",
        root,
      ],
      { cwd: resolve("."), stdio: ["ignore", "pipe", "pipe"] },
    );
    let logs = "";
    child.stdout.on("data", (chunk) => {
      logs += String(chunk);
    });
    child.stderr.on("data", (chunk) => {
      logs += String(chunk);
    });
    const timer = setTimeout(() => child.kill(), 115_000);
    const status = await new Promise<number | null>((done, reject) => {
      child.once("error", reject);
      child.once("exit", done);
    });
    clearTimeout(timer);
    assert.equal(status, 0, logs);
    const evidence = JSON.parse(readFileSync(output, "utf8"));
    assert.equal(evidence.passed, true, JSON.stringify(evidence.failure));
    assert.equal(evidence.model_calls, 0);
    assert.equal(evidence.groups.length, 2);
    for (const group of evidence.groups) {
      assert.equal(group.actual.receipts, 6);
      assert.deepEqual(group.actual, group.expected);
      assert.equal(group.cursor_survived_unrelated_writes, true);
      assert.equal(group.all_replays_identical, true);
      assert.equal(group.changed_payload_rejected, true);
      assert.equal(group.generated_histories_match_receipts, true);
    }
    assert.equal(evidence.guarded_conflict.revision_conflicts, 1);
    assert.equal(evidence.guarded_conflict.recovered_revision, 3);
    assert.equal(evidence.lost_reply_recovery.no_duplicate_receipt, true);
  },
);

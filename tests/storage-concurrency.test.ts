import test from "node:test";
import assert from "node:assert/strict";
import { DatabaseSync } from "node:sqlite";
import { mkdtempSync, readFileSync, writeFileSync, existsSync } from "node:fs";
import { join } from "node:path";
import { tmpdir } from "node:os";
import { execFileSync } from "node:child_process";
import { DiskStorage } from "../src/storage/index.ts";
import { Core } from "../src/core/index.ts";
function fixture() {
  const home = join(mkdtempSync(join(tmpdir(), "zara-storage9-")), "home");
  const disk = new DiskStorage(home);
  const core = new Core(disk, {
    ...disk.workspace,
    principal: "trusted-personal",
    session_id: "synthetic",
    runtime_id: "synthetic",
    can_write: true,
    processing_allowed: true,
  });
  return { home, disk, core };
}
test("storage: busy close remains retryable and finally releases runtime OS lease", () => {
  const f = fixture();
  const rival = new DatabaseSync(f.disk.coordination.path);
  rival.exec("BEGIN IMMEDIATE");
  assert.throws(() => f.disk.close(), { code: "STORE_BUSY" });
  assert.equal(f.disk.connectionClosed, false);
  rival.exec("ROLLBACK");
  rival.close();
  f.disk.close();
  assert.equal(f.disk.connectionClosed, true);
  const probe = new DatabaseSync(
    join(f.home, "runtimes", f.disk.coordination.runtimeId + ".sqlite"),
  );
  assert.doesNotThrow(() => probe.exec("BEGIN IMMEDIATE; ROLLBACK"));
  probe.close();
});
test("storage: unsupported runtime refuses before creating personal storage", () => {
  const home = join(mkdtempSync(join(tmpdir(), "zara-runtime9-")), "unopened");
  const source = `Object.defineProperty(process.versions,'node',{value:'22.19.0'}); const {DiskStorage}=await import('./src/storage/index.ts'); try{new DiskStorage(${JSON.stringify(home)});process.exitCode=1}catch(e){console.log(e.code)}`;
  const output = execFileSync(
    process.execPath,
    ["--import", "tsx", "--input-type=module", "-e", source],
    { cwd: process.cwd(), encoding: "utf8" },
  );
  assert.match(output, /RUNTIME_UNSUPPORTED/);
  assert.equal(existsSync(home), false);
});
test("storage: next operation revalidates generation after cached same-phase reads", async () => {
  const f = fixture();
  try {
    await f.disk.withOperation("read", () => {
      f.disk.get("SELECT 1");
      f.disk.get("SELECT 2");
    });
    const path = join(f.home, "active.json"),
      before = readFileSync(path, "utf8");
    const control = JSON.parse(before);
    control.epoch = "synthetic-replaced-epoch";
    writeFileSync(path, JSON.stringify(control));
    assert.throws(() => f.core.map(), {
      code: "RESTORE_RECONCILIATION_REQUIRED",
    });
    writeFileSync(path, before);
    assert.equal(f.core.map().ok, true);
  } finally {
    f.disk.close();
  }
});
test("storage: failed commit keeps its prepared intent discoverable on the first following read", () => {
  const f = fixture();
  try {
    const source = f.core.capture(
      "Synthetic invalid batch, retain failed intention.",
      "rpc",
      "synthetic",
    );
    const op = {
      op: "create_record",
      client_ref: "duplicate",
      kind: "activity",
      title: "Synthetic",
      visibility: "workspace",
      data: { purpose: "test", status: "active" },
    };
    assert.throws(
      () =>
        f.core.commit({
          request_id: "failed-durable-intent",
          reason: "mechanical",
          source_handles: [source.source_handle],
          guards: [],
          ops: [op, op],
        }),
      { code: "VALIDATION_ERROR" },
    );
    assert.match(
      JSON.stringify(f.core.browse("operations")),
      /failed-durable-intent/,
    );
    assert.equal(
      f.disk.get<{ n: number }>("SELECT count(*) AS n FROM records")!.n,
      0,
    );
  } finally {
    f.disk.close();
  }
});

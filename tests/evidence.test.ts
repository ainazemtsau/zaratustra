import test from "node:test";
import assert from "node:assert/strict";
import {
  mkdtempSync,
  writeFileSync,
  readFileSync,
  openSync,
  closeSync,
  existsSync,
} from "node:fs";
import { tmpdir } from "node:os";
import { join, resolve } from "node:path";
import { execFileSync } from "node:child_process";
import { createHash } from "node:crypto";

test("developer evidence export uses completed sealed inputs and rejects its own live stdout or changed sources", () => {
  const root = mkdtempSync(
    join(process.env.ZARATUSTRA_TEST_ROOT ?? tmpdir(), "zara-evidence-"),
  );
  const hash = (b: Uint8Array) => createHash("sha256").update(b).digest("hex");
  const sealed = join(root, "sealed.json"),
    log = join(root, "export.log");
  const seal = (paths: string[]) =>
    writeFileSync(
      sealed,
      JSON.stringify({
        root,
        entries: paths.map((path) => {
          const b = readFileSync(join(root, path));
          return { path, bytes: b.length, sha256: hash(b) };
        }),
      }),
    );
  const run = (out: string) => {
    const fd = openSync(log, "w");
    try {
      execFileSync(
        process.execPath,
        [resolve("scripts/export-evidence.mjs"), sealed, join(root, out), log],
        { stdio: ["ignore", fd, "pipe"] },
      );
    } finally {
      closeSync(fd);
    }
  };
  writeFileSync(join(root, "completed.log"), "Completed output.\r\n");
  seal(["completed.log"]);
  run("good");
  const manifest = JSON.parse(
    readFileSync(join(root, "good/manifest.json"), "utf8"),
  );
  assert.equal(manifest.entries.length, 1);
  const e = manifest.entries[0];
  assert.equal(
    e.original_sha256,
    hash(readFileSync(join(root, "completed.log"))),
  );
  assert.equal(
    e.derivative_sha256,
    hash(readFileSync(join(root, "good", e.derivative_path))),
  );
  assert.equal(
    readFileSync(join(root, "good/completed.log"), "utf8"),
    "Completed output.\n",
  );
  assert.equal(existsSync(join(root, "good/export.log")), false);
  // Even an empty snapshot of our redirected stdout is refused, rather than
  // mistaken for a finished immutable log as in the historical LOW finding.
  writeFileSync(log, "");
  seal(["export.log"]);
  assert.throws(() => run("self"), /Current exporter stdout/);
  assert.equal(existsSync(join(root, "self")), false);
  seal(["completed.log"]);
  writeFileSync(join(root, "completed.log"), "Changed after sealing.");
  assert.throws(() => run("changed"), /Sealed source/);
  assert.equal(existsSync(join(root, "changed")), false);
});

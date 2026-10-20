import test from "node:test";
import assert from "node:assert/strict";
import {
  mkdtempSync,
  mkdirSync,
  writeFileSync,
  readFileSync,
  openSync,
  closeSync,
  existsSync,
  linkSync,
  symlinkSync,
  statSync,
} from "node:fs";
import { tmpdir } from "node:os";
import { join, resolve, basename } from "node:path";
import { spawnSync } from "node:child_process";
import { createHash } from "node:crypto";

const hash = (b: Uint8Array) => createHash("sha256").update(b).digest("hex");
function fixture() {
  const root = mkdtempSync(
    join(process.env.ZARATUSTRA_TEST_ROOT ?? tmpdir(), "zara-evidence-"),
  );
  const sealed = join(root, "sealed.json"),
    log = join(root, "Current-Stdout.log");
  writeFileSync(log, "");
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
  const run = (out: string, stdout = log, preload: string[] = []) => {
    const fd = openSync(log, "w");
    try {
      return spawnSync(
        process.execPath,
        [
          ...preload,
          resolve("scripts/export-evidence.mjs"),
          sealed,
          join(root, out),
          stdout,
        ],
        { stdio: ["ignore", fd, "pipe"], encoding: "utf8" },
      );
    } finally {
      closeSync(fd);
    }
  };
  const refuse = (
    out: string,
    reason: RegExp,
    stdout = log,
    preload: string[] = [],
  ) => {
    const result = run(out, stdout, preload);
    assert.equal(result.status, 1, result.stderr);
    assert.match(result.stderr, reason);
    assert.equal(existsSync(join(root, out)), false);
    assert.equal(existsSync(join(root, out, "manifest.json")), false);
    assert.equal(readFileSync(log).length, 0);
  };
  return { root, log, seal, run, refuse };
}

test("developer evidence export preserves completed sealed inputs and refuses changes before or during processing", () => {
  const { root, seal, run, refuse } = fixture();
  const completed = join(root, "completed.log");
  writeFileSync(completed, "Completed output.\r\n");
  seal(["completed.log"]);
  const result = run("good");
  assert.equal(result.status, 0, result.stderr);
  const manifest = JSON.parse(
    readFileSync(join(root, "good/manifest.json"), "utf8"),
  );
  assert.equal(manifest.entries.length, 1);
  const e = manifest.entries[0];
  assert.equal(e.original_bytes, readFileSync(completed).length);
  assert.equal(e.original_sha256, hash(readFileSync(completed)));
  const derivative = readFileSync(join(root, "good", e.derivative_path));
  assert.equal(e.derivative_bytes, derivative.length);
  assert.equal(e.derivative_sha256, hash(derivative));
  assert.equal(derivative.toString(), "Completed output.\n");
  seal(["completed.log"]);
  writeFileSync(completed, "Changed after sealing.");
  refuse("changed-length", /Sealed source length changed/);
  writeFileSync(completed, "X".repeat(e.original_bytes));
  refuse("changed-digest", /Sealed source digest changed/);

  // Test-only preload mutates the actual file just after its initial read. The
  // exporter must validate again before creating any publication directory.
  seal(["completed.log"]);
  const preload = join(root, "mutate.cjs");
  writeFileSync(
    preload,
    `const fs = require('node:fs');
const original = fs.readFileSync; let first = true;
fs.readFileSync = function(path, ...args) {
  const bytes = original(path, ...args);
  if (String(path) === ${JSON.stringify(completed)} && first) {
    first = false; fs.writeFileSync(path, Buffer.from('Y'.repeat(bytes.length)));
  }
  return bytes;
};
require('node:module').syncBuiltinESMExports();
`,
  );
  refuse("changed-after-read", /Source changed during export/, undefined, [
    "--require",
    preload,
  ]);
});

test("developer evidence export rejects its redirected stdout through filesystem aliases", async (t) => {
  const cases: [string, (root: string, log: string) => string][] = [
    ["same spelling", (_root, log) => log],
    [
      "normalized separators and components",
      (root, log) => {
        mkdirSync(join(root, "scratch"));
        return root.replaceAll("\\", "/") + "/./scratch/../" + basename(log);
      },
    ],
    [
      "hard link",
      (root, log) => {
        const alias = join(root, "hardlink.log");
        linkSync(log, alias);
        return alias;
      },
    ],
  ];
  if (process.platform === "win32")
    cases.push(
      [
        "drive letter case",
        (_root, log) => log[0].toLowerCase() + log.slice(1),
      ],
      ["path case", (_root, log) => log.toUpperCase()],
      [
        "junction",
        (root, log) => {
          const alias = join(root, "junction");
          symlinkSync(root, alias, "junction");
          return join(alias, basename(log));
        },
      ],
    );
  for (const [name, alias] of cases)
    await t.test(name, () => {
      const f = fixture();
      const stdout = alias(f.root, f.log);
      f.seal([basename(f.log)]);
      f.refuse(
        "rejected",
        /Current exporter stdout cannot be an input/,
        stdout,
      );
    });
  await t.test("file symlink when permitted", (t) => {
    const f = fixture(),
      alias = join(f.root, "symlink.log");
    try {
      symlinkSync(f.log, alias, "file");
    } catch (error) {
      if ((error as NodeJS.ErrnoException).code !== "EPERM") throw error;
      t.skip("File symlink unavailable without changing current permissions");
      return;
    }
    f.seal([basename(f.log)]);
    f.refuse("rejected", /Current exporter stdout cannot be an input/, alias);
  });
});

test("developer evidence export does not merge distinct case-sensitive files", (t) => {
  const f = fixture(),
    source = join(f.root, "current-stdout.log");
  writeFileSync(source, "Completed different file.\r\n");
  const a = statSync(source, { bigint: true }),
    b = statSync(f.log, { bigint: true });
  if (a.dev === b.dev && a.ino === b.ino) {
    t.skip(
      "This directory is case-insensitive; distinct case-only names unavailable",
    );
    return;
  }
  f.seal([basename(source)]);
  const result = f.run("distinct");
  assert.equal(result.status, 0, result.stderr);
  assert.equal(
    readFileSync(join(f.root, "distinct", basename(source)), "utf8"),
    "Completed different file.\n",
  );
});

import assert from "node:assert/strict";
import { mkdtempSync, readFileSync, readdirSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join, relative } from "node:path";
import { createHash } from "node:crypto";
import { spawnSync } from "node:child_process";
import { pathToFileURL } from "node:url";
import { DiskStorage } from "../src/storage/index.ts";
const root = mkdtempSync(join(tmpdir(), "zara-v2-old-writer-"));
const home = join(root, ".local", "memory");
const disk = new DiskStorage(home, undefined, { projectRoot: root });
const identity = disk.workspace;
disk.close();
function inventory(path) {
  const out = {};
  function walk(p) {
    for (const entry of readdirSync(p, { withFileTypes: true })) {
      const full = join(p, entry.name);
      if (entry.isDirectory()) walk(full);
      else
        out[relative(path, full).replaceAll("\\", "/")] = createHash("sha256")
          .update(readFileSync(full))
          .digest("hex");
    }
  }
  walk(path);
  return out;
}
const before = inventory(root);
assert.ok(
  process.argv[2],
  "Pass an unchanged public schema-9 storage module path",
);
const old = pathToFileURL(process.argv[2]).href;
const code = `const {DiskStorage}=await import(${JSON.stringify(old)});let disk;try{disk=new DiskStorage(${JSON.stringify(home)});disk.close();process.exitCode=2;console.log(JSON.stringify({refused:false}));}catch(error){console.log(JSON.stringify({refused:true,code:error.code??null,name:error.name}));}`;
const run = spawnSync(
  process.execPath,
  ["--import", "tsx", "--input-type=module", "--eval", code],
  { cwd: process.cwd(), encoding: "utf8", timeout: 15000 },
);
assert.equal(run.status, 0, run.stderr);
const result = JSON.parse(run.stdout.trim());
assert.equal(result.refused, true);
assert.deepEqual(
  inventory(root),
  before,
  "Old writer changed new-format fixture",
);
const output = {
  format: 1,
  check: "old-9ccf36-writer-refuses-control3",
  runtime: process.version,
  schema: identity.schema_version,
  ...result,
  canonical_and_runtime_files_unchanged: true,
  models: 0,
};
writeFileSync(
  new URL("../docs/memory-v2-evidence/old-writer.json", import.meta.url),
  JSON.stringify(output, null, 2) + "\n",
);
console.log(JSON.stringify(output));

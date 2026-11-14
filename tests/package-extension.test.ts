import test from "node:test";
import assert from "node:assert/strict";
import { createHash } from "node:crypto";
import {
  mkdirSync,
  mkdtempSync,
  readFileSync,
  unlinkSync,
  writeFileSync,
} from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { readDependencyLock } from "../src/extension/resources.ts";
import { getWorkspaceProduct } from "../src/workspace/product.ts";

const digest = (bytes: Uint8Array | string) =>
  createHash("sha256").update(bytes).digest("hex");
const lock = Buffer.from(
  '\ufeff{"name":"synthetic-package","lockfileVersion":3}\r\n',
);

function fixture(packaged = false) {
  const root = mkdtempSync(
    join(process.env.ZARATUSTRA_TEST_ROOT ?? tmpdir(), "zara-package-lock-"),
  );
  writeFileSync(
    join(root, "package.json"),
    JSON.stringify({ name: "synthetic-package", version: "1.0.0" }),
  );
  if (!packaged) {
    writeFileSync(join(root, "package-lock.json"), lock);
    return root;
  }
  mkdirSync(join(root, "dist"));
  writeFileSync(join(root, "dist/dependency-lock.json"), lock);
  writeFileSync(
    join(root, "dist/runtime.js"),
    "export const synthetic = true;\n",
  );
  const files = ["dist/dependency-lock.json", "dist/runtime.js"].map(
    (path) => ({
      path,
      sha256: digest(readFileSync(join(root, path))),
    }),
  );
  writeFileSync(
    join(root, "dist/build-manifest.json"),
    JSON.stringify({
      format: 1,
      source_revision: getWorkspaceProduct(root, { runtime: "source" })
        .revision,
      runtime_revision: "sha256:" + digest(JSON.stringify(files)),
      files,
    }),
  );
  return root;
}

const fails = (code: string) => (error: unknown) =>
  (error as { code?: string }).code === code;

test("source Pi loading retains exact dependency provenance without a compiled dist", () => {
  const root = fixture();
  assert.deepEqual(readDependencyLock(root), lock);
});

test("installed package reads the exact build dependency lock after compiled inventory validation", () => {
  const root = fixture(true);
  assert.deepEqual(readDependencyLock(root), lock);
});

test("packaged dependency provenance rejects missing or corrupted retained lock bytes", () => {
  for (const corruption of ["missing", "changed"] as const) {
    const root = fixture(true);
    const path = join(root, "dist/dependency-lock.json");
    if (corruption === "missing") unlinkSync(path);
    else writeFileSync(path, "Different dependency provenance\n");
    assert.throws(() => readDependencyLock(root), fails("REVISION_CONFLICT"));
  }
});

test("packaged dependency fallback rejects another stale compiled file and an absent build", () => {
  const root = fixture(true);
  writeFileSync(join(root, "dist/runtime.js"), "Changed compiled code\n");
  assert.throws(() => readDependencyLock(root), fails("REVISION_CONFLICT"));
  const source = fixture();
  unlinkSync(join(source, "package-lock.json"));
  assert.throws(() => readDependencyLock(source), fails("RUNTIME_UNSUPPORTED"));
});

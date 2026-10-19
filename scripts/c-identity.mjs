// Check every tracked installed byte; disclose normal Pi/npm lockfile metadata changes.
import assert from "node:assert/strict";
import { execFileSync } from "node:child_process";
import { readFileSync, writeFileSync } from "node:fs";
import { join, resolve } from "node:path";
import { createHash } from "node:crypto";
const [pkgArg, out, previous] = process.argv.slice(2),
  pkg = resolve(pkgArg);
const git = (...args) =>
  execFileSync("git", ["-C", pkg, ...args], { maxBuffer: 32 * 1024 * 1024 });
const hash = (b) => createHash("sha256").update(b).digest("hex");
const head = git("rev-parse", "HEAD").toString().trim();
const paths = git("ls-files", "-z").toString().split("\0").filter(Boolean),
  entries = [],
  exceptions = [];
function diff(a, b, path = "") {
  if (JSON.stringify(a) === JSON.stringify(b)) return [];
  if (a && b && typeof a === "object" && typeof b === "object")
    return [...new Set([...Object.keys(a), ...Object.keys(b)])].flatMap((k) =>
      diff(a[k], b[k], path + "/" + k),
    );
  return [{ path, before: a ?? null, after: b ?? null }];
}
for (const path of paths) {
  const published = git("show", "HEAD:" + path),
    installed = readFileSync(join(pkg, path));
  const entry = {
    path,
    published_sha256: hash(published),
    installed_sha256: hash(installed),
  };
  entries.push(entry);
  if (!published.equals(installed)) {
    assert.equal(
      path,
      "package-lock.json",
      "Unexpected installed byte drift: " + path,
    );
    const differences = diff(JSON.parse(published), JSON.parse(installed));
    assert.ok(
      differences.every(
        (d) =>
          d.path.endsWith("/peer") && d.before === true && d.after === null,
      ),
      "Lock drift includes more than native peer metadata removal",
    );
    exceptions.push({ path, differences });
  }
}
let product_equality = null;
if (previous) {
  const productPaths = paths.filter((p) =>
    /^(src\/|instructions\/|skills\/|scripts\/|tests\/|package|tsconfig|\.dependency|eslint|validation\.config|AGENTS\.md)/.test(
      p,
    ),
  );
  const changes = git(
    "diff",
    "--name-only",
    previous,
    head,
    "--",
    ...productPaths,
  )
    .toString()
    .trim();
  assert.equal(changes, "");
  product_equality = {
    previous,
    head,
    count: productPaths.length,
    identical: true,
    paths: productPaths,
  };
}
writeFileSync(
  out,
  JSON.stringify(
    {
      head,
      tracked_files: paths.length,
      status: git("status", "--porcelain=v1").toString(),
      entries,
      exceptions,
      product_equality,
    },
    null,
    2,
  ),
);
console.log(
  JSON.stringify({
    head,
    tracked_files: paths.length,
    exceptions: exceptions.map((e) => ({
      path: e.path,
      count: e.differences.length,
    })),
    product_equality: product_equality?.identical,
  }),
);

// Synthetic developer proof only. Sessions must already be closed. No commit/push.
import assert from "node:assert/strict";
import { execFileSync } from "node:child_process";
import { createHash } from "node:crypto";
import {
  existsSync,
  lstatSync,
  readFileSync,
  readdirSync,
  writeFileSync,
} from "node:fs";
import { join, relative, resolve } from "node:path";
import { DatabaseSync } from "node:sqlite";

const [projectArg, reportArg] = process.argv.slice(2);
const project = resolve(projectArg),
  report = resolve(reportArg);
assert.ok(
  relative(project, report).startsWith(".."),
  "Keep the receipt outside the indexed fixture",
);
assert.equal(
  existsSync(join(project, ".local/memory/writer.lock")),
  false,
  "Close the writer before Git proof",
);
const git = (...args) =>
  execFileSync("git", [
    "-C",
    project,
    "-c",
    "core.autocrlf=false",
    "-c",
    "core.excludesFile=",
    ...args,
  ]);
git("init");
assert.equal(
  git("remote").toString().trim(),
  "",
  "Fixture must have no remote",
);
const memory = join(project, ".local/memory");
const db = new DatabaseSync(join(memory, "zara.sqlite"), { readOnly: true });
let state;
try {
  const count = (table) =>
    db.prepare(`SELECT count(*) AS n FROM ${table}`).get().n;
  state = {
    integrity: db.prepare("PRAGMA integrity_check").get().integrity_check,
    workspace: JSON.parse(db.prepare("SELECT json FROM meta").get().json),
    records: count("records"),
    work: db
      .prepare("SELECT count(*) AS n FROM records WHERE kind='work'")
      .get().n,
    receipts: count("receipts"),
    changes: count("changes"),
  };
  assert.equal(state.integrity, "ok");
  assert.ok(state.work > 0 && state.receipts > 0 && state.changes > 0);
} finally {
  db.close();
}
// Inventory after the read connection closes. Any WAL/SHM still present is included,
// never hidden by a blanket exclusion. Git is not run against an open SQLite handle.
assert.equal(existsSync(join(memory, "writer.lock")), false);
const files = [];
function visit(path) {
  assert.equal(lstatSync(path).isSymbolicLink(), false);
  if (lstatSync(path).isDirectory()) {
    for (const name of readdirSync(path).sort()) visit(join(path, name));
  } else files.push(relative(project, path).replaceAll("\\", "/"));
}
visit(join(project, ".local"));
for (const path of [
  ".local/memory/zara.sqlite",
  ".local/memory/workspace.json",
  ".local/memory/active.json",
  ".local/imports/fixture.md",
  ".local/output/report.txt",
])
  assert.ok(files.includes(path), path);
assert.ok(files.some((path) => path.startsWith(".local/memory/materials/")));
const status = git("status", "--short", "--untracked-files=all").toString();
assert.ok(status.includes(".local/memory/zara.sqlite"));
git("add", "-A");
const entries = git("ls-files", "--stage", "-z")
  .toString()
  .split("\0")
  .filter(Boolean)
  .map((line) => {
    const [meta, path] = line.split("\t");
    return { path, object: meta.split(" ")[1] };
  });
const sha = (bytes) => createHash("sha256").update(bytes).digest("hex");
const objects = files.map((path) => {
  const entry = entries.find((item) => item.path === path);
  assert.ok(entry, `${path} must be available to ordinary git add -A`);
  const disk = readFileSync(join(project, path)),
    blob = git("cat-file", "blob", entry.object);
  assert.equal(sha(blob), sha(disk), path);
  return {
    path,
    git_object: entry.object,
    bytes: disk.length,
    sha256: sha(disk),
  };
});
const receipt = {
  project,
  state,
  closed_session: true,
  no_remote: true,
  commit_or_push: false,
  fixture_git_settings: {
    autocrlf: false,
    global_excludes_disabled_for_fixture: true,
  },
  status_before_add: status,
  memory_files_after_close: readdirSync(memory),
  wal_or_shm_after_close: files.filter((p) =>
    /zara\.sqlite-(wal|shm)$/.test(p),
  ),
  objects,
  no_live_sqlite_commit_or_restore_claim: true,
};
writeFileSync(report, JSON.stringify(receipt, null, 2));
console.log(
  JSON.stringify({
    indexed_local_objects: objects.length,
    records: state.records,
    work: state.work,
    receipts: state.receipts,
    changes: state.changes,
    wal_or_shm_after_close: receipt.wal_or_shm_after_close,
  }),
);

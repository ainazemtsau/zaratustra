import test from "node:test";
import assert from "node:assert/strict";
import { spawnSync } from "node:child_process";
import {
  existsSync,
  mkdirSync,
  mkdtempSync,
  readFileSync,
  readdirSync,
  symlinkSync,
  unlinkSync,
  writeFileSync,
} from "node:fs";
import { tmpdir } from "node:os";
import { join, resolve } from "node:path";
import { workspacePaths } from "../src/extension/workspace.ts";
import { digest } from "../src/core/index.ts";
import { DiskStorage } from "../src/storage/index.ts";

const pkg = resolve("."),
  sdk = resolve("node_modules/@earendil-works/pi-coding-agent/dist/index.js");
function fixture() {
  const base = mkdtempSync(
    join(process.env.ZARATUSTRA_TEST_ROOT ?? tmpdir(), "zara-startup-"),
  );
  const project = join(base, "project"),
    agent = join(base, "agent");
  mkdirSync(join(project, ".pi"), { recursive: true });
  mkdirSync(agent);
  writeFileSync(
    join(project, ".pi/settings.json"),
    JSON.stringify({ packages: [pkg] }),
  );
  const env: NodeJS.ProcessEnv = { ...process.env, PI_CODING_AGENT_DIR: agent };
  for (const name of Object.keys(env))
    if (name.startsWith("ZARATUSTRA_")) delete env[name];
  let serial = 0;
  const run = (action: string, overrides: NodeJS.ProcessEnv = {}) => {
    const report = join(base, `report-${++serial}.json`);
    const result = spawnSync(
      process.execPath,
      [resolve("scripts/startup-native.mjs"), sdk, pkg, action, report],
      {
        cwd: project,
        env: { ...env, ...overrides },
        encoding: "utf8",
        timeout: 90000,
      },
    );
    writeFileSync(
      join(base, `attempt-${serial}.log`),
      result.stdout + result.stderr,
    );
    assert.equal(result.status, 0, result.stdout + result.stderr);
    return JSON.parse(readFileSync(report, "utf8"));
  };
  return { base, project, agent, run };
}

test("startup native package discovery creates all four trusted roots, preserves observed provenance, peers and fresh-process state", () => {
  const f = fixture();
  mkdirSync(join(f.agent, "extensions"));
  writeFileSync(
    join(f.agent, "extensions/peer.js"),
    `export default function(pi) {
    pi.on('input', (event) => ({ action: 'transform', text: 'Peer transformed: ' + event.text }));
    pi.on('context', (event) => ({ messages: [...event.messages, {role:'custom', customType:'startup.peer', content:'Retained peer data', display:false, timestamp:0}] }));
  }`,
  );
  mkdirSync(join(f.project, ".local/imports"), { recursive: true });
  writeFileSync(
    join(f.project, ".local/imports/fixture.md"),
    "# Synthetic input\nPreserve these original bytes.\n",
  );
  const first = f.run("init");
  assert.equal(first.extensions.length, 2);
  assert.ok(first.contextTypes.includes("startup.peer"));
  const original = first.calls.find(
    (c: { name: string }) => c.name === "zara_read",
  ).result.details.data;
  assert.match(original.data.retained_excerpt, /^Peer transformed:/);
  assert.equal(original.data.provenance.input_integrity, "observed_stage_only");
  const second = f.run("read");
  assert.equal(second.snapshot.workspace_id, first.snapshot.workspace_id);
  assert.equal(second.snapshot.active_epoch, first.snapshot.active_epoch);
  assert.equal(second.provider_dispatches, 0);
  assert.equal(second.snapshot.captured_sources.length, 0);
  assert.equal(existsSync(join(f.project, ".local/.gitignore")), false);
  assert.ok(first.storage_files_while_open.includes("writer.lock"));
  assert.ok(first.storage_files_while_open.includes("zara.sqlite-wal"));
  assert.ok(!first.storage_files_after_close.includes("writer.lock"));
  // Explicit synthetic fixture setup only: exclude Pi/package cache, never data.
  writeFileSync(join(f.project, ".gitignore"), "/.pi/\n");
  const gitProof = join(f.base, "closed-git-objects.json");
  const indexed = spawnSync(
    process.execPath,
    [resolve("scripts/startup-git.mjs"), f.project, gitProof],
    { encoding: "utf8" },
  );
  writeFileSync(
    join(f.base, "closed-git-objects.log"),
    indexed.stdout + indexed.stderr,
  );
  assert.equal(indexed.status, 0, indexed.stdout + indexed.stderr);
  const objects = JSON.parse(readFileSync(gitProof, "utf8"));
  assert.ok(objects.objects.length >= 7);
  assert.equal(objects.no_remote, true);
  assert.ok(objects.state.work > 0 && objects.state.changes > 0);
  const other = fixture().run("health");
  assert.notEqual(other.snapshot.workspace_id, first.snapshot.workspace_id);
  // A separately preconfigured scope can use the automatic backup destination.
  const protectedReport = f.run("backup", {
    ZARATUSTRA_SCOPES: '["restricted:read","restricted:write"]',
  });
  assert.equal(
    protectedReport.snapshot.workspace_id,
    first.snapshot.workspace_id,
  );
  assert.ok(readdirSync(join(f.project, ".local/backups")).length > 0);
});

test("startup untrusted native personal extension refuses before project-local writes", () => {
  const f = fixture();
  // A personal package can load before trust, unlike the normal project package.
  writeFileSync(
    join(f.agent, "settings.json"),
    JSON.stringify({ packages: [pkg] }),
  );
  const report = f.run("untrusted");
  assert.equal(report.snapshot.available, false);
  assert.equal(report.snapshot.error.code, "PERMISSION_DENIED");
  assert.equal(existsSync(join(f.project, ".local")), false);
});

test("startup corrupt and missing known databases refuse instead of initializing replacements", () => {
  for (const fault of ["missing", "corrupt"]) {
    const f = fixture();
    f.run("health");
    const memory = join(f.project, ".local/memory"),
      db = join(memory, "zara.sqlite");
    const control = readFileSync(join(memory, "active.json"));
    if (fault === "missing") unlinkSync(db);
    else writeFileSync(db, "Synthetic damaged database");
    const bytes = existsSync(db) ? digest(readFileSync(db)) : null;
    const report = f.run("inspect");
    assert.equal(report.snapshot.available, false);
    assert.deepEqual(readFileSync(join(memory, "active.json")), control);
    assert.equal(existsSync(db) ? digest(readFileSync(db)) : null, bytes);
  }
});

test("startup explicit legacy directories and absent optional roots retain their behavior", () => {
  const f = fixture(),
    home = join(f.base, "explicit-memory");
  const explicit = f.run("health", { ZARATUSTRA_HOME: home });
  assert.equal(explicit.snapshot.workspace_paths.profile, "explicit");
  assert.equal(explicit.snapshot.workspace_paths.memory, home);
  assert.equal(explicit.snapshot.managed_output_root, null);
  assert.deepEqual(explicit.snapshot.workspace_paths.imports, []);
  assert.equal(existsSync(join(f.project, ".local")), false);
  const again = f.run("health", { ZARATUSTRA_HOME: home });
  assert.equal(again.snapshot.workspace_id, explicit.snapshot.workspace_id);
  const integrity = f.run("integrity", {
    ZARATUSTRA_HOME: home,
    ZARATUSTRA_INTERACTIVE_INPUT_CONTRACT: "first-untransformed",
  });
  assert.equal(integrity.snapshot.workspace_id, explicit.snapshot.workspace_id);
  const imports = join(f.base, "imports"),
    output = join(f.base, "output"),
    backups = join(f.base, "backups");
  for (const directory of [imports, output, backups]) mkdirSync(directory);
  writeFileSync(
    join(imports, "fixture.md"),
    "# Synthetic explicit input\nPreserve configured deployment.\n",
  );
  const full = f.run("init", {
    ZARATUSTRA_HOME: home,
    ZARATUSTRA_IMPORT_ROOTS: JSON.stringify([imports]),
    ZARATUSTRA_OUTPUT_ROOT: output,
    ZARATUSTRA_BACKUP_ROOT: backups,
  });
  assert.equal(full.snapshot.workspace_id, explicit.snapshot.workspace_id);
  assert.equal(existsSync(join(f.project, ".local")), false);
  for (const overrides of [
    { ZARATUSTRA_OUTPUT_ROOT: join(f.base, "output") },
    { ZARATUSTRA_IMPORT_ROOTS: "[]" },
    { ZARATUSTRA_BACKUP_ROOT: "" },
    { ZARATUSTRA_HOME: "" },
    { ZARATUSTRA_HOME: "relative" },
    { ZARATUSTRA_SCOPES: "invalid" },
    { ZARATUSTRA_INTERACTIVE_INPUT_CONTRACT: "invalid" },
  ]) {
    assert.equal(f.run("inspect", overrides).snapshot.available, false);
    assert.equal(existsSync(join(f.project, ".local")), false);
  }
});

test("startup defaults reject links into package/cache/other memory before writes", () => {
  for (const blocked of ["package", "agent", "memory"]) {
    const f = fixture();
    if (blocked === "memory")
      writeFileSync(join(f.project, "zara.sqlite"), "Synthetic memory marker");
    assert.throws(() =>
      workspacePaths(
        { cwd: f.project, isProjectTrusted: () => true },
        blocked === "package" ? f.project : pkg,
        blocked === "agent" ? f.project : f.agent,
        {},
      ),
    );
    assert.equal(existsSync(join(f.project, ".local")), false);
  }
  for (const targetName of ["package", "agent", "other-memory"]) {
    const f = fixture(),
      target = join(
        f.base,
        targetName === "agent" ? "agent/cache" : targetName,
      );
    mkdirSync(target, { recursive: true });
    symlinkSync(
      target,
      join(f.project, ".local"),
      process.platform === "win32" ? "junction" : "dir",
    );
    assert.throws(() =>
      workspacePaths(
        { cwd: f.project, isProjectTrusted: () => true },
        targetName === "package" ? target : pkg,
        f.agent,
        {},
      ),
    );
    assert.deepEqual(readdirSync(target), []);
    assert.equal(f.run("inspect").snapshot.available, false);
    assert.deepEqual(readdirSync(target), []);
  }
  const f = fixture();
  mkdirSync(join(f.project, ".local"));
  symlinkSync(
    f.agent,
    join(f.project, ".local/output"),
    process.platform === "win32" ? "junction" : "dir",
  );
  assert.equal(f.run("inspect").snapshot.available, false);
  assert.equal(existsSync(join(f.project, ".local/.gitignore")), false);
  assert.equal(existsSync(join(f.project, ".local/memory")), false);
});

test("startup respects arbitrary user Git exclusion rules without a prerequisite or ignore writes", () => {
  const f = fixture(),
    local = join(f.project, ".local");
  mkdirSync(local);
  const ignore = join(local, ".gitignore"),
    rootIgnore = join(f.project, ".gitignore");
  const initialized = spawnSync("git", ["init", f.project], {
    encoding: "utf8",
  });
  assert.equal(initialized.status, 0, initialized.stderr);
  const exclude = join(f.project, ".git/info/exclude");
  for (const bytes of [
    "# User rules\noutput/\n",
    " *\n",
    "/*\n!memory/\n",
    "*\n",
    "",
  ]) {
    writeFileSync(ignore, bytes);
    writeFileSync(rootIgnore, "# Owner configuration\n.local/output/\n");
    writeFileSync(exclude, "# Owner local exclusion\n.local/backups/\n");
    const before = [ignore, rootIgnore, exclude].map((path) =>
      readFileSync(path),
    );
    assert.notEqual(f.run("health").snapshot.available, false);
    for (const [i, path] of [ignore, rootIgnore, exclude].entries())
      assert.deepEqual(readFileSync(path), before[i]);
  }
});

test("startup ordinary project metadata is not mistaken for a Zaratustra store", () => {
  for (const name of ["workspace.json", "active.json"]) {
    const f = fixture(),
      content = '{"ordinary_project":true}\n';
    writeFileSync(join(f.project, name), content);
    const paths = workspacePaths(
      { cwd: f.project, isProjectTrusted: () => true },
      pkg,
      f.agent,
      {},
    );
    assert.equal(paths.profile, "project-local");
    assert.equal(readFileSync(join(f.project, name), "utf8"), content);
  }
  const f = fixture();
  for (const name of ["workspace.json", "active.json"])
    writeFileSync(join(f.project, name), "Synthetic damaged memory metadata");
  assert.throws(() =>
    workspacePaths(
      { cwd: f.project, isProjectTrusted: () => true },
      pkg,
      f.agent,
      {},
    ),
  );
  assert.equal(existsSync(join(f.project, ".local")), false);
});

function fileBytes(root: string): Record<string, string> {
  const files: Record<string, string> = {};
  const visit = (path: string) => {
    for (const entry of readdirSync(path, { withFileTypes: true })) {
      const full = join(path, entry.name);
      if (entry.isDirectory()) visit(full);
      else files[full.slice(root.length)] = digest(readFileSync(full));
    }
  };
  visit(root);
  return files;
}

test("startup refuses an actual existing .local store before creating nested default roots and preserves bytes/identity", () => {
  const f = fixture(),
    home = join(f.project, ".local");
  const old = new DiskStorage(home),
    identity = { ...old.workspace };
  old.close();
  const before = fileBytes(home);
  assert.throws(
    () =>
      workspacePaths(
        { cwd: f.project, isProjectTrusted: () => true },
        pkg,
        f.agent,
        {},
      ),
    /existing memory/,
  );
  const report = f.run("inspect");
  assert.equal(report.snapshot.available, false);
  assert.equal(report.snapshot.error.code, "PERMISSION_DENIED");
  assert.deepEqual(fileBytes(home), before);
  assert.deepEqual(
    JSON.parse(readFileSync(join(home, "workspace.json"), "utf8")),
    identity,
  );
  for (const name of ["memory", "imports", "output", "backups", ".gitignore"])
    assert.equal(existsSync(join(home, name)), false);
  const reopened = new DiskStorage(home);
  assert.deepEqual(reopened.workspace, identity);
  reopened.close();
});

test("startup accepts benign .local workspace metadata and reopens normal .local/memory", () => {
  const f = fixture(),
    local = join(f.project, ".local"),
    content = '{"ordinary_project":true}\n';
  mkdirSync(local);
  writeFileSync(join(local, "workspace.json"), content);
  const first = f.run("health"),
    second = f.run("health");
  assert.notEqual(first.snapshot.available, false);
  assert.equal(second.snapshot.workspace_id, first.snapshot.workspace_id);
  assert.equal(readFileSync(join(local, "workspace.json"), "utf8"), content);
  assert.equal(existsSync(join(local, ".gitignore")), false);
});

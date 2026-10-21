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
  const initialized = spawnSync("git", ["init", f.project], {
    encoding: "utf8",
  });
  assert.equal(initialized.status, 0, initialized.stderr);
  const untracked = spawnSync(
    "git",
    ["-C", f.project, "ls-files", "--others", "--exclude-standard"],
    { encoding: "utf8" },
  );
  assert.equal(untracked.status, 0, untracked.stderr);
  assert.ok(!untracked.stdout.includes(".local"));
  assert.equal(existsSync(join(f.project, ".gitignore")), false);
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

test("startup preserves existing user ignore bytes and refuses inadequate protection", () => {
  const f = fixture(),
    local = join(f.project, ".local");
  mkdirSync(local);
  const ignore = join(local, ".gitignore"),
    bytes = "# User rules\noutput/\n";
  writeFileSync(ignore, bytes);
  assert.equal(f.run("inspect").snapshot.available, false);
  assert.equal(readFileSync(ignore, "utf8"), bytes);
  assert.deepEqual(readdirSync(local), [".gitignore"]);
  for (const ineffective of [" *\n", "/*\n!memory/\n"]) {
    writeFileSync(ignore, ineffective);
    assert.throws(() =>
      workspacePaths(
        { cwd: f.project, isProjectTrusted: () => true },
        pkg,
        f.agent,
        {},
      ),
    );
    assert.equal(readFileSync(ignore, "utf8"), ineffective);
    assert.deepEqual(readdirSync(local), [".gitignore"]);
  }
  writeFileSync(ignore, "# User protection\n*\n");
  const paths = workspacePaths(
    { cwd: f.project, isProjectTrusted: () => true },
    pkg,
    f.agent,
    {},
  );
  assert.equal(paths.profile, "project-local");
  assert.equal(readFileSync(ignore, "utf8"), "# User protection\n*\n");
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

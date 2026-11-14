import test from "node:test";
import assert from "node:assert/strict";
import { execFileSync } from "node:child_process";
import { mkdirSync, mkdtempSync, readFileSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { dirname, join, resolve } from "node:path";
import {
  WorkspaceInstaller,
  attachPi,
  readWorkspaceManifest,
} from "../src/workspace/index.ts";
import { PRODUCT_SKILLS } from "../src/workspace/templates.ts";

interface DiscoveryReport {
  skills: { name: string; filePath: string }[];
  extension_errors: unknown[];
  extension_warnings: unknown[];
  skill_diagnostics: {
    type: string;
    collision?: { name: string; winnerPath: string; loserPath: string };
  }[];
  prompt_diagnostics: unknown[];
  theme_diagnostics: unknown[];
  model_calls: number;
  network_calls: number;
}

function write(path: string, text: string) {
  mkdirSync(dirname(path), { recursive: true });
  writeFileSync(path, text);
}
function skill(path: string, name: string) {
  write(
    path,
    `---\nname: ${name}\ndescription: Synthetic ${name} fixture.\n---\n\nRead the synthetic source.\n`,
  );
}
function fixture() {
  assert.equal(
    process.platform,
    "win32",
    "Qualified discovery fixture is Windows",
  );
  const base = mkdtempSync(
    join(process.env.ZARATUSTRA_TEST_ROOT ?? tmpdir(), "zara-discovery-"),
  );
  const project = join(base, "project");
  const packageRoot = join(base, "product");
  const home = join(base, "synthetic-home");
  const agent = join(base, "synthetic-agent");
  for (const path of [join(project, ".git"), packageRoot, home, agent])
    mkdirSync(path, { recursive: true });
  write(
    join(packageRoot, "package.json"),
    JSON.stringify({
      name: "synthetic-product",
      version: "1.0.0",
      pi: { skills: PRODUCT_SKILLS.map((name) => `skills/${name}`) },
    }),
  );
  for (const name of PRODUCT_SKILLS)
    skill(join(packageRoot, "skills", name, "SKILL.md"), name);
  return { base, project, packageRoot, home, agent };
}
function probe(f: ReturnType<typeof fixture>) {
  const env: NodeJS.ProcessEnv = {
    ...process.env,
    USERPROFILE: f.home,
    PI_CODING_AGENT_DIR: f.agent,
    PI_OFFLINE: "1",
  };
  delete env.HOME;
  for (const key of Object.keys(env))
    if (key.startsWith("ZARATUSTRA_")) delete env[key];
  const output = join(f.base, "discovery.json");
  execFileSync(
    process.execPath,
    [
      resolve("scripts/skill-discovery-probe.mjs"),
      resolve("node_modules/@earendil-works/pi-coding-agent"),
      f.project,
      f.agent,
      f.home,
      output,
    ],
    { env, encoding: "utf8", windowsHide: true },
  );
  return JSON.parse(readFileSync(output, "utf8")) as DiscoveryReport;
}
function clean(report: DiscoveryReport) {
  for (const diagnostics of [
    report.extension_errors,
    report.extension_warnings,
    report.skill_diagnostics,
    report.prompt_diagnostics,
    report.theme_diagnostics,
  ])
    assert.deepEqual(diagnostics, []);
  assert.equal(report.model_calls, 0);
  assert.equal(report.network_calls, 0);
}
function portable(f: ReturnType<typeof fixture>) {
  new WorkspaceInstaller(f.project, {
    packageRoot: f.packageRoot,
  }).initialize();
  attachPi(f.project, {
    packageRoot: f.packageRoot,
    runInstall(source) {
      write(
        join(f.project, ".pi/settings.json"),
        JSON.stringify({ packages: [source] }),
      );
    },
  });
}

test("native discovery reproduces three-source collisions before prompt hooks", () => {
  const f = fixture();
  for (const name of PRODUCT_SKILLS)
    for (const directory of [".agents", ".pi"])
      skill(join(f.project, directory, "skills", name, "SKILL.md"), name);
  write(
    join(f.project, ".pi/settings.json"),
    JSON.stringify({ packages: [f.packageRoot] }),
  );
  const result = probe(f);
  assert.equal(result.skill_diagnostics.length, 8);
  for (const name of PRODUCT_SKILLS) {
    assert.equal(
      result.skills.filter((entry) => entry.name === name).length,
      1,
    );
    assert.equal(
      result.skill_diagnostics.filter((d) => d.collision?.name === name).length,
      2,
    );
  }
});

test("portable native discovery loads shared routes plus scoped personal and unrelated skills once", () => {
  const f = fixture();
  portable(f);
  skill(
    join(f.project, "skills/personal/synthetic-summary/SKILL.md"),
    "synthetic-summary",
  );
  const manifest = readWorkspaceManifest(f.project)!;
  manifest.personal_skills = [
    {
      name: "synthetic-summary",
      description: "Synthetic scoped procedure",
      path: "skills/personal/synthetic-summary/SKILL.md",
      activity_key: "synthetic-activity",
    },
  ];
  write(join(f.project, "zaratustra.json"), JSON.stringify(manifest));
  new WorkspaceInstaller(f.project, {
    packageRoot: f.packageRoot,
  }).initialize();
  skill(join(f.project, ".pi/skills/owner-tool/SKILL.md"), "owner-tool");
  skill(
    join(f.home, ".agents/skills/synthetic-global/SKILL.md"),
    "synthetic-global",
  );
  const result = probe(f);
  clean(result);
  assert.equal(result.skills.length, 7);
  for (const name of [...PRODUCT_SKILLS, "synthetic-summary"])
    assert.equal(
      resolve(result.skills.find((entry) => entry.name === name)!.filePath),
      join(f.project, ".agents/skills", name, "SKILL.md"),
    );
  const route = readFileSync(
    join(f.project, ".agents/skills/synthetic-summary/SKILL.md"),
    "utf8",
  );
  assert.match(route, /Activity "synthetic-activity"/);
  assert.match(
    route,
    /\.\.\/\.\.\/\.\.\/skills\/personal\/synthetic-summary\/SKILL.md/,
  );
  assert(result.skills.some((entry) => entry.name === "owner-tool"));
  assert(result.skills.some((entry) => entry.name === "synthetic-global"));
});

test("standalone Pi package retains its four original package skills", () => {
  const f = fixture();
  write(
    join(f.project, ".pi/settings.json"),
    JSON.stringify({ packages: [f.packageRoot] }),
  );
  const result = probe(f);
  clean(result);
  assert.equal(result.skills.length, 4);
  for (const name of PRODUCT_SKILLS)
    assert.equal(
      resolve(result.skills.find((entry) => entry.name === name)!.filePath),
      join(f.packageRoot, "skills", name, "SKILL.md"),
    );
});

test("a genuine owner name conflict stays visible instead of being suppressed", () => {
  const f = fixture();
  portable(f);
  const owner = join(f.project, ".pi/skills/owner-copy/SKILL.md");
  skill(owner, "zaratustra-work");
  const result = probe(f);
  assert.deepEqual(result.extension_errors, []);
  assert.equal(result.skill_diagnostics.length, 1);
  assert.equal(result.skill_diagnostics[0].type, "collision");
  assert.equal(result.skill_diagnostics[0].collision?.name, "zaratustra-work");
  assert.equal(
    resolve(result.skill_diagnostics[0].collision!.winnerPath),
    owner,
  );
  assert.equal(
    resolve(result.skill_diagnostics[0].collision!.loserPath),
    join(f.project, ".agents/skills/zaratustra-work/SKILL.md"),
  );
});

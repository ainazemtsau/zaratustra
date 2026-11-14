// Actual npm archive installation, native Pi discovery and optional managed session checks.
import assert from "node:assert/strict";
import { createHash } from "node:crypto";
import { execFileSync } from "node:child_process";
import {
  existsSync,
  mkdirSync,
  mkdtempSync,
  readFileSync,
  writeFileSync,
} from "node:fs";
import { tmpdir } from "node:os";
import { dirname, isAbsolute, join, resolve } from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";
import { parseArgs } from "node:util";

const packageRoot = fileURLToPath(new URL("..", import.meta.url));
const { values } = parseArgs({
  options: { "sdk-root": { type: "string" }, managed: { type: "boolean" } },
});
assert.equal(process.platform, "win32", "Qualified startup fixture is Windows");
if (values["sdk-root"])
  assert(isAbsolute(values["sdk-root"]), "Use an absolute --sdk-root path");
const sdkRoot = resolve(
  values["sdk-root"] ??
    join(packageRoot, "node_modules/@earendil-works/pi-coding-agent"),
);
const sdkInfo = JSON.parse(readFileSync(join(sdkRoot, "package.json"), "utf8"));
assert.equal(sdkInfo.name, "@earendil-works/pi-coding-agent");
const base = mkdtempSync(
  join(
    process.env.ZARATUSTRA_TEST_ROOT ?? tmpdir(),
    "zara-packaged-extension-",
  ),
);
const consumer = join(base, "consumer");
const project = join(base, "workspace");
const agentDir = join(base, "pi-agent");
const syntheticHome = join(base, "synthetic-home");
for (const directory of [consumer, agentDir, syntheticHome])
  mkdirSync(directory);
const npmrc = join(base, "empty.npmrc");
const globalNpmrc = join(base, "global.npmrc");
writeFileSync(npmrc, "");
writeFileSync(globalNpmrc, "");
const npmCLI = [
  process.env.npm_execpath,
  join(dirname(process.execPath), "node_modules/npm/bin/npm-cli.js"),
  resolve(dirname(process.execPath), "../lib/node_modules/npm/bin/npm-cli.js"),
].find((path) => path && existsSync(path));
assert(npmCLI, "Run with a standard Node/npm installation or npm_execpath.");
const env = {
  ...process.env,
  PI_OFFLINE: "1",
  NPM_CONFIG_LOGS_DIR: join(base, "npm-logs"),
};
const npm = (args) =>
  execFileSync(
    process.execPath,
    [
      npmCLI,
      ...args,
      "--offline",
      "--userconfig",
      npmrc,
      "--globalconfig",
      globalNpmrc,
    ],
    {
      cwd: packageRoot,
      env,
      encoding: "utf8",
      windowsHide: true,
      maxBuffer: 8 * 1024 * 1024,
    },
  );
const packed = JSON.parse(
  npm(["pack", "--ignore-scripts", "--json", "--pack-destination", base]),
)[0];
const tarball = join(base, packed.filename);
npm([
  "install",
  "--prefix",
  consumer,
  tarball,
  "--ignore-scripts",
  "--omit=dev",
  "--omit=optional",
  "--no-audit",
  "--no-fund",
]);
const installedPackage = join(consumer, "node_modules/zaratustra");
assert.equal(existsSync(join(installedPackage, "package-lock.json")), false);
for (const peer of ["@earendil-works/pi-coding-agent", "typebox"])
  assert.equal(existsSync(join(consumer, "node_modules", peer)), false);
const hash = (bytes) => createHash("sha256").update(bytes).digest("hex");
assert.equal(
  hash(readFileSync(join(installedPackage, "dist/dependency-lock.json"))),
  hash(readFileSync(join(packageRoot, "package-lock.json"))),
);
const {
  WorkspaceInstaller,
  attachPi,
  getWorkspaceProduct,
  readWorkspaceManifest,
} = await import(
  pathToFileURL(join(installedPackage, "dist/workspace/index.js")).href
);
const product = getWorkspaceProduct(installedPackage);
execFileSync(
  process.execPath,
  [
    join(installedPackage, "dist/cli/index.js"),
    "workspace",
    "init",
    "--path",
    project,
  ],
  { cwd: consumer, env, encoding: "utf8", windowsHide: true },
);
const productNames = [
  "zaratustra-work",
  "zaratustra-memory",
  "zaratustra-documents",
  "zaratustra-sleep",
];
function write(path, text) {
  mkdirSync(dirname(path), { recursive: true });
  writeFileSync(path, text);
}
function syntheticSkill(path, name) {
  write(
    path,
    `---\nname: ${name}\ndescription: Synthetic ${name} fixture.\n---\n\nRead the synthetic observations.\n`,
  );
}
function isolatedEnvironment(home, agent) {
  const isolated = {
    ...env,
    USERPROFILE: home,
    PI_CODING_AGENT_DIR: agent,
  };
  // The native SDK falls back to the Windows profile. Do not expose the caller's
  // HOME override or ancestor/user skill directories to a synthetic fixture.
  delete isolated.HOME;
  for (const key of Object.keys(isolated))
    if (key.startsWith("ZARATUSTRA_")) delete isolated[key];
  return isolated;
}
const nativeCLI = join(
  sdkRoot,
  typeof sdkInfo.bin === "string" ? sdkInfo.bin : sdkInfo.bin.pi,
);
function nativeInstall(source, cwd, home, agent) {
  execFileSync(
    process.execPath,
    [nativeCLI, "install", "--local", "--approve", source],
    {
      cwd,
      env: isolatedEnvironment(home, agent),
      encoding: "utf8",
      windowsHide: true,
    },
  );
}
function probe(
  cwd,
  home,
  agent,
  label,
  selectedSDK = sdkRoot,
  defaultPackage,
  cliPath,
) {
  const path = join(base, `${label}-startup.json`);
  execFileSync(
    process.execPath,
    [
      join(packageRoot, "scripts/skill-discovery-probe.mjs"),
      selectedSDK,
      cwd,
      agent,
      home,
      path,
      ...(defaultPackage ? [defaultPackage] : []),
    ],
    {
      cwd: base,
      env: {
        ...isolatedEnvironment(home, agent),
        ...(cliPath !== undefined ? { Path: cliPath, PATH: cliPath } : {}),
      },
      encoding: "utf8",
      windowsHide: true,
    },
  );
  return JSON.parse(readFileSync(path, "utf8"));
}
function clean(report) {
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
  assert.equal(report.managed_store_created, false);
}
mkdirSync(join(project, ".git")); // Native ancestor discovery stops here.
const personalPath = "skills/personal/synthetic-summary/SKILL.md";
syntheticSkill(join(project, personalPath), "synthetic-summary");
write(
  join(project, "activities/synthetic/AGENTS.md"),
  "# Synthetic Activity\n",
);
const manifest = readWorkspaceManifest(project);
manifest.activities = [
  {
    key: "synthetic-activity",
    label: "Synthetic Activity",
    guidance_path: "activities/synthetic/AGENTS.md",
  },
];
manifest.personal_skills = [
  {
    name: "synthetic-summary",
    description: "Synthetic scoped summary",
    path: personalPath,
    activity_key: "synthetic-activity",
  },
];
writeFileSync(join(project, "zaratustra.json"), JSON.stringify(manifest));
assert.equal(
  new WorkspaceInstaller(project, {
    packageRoot: installedPackage,
  }).initialize().state,
  "committed",
);
const attachment = attachPi(project, {
  packageRoot: installedPackage,
  source: installedPackage,
  runInstall: (source, cwd) =>
    nativeInstall(source, cwd, syntheticHome, agentDir),
});
assert.equal(attachment.state, "pending_native_trust");
const settings = JSON.parse(
  readFileSync(join(project, ".pi/settings.json"), "utf8"),
);
assert.equal(settings.packages.length, 1);
assert.deepEqual(settings.packages[0].skills, []);
syntheticSkill(join(project, ".pi/skills/owner-tool/SKILL.md"), "owner-tool");
syntheticSkill(
  join(syntheticHome, ".agents/skills/synthetic-global/SKILL.md"),
  "synthetic-global",
);
const portable = probe(project, syntheticHome, agentDir, "portable");
clean(portable);
const entry = resolve(installedPackage, "src/extension/index.ts");
const extensions = portable.extensions.filter(
  (extension) => resolve(extension.path) === entry,
);
assert.equal(extensions.length, 1);
assert(extensions[0].tools.includes("zara_map"));
assert.equal(portable.skills.length, 7);
for (const name of [...productNames, "synthetic-summary"]) {
  const selected = portable.skills.filter((skill) => skill.name === name);
  assert.equal(selected.length, 1);
  const wrapper = join(project, ".agents/skills", name, "SKILL.md");
  assert.equal(resolve(selected[0].filePath), wrapper);
  assert.equal(
    existsSync(join(project, ".pi/skills", name, "SKILL.md")),
    false,
  );
  const source =
    name === "synthetic-summary"
      ? personalPath
      : `skills/system/${name}/SKILL.md`;
  const route = readFileSync(wrapper, "utf8");
  assert(route.includes(`zaratustra_source: ${source}\n`));
  assert(
    route.includes(
      `zaratustra_source_sha256: ${hash(readFileSync(join(project, source)))}\n`,
    ),
  );
  assert.equal(
    resolve(dirname(wrapper), `../../../${source}`),
    join(project, source),
  );
}
assert.match(
  readFileSync(
    join(project, ".agents/skills/synthetic-summary/SKILL.md"),
    "utf8",
  ),
  /Activity "synthetic-activity"/,
);
assert(portable.skills.some((skill) => skill.name === "owner-tool"));
assert(portable.skills.some((skill) => skill.name === "synthetic-global"));

const legacy = join(base, "legacy");
const legacyHome = join(base, "legacy-home");
const legacyAgent = join(base, "legacy-agent");
for (const path of [join(legacy, ".git"), legacyHome, legacyAgent])
  mkdirSync(path, { recursive: true });
nativeInstall(installedPackage, legacy, legacyHome, legacyAgent);
const standalone = probe(legacy, legacyHome, legacyAgent, "legacy");
clean(standalone);
assert.equal(standalone.skills.length, 4);
for (const name of productNames)
  assert.equal(
    resolve(standalone.skills.find((skill) => skill.name === name).filePath),
    join(installedPackage, "skills", name, "SKILL.md"),
  );

const ownerShadow = join(project, ".pi/skills/owner-shadow/SKILL.md");
syntheticSkill(ownerShadow, "zaratustra-work");
const genuineConflict = probe(
  project,
  syntheticHome,
  agentDir,
  "owner-conflict",
);
assert.deepEqual(genuineConflict.extension_errors, []);
assert.deepEqual(genuineConflict.extension_warnings, []);
assert.deepEqual(genuineConflict.prompt_diagnostics, []);
assert.deepEqual(genuineConflict.theme_diagnostics, []);
assert.equal(genuineConflict.skill_diagnostics.length, 1);
assert.equal(genuineConflict.skill_diagnostics[0].type, "collision");
assert.equal(
  genuineConflict.skill_diagnostics[0].collision.name,
  "zaratustra-work",
);
assert.equal(
  resolve(genuineConflict.skill_diagnostics[0].collision.winnerPath),
  ownerShadow,
);
assert.equal(
  resolve(genuineConflict.skill_diagnostics[0].collision.loserPath),
  join(project, ".agents/skills/zaratustra-work/SKILL.md"),
);
// The production-only consumer above stays Pi-free. This second consumer tests
// the shipped default installer with a real hoisted, import-only-exported peer.
const peerConsumer = join(base, "peer-consumer");
mkdirSync(peerConsumer);
npm([
  "install",
  "--prefix",
  peerConsumer,
  tarball,
  "@earendil-works/pi-coding-agent@1.4.0",
  "typebox@1.3.27",
  "--ignore-scripts",
  "--omit=dev",
  "--omit=optional",
  "--no-audit",
  "--no-fund",
]);
const peerPackage = join(peerConsumer, "node_modules/zaratustra");
const peerSDK = join(
  peerConsumer,
  "node_modules/@earendil-works/pi-coding-agent",
);
assert.deepEqual(getWorkspaceProduct(peerPackage), product);
assert.equal(
  JSON.parse(readFileSync(join(peerSDK, "package.json"), "utf8")).version,
  "1.4.0",
);
const peerProject = join(base, "default-installer-project");
const peerHome = join(base, "default-installer-home");
const peerAgent = join(base, "default-installer-agent");
for (const path of [peerHome, peerAgent]) mkdirSync(path);
execFileSync(
  process.execPath,
  [
    join(peerPackage, "dist/cli/index.js"),
    "workspace",
    "init",
    "--path",
    peerProject,
  ],
  { cwd: peerConsumer, env, encoding: "utf8", windowsHide: true },
);
mkdirSync(join(peerProject, ".git"));
const defaultInstaller = probe(
  peerProject,
  peerHome,
  peerAgent,
  "default-installer",
  peerSDK,
  peerPackage,
  "",
);
clean(defaultInstaller);
assert.equal(defaultInstaller.sdk_version, "1.4.0");
assert.equal(defaultInstaller.default_attachment.state, "pending_native_trust");
assert.equal(defaultInstaller.skills.length, 4);
assert(
  defaultInstaller.extensions.some(
    (extension) =>
      resolve(extension.path) === join(peerPackage, "src/extension/index.ts") &&
      extension.tools.includes("zara_map"),
  ),
);
for (const name of productNames)
  assert.equal(
    resolve(
      defaultInstaller.skills.find((skill) => skill.name === name).filePath,
    ),
    join(peerProject, ".agents/skills", name, "SKILL.md"),
  );
let managed;
if (values.managed) {
  // The real Windows npm shim is alongside node_modules in the selected prefix.
  const prefix = resolve(sdkRoot, "../../..");
  assert(
    existsSync(join(prefix, "pi.cmd")),
    "Use the installed Pi npm prefix for --managed",
  );
  const managedProject = join(base, "managed");
  const managedHome = join(base, "managed-home");
  const managedAgent = join(base, "managed-agent");
  for (const path of [managedHome, managedAgent]) mkdirSync(path);
  new WorkspaceInstaller(managedProject, {
    packageRoot: installedPackage,
  }).initialize();
  mkdirSync(join(managedProject, ".git"));
  const startup = probe(
    managedProject,
    managedHome,
    managedAgent,
    "path-installer",
    sdkRoot,
    installedPackage,
    prefix,
  );
  clean(startup);
  assert.equal(startup.default_attachment.state, "pending_native_trust");
  assert.equal(startup.skills.length, 4);
  const managedReport = join(base, "managed.json");
  execFileSync(
    process.execPath,
    [
      join(packageRoot, "scripts/pi-managed-probe.mjs"),
      sdkRoot,
      managedProject,
      managedAgent,
      managedReport,
    ],
    {
      cwd: base,
      env: isolatedEnvironment(managedHome, managedAgent),
      encoding: "utf8",
      windowsHide: true,
    },
  );
  managed = JSON.parse(readFileSync(managedReport, "utf8"));
}
const result = {
  base,
  installedPackage,
  tarball,
  tarball_sha256: hash(readFileSync(tarball)),
  product,
  root_package_lock_absent: true,
  retained_dependency_lock_exact: true,
  optional_peers_absent: true,
  qualification_scope: managed
    ? "startup-discovery-and-managed-scenarios"
    : "startup-discovery-only",
  sdk_version: sdkInfo.version,
  native_extension_errors: portable.extension_errors.length,
  native_extension_warnings: portable.extension_warnings.length,
  native_skill_diagnostics: portable.skill_diagnostics.length,
  native_prompt_diagnostics: portable.prompt_diagnostics.length,
  native_theme_diagnostics: portable.theme_diagnostics.length,
  product_skills_loaded_once: true,
  common_codex_pi_routes: true,
  scoped_personal_skill_preserved: true,
  unrelated_project_and_user_skills_preserved: true,
  legacy_package_skills: standalone.skills.length,
  genuine_owner_collision_reported: true,
  default_native_attach_peer_present: true,
  default_native_attach_sdk_version: defaultInstaller.sdk_version,
  default_native_attach_settings_filtered: true,
  default_native_attach_diagnostics: 0,
  zara_map_registered: true,
  model_calls: 0,
  network_calls: portable.network_calls,
  native_project_trust: "explicit-synthetic-sdk-setup",
  ...(managed ? { managed } : {}),
};
writeFileSync(
  join(base, "result.json"),
  JSON.stringify(result, null, 2) + "\n",
);
mkdirSync(join(packageRoot, "_scratch"), { recursive: true });
writeFileSync(
  join(packageRoot, "_scratch/packaged-extension-smoke.json"),
  JSON.stringify(result, null, 2) + "\n",
);
console.log(JSON.stringify(result));

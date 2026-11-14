// Native startup discovery only. The caller supplies an isolated synthetic home.
import assert from "node:assert/strict";
import childProcess from "node:child_process";
import { existsSync, readFileSync, realpathSync, writeFileSync } from "node:fs";
import { syncBuiltinESMExports } from "node:module";
import { homedir } from "node:os";
import { join, resolve } from "node:path";
import { pathToFileURL } from "node:url";

const [
  sdkArgument,
  projectArgument,
  agentArgument,
  homeArgument,
  outputArgument,
  defaultAttachPackageArgument,
] = process.argv.slice(2);
const sdkRoot = resolve(sdkArgument);
const sdkInfo = JSON.parse(readFileSync(join(sdkRoot, "package.json"), "utf8"));
const project = resolve(projectArgument);
const agentDir = resolve(agentArgument);
const expectedHome = resolve(homeArgument);
assert.equal(
  resolve(homedir()),
  expectedHome,
  "Synthetic home is not isolated",
);
assert(
  !process.env.HOME || resolve(process.env.HOME) === expectedHome,
  "Inherited HOME would expose unrelated skill sources",
);
assert.equal(resolve(process.env.PI_CODING_AGENT_DIR), agentDir);
let networkCalls = 0;
globalThis.fetch = async () => {
  networkCalls++;
  throw new Error("Network is disabled for startup discovery qualification.");
};
let defaultAttachment;
if (defaultAttachPackageArgument) {
  const packageRoot = resolve(defaultAttachPackageArgument);
  const nativeInvocations = [];
  const spawnSync = childProcess.spawnSync;
  childProcess.spawnSync = (file, args, options) => {
    if (file === process.execPath && args[1] === "install")
      nativeInvocations.push(args[0]);
    return spawnSync(file, args, options);
  };
  syncBuiltinESMExports();
  try {
    const { attachPi } = await import(
      pathToFileURL(join(packageRoot, "dist/workspace/index.js")).href
    );
    // Exercise the shipped resolver and forward its actual native invocation.
    defaultAttachment = attachPi(project, { packageRoot, source: packageRoot });
  } finally {
    childProcess.spawnSync = spawnSync;
    syncBuiltinESMExports();
  }
  assert.deepEqual(nativeInvocations, [
    realpathSync(join(sdkRoot, sdkInfo.bin.pi)),
  ]);
  assert.equal(defaultAttachment.state, "pending_native_trust");
  const settings = JSON.parse(
    readFileSync(join(project, ".pi/settings.json"), "utf8"),
  );
  assert.equal(settings.packages.length, 1);
  assert.deepEqual(settings.packages[0].skills, []);
}
const sdk = await import(pathToFileURL(join(sdkRoot, "dist/index.js")).href);
let modelRuntimeCreations = 0;
sdk.ModelRuntime.create = async () => {
  modelRuntimeCreations++;
  throw new Error("Model runtimes are disabled for startup discovery.");
};
const loader = new sdk.DefaultResourceLoader({
  cwd: project,
  agentDir,
  settingsManager: sdk.SettingsManager.create(project, agentDir, {
    projectTrusted: true,
  }),
  noContextFiles: true,
});
await loader.reload();
const extensions = loader.getExtensions();
const skills = loader.getSkills();
const report = {
  qualification_scope: "startup-discovery-only",
  sdk_version: sdkInfo.version,
  extensions: extensions.extensions.map((extension) => ({
    path: extension.path,
    tools: [...extension.tools.keys()],
  })),
  extension_errors: extensions.errors,
  extension_warnings: extensions.warnings ?? [],
  skills: skills.skills.map((skill) => ({
    name: skill.name,
    filePath: skill.filePath,
    sourceInfo: skill.sourceInfo,
  })),
  skill_diagnostics: skills.diagnostics,
  prompt_diagnostics: loader.getPrompts().diagnostics,
  theme_diagnostics: loader.getThemes().diagnostics,
  managed_store_created: existsSync(join(project, ".local/memory")),
  model_calls: modelRuntimeCreations,
  network_calls: networkCalls,
  synthetic_context_only: true,
  default_attachment: defaultAttachment,
};
assert.equal(modelRuntimeCreations, 0);
assert.equal(networkCalls, 0);
assert.equal(report.managed_store_created, false);
writeFileSync(resolve(outputArgument), JSON.stringify(report, null, 2) + "\n");

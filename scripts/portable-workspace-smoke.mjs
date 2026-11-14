import assert from "node:assert/strict";
import { execFileSync } from "node:child_process";
import { randomUUID } from "node:crypto";
import {
  lstatSync,
  mkdirSync,
  mkdtempSync,
  readFileSync,
  writeFileSync,
} from "node:fs";
import { tmpdir } from "node:os";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import {
  createAgentSession,
  DefaultResourceLoader,
  ModelRuntime,
  SessionManager,
  SettingsManager,
} from "@earendil-works/pi-coding-agent";

const packageRoot = fileURLToPath(new URL("..", import.meta.url));
const statePath = join(packageRoot, "_scratch/portable-workspace-smoke.json");
const skillPath = "skills/personal/synthetic-health-summary/SKILL.md";
const source = "2026-11-01 | 20 minutes\n2026-11-02 | 25 minutes\n";

function save(state) {
  mkdirSync(dirname(statePath), { recursive: true });
  writeFileSync(statePath, JSON.stringify(state, null, 2) + "\n");
}

function cli(...arguments_) {
  return JSON.parse(
    execFileSync(
      process.execPath,
      [join(packageRoot, "dist/cli/index.js"), ...arguments_],
      { cwd: packageRoot, encoding: "utf8", windowsHide: true },
    ),
  );
}

function isolatedEnvironment(agentDir) {
  process.env.PI_CODING_AGENT_DIR = agentDir;
  for (const key of Object.keys(process.env))
    if (key.startsWith("ZARATUSTRA_")) delete process.env[key];
  process.env.ZARATUSTRA_TEST_CONTROLLER = "portable-native-walkthrough";
}

function prepare() {
  const parent = mkdtempSync(join(tmpdir(), "zara-portable-native-"));
  const project = join(parent, "workspace");
  const agentDir = join(parent, "pi-agent");
  mkdirSync(agentDir);
  isolatedEnvironment(agentDir);
  cli("workspace", "init", "--path", project);
  mkdirSync(join(project, "activities/synthetic-health"), { recursive: true });
  mkdirSync(join(project, dirname(skillPath)), { recursive: true });
  writeFileSync(
    join(project, "activities/synthetic-health/AGENTS.md"),
    "# Synthetic Health\n\nUse the personal synthetic-health-summary skill.\n",
  );
  writeFileSync(join(project, "activities/synthetic-health/notes.md"), source);
  writeFileSync(
    join(project, skillPath),
    "---\nname: synthetic-health-summary\ndescription: Summarize isolated dated notes.\n---\n\n" +
      "# Synthetic Health summary\n\n" +
      "Read activities/synthetic-health/notes.md. Preserve both dates.\n" +
      "Write activities/synthetic-health/summary.md with the two observations,\n" +
      "their arithmetic mean in minutes and the source path. Label the fixture synthetic.\n",
  );
  writeFileSync(
    join(project, dirname(skillPath), "bundle.json"),
    JSON.stringify({
      format: 1,
      skill_id: randomUUID(),
      name: "Synthetic Health summary",
      entry: "SKILL.md",
    }),
  );
  const manifestPath = join(project, "zaratustra.json");
  const manifest = JSON.parse(readFileSync(manifestPath, "utf8"));
  manifest.activities.push({
    key: "synthetic-health",
    label: "Synthetic Health",
    guidance_path: "activities/synthetic-health/AGENTS.md",
  });
  writeFileSync(manifestPath, JSON.stringify(manifest, null, 2) + "\n");
  const state = {
    parent,
    project,
    agentDir,
    installation_id: manifest.installation_id,
  };
  save(state);
  console.log(
    JSON.stringify(
      {
        ...state,
        next_step:
          "Read root guidance and the Activity skill, then write its ordinary summary before running verify.",
      },
      null,
      2,
    ),
  );
}

async function verify() {
  const state = JSON.parse(readFileSync(statePath, "utf8"));
  const parent = resolve(state.parent);
  assert.equal(dirname(parent), resolve(tmpdir()));
  assert.ok(parent.split(/[\\/]/).at(-1).startsWith("zara-portable-native-"));
  assert.equal(state.project, join(parent, "workspace"));
  assert.equal(state.agentDir, join(parent, "pi-agent"));
  for (const path of [parent, state.project, state.agentDir])
    assert.equal(lstatSync(path).isSymbolicLink(), false);
  isolatedEnvironment(state.agentDir);
  const notes = join(state.project, "activities/synthetic-health/notes.md");
  assert.equal(readFileSync(notes, "utf8"), source);
  const summary = readFileSync(
    join(state.project, "activities/synthetic-health/summary.md"),
    "utf8",
  );
  for (const expected of ["2026-11-01", "2026-11-02", "22.5", "notes.md"])
    assert.ok(
      summary.includes(expected),
      `The ordinary summary must contain ${expected}.`,
    );
  if (!state.attachment) {
    state.attachment = cli(
      "adapter",
      "attach",
      "pi",
      "--path",
      state.project,
      "--source",
      packageRoot,
    );
    save(state);
  }
  assert.equal(state.attachment.state, "pending_native_trust");

  globalThis.fetch = async () => {
    throw new Error("Network is disabled for this qualification.");
  };
  const settingsManager = SettingsManager.create(
    state.project,
    state.agentDir,
    { projectTrusted: true },
  );
  const resourceLoader = new DefaultResourceLoader({
    cwd: state.project,
    agentDir: state.agentDir,
    settingsManager,
    noContextFiles: true,
    agentsFilesOverride: () => ({
      agentsFiles: [
        {
          path: join(state.project, "AGENTS.md"),
          content: readFileSync(join(state.project, "AGENTS.md"), "utf8"),
        },
      ],
    }),
  });
  await resourceLoader.reload();
  const modelRuntime = await ModelRuntime.create({
    authPath: join(state.agentDir, "auth.json"),
    modelsPath: null,
    modelsStorePath: join(state.agentDir, "models-store.json"),
    allowModelNetwork: false,
    refreshOnCreate: false,
  });
  let modelCalls = 0;
  for (const name of [
    "stream",
    "streamSimple",
    "streamDeferred",
    "images",
    "classify",
  ])
    modelRuntime[name] = () => {
      modelCalls++;
      throw new Error("Model calls are disabled.");
    };
  const model = {
    id: "synthetic-no-dispatch",
    name: "Synthetic no-dispatch",
    provider: "synthetic",
    api: "openai-completions",
    baseUrl: "http://127.0.0.1:9",
    reasoning: false,
    input: ["text"],
    contextWindow: 8192,
    maxTokens: 512,
    cost: { input: 0, output: 0, cacheRead: 0, cacheWrite: 0 },
  };
  const { session, extensionsResult } = await createAgentSession({
    cwd: state.project,
    agentDir: state.agentDir,
    settingsManager,
    resourceLoader,
    modelRuntime,
    model,
    thinkingLevel: "off",
    tools: ["zara_map", "read"],
    sessionManager: SessionManager.inMemory(state.project),
  });
  try {
    assert.equal(
      extensionsResult.errors.length,
      0,
      JSON.stringify(extensionsResult.errors),
    );
    await session.bindExtensions({ mode: "sdk" });
    const map = session.agent.state.tools.find(
      (tool) => tool.name === "zara_map",
    );
    const read = session.agent.state.tools.find((tool) => tool.name === "read");
    assert.ok(
      map && read,
      "Native Pi must load Zaratustra and the ordinary reader.",
    );
    const mapped = await map.execute("synthetic-map", {});
    assert.equal(mapped.details.ok, true, JSON.stringify(mapped.details));
    assert.equal(mapped.details.schema_version, 11);
    const skill = await read.execute("synthetic-read", {
      path: join(state.project, skillPath),
    });
    assert.ok(
      skill.content.some(
        (item) =>
          item.type === "text" &&
          item.text.includes("Synthetic Health summary"),
      ),
    );
    const activity = await read.execute("synthetic-activity", {
      path: join(state.project, "activities/synthetic-health/AGENTS.md"),
    });
    assert.ok(
      activity.content.some(
        (item) =>
          item.type === "text" &&
          item.text.includes("synthetic-health-summary"),
      ),
    );
    assert.equal(readFileSync(notes, "utf8"), source);
    assert.equal(modelCalls, 0);
    state.verified = {
      schema_version: mapped.details.schema_version,
      ordinary_summary_preserved: true,
      same_skill_path: skillPath,
      same_activity_path: "activities/synthetic-health/AGENTS.md",
      model_calls: modelCalls,
      native_project_trust: "explicit-synthetic-sdk-setup",
    };
    save(state);
    console.log(JSON.stringify(state, null, 2));
  } finally {
    session.dispose();
  }
}

if (process.argv[2] === "prepare") prepare();
else if (process.argv[2] === "verify") await verify();
else
  throw new Error(
    "Use prepare, follow the generated file workflow, then verify.",
  );

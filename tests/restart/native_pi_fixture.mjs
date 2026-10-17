// Actual installed Pi SDK; only the provider and Python bootstrap are controlled fixtures.
import { pathToFileURL } from "node:url";
import { join } from "node:path";
import { readFile, writeFile, mkdir, copyFile } from "node:fs/promises";
const [sdkPath, source, root, python, endpoint, mode] = process.argv.slice(2);
const sdk = await import(pathToFileURL(join(sdkPath, "dist/index.js")).href);
const agentDir = join(root, "agent");
const extensionDir = join(root, "extension");
await mkdir(agentDir, {recursive: true});
await mkdir(extensionDir, {recursive: true});
await copyFile(join(source, "pi-package/extension.ts"), join(extensionDir, "extension.ts"));
// Explicit fixture seam: production extension is unchanged; bootstrap installation is separately tested.
const bootstrapSource = await readFile(join(source, "pi-package/bootstrap.mjs"), "utf8");
await writeFile(join(extensionDir, "production-bootstrap.mjs"), bootstrapSource);
await writeFile(join(extensionDir, "bootstrap.mjs"), `export {run, dataRoot, home, selectDataRoot} from './production-bootstrap.mjs';\nexport async function bootstrap(){return ${JSON.stringify(python)}}\n`);
await writeFile(join(agentDir, "models.json"), JSON.stringify({providers: {fictional: {
  baseUrl: endpoint, api: "openai-completions", apiKey: "fictional-localhost-only",
  models: [{id: "scripted-transport", contextWindow: 32000, maxTokens: 1000, reasoning: false,
    input: ["text"], cost: {input: 0, output: 0, cacheRead: 0, cacheWrite: 0}}]
}}}));
const runtime = await sdk.ModelRuntime.create({authPath: join(agentDir,"auth.json"), modelsPath: join(agentDir,"models.json")});
const settings = sdk.SettingsManager.inMemory({compaction: {enabled: false}, retry: {enabled: false}});
const events = [];
async function open() {
  const loader = new sdk.DefaultResourceLoader({cwd: root, agentDir, settingsManager: settings,
    noSkills: true, noPromptTemplates: true, noThemes: true, noContextFiles: true,
    additionalExtensionPaths: [join(extensionDir,"extension.ts")]});
  await loader.reload();
  const loaded = loader.getExtensions();
  if (loaded.errors.length) throw new Error(JSON.stringify(loaded.errors));
  const {session} = await sdk.createAgentSession({cwd: root, agentDir, resourceLoader: loader,
    modelRuntime: runtime, model: runtime.getModel("fictional", "scripted-transport"),
    thinkingLevel: "off", settingsManager: settings,
    tools: ["read","write","bash","zara_context","zara_read","zara_route","zara_change","zara_result"],
    sessionManager: sdk.SessionManager.inMemory(root)});
  session.subscribe(e => { if (["tool_execution_end","agent_settled"].includes(e.type)) events.push(e); });
  session.subscribe(e => {
    if (mode === "aborted" && e.type === "tool_execution_start" && e.toolName === "bash") {
      setTimeout(() => void session.abort(), 300);
    }
  });
  await session.bindExtensions({onError: e => events.push({extensionError: e})});
  session.setActiveToolsByName(["read", "write", "bash", "zara_context", "zara_read", "zara_route", "zara_change", "zara_result"]);
  return session;
}
const first = await open();
await first.prompt("/zaratustra");
await first.prompt("Create and verify the fictional transport artifact.");
const firstMessages = first.messages;
first.dispose();
const second = await open();
await second.prompt("/reopen");
const reopened = [...second.messages];
let reviewMessages = [];
let reviewReopened = [];
let reviewAcceptance = null;
if (mode === "review") {
  await second.prompt("/zara-review-start fictional");
  await second.waitForIdle();
  reviewMessages = [...second.messages];
}
second.dispose();
if (mode === "review") {
  const third = await open();
  await third.prompt("/reopen");
  reviewReopened = [...third.messages];
  const bridge = await import(pathToFileURL(join(extensionDir, "bootstrap.mjs")).href);
  reviewAcceptance = JSON.parse(await bridge.run(python, ["-m", "zaratustra_app.pi_host"], JSON.stringify({
    data_root: await bridge.dataRoot(), session_id: third.sessionManager.getSessionId(),
    command: "tool", name: "read", call_id: "fictional-acceptance-read",
    payload: {operation: "read_page", arguments: {table: "acceptance"}}
  })));
  third.dispose();
}
console.log(JSON.stringify({events, firstMessages, reopened, reviewMessages, reviewReopened, reviewAcceptance, provenance: {
  installedPi: sdk.VERSION, bootstrap: "explicit-source-interpreter-fixture",
  provider: "fictional-localhost-script", semanticEvidence: false
}}));

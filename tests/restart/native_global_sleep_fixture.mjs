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
const events = [], notifications=[], selections=[];
const tools=['read','write','bash','zara_context','zara_read','zara_route','zara_change','zara_result'];
async function factory({sessionManager,sessionStartEvent}){
 const services=await sdk.createAgentSessionServices({cwd:root,agentDir,settingsManager:settings,modelRuntime:runtime,resourceLoaderOptions:{noSkills:true,noPromptTemplates:true,noThemes:true,noContextFiles:true,additionalExtensionPaths:[join(extensionDir,'extension.ts')]}});
 const errors=services.resourceLoader.getExtensions().errors;if(errors.length)throw new Error(JSON.stringify(errors));
 const result=await sdk.createAgentSessionFromServices({services,sessionManager,sessionStartEvent,model:runtime.getModel('fictional','scripted-transport'),thinkingLevel:'off',tools});
 return {...result,services,diagnostics:services.diagnostics};
}
const host=await sdk.createAgentSessionRuntime(factory,{cwd:root,agentDir,sessionManager:sdk.SessionManager.inMemory(root)});
async function bind(session){
 session.subscribe(event=>{if(['tool_execution_end','agent_settled'].includes(event.type))events.push(event);});
 await session.bindExtensions({uiContext:{notify:(...args)=>notifications.push(args),select:async(...args)=>{selections.push(args);throw new Error('Unexpected Activity picker');}},onError:e=>events.push({extensionError:e}),commandContextActions:{waitForIdle:()=>session.waitForIdle(),newSession:options=>host.newSession(options)}});
 session.setActiveToolsByName(tools);
}
host.setRebindSession(bind);await bind(host.session);
const first=host.session;
await first.prompt('/zaratustra');
const bridge=await import(pathToFileURL(join(extensionDir,'bootstrap.mjs')).href);
const dataRoot=await bridge.dataRoot();
const sessionId=first.sessionManager.getSessionId();
async function request(body){return JSON.parse(await bridge.run(python,['-m','zaratustra_app.pi_host'],JSON.stringify({data_root:dataRoot,session_id:sessionId,...body})));}
if(mode!=='empty'){
 await bridge.run(python,['-c',`from pathlib import Path
from zaratustra_core import Core
import sys
root=Path(sys.argv[1]);core=Core(root);owner=core.connect((root/'owner.credential').read_text(encoding='utf-8'))
owner.call('apply_changes',{'changes':[{'id':'fictional','kind':'activity','key':'fictional','body':'Fictional Activity'}]},'seed-activity',expected_heads={'fictional':0})`,dataRoot],'');
}
if(mode==='unknown')await request({command:'input',event_id:'pending',text:'Unresolved prior request'});
const before=await request({command:'context'});
await first.prompt(mode==='targeted'?'/zara-sleep fictional':mode==='invalid'?'/zara-sleep absent':'/zara-sleep');
await first.waitForIdle();
const context=await request({command:'context'}),delivery=await request({command:'delivery'});
const results=await request({command:'tool',name:'read',call_id:'inspect-sleep-results',payload:{operation:'read_page',arguments:{table:'results',limit:100}}});
console.log(JSON.stringify({mode,notifications,selections,before,context,delivery,results,events,messages:first.messages,provenance:{pi:sdk.VERSION,fictionalProvider:true,semanticEvidence:false}}));
await host.dispose();

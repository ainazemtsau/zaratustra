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
 await session.bindExtensions({uiContext:{confirm:async()=>true,notify:(...args)=>notifications.push(args),select:async(...args)=>{selections.push(args);throw new Error('Unexpected Activity picker');}},onError:e=>events.push({extensionError:e}),commandContextActions:{waitForIdle:()=>session.waitForIdle(),newSession:options=>host.newSession(options)}});
 session.setActiveToolsByName(tools);
}
host.setRebindSession(bind);await bind(host.session);
const first=host.session;
await first.prompt('/zaratustra');
const bridge=await import(pathToFileURL(join(extensionDir,'bootstrap.mjs')).href);
const dataRoot=await bridge.dataRoot();
const sessionId=first.sessionManager.getSessionId();
async function request(body){return JSON.parse(await bridge.run(python,['-m','zaratustra_app.pi_host'],JSON.stringify({data_root:dataRoot,session_id:sessionId,...body})));}
const stages=[];
async function snapshot(label){const value=await request({command:'context'});stages.push({label,value});await writeFile(join(root,'stages.json'),JSON.stringify(stages));return value;}
async function sleep(){await first.prompt('/zara-sleep');await first.waitForIdle();}
await sleep();
await snapshot('first');
if(mode==='child'){
 await sleep();await snapshot('child');
}
const before=stages[stages.length-1].value;
if(mode==='unknown'){
 await sleep();await snapshot('refused');
}else{
 if(mode==='window'){
  const code=`import json,sys
from pathlib import Path
from zaratustra_core import Core
root=Path(sys.argv[1]);mapping=json.loads(sys.argv[2]);core=Core(root);owner=core.connect((root/'owner.credential').read_text(encoding='utf-8'))
works=owner.call('read_page',{'table':'works','work':mapping['work'],'limit':100},'window-work')['rows']
work=works[0]
owner.call('control_work',{'work_id':work['id'],'revision':work['revision'],'action':'cancel','reason':'Fictional explicit owner cancellation before mapping clear'},'window-cancel')`;
  await bridge.run(python,['-c',code,dataRoot,JSON.stringify(before.current)],'');
  await first.prompt('/reopen');await snapshot('reopened-cancelled');
 }else await first.prompt('/zara-cancel');
 await sleep();await snapshot('fresh');
 if(mode==='child'){await sleep();await snapshot('successor');}
}
const tables={};
for(const table of ['works','attempts','actions','results'])tables[table]=await request({command:'tool',name:'read',call_id:'inspect-'+table,payload:{operation:'read_page',arguments:{table,limit:100}}});
console.log(JSON.stringify({mode,notifications,selections,stages,tables,events,messages:first.messages,provenance:{pi:sdk.VERSION,fictionalProvider:true,semanticEvidence:false}}));
await host.dispose();

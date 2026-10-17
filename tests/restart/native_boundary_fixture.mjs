// Actual installed Pi runtime; source extension and explicit Python bootstrap seam.
import {pathToFileURL} from 'node:url';
import {join} from 'node:path';
import {readFile,writeFile,mkdir,copyFile} from 'node:fs/promises';
const [sdkPath,source,root,python,endpoint,scenario]=process.argv.slice(2);
const sdk=await import(pathToFileURL(join(sdkPath,'dist/index.js')).href);
const agentDir=join(root,'agent'),extensionDir=join(root,'extension');
await mkdir(root,{recursive:true});
await writeFile(join(root,'read-a.txt'),'Fictional A');await writeFile(join(root,'read-b.txt'),'Fictional B');
await mkdir(agentDir,{recursive:true});await mkdir(extensionDir,{recursive:true});
await copyFile(join(source,'extension.ts'),join(extensionDir,'extension.ts'));
await copyFile(join(source,'bootstrap.mjs'),join(extensionDir,'production-bootstrap.mjs'));
const shim="import {run as originalRun} from './production-bootstrap.mjs';\nexport {dataRoot,home} from './production-bootstrap.mjs';\nconst trace=[];let running=0,maxRunning=0,rejected=false;\nexport function transportTrace(){return {trace,maxRunning};}\nexport async function run(cmd,args,input){\n const packet=JSON.parse(input),kind=packet.value?.kind;\n const row={packet:JSON.parse(input),status:'started'};trace.push(row);\n running++;maxRunning=Math.max(maxRunning,running);\n try {\n  if(SCENARIO==='profile-failure' && packet.command==='verify-profile') return JSON.stringify({state:'error',text:'Fictional profile rejection'});\n  if(SCENARIO==='tool-block' && packet.command==='observation' && kind==='tool_call' && packet.value.event.toolName==='write') return JSON.stringify({state:'error',text:'Fictional observation rejection'});\n  let result;\n  if(SCENARIO.startsWith('parallel-') && packet.command==='observation' && kind==='tool_execution_end'){\n   const slow='import time\\nfrom zaratustra_app.native_session import NativeSession\\nfrom zaratustra_app.pi_host import main\\noriginal=NativeSession.observation\\ndef delayed(self,event,value):\\n time.sleep(0.6)\\n return original(self,event,value)\\nNativeSession.observation=delayed\\nmain()';\n   if(SCENARIO==='parallel-rejection' && !rejected && packet.value.event.toolCallId.startsWith('parallel-read-')){\n    rejected=true;\n    const mutation={...packet,command:'tool',name:'change',call_id:'fictional-rejected-mutation',payload:{changes:[{id:'native-host:forbidden',kind:'data',key:'native-host:forbidden',body:'denied'}],expected_heads:{'native-host:forbidden':0}}};\n    result=await originalRun(cmd,args,JSON.stringify(mutation));\n   }else result=await originalRun(cmd,['-c',slow],input);\n  }else result=await originalRun(cmd,args,input);\n  row.result=JSON.parse(result);return result;\n }finally{running--;row.status='ended';}\n}\nexport async function bootstrap(){return PYTHON;}\n";
await writeFile(join(extensionDir,'bootstrap.mjs'),shim.replaceAll('SCENARIO',JSON.stringify(scenario)).replace('PYTHON',JSON.stringify(python)));
await writeFile(join(agentDir,'models.json'),JSON.stringify({providers:{fictional:{baseUrl:endpoint,api:'openai-completions',apiKey:'fictional-localhost-only',models:[{id:'scripted-transport',contextWindow:32000,maxTokens:1000,reasoning:false,input:['text'],cost:{input:0,output:0,cacheRead:0,cacheWrite:0}}]}}}));
const modelRuntime=await sdk.ModelRuntime.create({authPath:join(agentDir,'auth.json'),modelsPath:join(agentDir,'models.json')});
const settings=sdk.SettingsManager.inMemory({compaction:{enabled:false},retry:{enabled:false}});
const events=[],notifications=[];let cancelPromise=null;
const tools=['read','write','bash','zara_context','zara_read','zara_route','zara_change','zara_result'];
async function factory({sessionManager,sessionStartEvent}){
 const services=await sdk.createAgentSessionServices({cwd:root,agentDir,settingsManager:settings,modelRuntime,resourceLoaderOptions:{noSkills:true,noPromptTemplates:true,noThemes:true,noContextFiles:true,additionalExtensionPaths:[join(extensionDir,'extension.ts')]}});
 const errors=services.resourceLoader.getExtensions().errors;
 if(errors.length)throw new Error(JSON.stringify(errors));
 const result=await sdk.createAgentSessionFromServices({services,sessionManager,sessionStartEvent,model:modelRuntime.getModel('fictional','scripted-transport'),thinkingLevel:'off',tools});
 return {...result,services,diagnostics:services.diagnostics};
}
const host=await sdk.createAgentSessionRuntime(factory,{cwd:root,agentDir,sessionManager:sdk.SessionManager.inMemory(root)});
async function bind(session){
 session.subscribe(event=>{
 if(scenario==='cancel-stream' && event.type==='message_update' && event.assistantMessageEvent?.type==='text_delta' && !cancelPromise){
  cancelPromise=Promise.resolve().then(()=>host.session.prompt('/zara-cancel'));
 }
if(['tool_execution_end','agent_settled'].includes(event.type))events.push({sessionId:session.sessionManager.getSessionId(),...event});});
 await session.bindExtensions({uiContext:{confirm:async()=>true,notify:(...args)=>notifications.push(args)},onError:e=>events.push({extensionError:e}),commandContextActions:{waitForIdle:()=>session.waitForIdle(),newSession:options=>host.newSession(options)}});
 session.setActiveToolsByName(tools);
}
host.setRebindSession(bind);await bind(host.session);
await host.session.prompt('/zaratustra');
const originalSession=host.session.sessionManager.getSessionId();
if(scenario==='command-failure') await host.session.prompt('/zara-review absent');
else await host.session.prompt('Build the fictional file in the retained Activity.');
await host.session.waitForIdle();
if(cancelPromise)await cancelPromise;
let afterFirst=[...host.session.messages];
if(scenario==='review-command'||scenario==='review-reopen'||scenario==='review-cancel-normal'){
 await host.session.prompt('/zara-review fictional');
 await host.session.waitForIdle();
}else if(scenario==='failed-input'){
 await host.session.prompt('A new fictional request while previous Work is unresolved.');
 await host.session.waitForIdle();
}
if(scenario==='review-cancel-normal'){
 await host.session.prompt('/zara-cancel');
 await host.session.prompt('A new ordinary fictional request after cancelling review.');
 await host.session.waitForIdle();
}
let reviewTools=null;
if(scenario==='review-command') reviewTools=host.session.getActiveToolNames();
const afterSecond=[...host.session.messages];
const finalSession=host.session.sessionManager.getSessionId();
const activeTools=host.session.getActiveToolNames();
const bridge=await import(pathToFileURL(join(extensionDir,'bootstrap.mjs')).href);
async function request(body){return JSON.parse(await bridge.run(python,['-m','zaratustra_app.pi_host'],JSON.stringify({data_root:await bridge.dataRoot(),session_id:finalSession,...body})));}
let reopenTools=null;
if(scenario==='review-reopen'){
 await host.newSession();
 await host.session.prompt('/reopen');
 reopenTools=host.session.getActiveToolNames();
 await request({command:'cancel'});
 await host.session.prompt('/zaratustra');
}
const context=await request({command:'context'});
const observations=await request({command:'tool',name:'read',call_id:'independent-inspection',payload:{operation:'read_page',arguments:{table:'observations',limit:100}}});
const messages=await request({command:'tool',name:'read',call_id:'independent-message-inspection',payload:{operation:'read_page',arguments:{table:'messages',limit:100}}});
const delivery=await request({command:'delivery'});
console.log(JSON.stringify({transport:bridge.transportTrace(),scenario,originalSession,finalSession,activeTools:host.session.getActiveToolNames(),reviewTools,reopenTools,events,afterFirst,afterSecond,context,observations,messages,delivery,provenance:{pi:sdk.VERSION,provider:'fictional-localhost-only',semanticEvidence:false,bootstrap:'source-interpreter seam',extensionSource:source}}));
await host.dispose();

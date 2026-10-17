// Actual installed Pi runtime; source extension and explicit Python bootstrap seam.
import {pathToFileURL} from 'node:url';
import {createHash} from 'node:crypto';
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
const shim="import {run as originalRun} from './production-bootstrap.mjs';\nexport {dataRoot,home} from './production-bootstrap.mjs';\nconst trace=[];let running=0,maxRunning=0,rejected=false;\nexport function transportTrace(){return {trace,maxRunning};}\nexport async function run(cmd,args,input){\n const packet=JSON.parse(input),kind=packet.value?.kind;\n const row={packet:JSON.parse(input),status:'started'};trace.push(row);\n running++;maxRunning=Math.max(maxRunning,running);\n try {\n  if(SCENARIO==='profile-failure' && packet.command==='verify-profile') return JSON.stringify({state:'error',text:'Fictional profile rejection'});\n  if(SCENARIO==='tool-block' && packet.command==='observation' && kind==='tool_call' && packet.value.event.toolName==='write') return JSON.stringify({state:'error',text:'Fictional observation rejection'});\n  if(packet.command==='tool' && packet.name==='read' && packet.payload?.operation==='read_history'){\n   if(SCENARIO==='read-revoked') return originalRun(cmd,['-c',\"from zaratustra_app.native_session import NativeSession\\nfrom zaratustra_app.pi_host import main\\noriginal=NativeSession.tool\\ndef revoked(self,name,call_id,payload):\\n if name == \\\"read\\\":\\n  token=self.core.grant(self.token,\\\"fictional-revoked-reader\\\",[\\\"read\\\"],origin=\\\"host\\\")\\n  client=self.core.connect(token)\\n  self.core.revoke(self.token,\\\"fictional-revoked-reader\\\")\\n  return client.call(payload[\\\"operation\\\"],payload[\\\"arguments\\\"],\\\"revoked-read-command\\\")\\n return original(self,name,call_id,payload)\\nNativeSession.tool=revoked\\nmain()\\n\"],input);\n   if(SCENARIO==='read-transport') return originalRun(cmd,['-c','import sys;sys.exit(23)'],input);\n   if(SCENARIO==='read-payload' || SCENARIO==='read-wire') return originalRun(cmd,['-c',\"from zaratustra_app.native_session import NativeSession\\nfrom zaratustra_app.pi_host import main\\nfrom zaratustra_core import CoreError\\noriginal=NativeSession.tool\\ndef failed(self,name,call_id,payload):\\n if name == \\\"read\\\": raise CoreError(\\\"invalid_request\\\", \\\"ERROR_FIELD\\\")\\n return original(self,name,call_id,payload)\\nNativeSession.tool=failed\\nmain()\\n\".replace('ERROR_FIELD',SCENARIO==='read-payload'?'payload':'wire')],input);\n  }\n  if(['history-large','page-large','exact-large'].includes(SCENARIO) && packet.command==='tool' && packet.name==='read' && !rejected){rejected=true;await originalRun(cmd,['-c',\"import json,sys\\nfrom pathlib import Path\\nfrom zaratustra_core import Core\\np=json.loads(sys.argv[1]); root=Path(p[\\\"data_root\\\"]); core=Core(root)\\nowner=core.connect((root/\\\"owner.credential\\\").read_text(encoding=\\\"utf-8\\\"))\\nowner.call(\\\"apply_changes\\\",{\\\"changes\\\":[{\\\"id\\\":\\\"tiny-history\\\",\\\"kind\\\":\\\"data\\\",\\\"key\\\":\\\"tiny-history\\\",\\\"scope\\\":\\\"fictional\\\",\\\"body\\\":\\\"Exact tiny source\\\"},{\\\"id\\\":\\\"huge-history\\\",\\\"kind\\\":\\\"data\\\",\\\"key\\\":\\\"huge-history\\\",\\\"scope\\\":\\\"fictional\\\",\\\"body\\\":\\\"x\\\"*150000}]},\\\"seed-large-history\\\",expected_heads={\\\"tiny-history\\\":0,\\\"huge-history\\\":0})\\n\\nimport base64\\nowner.call(\\\"ingest_message\\\",{\\\"conversation\\\":\\\"fictional-large-page\\\",\\\"event_id\\\":\\\"large-message\\\",\\\"raw_base64\\\":base64.b64encode(b\\\"x\\\"*150000).decode()},\\\"seed-large-message\\\")\\n\",input],'');}\n  let result;\n  if(SCENARIO.startsWith('parallel-') && packet.command==='observation' && kind==='tool_execution_end'){\n   const slow='import time\\nfrom zaratustra_app.native_session import NativeSession\\nfrom zaratustra_app.pi_host import main\\noriginal=NativeSession.observation\\ndef delayed(self,event,value):\\n time.sleep(0.6)\\n return original(self,event,value)\\nNativeSession.observation=delayed\\nmain()';\n   if(SCENARIO==='parallel-rejection' && !rejected && packet.value.event.toolCallId.startsWith('parallel-read-')){\n    rejected=true;\n    const mutation={...packet,command:'tool',name:'change',call_id:'fictional-rejected-mutation',payload:{changes:[{id:'native-host:forbidden',kind:'data',key:'native-host:forbidden',body:'denied'}],expected_heads:{'native-host:forbidden':0}}};\n    result=await originalRun(cmd,args,JSON.stringify(mutation));\n   }else result=await originalRun(cmd,['-c',slow],input);\n  }else result=await originalRun(cmd,args,input);\n  if(SCENARIO==='codec-readable' && packet.command==='tool' && packet.name==='route'){await originalRun(cmd,['-c',\"import base64,json,sys\\nfrom pathlib import Path\\nfrom zaratustra_core import Core\\nfrom zaratustra_app.native_session import NativeSession\\npacket=json.loads(sys.argv[1]);root=Path(packet[\\\"data_root\\\"]);core=Core(root)\\nsession=NativeSession(core,(root/\\\"owner.credential\\\").read_text(encoding=\\\"utf-8\\\"),packet[\\\"session_id\\\"])\\n_,mapping=session._load()\\nsession.coordinator.client.call(\\\"observe_attempt\\\",{\\\"attempt_id\\\":mapping[\\\"attempt\\\"],\\\"event_id\\\":\\\"codec-readable-fact\\\",\\\"kind\\\":\\\"progress\\\",\\\"raw_base64\\\":base64.b64encode(\\\"CODEC_FACT_7F4A: \\u0416\\ud83d\\ude42 source data only\\\".encode(\\\"utf-8\\\")).decode()},\\\"codec-readable-fact\\\")\\n\",input],'');}\n  if(SCENARIO==='codec-unfit' && packet.command==='verify-profile'){const value=JSON.parse(result);if(value.current?.mode==='sleep'){value.fixture_padding='x'.repeat(1048576);result=JSON.stringify(value);}}\n  row.result=JSON.parse(result);return result;\n }finally{running--;row.status='ended';}\n}\nexport async function bootstrap(){return PYTHON;}\n";
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
if(['codec-fallback','codec-unfit'].includes(scenario)){
 const seedBridge=await import(pathToFileURL(join(extensionDir,'production-bootstrap.mjs')).href);
 const seedCode=`import base64,json,sys
from pathlib import Path
from zaratustra_core import Core
root=Path(sys.argv[1]);core=Core(root);owner=core.connect((root/'owner.credential').read_text(encoding='utf-8'))
owner.call('apply_changes',{'changes':[{'id':'fictional','kind':'activity','key':'fictional','body':'Fictional codec boundary'}]},'seed-codec-activity',expected_heads={'fictional':0})
owner.call('ingest_message',{'conversation':'codec-fixture','scope':'fictional','event_id':'codec-expansion','raw_base64':base64.b64encode(b'FALLBACK_SOURCE_9C2D:'+bytes(262144)).decode()},'seed-codec-message')`;
 await seedBridge.run(python,['-c',seedCode,await seedBridge.dataRoot()],'');
 await host.session.prompt('/zara-sleep fictional');
}else if(scenario==='command-failure') await host.session.prompt('/zara-review absent');
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
if(scenario==='codec-fallback'){await host.session.prompt('/reopen');}
if(scenario==='codec-readable'){await host.session.prompt('/zara-sleep fictional');await host.session.waitForIdle();await host.session.prompt('/reopen');}
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
console.log(JSON.stringify({transport:bridge.transportTrace(),notifications,scenario,originalSession,finalSession,activeTools:host.session.getActiveToolNames(),reviewTools,reopenTools,events,afterFirst,afterSecond,context,observations,messages,delivery,provenance:{pi:sdk.VERSION,provider:'fictional-localhost-only',semanticEvidence:false,bootstrap:'source-interpreter seam',extensionSource:source,extensionSHA256:createHash('sha256').update(await readFile(join(extensionDir,'extension.ts'))).digest('hex')}}));
await host.dispose();

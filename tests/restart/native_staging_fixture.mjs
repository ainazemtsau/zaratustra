// Installed Pi transport with fictional inference and an explicit source-Python bootstrap seam.
import {pathToFileURL} from 'node:url';
import {createHash} from 'node:crypto';
import {join} from 'node:path';
import {readFile,writeFile,mkdir,copyFile} from 'node:fs/promises';
const [sdkPath,source,root,python,endpoint]=process.argv.slice(2);
const sdk=await import(pathToFileURL(join(sdkPath,'dist/index.js')).href);
const agentDir=join(root,'agent'),extensionDir=join(root,'extension');
await mkdir(agentDir,{recursive:true});await mkdir(extensionDir,{recursive:true});
await copyFile(join(source,'extension.ts'),join(extensionDir,'extension.ts'));
await copyFile(join(source,'bootstrap.mjs'),join(extensionDir,'production-bootstrap.mjs'));
await writeFile(join(extensionDir,'bootstrap.mjs'), `import {run as actualRun} from './production-bootstrap.mjs';
export {dataRoot,home,selectDataRoot} from './production-bootstrap.mjs';
const trace=[];export function receipts(){return trace;}
export async function run(cmd,args,input){const packet=JSON.parse(input);const result=JSON.parse(await actualRun(cmd,args,input));trace.push({packet,result});return JSON.stringify(result);}
export async function bootstrap(){return ${JSON.stringify(python)};}`);
await writeFile(join(agentDir,'models.json'),JSON.stringify({providers:{fictional:{baseUrl:endpoint,api:'openai-completions',apiKey:'fictional-localhost-only',models:[{id:'scripted-transport',contextWindow:32000,maxTokens:1000,reasoning:false,input:['text'],cost:{input:0,output:0,cacheRead:0,cacheWrite:0}}]}}}));
const modelRuntime=await sdk.ModelRuntime.create({authPath:join(agentDir,'auth.json'),modelsPath:join(agentDir,'models.json')});
const settings=sdk.SettingsManager.inMemory({compaction:{enabled:false},retry:{enabled:false}});
const loader=new sdk.DefaultResourceLoader({cwd:root,agentDir,settingsManager:settings,noSkills:true,noPromptTemplates:true,noThemes:true,noContextFiles:true,additionalExtensionPaths:[join(extensionDir,'extension.ts')]});
await loader.reload();if(loader.getExtensions().errors.length)throw new Error(JSON.stringify(loader.getExtensions().errors));
const tools=['read','zara_context','zara_read','zara_route','zara_change','zara_result'];
const {session}=await sdk.createAgentSession({cwd:root,agentDir,resourceLoader:loader,modelRuntime,model:modelRuntime.getModel('fictional','scripted-transport'),thinkingLevel:'off',settingsManager:settings,tools,sessionManager:sdk.SessionManager.inMemory(root)});
const events=[];await session.bindExtensions({onError:error=>events.push({extensionError:error})});session.setActiveToolsByName(tools);
session.subscribe(event=>{if(['tool_execution_end','agent_settled'].includes(event.type))events.push(event);});
await session.prompt('/zaratustra');await session.prompt('Complete a fictional metadata correction task.');await session.waitForIdle();
const bridge=await import(pathToFileURL(join(extensionDir,'bootstrap.mjs')).href);
const receipts=[...bridge.receipts()];
async function request(command,fields={}){return JSON.parse(await bridge.run(python,['-m','zaratustra_app.pi_host'],JSON.stringify({data_root:await bridge.dataRoot(),session_id:session.sessionManager.getSessionId(),command,...fields})));}
const context=await request('context');
const results=await request('tool',{origin:context.current?.attempt?context.current:undefined,name:'read',call_id:'fictional-inspect-results',payload:{operation:'read_page',arguments:{table:'results',limit:100}}});
const observations=await request('tool',{origin:context.current?.attempt?context.current:undefined,name:'read',call_id:'fictional-inspect-observations',payload:{operation:'read_page',arguments:{table:'observations',limit:100}}});
console.log(JSON.stringify({events,receipts,context,results,observations,messages:session.messages,provenance:{pi:sdk.VERSION,semanticEvidence:false,provider:'fictional-localhost-only',bootstrap:'source-interpreter seam',extensionSHA256:createHash('sha256').update(await readFile(join(extensionDir,'extension.ts'))).digest('hex')}}));
session.dispose();

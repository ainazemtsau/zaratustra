import { mkdirSync, writeFileSync, readFileSync } from 'node:fs';
import { join } from 'node:path';
import { spawnSync } from 'node:child_process';
import { pathToFileURL } from 'node:url';
const trial = process.cwd();
const agentDir=join(trial,'agent'); const cwd=join(trial,'cwd');
mkdirSync(agentDir,{recursive:true}); mkdirSync(cwd,{recursive:true});
const cli='C:/Users/Anton/AppData/Roaming/npm/node_modules/@earendil-works/pi-coding-agent/dist/bundle/cli.js';
const sdk='C:/Users/Anton/AppData/Roaming/npm/node_modules/@earendil-works/pi-coding-agent/dist/index.js';
process.env.PI_CODING_AGENT_DIR=agentDir; process.env.PI_OFFLINE='1';
const env={...process.env,PI_CODING_AGENT_DIR:agentDir,PI_OFFLINE:'1'};
const sources=['old-same-name','new-same-name'].map((label,i)=>{
 const dir=join(trial,label); mkdirSync(dir,{recursive:true});
 writeFileSync(join(dir,'package.json'),JSON.stringify({name:'zaratustra-update-path-fixture',version:i?'0.2.0':'0.1.0',type:'module',pi:{extensions:['./extension.ts']}}));
 writeFileSync(join(dir,'extension.ts'),`export default function(pi) { pi.registerCommand('same-fixture-command', { description: '${label}', handler: async () => {} }); }`);
 return dir;
});
function cliRun(args){const r=spawnSync(process.execPath,[cli,...args],{cwd,env,encoding:'utf8',timeout:30000}); console.log(JSON.stringify({args,status:r.status,stdout:r.stdout,stderr:r.stderr,error:r.error?.message})); if(r.status!==0)throw Error('fixture cli failed');}
function settings(){return JSON.parse(readFileSync(join(agentDir,'settings.json'),'utf8'));}
cliRun(['install',sources[0]]);cliRun(['install',sources[1]]);
console.log(JSON.stringify({afterBoth:settings()}));
const {DefaultResourceLoader,SettingsManager}=await import(pathToFileURL(sdk).href);
const loader=new DefaultResourceLoader({cwd,agentDir,settingsManager:SettingsManager.create(cwd,agentDir),noContextFiles:true,noSkills:true,noPromptTemplates:true,noThemes:true});
await loader.reload();
const loaded=loader.getExtensions(); console.log(JSON.stringify({bothLoad:{extensionPaths:loaded.extensions.map(e=>e.path),errors:loaded.errors}}));
cliRun(['remove',sources[0]]);console.log(JSON.stringify({afterRemoveOld:settings()}));
await loader.reload();const fresh=loader.getExtensions(); console.log(JSON.stringify({afterRemoveLoad:{extensionPaths:fresh.extensions.map(e=>e.path),errors:fresh.errors}}));
cliRun(['list']);

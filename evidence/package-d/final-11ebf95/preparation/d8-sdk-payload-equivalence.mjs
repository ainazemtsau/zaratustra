import {pathToFileURL} from 'node:url';
import {writeFileSync} from 'node:fs';
import assert from 'node:assert/strict';
const {ModelRuntime}=await import(pathToFileURL('C:/Users/Anton/AppData/Roaming/npm/node_modules/@earendil-works/pi-coding-agent/dist/index.js'));
const credentials={read:async()=>({type:'oauth',access:'FICTIONAL_ACCESS',refresh:'FICTIONAL_REFRESH',expires:Date.now()+3600000}),list:async()=>[{providerId:'openai',type:'oauth'}],modify:async()=>{throw Error('no_refresh')},delete:async()=>{throw Error('no_delete')}};
let calls=0,current;
globalThis.fetch=async(input,init)=>{assert.equal(String(input),'http://127.0.0.1:1/v1/responses');if(++calls>4)throw Error('finite_capture_cap');current=JSON.parse(init.body);return new Response(JSON.stringify({error:{message:'controlled_capture_only',type:'invalid_request_error'}}),{status:400,headers:{'Content-Type':'application/json'}})};
const runtime=await ModelRuntime.create({credentials,modelsPath:null,modelsStorePath:null,allowModelNetwork:false,refreshOnCreate:false});
const base=runtime.getModel('openai','gpt-6-luna');assert(base);
const context={systemPrompt:'Same fictional system instruction.',messages:[{role:'user',content:'Same fictional input.',timestamp:1}],tools:[{name:'zara_change',description:'Same typed tool.',parameters:{type:'object',properties:{value:{type:'string'}},required:['value']}}]};
const output=[];
for(const effort of ['medium','high']){
 const packets=[];
 for(const enabled of [true,false]){
  current=undefined;
  await runtime.complete({...base,baseUrl:'http://127.0.0.1:1/v1',maxTokens:64,contextWindow:8192,compat:{...base.compat,supportsMidConvoEffort:enabled}},context,{reasoningEffort:effort,maxTokens:64,maxRetries:0,signal:AbortSignal.timeout(10000)});
  assert(current);packets.push(current);
 }
 const [old,fixed]=packets;
 const updates=old.input.filter(x=>x.type==='configuration_update');assert.equal(updates.at(-1).reasoning.effort,effort);
 assert(!fixed.input.some(x=>x.type==='configuration_update'));assert.equal(fixed.reasoning.effort,effort);assert.equal(fixed.max_output_tokens,64);
 const expected=structuredClone(old);expected.input=expected.input.filter(x=>x.type!=='configuration_update');expected.reasoning.effort=effort;assert.deepEqual(fixed,expected);
 output.push({effort,old,fixed,exact_message_tool_cap_equality:true});
}
writeFileSync('_scratch/d8-sdk-payload-equivalence.json',JSON.stringify({model:'gpt-6-luna',calls,live_inference:0,credentials:'fictional',pairs:output},null,2));console.log(JSON.stringify({calls,live_inference:0,efforts:['medium','high'],exact_message_tool_cap_equality:true}));

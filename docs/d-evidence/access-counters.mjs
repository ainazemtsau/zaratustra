import assert from "node:assert/strict";
import {createRequire} from "node:module";
import {pathToFileURL} from "node:url";
import {join} from "node:path";
import {mkdirSync,writeFileSync} from "node:fs";
const [pkg,out,expected]=process.argv.slice(2);mkdirSync(out,{recursive:true});
const {createJiti}=createRequire(pathToFileURL(process.env.ZARA_PI_SDK))("jiti"),jiti=createJiti(import.meta.url);
const {Core}=await jiti.import(join(pkg,"src/core/index.ts")),{DiskStorage}=await jiti.import(join(pkg,"src/storage/index.ts"));
const d=new DiskStorage(join(out,"home")),ctx={...d.workspace,principal:"trusted-personal",session_id:"scope",runtime_id:"scope",can_write:true,processing_allowed:true};
const hi=new Core(d,{...ctx,scopes:["restricted:read","restricted:write"]}),lo=new Core(d,{...ctx,scopes:[]});
const s=hi.capture("Synthetic scope-bound metadata counterexample","rpc","synthetic");
const put=(c,id,visibility)=>c.commit({request_id:id,reason:"Scope counterexample",source_handles:[s.source_handle],guards:[],ops:[{op:"create_record",client_ref:"e",kind:"entity",title:id,visibility,data:{entity_kind:"device",aliases:[],disambiguation:"Distinct synthetic object",status:"active"}}]});
put(hi,"secret","restricted");put(hi,"visible-one","workspace");put(hi,"visible-two","workspace");
const page=lo.search({kinds:["entity"],limit:1}).data,operation=lo.operation("visible-one"),changes=lo.browse("changes");
let decoded=null;try {decoded=JSON.parse(Buffer.from(page.next_cursor,"base64url").toString());}catch{}
const observation={expected,sequence:lo.sequence(),operation,changes,page,decoded,visible_entities:lo.search({kinds:["entity"]}).data.cards.length};
if(expected==="red") {assert.ok(decoded && decoded.last>1);assert.equal(lo.sequence(),3);assert.equal(operation.data.receipt.snapshot_seq,2);}
else {assert.equal(decoded,null);assert.equal(lo.sequence(),2);assert.equal(operation.data.receipt.snapshot_seq,1);assert.deepEqual(changes.data.cards.map(c=>c.change_seq),[1,2]);}
writeFileSync(join(out,"observations.json"),JSON.stringify(observation,null,2));d.close();console.log(JSON.stringify({expected,checked:true}));

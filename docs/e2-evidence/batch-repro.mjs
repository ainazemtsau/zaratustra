import assert from "node:assert/strict";
import {createRequire} from "node:module";
import {pathToFileURL} from "node:url";
import {join,resolve} from "node:path";
import {mkdirSync,writeFileSync} from "node:fs";
const [packageArg,outArg]=process.argv.slice(2), pkg=resolve(packageArg),out=resolve(outArg);
mkdirSync(out,{recursive:false});
const {createJiti}=createRequire(pathToFileURL(process.env.ZARA_PI_SDK))("jiti"),jiti=createJiti(import.meta.url);
const {Core}=await jiti.import(join(pkg,"src/core/index.ts")),{DiskStorage}=await jiti.import(join(pkg,"src/storage/index.ts"));
const disk=new DiskStorage(join(out,"home")),core=new Core(disk,{...disk.workspace,principal:"trusted-personal",can_write:true,processing_allowed:true,session_id:"own-batch",runtime_id:"own-batch"});
try{
const source=core.capture("Synthetic same lamp and explicit corrected serial E2-B62","rpc","declared-synthetic");
const make=(request_id,ops,guards=[])=>({request_id,ops,guards,reason:"Synthetic exact connected batch",source_handles:[source.source_handle]});
const created=core.commit(make("create",["a","b"].map(k=>({op:"create_record",client_ref:k,kind:"entity",title:k==="a"?"Bench lamp Ω":"Reference lamp",visibility:"workspace",data:{entity_kind:"device",aliases:[k+" original"],disambiguation:"Serial not checked",external_ids:{serial:"unknown"},status:"active"}})))).created;
const before=core.read(created.b).data;
const req=make("correct-merge",[{op:"update_record",ref:{id:created.b},title:"Reference lamp E2-B62",body:"Exact approved corrected label",data:{...before.data,external_ids:{serial:"E2-B62"},disambiguation:"Marking confirmed in synthetic fixture"}},{op:"merge_identity",from_ref:{id:created.a},to_ref:{id:created.b}}],Object.values(created).map(id=>({ref:{id},expected_revision:1})));
const preview=core.prepareCommit(req,"Correct target title, body, serial/disambiguation and merge the original lamp into it","Keep the separate entries");const shown=core.approvals.present(preview.request_id);core.approvals.answer(shown.token,true,{source_ref:"own-registered-answer",transport:"native-dialog",channel_identity:"declared-synthetic",stage:"pi-confirm-return"});
const receipt=core.commit({...req,preview_ref:preview.request_id}),actual=core.read(created.b).data;
writeFileSync(join(out,"proof.json"),JSON.stringify({pkg,request:req,preview,receipt,before,actual,source_after:core.read(created.a).data},null,2));
assert.equal(actual.title,"Reference lamp E2-B62");assert.equal(actual.body,"Exact approved corrected label");assert.equal(actual.data.external_ids.serial,"E2-B62");assert.equal(actual.data.disambiguation,"Marking confirmed in synthetic fixture");
assert.deepEqual(core.commit({...req,preview_ref:preview.request_id}),receipt);
console.log(JSON.stringify({preserves_exact_connected_batch:true,replay_same_receipt:true}));
}finally{disk.close();}

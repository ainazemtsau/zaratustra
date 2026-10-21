import test from "node:test";
import assert from "node:assert/strict";
import { mkdtempSync,mkdirSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { Core } from "../src/core/index.ts";
import type { CallContext, RecordRow, JsonObject } from "../src/core/index.ts";
import { Administration, DiskStorage } from "../src/storage/index.ts";
function setup(){
 const root=mkdtempSync(join(process.env.ZARATUSTRA_TEST_ROOT??tmpdir(),"e3-controls-")),home=join(root,"home"),backups=join(root,"backups");mkdirSync(backups);const disk=new DiskStorage(home);
 const ctx:CallContext={workspace_id:disk.workspace.workspace_id,epoch:disk.workspace.epoch,principal:"trusted-personal",session_id:"synthetic",runtime_id:"controls",can_write:true,processing_allowed:true,scopes:["restricted:read","restricted:write"]},core=new Core(disk,ctx),admin=new Administration(home,backups,ctx);let serial=0;
 const save=(ops:JsonObject[],guards:{ref:{id:string};expected_revision:number}[]=[])=>{const source=core.capture("Synthetic control instruction "+(++serial),"rpc","registered-controls");return core.commit({request_id:"control-"+serial,reason:"Addressed synthetic control",source_handles:[source.source_handle],guards,ops:ops.map(o=>o.op==="import_evidence"?{...o,source_handle:source.source_handle}:o)});};
 const read=(id:string)=>core.read(id).data as RecordRow;
 const method=(instructions:string,dependencies:unknown[]=[])=>({applicability:"Synthetic control",instructions,input_contract:"Given input",expected_output:"Grounded result",context_requirements:[],dependencies,tool_requirements:[],content_version:1,state:"candidate",derived_from:[],limitations:"Synthetic fixture only"});
 const work=(refs:unknown[])=>save([{op:"create_record",client_ref:"w",kind:"work",title:"Open exact dependency obligation",visibility:"workspace",data:{activity_id:null,parent_work_id:null,objective:"Check supplied exact dependency",acceptance:[{criterion_id:"check",description:"Grounded result",verification:"Read exact dependency",required:true}],status:"active",current_state:"Awaiting check",next_action:"Inspect exact grounds",steps:[],waits:[],context_refs:refs,completion:null}}]).created.w;
 return {root,home,backups,disk,ctx,core,admin,save,read,method,work};
}
function approve(core:Core,ref:string){const p=core.approvals.present(ref);core.approvals.answer(p.token,true,{source_ref:"synthetic-approval",transport:"native-dialog",channel_identity:"registered-controls",stage:"pi-confirm-return"});}
function code(action:()=>unknown){try{action();return "success";}catch(e){return (e as {code?:string}).code??"unknown";}}
test("E3 control operations cards remain readable after exact tombstone redacts a preview payload",t=>{
 const f=setup();t.after(()=>f.disk.close());const id=f.save([{op:"create_record",client_ref:"e",kind:"entity",title:"Removable control",body:"REMOVABLE_CONTROL_BODY",visibility:"workspace",data:{entity_kind:"item",aliases:[],disambiguation:"Synthetic removable",status:"active"}}]).created.e;
 const p=f.core.storagePreview({action:"tombstone",targets:[{id,revision:1}]},"Delete selected body","Keep");approve(f.core,p.request_id);f.core.applyStorage(p.request_id);
 assert.doesNotThrow(()=>f.core.browse("operations"));assert.equal(JSON.stringify(f.core.browse("operations")).includes("REMOVABLE_CONTROL_BODY"),false);assert.equal(JSON.stringify(f.core.operation(p.request_id)).includes("REMOVABLE_CONTROL_BODY"),false);
});
test("E3 control unreferenced Concept has a valid tombstone and its bundle verifies/restores",async t=>{
 const f=setup();t.after(()=>f.disk.close());const id=f.save([{op:"create_record",client_ref:"c",kind:"concept",title:"Empty optional section",visibility:"workspace",data:{definition:"Unused root",aliases:[],broader_ids:[],status:"active"}}]).created.c;
 const p=f.core.storagePreview({action:"tombstone",targets:[{id,revision:1}]},"Delete unused section body","Keep");approve(f.core,p.request_id);f.core.applyStorage(p.request_id);assert.equal(f.read(id).storage,"tombstone");const b=await f.admin.backup(f.disk);assert.equal(f.admin.verify(b.backup).manifest.complete,true);
});
test("E3 control exact Method dependency pinned by open Work survives current Method revision; releasing obligation does not pin all history",t=>{
 const f=setup();t.after(()=>f.disk.close());const b=f.save([{op:"create_record",client_ref:"b",kind:"method",title:"Dependency B",visibility:"workspace",data:f.method("Required B v1")}]).created.b;
 const a=f.save([{op:"create_record",client_ref:"a",kind:"method",title:"Composed A",visibility:"workspace",data:f.method("A v1 needs B",[{id:b,content_version:1}])}]).created.a,w=f.work([{id:a,content_version:1}]);
 const a1=f.read(a);f.save([{op:"revise_method",ref:{id:a},data:{...a1.data,instructions:"A v2 independent",dependencies:[]}}],[{ref:{id:a},expected_revision:1}]);
 assert.throws(()=>f.core.storagePreview({action:"tombstone",targets:[{id:b,revision:1}]},"Delete B","Keep B"),{code:"DEPENDENCY_UNSATISFIED"});
 assert.throws(()=>f.core.storagePreview({action:"tombstone",targets:[{id:b,revision:1},{id:a,revision:2}]},"Delete both methods","Keep grounded Work"),{code:"DEPENDENCY_UNSATISFIED"});
 const old=f.read(w);f.save([{op:"update_record",ref:{id:w},data:{...old.data,context_refs:[]}}],[{ref:{id:w},expected_revision:old.revision}]);
 assert.doesNotThrow(()=>f.core.storagePreview({action:"tombstone",targets:[{id:b,revision:1}]},"Delete now unpinned B","Keep historical body"));
});
test("E3 control exact historical Knowledge grounds remain pinned by open Work after current correction",t=>{
 const f=setup();t.after(()=>f.disk.close());const e1=f.save([{op:"import_evidence",client_ref:"e",title:"First grounds",source_language:"en"}]).created.e,e2=f.save([{op:"import_evidence",client_ref:"e",title:"Later grounds",source_language:"en"}]).created.e;
 const k=f.save([{op:"create_record",client_ref:"k",kind:"knowledge",title:"Changing observation",visibility:"workspace",data:{knowledge_kind:"observation",statement:"Old synthetic observation",state:"current",basis:"user_statement",evidence_refs:[{id:e1}],conditions:"Synthetic"}}]).created.k;f.work([{id:k,revision:1}]);const prior=f.read(k);f.save([{op:"update_record",ref:{id:k},data:{...prior.data,statement:"New observation",evidence_refs:[{id:e2}]}}],[{ref:{id:k},expected_revision:1}]);
 assert.throws(()=>f.core.storagePreview({action:"tombstone",targets:[{id:e1,revision:1}]},"Delete old grounds","Keep obligation"),{code:"DEPENDENCY_UNSATISFIED"});
});
test("E3 control hidden primary guessed missing revision is indistinguishable from nonexistent ID",t=>{
 const f=setup();t.after(()=>f.disk.close());const id=f.save([{op:"create_record",client_ref:"e",kind:"entity",title:"Hidden synthetic identity",visibility:"restricted",data:{entity_kind:"item",aliases:[],disambiguation:"Private fixture",status:"active"}}]).created.e,low=new Core(f.disk,{...f.ctx,scopes:[]});
 assert.equal(code(()=>low.read(id,999999)),code(()=>low.read("entity-nonexistent",999999)));assert.equal(code(()=>low.read(id,999999)),"REFERENCE_NOT_FOUND");assert.equal(code(()=>f.core.read(id,999999)),"CONTENT_NOT_RETAINED");
});
test("E3 control stable lease survives SQLite close; a real interleaving writer cannot commit unpreviewed data",async t=>{
 const f=setup();const b=await f.admin.backup(f.disk),p=f.admin.restorePreview(b.backup,"Restore exact empty snapshot","Keep current");const shown=f.admin.approvals.present(p.preview.request_id);f.admin.approvals.answer(shown.token,true,{source_ref:"synthetic",transport:"native-dialog",channel_identity:"registered-controls",stage:"pi-confirm-return"});
 const optional=f.disk as unknown as {closeConnection?:()=>void};const original=(optional.closeConnection??f.disk.close).bind(f.disk);let once=false,attempted=false,blocked=false;
 const interpose=()=>{original();if(once)return;once=true;attempted=true;const other=new DiskStorage(f.home);try {const c=new Core(other,{...f.ctx,runtime_id:"intervening-writer",can_write:true});const s=c.capture("Intervening real writer","rpc","synthetic");blocked=code(()=>c.commit({request_id:"intervening",source_handles:[s.source_handle],guards:[],reason:"Must not be discarded by unpreviewed restore",ops:[{op:"create_record",client_ref:"a",kind:"activity",title:"Unpreviewed intervening commit",visibility:"workspace",data:{purpose:"Would be lost",status:"active"}}]}))==="READ_ONLY";}finally{other.close();}};
 if(optional.closeConnection) Object.defineProperty(f.disk,"closeConnection",{value:interpose});else f.disk.close=interpose;
 f.admin.restore(p.preview.request_id,f.disk);assert.equal(attempted,true);assert.equal(blocked,true,"A legitimate writer must remain blocked across the connection-close/pointer gap");const current=new DiskStorage(f.home);t.after(()=>current.close());
});

import assert from "node:assert/strict";
import {createRequire} from "node:module";
import {pathToFileURL} from "node:url";
import {join,resolve} from "node:path";
import {readFileSync,writeFileSync} from "node:fs";
const [pkgArg,rootArg]=process.argv.slice(2),pkg=resolve(pkgArg),root=resolve(rootArg);
const fixture=JSON.parse(readFileSync(join(root,"observations.json"),"utf8"));
const {createJiti}=createRequire(pathToFileURL(process.env.ZARA_PI_SDK))("jiti"),jiti=createJiti(import.meta.url);
const {Core}=await jiti.import(join(pkg,"src/core/index.ts")),{DiskStorage}=await jiti.import(join(pkg,"src/storage/index.ts"));
const d=new DiskStorage(join(root,"home")),c=new Core(d,{...d.workspace,principal:"trusted-personal",session_id:"measure",runtime_id:"measure",can_write:true,processing_allowed:true});
const measurements=[];const measure=(name,fn)=>{const start=performance.now(),value=fn();measurements.push({name,ms:performance.now()-start,bytes:Buffer.byteLength(JSON.stringify(value))});return value;};
try {
 const map=measure("map",()=>c.map()),branch=measure("branch",()=>c.browse("topics",fixture.ids.concepts[0]));
 const search=measure("lexical",()=>c.search({query:"risograph printing",match:"all",kinds:["knowledge"]}));assert.equal(search.data.cards[0].id,fixture.ids.claims[0]);
 const read=measure("selected-claim",()=>c.read(fixture.ids.claims[0])),snapshot=measure("snapshot",()=>c.snapshot());
 let cursor,count=0,pages=0,pageBytes=0;
 do {const p=measure("page-"+pages,()=>c.search({kinds:["knowledge"],limit:50,...(cursor?{cursor}:{})})).data;count+=p.cards.length;pageBytes+=Buffer.byteLength(JSON.stringify(p));pages++;cursor=p.next_cursor;}while(cursor);
 const observedKnowledge=d.get("SELECT count(*) AS n FROM records WHERE kind='knowledge'").n;assert.equal(count,observedKnowledge);
 const data={mechanical:true,prepared_knowledge:fixture.counts.knowledge,observedKnowledge,record_count:d.get("SELECT count(*) AS n FROM records").n,revisions:d.get("SELECT count(*) AS n FROM revisions").n,pages,count,pageBytes,measurements,map,branch,search,read,snapshot,trace_bound:c.diagnostics().data.trace_bound};
 writeFileSync(join(root,"measured-qualified.json"),JSON.stringify(data,null,2));console.log(JSON.stringify({record_count:data.record_count,pages,count,pageBytes,measurements:measurements.slice(0,5)}));
} finally {d.close();}

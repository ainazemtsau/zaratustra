// Mechanical fixture preparation, never a model-authored save.
import assert from "node:assert/strict";
import {createRequire} from "node:module";
import {pathToFileURL} from "node:url";
import {join,resolve} from "node:path";
import {readFileSync,writeFileSync} from "node:fs";
const [pkgArg,corpusArg]=process.argv.slice(2),pkg=resolve(pkgArg),root=resolve(corpusArg);
const fixture=JSON.parse(readFileSync(join(root,"observations.json"),"utf8"));
const {createJiti}=createRequire(pathToFileURL(process.env.ZARA_PI_SDK))("jiti"),jiti=createJiti(import.meta.url);
const {Core}=await jiti.import(join(pkg,"src/core/index.ts")),{DiskStorage}=await jiti.import(join(pkg,"src/storage/index.ts"));
const d=new DiskStorage(join(root,"home")),c=new Core(d,{...d.workspace,principal:"trusted-personal",session_id:"corpus-grounding",runtime_id:"corpus-grounding",can_write:true,processing_allowed:true});
try {
 const source=c.capture('Синтетические противоречащие сообщения об одном контрольном объекте 3. Источник A: «Доступ только по будням, в выходные доступа нет». Источник B: «Доступ только по выходным, по будням доступа нет». Достоверность и время действия не установлены; ни одному источнику не отдаётся предпочтение.',"rpc","synthetic-corpus-controller");
 const before=[3,4].map(n=>c.read(fixture.ids.claims[n]).data);
 const receipt=c.commit({request_id:"ground-conflicting-fixture-sources",reason:"Give contradictory conditions one addressed subject and exact retained source, not unrelated objects",source_handles:[source.source_handle],guards:before.map(v=>({ref:{id:v.id},expected_revision:v.revision})),ops:[{op:"import_evidence",client_ref:"conflict",source_handle:source.source_handle,title:"Conflicting synthetic reports about one device",source_language:"ru",semantic_source_kind:"external_reply"},...before.map((v,i)=>({op:"update_record",ref:{id:v.id},data:{...v.data,statement:i===0?"Source A reports weekday-only access to synthetic device 3 and excludes weekends.":"Source B reports weekend-only access to the same synthetic device 3 and excludes weekdays.",object_ref:{id:fixture.ids.entities[3]},basis:"external_source",state:"contested",conditions:i===0?"Weekdays only; weekends excluded. Unresolved conflict with source B; applicability time unknown.":"Weekends only; weekdays excluded. Unresolved conflict with source A; applicability time unknown.",evidence_refs:[{client_ref:"conflict"}],representation:{kind:"English paraphrase",source_ref:{client_ref:"conflict"},source_language:"ru"}}}))]});
 const after=before.map(v=>c.read(v.id).data);assert.equal(after[0].data.object_ref.id,after[1].data.object_ref.id);assert.ok(after.every(v=>v.data.state==="contested"));
 writeFileSync(join(root,"contradiction-grounding.json"),JSON.stringify({synthetic:true,mechanical:true,reason:"Strengthened a corpus observer gap: baseline contested filler rows had distinct objects",before,after,receipt,record_count:d.get("SELECT count(*) AS n FROM records").n,versions:d.get("SELECT count(*) AS n FROM revisions").n,grounds:c.read(receipt.created.conflict).data},null,2));
} finally {d.close();}
console.log(JSON.stringify({grounded_same_subject:true,root}));

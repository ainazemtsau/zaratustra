import assert from "node:assert/strict";
import {createRequire} from "node:module";
import {pathToFileURL} from "node:url";
import {join,resolve} from "node:path";
import {readFileSync,writeFileSync} from "node:fs";
const [pkgArg,rootArg]=process.argv.slice(2),pkg=resolve(pkgArg),root=resolve(rootArg);
const {createJiti}=createRequire(pathToFileURL(process.env.ZARA_PI_SDK))("jiti"),jiti=createJiti(import.meta.url);
const {Core}=await jiti.import(join(pkg,"src/core/index.ts")),{DiskStorage}=await jiti.import(join(pkg,"src/storage/index.ts"));
const summary=n=>JSON.parse(readFileSync(join(root,"live",n,"summary.json"),"utf8"));
const before=summary("21-scoped-save"),after=summary("23-scoped-changed");
const original=before.database.records.map(r=>JSON.parse(r.json));
const oldAccess=original.find(r=>r.kind==="knowledge" && r.data.predicate==="has_access_to");
const oldCode=original.find(r=>r.kind==="knowledge" && r.title.includes("Booking code"));
const home=join(root,"scoped-home"),d=new DiskStorage(home),ctx={...d.workspace,principal:"trusted-personal",session_id:"scoped-proof",runtime_id:"scoped-proof",can_write:false,processing_allowed:true};
const hi=new Core(d,{...ctx,scopes:["restricted:read","restricted:write"]}),lo=new Core(d,{...ctx,scopes:[]});
const canonical=()=>JSON.stringify(["records","revisions","changes","receipts","intents","claims","handoffs"].map(t=>d.all("SELECT * FROM "+t+" ORDER BY rowid")));
const start=canonical();
try {
 const old=hi.read(oldAccess.id,1).data;assert.deepEqual(old,oldAccess);
 const current=hi.read(oldAccess.id).data;assert.equal(current.data.state,"superseded");
 const code=hi.read(oldCode.id).data;assert.equal(code.data.state,"superseded");
 const currentResults=hi.search({query:"Парус Роса",match:"any",states:["current"]});
 assert.ok(!currentResults.data.cards.some(c=>[oldAccess.id,oldCode.id].includes(c.id)));
 const denied=[];
 for(const action of [()=>lo.read(oldAccess.id),()=>lo.read(oldAccess.id,1),()=>lo.read(oldCode.id),()=>lo.search({object_id:oldAccess.data.object_ref.id,states:["current"]})]) {
  try {const value=action();if(value.data.cards) assert.ok(!value.data.cards.some(c=>[oldAccess.id,oldCode.id].includes(c.id)));else throw new Error("Unexpected private read");}catch(e){assert.equal(e.code,"REFERENCE_NOT_FOUND");denied.push(e.code);}
 }
 const low={map:lo.map(),knowledge:lo.browse("knowledge"),operations:lo.browse("operations"),changes:lo.browse("changes"),snapshot:lo.snapshot(),diagnostics:lo.diagnostics()};
 assert.ok(!JSON.stringify(low).includes("Роса-73"));assert.ok(!JSON.stringify(low).includes(oldCode.title));
 const snapshot=hi.snapshot(),works=after.database.records.map(r=>JSON.parse(r.json)).filter(r=>r.kind==="work");
 assert.ok(works.length>0 && works.every(w=>w.data.status!=="done"));
 const requests=readFileSync(join(root,"live/23-scoped-changed/requests.jsonl"),"utf8").trim().split("\n").map(JSON.parse);
 const last=JSON.parse(requests.at(-1).snapshots[0].content);
 assert.ok(works.every(w=>last.records.some(s=>s.id===w.id && s.revision===w.revision) || last.must_read.includes(w.id)));
 assert.equal(canonical(),start);
 writeFileSync(join(root,"scoped-state-proof.json"),JSON.stringify({source_old:old,current_old_claim:current,current_old_code:code,currentResults,low,denied,works,snapshot,last_model_snapshot:last,exact_old_version:true,domain_unchanged_by_proof:true},null,2));
} finally {d.close();}
console.log(JSON.stringify({history_exact:true,current_superseded:true,protected_scope_enforced:true,next_model_snapshot_current:true}));

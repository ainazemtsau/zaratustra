// Final native upgrade readback; synthetic domain only, zero model requests.
import assert from 'node:assert/strict';
import {DatabaseSync} from 'node:sqlite';
import {readFileSync,writeFileSync,readdirSync,existsSync} from 'node:fs';
import {join} from 'node:path';
import {createHash} from 'node:crypto';
import {createRequire} from 'node:module';
import {pathToFileURL} from 'node:url';
const [mode,root,pkg,home,output]=process.argv.slice(2);
const hash=b=>createHash('sha256').update(b).digest('hex');
const tables=['meta','records','revisions','changes','intents','receipts','focus','claims','handoffs','migrations'];
const db=new DatabaseSync(join(home,'zara.sqlite'),{readOnly:true});
const snapshot={tables:Object.fromEntries(tables.map(t=>[t,db.prepare('SELECT * FROM '+t+' ORDER BY rowid').all()])),materials:Object.fromEntries(readdirSync(join(home,'materials')).map(n=>[n,hash(readFileSync(join(home,'materials',n)))]))};db.close();
if(mode==='before'){writeFileSync(output,JSON.stringify(snapshot,null,2));console.log('Exact pre-delivery snapshot saved');}
else{
 const before=JSON.parse(readFileSync(join(root,'final-preservation-before.json'),'utf8'));
 assert.deepEqual(JSON.parse(JSON.stringify(snapshot)),before);
 const {createJiti}=createRequire(pathToFileURL(process.env.ZARA_PI_SDK))('jiti'),jiti=createJiti(import.meta.url);
 const {DiskStorage}=await jiti.import(join(pkg,'src/storage/index.ts'));
 const {Core}=await jiti.import(join(pkg,'src/core/index.ts'));
 const disk=new DiskStorage(home),core=new Core(disk,{...disk.workspace,principal:'trusted-personal',session_id:'final-mechanical-readback',runtime_id:'final-mechanical-readback',can_write:true,processing_allowed:true});
 const materials=JSON.parse(readFileSync(join(root,'live-materials-manifest.json'),'utf8')).materials;
 const reads=[];
 try{for(const m of materials){
  const original=core.read(m.original_ref.id,m.original_ref.revision).data;
  assert.equal(original.data.content_hash,m.source_sha256);assert.equal(existsSync(original.data.source_locator),false);
  const derivative=core.read(m.derived_ref.id,m.derived_ref.revision).data;
  const text=readFileSync(join(home,'materials',derivative.data.blob_ref),'utf8');
  const locator=m.sections.at(-1)?.locator;
  const start=locator?0:10000;
  const data=core.read(m.derived_ref.id,m.derived_ref.revision,{...(locator?{locator}:{}),start,length:8000}).data;
  assert.equal(data.text,Array.from(text).slice(data.global_start,data.global_start+Array.from(data.text).length).join(''));
  reads.push({name:m.name,original_sha256:m.source_sha256,derived_ref:m.derived_ref,source_path_absent:true,locator:data.locator,global_start:data.global_start,text:data.text,exact_managed_range:true});
 }}finally{disk.close();}
 writeFileSync(output,JSON.stringify({synthetic:true,model_requests:0,all_ten_tables_and_material_bytes_exact:true,counts:Object.fromEntries(Object.entries(snapshot.tables).map(([t,r])=>[t,r.length])),materials:Object.keys(snapshot.materials).length,final_managed_api_reads:reads},null,2));
 console.log('All predecessor and new-format rows/materials exact; final managed API reads passed');
}

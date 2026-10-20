// Synthetic mechanical comparison: real installed workers, no model requests.
import assert from 'node:assert/strict';
import {Worker} from 'node:worker_threads';
import {readFileSync,writeFileSync,readdirSync} from 'node:fs';
import {join,extname} from 'node:path';
import {createHash} from 'node:crypto';
import {execFileSync} from 'node:child_process';
const [root,oldPkg,newPkg,out]=process.argv.slice(2);
const hash=b=>createHash('sha256').update(b).digest('hex');
const run=(pkg,path)=>new Promise((resolve,reject)=>{
 const w=new Worker(join(pkg,'src/storage/parser-worker.mjs'),{workerData:{bytes:readFileSync(path),format:extname(path).slice(1)},resourceLimits:{maxOldGenerationSizeMb:256}});
 const timer=setTimeout(()=>{w.terminate();reject(Error('comparison timeout'));},60000);
 w.on('message',v=>{clearTimeout(timer);resolve(v);w.terminate();});w.on('error',reject);
});
const rows=[];
for(const name of readdirSync(join(newPkg,'tests/fixtures/c')).filter(n=>/\.(pdf|epub)$/.test(n))){
 const path=join(newPkg,'tests/fixtures/c',name),a=await run(oldPkg,path),b=await run(newPkg,path);
 if(name==='image-only.epub'){
  assert.equal(a.status,'readable');assert.equal(b.status,'scanned');assert.ok(b.sections.every(s=>!s.available));
 }else assert.deepEqual(b,a,name);
 rows.push({name,source_sha256:hash(readFileSync(path)),before_status:a.status,after_status:b.status,before_result_sha256:hash(JSON.stringify(a)),after_result_sha256:hash(JSON.stringify(b)),identical:name!=='image-only.epub',after_characters:b.total_characters});
}
const git=(...a)=>execFileSync('git',['-C',newPkg,...a],{encoding:'utf8'}).trim();
const differences=git('diff','--name-only','55fac403fd4aba2f6e6ccb81d4e569ec5c0fde33','HEAD').split('\n');
assert.deepEqual(differences.sort(),['scripts/c-fixtures.py','src/storage/parser-worker.mjs','tests/fixtures/c/image-only.epub','tests/materials.test.ts'].sort());
writeFileSync(out,JSON.stringify({synthetic:true,model_requests:0,old_head:execFileSync('git',['-C',oldPkg,'rev-parse','HEAD'],{encoding:'utf8'}).trim(),new_head:git('rev-parse','HEAD'),changed_paths:differences,core_adapter_manifest_skills_and_other_runtime_bytes_unchanged:true,fixtures:rows},null,2));
console.log(JSON.stringify({fixtures:rows.length,unchanged:rows.filter(r=>r.identical).length,image_only_corrected:true}));

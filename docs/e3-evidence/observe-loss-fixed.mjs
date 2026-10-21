import assert from 'node:assert/strict';
import {createRequire} from 'node:module';
import {pathToFileURL} from 'node:url';
import {join,resolve} from 'node:path';
import {existsSync,readFileSync,writeFileSync,mkdirSync,lstatSync,renameSync} from 'node:fs';
import {DatabaseSync} from 'node:sqlite';
import {createHash} from 'node:crypto';
const root=resolve(process.argv[2]), mode=process.argv[3], home=join(root,'profiles/fixed-protected/home');
const {createJiti}=createRequire(pathToFileURL(process.env.ZARA_PI_SDK))('jiti'),jiti=createJiti(import.meta.url);
const pkg=join(root,'profiles/fixed-protected/agent/git/github.com/ainazemtsau/zaratustra');
const {activeLocation,safePath}=await jiti.import(join(pkg,'src/storage/index.ts'));
const path=join(activeLocation(home),'zara.sqlite'), target=join(root,'profiles/fixed-protected/output', mode==='loss'?'observatory-report.txt':'generation-check.txt');
const sha=b=>createHash('sha256').update(b).digest('hex');
const bytes=readFileSync(target);assert.equal(bytes.toString(), mode==='loss'?'Observatory: optics checked; result ready.\n':'Generation check: confirmed.\n');
const db=new DatabaseSync(path,{readOnly:true});
const attempts=db.prepare("SELECT json FROM intents WHERE json_extract(json,'$.kind')='managed_file' AND json_extract(json,'$.payload.target')=?").all(target).map(r=>JSON.parse(r.json));db.close();
assert.equal(attempts.length,1);assert.equal(attempts[0].status,'requested');assert.equal(attempts[0].receipt,null);
const proof={active_database:path,target,length:bytes.length,sha256:sha(bytes),attempt:attempts[0],actual_world_bytes:true};
if(mode==='loss'){
 const pid=JSON.parse(readFileSync(join(root,'live-fixed/L03-write-B/identity.jsonl'),'utf8').trim()).pid;
 assert.throws(()=>process.kill(pid,0));
 const loss=join(root,'fixed-lost-current-after-B'); assert.equal(existsSync(loss),false);mkdirSync(loss);
 proof.retained_loss=[];
 for(const suffix of ['', '-wal','-shm']){
  const source=safePath(root,path+suffix), destination=safePath(root,join(loss,'zara.sqlite'+suffix));
  if(!existsSync(source))continue;
  const before=lstatSync(source,{bigint:true});assert.ok(before.isFile());const b=readFileSync(source);
  const recheck=lstatSync(source,{bigint:true});assert.equal(before.dev,recheck.dev);assert.equal(before.ino,recheck.ino);assert.equal(existsSync(destination),false);
  renameSync(source,destination);assert.equal(sha(readFileSync(destination)),sha(b));
  proof.retained_loss.push({source,destination,length:b.length,sha256:sha(b),dev:String(before.dev),ino:String(before.ino)});
 }
 assert.equal(existsSync(path),false);proof.current_database_missing=true;
}
writeFileSync(join(root,mode==='loss'?'FIXED-B-WRITE-AND-LOSS-PROOF.json':'FIXED-GENERATION-WRITE-PROOF.json'),JSON.stringify(proof,null,2));
console.log(JSON.stringify({mode,active_database:path,real_bytes:true,requested_attempt:attempts[0].request_id,current_missing:mode==='loss'}));

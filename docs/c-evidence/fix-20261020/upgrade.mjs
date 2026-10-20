// Isolated synthetic predecessor fixture, not a user backup/restore facility.
import assert from 'node:assert/strict';
import {readFileSync,writeFileSync} from 'node:fs';
import {join} from 'node:path';
import {createRequire} from 'node:module';
import {pathToFileURL} from 'node:url';
const [mode,root,pkg]=process.argv.slice(2);
const {createJiti}=createRequire(pathToFileURL(process.env.ZARA_PI_SDK))('jiti'),jiti=createJiti(import.meta.url);
const {DiskStorage}=await jiti.import(join(pkg,'src/storage/index.ts'));
const {Core}=await jiti.import(join(pkg,'src/core/index.ts'));
const disk=new DiskStorage(join(root,'upgrade-home'));
const core=new Core(disk,{...disk.workspace,principal:'trusted-personal',session_id:'mechanical-upgrade',runtime_id:'mechanical-upgrade-'+mode,can_write:true,processing_allowed:true});
const tables=['meta','records','revisions','changes','intents','receipts','focus','claims','handoffs','migrations'];
const snap=()=>JSON.parse(JSON.stringify(Object.fromEntries(tables.map(t=>[t,disk.all('SELECT * FROM '+t+' ORDER BY rowid')]))));
const row=id=>core.read(id).data;
const source=core.capture('Synthetic authorized lifecycle and plan reconciliation, no external sending.','rpc','trusted-synthetic-upgrade').source_handle;
let serial=0;
const send=(ops,ids=[],tokens=[])=>core.commit({request_id:mode+'-'+(++serial),reason:'Synthetic upgrade and compatibility behavior',source_handles:[source],guards:ids.map(id=>({ref:{id},expected_revision:row(id).revision})),claim_tokens:tokens,ops});
const claim=(id,purpose,step_id)=>core.claim({action:'acquire',work_id:id,expected_revision:row(id).revision,purpose,step_id,reason:'Supported local recording'}).data.token;
try{
 if(mode==='seed'){
  const refs=send([{op:'import_evidence',client_ref:'input',source_handle:source,title:'Synthetic original input',source_language:'en'},{op:'create_record',client_ref:'w',kind:'work',title:'Legacy preparation and future clarification',visibility:'workspace',data:{activity_id:null,parent_work_id:null,objective:'Retain a card after its review',acceptance:[{criterion_id:'card',description:'Card retained',verification:'Inspect saved card',required:true}],status:'active',current_state:'Prepare the review request',next_action:'Prepare request',steps:[{step_id:'prepare',intent:'Prepare a manual review request; send nothing',status:'todo',required:false,depends_on:[],result_refs:[]}],waits:[],context_refs:[{client_ref:'input'}],completion:null}}]).created;
  const id=refs.w,h=send([{op:'prepare_handoff',client_ref:'h',work_ref:{id},step_id:'prepare',objective:'Review card',conditions:'No sending',expected_result:'Clarity comments',context_refs:[{id:refs.input}],message:'Please review this card for clarity.'}],[id],[claim(id,'handoff','prepare')]).created.h;
  const complete=send([{op:'record_result',client_ref:'card',work_ref:{id},title:'Original completed card',content:'Keep the observation separate from its explanation.',source_language:'en'},{op:'transition_work',ref:{id},status:'done',reason:'Card saved; optional unfinished preparation remains a legacy planning defect',grounds:[{criterion_id:'card',explanation:'Saved card inspected',evidence_refs:[{client_ref:'card'}]}]}],[id],[claim(id,'work')]);
  const completed=row(id);
  send([{op:'transition_work',ref:{id},status:'active',reason:'Explicitly reopen for later clarification',next_action:'Await future clarification',decision_source_handle:source}],[id]);
  writeFileSync(join(root,'upgrade-before.json'),JSON.stringify({tables:snap(),refs:{...refs,h,card:complete.created.card},completed,workspace:disk.workspace},null,2));
 }else if(mode==='verify'){
  const before=JSON.parse(readFileSync(join(root,'upgrade-before.json'),'utf8'));
  assert.deepEqual(snap(),before.tables);
  const id=before.refs.w;
  send([{op:'transition_step',ref:{id},step_id:'prepare',status:'done',reason:'Reuse the actual saved preparation',result_refs:[{id:before.refs.h}]}],[id],[claim(id,'step','prepare')]);
  send([{op:'update_record',ref:{id},data:{...row(id).data,next_action:null,waits:[{wait_id:'clarification',kind:'user',target:'work',subject:'Future card clarification',satisfied_by:'Requested clarification is received',received_refs:[],question:'Send clarification',status:'pending'}]},plan_change_reason:'Explicitly represent the new upcoming input',decision_source_handle:source},{op:'transition_work',ref:{id},status:'waiting',reason:'No independent work before the clarification'}],[id]);
  assert.deepEqual(core.read(id,before.completed.revision).data,before.completed);
  for(const t of ['revisions','changes','receipts','intents','handoffs'])for(const old of before.tables[t])assert.ok(snap()[t].some(r=>JSON.stringify(r)===JSON.stringify(old)),t);
  writeFileSync(join(root,'upgrade-verification.json'),JSON.stringify({synthetic:true,model_requests:0,initial_all_tables_exact:true,schema_unchanged:disk.workspace.schema_version===2,old_history_and_receipts_exact:true,old_completion_exact:true,old_card_exact:row(before.refs.card),before:JSON.parse(before.tables.records.find(r=>r.id===id).json),after:row(id),handoff:core.handoff(before.refs.h).data,all_current_tables:snap()},null,2));
 }else if(mode==='old-reject'){
  const before=snap();
  assert.throws(()=>send([{op:'create_record',client_ref:'x',kind:'activity',title:'Forbidden old writer attempt',visibility:'workspace',data:{purpose:'Test old resolver failure',status:'active'}}]),/unavailable/);
  const after=snap();
  for(const t of tables.filter(t=>t!=='intents'))assert.deepEqual(after[t],before[t]);
  assert.equal(after.receipts.length,before.receipts.length);
  writeFileSync(join(root,'old-writer-rejection.json'),JSON.stringify({synthetic:true,model_requests:0,old_record_only_resolver_rejected_handoff_result:true,domain_claims_handoffs_receipts_unchanged:true,possible_new_prepared_intent_not_commit:true},null,2));
 }else throw Error('Unknown mode');
 console.log(JSON.stringify({mode,pass:true}));
}finally{disk.close();}

// Explicitly mechanical synthetic preparation after transport failure in attempt 06.
// These Core mutations are not model actions and are not a completed live attempt 06.
import {join} from 'node:path';import {createRequire} from 'node:module';import {pathToFileURL} from 'node:url';import {writeFileSync} from 'node:fs';
const [root,pkg]=process.argv.slice(2);const {createJiti}=createRequire(pathToFileURL(process.env.ZARA_PI_SDK))('jiti'),jiti=createJiti(import.meta.url);
const {Core}=await jiti.import(join(pkg,'src/core/index.ts'));const {DiskStorage}=await jiti.import(join(pkg,'src/storage/index.ts'));
const disk=new DiskStorage(join(root,'ambiguity-home')),core=new Core(disk,{...disk.workspace,principal:'trusted-personal',session_id:'mechanical-pair-fixture',runtime_id:'mechanical-pair-fixture',can_write:true,processing_allowed:true});
const source=core.capture('Synthetic fixture: two distinct card review requests, Лампа and Компас, each prepared but not sent. No reply has arrived.','rpc','trusted-synthetic-fixture').source_handle;
let n=0;const row=id=>core.read(id).data;const send=(ops,ids=[],tokens=[])=>core.commit({request_id:'pair-'+(++n),reason:'Explicit mechanical setup of two similar prepared requests, not model behavior',source_handles:[source],guards:ids.map(id=>({ref:{id},expected_revision:row(id).revision})),claim_tokens:tokens,ops});
const claim=(id,purpose)=>core.claim({action:'acquire',work_id:id,expected_revision:row(id).revision,purpose,step_id:'prepare',reason:'Local synthetic preparation recording'}).data.token;
try{
 const origin=send([{op:'import_evidence',client_ref:'input',source_handle:source,title:'Mechanical pair fixture source',source_language:'en'}]).created.input;
 const refs=[];
 for(const name of ['Лампа','Компас']){
  const id=send([{op:'create_record',client_ref:'w',kind:'work',title:'Review the '+name+' card',visibility:'workspace',data:{activity_id:null,parent_work_id:null,objective:'Obtain a separate clarity review of the '+name+' card',acceptance:[{criterion_id:'review',description:'Review reply received for this card',verification:'Inspect addressed external Evidence',required:true}],status:'active',current_state:'Prepare a manual request',next_action:'Prepare the message without sending',steps:[{step_id:'prepare',intent:'Prepare a manual review request; send nothing',required:false,status:'todo',depends_on:[],result_refs:[]},{step_id:'review',intent:'Receive and inspect the external clarity review',status:'todo',depends_on:[{step_id:'prepare'}],result_refs:[]}],waits:[{wait_id:'external-review',kind:'external_result',target:{step_id:'review'},subject:'Separate review for '+name,satisfied_by:'Clarity assessment and any needed correction are received',received_refs:[],question:'What is the separate review for this card?',status:'pending'}],context_refs:[{id:origin}],completion:null}}]).created.w;
  const h=send([{op:'prepare_handoff',client_ref:'h',work_ref:{id},step_id:'prepare',objective:'Review the '+name+' card',conditions:'Manual transfer only; not sent',expected_result:'Clarity and needed correction',context_refs:[{id:origin}],message:'Проверь карточку «'+name+'»: «Записывай наблюдение отдельно от объяснения». Понятна ли формулировка и нужна ли правка?'}],[id],[claim(id,'handoff')]).created.h;
  send([{op:'transition_step',ref:{id},step_id:'prepare',status:'done',reason:'Saved request reused, not sent',result_refs:[{id:h}]},{op:'transition_step',ref:{id},step_id:'review',status:'waiting',reason:'Separate external response missing'},{op:'transition_work',ref:{id},status:'waiting',reason:'Preparation done; await this card review'}],[id],[claim(id,'step')]);
  refs.push({name,work:row(id),handoff:core.handoff(h).data});
 }
 writeFileSync(join(root,'pair-fixture.json'),JSON.stringify({synthetic:true,mechanical_setup:true,model_actions:false,reason:'Attempt 06 failed all four provider dispatch attempts with fetch failed; no domain records existed. This fixture enables the two remaining model attempts to test ambiguity and clarified binding.',refs},null,2));
 console.log('Two mechanical handoffs prepared with real claims/receipts; no model request');
}finally{disk.close();}

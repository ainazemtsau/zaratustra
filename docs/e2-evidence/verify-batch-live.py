import json,pathlib,hashlib
b=pathlib.Path(__file__).parent
load=lambda p:json.loads(p.read_text(encoding='utf-8-sig'))
lines=lambda p:[json.loads(s)for s in p.read_text(encoding='utf-8-sig').splitlines()] if p.exists()else []
rows=lambda n,t:[json.loads(r['json'])for r in load(b/'attempts'/n/'summary.json')['database'][t]]
events=lambda n:lines(b/'attempts'/n/'events.jsonl')
starts=lambda n,t:[e for e in events(n)if e['type']=='tool_execution_start' and e['toolName']==t]
checks=[]
for n,prefix,target,serial in [('live-10','Copper lamp sleeve Ω','Optics reference lamp','E2-B62'),('live-12','Violet lamp sleeve Ω','Optics calibration lamp','E2-V73')]:
 records=rows(n,'records');source=next(r for r in records if r['title']==prefix);dest=next(r for r in records if r['title']==target+' '+serial)
 assert dest['data']['external_ids']['serial']==serial and dest['data']['disambiguation']=='Verified synthetic marking '+serial
 assert source['data']['status']=='merged' and source['data']['redirect_to']['id']==dest['id']
 assert prefix in dest['data']['aliases'] and target in dest['data']['aliases']
 history=rows(n,'revisions');old=next(r for r in history if r['id']==dest['id']and r['revision']==1);assert old['title']==target and old['data']['external_ids']['serial']=='unknown'
 proposals=starts(n,'zara_preview');assert len(proposals)==1
 ops=proposals[0]['args']['request']['ops'];assert [o['op']for o in ops]==['update_record','merge_identity']
 dialogs=lines(b/'attempts'/n/'dialogs.jsonl');assert len(dialogs)==1 and dialogs[0]['answer'] and dialogs[0]['matches_expected_consequence'];assert 'Destination identity:'in dialogs[0]['message'] and 'Verified synthetic marking '+serial in dialogs[0]['message']
 checks.append({'attempt':n,'single_exact_correct_then_merge_batch':True,'corrected_fields_actual':True,'stable_ID_history_aliases_actual':True,'preview_corrected_destination_actual':True})
for n,sourceName,targetName,workName,purpose in [('live-11','Copper notes area','Optics labeling area','Prepare source label','Labeling optical source notes'),('live-13','Violet notes area','Optics calibration area','Prepare calibration label','Labeling optical calibration notes')]:
 records=rows(n,'records');source=next(r for r in records if r['title']==sourceName);dest=next(r for r in records if r['title']==targetName);work=next(r for r in records if r['title']==workName)
 assert source['data']['status']=='merged'and source['data']['redirect_to']['id']==dest['id']and dest['data']['purpose']==purpose
 assert work['data']['activity_id']['id']==dest['id']and work['origin_activity_id']['id']==source['id']
 old=next(r for r in rows(n,'revisions')if r['id']==work['id']and r['revision']==1)
 assert old['data']['activity_id']['id']==source['id']
 for k in ['objective','priority','status']:assert work['data'][k]==old['data'][k]
 proposals=starts(n,'zara_preview');assert len(proposals)==1;ops=proposals[0]['args']['request']['ops'];assert [o['op']for o in ops]==['update_record','merge_activity'];assert ops[1]['moved_work_refs']==[{'id':work['id']}]
 dialogs=lines(b/'attempts'/n/'dialogs.jsonl');assert len(dialogs)==1 and dialogs[0]['answer']and dialogs[0]['matches_expected_consequence']
 checks.append({'attempt':n,'single_exact_purpose_then_activity_merge_batch':True,'purpose_and_only_moved_Work_actual':True,'origin_history_goal_priority_preserved':True})
(b/'BATCH-L-VERIFICATION.json').write_text(json.dumps({'executor_qualification_only':True,'code_refs':{'live-10/11':'85e44c1859421ff0815fb845b3c2c6553860c2a5','live-12/13':'d6a3187163c385c3c45f5fb89f7279dfbf636ced'},'checks':checks},indent=2),encoding='utf-8')
print(json.dumps({'checks':len(checks),'actual_saved_batch_fields':True}))

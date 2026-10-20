from pathlib import Path
import json,hashlib,sys
root=Path(sys.argv[1]);out=Path(sys.argv[2]);assert not out.exists()
read=lambda p:json.loads(p.read_text(encoding='utf-8-sig'))
lines=lambda p:[json.loads(l) for l in p.read_text(encoding='utf-8-sig').splitlines() if l.strip()]
cases=sorted(p for p in (root/'live').iterdir() if (p/'summary.json').exists())
report={'synthetic':True,'mechanical_verification_of_actual_model_runs':True,'final_execution_candidate':'55fac403fd4aba2f6e6ccb81d4e569ec5c0fde33','attempts':[]}
previous={'prompts':0,'requests':0,'estimated_usd':0,'input':0,'output':0,'cache_read':0};pids=[]
for folder in cases:
 s=read(folder/'summary.json');identity=lines(folder/'identity.jsonl')[0];startup=lines(folder/'startup.jsonl')[0];resources=lines(folder/'resources.jsonl')[0];requests=lines(folder/'requests.jsonl');provider=lines(folder/'provider-requests.jsonl');events=lines(folder/'events.jsonl')
 assert s['settled'] and s['permanent_snapshot_count']==0
 assert startup['messages_before_prompt']==[]
 assert identity['os_cwd'].replace('\\','/').casefold()==identity['sdk_cwd'].replace('\\','/').casefold()
 assert identity['provider']=='openai-codex' and identity['model']=='gpt-6.1-sol' and identity['thinking']=='medium'
 assert not resources['errors']
 assert len([p for p in resources['extension_paths'] if p!='<inline:1>'])==1
 assert {x['name'] for x in resources['skills']}=={'zaratustra-work','zaratustra-memory'}
 assert all(len(q['snapshots'])==1 and q['bootstrap_occurrences']==1 for q in requests)
 b=s['budget'];delta={k:b[k]-previous[k] for k in previous};assert delta['prompts']==1;assert delta['requests']==len(provider)
 errors=[e for e in events if e['type']=='tool_execution_end' and e.get('isError')]
 report['attempts'].append({'name':folder.name,'public_candidate':('d3dc6c38b02ba6e91c1037bdf1ed074b9be3c3b3' if int(folder.name[:2])<=3 else 'fe8271d41228dc67cdcd12fc1e9d8a04ac36c40b' if int(folder.name[:2])<=5 else report['final_execution_candidate']),'pid':identity['pid'],'empty_transcript':True,'os_and_sdk_cwd_match':True,'provider_requests':delta['requests'],'usage':delta,'tool_errors':errors,'response':s['response'],'permanent_snapshots':0})
 pids.append(identity['pid']);previous={k:b[k] for k in previous}
assert len(set(pids))==len(pids)
report['totals_from_completed_attempts']=previous
summary=lambda name:read(root/'live'/name/'summary.json')
records=lambda name:{r['id']:json.loads(r['json']) for r in summary(name)['database']['records']}
a=records('06-qualified-plan');b=records('07-qualified-partial');c=records('08-pause-goal');d=records('09-late-paused');f=records('11-cancel-late');done=records('12-complete');reopen=records('13-reopen')
parent=next(r for r in a.values() if r['kind']=='work' and r['data']['parent_work_id'] is None)
children=[r for r in a.values() if r['kind']=='work' and r['data']['parent_work_id'] and r['data']['parent_work_id']['id']==parent['id']]
assert len(children)==2 and sorted(x['data']['status'] for x in children)==['done','waiting']
assert any(w.get('status')=='partial' for r in b.values() if r['kind']=='work' for w in r['data']['waits'])
assert c[parent['id']]['data']['status']=='paused' and d[parent['id']]['data']['status']=='paused'
assert all(b[x['id']]==c[x['id']] for x in children)
assert d[parent['id']]['data']['objective']==c[parent['id']]['data']['objective']
late=[r for r in d.values() if r['data'].get('handoff_reply',{}).get('disposition')=='late'];assert late and all(r['data']['handoff_reply']['stale'] for r in late)
assert all(r['data']['source_kind']=='external_reply' and r['data']['provenance']['transport']=='rpc' for r in late)
assert f[parent['id']]['data']['status']=='cancelled' and f[parent['id']]['data']['completion'] is None and f[parent['id']]['data']['cancellation']['consequences']
review=next(x for x in children if x['data']['status']=='waiting');assert f[review['id']]['data']['status']=='cancelled'
completed=next(r for r in done.values() if r['kind']=='work' and r['data']['parent_work_id'] is None and r['data']['status']=='done')
completed_children=[r for r in done.values() if r['kind']=='work' and r['data']['parent_work_id'] and r['data']['parent_work_id']['id']==completed['id']]
assert len(completed_children)==2 and all(r['data']['status']=='done' for r in completed_children)
assert all(any(g['criterion_id']==criterion['criterion_id'] for g in completed['data']['completion']['grounds']) for criterion in completed['data']['acceptance'] if criterion['required'])
assert all(ref.get('revision') for g in completed['data']['completion']['grounds'] for ref in g['evidence_refs'])
assert reopen[completed['id']]['data']['status']=='active' and reopen[completed['id']]['data']['completion'] is None
historical=next(json.loads(r['json']) for r in summary('13-reopen')['database']['revisions'] if r['id']==completed['id'] and r['revision']==completed['revision']);assert historical==completed
report['work_assertions']={'nested_independent_success_while_other_child_waits':True,'partial_reply_keeps_remaining_waits':True,'pause_preserves_child_rows':True,'ancestor_goal_change_makes_reply_late':True,'late_response_does_not_resume':True,'cancelled_is_not_done':True,'required_children_complete_before_grounded_parent_close':True,'explicit_reopen_same_id_with_exact_historical_completion':True}
legacy=read(root/'qualified-upgrade-proof/predecessor-state.json')
for t,rows in legacy['tables'].items():
 if not rows:continue
 current=summary('15-read-books')['database'][t]
 assert all(row in current for row in rows),(t,'old row changed')
report['upgrade_all_original_rows_exact_after_live_new_formats']=True
materials=read(root/'live-materials-manifest.json')['materials'];bookrows=records('15-read-books');events=lines(root/'live/15-read-books/events.jsonl');payloads=lines(root/'live/15-read-books/provider-requests.jsonl');snapshots=lines(root/'live/15-read-books/requests.jsonl');scenario=read(root/'scenarios/15-read-books.json')
hidden=['L-42','M-73','LICHEN-2948','R-17','QUARTZ-6815']
assert all(v not in scenario['prompt'] for v in hidden)
assert all(v not in json.dumps(q,ensure_ascii=False) for q in snapshots for v in hidden)
reads=[]
for e in events:
 if e['type']=='tool_execution_end' and e['toolName']=='zara_read':
  data=e.get('result',{}).get('details',{}).get('data',{})
  if 'text' not in data:continue
  ref=data['ref'];r=bookrows[ref['id']];assert ref['revision']==1
  blob=(root/'qualified-upgrade-home/materials'/r['data']['blob_ref']).read_bytes();text=blob.decode('utf8');assert hashlib.sha256(blob).hexdigest()==r['data']['content_hash']
  at=data['global_start'];assert data['text']==text[at:at+len(data['text'])]
  reads.append({'ref':ref,'locator':data.get('locator'),'global_start':at,'characters':len(data['text']),'exact_text_from_managed_derivative':True,'contains':[v for v in hidden if v in data['text']]})
assert set(v for x in reads for v in x['contains'])==set(hidden)
for value in hidden:
 first=next(i for i,p in enumerate(payloads) if value in json.dumps(p,ensure_ascii=False))
 p=payloads[first]['payload'];outputs=[x for x in p['input'] if x.get('type')=='function_call_output' and value in x.get('output','')]
 assert outputs and any(x.get('type')=='function_call' and x.get('name')=='zara_read' and x.get('call_id')==o['call_id'] for o in outputs for x in p['input'])
 assert value in summary('15-read-books')['response']
for m in materials:
 original=bookrows[m['original_ref']['id']];derived=bookrows[m['derived_ref']['id']];assert original['data']['content_hash']==m['source_sha256'];assert derived['data']['derived_from']==m['original_ref'];assert derived['data']['source_hash']==m['source_sha256'];assert not Path(original['data']['source_locator']).exists()
 assert hashlib.sha256((root/'qualified-upgrade-home/materials'/m['source_sha256']).read_bytes()).hexdigest()==m['source_sha256']
assert not any(e['type']=='tool_execution_start' and e['toolName']=='zara_read' and e.get('args',{}).get('range') for e in lines(root/'live/14-retain-books/events.jsonl'))
assert len([r for r in records('14-retain-books').values() if r['kind']=='work'])==1
report['materials_assertions']={'originals_exact_and_source_paths_gone':True,'separate_addressed_text_and_parser_metadata':True,'actual_model_managed_reads':reads,'answers_absent_question_snapshots_cards_before_reads':True,'provider_answers_arrive_via_actual_zara_read_outputs':True,'all_original_predecessor_rows_preserved':True,'retention_created_no_work':True}
if (root/'live/17-ambiguous-return/summary.json').exists():
 ambiguous=summary('17-ambiguous-return');assert 'Север' in ambiguous['response'] and 'Юг' in ambiguous['response']
 assert not any(r['data'].get('handoff_reply') for r in records('17-ambiguous-return').values())
 report['ambiguity_asks_without_target_guess']=True
out.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf8');print(json.dumps({'verified_attempts':len(cases),'requests':previous['requests'],'estimated_usd':previous['estimated_usd'],'work':True,'materials':True,'output':out.name}))

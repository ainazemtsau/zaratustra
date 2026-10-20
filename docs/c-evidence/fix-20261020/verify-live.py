from pathlib import Path
import json,sys
r=Path(sys.argv[1]);out=Path(sys.argv[2]);assert not out.exists()
read=lambda p:json.loads(p.read_text(encoding='utf-8-sig'))
lines=lambda p:[json.loads(l) for l in p.read_text(encoding='utf-8-sig').splitlines() if l]
names=sorted(p.name for p in (r/'live').iterdir() if (p/'summary.json').exists())
summaries={n:read(r/'live'/n/'summary.json') for n in names}
records=lambda n:{a['id']:json.loads(a['json']) for a in summaries[n]['database']['records']}
handoffs=lambda n:[json.loads(a['json']) for a in summaries[n]['database']['handoffs']]
works=lambda n:[a for a in records(n).values() if a['kind']=='work']
report={'synthetic':True,'actual_public_candidate':'14c4e0d263542344c9d577ef4035fefba5afcac4','mechanical_readback_of_actual_model_actions':True,'attempts':[],'assertions':{}}
prev={k:0 for k in ['prompts','requests','input','output','cache_read','estimated_usd']};pids=[]
for n in names:
 s=summaries[n];es=lines(r/'live'/n/'events.jsonl');identity=lines(r/'live'/n/'identity.jsonl')[0];startup=lines(r/'live'/n/'startup.jsonl')[0];qs=lines(r/'live'/n/'requests.jsonl');ps=lines(r/'live'/n/'provider-requests.jsonl')
 assert startup['messages_before_prompt']==[] and s['settled'] and s['permanent_snapshot_count']==0
 assert identity['provider']=='openai-codex' and identity['model']=='gpt-6.1-sol' and identity['thinking']=='medium'
 assert identity['os_cwd'].replace('\\','/').casefold()==identity['sdk_cwd'].replace('\\','/').casefold()
 assert all(len(q['snapshots'])==1 and q['bootstrap_occurrences']==1 for q in qs)
 delta={k:s['budget'][k]-prev[k] for k in prev};assert delta['prompts']==1
 aborted=any(e.get('type')=='agent_settled' and e.get('aborted') for e in es)
 blocked=len(ps)-delta['requests'];assert blocked in [0,1] and (not blocked or aborted)
 errs=[e for e in es if e.get('type')=='tool_execution_end' and e.get('isError')]
 report['attempts'].append({'name':n,'pid':identity['pid'],'empty_transcript':True,'usage_delta':delta,'tool_errors':errs,'response':s.get('response'),'aborted':aborted,'blocked_payloads_not_sent':blocked,'assistant_errors':[e['message'].get('errorMessage') for e in es if e.get('type')=='message_end' and e.get('message',{}).get('role')=='assistant' and e['message'].get('errorMessage')]})
 pids.append(identity['pid']);prev={k:s['budget'][k] for k in prev}
assert len(set(pids))==len(pids);report['budget']=prev
first=works('01-prepare')[0];wid=first['id'];h=handoffs('01-prepare')[0]
prep=next(s for s in first['data']['steps'] if any(ref['id']==h['handoff_id'] for ref in s['result_refs']))
assert prep['status']=='done' and h['transport_state']=='prepared_not_sent' and len(handoffs('01-prepare'))==1
pending=lambda w:[x for x in w['data']['waits'] if x.get('status','pending') in ['pending','partial']]
assert first['data']['status']=='waiting' and pending(first)
assert all(not isinstance(x['target'],dict) or x['target']['step_id']!=prep['step_id'] for x in pending(first))
assert not any(a['kind']=='evidence' and a['data'].get('source_kind')=='generated_artifact' for a in records('01-prepare').values())
assert summaries['02-continue']['database']==summaries['01-prepare']['database']
report['assertions']['preparation_done_uses_original_handoff_no_duplicate_message']=True
report['assertions']['separate_response_wait_and_restart_no_database_changes']=True
report['preparation_after']={'work_id':wid,'revision':first['revision'],'status':first['data']['status'],'steps':first['data']['steps'],'waits':first['data']['waits'],'handoff':h}
if '03-complete' in names:
 done=records('03-complete')[wid];assert done['data']['status']=='done' and done['data']['completion']
 report['completed_before_reopen']=done
if '04-reopen' in names:
 reopened=records('04-reopen')[wid];done=records('03-complete')[wid]
 assert reopened['data']['status']=='waiting' and reopened['data']['completion'] is None
 newwait=[w for w in pending(reopened) if w['wait_id'] not in {x['wait_id'] for x in done['data']['waits']}];assert len(newwait)==1
 old=next(json.loads(a['json']) for a in summaries['04-reopen']['database']['revisions'] if a['id']==wid and a['revision']==done['revision']);assert old==done
 generated=lambda n:{i:a for i,a in records(n).items() if a['kind']=='evidence' and a['data'].get('source_kind')=='generated_artifact'}
 assert generated('04-reopen')==generated('03-complete')
 assert handoffs('04-reopen')==handoffs('03-complete')
 assert reopened['data']['steps']==done['data']['steps']
 report['assertions']['explicit_reopen_new_pending_wait_old_completion_and_result_exact']=True
 report['reopened_after']={'id':wid,'revision':reopened['revision'],'status':reopened['data']['status'],'steps':reopened['data']['steps'],'waits':reopened['data']['waits']}
if '05-clarification' in names:
 later=records('05-clarification')[wid];waitid=newwait[0]['wait_id'];resolved=next(w for w in later['data']['waits'] if w['wait_id']==waitid)
 assert resolved['status']=='satisfied' and resolved['received_refs']
 assert len(later['data']['waits'])==len(reopened['data']['waits']) and handoffs('05-clarification')==handoffs('04-reopen')
 for ref in resolved['received_refs']:assert records('05-clarification')[ref['id']]['kind']=='evidence'
 assert all(a in summaries['05-clarification']['database']['revisions'] for a in summaries['04-reopen']['database']['revisions'])
 report['assertions']['later_clarification_satisfies_exact_new_wait_without_new_handoff']=True
 report['clarified_after']={'id':wid,'revision':later['revision'],'status':later['data']['status'],'steps':later['data']['steps'],'waits':later['data']['waits']}
if '06-two-handoffs' in names and summaries['06-two-handoffs'].get('response'):
 hs=handoffs('06-two-handoffs');assert len(hs)==2 and len({h['work_ref']['id'] for h in hs})==2
 assert all(w['data']['status']=='waiting' and pending(w) for w in works('06-two-handoffs'))
 for h in hs:
  owner=records('06-two-handoffs')[h['work_ref']['id']]
  assert any(s['status']=='done' and any(ref['id']==h['handoff_id'] for ref in s['result_refs']) for s in owner['data']['steps'])
 report['assertions']['two_preparations_done_and_independent_response_waits']=True
if '07-ambiguous' in names:
 assert all(not a['data'].get('handoff_reply') for a in records('07-ambiguous').values())
 assert 'Лампа' in summaries['07-ambiguous']['response'] and 'Компас' in summaries['07-ambiguous']['response']
 fixture=read(r/'pair-fixture.json'); assert works('07-ambiguous')==[x['work'] for x in fixture['refs']]
 report['ambiguity_setup']='explicit mechanical pair fixture after failed transport attempt 06, not model preparation'
 report['assertions']['ambiguous_reply_asks_no_guess']=True
if '08-clarified' in names and not report['attempts'][-1]['aborted']:
 replies=[a for a in records('08-clarified').values() if a['data'].get('handoff_reply')];assert len(replies)==1
 chosen=replies[0]['data']['handoff_reply']['current_work_ref']['id']
 h=next(h for h in handoffs('08-clarified') if h['work_ref']['id']==chosen);assert 'Компас' in h['message'] or 'Компас' in h['objective']
 other=next(w for w in works('07-ambiguous') if w['id']!=chosen)
 assert records('08-clarified')[other['id']]==other and pending(other)
 assert handoffs('08-clarified')==handoffs('07-ambiguous')
 report['assertions']['clarified_reply_binds_only_compass_other_work_exact_and_waiting']=True
 report['ambiguity_after']={'reply':replies[0],'chosen_work':records('08-clarified')[chosen],'other_work':other}
out.write_bytes((json.dumps(report,ensure_ascii=False,indent=2)+'\n').encode())
print(json.dumps({'verified_attempts':len(names),'requests':prev['requests'],'estimated_usd':prev['estimated_usd'],'assertions':report['assertions']}))

from pathlib import Path
import json, collections, hashlib
R=Path(__file__).parent
def load(p): return json.loads(p.read_text('utf-8-sig'))
def lines(p): return [json.loads(s) for s in p.read_text('utf-8').splitlines()] if p.exists() else []
def visible(v):
 if isinstance(v,list): return [visible(x) for x in v if not isinstance(x,dict) or x.get('type') not in ('thinking','redactedThinking','reasoning')]
 if isinstance(v,dict): return {k:visible(x) for k,x in v.items() if k not in ('signature','encrypted_content')}
 return v
def result(e):
 r=e.get('result',{})
 if isinstance(r,dict) and 'details' in r: return r['details']
 for c in r.get('content',[]):
  if c.get('type')=='text':
   try:return json.loads(c['text'])
   except ValueError:pass
 return r
runs=[]
for folder in sorted((R/'live').iterdir()):
 if not (folder/'summary.json').exists():continue
 summary=load(folder/'summary.json');events=lines(folder/'events.jsonl');requests=lines(folder/'requests.jsonl');startup=lines(folder/'startup.jsonl')[0]
 assert startup['messages_before_prompt']==[],folder.name
 assert summary['settled'] and summary['permanent_snapshot_count']==0,folder.name
 starts=[e for e in events if e.get('type')=='tool_execution_start']
 ends=[e for e in events if e.get('type')=='tool_execution_end']
 records=[json.loads(r['json']) for r in summary['database']['records']]
 reads=[result(e) for e in ends if e.get('toolName')=='zara_read' and not e.get('isError')]
 errors=[dict(tool=e.get('toolName'),result=result(e)) for e in ends if e.get('isError')]
 before=load(folder/'controller-before.json') if (folder/'controller-before.json').exists() else None
 after=load(folder/'controller-after.json') if (folder/'controller-after.json').exists() else None
 if before:
  assert before['sha']==after['sha'] and after['exit']==0
  if 'delivery' in folder.name and int(folder.name[:2])>=10: assert before['sha']=='2e67880ccc6f52c22ee99f38a12f232a5e8a9f9e'
  if 'release' in folder.name or 'scoped' in folder.name: assert before['sha']=='2e67880ccc6f52c22ee99f38a12f232a5e8a9f9e'
 run=dict(name=folder.name,sha=before['sha'] if before else 'a17a399baed2eb2e49a239d14a13350ba0371e93',response=summary['response'],tools=dict(collections.Counter(e['toolName'] for e in starts)),tool_errors=errors,read_refs=[r.get('data',{}).get('id') or r.get('data',{}).get('ref') for r in reads],zara_read_bytes=sum(len(c.get('text','').encode()) for e in ends if e.get('toolName')=='zara_read' for c in e.get('result',{}).get('content',[])),max_snapshot_bytes=max((len(x['content'].encode()) for q in requests for x in q.get('snapshots',[])),default=0),memory_query_bytes=sum(len(c.get('text','').encode()) for e in ends if e.get('toolName') in ('zara_map','zara_browse','zara_search') for c in e.get('result',{}).get('content',[])),records=len(records),request_count=len(lines(folder/'provider-requests.jsonl')),reported_messages=sum(e.get('type')=='message_end' and e.get('message',{}).get('role')=='assistant' for e in events),retries=[e for e in events if e.get('type') in ('auto_retry_start','auto_retry_end')])
 if folder.name in ('02-origin-save','05-final-origin','07-delivery-origin','21-scoped-save'):
  assert any(r['kind']=='activity' and r['title']=='Workshop' for r in records)
  assert any(r['kind']=='knowledge' and r['origin_activity_id'] and 'weekday' in r['data']['statement'].lower() for r in records)
  assert any(r['kind']=='evidence' and r['data']['retained_excerpt']==load(R/(folder.name+'.json'))['prompt'] for r in records)
 if folder.name in ('03-cross-area','06-final-cross','08-delivery-cross','22-scoped-cross'):
  prompt=load(R/(folder.name+'.json'))['prompt'];assert all(key not in prompt for key in ['Парус','Роса','risograph'])
  # Only the initial request snapshot must lack the answer; a later model-saved plan can include what was read.
  initial=json.dumps(requests[0].get('snapshots',[]),ensure_ascii=False)
  assert 'Роса-73' not in initial and 'Парус-41' not in initial
  first=next(e for e in ends if 'Роса-73' in json.dumps(visible(e.get('result')),ensure_ascii=False))
  assert first['toolName']=='zara_read',first['toolName']
  assert 'Роса-73' in summary['response'] and '10:00' in summary['response']
  assert len([r for r in records if r['kind']=='activity'])>=2
  run['answer_first_from']={'tool':first['toolName'],'result':result(first)}
 if folder.name in ('10-catalog','11-fallback','12-prohibited','13-identities','15-delivery-catalog','16-delivery-fallback','17-delivery-prohibited','18-delivery-identities','19-delivery-large'):
  config=load(R/(folder.name+'.json'));assert not any(s in config['prompt'] for s in ['Quiet Shore','Тихий берег','risograph','duplicator'])
  assert not any('risograph' in json.dumps(q.get('snapshots',[]),ensure_ascii=False) for q in requests)
  if folder.name in ('10-catalog','15-delivery-catalog'): assert any(e['toolName']=='zara_browse' and e['args'].get('view') in ['resources','topics'] for e in starts)
  if folder.name in ('11-fallback','16-delivery-fallback','19-delivery-large'):
   assert any(e['toolName']=='zara_search' for e in starts)
   assert any('risograph' in json.dumps(r) for r in reads)
  if folder.name in ('12-prohibited','17-delivery-prohibited'): assert 'воскрес' in summary['response'].lower()
  if folder.name in ('15-delivery-catalog','16-delivery-fallback','19-delivery-large'):
   key='Weekdays only, prior booking; unavailable on Sunday.'
   first=next(e for e in ends if key in json.dumps(visible(e.get('result')),ensure_ascii=False))
   assert first['toolName']=='zara_read',first['toolName']
   run['condition_first_from']={'tool':first['toolName'],'result':result(first)}

 if folder.name in ('12-delivery-recording-error','14-delivery-example-retract'):
  target='Лира-9' if folder.name.startswith('12') else 'Мята-8'
  personal=[x for x in records if x['kind']=='knowledge' and target in json.dumps(x,ensure_ascii=False)]
  assert any(x['data']['state']=='retracted' for x in personal)
  historical=[json.loads(x['json']) for x in summary['database']['revisions']]
  old=[x for x in historical if x['kind']=='knowledge' and x['revision']==1 and target in x['data'].get('statement','')]
  assert any(x['data']['state']=='current' for x in old)
  run['correction_current']=[dict(id=x['id'],revision=x['revision'],state=x['data']['state'],statement=x['data']['statement'],conditions=x['data']['conditions']) for x in personal]
  run['prior_versions_preserved']=[dict(id=x['id'],revision=x['revision'],state=x['data']['state']) for x in old]
 if folder.name=='20-release-origin':
  assert records==[] and any(e['result'].get('code')=='PERMISSION_DENIED' for e in errors)
  run['outcome']='failed ordinary-save qualification in workspace-only scope; truthful denial, no domain commit'
 if folder.name=='23-scoped-changed':
  run['current_state_proof']='scoped-state-proof.json'
 runs.append(run)
out={'synthetic':True,'runs':runs,'budget':load(R/'budget.json'),'scope':'Executor observations, not independent PASS or owner acceptance'}
(R/'live-verification.json').write_text(json.dumps(out,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps({'runs':len(runs),'tool_errors':sum(len(r['tool_errors']) for r in runs),'requests':sum(r['request_count'] for r in runs),'ledger':out['budget']},ensure_ascii=False))

from pathlib import Path
import json,hashlib,datetime
r=Path(r'<SYNTHETIC_EVIDENCE_ROOT>');j=lambda p:json.loads((r/p).read_text(encoding='utf-8'))
a=j('attempts.json');b=j('budget.json');v=j('live-verification.json');sc={x['scenario']:x for x in v['scenarios']}
checks=[]
def ok(name,condition):
 assert condition,name
 checks.append({'check':name,'observed':True})
rows=lambda name: {x['id']:x for key in ['methods','runs','invocations','evaluations','signals','reviews','results'] for x in sc[name][key]}
final=sc['11-final-read'];f=rows('11-final-read');method=final['methods'][0]
ok('same Method reached content version 3',method['data']['content_version']==3)
for name,cv in [('01-create-apply',1),('02-fresh-discovery',1),('03-correct-and-apply',2),('06-failure',2),('10-epsilon-discovery',3),('13-zeta-discovery',3)]:
 old=[]
 for x in v['scenarios']:
  if x['scenario']==name:break
  old=[i['id'] for i in x['invocations']]
 new=[i for i in sc[name]['invocations'] if i['id'] not in old]
 ok(name+' exact new invocation version',len(new)==1 and new[0]['data']['method_ref']['content_version']==cv)
 ok(name+' exact selected closure and actual retained observation',new[0]['data']['selected_versions']==[new[0]['data']['method_ref']] and bool(new[0]['data']['observation_refs']) and bool(sc[name]['actual_retained_observations']))
 ok(name+' actual application report distinct from observation',new[0]['data']['reported_application']['applied'] is True)
for name in ['04-late-feedback','05-correct-feedback','07-correction-not-resolution','08-read-and-foreign-report','09-correction-continuation','12-correction-links','11-final-read']:
 idx=next(i for i,x in enumerate(v['scenarios']) if x['scenario']==name);prev=v['scenarios'][idx-1]
 ok(name+' no new invocation',[x['id'] for x in sc[name]['invocations']]==[x['id'] for x in prev['invocations']])
 if name not in ['07-correction-not-resolution','09-correction-continuation']:
  ok(name+' no new Run',[x['id'] for x in sc[name]['runs']]==[x['id'] for x in prev['runs']])
oldids=[x['id'] for x in j('old-application-preservation.json')['rows']]
def canonical(name):
 s=j('qualified-live/'+name+'/summary.json')
 return {x['id']:x['json'] for t in ['records','experience_rows'] for x in s['database'][t]}
c1=canonical('01-create-apply');cf=canonical('11-final-read')
ok('eight old source/result/Run/invocation/Evaluation rows byte-exact after v3',all(cf[x]==c1[x] for x in oldids))
late=f['evaluation-07bd806e-b2a1-49ae-99ea-d41d7baa5483'];mixed=f['evaluation-774c0135-fd51-4f0a-8e03-7cbdfe14a66e']
ok('late and superseding Evaluation target old exact result',late['data']['target_ref']==mixed['data']['target_ref']=={'id':'evidence-1cbb5195-c021-4cec-bfbf-bf63864be388','revision':1})
ok('correction preserves same target/dimension and supersedes history',mixed['data']['supersedes_evaluation_ref']['id']==late['id'] and mixed['data']['dimension']==late['data']['dimension'])
ok('all live feedback remains non-owner',all(x['data'].get('owner_feedback',False) is False and x['data']['basis']!='user_feedback' for x in final['evaluations']))
ok('Delta Signal remains open after edits and unrelated successful cases',f['signal-fbaab4a8-6f84-48cd-99d9-516727dfeb30']['data']['problem_state']=='open')
sumfinal=j('qualified-live/11-final-read/summary.json');primary=[json.loads(x['json']) for x in sumfinal['database']['records']]
w=next(x for x in primary if x['id']=='work-53890323-b0a4-41aa-ba3c-ae4909c794e3')
ok('Delta Work still waiting',w['data']['status']=='waiting')
ok('at least one failed Run retained',any(x['data']['execution']=='failed' for x in final['runs']))
runs={x['id']:x for x in final['runs']};cont=runs['run-659b5e23-41a4-4f2c-8f88-f5364ec26f74'];prior=runs['run-82c6a057-a3ac-443f-95c4-70f8f50d798f']
ok('correction continuation retains original case_id',cont['data']['case_id']==prior['data']['case_id'] and cont['data']['continuation_of']['id']==prior['id'])
encoded=json.dumps(sumfinal['database']['relations'])
ok('direct navigation to exact Method v3 and immutable review exists',method['id'] in encoded and 'signal_review-dd53e7ba-26d2-4a7e-90c8-f16715a70f87' in encoded)
requests=usage_count=0;cost=0.0;errors=[];retries=[];faults=[];usage_input=output=cache=0
transcript=['# Synthetic ordinary Pi/model conversations','All RPC prompts originate from an isolated synthetic controller, never Anton. No mutation JSON or prepared tool calls were placed in these prompts. All attempts share one never-reset ledger. Repeated candidate fixtures are not independent successful cases.','']
for attempt in a['attempts']:
 cfg=j(attempt['scenario']);d=Path(cfg['output']);s=json.loads((d/'summary.json').read_text(encoding='utf-8'));ev=[json.loads(x) for x in (d/'events.jsonl').read_text(encoding='utf-8').splitlines()]
 requests+=len((d/'provider-requests.jsonl').read_text(encoding='utf-8').splitlines())
 for e in ev:
  if e['type']=='tool_execution_end' and e.get('isError'):errors.append({'attempt':attempt['id'],'tool':e['toolName'],'result':e['result']})
  if e['type'].startswith('auto_retry'):retries.append(e)
  if e['type']=='message_end' and e['message']['role']=='assistant':
   u=e['message'].get('usage')
   if u:
    usage_count+=1;cost+=u.get('cost',{}).get('total',0);usage_input+=u.get('input',0)+u.get('cacheRead',0)+u.get('cacheWrite',0);output+=u.get('output',0);cache+=u.get('cacheRead',0)
   if e['message'].get('stopReason')=='error':faults.append(e)
 if (d/'faults.jsonl').exists():faults.extend((d/'faults.jsonl').read_text().splitlines())
 transcript.extend(['## '+attempt['id'],f'Code: {attempt["candidate"]}. Fixed scopes: {json.dumps(cfg.get("scopes",[]))}. Actual calls, refs and receipts: '+attempt['summary']+' and sibling events/requests.','', 'User/controller:', '',cfg['prompt'],'','Actual final model reply:','',s['response'],''])
ok('every attempt settled and counted in one ledger',all(x['status'].startswith('settled') for x in a['attempts']) and len(a['attempts'])==b['prompts'])
ok('actual provider-dispatch count matches ledger',requests==b['requests'])
ok('reported usage and Pi cost match untransformed actual events',usage_count==b['reported_usage_messages'] and abs(cost-b['estimated_usd'])<1e-9 and (usage_input,output,cache)==(b['input'],b['output'],b['cache_read']))
ok('no provider errors, automatic retries or timeouts',not faults and not retries)
ok('below every non-reset cap',b['prompts']<24 and b['requests']<180 and b['estimated_usd']<15)
(r/'CONVERSATIONS.md').write_text('\n'.join(transcript)+'\n',encoding='utf-8')
proof={'checks':checks,'code_attribution':{x['scenario']:x['candidate'] for x in v['scenarios']},'final_code':'6659f4c4d9de1871624efaec37933aa8d03dc0bf','synthetic_only':True,'real_owner_feedback':False,'T31':False,'budget':b,'tool_refusals':errors,'provider_errors':faults,'automatic_retries':retries,'scope':'First-hand engineering evidence, not independent PASS, owner acceptance, benefit improvement or proof of Method causality. Distinct fixture materials do not establish statistical independence.'}
(r/'story-checks.json').write_text(json.dumps(proof,ensure_ascii=False,indent=2),encoding='utf-8')
b.update(closed=True,closed_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),closure='All E1 live producers settled; no further dispatch authorized by this ledger after sealing.')
(r/'budget.json').write_text(json.dumps(b,indent=2),encoding='utf-8');a.update(status='closed',qualified_story='13 scenario continuations attributed to 7b06465/b528382/6659f4c; see story-checks.json; one unchanged profile and ledger');(r/'attempts.json').write_text(json.dumps(a,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps({'checks':len(checks),'attempts':b['prompts'],'dispatches':requests,'usd':cost,'tool_refusals':len(errors),'qualified_requests':sum(x['requests'] for x in v['scenarios']),'max_snapshot_bytes':max(x['max_snapshot_bytes'] for x in v['scenarios'])},indent=2))

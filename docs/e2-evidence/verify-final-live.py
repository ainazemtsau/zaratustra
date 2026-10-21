import pathlib,json,hashlib,datetime
b=pathlib.Path(__file__).parent
load=lambda p:json.loads(p.read_text(encoding='utf-8-sig'))
lines=lambda p:[json.loads(s)for s in p.read_text(encoding='utf-8-sig').splitlines()]if p.exists()else []
names=['live-01','live-01b',*[f'live-{i:02d}'for i in range(2,18)]]
events={n:lines(b/'attempts'/n/'events.jsonl')for n in names}
starts=lambda n,t:[e for e in events[n]if e['type']=='tool_execution_start'and e['toolName']==t]
ends=lambda n,t:[e for e in events[n]if e['type']=='tool_execution_end'and e['toolName']==t]
rows=lambda n,t:[json.loads(r['json'])for r in load(b/'attempts'/n/'summary.json')['database'][t]]
dispatch=0;cost=0;inputTokens=0;outputTokens=0;cache=0;native=[];attempts=[]
for n in names:
 a=b/'attempts'/n;identity=lines(a/'identity.jsonl')[0];assert identity['provider']=='openai-codex'and identity['model']=='gpt-6.1-sol'and identity['thinking']=='medium'
 assert identity['os_cwd']==identity['sdk_cwd'];assert lines(a/'startup.jsonl')[0]['messages_before_prompt']==[]
 count=len(lines(a/'provider-requests.jsonl'));dispatch+=count;owncost=0
 for e in events[n]:
  if e['type']=='message_end'and e['message']['role']=='assistant':
   u=e['message'].get('usage',{});v=u.get('cost',{}).get('total',0);cost+=v;owncost+=v;inputTokens+=u.get('input',0)+u.get('cacheRead',0)+u.get('cacheWrite',0);outputTokens+=u.get('output',0);cache+=u.get('cacheRead',0)
  if e['type']=='tool_execution_start'and e['toolName']in ['write','edit','powershell','bash']:native.append({'attempt':n,'name':e['toolName'],'args':e['args']})
 for d in lines(a/'dialogs.jsonl'):assert d['principal']=='isolated-synthetic-sdk-controller'and d['matches_expected_consequence']
 ref='0d6c9a2d604aec0f8b108841219c68369189315b'if n in names[:10]else '85e44c1859421ff0815fb845b3c2c6553860c2a5'if n in ['live-10','live-11']else 'd6a3187163c385c3c45f5fb89f7279dfbf636ced'
 attempts.append({'attempt':n,'public_code':ref,'pid':identity['pid'],'dispatches':count,'estimated_usd':owncost,'summary_present':(a/'summary.json').exists()})
assert len(names)==18
budget=load(b/'budget.json');assert budget['prompts']==18 and budget['requests']==dispatch and abs(cost-budget['estimated_usd'])<1e-8
assert inputTokens==budget['input']and outputTokens==budget['output']and cache==budget['cache_read']
assert budget['requests']<240 and budget['estimated_usd']<20
assert not any(e['name']!='write'for e in native)
assert len(native)==7
lost=load(b/'lost-before-recovery-d6a.json');assert lost['durable_attempt']['status']=='requested'and lost['postcondition_receipt_absent']
assert len(starts('live-14','write'))==1 and not (b/'attempts/live-14/summary.json').exists()
assert not starts('live-15','write')and not starts('live-15','edit');assert starts('live-15','zara_browse')[0]['args']['view']=='operations'
intent=next(e for e in rows('live-15','intents')if e.get('kind')=='managed_file'and e['payload']['target'].endswith('calibration-note.txt'))
assert intent['status']=='confirmed'and intent['receipt']['writer_attribution']=='unknown'and intent['interruption']
assert intent['request_id']not in lines(b/'attempts/live-15/identity.jsonl')[0]['prompt']
assert (b/'workspace/output/calibration-note.txt').read_bytes()=='Optics calibration C-73\nOriginal label: «Луч Ω»\nNext check: align the reference mark\n'.encode()
assert 'unknown'in str(ends('live-15','zara_read')[0]['result']['details'])
before=ends('live-16','zara_skill_inspect')[0]['result']['details'];assert before['drift']and not before['export_current'];assert not starts('live-16','write')
external=(b/'skill-drift-d6a/external-edit-v2.md').read_bytes();extHash=hashlib.sha256(external).hexdigest();assert (b/'workspace/home/materials'/extHash).read_bytes()==external
records=rows('live-17','records');method=next(r for r in records if r['kind']=='method'and r['title']=='Bench note check');assert method['data']['content_version']==3 and 'ambient temperature'in method['data']['instructions']
evidence=next(r for r in records if r['data'].get('blob_ref')==extHash);assert evidence['data']['provenance']['owner_channel_eligible']==False and evidence['data']['trust_origin']=='programmatic-or-file-not-owner-approval'
for version in [1,2]:assert any(r['id']==method['id']and r['data']['content_version']==version for r in rows('live-17','revisions'))
status=ends('live-17','zara_skill_inspect')[-1]['result']['details'];assert status['export_current']and not status['drift']and status['method_export']['method_ref']['content_version']==3
raw=(b/'workspace/output/SKILL.md').read_bytes();assert hashlib.sha256(raw).hexdigest()==status['method_export']['export_hash']
assert hashlib.sha256(json.dumps(method['data'],sort_keys=True,separators=(',',':'),ensure_ascii=False).encode()).hexdigest()==status['method_export']['content_hash']
report={'executor_qualification_only':True,'independent_verdict_not_assigned':True,'live_code_candidate':'d6a3187163c385c3c45f5fb89f7279dfbf636ced','all_18_attempts':attempts,'all_dispatch_and_usage_counters_reconcile':True,'single_non_reset_budget':budget,'actual_native_L_calls':native,'native_call_counts':{'write_starts':7,'stale_blocked':1,'native_writes':6,'lost_results':2},'final_code_lost_reply':{'current_bytes':91,'fresh_inspect_without_old_ID_or_write':True,'postcondition_confirmed_author_unknown':True},'final_code_textual_export':{'method_ID':method['id'],'version':3,'history_1_2_preserved':True,'external_Evidence_hash':extHash,'external_Evidence_bytes':len(external),'final_export_bytes':len(raw),'final_export_sha256':hashlib.sha256(raw).hexdigest(),'final_content_hash':status['method_export']['content_hash'],'export_current':True,'drift':False},'actual_billing':'unknown','cost_kind':'Pi estimate'}
(b/'FINAL-L-VERIFICATION.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
(b/'LIVE-CLOSED-FINAL.json').write_text(json.dumps({'closed_at':datetime.datetime.now(datetime.timezone.utc).isoformat(),'candidate':report['live_code_candidate'],'budget':budget,'budget_reset':False,'further_runtime_change_requires_affected_reruns_in_same_ledger':True},indent=2),encoding='utf-8')
print(json.dumps({'attempts':len(names),'dispatches':dispatch,'estimated_usd':cost,'final_export':report['final_code_textual_export']}))

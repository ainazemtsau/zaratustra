from pathlib import Path
import json,hashlib,sqlite3
r=Path(__file__).resolve().parent
names=['L01-save','L02-backup-A','L03-write-B','L04-restore-A','L05-fresh-readback','L06-new-generation-write','L07-unknown-readback','L08-archive-pins','L09-low-denial']
load=lambda p:json.loads(p.read_text(encoding='utf8').lstrip('\ufeff'))
lines=lambda p:[json.loads(x) for x in p.read_text(encoding='utf8').splitlines() if x.strip()]
events={n:lines(r/'live'/n/'events.jsonl') for n in names}
starts=lambda n:[e for e in events[n] if e['type']=='tool_execution_start']
ends=lambda n:[e for e in events[n] if e['type']=='tool_execution_end']
value=lambda e:e['result'].get('details',{})
summary=lambda n:load(r/'live'/n/'summary.json')
checks=[]
def ok(name, condition):
 assert condition,name
 checks.append(name)
for n in names:
 startup=lines(r/'live'/n/'startup.jsonl')[0]
 ok(n+' starts with empty transcript',startup['messages_before_prompt']==[])
 identity=lines(r/'live'/n/'identity.jsonl')[0]
 ok(n+' fixed recipient/effort',identity['provider']=='openai-codex' and identity['model']=='gpt-6.1-sol' and identity['thinking']=='medium')
 resources=lines(r/'live'/n/'resources.jsonl')[0]
 ok(n+' native package resources',not resources['errors'] and all('agent' in p for p in resources['extension_paths']))
a=load(r/'A-SNAPSHOT-PROOF.json');b=load(r/'B-WRITE-AND-LOSS-PROOF.json');rest=load(r/'RESTORED-A-BARRIER-PROOF.json');g=load(r/'GENERATION-WRITE-PROOF.json')
ok('A precedes all managed effect intents/output',a['managed_effect_intents']==0 and a['report_absent_before_B'])
ok('B actual bytes and requested intent retained before genuine loss',b['actual_world_bytes'] and b['current_database_missing'] and b['attempt']['status']=='requested' and b['attempt']['receipt'] is None and bool(b['retained_loss']))
ok('unavailable DB restores A into new epoch/generation with all required barriers',rest['managed_file_intents']==0 and all(x['status']=='required' for x in rest['required_barriers']) and 'generations' in rest['active_database'])
calls=[e['toolName'] for e in starts('L05-fresh-readback')]
ok('fresh continuation FIRST managed call is actual recovery inspection',next(x for x in calls if x.startswith('zara_'))=='zara_recovery_inspect')
ok('fresh continuation never repeats native effects',not set(calls)&{'write','edit','bash','powershell'})
inspect=next(value(e) for e in ends('L05-fresh-readback') if e['toolName']=='zara_recovery_inspect')
ok('actual current report bytes returned',inspect['current_text']=='Observatory: optics checked; result ready.\n')
barriers=[json.loads(x['json']) for x in summary('L05-fresh-readback')['database']['recovery_barriers']]
ok('only named action cleared; other barriers remain',sum(x['status']=='cleared' for x in barriers)==1 and any(x['status']=='required' for x in barriers))
ok('named native reconciliation committed',any(e['toolName']=='zara_reconcile' and value(e)['data']['committed'] for e in ends('L05-fresh-readback')))
fault=lines(r/'live/L06-new-generation-write/faults.jsonl')[0]
ok('new generation observer uses authoritative actual active database',fault['active_database']==g['active_database'] and 'generations' in g['active_database'] and fault['attempt']['request_id']==g['attempt']['request_id'])
ok('actual second native loss exits86',int((r/'L06-node-exit.txt').read_text())==86)
ok('fresh unknown recovery does not write',not {e['toolName'] for e in starts('L07-unknown-readback')}&{'write','edit','bash','powershell'})
operation=next(json.loads(x['json']) for x in summary('L07-unknown-readback')['database']['intents'] if x['request_id']==g['attempt']['request_id'])
ok('unknown current-state readback retains unknown author',operation['status']=='confirmed' and operation['receipt']['writer_attribution']=='unknown' and operation['current_observation']['postcondition_matches'])
arch=summary('L08-archive-pins');source=a['work']['data']['context_refs'][0]['id']
record=next(json.loads(x['json']) for x in arch['database']['records'] if x['id']==source)
ok('archive body retained and found explicitly',record['storage']=='archive' and any(e['toolName']=='zara_search' and e['args'].get('storage')=='archive' for e in starts('L08-archive-pins')))
refusal=[value(e) for e in ends('L08-archive-pins') if value(e).get('code')=='DEPENDENCY_UNSATISFIED']
ok('dangerous deletion has exact pinned-ground refusal',bool(refusal) and 'knowledge-' in refusal[0]['message'] and source in refusal[0]['message'])
ok('no silent obligation retirement',any(json.loads(x['json'])['kind']=='work' and json.loads(x['json'])['data']['status']=='active' for x in arch['database']['records']))
low=[value(e) for e in ends('L09-low-denial') if e['toolName']=='zara_backup']
ok('predeclared low setup refuses full backup',bool(low) and low[0]['code']=='PERMISSION_DENIED' and load(r/'scenarios/L09-low-denial.json')['scopes']==[])
ok('only two actual native writes across all conversations',sum(e['toolName']=='write' for n in names for e in starts(n))==2)
for name,proof in [('observatory-report.txt',b),('generation-check.txt',g)]:
 ok('final bytes unchanged '+name,hashlib.sha256((r/'profiles/protected/output'/name).read_bytes()).hexdigest()==proof['sha256'])
budget=load(r/'budget.json');dispatches=sum(len(lines(r/'live'/n/'provider-requests.jsonl')) for n in names)
ok('non-reset ledger matches every actual dispatch/attempt',budget['prompts']==len(names) and budget['requests']==dispatches)
ok('all first-cap limits preserved',budget['prompts']<=30 and budget['requests']<=240 and budget['estimated_usd']<=20)
errors=[{'attempt':n,'tool':e['toolName'],'code':value(e).get('code'),'message':value(e).get('message')} for n in names for e in ends(n) if e.get('isError')]
results={'code_sha':'01a111fd4cb7e82be782a63499e60580f541e7cf','checks':checks,'conversations':len(names),'provider_dispatches':dispatches,'budget':budget,'tool_refusals':errors,'L03_exit_note':'Outer PowerShell reported1 after frozen runner process.exit(86); actual Node status was not separately captured. Durable intent/native bytes/fault point/loss proof retained. L06 directly records86.','scope':'synthetic registered controller; no owner/T31/independent verdict'}
(r/'LIVE-VERIFICATION.json').write_text(json.dumps(results,ensure_ascii=False,indent=2),encoding='utf8')
print(json.dumps({'checks':len(checks),'conversations':len(names),'dispatches':dispatches,'estimated_usd':budget['estimated_usd'],'tool_refusals':len(errors)}))

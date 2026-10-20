from pathlib import Path
import json,hashlib,subprocess,sys,datetime
r=Path(r'<SYNTHETIC_EVIDENCE_ROOT>');p=r/'installed/agent/git/github.com/ainazemtsau/zaratustra'
mode,name=sys.argv[1:3];cfg=json.loads((r/'scenarios-qualified'/f'{name}.json').read_text(encoding='utf-8'));d=Path(cfg['output'])
head=subprocess.check_output(['git','-C',str(p),'rev-parse','HEAD'],text=True).strip()
assert head=='6659f4c4d9de1871624efaec37933aa8d03dc0bf'
paths=[p/'package.json',p/'package-lock.json']+[f for folder in ['src','instructions','skills'] for f in (p/folder).rglob('*') if f.is_file()]
hashes={f.relative_to(p).as_posix():hashlib.sha256(f.read_bytes()).hexdigest() for f in paths}
a=json.loads((r/'attempts.json').read_text(encoding='utf-8'));b=json.loads((r/'budget.json').read_text(encoding='utf-8'))
if mode=='begin':
 assert not d.exists();d.mkdir(parents=True)
 assert not any(x['scenario']==f'scenarios-qualified/{name}.json' for x in a['attempts'])
 (d/'controller-before.json').write_text(json.dumps({'head':head,'product_hashes':hashes},indent=2),encoding='utf-8')
 a['attempts'].append({'id':f'{len(a["attempts"])+1:02d}-{name}','scenario':f'scenarios-qualified/{name}.json','candidate':head,'status':'started','started_at':datetime.datetime.now(datetime.timezone.utc).isoformat()})
else:
 before=json.loads((d/'controller-before.json').read_text());assert hashes==before['product_hashes']
 s=json.loads((d/'summary.json').read_text(encoding='utf-8'));assert s['settled']
 (d/'controller-after.json').write_text(json.dumps({'head':head,'all_product_hashes_unchanged':True},indent=2),encoding='utf-8')
 q=next(x for x in a['attempts'] if x['scenario']==f'scenarios-qualified/{name}.json')
 q.update(status='settled',summary=f'qualified-live/{name}/summary.json',finished_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),cumulative_requests=b['requests'],cumulative_estimated_usd=b['estimated_usd'])
 print(json.dumps({'budget':b,'response':s['response']},ensure_ascii=False,indent=2))
(r/'attempts.json').write_text(json.dumps(a,ensure_ascii=False,indent=2),encoding='utf-8')

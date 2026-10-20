"""Seal only finished chosen evidence. Exporter stdout lives in excluded export-logs/."""
from pathlib import Path
import json,hashlib,os
r=Path(__file__).resolve().parent
paths=[]
paths += [p for p in r.glob('*.txt') if p.name!='spec-reading.txt']
paths += [p for p in r.glob('*.json') if p.name not in ['protected-inputs.json','sealed-inputs.json','FINAL-READBACK.json']]
paths += list(r.glob('*.mjs'))+list(r.glob('*.py'))
for folder in ['scenarios','review-inputs','source-snapshots','p2']:
 paths += list((r/folder).glob('*.json'))+list((r/folder).glob('*.txt'))
paths += list((r/'live').glob('*/*.json'))+list((r/'live').glob('*/*.jsonl'))
assert all('export-logs' not in p.parts for p in paths)
entries=[]
for p in sorted(set(paths)):
 b=p.read_bytes();entries.append({'path':p.relative_to(r).as_posix(),'bytes':len(b),'sha256':hashlib.sha256(b).hexdigest()})
sealed={'root':str(r),'redactions':[['<C_REVIEW_ROOT>','<C_REVIEW_ROOT>'],['<PREVIOUS_C_EVIDENCE_ROOT>','<PREVIOUS_C_EVIDENCE_ROOT>'],['<CHECKOUT>','<CHECKOUT>'],[os.environ['USERPROFILE'],'<USER_HOME>']],'entries':entries}
p=r/'sealed-inputs.json';assert not p.exists();p.write_bytes((json.dumps(sealed,ensure_ascii=False,indent=2)+'\n').encode())
print(json.dumps({'sealed_finished_sources':len(entries),'current_export_stdout_excluded':True}))

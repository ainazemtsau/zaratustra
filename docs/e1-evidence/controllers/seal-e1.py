from pathlib import Path
import json,hashlib,datetime
r=Path(r'<SYNTHETIC_EVIDENCE_ROOT>');repo=Path(r'<CHECKOUT>');h=lambda p:hashlib.sha256(p.read_bytes()).hexdigest();q=json.loads((r/'audit/preservation.json').read_text())
assert all(h(repo/x['path'])==x['sha256'] for x in q['entries'])
assert all(h(repo/x['copy'])==x['sha256'] for x in q['previous_current_copies'])
(r/'audit/final-preservation.json').write_text(json.dumps({'checked_at':datetime.datetime.now(datetime.timezone.utc).isoformat(),'all_1256_exact':True,'D_previous_current_copies_exact':True,'source':'audit/preservation.json','public_spec_sha256':h(repo/'docs/specification-v1.1.html')},indent=2),encoding='utf-8')
# All producers have exited; select only finished synthetic text/JSON and test/audit logs.
assert json.loads((r/'budget.json').read_text())['closed']
paths=[]
for folder in ['scenarios','scenarios-final','scenarios-qualified','inputs','audit','controllers']:
 paths.extend(x for x in (r/folder).rglob('*') if x.is_file() and x.suffix in ['.json','.txt','.py','.md','.log'])
for folder in ['live','live-final','qualified-live']:
 for x in (r/folder).rglob('*'):
  if x.is_file() and x.name in ['summary.json','events.jsonl','identity.jsonl','provider-requests.jsonl','requests.jsonl','resources.jsonl','startup.jsonl','controller-before.json','controller-after.json','faults.jsonl']:paths.append(x)
for name in ['attempts.json','budget.json','profiles.json','CONVERSATIONS.md','story-checks.json','live-verification.json','old-application-preservation.json','final-code-identity.json','final-code-identity.log','qualified-identity.json','delivery-identity.json','installed-code-identity.json','final-code-tests.log','final-code-sdk.log','final-code-p2.log','scale-regression.log','final-code-upgrade-seed.log','final-code-upgrade-seed-02.log','final-code-upgrade-verify.log','final-code-upgrade-old-reject.log','upgrade-native-install.log','npm-ci.log','test-runner-install.log','test-baseline.log','experience-01.log','experience-02.log','experience-03.log','sdk-installed-01.log','sdk-installed-02.log']:
 paths.append(r/name)
paths.extend(r/f'deliver-{i:02d}.log' for i in range(1,8))
paths.extend(x for x in r.glob('install-*.log'))
for name in ['final-code-sdk/verification.json','final-code-p2/adapter-results.json','final-code-upgrade/proof/verification.json','final-code-upgrade/proof/before.json','final-code-upgrade/proof/old-rejection.json','final-code-upgrade/proof/original.md','scale-regression/observations.json']:
 paths.append(r/name)
paths=sorted(set(paths));assert all(p.is_file() for p in paths)
sealed={'root':str(r),'sealed_at':datetime.datetime.now(datetime.timezone.utc).isoformat(),'producers_finished':True,'ledger_closed':True,'redactions':[[r'<USER_PROFILE>','<USER_PROFILE>'],[r'<CHECKOUT>','<CHECKOUT>']], 'entries':[{'path':p.relative_to(r).as_posix(),'bytes':p.stat().st_size,'sha256':h(p)} for p in paths]}
(r/'sealed-inputs.json').write_text(json.dumps(sealed,indent=2),encoding='utf-8')
print(json.dumps({'files':len(paths),'raw_bytes':sum(x['bytes'] for x in sealed['entries'])},indent=2))

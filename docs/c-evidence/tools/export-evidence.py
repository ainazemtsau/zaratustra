"""Export synthetic derivatives only; preserve every source byte and link both hashes."""
from pathlib import Path
import json, hashlib, gzip, sys, re
root=Path(sys.argv[1]).resolve(); dest=Path(sys.argv[2]).resolve()
assert not dest.exists(), 'Use a fresh export directory'
dest.mkdir(parents=True)
sha=lambda b:hashlib.sha256(b).hexdigest()
replacements=[(str(root),'<C_EVIDENCE_ROOT>'),('<FIRST_BLOCK_REVIEW_ROOT>','<FIRST_BLOCK_REVIEW_ROOT>'),('<P2_EVIDENCE_ROOT>','<P2_EVIDENCE_ROOT>'),('<CHECKOUT>','<CHECKOUT>'),('<USER_HOME>','<USER_HOME>')]
def clean_string(s):
 for a,b in replacements:
  for n in [4,2,1]: s=s.replace(a.replace('\\','\\'*n),b)
  s=s.replace(a.replace('\\','/'),b)
 return s
def clean(v):
 if isinstance(v,dict):
  if v.get('type') in ['thinking','redactedThinking','reasoning']: return None
  return {k:clean(x) for k,x in v.items() if k not in ['encrypted_content','redactedThinking','signature']}
 if isinstance(v,list): return [y for x in v if (y:=clean(x)) is not None]
 if isinstance(v,str):
  if v.startswith(('{','[')):
   try:return json.dumps(clean(json.loads(v)),ensure_ascii=False,separators=(',',':'))
   except (ValueError,TypeError):pass
  return clean_string(v)
 return v
manifest=[]
def export(src,relative=None):
 relative=relative or src.relative_to(root).as_posix();target=dest/relative
 original=src.read_bytes();text=original.decode('utf-8-sig')
 if src.suffix=='.json':
  try:parsed=json.loads(text)
  except json.JSONDecodeError:
   parsed,end=json.JSONDecoder().raw_decode(text.lstrip());tail=text.lstrip()[end:].strip()
   assert 'ExperimentalWarning: SQLite' in tail,src
   parsed={'captured_json':parsed,'captured_trailing_stderr':tail}
  value=json.dumps(clean(parsed),ensure_ascii=False,indent=2)+'\n'
 elif src.suffix=='.jsonl': value=''.join(json.dumps(clean(json.loads(l)),ensure_ascii=False,separators=(',',':'))+'\n' for l in text.splitlines() if l.strip())
 else:value=clean_string(text)
 value=value.replace('\r\n','\n').replace('\r','\n')
 derivative=value.encode('utf8');transform=['UTF-8 without BOM; canonical LF line endings; local path placeholders']
 if src.suffix in ['.json','.jsonl']:transform+=['parse and reserialize JSON; split trailing SQLite stderr if present; redact reasoning blocks/encrypted reasoning; recursively normalize embedded JSON strings']
 if src.name=='provider-requests.jsonl':
  relative+='.gz';target=dest/relative;derivative=gzip.compress(derivative,mtime=0);transform+=['deterministic gzip; includes blocked unsent payload explicitly accounted in verification-final']
 target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(derivative)
 manifest.append({'original_relative_path':src.relative_to(root).as_posix(),'original_sha256':sha(original),'original_bytes':len(original),'derivative_path':relative,'derivative_sha256':sha(derivative),'derivative_bytes':len(derivative),'transforms':transform,'synthetic':True})
for src in sorted(root.glob('*.txt')):export(src)
root_json=['live-budget.json','environment-profile.json','baseline-acceptance.json','audit-full.json','audit-product.json','qualified-identity.json','qualified-resources.json','live-materials-manifest.json','verification-01.json','verification-02.json','verification-03.json','verification-final.json','clarification-verification.json','final-code-identity.json','final-code-resources.json','parser-equivalence.json','final-preservation-before.json']
for name in root_json:export(root/name)
for folder in ['qualified-upgrade-proof','final-upgrade-proof','state-coverage','async-qualified','async-final','image-only-red','image-only-green','qualified-p2','final-code-p2-retry','scenarios']:
 for src in sorted((root/folder).glob('*.json')):export(src)
for src in sorted((root/'live').glob('*/*')):
 if src.suffix in ['.json','.jsonl']:export(src)
for name in ['verify-c.py','verify-final.py','parser-equivalence.mjs','async-qualified-probe.mjs','async-final-probe.mjs','extra-states.mjs','image-only-probe.mjs','final-preservation.mjs','export-evidence.py']:export(root/name,'tools/'+name)
# Avoid republishing a third-party advisory narrative; link and retain factual fields.
advisory=json.loads((root/'braces-advisory.json').read_text(encoding='utf-8-sig'))
projection={k:advisory[k] for k in ['ghsa_id','cve_id','html_url','summary','severity','vulnerabilities','published_at','updated_at'] if k in advisory}
b=(json.dumps(projection,ensure_ascii=False,indent=2)+'\n').encode();(dest/'braces-advisory.json').write_bytes(b)
manifest.append({'original_relative_path':'braces-advisory.json','original_sha256':sha((root/'braces-advisory.json').read_bytes()),'derivative_path':'braces-advisory.json','derivative_sha256':sha(b),'transforms':['selected factual fields; omitted advisory narrative'],'synthetic':False,'public_primary_source':True})
# Inspect exported files again, without printing possible matches.
for row in manifest:
 b=(dest/row['derivative_path']).read_bytes();assert sha(b)==row['derivative_sha256']
 text=(gzip.decompress(b) if row['derivative_path'].endswith('.gz') else b).decode('utf8')
 assert not re.search(r'C:(?:\\+|/)Users(?:\\+|/)Anton',text,re.I),row['derivative_path']
 assert not re.search(r'\bsk-[A-Za-z0-9_-]{20,}\b',text),row['derivative_path']
 if '.json' in row['derivative_path']:
  assert not re.search(r'"encrypted_content"|"type"\s*:\s*"(?:thinking|redactedThinking|reasoning)"',text),row['derivative_path']
 if row['derivative_path'].endswith('.json'):json.loads(text)
 if '.jsonl' in row['derivative_path']:
  for l in text.splitlines():json.loads(l)
(dest/'manifest.json').write_text(json.dumps({'original_root':'isolated synthetic C evidence root (not published)','originals_unchanged':True,'no_credentials_read_or_exported':True,'thinking_omitted':True,'entries':manifest},ensure_ascii=False,indent=2)+'\n',encoding='utf8')
print(json.dumps({'exported':len(manifest),'bytes':sum((dest/r['derivative_path']).stat().st_size for r in manifest),'validated':True}))

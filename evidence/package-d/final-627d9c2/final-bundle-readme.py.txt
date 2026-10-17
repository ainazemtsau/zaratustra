import hashlib,json,zipfile
from pathlib import Path
e=Path('evidence/package-d/final-627d9c2');bundle=e/'owner-bundle'
p=bundle/'README.txt';p.write_text(p.read_text(encoding='utf-8').replace('Pi 1.0.4','Pi 1.3.0'),encoding='utf-8')
p=e/'OWNER-BUNDLE-MANIFEST.json';manifest=json.loads(p.read_bytes());manifest['files']=[{'path':f.relative_to(bundle).as_posix(),'sha256':hashlib.sha256(f.read_bytes()).hexdigest(),'bytes':f.stat().st_size} for f in sorted(bundle.rglob('*')) if f.is_file()];manifest['packaging_note']='Final SDK audit observes Pi1.3.0. README aligned before candidate evidence freeze; original historical source095 bundle remains unchanged.';p.write_text(json.dumps(manifest,indent=2),encoding='utf-8')
with zipfile.ZipFile(e/'zaratustra-next-d-627d9c2-windows-x64.zip','w',compression=zipfile.ZIP_DEFLATED) as archive:
 for f in sorted(bundle.rglob('*')):
  if f.is_file():archive.write(f,f.relative_to(bundle))

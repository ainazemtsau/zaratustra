import fs from 'node:fs'; import {syncBuiltinESMExports} from 'node:module';
const original=fs.readFileSync; let first=true; const source="<SYNTHETIC_EVIDENCE_ROOT>\\green-installed\\changed-after-read\\Completed.log";
fs.readFileSync=function(path,...args){const b=original(path,...args);if(String(path)===source&&first){first=false;fs.writeFileSync(source,Buffer.from('X'.repeat(b.length)));}return b;};syncBuiltinESMExports();

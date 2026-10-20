import { DatabaseSync } from 'node:sqlite';
import {readFileSync,writeFileSync} from 'node:fs';
import {createHash} from 'node:crypto';
const r=process.argv[2],s=JSON.parse(readFileSync(r+'/qualified-live/11-final-read/summary.json','utf8'));
const db=new DatabaseSync(r+'/qualified-home/zara.sqlite',{readOnly:true}),out={after_installed_sha:'b20ff519881943e558f5e24eea1679f5d3c88821',all_captured_tables_exact:true,tables:{}};
for(const [table,before] of Object.entries(s.database)){const after=db.prepare('SELECT * FROM '+table).all();if(JSON.stringify(before)!==JSON.stringify(after))throw Error('Changed '+table);out.tables[table]={rows:after.length,sha256:createHash('sha256').update(JSON.stringify(after)).digest('hex')};}
db.close();writeFileSync(r+'/FINAL-qualified-state.json',JSON.stringify(out,null,2));

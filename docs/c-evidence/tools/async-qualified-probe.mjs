import assert from 'node:assert/strict';
import {readFileSync,writeFileSync,mkdirSync,readdirSync,copyFileSync} from 'node:fs';
import {join} from 'node:path';
import {pathToFileURL} from 'node:url';
import {DatabaseSync} from 'node:sqlite';
const root=process.argv[2],pkg=join(root,'qualified-config/git/github.com/ainazemtsau/zaratustra'),out=join(root,'async-qualified');mkdirSync(out,{recursive:true});
const home=join(out,'home'),cwd=join(out,'cwd'),inputs=join(out,'inputs');mkdirSync(cwd);mkdirSync(inputs);
process.env.PI_CODING_AGENT_DIR=join(root,'qualified-config');process.env.ZARATUSTRA_HOME=home;process.env.ZARATUSTRA_IMPORT_ROOTS=JSON.stringify([inputs]);
const sdk=await import(pathToFileURL(process.env.ZARA_PI_SDK).href);
const runtime=await sdk.ModelRuntime.create({authPath:process.env.ZARA_AUTH_PATH,modelsPath:null,modelsStorePath:join(out,'models.json'),allowModelNetwork:false});
const model=runtime.getModel('openai-codex','gpt-6.1-sol'),alternative=runtime.getModels('openai-codex').find(m=>m.id!==model.id);
const settingsManager=sdk.SettingsManager.create(cwd,process.env.PI_CODING_AGENT_DIR);let requests=0;
const loader=new sdk.DefaultResourceLoader({cwd,agentDir:process.env.PI_CODING_AGENT_DIR,settingsManager,extensionFactories:[pi=>pi.on('before_provider_request',()=>{requests++;throw Error('No model requests authorized by this mechanical probe');})]});await loader.reload();assert.equal(loader.getExtensions().errors.length,0);
const {session}=await sdk.createAgentSession({cwd,agentDir:process.env.PI_CODING_AGENT_DIR,settingsManager,resourceLoader:loader,modelRuntime:runtime,model,sessionManager:sdk.SessionManager.inMemory()});await session.bindExtensions({});
const tools=loader.getExtensions().extensions.find(e=>e.tools.has('zara_import')).tools;
const path=join(inputs,'large.pdf');copyFileSync(join(pkg,'tests/fixtures/c/large.pdf'),path);
const domain=()=>{const db=new DatabaseSync(join(home,'zara.sqlite'),{readOnly:true});try{return JSON.stringify(['records','revisions','changes','intents','receipts'].map(t=>db.prepare('SELECT * FROM '+t).all()));}finally{db.close();}};
const before=domain();let settled=false;
try{
 const pending=tools.get('zara_import').definition.execute('async-native-import',{path},undefined,undefined,undefined);pending.then(()=>{settled=true;});
 const pending_before_switch=!settled;await session.setModel(alternative);const result=await pending;
 assert.equal(result.isError,true);assert.equal(result.details.source_handle,undefined);assert.equal(domain(),before);assert.deepEqual(readdirSync(join(home,'materials')),[]);assert.deepEqual(readdirSync(join(home,'staging')),[]);assert.equal(requests,0);
 writeFileSync(join(out,'verification.json'),JSON.stringify({pending_before_switch,result,provider_requests:requests,no_material_or_handle:true,domain_unchanged:true,initial_model:model.id,changed_model:alternative.id},null,2));
 console.log('Native asynchronous revoke: PASS, no publication and zero provider requests');
}finally{await session.extensionRunner.emit({type:'session_shutdown',reason:'exit'});session.dispose();}

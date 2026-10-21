// Deterministic SDK/native-tool checks only. No session.prompt/provider dispatch.
import assert from "node:assert/strict";
import { createRequire } from "node:module";
import { join, resolve } from "node:path";
import { pathToFileURL } from "node:url";
import { mkdirSync, existsSync, readFileSync, writeFileSync } from "node:fs";
import { promises as fs } from "node:fs";
const [pkgArg, outArg] = process.argv.slice(2),
  pkg = resolve(pkgArg),
  out = resolve(outArg);
assert.equal(existsSync(out), false);
mkdirSync(out, { recursive: true });
const sdk = await import(pathToFileURL(process.env.ZARA_PI_SDK).href);
const { createJiti } = createRequire(pathToFileURL(process.env.ZARA_PI_SDK))(
    "jiti",
  ),
  jiti = createJiti(import.meta.url);
const { activeLocation, removeOwned, DiskStorage:StorageClass } = await jiti.import(
  join(pkg, "src/storage/index.ts"),
);
const calls = [],
  dialogs = [],
  checks = [];
let serial = 0,
  dispatches = 0;
const save = () => {
  for (const [name, value] of Object.entries({
    calls,
    dialogs,
    verification: {
      checks,
      provider_dispatches: dispatches,
      mechanical_only: true,
    },
  }))
    writeFileSync(join(out, name + ".json"), JSON.stringify(value, null, 2));
};
process.on("exit", save);
async function start(profile) {
  const base = join(out, profile),
    agentDir = join(base, "agent"),
    home = join(base, "home"),
    cwd = join(base, "cwd"),
    output = join(base, "output"),
    backups = join(base, "backups");
  for (const p of [agentDir, cwd, output, backups])
    mkdirSync(p, { recursive: true });
  Object.assign(process.env, {
    PI_CODING_AGENT_DIR: agentDir,
    ZARATUSTRA_HOME: home,
    ZARATUSTRA_OUTPUT_ROOT: output,
    ZARATUSTRA_BACKUP_ROOT: backups,
    ZARATUSTRA_SCOPES: JSON.stringify(
      profile.startsWith("protected") ? ["restricted:read", "restricted:write"] : [],
    ),
    ZARATUSTRA_IMPORT_ROOTS:JSON.stringify([cwd]),
    ZARATUSTRA_TEST_CONTROLLER: "predeclared-E3-native-fixtures",
  });
  const runtime = await sdk.ModelRuntime.create({
      authPath: process.env.ZARA_AUTH_PATH,
      modelsPath: null,
      modelsStorePath: join(agentDir, "models.json"),
      allowModelNetwork: false,
    }),
    model = runtime.getModel("openai-codex", "gpt-6.1-sol");
  assert.ok(model);
  const settingsManager = sdk.SettingsManager.create(cwd, agentDir),
    loader = new sdk.DefaultResourceLoader({
      cwd,
      agentDir,
      settingsManager,
      noExtensions: true,
      additionalExtensionPaths: [join(pkg, "src/extension/index.ts")],
      extensionFactories: [
        (pi) => {
          pi.on("before_provider_request", () => {
            dispatches++;
            throw Error("Unexpected mechanical provider dispatch");
          });
        },
      ],
    });
  await loader.reload();
  assert.deepEqual(loader.getExtensions().errors, []);
  const { session } = await sdk.createAgentSession({
    cwd,
    agentDir,
    modelRuntime: runtime,
    model,
    thinkingLevel: "medium",
    settingsManager,
    resourceLoader: loader,
    sessionManager: sdk.SessionManager.inMemory(),
  });
  await session.bindExtensions({});
  const runner = session.extensionRunner;
  runner.setUIContext(
    {
      ...runner.getUIContext(),
      confirm: async (title, message) => {
        dialogs.push({
          profile,
          title,
          message,
          answer: true,
          principal: "predeclared isolated synthetic controller, not owner",
        });
        return true;
      },
      notify: (message, type) =>
        calls.push({ profile, notification: message, type }),
    },
    "rpc",
  );
  const custom = async (name, args) => {
    const id = "e3-sdk-" + ++serial,
      result = await runner
        .getToolDefinition(name)
        .execute(id, args, undefined, undefined, runner.createToolContext(id));
    calls.push({ profile, name, args, result });
    return result.details;
  };
  const snap = async () =>
    JSON.parse(
      (await runner.emitContext([])).find(
        (m) => m.customType === "zaratustra.snapshot.v1",
      ).content,
    );
  const source = async () => {
    await runner.emitInput(
      "Synthetic fixture instruction, not owner testimony.",
      undefined,
      "rpc",
    );
    return (await snap()).captured_sources.at(-1)?.source_handle;
  };
  const native = async (args) => {
    const id = "native-e3-" + ++serial,
      block = await runner.emitToolCall({
        type: "tool_call",
        toolName: "write",
        toolCallId: id,
        input: args,
      });
    calls.push({ profile, name: "write", args, id, block });
    assert.ok(!block?.block);
    const result = await sdk.createWriteTool(cwd).execute(id, args);
    calls.push({
      profile,
      native_result: result,
      dropped_before_product_result: true,
    });
  };
  return {
    runner,model,
    home,
    cwd,
    output,
    backups,
    custom,
    snap,
    source,
    native,
    close: async () => {
      await runner.emit({ type: "session_shutdown", reason: "exit" });
      session.dispose();
    },
  };
}

async function run(name,action){try{await action();checks.push({name,passed:true});}catch(error){checks.push({name,passed:false,error:String(error),stack:error.stack});}save();}
for(const unavailable of [false,true]) await run("recipient denial survives guessed restore/reopen "+(unavailable?"unavailable":"healthy"),async()=>{
 const f=await start("protected-recipient-"+unavailable);
 try {
  if(unavailable){await f.runner.emit({type:"session_shutdown",reason:"exit"});removeOwned(f.home,join(activeLocation(f.home),"zara.sqlite"));await f.runner.emit({type:"session_start"});assert.equal((await f.snap()).available,false);}
  await f.runner.emit({type:"model_select",model:{...f.model,id:f.model.id+"-unexplained-fixture"},previousModel:f.model,source:"set"});
  assert.equal((await f.custom("zara_backups",{})).code,"PERMISSION_DENIED");
  const refused=await f.custom("zara_restore",{preview_ref:"preview-guessed"});assert.equal(refused.code,"PERMISSION_DENIED");
  assert.equal((await f.custom("zara_backups",{})).code,"PERMISSION_DENIED","A failed restore must not relabel existing recipient denial as startup consent");
  if(!unavailable) assert.equal((await f.custom("zara_map",{})).code,"PERMISSION_DENIED");
  await f.runner.emit({type:"model_select",model:f.model,previousModel:{...f.model,id:"unexplained-fixture"},source:"restore"});
  assert.ok(!(await f.custom("zara_backups",{})).code,"Fresh native synthetic decision on the actual current recipient may resolve denial");
 } finally {await f.close();}
});
for(const unavailable of [false,true]) await run("restore refuses real in-flight native write "+(unavailable?"unavailable":"healthy"),async()=>{
 const f=await start("protected-flight-"+unavailable),backup=await f.custom("zara_backup",{}),path=join(f.output,"late-report.txt"),args={path,content:"Actual public native write completes only after the controlled gate.\n"};
 let release,arrived;const gate=new Promise(resolve=>release=resolve),entered=new Promise(resolve=>arrived=resolve);let pending;
 try {
  const proposal=await f.custom("zara_file_preview",{request_id:"delayed-native-B",tool:"write",arguments:args,independent_basis:"New independent isolated fixture action",consequence:"Write synthetic delayed report","alternatives":"Keep absent"});assert.ok(proposal.request_id);await f.custom("zara_confirm",{preview_ref:proposal.request_id});
  const callId="real-delayed-native-"+(++serial),block=await f.runner.emitToolCall({type:"tool_call",toolName:"write",toolCallId:callId,input:args});assert.ok(!block?.block);
  pending=sdk.createWriteTool(f.cwd,{operations:{mkdir:async dir=>{await fs.mkdir(dir,{recursive:true});},writeFile:async(p,content)=>{arrived();await gate;await fs.writeFile(p,content);}}}).execute(callId,args);await entered;
  if(unavailable){await f.runner.emit({type:"session_shutdown",reason:"exit"});removeOwned(f.home,join(activeLocation(f.home),"zara.sqlite"));await f.runner.emit({type:"session_start"});assert.equal((await f.snap()).available,false);}
  const before=activeLocation(f.home),r=await f.custom("zara_restore_preview",{backup:backup.backup,consequence:"Restore snapshot; external action must first settle","alternatives":"Keep current"});assert.ok(r.preview);await f.custom("zara_confirm",{preview_ref:r.preview.request_id});
  const result=await f.custom("zara_restore",{preview_ref:r.preview.request_id});assert.equal(result.code,"WORK_IN_USE");assert.equal(activeLocation(f.home),before);assert.equal(existsSync(path),false);
  release();const real=await pending;pending=null;await f.runner.emitToolResult({type:"tool_result",toolName:"write",toolCallId:callId,input:args,content:real.content,isError:false});assert.equal(readFileSync(path,"utf8"),args.content);
  const fresh=await f.custom("zara_restore_preview",{backup:backup.backup,consequence:"Native action has settled; restore earlier DB while preserving real output","alternatives":"Keep current"});assert.ok(fresh.preview);await f.custom("zara_confirm",{preview_ref:fresh.preview.request_id});assert.equal((await f.custom("zara_restore",{preview_ref:fresh.preview.request_id})).switched,true);
 } finally {release?.();if(pending){const real=await pending;calls.push({late_real_result:real,path,bytes:existsSync(path)?readFileSync(path,"utf8"):null});}await f.close();}
});

await run("pending native decision cannot survive recipient denial or permit concurrent restore",async()=>{
 const f=await start("protected-pending-ui"),backup=await f.custom("zara_backup",{});let release,arrived;const gate=new Promise(resolve=>release=resolve),entered=new Promise(resolve=>arrived=resolve);
 try {
  const r=await f.custom("zara_restore_preview",{backup:backup.backup,consequence:"Restore exact fixture","alternatives":"Keep"});assert.ok(r.preview);
  f.runner.setUIContext({...f.runner.getUIContext(),confirm:async(title,message)=>{dialogs.push({title,message,stage:"delayed actual native confirm callback"});arrived();return await gate;}},"rpc");
  const pending=f.custom("zara_confirm",{preview_ref:r.preview.request_id});await entered;
  assert.equal((await f.custom("zara_restore",{preview_ref:r.preview.request_id})).code,"WORK_IN_USE");
  await f.runner.emit({type:"model_select",model:{...f.model,id:f.model.id+"-unexplained"},previousModel:f.model,source:"set"});release(true);const old=await pending;assert.notEqual(old.status,"approved-transient");assert.equal((await f.custom("zara_backups",{})).code,"PERMISSION_DENIED");
  f.runner.setUIContext({...f.runner.getUIContext(),confirm:async()=>true},"rpc");await f.runner.emit({type:"model_select",model:f.model,previousModel:{...f.model,id:"unexplained"},source:"restore"});assert.notEqual((await f.custom("zara_restore",{preview_ref:r.preview.request_id})).switched,true,"Old delayed yes is not new permission after recipient consent");
 } finally {release?.(false);await f.close();}
});
for(const unavailable of [false,true]) await run("pending actual import blocks restore until settlement "+unavailable,async()=>{
 let release,arrived;const gate=new Promise(resolve=>release=resolve),entered=new Promise(resolve=>arrived=resolve),original=StorageClass.prototype.importMaterial;
 StorageClass.prototype.importMaterial=async function(...args){arrived();await gate;return await original.apply(this,args);};
 const f=await start("protected-pending-import-"+unavailable),backup=await f.custom("zara_backup",{}),path=join(f.cwd,"pending.md");writeFileSync(path,"Actual pending material, never a forced import result.\n");let pending;
 try {
  pending=f.custom("zara_import",{path});let timer;try{await Promise.race([entered,new Promise((_,reject)=>timer=setTimeout(()=>reject(Error("Actual import delay was not reached")),3000))]);}finally{clearTimeout(timer);}
  if(unavailable){await f.runner.emit({type:"session_shutdown",reason:"exit"});removeOwned(f.home,join(activeLocation(f.home),"zara.sqlite"));await f.runner.emit({type:"session_start"});assert.equal((await f.snap()).available,false);}
  const p=await f.custom("zara_restore_preview",{backup:backup.backup,consequence:"Restore after import has settled","alternatives":"Keep"});assert.ok(p.preview);await f.custom("zara_confirm",{preview_ref:p.preview.request_id});assert.equal((await f.custom("zara_restore",{preview_ref:p.preview.request_id})).code,"WORK_IN_USE");
  release();const actual=await pending;pending=null;assert.equal(actual.committed,unavailable?undefined:false);
  const fresh=await f.custom("zara_restore_preview",{backup:backup.backup,consequence:"Import settled; restore earlier fixture","alternatives":"Keep"});assert.ok(fresh.preview);await f.custom("zara_confirm",{preview_ref:fresh.preview.request_id});assert.equal((await f.custom("zara_restore",{preview_ref:fresh.preview.request_id})).switched,true);
 } finally {release?.();if(pending)await pending;StorageClass.prototype.importMaterial=original;await f.close();}
});
assert.equal(dispatches,0);save();console.log(JSON.stringify({checks,provider_dispatches:dispatches},null,2));if(checks.some(c=>!c.passed))process.exitCode=1;

import { createHash, randomUUID } from "node:crypto";
import { readFile, mkdir, rm, writeFile, rename } from "node:fs/promises";
import { join, dirname, basename, isAbsolute } from "node:path";
import { fileURLToPath } from "node:url";
import { homedir } from "node:os";
import { spawn } from "node:child_process";

export function home() {
  return process.env.ZARATUSTRA_HOME || (process.platform === "win32"
    ? join(process.env.LOCALAPPDATA || join(homedir(), "AppData", "Local"), "Zaratustra")
    : process.platform === "darwin" ? join(homedir(), "Library", "Application Support", "Zaratustra")
    : join(process.env.XDG_DATA_HOME || join(homedir(), ".local", "share"), "zaratustra"));
}
export async function dataRoot() {
  try {
    const selection = JSON.parse(await readFile(join(home(), "data-selection.json"), "utf8"));
    if (!isAbsolute(selection.data_root)) throw new Error("Absolute data root required.");
    return selection.data_root;
  } catch (error) {
    if (error.code === "ENOENT") return join(home(), "data");
    throw error;
  }
}
export async function selectDataRoot(root) {
  if (!isAbsolute(root)) throw new Error("Absolute data root required.");
  await mkdir(home(), { recursive: true });
  const temporary = join(home(), "data-selection-" + randomUUID() + ".json");
  await writeFile(temporary, JSON.stringify({ data_root: root }), { flag: "wx" });
  await rename(temporary, join(home(), "data-selection.json"));
}
export function run(command, args, input) {
  return new Promise((resolve, reject) => {
    const child = spawn(command, args, { shell: false, windowsHide: true, stdio: ["pipe", "pipe", "pipe"] });
    let output = "";
    child.stdout.setEncoding("utf8");
    child.stdout.on("data", chunk => { output += chunk; });
    child.stderr.resume();
    child.on("error", () => reject(new Error("Required executable unavailable: " + command)));
    child.on("close", code => code === 0 ? resolve(output) : reject(new Error("Zaratustra runtime command failed; existing data and runtime selection retained.")));
    child.stdin.on("error", () => {});
    child.stdin.end(input || "");
  });
}
const digest = bytes => createHash("sha256").update(bytes).digest("hex");
const interpreter = runtime => join(runtime, process.platform === "win32" ? "Scripts/python.exe" : "bin/python");
const verify = `import json,sys,importlib.metadata as m
import zaratustra_core,zaratustra_app.pi_host
v=json.loads(sys.argv[1])
assert all(m.version(k)==value for k,value in v.items())
assert sys.version_info[:2]==(3,13)
`;
// Environments are created at unique final paths: console launchers retain valid absolute paths.
// Publication alone is serialized with an OS lock, automatically released after process death.
const publish = `import json,os,sys,time,uuid,subprocess
from pathlib import Path
from zaratustra_app.entry_lock import host_lock
from zaratustra_core import CoreError
from zaratustra_app.pi_host import handle
root=Path(sys.argv[1]); candidate=Path(sys.argv[2]); identity=sys.argv[3]
lock=root/'runtime-publish.lock'
for attempt in range(1200):
 try:
  with host_lock(lock):
   current=root/'.current'
   selected=None
   if current.exists():
    try: selected=json.loads(current.read_text(encoding='utf-8'))
    except ValueError: selected=None
   if selected and selected.get('identity')==identity:
    chosen=Path(selected['runtime'])
    try:
     executable=chosen/('Scripts/python.exe' if os.name=='nt' else 'bin/python')
     assert (chosen/'.ready').read_text(encoding='utf-8')==identity
     subprocess.run([str(executable),'-c',sys.argv[5],sys.argv[6]],check=True,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
    except (OSError,AssertionError,subprocess.CalledProcessError): pass
    else:
     print(str(chosen)); break
   data=Path(sys.argv[4])
   if data.exists():
    backup=root/'backups'/('update-'+uuid.uuid4().hex)
    backup.parent.mkdir(parents=True,exist_ok=True)
    result=handle({'command':'prepare-update','data_root':str(data),'destination':str(backup)})
    if result.get('state')!='compatible': raise RuntimeError('Incompatible Core update')
   (candidate/'.ready').write_text(identity,encoding='utf-8')
   temporary=root/('.current-'+uuid.uuid4().hex)
   with temporary.open('x',encoding='utf-8') as stream:
    json.dump({'identity':identity,'runtime':str(candidate)},stream)
    stream.flush(); os.fsync(stream.fileno())
   os.replace(temporary,current)
   print(str(candidate)); break
 except CoreError as error:
  if error.field!='native.host_busy': raise
  time.sleep(0.1)
else: raise RuntimeError('Runtime publication busy')
`;
export async function bootstrap() {
  if (Number(process.versions.node.split(".")[0]) < 22) throw new Error("Node 22 or newer is required.");
  const base = dirname(fileURLToPath(import.meta.url));
  const wheels = join(base, "wheels");
  const manifest = await readFile(join(wheels, "SHA256SUMS"), "utf8");
  const release = JSON.parse(await readFile(join(base, "release.json"), "utf8"));
  const requirements = await readFile(join(base, "requirements.txt"));
  if (digest(requirements) !== release.requirements_sha256) throw new Error("Requirements integrity check failed.");
  const names = [];
  for (const line of manifest.trim().split(/\r?\n/)) {
    const match = /^([a-f0-9]{64})  ([A-Za-z0-9_.+-]+\.whl)$/.exec(line);
    if (!match || basename(match[2]) !== match[2] || names.includes(match[2])) throw new Error("Invalid wheel manifest.");
    if (digest(await readFile(join(wheels, match[2]))) !== match[1]) throw new Error("Wheel integrity check failed.");
    names.push(match[2]);
  }
  for (const name of ["zaratustra_core", "zaratustra_next"]) {
    if (names.filter(n => n.startsWith(name + "-") && n.endsWith("-py3-none-any.whl")).length !== 1) throw new Error("Both universal product wheels are required exactly once.");
  }
  const identity = digest(manifest + requirements.toString() + JSON.stringify(release.versions));
  const root = home();
  await mkdir(join(root, "runtimes"), { recursive: true });
  try {
    const selected = JSON.parse(await readFile(join(root, ".current"), "utf8"));
    if (selected.identity === identity && await readFile(join(selected.runtime, ".ready"), "utf8") === identity) {
      const python = interpreter(selected.runtime);
      await run(python, ["-c", verify, JSON.stringify(release.versions)]);
      return python;
    }
  } catch {}
  const runtime = join(root, "runtimes", identity + "-" + randomUUID());
  const python = interpreter(runtime);
  let published = false;
  try {
    await run("uv", ["venv", "--python", "3.13.7", runtime]);
    const offline = process.env.ZARATUSTRA_OFFLINE === "1" ? ["--no-index"] : [];
    await run("uv", ["pip", "install", "--python", python, "--require-hashes", ...offline, "--find-links", wheels, "-r", join(base, "requirements.txt")]);
    await run(python, ["-c", verify, JSON.stringify(release.versions)]);
    const chosen = (await run(python, ["-c", publish, root, runtime, identity, await dataRoot(), verify, JSON.stringify(release.versions)])).trim();
    published = chosen === runtime;
    await run(interpreter(chosen), ["-c", verify, JSON.stringify(release.versions)]);
    return interpreter(chosen);
  } finally {
    // Only this invocation's unpublished candidate may be removed. Crash leftovers are inert.
    if (!published) {
      let ready = false;
      try { await readFile(join(runtime, ".ready")); ready = true; } catch {}
      if (!ready) await rm(runtime, { recursive: true, force: true });
    }
  }
}




import assert from "node:assert/strict";
import fs from "node:fs";
import crypto from "node:crypto";
import { syncBuiltinESMExports, createRequire } from "node:module";
import { join, resolve } from "node:path";
import { pathToFileURL } from "node:url";
import { DatabaseSync } from "node:sqlite";

const [packageArg, outputArg, expected = "fixed"] = process.argv.slice(2);
if (
  !packageArg ||
  !outputArg ||
  !["baseline", "import-fixed", "fixed"].includes(expected)
)
  throw Error(
    "Usage: node p2-probe.mjs <package> <new-output> baseline|import-fixed|fixed",
  );
const pkg = resolve(packageArg),
  out = resolve(outputArg);
assert.equal(
  fs.existsSync(out),
  false,
  "Each probe needs a fresh output directory",
);
fs.mkdirSync(out, { recursive: true });
const sdkUrl = pathToFileURL(process.env.ZARA_PI_SDK);
const sdk = await import(sdkUrl.href);
const { createJiti } = createRequire(sdkUrl)("jiti");
const jiti = createJiti(import.meta.url);
const { Core, failure, digest } = await jiti.import(
  join(pkg, "src/core/index.ts"),
);
const { DiskStorage } = await jiti.import(join(pkg, "src/storage/index.ts"));
const sourceHashes = Object.fromEntries(
  ["src/core/index.ts", "src/extension/index.ts"].map((p) => [
    p,
    digest(fs.readFileSync(join(pkg, p))),
  ]),
);
const coreDisk = new DiskStorage(join(out, "core-home"));
const core = new Core(coreDisk, {
  workspace_id: coreDisk.workspace.workspace_id,
  epoch: coreDisk.workspace.epoch,
  principal: "trusted-personal",
  session_id: "p2-probe",
  runtime_id: "p2-probe",
  can_write: true,
  processing_allowed: true,
});
const text = "A".repeat(8500) + "\nTAIL-UNIQUE-ELM-93";
const source = core.capture(text, "rpc", "p2-synthetic-controller");
const receipt = core.commit({
  request_id: "long-observed-original",
  reason: "Retain a long synthetic observed source.",
  source_handles: [source.source_handle],
  guards: [],
  ops: [
    {
      op: "import_evidence",
      client_ref: "original",
      source_handle: source.source_handle,
      title: "Long observed source",
      source_language: "en",
    },
  ],
});
const beforeRows = JSON.stringify(
  coreDisk.all("SELECT json FROM revisions ORDER BY id,revision"),
);
const normal = core.read(receipt.created.original).data;
let ranged;
try {
  ranged = core.read(receipt.created.original, 1, {
    start: 8000,
    length: 1000,
  });
} catch (e) {
  ranged = failure(e);
}
const unicode = "A".repeat(7999) + "🦉" + "B".repeat(518);
const u = core.capture(unicode, "rpc", "p2-synthetic-controller");
const ur = core.commit({
  request_id: "unicode-boundary",
  reason: "Retain a Unicode boundary witness.",
  source_handles: [u.source_handle],
  guards: [],
  ops: [
    {
      op: "import_evidence",
      client_ref: "original",
      source_handle: u.source_handle,
      title: "Unicode boundary source",
      source_language: "en",
    },
  ],
});
const unicodeRead = core.read(ur.created.original).data.data.retained_excerpt;
const coreResult = {
  sourceHashes,
  input_code_points: Array.from(text).length,
  retained_exact:
    JSON.parse(
      coreDisk.get(
        "SELECT json FROM records WHERE id=?",
        receipt.created.original,
      ).json,
    ).data.retained_excerpt === text,
  normal_code_points: Array.from(normal.data.retained_excerpt).length,
  normal_truncated: normal.data.excerpt_truncated,
  normal_metadata: normal.data,
  range_result: ranged,
  unicode_last_code_unit: unicodeRead.charCodeAt(unicodeRead.length - 1),
  unicode_split: /[\uD800-\uDBFF]$/.test(unicodeRead),
  old_revision_unchanged:
    JSON.stringify(
      coreDisk.all(
        "SELECT json FROM revisions WHERE id=? ORDER BY revision",
        receipt.created.original,
      ),
    ) === beforeRows,
};
fs.writeFileSync(
  join(out, "core-results.json"),
  JSON.stringify(coreResult, null, 2),
);
coreDisk.close();

const home = join(out, "adapter-home"),
  agentDir = join(out, "pi-agent"),
  cwd = join(out, "cwd"),
  inputs = join(out, "inputs");
for (const p of [agentDir, cwd, inputs]) fs.mkdirSync(p, { recursive: true });
const allowed = join(inputs, "allowed.txt"),
  denied = join(inputs, "denied.txt");
const allowedBytes = Buffer.from(
  "\ufeff# Exact original\r\nРусский текст 🦉\r\n",
);
fs.writeFileSync(allowed, allowedBytes);
fs.writeFileSync(denied, "This denied source must never be read.\n");
process.env.PI_CODING_AGENT_DIR = agentDir;
process.env.ZARATUSTRA_HOME = home;
process.env.ZARATUSTRA_IMPORT_ROOTS = JSON.stringify([inputs]);
let watch = null,
  sourceReads = 0,
  uuidCalls = 0,
  trace = [];
const originalRead = fs.readFileSync,
  originalUUID = crypto.randomUUID;
fs.readFileSync = function (path, ...args) {
  if (watch && typeof path === "string" && resolve(path) === watch) {
    sourceReads++;
    trace.push("read-source-content");
  }
  return Reflect.apply(originalRead, this, [path, ...args]);
};
crypto.randomUUID = function (...args) {
  if (watch) {
    uuidCalls++;
    trace.push("allocate-uuid");
  }
  return Reflect.apply(originalUUID, this, args);
};
syncBuiltinESMExports();
let session,
  requests = 0;
const rows = () => {
  const db = new DatabaseSync(join(home, "zara.sqlite"), { readOnly: true });
  try {
    return Object.fromEntries(
      ["records", "revisions", "changes", "receipts", "intents"].map((t) => [
        t,
        db.prepare(`SELECT count(*) AS count FROM ${t}`).get().count,
      ]),
    );
  } finally {
    db.close();
  }
};
const files = () =>
  Object.fromEntries(
    ["materials", "staging"].map((d) => [
      d,
      fs.readdirSync(join(home, d)).sort(),
    ]),
  );
try {
  const runtime = await sdk.ModelRuntime.create({
    authPath: process.env.ZARA_AUTH_PATH,
    modelsPath: null,
    modelsStorePath: join(agentDir, "model-store.json"),
    allowModelNetwork: false,
  });
  const model = runtime.getModel("openai-codex", "gpt-6.1-sol");
  assert.ok(model);
  const alternative = runtime
    .getModels("openai-codex")
    .find((m) => m.id !== model.id);
  assert.ok(alternative);
  const settingsManager = sdk.SettingsManager.create(cwd, agentDir);
  const loader = new sdk.DefaultResourceLoader({
    cwd,
    agentDir,
    settingsManager,
    additionalExtensionPaths: [join(pkg, "src/extension/index.ts")],
    extensionFactories: [
      (pi) =>
        pi.on("before_provider_request", (_event, ctx) => {
          requests++;
          ctx.abort();
          throw Error("This mechanical probe must never request a model");
        }),
    ],
  });
  await loader.reload();
  assert.equal(loader.getExtensions().errors.length, 0);
  const made = await sdk.createAgentSession({
    cwd,
    agentDir,
    settingsManager,
    resourceLoader: loader,
    modelRuntime: runtime,
    model,
    sessionManager: sdk.SessionManager.inMemory(),
  });
  session = made.session;
  await session.bindExtensions({});
  const tools = loader
    .getExtensions()
    .extensions.find((e) => e.tools.has("zara_import")).tools;
  const run = (name, input) =>
    tools
      .get(name)
      .definition.execute("p2-" + name, input, undefined, undefined, undefined);
  watch = resolve(allowed);
  const allowedResult = await run("zara_import", { path: allowed });
  watch = null;
  assert.equal(allowedResult.isError, undefined);
  assert.equal(
    sourceReads,
    1,
    "Positive control: the source-read spy must observe actual content access",
  );
  const allowedReadCount = sourceReads,
    allowedUUIDs = uuidCalls;
  assert.ok(
    allowedUUIDs >= 3,
    "Positive control: UUID observation includes source-handle allocation",
  );
  assert.deepEqual(
    fs.readFileSync(
      join(home, "materials", allowedResult.details.content_hash),
    ),
    allowedBytes,
  );
  const committed = await run("zara_commit", {
    request_id: "allowed-file",
    reason: "Retain an authorized import.",
    source_handles: [allowedResult.details.source_handle],
    guards: [],
    ops: [
      {
        op: "import_evidence",
        client_ref: "material",
        source_handle: allowedResult.details.source_handle,
        title: "Authorized exact bytes",
        source_language: "ru",
      },
    ],
  });
  assert.equal(committed.details.committed, true);
  const allowedRange = await run("zara_read", {
    id: committed.details.created.material,
    range: { start: 0, length: 8000 },
  });
  assert.equal(allowedRange.details.data.text, allowedBytes.toString("utf8"));
  await session.setModel(alternative);
  const beforeFiles = files(),
    beforeDomain = rows();
  sourceReads = 0;
  uuidCalls = 0;
  trace = [];
  watch = resolve(denied);
  const deniedResult = await run("zara_import", { path: denied });
  watch = null;
  const adapterResult = {
    initial_recipient: model.provider + "/" + model.id,
    selected_without_request: alternative.provider + "/" + alternative.id,
    provider_requests: requests,
    allowed_source_reads: allowedReadCount,
    allowed_uuid_calls: allowedUUIDs,
    allowed_exact_bytes: true,
    allowed_range: allowedRange.details,
    denied_result: deniedResult,
    denied_source_reads: sourceReads,
    denied_uuid_calls: uuidCalls,
    denied_trace: trace,
    before_files: beforeFiles,
    after_files: files(),
    before_domain: beforeDomain,
    after_domain: rows(),
    source_hashes: sourceHashes,
  };
  fs.writeFileSync(
    join(out, "adapter-results.json"),
    JSON.stringify(adapterResult, null, 2),
  );
  assert.equal(requests, 0);
  assert.equal(deniedResult.details.code, "PERMISSION_DENIED");
  assert.equal(deniedResult.details.source_handle, undefined);
  assert.deepEqual(beforeDomain, rows());
  if (expected === "baseline") {
    assert.ok(sourceReads > 0);
    assert.notDeepEqual(beforeFiles, files());
    assert.equal(ranged.code, "VALIDATION_ERROR");
    assert.equal(coreResult.unicode_split, true);
  } else {
    assert.equal(sourceReads, 0);
    assert.equal(uuidCalls, 0);
    assert.deepEqual(beforeFiles, files());
    if (expected === "fixed") {
      assert.equal(ranged.ok, true);
      assert.equal(ranged.data.text, Array.from(text).slice(8000).join(""));
      assert.equal(coreResult.unicode_split, false);
    } else {
      assert.equal(ranged.code, "VALIDATION_ERROR");
      assert.equal(coreResult.unicode_split, true);
    }
  }
  console.log(
    JSON.stringify(
      {
        expected,
        provider_requests: requests,
        denied_source_reads: sourceReads,
        denied_uuid_calls: uuidCalls,
        long_range_ok: ranged.ok === true,
        unicode_split: coreResult.unicode_split,
        output: out,
      },
      null,
      2,
    ),
  );
} finally {
  watch = null;
  fs.readFileSync = originalRead;
  crypto.randomUUID = originalUUID;
  syncBuiltinESMExports();
  if (session) {
    await session.extensionRunner.emit({
      type: "session_shutdown",
      reason: "exit",
    });
    session.dispose();
  }
}

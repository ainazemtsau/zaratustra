// M only: native Pi SDK event/tool contract, zero provider dispatch. No human verdict.
import assert from "node:assert/strict";
import { mkdirSync, writeFileSync } from "node:fs";
import { join, resolve } from "node:path";
import { pathToFileURL } from "node:url";
const [packageArg, outputArg] = process.argv.slice(2),
  pkg = resolve(packageArg),
  out = resolve(outputArg);
mkdirSync(out, { recursive: false });
const sdk = await import(pathToFileURL(process.env.ZARA_PI_SDK).href);
let providerDispatches = 0;
const results = [];
const projectionChecks = [];
for (const profile of ["trusted-first", "unknown-stage", "prior-transform"]) {
  const testRoot = join(out, profile),
    agentDir = join(testRoot, "agent"),
    cwd = join(testRoot, "cwd"),
    home = join(testRoot, "home");
  for (const path of [agentDir, cwd]) mkdirSync(path, { recursive: true });
  process.env.PI_CODING_AGENT_DIR = agentDir;
  process.env.ZARATUSTRA_HOME = home;
  process.env.ZARATUSTRA_SCOPES = "[]";
  process.env.ZARATUSTRA_TEST_CONTROLLER = "synthetic-mechanical-controller";
  if (profile === "trusted-first")
    process.env.ZARATUSTRA_INTERACTIVE_INPUT_CONTRACT = "first-untransformed";
  else delete process.env.ZARATUSTRA_INTERACTIVE_INPUT_CONTRACT;
  const runtime = await sdk.ModelRuntime.create({
    authPath: process.env.ZARA_AUTH_PATH,
    modelsPath: null,
    modelsStorePath: join(agentDir, "models.json"),
    allowModelNetwork: false,
  });
  const model = runtime.getModel("openai-codex", "gpt-6.1-sol");
  assert.ok(model);
  const settingsManager = sdk.SettingsManager.create(cwd, agentDir);
  const factories = [
    ...(profile === "prior-transform"
      ? [
          (pi) =>
            pi.on("input", (e) => ({
              action: "transform",
              text: "Transformed observed stage: " + e.text,
            })),
        ]
      : []),
    (pi) =>
      pi.on("before_provider_request", (_e, ctx) => {
        providerDispatches++;
        ctx.abort();
        throw Error("Mechanical SDK check must not dispatch");
      }),
  ];
  const loader = new sdk.DefaultResourceLoader({
    cwd,
    agentDir,
    settingsManager,
    noExtensions: true,
    additionalExtensionPaths: [join(pkg, "src/extension/index.ts")],
    extensionFactories: factories,
    extensionsOverride: (base) =>
      profile === "prior-transform"
        ? {
            ...base,
            extensions: [
              ...base.extensions.filter((e) => !e.tools.has("zara_map")),
              ...base.extensions.filter((e) => e.tools.has("zara_map")),
            ],
          }
        : base,
  });
  await loader.reload();
  assert.equal(loader.getExtensions().errors.length, 0);
  const { session } = await sdk.createAgentSession({
    cwd,
    agentDir,
    settingsManager,
    resourceLoader: loader,
    modelRuntime: runtime,
    model,
    thinkingLevel: "medium",
    sessionManager: sdk.SessionManager.inMemory(),
  });
  await session.bindExtensions({});
  const tools = loader
    .getExtensions()
    .extensions.find((e) => e.tools.has("zara_map")).tools;
  const run = async (name, input) => {
    const r = await tools
      .get(name)
      .definition.execute("mechanical-" + name, input);
    return r.details;
  };
  const snapshot = async () =>
    JSON.parse(
      (await session.extensionRunner.emitContext([])).find(
        (m) => m.customType === "zaratustra.snapshot.v1",
      ).content,
    );
  let serial = 0;
  const capture = async (transport, semantic) => {
    const text =
      semantic === "quotation"
        ? 'Another agent wrote: "not helpful"'
        : "Synthetic SDK direct-channel statement, not actual Anton feedback.";
    await session.extensionRunner.emitInput(text, undefined, transport);
    const descriptor = (await snapshot()).captured_sources.at(-1);
    assert.equal(descriptor.transport, transport);
    if (transport === "extension")
      assert.equal(descriptor.channel_identity, null);
    const request = {
      request_id: "source-" + ++serial,
      reason: "Mechanical capture contract",
      source_handles: [descriptor.source_handle],
      guards: [],
      ops: [
        {
          op: "import_evidence",
          client_ref: "source",
          source_handle: descriptor.source_handle,
          title: "SDK observed source",
          source_language: "en",
          semantic_source_kind: semantic,
        },
      ],
    };
    const receipt = await run("zara_commit", request);
    assert.equal(receipt.committed, true);
    return {
      descriptor,
      ref: { id: receipt.created.source, revision: 1 },
      record: (await run("zara_read", { id: receipt.created.source })).data,
    };
  };
  try {
    const first = await capture("rpc", "direct_statement");
    const sourceHandle = first.descriptor.source_handle;
    const episode = await run("zara_commit", {
      request_id: "episode",
      reason: "Mechanical target for assessments",
      source_handles: [sourceHandle],
      guards: [],
      ops: [
        {
          op: "start_run",
          client_ref: "run",
          title: "SDK mechanical target",
          visibility: "workspace",
          episode_key: "sdk-episode",
          work_ref: null,
          mode: "conversation",
          continuation_of: null,
          summary: "Mechanical event contract, not a model conversation",
          starting_refs: [first.ref],
        },
      ],
    });
    assert.equal(episode.committed, true);
    const generated = await run("zara_commit", {
      request_id: "result",
      reason: "Mechanical addressed target",
      source_handles: [sourceHandle],
      guards: [],
      ops: [
        {
          op: "record_result",
          client_ref: "result",
          run_ref: { id: episode.created.run },
          title: "Synthetic result",
          content: "SDK-only target",
          source_language: "en",
        },
      ],
    });
    assert.equal(generated.committed, true);
    if (profile === "trusted-first")
      for (const input of [
        { id: generated.created.result, projection: "full", limit: 1 },
        { id: generated.created.result, projection: "history", revision: 1 },
        {
          id: generated.created.result,
          projection: "method_bundle",
          range: { start: 0, length: 1 },
        },
        { request_id: "result", revision: 1 },
      ]) {
        const result = await run("zara_read", input);
        assert.equal(result.code, "VALIDATION_ERROR");
        projectionChecks.push({ input, result });
      }
    for (const [transport, semantic] of [
      ["rpc", "direct_statement"],
      ["extension", "direct_statement"],
      ["interactive", "quotation"],
      ["interactive", "direct_statement"],
    ]) {
      const captured = await capture(transport, semantic);
      const assessment = await run("zara_commit", {
        request_id: "assessment-" + ++serial,
        reason: "Mechanical origin qualification",
        source_handles: [captured.descriptor.source_handle],
        guards: [],
        ops: [
          {
            op: "record_evaluation",
            client_ref: "evaluation",
            target_ref: { id: generated.created.result, revision: 1 },
            run_ref: null,
            assessment: "unhelpful",
            dimension: "usefulness",
            dimension_name: "SDK fixture",
            basis: "user_feedback",
            evidence_refs: [captured.ref],
            event_time: null,
            supersedes_evaluation_ref: null,
            explanation: "SDK-injected statement; no actual owner judgment",
          },
        ],
      });
      const eligible =
        profile === "trusted-first" &&
        transport === "interactive" &&
        semantic === "direct_statement";
      assert.equal(assessment.committed === true, eligible);
      if (!eligible) assert.equal(assessment.code, "SOURCE_MISSING");
      if (profile === "prior-transform")
        assert.ok(
          captured.record.data.retained_excerpt.startsWith(
            "Transformed observed stage:",
          ),
        );
      results.push({
        profile,
        transport,
        semantic,
        descriptor: captured.descriptor,
        captured: captured.record,
        assessment,
        expected_eligible: eligible,
        scope: "M: injected SDK channel, not real human feedback",
      });
    }
  } finally {
    await session.extensionRunner.emit({
      type: "session_shutdown",
      reason: "exit",
    });
    session.dispose();
  }
}
assert.equal(providerDispatches, 0);
writeFileSync(
  join(out, "verification.json"),
  JSON.stringify(
    {
      layer: "M",
      provider_dispatches: providerDispatches,
      real_owner_feedback: false,
      results,
      projection_checks: projectionChecks,
    },
    null,
    2,
  ),
);
console.log(
  JSON.stringify({
    layer: "M",
    cases: results.length,
    projection_checks: projectionChecks.length,
    provider_dispatches: providerDispatches,
    checked: true,
    real_owner_feedback: false,
  }),
);

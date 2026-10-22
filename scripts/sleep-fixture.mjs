// Mechanical preparation ONLY. Uses installed public Core, never scripted model replies.
// Prior cases and feedback are visibly synthetic; none certify actual owner testimony.
import assert from "node:assert/strict";
import { createRequire } from "node:module";
import { pathToFileURL } from "node:url";
import { resolve, join, relative } from "node:path";
import { mkdirSync, writeFileSync, readFileSync, existsSync } from "node:fs";

const [pkgArg, rootArg, mode = "seed"] = process.argv.slice(2);
const pkg = resolve(pkgArg),
  root = resolve(rootArg);
assert.ok(root.toLowerCase().includes("zaratustra-v1-sleep-evidence-20261022"));
assert.ok(
  relative(pkg, root).startsWith(".."),
  "All fixture state stays outside package storage",
);
mkdirSync(root, { recursive: true });
for (const name of ["cwd", "output", "backups"])
  mkdirSync(join(root, name), { recursive: true });
const { createJiti } = createRequire(pathToFileURL(process.env.ZARA_PI_SDK))(
    "jiti",
  ),
  jiti = createJiti(import.meta.url);
const { Core } = await jiti.import(join(pkg, "src/core/index.ts")),
  { DiskStorage } = await jiti.import(join(pkg, "src/storage/index.ts"));
if (mode === "seed")
  assert.equal(existsSync(join(root, "fixture.json")), false);
const disk = new DiskStorage(join(root, "home")),
  context = {
    ...disk.workspace,
    principal: "trusted-personal",
    session_id: "mechanical-synthetic-preparation",
    runtime_id: "fixture-" + mode,
    processing_allowed: true,
    can_write: true,
    scopes: [],
    environment: {
      fixture: "mechanical preparation only; no provider dispatch",
    },
  },
  core = new Core(disk, context);
let serial = Date.now();
const source = core.capture(
  "Mechanically prepared synthetic exercise. This controller is not the owner; no real-world usefulness or execution is certified.",
  "rpc",
  "sleep-synthetic-fixture",
);
const commit = (ops, ids = []) =>
  core.commit({
    request_id: `sleep-fixture-${mode}-${++serial}`,
    reason: "Mechanical synthetic fixture preparation, not live model behavior",
    source_handles: [source.source_handle],
    guards: ids.map((id) => ({
      ref: { id },
      expected_revision: core.read(id).data.revision,
    })),
    ops,
  });
const evidence = (title, content) => {
  const s = core.capture(content, "rpc", "sleep-synthetic-reported-feedback");
  return core.commit({
    request_id: "fixture-evidence-" + ++serial,
    reason: "Retain synthetic source exactly, not owner testimony",
    source_handles: [s.source_handle],
    guards: [],
    ops: [
      {
        op: "import_evidence",
        client_ref: "e",
        source_handle: s.source_handle,
        title,
        source_language: "en",
      },
    ],
  }).created.e;
};
const work = (client_ref, title, activity = null, context_refs = []) => ({
  op: "create_record",
  kind: "work",
  client_ref,
  title,
  visibility: "workspace",
  data: {
    activity_id: activity ? { id: activity } : null,
    parent_work_id: null,
    objective: title,
    acceptance: [
      {
        criterion_id: "result",
        description:
          "A grounded addressed result consistent with original source conditions",
        verification: "Inspect original source and delivered result",
        required: true,
      },
    ],
    status: "active",
    current_state: "Explicit synthetic task supplied",
    next_action: "Read retained source and relevant guidance",
    steps: [],
    waits: [],
    context_refs,
    completion: null,
  },
});
const fixturePath = join(root, "fixture.json");
try {
  if (mode === "seed") {
    const method = commit([
      {
        op: "create_record",
        kind: "method",
        client_ref: "m",
        title: "Packet unit reconciliation",
        visibility: "workspace",
        data: {
          applicability: "Small packet unit reconciliations from retained rows",
          instructions:
            "Read the packet's original rows. Preserve every exact identifier. Extract each row's unit value, list the units and sum them. Retain a traceable result and report limitations.",
          input_contract: "Exact original packet rows",
          expected_output: "Traceable rows and total units",
          context_requirements: [
            {
              description: "Inspect the current packet's original source",
              refs: [],
              selector: "materials",
              retrieval:
                "Find the packet Evidence and read its exact source body",
            },
          ],
          dependencies: [],
          tool_requirements: ["read"],
          content_version: 1,
          state: "candidate",
          derived_from: [],
          limitations:
            "Synthetic initial candidate; no established usefulness or causal claim",
        },
      },
    ]).created.m;
    const cases = [];
    for (const [index, numbers] of [
      [1, [8, 5, 2]],
      [2, [4, 7, 6]],
    ]) {
      const input = evidence(
        "Synthetic prior packet source " + index,
        `SYNTHETIC SOURCE, not owner testimony. Packet reconciliation protocol: only confirmed operational rows contribute units to the delivered total. Calibration rows are retained for traceability but excluded from the operational total. Preserve exact identifiers.\nP-${index}A | confirmed operational | ${numbers[0]}\nP-${index}B | calibration | ${numbers[1]}\nP-${index}C | confirmed operational | ${numbers[2]}\n`,
      );
      const feedback = evidence(
        "Synthetic prior criterion feedback " + index,
        `Synthetic downstream report about this exact packet: the delivered total included the calibration row and failed the original operational-total criterion. This is a reported assessment from a synthetic controller, not the owner. The observation supports a problem; its cause remains a hypothesis. The operational total from the original is ${numbers[0] + numbers[2]}, while the prior result was ${numbers.reduce((a, b) => a + b, 0)}.`,
      );
      const run = commit([
        {
          op: "start_run",
          client_ref: "r",
          title: "Mechanically prepared prior packet case " + index,
          visibility: "workspace",
          episode_key: "mechanical-prior-packet-" + index,
          work_ref: null,
          mode: "work",
          continuation_of: null,
          summary:
            "Mechanically prepared synthetic prior case, not actual model/tool execution",
          starting_refs: [{ id: input }],
        },
      ]).created.r;
      const bundle = core.methodBundle(method).data;
      const invocation = commit([
        {
          op: "invoke_method",
          client_ref: "i",
          run_ref: { id: run },
          invocation_key: "mechanically-prepared-selection",
          method_ref: bundle.root_ref,
          selected_versions: bundle.selected_versions,
          input_refs: [{ id: input }],
          context_refs: [],
          bindings: {},
          parent_invocation_ref: null,
        },
      ]).created.i;
      const result = commit([
        {
          op: "record_result",
          client_ref: "result",
          run_ref: { id: run },
          title: "Synthetic prior packet output " + index,
          content: `Mechanically prepared prior synthetic result: all three rows included; total ${numbers.reduce((a, b) => a + b, 0)}. No live execution is certified.`,
          source_language: "en",
        },
      ]).created.result;
      commit(
        [
          {
            op: "report_application",
            ref: { id: invocation },
            output_refs: [{ id: result }],
            observation_refs: [],
            reported_application: {
              applied: true,
              summary:
                "Mechanically prepared synthetic report only, not actual observed execution",
              deviations: [],
            },
          },
          {
            op: "finish_run",
            ref: { id: run },
            execution: "completed",
            summary: "Prepared prior case ended; criterion failure remains",
            result_refs: [{ id: result }],
          },
        ],
        [invocation, run],
      );
      const evalSignal = commit([
        {
          op: "record_evaluation",
          client_ref: "e",
          target_ref: { id: result, revision: 1 },
          run_ref: { id: run },
          assessment: "unhelpful",
          dimension: "criterion",
          dimension_name: "Original packet result",
          basis: "reported_feedback",
          evidence_refs: [{ id: feedback }],
          event_time: "2026-10-01T12:00:00Z",
          supersedes_evaluation_ref: null,
          explanation:
            "Synthetic downstream criterion report failed; read addressed feedback and original source before interpreting the cause.",
        },
        {
          op: "open_signal",
          client_ref: "s",
          kind: "problem",
          subject_refs: [{ id: method, content_version: 1 }, { id: run }],
          evidence_refs: [{ id: feedback }, { id: input }, { id: result }],
          description:
            "Prior synthetic packet result failed its source criterion; diagnosis remains open",
          next_check:
            "Review exact grounds, then check a suitable new real execution",
          visibility: "workspace",
        },
      ]);
      cases.push({
        input,
        feedback,
        run,
        invocation,
        result,
        evaluation: evalSignal.created.e,
        signal: evalSignal.created.s,
      });
    }
    writeFileSync(
      fixturePath,
      JSON.stringify(
        { mechanical_preparation: true, owner_testimony: false, method, cases },
        null,
        2,
      ),
    );
  } else if (mode === "next") {
    const fixture = JSON.parse(readFileSync(fixturePath, "utf8"));
    const input = evidence(
      "New synthetic packet job source",
      "SYNTHETIC NEW JOB. Use the established packet protocol. Original rows:\nQ-71 | confirmed operational | 13\nQ-72 | calibration | 9\nQ-73 | confirmed operational | 6\nRetain exact identifiers and the traceable operational total.\n",
    );
    const w = commit([
      work("w", "Reconcile the new retained packet job", null, [{ id: input }]),
    ]).created.w;
    fixture.next = {
      input,
      work: w,
      expectedOperationalTotal: 19,
      excludedIdentifier: "Q-72",
    };
    writeFileSync(fixturePath, JSON.stringify(fixture, null, 2));
  } else if (mode === "scoped") {
    const fixture = JSON.parse(readFileSync(fixturePath, "utf8"));
    const a = commit([
      {
        op: "create_record",
        kind: "activity",
        client_ref: "a",
        title: "Synthetic observatory packets",
        visibility: "workspace",
        data: {
          purpose: "Review this explicitly scoped synthetic work",
          status: "active",
        },
      },
    ]).created.a;
    const e = evidence(
      "Scoped synthetic feedback source",
      "SYNTHETIC REPORTED CHECK. The shared packet Method would be clearer with a compact final operational subtotal and an explicit separate list of retained excluded rows. This is a proposed shared textual adjustment, not a local ownership transfer, owner testimony or proven improvement.",
    );
    const w = commit([
      work("w", "Review scoped packet operational feedback", a, [{ id: e }]),
    ]).created.w;
    const s = commit([
      {
        op: "open_signal",
        client_ref: "s",
        kind: "possible_regression",
        subject_refs: [{ id: w }, { id: fixture.method }],
        evidence_refs: [{ id: e }],
        description:
          "Scoped synthetic feedback concerns shared guidance; ownership is mixed",
        next_check:
          "Explicitly scoped review with exact shared-change authority",
        visibility: "workspace",
      },
    ]).created.s;
    fixture.scoped = { activity: a, work: w, feedback: e, signal: s };
    writeFileSync(fixturePath, JSON.stringify(fixture, null, 2));
  } else throw Error("Unknown mechanical preparation mode");
  console.log(
    JSON.stringify({
      mode,
      mechanical_preparation: true,
      provider_dispatches: 0,
      schema: disk.workspace.schema_version,
    }),
  );
} finally {
  disk.close();
}

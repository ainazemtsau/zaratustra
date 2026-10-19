// Synthetic retained-observation fixture for the separate fresh-process retrieval check.
// This does not claim that a model authored the fixture or test the model create path.
import assert from "node:assert/strict";
import { existsSync, mkdirSync, writeFileSync } from "node:fs";
import { createRequire } from "node:module";
import { join, resolve } from "node:path";
import { pathToFileURL } from "node:url";
const [packageArg, homeArg, outputArg] = process.argv.slice(2);
if (!packageArg || !homeArg || !outputArg)
  throw Error(
    "Usage: node p2-tail.mjs <installed-package> <home> <new-output>",
  );
const output = resolve(outputArg);
assert.equal(existsSync(output), false, "Preserve every fixture output");
mkdirSync(output, { recursive: true });
const sdk = pathToFileURL(process.env.ZARA_PI_SDK);
const { createJiti } = createRequire(sdk)("jiti");
const jiti = createJiti(import.meta.url);
const { Core, digest } = await jiti.import(
  join(resolve(packageArg), "src/core/index.ts"),
);
const { DiskStorage } = await jiti.import(
  join(resolve(packageArg), "src/storage/index.ts"),
);
const disk = new DiskStorage(resolve(homeArg));
try {
  const core = new Core(disk, {
    workspace_id: disk.workspace.workspace_id,
    epoch: disk.workspace.epoch,
    principal: "trusted-personal",
    session_id: "synthetic-tail-controller",
    runtime_id: "synthetic-tail-controller",
    can_write: true,
    processing_allowed: true,
  });
  const prefix =
    "Routine observation: the monitoring session is still in progress. No location instruction appears in this entry.\n"
      .repeat(100)
      .slice(0, 8500);
  const answer =
    "The control sample must be left in the amber cabinet, on its fourth shelf.";
  const text = prefix + "\nFinal handling instruction: " + answer + "\n";
  assert.ok(!Array.from(text).slice(0, 8000).join("").includes(answer));
  const captured = core.capture(text, "rpc", "synthetic-tail-controller");
  const receipt = core.commit({
    request_id: "synthetic-long-observation",
    reason:
      "Retain the exact synthetic observation log for a fresh-process retrieval test.",
    source_handles: [captured.source_handle],
    guards: [],
    ops: [
      {
        op: "import_evidence",
        client_ref: "log",
        source_handle: captured.source_handle,
        title: "Sample handling observation log",
        source_language: "en",
      },
    ],
  });
  const id = receipt.created.log;
  const snapshot = core.snapshot();
  const cards = core.browse("materials");
  const normal = core.read(id, 1);
  for (const representation of [snapshot, cards, normal]) {
    assert.ok(!JSON.stringify(representation).includes("amber cabinet"));
    assert.ok(!JSON.stringify(representation).includes("fourth shelf"));
  }
  const proof = {
    provenance:
      "Mechanically seeded synthetic fixture through installed Core capture/commit; the retrieval model receives no fixture transcript, ID or answer.",
    id,
    code_points: Array.from(text).length,
    content_hash: digest(text),
    answer_start: Array.from(text.slice(0, text.indexOf(answer))).length,
    receipt,
    snapshot,
    cards,
    normal,
  };
  writeFileSync(join(output, "fixture.json"), JSON.stringify(proof, null, 2));
  writeFileSync(join(output, "original.txt"), text);
  console.log(
    JSON.stringify({
      id,
      code_points: proof.code_points,
      answer_start: proof.answer_start,
      short_representations_exclude_answer: true,
    }),
  );
} finally {
  disk.close();
}

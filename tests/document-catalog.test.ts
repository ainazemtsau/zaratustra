import test from "node:test";
import assert from "node:assert/strict";
import type { ExtensionAPI } from "@earendil-works/pi-coding-agent";
import extension from "../src/extension/index.ts";

test("Pi document catalogs are accepted by the advertised schema and actual tool parser", async () => {
  const tools: Parameters<ExtensionAPI["registerTool"]>[0][] = [];
  extension({
    on() {},
    registerTool(tool: Parameters<ExtensionAPI["registerTool"]>[0]) {
      tools.push(tool);
    },
  } as unknown as ExtensionAPI);
  const browse = tools.find((t) => t.name === "zara_browse")!;
  const schema = browse.parameters as unknown as {
    properties: { view: { enum: string[] } };
  };
  for (const view of ["documents", "documents_archive", "documents_removed"]) {
    assert.ok(schema.properties.view.enum.includes(view), view);
    // No workspace/session/provider is opened. Reaching get() rather than Zod rejection
    // proves that the registered Pi adapter accepts the catalog emitted by Core.map().
    const result = await browse.execute(
      "mechanical-catalog-" + view,
      { view },
      undefined,
      undefined,
      {} as Parameters<typeof browse.execute>[4],
    );
    assert.equal(
      (result.details as { code: string }).code,
      "STORE_UNAVAILABLE",
      view,
    );
  }
});

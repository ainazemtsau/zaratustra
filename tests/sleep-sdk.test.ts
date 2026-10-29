import test from "node:test";
import assert from "node:assert/strict";
import { mkdtempSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { Type } from "typebox";
import {
  createAgentSession,
  ModelRuntime,
  SessionManager,
  SettingsManager,
} from "@earendil-works/pi-coding-agent";
import { sleepResourceLoader } from "../src/extension/sleep.ts";

test("native Pi 1.4 SDK constructs the isolated Sleep resource/tool profile without provider dispatch", async () => {
  const root = mkdtempSync(join(tmpdir(), "zara-v2-native-sdk-"));
  const runtime = await ModelRuntime.create({
    authPath: join(root, "auth.json"),
    modelsPath: null,
    modelsStorePath: join(root, "models.json"),
    allowModelNetwork: false,
    refreshOnCreate: false,
  });
  const model = runtime.getModel("openai", "gpt-4.1") ?? runtime.getModels()[0];
  assert.ok(
    model,
    "Installed Pi must provide physical model metadata for a no-dispatch SDK check",
  );
  let dispatches = 0;
  runtime.streamSimple = (() => {
    dispatches++;
    throw new Error("No provider dispatch belongs in construction");
  }) as typeof runtime.streamSimple;
  const resources = sleepResourceLoader();
  const settings = SettingsManager.inMemory({
    cacheWarming: "off",
    compaction: { enabled: false },
    retry: { enabled: false, provider: { maxRetries: 0 } },
  });
  const names = ["sleep_read", "sleep_finish"];
  const { session, modelFallbackMessage } = await createAgentSession({
    cwd: root,
    agentDir: root,
    modelRuntime: runtime,
    model,
    thinkingLevel: "off",
    noTools: "all",
    tools: names,
    customTools: names.map((name) => ({
      name,
      label: name,
      description: "No-dispatch resource construction control",
      parameters: Type.Object({}),
      async execute() {
        return {
          details: {},
          content: [
            {
              type: "text" as const,
              text: "No execution belongs in construction",
            },
          ],
        };
      },
    })),
    resourceLoader: resources,
    settingsManager: settings,
    sessionManager: SessionManager.inMemory(root),
  });
  try {
    assert.equal(modelFallbackMessage, undefined);
    assert.deepEqual(session.getActiveToolNames().sort(), names.sort());
    assert.deepEqual(
      session
        .getAllTools()
        .map((t) => t.name)
        .sort(),
      names.sort(),
    );
    assert.equal(resources.getExtensions().extensions.length, 0);
    assert.equal(resources.getSkills().skills.length, 0);
    assert.equal(resources.getAgentsFiles().agentsFiles.length, 0);
    assert.equal(settings.getCacheWarmingMode(), "off");
    assert.equal(settings.getCompactionEnabled(), false);
    assert.equal(settings.getRetrySettings().enabled, false);
    assert.equal(dispatches, 0);
  } finally {
    session.dispose();
  }
});

import test from "node:test";
import assert from "node:assert/strict";
import { replaceSnapshot, SNAPSHOT_TYPE } from "../src/extension/index.ts";

test("snapshot replacement preserves system, tool, user and unrelated extension data by identity", () => {
  type Message = {
    role: string;
    content: string;
    customType?: string;
    details?: { owner: string; runtime_id: string };
  };
  const system: Message = {
    role: "system",
    content: "Existing host system prompt",
  };
  const user: Message = {
    role: "user",
    content: "Unrelated earlier user input",
  };
  const tool: Message = {
    role: "toolResult",
    content: "Historical result remains historical",
  };
  const foreign: Message = {
    role: "custom",
    customType: SNAPSHOT_TYPE,
    content: "Other owner data",
    details: { owner: "other-extension", runtime_id: "foreign" },
  };
  const old: Message = {
    role: "custom",
    customType: SNAPSHOT_TYPE,
    content: "Old snapshot",
    details: { owner: "zaratustra", runtime_id: "old-runtime" },
  };
  const fresh: Message = {
    ...old,
    content: "Current snapshot",
    details: { owner: "zaratustra", runtime_id: "new-runtime" },
  };
  const input = [system, user, old, tool, foreign];
  const output = replaceSnapshot(input, fresh);
  assert.deepEqual(input, [system, user, old, tool, foreign]);
  assert.equal(output.length, 5);
  for (const message of [system, user, tool, foreign, fresh])
    assert.equal(output.includes(message), true);
  assert.equal(output.includes(old), false);
});

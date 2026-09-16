// Exercise the installed Pi loader and our real subprocess adapter without a model.
import assert from "node:assert/strict";
import { pathToFileURL } from "node:url";
import path from "node:path";

const [piRoot, home] = process.argv.slice(2);
const { loadExtensions } = await import(pathToFileURL(path.join(piRoot, "dist/core/extensions/loader.js")));
async function session(entries = []) {
  const loaded = await loadExtensions([path.join(home, ".pi/extensions/zaratustra.ts")], home);
  assert.deepEqual(loaded.errors, []);
  loaded.runtime.appendEntry = (customType, data) => entries.push({ type: "custom", customType, data });
  const extension = loaded.extensions[0];
  const ctx = { sessionManager: { getBranch: () => entries } };
  const emit = async (name, data) => {
    let result;
    for (const handler of extension.handlers.get(name) ?? []) result = await handler(data, ctx);
    return result;
  };
  await emit("session_start", {});
  const tool = extension.tools.get("zaratustra").definition;
  const call = async (params) => JSON.parse((await tool.execute("technical-probe", params)).content[0].text).result;
  const context = async (messages = []) => {
    const result = await emit("context", { messages });
    const active = result.messages.at(-1);
    return { result, active: JSON.parse(active.content.slice(active.content.indexOf("\n") + 1)) };
  };
  return { emit, call, context, entries };
}
const first = await session();
await first.context();
await first.call({ action: "process.open", process: "A" });
await assert.rejects(first.call({ action: "material.save", title: "Stale target", text: "must refuse" }), /context_changed/);
await first.context();
await first.call({ action: "skill.load", slot: "overview" });
const old = await first.context();
assert.ok(old.active.skills[0].markdown);
const customUser = { role: "user", content: "Do not remove my arbitrary text", timestamp: 1 };
const replaced = await first.context([...old.result.messages, customUser]);
assert.equal(replaced.result.messages.filter(m => m.customType === "zaratustra-active").length, 1);
assert.ok(replaced.result.messages.includes(customUser));

const independent = await session();
await independent.context();
await independent.call({ action: "process.open", process: "A" });
await independent.context();
const switchRequest = first.call({ action: "process.open", process: "B" });
const staleRequest = first.call({ action: "material.save", title: "Queued old action", text: "must refuse" });
const outcomes = await Promise.allSettled([switchRequest, staleRequest]);
assert.equal(outcomes[0].status, "fulfilled");
assert.equal(outcomes[1].status, "rejected");
const b = await first.context();
assert.equal(b.active.process.title, "B");
assert.equal(b.active.skills[0].markdown, undefined);
assert.equal((await independent.context()).active.process.title, "A");
await assert.rejects(first.call({ action: "process.open", process: "Missing process" }));
assert.equal((await first.context()).active.process.title, "B");
const restored = await session(first.entries);
assert.equal((await restored.context()).active.process.title, "B");
assert.ok(first.entries.some(e => e.customType === "zaratustra-context-delivery" && e.data.skills?.some(s => s.body_provided)));
console.log(JSON.stringify({ loader: "installed Pi", current_chat_switch: true, queued_target_refused: true,
  sequential_stale_target_refused: true, independent_session: true, owned_block_replaced: true,
  user_text_preserved: true, failed_switch_preserved: true, restored_session: true, progressive_delivery: true }));

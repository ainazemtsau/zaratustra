import test from "node:test";
import assert from "node:assert/strict";
import { mkdtempSync, mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { Core, digest } from "../src/core/index.ts";
import type { RecordRow } from "../src/core/index.ts";
import { DiskStorage } from "../src/storage/index.ts";

function fixture() {
  const root = mkdtempSync(
    join(process.env.ZARATUSTRA_TEST_ROOT ?? tmpdir(), "zaratustra-p2-"),
  );
  const disk = new DiskStorage(join(root, "home"));
  const core = new Core(disk, {
    workspace_id: disk.workspace.workspace_id,
    epoch: disk.workspace.epoch,
    principal: "trusted-personal",
    session_id: "p2-regression",
    runtime_id: "p2-regression",
    can_write: true,
    processing_allowed: true,
  });
  return { root, disk, core };
}
function retain(core: Core, text: string) {
  const source = core.capture(text, "rpc", "synthetic-regression-controller");
  return core.commit({
    request_id: "retain-once",
    reason: "Retain the exact synthetic source.",
    source_handles: [source.source_handle],
    guards: [],
    ops: [
      {
        op: "import_evidence",
        client_ref: "source",
        source_handle: source.source_handle,
        title: "Synthetic observed source",
        source_language: "en",
      },
    ],
  }).created.source;
}
function domain(disk: DiskStorage) {
  return JSON.stringify(
    ["records", "revisions", "changes", "receipts", "intents"].map((table) =>
      disk.all(`SELECT * FROM ${table} ORDER BY rowid`),
    ),
  );
}
type Excerpt = RecordRow & {
  data: RecordRow["data"] & {
    retained_excerpt: string;
    excerpt_truncated?: boolean;
    must_read_material_range?: boolean;
    range_unit?: string;
    total_characters?: number;
    next_start?: number;
    has_more?: boolean;
  };
};
type Range = {
  ref: { id: string; revision: number };
  text: string;
  range_unit: string;
  start: number;
  total_characters: number;
  has_more: boolean;
  next_start: number;
  content_hash: string;
};
const page = (
  core: Core,
  id: string,
  start: number,
  length = 8000,
  revision?: number,
) => core.read(id, revision, { start, length }).data as unknown as Range;

for (const [name, text, first] of [
  ["long ASCII", "A".repeat(8500) + "\nTAIL-UNIQUE-ELM-93", "A".repeat(8000)],
  [
    "emoji on page boundary",
    "A".repeat(7999) + "🦉" + "B".repeat(519),
    "A".repeat(7999) + "🦉",
  ],
  ["exactly 8000 non-BMP code points", "🦉".repeat(8000), "🦉".repeat(8000)],
  ["exactly 8000 BMP code points", "Z".repeat(8000), "Z".repeat(8000)],
]) {
  test(`retained excerpt: ${name}, bounded reading reconstructs original without mutation`, (t) => {
    const f = fixture();
    t.after(() => f.disk.close());
    const id = retain(f.core, text);
    const before = domain(f.disk);
    const full = f.core.read(id, 1).data as unknown as Excerpt;
    assert.equal(full.data.retained_excerpt, first);
    assert.equal(/[\uD800-\uDBFF]$/.test(full.data.retained_excerpt), false);
    const count = Array.from(text).length;
    assert.equal(full.data.excerpt_truncated ?? false, count > 8000);
    if (count > 8000) {
      assert.equal(full.data.range_unit, "Unicode code points");
      assert.equal(full.data.total_characters, count);
      assert.equal(full.data.next_start, 8000);
      assert.equal(full.data.has_more, true);
      assert.equal(full.data.must_read_material_range, true);
    }
    let recovered = "",
      start = 0;
    while (true) {
      const p = page(f.core, id, start, 8000, 1);
      assert.equal(p.range_unit, "Unicode code points");
      assert.equal(p.ref.revision, 1);
      assert.equal(p.content_hash, digest(text));
      assert.equal(p.start, start);
      assert.equal(p.total_characters, count);
      assert.equal(p.next_start, start + Array.from(p.text).length);
      assert.equal(p.has_more, p.next_start < count);
      recovered += p.text;
      if (!p.has_more) break;
      assert.ok(p.next_start > start);
      start = p.next_start;
    }
    assert.equal(recovered, text);
    assert.equal(digest(recovered), digest(text));
    const end = page(f.core, id, count, 1, 1);
    assert.equal(end.text, "");
    assert.equal(end.next_start, count);
    assert.equal(end.has_more, false);
    assert.equal(domain(f.disk), before);
  });
}
test("import preflight uses Core processing, identity and write authority", (t) => {
  const f = fixture();
  t.after(() => f.disk.close());
  const before = domain(f.disk);
  f.core.context.processing_allowed = false;
  assert.throws(() => f.core.authorizeImport(), /authority is unresolved/);
  f.core.context.processing_allowed = true;
  f.core.context.can_write = false;
  assert.throws(() => f.core.authorizeImport(), /writes are disabled/);
  f.core.context.can_write = true;
  const epoch = f.core.context.epoch;
  f.core.context.epoch = "wrong";
  assert.throws(() => f.core.authorizeImport(), /epoch mismatch/);
  f.core.context.epoch = epoch;
  assert.doesNotThrow(() => f.core.authorizeImport());
  assert.equal(domain(f.disk), before);
});
test("historical excerpt ranges use the requested revision, not current text", (t) => {
  const f = fixture();
  t.after(() => f.disk.close());
  const original = "A".repeat(8000) + " original tail 🦉";
  const id = retain(f.core, original);
  const first = f.core.read(id, 1).data as unknown as RecordRow;
  const changed = "B".repeat(8000) + " newer tail 🌍";
  // Deliberately seed a historical storage fixture; no Evidence-update product API is added.
  const current = {
    ...first,
    revision: 2,
    data: {
      ...first.data,
      retained_excerpt: changed,
      content_hash: digest(changed),
    },
  };
  f.disk.run(
    "UPDATE records SET json=? WHERE id=?",
    JSON.stringify(current),
    id,
  );
  f.disk.run(
    "INSERT INTO revisions(id,revision,json) VALUES(?,?,?)",
    id,
    2,
    JSON.stringify(current),
  );
  const before = domain(f.disk);
  const old = page(f.core, id, 8000, 8000, 1),
    now = page(f.core, id, 8000);
  assert.equal(old.text, " original tail 🦉");
  assert.equal(old.content_hash, digest(original));
  assert.equal(old.ref.revision, 1);
  assert.equal(now.text, " newer tail 🌍");
  assert.equal(now.content_hash, digest(changed));
  assert.equal(now.ref.revision, 2);
  assert.equal(
    (f.core.read(id, 1).data as unknown as Excerpt).data.retained_excerpt,
    "A".repeat(8000),
  );
  assert.equal(domain(f.disk), before);
});
test("authorized imported material still retains exact BOM/CRLF bytes and code-point ranges", (t) => {
  const f = fixture();
  t.after(() => f.disk.close());
  const inputs = join(f.root, "inputs");
  mkdirSync(inputs);
  const path = join(inputs, "original.md");
  const bytes = Buffer.from("\ufeff# Material\r\n🦉 🌍 Original.\r\n");
  writeFileSync(path, bytes);
  f.core.authorizeImport();
  const material = f.disk.importFile(path, [inputs]);
  const source = f.core.capture(material.text, "file", null, material);
  const receipt = f.core.commit({
    request_id: "material",
    reason: "Retain authorized bytes.",
    source_handles: [source.source_handle],
    guards: [],
    ops: [
      {
        op: "import_evidence",
        client_ref: "source",
        source_handle: source.source_handle,
        title: "Synthetic material",
        source_language: "en",
      },
    ],
  });
  const before = domain(f.disk);
  assert.deepEqual(
    readFileSync(join(f.disk.home, "materials", material.blob_ref)),
    bytes,
  );
  assert.equal(material.blob_ref, digest(bytes));
  assert.equal(
    page(f.core, receipt.created.source, 0).text,
    bytes.toString("utf8"),
  );
  assert.equal(
    page(f.core, receipt.created.source, 13, 2).text,
    Array.from(bytes.toString("utf8")).slice(13, 15).join(""),
  );
  assert.equal(domain(f.disk), before);
});
test("retained excerpt ranges keep explicit invalid-range errors", (t) => {
  const f = fixture();
  t.after(() => f.disk.close());
  const id = retain(f.core, "Original 🦉");
  const before = domain(f.disk);
  for (const [start, length] of [
    [-1, 1],
    [0, 0],
    [0, 8001],
  ])
    assert.throws(() => f.core.read(id, 1, { start, length }), /range/);
  assert.equal(domain(f.disk), before);
});

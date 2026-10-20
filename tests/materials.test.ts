import test from "node:test";
import assert from "node:assert/strict";
import {
  mkdtempSync,
  mkdirSync,
  readFileSync,
  writeFileSync,
  copyFileSync,
  unlinkSync,
  readdirSync,
} from "node:fs";
import { tmpdir } from "node:os";
import { join, resolve } from "node:path";
import { Core, digest, type RecordRow } from "../src/core/index.ts";
import { DiskStorage } from "../src/storage/index.ts";

function setup() {
  const root = mkdtempSync(
      join(process.env.ZARATUSTRA_TEST_ROOT ?? tmpdir(), "zara-materials-"),
    ),
    home = join(root, "home"),
    inputs = join(root, "inputs");
  mkdirSync(inputs);
  const disk = new DiskStorage(home),
    core = new Core(disk, {
      ...disk.workspace,
      principal: "trusted-personal",
      session_id: "synthetic",
      runtime_id: "synthetic",
      can_write: true,
      processing_allowed: true,
    });
  let n = 0;
  const retain = async (name: string) => {
    const path = join(inputs, name);
    copyFileSync(resolve("tests/fixtures/c", name), path);
    const m = await disk.importMaterial(path, [inputs], () =>
      core.authorizeImport(),
    );
    const s = core.capture(m.text, "file", null, m);
    const r = core.commit({
      request_id: "import-" + ++n,
      reason: "Retain synthetic parser fixture",
      source_handles: [s.source_handle],
      guards: [],
      ops: [
        {
          op: "import_evidence",
          client_ref: "original",
          source_handle: s.source_handle,
          title: name,
          source_language: "en",
        },
      ],
    });
    const original = core.read(r.created.original).data as RecordRow;
    const derived = original.data.text_derivative_ref as { id: string } | null;
    return { path, m, r, original, derived };
  };
  return { root, home, inputs, disk, core, retain };
}

test("TXT, multipage PDF and multichapter EPUB keep exact original bytes, separate text, stable code-point ranges and locators after source removal", async () => {
  const f = setup();
  for (const name of ["notes.md", "book.pdf", "book.epub"]) {
    const b = await f.retain(name),
      original = readFileSync(b.path);
    assert.deepEqual(
      readFileSync(join(f.home, "materials", b.m.blob_ref)),
      original,
    );
    assert.equal(digest(original), b.original.data.content_hash);
    assert.equal(b.m.extraction.status, "readable");
    assert.ok(b.derived);
    assert.throws(
      () => f.core.read(b.original.id, undefined, { start: 0, length: 10 }),
      /text_derivative_ref/,
    );
    unlinkSync(b.path);
    const d = f.core.read(b.derived!.id).data as RecordRow;
    assert.deepEqual(d.data.derived_from, { id: b.original.id, revision: 1 });
    assert.equal(d.data.source_hash, digest(original));
    assert.equal(d.data.parser, b.m.extraction.parser);
    assert.equal(d.data.parser_version, b.m.extraction.parser_version);
    let reconstructed = "",
      start = 0;
    do {
      const page = f.core.read(d.id, 1, { start, length: 2713 })
        .data as unknown as {
        text: string;
        has_more: boolean;
        next_start: number;
      };
      reconstructed += page.text;
      if (!page.has_more) break;
      assert.ok(page.next_start > start);
      start = page.next_start;
    } while (true);
    assert.equal(reconstructed, b.m.text);
    assert.equal(digest(reconstructed), d.data.content_hash);
    assert.equal(
      Array.from(reconstructed).length,
      b.m.extraction.total_characters,
    );
    for (const section of b.m.extraction.sections) {
      let part = "",
        at = 0;
      do {
        const page = f.core.read(
          d.id,
          1,
          { start: at, length: 2713 },
          section.locator,
        ).data as unknown as { text: string; section_next_start: number };
        part += page.text;
        at = page.section_next_start;
        if (at >= section.end - section.start) break;
      } while (true);
      assert.equal(
        part,
        Array.from(reconstructed).slice(section.start, section.end).join(""),
      );
    }
    if (name.endsWith("pdf")) {
      assert.equal(b.m.extraction.sections.length, 3);
      assert.match(reconstructed, /drawer L-42/);
    }
    if (name.endsWith("epub")) {
      assert.equal(b.m.extraction.sections.length, 2);
      assert.match(reconstructed, /niche M-73/);
      assert.match(reconstructed, /🦉/);
      assert.doesNotMatch(reconstructed, /fetch\(/);
    }
  }
  f.disk.close();
});

test("scanned/blank, encrypted, damaged, unsafe, unsupported and partly missing books expose honest availability", async () => {
  const f = setup();
  for (const [name, status] of [
    ["blank.pdf", "scanned"],
    ["encrypted.pdf", "encrypted"],
    ["damaged.pdf", "damaged"],
    ["encrypted.epub", "encrypted"],
    ["image-only.epub", "scanned"],
    ["traversal.epub", "damaged"],
    ["partial.epub", "partial"],
    ["entities.epub", "partial"],
    ["remote.epub", "readable"],
  ]) {
    const b = await f.retain(name);
    assert.equal(b.m.extraction.status, status, name);
    assert.equal(b.original.data.availability, "retained");
    assert.equal(!!b.derived, ["readable", "partial"].includes(status));
    if (status !== "readable") assert.ok(b.m.extraction.warnings.length, name);
    if (status === "partial") {
      const unavailable = b.m.extraction.sections.find((s) => !s.available)!;
      assert.throws(
        () =>
          f.core.read(b.derived!.id, undefined, undefined, unavailable.locator),
        /no available/,
      );
    }
  }
  const unsupported = join(f.inputs, "opaque.docx");
  writeFileSync(unsupported, "synthetic opaque bytes");
  const m = await f.disk.importMaterial(unsupported, [f.inputs], () =>
    f.core.authorizeImport(),
  );
  assert.equal(m.extraction.status, "unsupported");
  assert.equal(m.extraction.text_blob_ref, null);
  assert.equal(readdirSync(f.root).includes("escape.txt"), false);
  f.disk.close();
});

test("every new import authorizes before source access and rechecks after async extraction; interrupts never create records/handles", async () => {
  const f = setup(),
    missing = join(f.inputs, "does-not-exist.pdf");
  const before = readdirSync(join(f.home, "materials"));
  let authorized = false;
  await assert.rejects(
    f.disk.importMaterial(missing, [f.inputs], () => {
      authorized = true;
      f.core.context.processing_allowed = false;
      f.core.authorizeImport();
    }),
    /authority/,
  );
  assert.ok(authorized);
  assert.deepEqual(readdirSync(join(f.home, "materials")), before);
  f.core.context.processing_allowed = true;
  const source = join(f.inputs, "book.pdf");
  copyFileSync(resolve("tests/fixtures/c/book.pdf"), source);
  let calls = 0;
  await assert.rejects(
    f.disk.importMaterial(source, [f.inputs], () => {
      if (++calls === 2) f.core.context.processing_allowed = false;
      f.core.authorizeImport();
    }),
    /authority/,
  );
  assert.equal(calls, 2);
  assert.deepEqual(readdirSync(join(f.home, "materials")), before);
  f.core.context.processing_allowed = true;
  for (const point of ["after_stage", "after_rename"]) {
    await assert.rejects(
      f.disk.importMaterial(
        source,
        [f.inputs],
        () => f.core.authorizeImport(),
        undefined,
        (p) => {
          if (p === point) throw new Error("synthetic interrupted import");
        },
      ),
      /interrupted/,
    );
    assert.equal(f.core.sequence(), 0);
    assert.equal(f.core.browse("materials").data.cards.length, 0);
  }
  const abort = new AbortController();
  abort.abort();
  await assert.rejects(
    f.disk.importMaterial(
      source,
      [f.inputs],
      () => f.core.authorizeImport(),
      abort.signal,
    ),
    /cancelled|invalidated/,
  );
  f.disk.close();
});

test("book bounds exceed old TXT limit, extraction output and archive expansion stay bounded", async () => {
  const f = setup();
  const b = await f.retain("large.pdf");
  assert.ok(b.m.byte_length > 1024 * 1024);
  assert.equal(b.m.extraction.sections.length, 700);
  assert.match(b.m.text, /Book page 699/);
  const limited = await f.retain("output-limit.epub");
  assert.equal(limited.m.extraction.status, "partial");
  assert.equal(limited.m.extraction.total_characters, 8_000_000);
  const zip = await f.retain("zip-limit.epub");
  assert.equal(zip.m.extraction.status, "limit_exceeded");
  assert.equal(zip.derived, null);
  const txt = join(f.inputs, "oversized.txt");
  writeFileSync(txt, Buffer.alloc(1024 * 1024 + 1, 65));
  await assert.rejects(
    f.disk.importMaterial(txt, [f.inputs], () => f.core.authorizeImport()),
    /size limit/,
  );
  // A sparse oversized book checks the new 64 MiB source limit before read/parse.
  const pdf = join(f.inputs, "oversized.pdf");
  writeFileSync(pdf, Buffer.alloc(64 * 1024 * 1024 + 1));
  await assert.rejects(
    f.disk.importMaterial(pdf, [f.inputs], () => f.core.authorizeImport()),
    /size limit/,
  );
  f.disk.close();
});

test("new material transaction faults preserve original/text linkage and receipt atomicity on reopen", async () => {
  for (const point of [
    "after_prepare",
    "after_records",
    "before_commit",
    "after_commit",
  ]) {
    const f = setup();
    const path = resolve("tests/fixtures/c/book.epub");
    const m = await f.disk.importMaterial(
      path,
      [resolve("tests/fixtures/c")],
      () => f.core.authorizeImport(),
    );
    const c = new Core(f.disk, f.core.context, (p) => {
      if (p === point) throw new Error("synthetic import commit fault");
    });
    const s = c.capture(m.text, "file", null, m);
    assert.throws(
      () =>
        c.commit({
          request_id: "fault",
          reason: "Atomic original and extraction",
          source_handles: [s.source_handle],
          guards: [],
          ops: [
            {
              op: "import_evidence",
              client_ref: "book",
              source_handle: s.source_handle,
              title: "Synthetic book",
              source_language: "en",
            },
          ],
        }),
      /fault/,
    );
    f.disk.close();
    const reopened = new DiskStorage(f.home);
    assert.equal(
      reopened.get<{ n: number }>("SELECT count(*) AS n FROM records")!.n,
      point === "after_commit" ? 2 : 0,
    );
    assert.equal(
      reopened.get<{ n: number }>("SELECT count(*) AS n FROM receipts")!.n,
      point === "after_commit" ? 1 : 0,
    );
    reopened.close();
  }
});

test("schema-1 migration preserves every row and material; before/after-commit failures retain a verifiable backup and recover without reset", () => {
  for (const point of [
    "after_backup",
    "before_schema_commit",
    "after_schema_commit",
  ]) {
    const f = setup();
    const s = f.core.capture("Original 🦉 retained", "rpc", "synthetic");
    f.core.commit({
      request_id: "old-data",
      reason: "Original pre-upgrade record",
      source_handles: [s.source_handle],
      guards: [],
      ops: [
        {
          op: "import_evidence",
          client_ref: "e",
          source_handle: s.source_handle,
          title: "Existing Evidence",
          source_language: "en",
        },
      ],
    });
    // A schema-1 structural fixture, separately complemented by actual 27a74fd upgrade.
    f.disk.workspace.schema_version = 1;
    f.disk.run("UPDATE meta SET json=?", JSON.stringify(f.disk.workspace));
    f.disk.exec(
      "DROP TABLE claims; DROP TABLE handoffs; DROP TABLE migrations; PRAGMA user_version=1;",
    );
    writeFileSync(
      join(f.home, "workspace.json"),
      JSON.stringify(f.disk.workspace),
    );
    const tables = [
      "records",
      "revisions",
      "changes",
      "intents",
      "receipts",
      "focus",
    ];
    const before = tables.map((t) => f.disk.all("SELECT * FROM " + t));
    f.disk.close();
    assert.throws(
      () =>
        new DiskStorage(f.home, (p) => {
          if (p === point) throw new Error("synthetic migration interruption");
        }),
      /interruption/,
    );
    const recovered = new DiskStorage(f.home);
    assert.equal(recovered.workspace.schema_version, 2);
    assert.deepEqual(
      tables.map((t) => recovered.all("SELECT * FROM " + t)),
      before,
    );
    assert.ok(
      readdirSync(f.home).some(
        (s) => s.startsWith("pre-schema-2-") && s.endsWith(".sqlite"),
      ),
    );
    const receipt = recovered.get<{ json: string }>(
      "SELECT json FROM migrations WHERE version=2",
    )!;
    const info = JSON.parse(receipt.json);
    assert.equal(digest(readFileSync(info.backup)), info.backup_sha256);
    recovered.close();
    const again = new DiskStorage(f.home);
    assert.equal(again.workspace.schema_version, 2);
    again.close();
  }
});

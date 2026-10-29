import test from "node:test";
import assert from "node:assert/strict";
import { z } from "zod";
import fastUri from "fast-uri";
import {
  CommitSchema,
  DocumentPath,
  documentText,
  validateDocument,
} from "../src/core/index.ts";

// Bounded checks only: no huge allocations, timers, network or exploit traffic.
test("dependency patch: constrained arrays, sets and maps reject size before element validation", () => {
  let visited = 0;
  const item = z.string().superRefine(() => {
    visited++;
  });
  const cases = [
    { schema: z.array(item).max(2), input: ["a", "b", "c"], valid: ["a", "b"] },
    {
      schema: z.set(item).max(2),
      input: new Set(["a", "b", "c"]),
      valid: new Set(["a", "b"]),
    },
    {
      schema: z.map(z.string(), item).max(2),
      input: new Map([
        ["a", "a"],
        ["b", "b"],
        ["c", "c"],
      ]),
      valid: new Map([
        ["a", "a"],
        ["b", "b"],
      ]),
    },
  ];
  for (const { schema, input, valid } of cases) {
    visited = 0;
    const rejected = schema.safeParse(input);
    assert.equal(rejected.success, false);
    assert.equal(
      visited,
      0,
      "oversized constrained input must not validate every element",
    );
    assert.equal(schema.safeParse(valid).success, true);
    assert.equal(visited, 2);
  }
});

test("dependency patch: commit contracts and generated tool schema retain strict types and limits", () => {
  const op = { op: "set_focus", activity_ref: null, work_ref: null };
  const request = {
    request_id: "bounded-fixture",
    reason: "Mechanical check",
    source_handles: ["fixture"],
    guards: [],
    ops: [op],
  };
  assert.equal(CommitSchema.safeParse(request).success, true);
  for (const bad of [
    { ...request, ops: Array(21).fill(op) },
    { ...request, source_handles: Array(11).fill("fixture") },
    { ...request, reason: "x".repeat(4001) },
    { ...request, approved: true },
    { ...request, ops: [{ ...op, op: "not_an_operation" }] },
  ])
    assert.equal(CommitSchema.safeParse(bad).success, false);
  const json = z.toJSONSchema(CommitSchema, { target: "draft-7" });
  const properties = json.properties as Record<string, { maxItems?: number }>;
  assert.equal(json.additionalProperties, false);
  assert.equal(properties.ops.maxItems, 20);
  assert.equal(properties.source_handles.maxItems, 10);
});

const key = "3ec7246d-d358-46de-859e-56839e741594";
const block = (data: unknown) => "```json\n" + JSON.stringify(data) + "\n```\n";
const schema = {
  $schema: "https://json-schema.org/draft/2020-12/schema",
  $id: "https://example.invalid/formats/items.json",
  type: "array",
  maxItems: 3,
  items: { $ref: "#/$defs/item" },
  $defs: {
    item: {
      type: "object",
      required: ["name", "quantity"],
      additionalProperties: false,
      properties: {
        name: { type: "string", minLength: 1 },
        quantity: { type: "integer", minimum: 1 },
      },
    },
  },
};

test("dependency patch: document JSON Schema 2020-12 refs still validate content strictly", () => {
  const format = block(schema);
  assert.doesNotThrow(() =>
    validateDocument(
      documentText(key, block([{ name: "example", quantity: 2 }])),
      key,
      format,
    ),
  );
  for (const bad of [
    [{ name: "example" }],
    [{ name: "example", quantity: "two" }],
    [{ name: "example", quantity: 1, unexpected: true }],
    Array(4).fill({ name: "example", quantity: 1 }),
  ])
    assert.throws(
      () => validateDocument(documentText(key, block(bad)), key, format),
      /does not match/,
    );
  assert.throws(
    () =>
      validateDocument(
        documentText(key, block([])),
        key,
        block({ ...schema, $async: true }),
      ),
    /Async document schemas/,
  );
});

test("dependency patch: document identity, paths and byte bounds still reject invalid input", () => {
  assert.equal(DocumentPath.safeParse("example/report.md").success, true);
  for (const path of [
    "../report.md",
    "/report.md",
    "C:/report.md",
    "a//report.md",
    "a/./report.md",
    "report.txt",
  ])
    assert.equal(DocumentPath.safeParse(path).success, false);
  assert.throws(
    () =>
      validateDocument(
        documentText("3ec7246d-d358-46de-859e-56839e741595", "example"),
        key,
      ),
    /identity/,
  );
  assert.throws(
    () => validateDocument(documentText(key, "x".repeat(64000)), key),
    /64,000/,
  );
});

// Small representative cases from the upstream security tests, not a claim
// that this application exposed a network URL allowlist or was exploited.
test("dependency patch: URI normalization cannot decode an encoded scheme or introduce authority", () => {
  const encoded = "ht%74ps://example.invalid/";
  assert.match(fastUri.parse(encoded).error ?? "", /scheme is malformed/);
  assert.equal(fastUri.normalize(encoded), encoded);
  assert.equal(fastUri.equal(encoded, "https://example.invalid/"), false);
  const relative = fastUri.normalize("a/..//x");
  assert.equal(relative, ".//x");
  assert.equal(fastUri.parse(relative).host, undefined);
  assert.equal(fastUri.parse(fastUri.normalize("./a:b")).scheme, undefined);
  assert.equal(
    fastUri.resolve("https://example.invalid/a/b/", fastUri.normalize("../x")),
    "https://example.invalid/a/x",
  );
});

test("dependency patch: malformed host delimiters fail closed while valid hosts normalize", () => {
  for (const host of [
    "b@other.invalid",
    "ex\tample.invalid",
    "ex\nample.invalid",
    "ex\rample.invalid",
  ]) {
    const uri = `https://user@${host}/path`;
    assert.match(fastUri.parse(uri).error ?? "", /host is malformed/);
    assert.equal(fastUri.normalize(uri), uri);
    assert.throws(
      () => fastUri.resolve("https://example.invalid/", `//user@${host}/path`),
      /host is malformed/,
    );
  }
  assert.equal(
    fastUri.normalize("https://Example.INVALID/a"),
    "https://example.invalid/a",
  );
});

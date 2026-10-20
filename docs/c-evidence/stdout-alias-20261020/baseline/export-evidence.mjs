// Developer-only export of finished, explicitly sealed synthetic inputs.
// No runtime resource imports this script; it is not a product export/backup API.
import assert from "node:assert/strict";
import {
  readFileSync,
  writeFileSync,
  realpathSync,
  existsSync,
  mkdirSync,
} from "node:fs";
import { resolve, relative, isAbsolute, dirname, extname } from "node:path";
import { createHash } from "node:crypto";
import { gzipSync } from "node:zlib";

const [sealedArg, outputArg, stdoutArg] = process.argv.slice(2);
assert(
  sealedArg && outputArg && stdoutArg,
  "Usage: node export-evidence.mjs sealed-inputs.json new-output current-stdout-log",
);
const sealed = JSON.parse(
  readFileSync(sealedArg, "utf8").replace(/^\uFEFF/, ""),
);
const root = realpathSync(sealed.root),
  output = resolve(outputArg),
  stdout = resolve(stdoutArg);
const hash = (b) => createHash("sha256").update(b).digest("hex");
assert(!existsSync(output), "Export destination must be new");
assert(
  Array.isArray(sealed.entries) && sealed.entries.length > 0,
  "A fixed input list is required; no live globs",
);
const seen = new Set();
const sources = sealed.entries.map((entry) => {
  assert(typeof entry.path === "string" && !isAbsolute(entry.path));
  const path = realpathSync(resolve(root, entry.path)),
    rel = relative(root, path);
  assert(
    rel &&
      rel !== ".." &&
      !rel.startsWith("..\\") &&
      !rel.startsWith("../") &&
      !isAbsolute(rel),
    "Source escapes sealed root",
  );
  assert(
    path !== stdout && resolve(root, entry.path) !== stdout,
    "Current exporter stdout cannot be an input",
  );
  assert(!seen.has(entry.path), "Duplicate sealed input");
  seen.add(entry.path);
  const bytes = readFileSync(path);
  assert.equal(
    bytes.length,
    entry.bytes,
    "Sealed source length changed: " + entry.path,
  );
  assert.equal(
    hash(bytes),
    entry.sha256,
    "Sealed source digest changed: " + entry.path,
  );
  return { entry, path, bytes };
});
const replacements = [
  [root, "<SYNTHETIC_EVIDENCE_ROOT>"],
  ...(sealed.redactions ?? []),
];
const string = (value) => {
  for (const [from, to] of replacements) {
    assert(from && to);
    for (const n of [4, 2, 1])
      value = value.split(from.replaceAll("\\", "\\".repeat(n))).join(to);
    value = value.split(from.replaceAll("\\", "/")).join(to);
  }
  return value;
};
const clean = (value) => {
  if (Array.isArray(value))
    return value.map(clean).filter((v) => v !== undefined);
  if (value && typeof value === "object") {
    if (["thinking", "redactedThinking", "reasoning"].includes(value.type))
      return undefined;
    return Object.fromEntries(
      Object.entries(value)
        .filter(
          ([k]) =>
            !["encrypted_content", "signature", "redactedThinking"].includes(k),
        )
        .map(([k, v]) => [k, clean(v)]),
    );
  }
  if (typeof value === "string") {
    if (/^[{[]/.test(value)) {
      try {
        return JSON.stringify(clean(JSON.parse(value)));
      } catch {
        /* ordinary text */
      }
    }
    return string(value);
  }
  return value;
};
const exported = sources.map(({ entry, bytes }) => {
  const text = new TextDecoder("utf-8", { fatal: true })
    .decode(bytes)
    .replace(/^\uFEFF/, "");
  const suffix = extname(entry.path);
  let value;
  if (suffix === ".json")
    value = JSON.stringify(clean(JSON.parse(text)), null, 2) + "\n";
  else if (suffix === ".jsonl")
    value = text
      .split(/\r?\n/)
      .filter(Boolean)
      .map((line) => JSON.stringify(clean(JSON.parse(line))) + "\n")
      .join("");
  else value = string(text);
  value = value.replaceAll("\r\n", "\n").replaceAll("\r", "\n");
  assert(
    !/\bsk-[A-Za-z0-9_-]{20,}\b/.test(value),
    "Possible credential in derivative",
  );
  let derivative = Buffer.from(value),
    path = entry.path.replaceAll("\\", "/");
  const transforms = [
    "UTF-8 without BOM; canonical LF; declared local-path substitutions",
  ];
  if ([".json", ".jsonl"].includes(suffix))
    transforms.push(
      "parse/serialize JSON, including embedded JSON strings; omit reasoning blocks and encrypted reasoning",
    );
  if (path.endsWith("provider-requests.jsonl")) {
    derivative = gzipSync(derivative);
    path += ".gz";
    transforms.push("deterministic gzip");
  }
  return {
    derivative,
    manifest: {
      original_relative_path: entry.path,
      original_sha256: hash(bytes),
      original_bytes: bytes.length,
      derivative_path: path,
      derivative_sha256: hash(derivative),
      derivative_bytes: derivative.length,
      transforms,
    },
  };
});
// Validate the entire fixed source set again before publication. Never hash a live
// directory glob or a redirected stdout file while this exporter is still writing.
for (const { entry, path } of sources)
  assert.equal(
    hash(readFileSync(path)),
    entry.sha256,
    "Source changed during export",
  );
mkdirSync(output, { recursive: true });
for (const { derivative, manifest } of exported) {
  const path = resolve(output, manifest.derivative_path);
  mkdirSync(dirname(path), { recursive: true });
  writeFileSync(path, derivative);
  assert.equal(hash(readFileSync(path)), manifest.derivative_sha256);
}
writeFileSync(
  resolve(output, "manifest.json"),
  JSON.stringify(
    {
      synthetic: true,
      sealed_inputs_sha256: hash(readFileSync(sealedArg)),
      source_policy:
        "finished fixed inputs, SHA256 checked before and after; current stdout excluded",
      entries: exported.map((e) => e.manifest),
    },
    null,
    2,
  ) + "\n",
);
console.log(JSON.stringify({ exported: exported.length, validated: true }));

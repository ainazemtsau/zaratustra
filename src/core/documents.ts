import { Ajv2020 } from "ajv/dist/2020.js";
import { z } from "zod";
import { requireThat, type RecordRow } from "./contracts.ts";

export const DocumentPath = z
  .string()
  .min(1)
  .max(500)
  .refine(
    (p) =>
      !p.includes("\\") &&
      !p.includes(":") &&
      !p.startsWith("/") &&
      p
        .split("/")
        .every((s) => !!s && s !== "." && s !== ".." && !/[. ]$/.test(s)) &&
      /\.md$/i.test(p),
    "Use a relative Markdown path below the trusted activities root.",
  );
const Exact = z.strictObject({
  id: z.string().min(1),
  revision: z.number().int().positive(),
});
export const DocumentBinding = z.strictObject({
  ref: Exact.nullable(),
  key: z.string().uuid(),
  path: DocumentPath,
  document_type: z.string().min(1).max(100),
  state: z.enum(["active", "archived", "removed"]),
  activity_ref: Exact.nullable(),
  format_ref: Exact.nullable(),
  links: z.array(Exact).max(30),
  title: z.string().min(1).max(4000),
  visibility: z.enum(["workspace", "restricted"]),
  source_language: z.string().min(1).max(100),
  previous_path: DocumentPath.nullable(),
  previous_hash: z
    .string()
    .regex(/^[a-f0-9]{64}$/)
    .nullable(),
});
export const DocumentMetadata = DocumentBinding.omit({
  ref: true,
  title: true,
  visibility: true,
  source_language: true,
  previous_path: true,
  previous_hash: true,
  activity_ref: true,
}).extend({ head_ref: Exact, operation_id: z.string().min(1) });
export type DocumentPlan = z.infer<typeof DocumentBinding>;

export function documentKey(text: string) {
  const matches = [
    ...text.matchAll(/<!-- zaratustra-document: ([0-9a-f-]{36}) -->/g),
  ];
  requireThat(
    matches.length === 1,
    "VALIDATION_ERROR",
    "A managed document needs exactly one stable zaratustra-document comment.",
  );
  return z.string().uuid().parse(matches[0][1]);
}
export function documentText(key: string, text: string) {
  const matches = [
    ...text.matchAll(/<!-- zaratustra-document: ([0-9a-f-]{36}) -->/g),
  ];
  if (!matches.length) return `<!-- zaratustra-document: ${key} -->\n${text}`;
  requireThat(
    documentKey(text) === key,
    "VALIDATION_ERROR",
    "Document identity cannot change through an edit.",
  );
  return text;
}
/** A single standard JSON block holds structured data. Markdown remains ordinary text. */
export function documentData(text: string) {
  const blocks = [...text.matchAll(/^```json\s*\r?\n([\s\S]*?)^```\s*$/gm)];
  requireThat(
    blocks.length === 1,
    "VALIDATION_ERROR",
    "Structured documents need exactly one fenced json data block.",
  );
  return JSON.parse(blocks[0][1]) as unknown;
}
export function validateDocument(
  text: string,
  key: string,
  schemaText?: string,
) {
  requireThat(
    Buffer.byteLength(text) <= 64000,
    "VALIDATION_ERROR",
    "Split large documents into addressed files of at most 64,000 UTF-8 bytes.",
  );
  requireThat(
    documentKey(text) === key,
    "VALIDATION_ERROR",
    "Observed file identity differs from the registered document.",
  );
  if (schemaText !== undefined) {
    const schema = documentData(schemaText);
    requireThat(
      schema && typeof schema === "object",
      "VALIDATION_ERROR",
      "The format must contain a JSON Schema 2020-12 object.",
    );
    const ajv = new Ajv2020({ strict: true, validateFormats: false });
    const valid = ajv.compile(schema);
    requireThat(
      !(valid as unknown as { $async?: boolean }).$async,
      "VALIDATION_ERROR",
      "Async document schemas are unsupported.",
    );
    requireThat(
      valid(documentData(text)),
      "VALIDATION_ERROR",
      "Document data does not match its pinned format: " +
        ajv.errorsText(valid.errors),
    );
  }
}
export function managedDocument(row: RecordRow) {
  requireThat(
    row.kind === "entity" && row.data.document,
    "REFERENCE_TYPE_MISMATCH",
    "Expected a managed document resource.",
  );
  return DocumentMetadata.parse(row.data.document);
}

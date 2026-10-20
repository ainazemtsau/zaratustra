import {
  createEditTool,
  createWriteTool,
} from "@earendil-works/pi-coding-agent";
import {
  canonical,
  digest,
  requireThat,
  FileEffectSchema,
  NativeArguments,
} from "../core/index.ts";
import type { FileEffect } from "../core/index.ts";
import { OutputBoundary } from "../storage/index.ts";

/** Obtain native path resolution through public operations, without filesystem IO. */
export async function nativeTarget(path: string, cwd: string) {
  let target = "";
  await createWriteTool(cwd, {
    operations: {
      mkdir: async () => {},
      writeFile: async (p) => {
        target = p;
      },
    },
  }).execute("resolve-only", { path, content: "" });
  requireThat(
    target,
    "VALIDATION_ERROR",
    "Native tool did not resolve a target.",
  );
  return target;
}
/** Reuse the PUBLIC native edit engine, with in-memory EditOperations. This never edits a file. */
export async function simulateNative(
  boundary: OutputBoundary,
  cwd: string,
  input: { tool: "write" | "edit"; arguments: unknown },
) {
  const args = NativeArguments.parse(input.arguments);
  requireThat(
    Buffer.byteLength(canonical(args)) <= 128000,
    "VALIDATION_ERROR",
    "Native argument byte bound exceeded.",
  );
  requireThat(
    !args.path.split(/[\\/]/).includes(".."),
    "PERMISSION_DENIED",
    "Output traversal is not allowed.",
  );
  const target = await nativeTarget(args.path, cwd),
    before = boundary.inspect(target, cwd);
  let finalText: string | undefined;
  if (input.tool === "write") {
    requireThat(
      "content" in args,
      "VALIDATION_ERROR",
      "Native write needs content.",
    );
    await createWriteTool(cwd, {
      operations: {
        mkdir: async () => {},
        writeFile: async (path, content) => {
          requireThat(
            path === before.target,
            "PERMISSION_DENIED",
            "Native write target mismatch.",
          );
          finalText = content;
        },
      },
    }).execute("preview-write-only", args);
  } else {
    requireThat(
      "edits" in args && before.bytes,
      "VALIDATION_ERROR",
      "Native edit needs existing bytes and edits.",
    );
    // Invalid UTF-8 is excluded: the native decoder would silently replace it.
    requireThat(
      Buffer.from(before.bytes.toString("utf8"), "utf8").equals(before.bytes),
      "VALIDATION_ERROR",
      "Controlled native edit requires round-trippable UTF-8 bytes.",
    );
    const tool = createEditTool(cwd, {
      operations: {
        access: async (path) => {
          requireThat(
            path === before.target,
            "PERMISSION_DENIED",
            "Simulator path mismatch.",
          );
        },
        readFile: async (path) => {
          requireThat(
            path === before.target,
            "PERMISSION_DENIED",
            "Simulator path mismatch.",
          );
          return before.bytes!;
        },
        writeFile: async (path, content) => {
          requireThat(
            path === before.target,
            "PERMISSION_DENIED",
            "Simulator path mismatch.",
          );
          finalText = content;
        },
      },
    });
    await tool.execute("preview-only", args);
  }
  requireThat(
    finalText !== undefined &&
      Buffer.byteLength(finalText) <= 64000 &&
      Buffer.from(finalText).toString("utf8") === finalText,
    "VALIDATION_ERROR",
    "Native output must be bounded exact UTF-8 (including explicit BOM/newlines).",
  );
  return {
    arguments: args,
    target: before.target,
    boundary: before.boundary,
    before_hash: before.hash,
    before_length: before.byte_length,
    final_text: finalText,
    final_hash: digest(finalText),
    final_length: Buffer.byteLength(finalText),
  };
}
export function fileFromPreview(value: unknown): FileEffect {
  return FileEffectSchema.parse(value);
}
export const sameNative = (effect: FileEffect, name: string, args: unknown) =>
  effect.tool === name && canonical(effect.arguments) === canonical(args);

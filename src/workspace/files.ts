import { createHash, randomUUID } from "node:crypto";
import {
  closeSync,
  existsSync,
  fstatSync,
  ftruncateSync,
  fsyncSync,
  lstatSync,
  mkdirSync,
  openSync,
  readFileSync,
  readdirSync,
  renameSync,
  unlinkSync,
  writeSync,
} from "node:fs";
import { dirname, join, relative, resolve } from "node:path";
import { CoreError, safePath } from "../storage/index.ts";
import { WorkspacePathSchema } from "./contracts.ts";

export const workspaceHash = (bytes: Uint8Array | string) =>
  createHash("sha256").update(bytes).digest("hex");

export function workspaceError(code: string, message: string): never {
  throw new CoreError(code, message);
}

export function workspaceUTF8(bytes: Buffer, subject: string) {
  let text: string;
  try {
    text = new TextDecoder("utf-8", { fatal: true, ignoreBOM: true }).decode(
      bytes,
    );
  } catch {
    workspaceError(
      "VALIDATION_ERROR",
      `${subject} must be valid UTF-8 text. Preserve the original bytes and review its encoding explicitly.`,
    );
  }
  if (/[\x00-\x08\x0b\x0c\x0e-\x1f]/.test(text))
    workspaceError(
      "VALIDATION_ERROR",
      `${subject} contains binary control bytes. Preserve the original file for an explicit encoding decision.`,
    );
  return text;
}

export function workspaceIdentity(path: string) {
  const info = lstatSync(path);
  return `${info.dev}:${info.ino}`;
}

export function workspaceTarget(root: string, path: string) {
  WorkspacePathSchema.parse(path);
  const target = safePath(root, resolve(root, path));
  let current = root;
  for (const component of path.split("/")) {
    if (existsSync(current)) {
      const names = readdirSync(current);
      const matching = names.filter(
        (name) => name.toLowerCase() === component.toLowerCase(),
      );
      if (matching.length > 1)
        workspaceError("PERMISSION_DENIED", "Ambiguous Windows path spelling.");
    }
    current = join(current, component);
  }
  return target;
}

export interface WorkspaceObservation {
  bytes: Buffer | null;
  hash: string | null;
  identity: string | null;
}

export function observeWorkspaceFile(
  root: string,
  path: string,
  limit = 1024 * 1024,
): WorkspaceObservation {
  const target = workspaceTarget(root, path);
  const info = lstatSync(target, { throwIfNoEntry: false });
  if (!info) return { bytes: null, hash: null, identity: null };
  if (!info.isFile() || info.nlink !== 1 || info.size > limit)
    workspaceError(
      "PERMISSION_DENIED",
      "Workspace file must be a bounded regular single-link file.",
    );
  const handle = openSync(target, "r");
  try {
    const actual = fstatSync(handle);
    const bytes = readFileSync(handle);
    const after = fstatSync(handle);
    if (
      actual.dev !== info.dev ||
      actual.ino !== info.ino ||
      actual.nlink !== 1 ||
      after.nlink !== 1 ||
      actual.size !== after.size ||
      actual.mtimeMs !== after.mtimeMs ||
      bytes.length !== after.size ||
      bytes.length > limit
    )
      workspaceError(
        "REVISION_CONFLICT",
        "Workspace file changed during read.",
      );
    return {
      bytes,
      hash: workspaceHash(bytes),
      identity: `${actual.dev}:${actual.ino}`,
    };
  } finally {
    closeSync(handle);
  }
}

export function ensureWorkspaceDirectory(root: string, path: string) {
  const target = workspaceTarget(root, path);
  mkdirSync(target, { recursive: true });
  safePath(root, target);
  if (!lstatSync(target).isDirectory())
    workspaceError("PERMISSION_DENIED", "Workspace area must be a directory.");
  return target;
}

/** Callers hold their qualified mutation reservation and guard before bytes. */
export function publishWorkspaceFile(
  root: string,
  path: string,
  bytes: Buffer | null,
) {
  const target = workspaceTarget(root, path);
  if (bytes === null) {
    unlinkSync(target);
    return;
  }
  const parent = relative(root, dirname(target)).replaceAll("\\", "/");
  if (parent) ensureWorkspaceDirectory(root, parent);
  const before = lstatSync(target, { throwIfNoEntry: false });
  if (before && (!before.isFile() || before.nlink !== 1))
    workspaceError(
      "PERMISSION_DENIED",
      "Publication requires an ordinary single-link file.",
    );
  const handle = openSync(target, before ? "r+" : "wx");
  try {
    const actual = fstatSync(handle);
    if (
      actual.nlink !== 1 ||
      (before && (actual.dev !== before.dev || actual.ino !== before.ino))
    )
      workspaceError(
        "REVISION_CONFLICT",
        "Publication file identity changed at admission.",
      );
    let offset = 0;
    while (offset < bytes.length) {
      const written = writeSync(
        handle,
        bytes,
        offset,
        bytes.length - offset,
        offset,
      );
      if (written <= 0)
        workspaceError(
          "STORE_UNAVAILABLE",
          "Publication stopped before all file bytes were written.",
        );
      offset += written;
    }
    ftruncateSync(handle, bytes.length);
    fsyncSync(handle);
  } finally {
    closeSync(handle);
  }
  safePath(root, target);
}

/** Product-owned technical records keep either their old or new complete JSON. */
export function writeWorkspaceJSON(
  root: string,
  path: string,
  value: unknown,
  options: {
    fault?: (point: string, path?: string, temporaryPath?: string) => void;
  } = {},
) {
  if (
    !/^\.local\/workspace\/(?:operations\/[a-f0-9-]{36}\.(?:plan|journal|receipt)|attachments\/[a-f0-9-]{36})\.json$/.test(
      path,
    )
  )
    workspaceError(
      "PERMISSION_DENIED",
      "Atomic technical publication is restricted to owned workspace records.",
    );
  const target = workspaceTarget(root, path);
  const parent = relative(root, dirname(target)).replaceAll("\\", "/");
  ensureWorkspaceDirectory(root, parent);
  const before = observeWorkspaceFile(root, path, 8 * 1024 * 1024);
  const temporary = `${target}.${randomUUID()}.tmp`;
  workspaceTarget(root, relative(root, temporary).replaceAll("\\", "/"));
  const bytes = Buffer.from(JSON.stringify(value, null, 2) + "\n");
  const handle = openSync(temporary, "wx");
  try {
    let offset = 0;
    while (offset < bytes.length) {
      const written = writeSync(
        handle,
        bytes,
        offset,
        bytes.length - offset,
        offset,
      );
      if (written <= 0)
        workspaceError(
          "STORE_UNAVAILABLE",
          "Technical publication stopped before all JSON bytes were staged.",
        );
      offset += written;
    }
    fsyncSync(handle);
  } finally {
    closeSync(handle);
  }
  options.fault?.("before_internal_publish", path, temporary);
  const current = observeWorkspaceFile(root, path, 8 * 1024 * 1024);
  if (current.hash !== before.hash || current.identity !== before.identity)
    workspaceError(
      "REVISION_CONFLICT",
      "Technical record changed before publication.",
    );
  safePath(root, target);
  renameSync(temporary, target);
  options.fault?.("after_internal_publish", path);
}

export function canonicalWorkspaceValue(value: unknown): string {
  if (Array.isArray(value))
    return "[" + value.map(canonicalWorkspaceValue).join(",") + "]";
  if (value !== null && typeof value === "object") {
    const object = value as Record<string, unknown>;
    return (
      "{" +
      Object.keys(object)
        .sort()
        .map(
          (key) =>
            JSON.stringify(key) + ":" + canonicalWorkspaceValue(object[key]),
        )
        .join(",") +
      "}"
    );
  }
  return JSON.stringify(value);
}

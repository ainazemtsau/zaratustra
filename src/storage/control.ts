import type { Coordination } from "./coordination.ts";
import { randomUUID, createHash } from "node:crypto";
import {
  closeSync,
  existsSync,
  fsyncSync,
  lstatSync,
  mkdirSync,
  openSync,
  readFileSync,
  realpathSync,
  renameSync,
  rmSync,
  writeFileSync,
} from "node:fs";
import { dirname, isAbsolute, join, relative, resolve } from "node:path";
import { z } from "zod";
import { requireThat } from "../core/index.ts";
import { noAliases } from "./output.ts";

export const bytesHash = (b: Uint8Array | string) =>
  createHash("sha256").update(b).digest("hex");
export const ControlSchema = z
  .strictObject({
    format: z.union([z.literal(1), z.literal(2)]),
    coordination_id: z.string().min(1).optional(),
    coordination_protocol: z.literal(1).optional(),
    workspace_id: z.string().min(1),
    epoch: z.string().min(1),
    generation: z.string().regex(/^(\.|generations\/[a-f0-9-]+)$/),
    restoration: z.record(z.string(), z.unknown()).nullable(),
  })
  .refine(
    (c) => c.format !== 2 || !!c.coordination_id,
    "Coordinated control requires a stable coordination identity.",
  );
export type Control = z.infer<typeof ControlSchema>;
export function contained(root: string, path: string) {
  const rel = relative(resolve(root), resolve(path));
  return rel === "" || (!rel.startsWith("..") && !isAbsolute(rel));
}
/** Check every existing component, not just the final path. No reparse aliases. */
export function safePath(root: string, path: string, allowRoot = false) {
  root = resolve(root);
  path = resolve(path);
  requireThat(
    isAbsolute(root) && contained(root, path) && (allowRoot || path !== root),
    "PERMISSION_DENIED",
    "Path escapes the designated root.",
  );
  noAliases(root);
  noAliases(path);
  let part = path;
  while (contained(root, part)) {
    if (existsSync(part)) {
      requireThat(
        !lstatSync(part).isSymbolicLink(),
        "PERMISSION_DENIED",
        "Symbolic/reparse paths are unsupported for administration.",
      );
      requireThat(
        contained(realpathSync(root), realpathSync(part)),
        "PERMISSION_DENIED",
        "Resolved path escapes the designated root.",
      );
    }
    if (part === root) break;
    part = dirname(part);
  }
  return path;
}
export function durableNew(path: string, bytes: Uint8Array | string) {
  noAliases(path);
  const fd = openSync(path, "wx");
  try {
    writeFileSync(fd, bytes);
    fsyncSync(fd);
  } finally {
    closeSync(fd);
  }
}
export function atomicJSON(path: string, value: unknown) {
  noAliases(path);
  const temp = path + "." + randomUUID() + ".tmp";
  durableNew(temp, JSON.stringify(value, null, 2));
  renameSync(temp, path);
}
export function readControl(home: string): Control | undefined {
  const p = join(home, "active.json");
  if (!existsSync(p)) return undefined;
  safePath(home, p);
  return ControlSchema.parse(JSON.parse(readFileSync(p, "utf8")));
}
export function activeLocation(home: string) {
  home = resolve(home);
  const c = readControl(home);
  return c?.generation && c.generation !== "."
    ? safePath(home, join(home, c.generation))
    : home;
}
export function writeControl(home: string, control: Control) {
  atomicJSON(join(home, "active.json"), ControlSchema.parse(control));
}
export function newDirectory(root: string, prefix: string) {
  noAliases(resolve(root));
  mkdirSync(root, { recursive: true });
  safePath(root, root, true);
  const path = safePath(root, join(root, prefix + randomUUID()));
  mkdirSync(path);
  return path;
}
/** Only own checked directories, with identity recheck immediately before removal. */
export function removeOwned(root: string, path: string) {
  path = safePath(root, path);
  const before = lstatSync(path, { bigint: true });
  const visit = (p: string) => {
    safePath(root, p);
    requireThat(
      !lstatSync(p).isSymbolicLink(),
      "PERMISSION_DENIED",
      "Cleanup refuses links.",
    );
  };
  visit(path);
  const after = lstatSync(path, { bigint: true });
  requireThat(
    before.dev === after.dev && before.ino === after.ino,
    "REVISION_CONFLICT",
    "Cleanup identity changed.",
  );
  // Callers use single files or explicitly owned staging directories; recursive
  // traversal is deliberately not exposed by this helper.
  requireThat(
    before.isFile(),
    "PERMISSION_DENIED",
    "Cleanup only removes a checked regular file.",
  );
  rmSync(path);
}

/** Recover only a proven-dead administrator at the atomic generation-pointer boundary.
 * Never resumes an external action or releases uncertain resource reservations.
 */
export async function recoverMaintenance(
  home: string,
  coordination: Coordination,
) {
  const deadline = Date.now() + 30000;
  for (;;) {
    try {
      const state = coordination.maintenanceInfo();
      if (state.mode === "normal") return false;
      requireThat(
        state.token,
        "STORE_UNAVAILABLE",
        "Unrecognized maintenance fence; preserve control data.",
      );
      coordination.adoptMaintenance(state.token);
      return await coordination.run(
        "maintenance",
        () => {
          const current = readControl(home);
          requireThat(
            current?.format === 2 &&
              current.coordination_id === coordination.identity,
            "STORE_UNAVAILABLE",
            "Dead maintenance has an unrecognized control identity; preserve the fence.",
          );
          const unchanged = current.epoch === state.expected_epoch;
          const switched =
            state.kind === "restore" &&
            current.restoration?.previous_epoch === state.expected_epoch &&
            current.restoration?.new_epoch === current.epoch &&
            !!current.restoration?.preview_digest;
          requireThat(
            state.kind === "restore" && (unchanged || switched),
            "STORE_UNAVAILABLE",
            "Cannot prove whether interrupted maintenance switched generations; preserve and inspect control data.",
          );
          coordination.endMaintenance(state.token!);
          return true;
        },
        { timeoutMs: Math.max(1, deadline - Date.now()) },
      );
    } catch (error) {
      if (
        (error as { code?: string }).code !== "STORE_BUSY" ||
        Date.now() >= deadline
      )
        throw error;
      await new Promise((resolve) => setTimeout(resolve, 25));
    }
  }
}

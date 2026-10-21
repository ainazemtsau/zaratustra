import {
  closeSync,
  existsSync,
  fstatSync,
  lstatSync,
  openSync,
  readFileSync,
  realpathSync,
} from "node:fs";
import { dirname, isAbsolute, parse, relative, resolve, sep } from "node:path";
import { digest, requireThat } from "../core/index.ts";
import type { FileEffect } from "../core/index.ts";

const identity = (s: NonNullable<ReturnType<typeof lstatSync>>) =>
  `${s.dev}:${s.ino}`;
const inside = (root: string, path: string) => {
  const r = relative(root, path);
  return r !== "" && !r.startsWith("..") && !isAbsolute(r);
};
export function noAliases(path: string) {
  const volume = parse(path).root;
  let current = volume;
  for (const component of path
    .slice(volume.length)
    .split(sep)
    .filter(Boolean)) {
    requireThat(
      !/[\x00-\x1f<>:"|?*]/.test(component) &&
        !/[. ]$/.test(component) &&
        !/^(con|prn|aux|nul|com[1-9]|lpt[1-9])(?:\.|$)/i.test(component),
      "PERMISSION_DENIED",
      "Output names must be ordinary local file names without device/stream/control aliases.",
    );
    current = resolve(current, component);
    if (lstatSync(current, { throwIfNoEntry: false }))
      requireThat(
        !lstatSync(current).isSymbolicLink() &&
          realpathSync(current).toLowerCase() === current.toLowerCase(),
        "PERMISSION_DENIED",
        "Links/junctions are outside the controlled output contract.",
      );
  }
}
/** Qualified local single-writer observation; no OS-wide compare-and-swap. Never writes. */
export class OutputBoundary {
  readonly root: string;
  private rootIdentity: string;
  constructor(root: string) {
    requireThat(
      isAbsolute(root) && !root.startsWith("\\\\"),
      "PERMISSION_DENIED",
      "Trusted output root must be an absolute local directory.",
    );
    this.root = resolve(root);
    noAliases(this.root);
    requireThat(
      lstatSync(this.root).isDirectory(),
      "PERMISSION_DENIED",
      "Designated output root must already exist.",
    );
    this.rootIdentity = identity(lstatSync(this.root));
  }
  contains(path: string, cwd: string) {
    return inside(this.root, resolve(cwd, path));
  }
  inspect(path: string, cwd: string) {
    requireThat(
      !path.split(/[\\/]/).includes(".."),
      "PERMISSION_DENIED",
      "Output traversal is not allowed.",
    );
    const target = resolve(cwd, path);
    requireThat(
      inside(this.root, target),
      "PERMISSION_DENIED",
      "Target escapes the designated output root.",
    );
    noAliases(target);
    requireThat(
      identity(lstatSync(this.root)) === this.rootIdentity &&
        realpathSync(this.root).toLowerCase() === this.root.toLowerCase(),
      "PERMISSION_DENIED",
      "Output root filesystem identity changed.",
    );
    const parent = dirname(target);
    requireThat(
      existsSync(parent) &&
        lstatSync(parent).isDirectory() &&
        (parent === this.root || inside(this.root, realpathSync(parent))),
      "PERMISSION_DENIED",
      "Output parent must exist within the designated root.",
    );
    let bytes: Buffer | null = null,
      fileIdentity: string | null = null;
    if (lstatSync(target, { throwIfNoEntry: false })) {
      const s = lstatSync(target);
      requireThat(
        s.isFile() && s.nlink === 1 && s.size <= 64000,
        "PERMISSION_DENIED",
        "Controlled output must be a bounded regular single-link file.",
      );
      const fd = openSync(target, "r");
      try {
        const actual = fstatSync(fd);
        requireThat(
          identity(actual) === identity(s) && actual.nlink === 1,
          "PERMISSION_DENIED",
          "Output filesystem identity changed during observation.",
        );
        bytes = readFileSync(fd);
        requireThat(
          bytes.length <= 64000,
          "VALIDATION_ERROR",
          "Output byte bound exceeded.",
        );
        fileIdentity = identity(actual);
      } finally {
        closeSync(fd);
      }
    }
    return {
      target,
      bytes,
      hash: bytes ? digest(bytes) : null,
      byte_length: bytes?.length ?? 0,
      boundary: {
        root: this.root,
        root_identity: this.rootIdentity,
        parent,
        parent_identity: identity(lstatSync(parent)),
        file_identity: fileIdentity,
      },
    };
  }
  check(effect: FileEffect, cwd: string) {
    const now = this.inspect(effect.target, cwd);
    requireThat(
      now.target === effect.target &&
        JSON.stringify(now.boundary) === JSON.stringify(effect.boundary) &&
        now.hash === effect.before_hash &&
        now.byte_length === effect.before_length,
      "APPROVAL_STALE",
      "Native target, identity or existing bytes changed after preview.",
    );
    return now;
  }
}

import { existsSync, mkdirSync, readFileSync, unlinkSync } from "node:fs";
import { dirname, resolve } from "node:path";
import {
  DocumentPath,
  digest,
  documentKey,
  requireThat,
} from "../core/index.ts";
import { OutputBoundary, noAliases } from "./output.ts";

/** One trusted root; file identity checks reuse the existing native-output boundary. */
export class DocumentFiles {
  readonly root: string;
  constructor(project: string) {
    this.root = resolve(project, "activities");
  }
  path(relative: string) {
    return resolve(this.root, DocumentPath.parse(relative));
  }
  prepareParent(relative: string) {
    const path = this.path(relative);
    noAliases(path);
    mkdirSync(dirname(path), { recursive: true });
    noAliases(path);
    return path;
  }
  boundary() {
    return new OutputBoundary(this.root);
  }
  inspect(relative: string) {
    const path = this.path(relative);
    noAliases(path);
    if (!existsSync(this.root) || !existsSync(dirname(path)))
      return { target: path, bytes: null, hash: null, byte_length: 0 };
    return this.boundary().inspect(path, this.root);
  }
  cleanup(relative: string, key: string, expectedHash: string) {
    const current = this.inspect(relative);
    if (!current.bytes) return { removed: true, already_absent: true };
    requireThat(
      current.hash === expectedHash &&
        documentKey(current.bytes.toString("utf8")) === key,
      "REVISION_CONFLICT",
      "Cleanup target changed; preserve the file and inspect before retrying.",
    );
    // Qualified single-writer local operation. No OS-wide compare-and-swap claim.
    requireThat(
      digest(readFileSync(current.target)) === expectedHash,
      "REVISION_CONFLICT",
      "File changed before cleanup.",
    );
    unlinkSync(current.target);
    return { removed: true, already_absent: false };
  }
}

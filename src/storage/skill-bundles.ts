import {
  closeSync,
  existsSync,
  fstatSync,
  fsyncSync,
  ftruncateSync,
  lstatSync,
  mkdirSync,
  openSync,
  readFileSync,
  readdirSync,
  unlinkSync,
  writeSync,
} from "node:fs";
import { dirname, isAbsolute, join, resolve } from "node:path";
import { DatabaseSync } from "node:sqlite";
import {
  BundleManifestSchema,
  BundleMetadataSchema,
  CoreError,
  canonical,
  requireThat,
  type BundleManifest,
  type BundleMetadata,
} from "../core/index.ts";
import { atomicJSON, bytesHash, durableNew, safePath } from "./control.ts";

export interface SkillBundleSnapshot {
  metadata: BundleMetadata;
  manifest: BundleManifest;
  bytes: Record<string, Uint8Array>;
}

export interface BundleVersionView {
  invocation_id: string;
  path: string;
  manifest: BundleManifest;
}

export interface BundleFileReceipt {
  operation_id: string;
  path: string;
  content_hash: string;
  previous_content_hash: string | null;
  committed: true;
}

export interface BundlePublication {
  format: 1;
  operation_id: string;
  digest: string;
  path: string;
  before: BundleManifest | null;
  after: BundleManifest;
  project_identity: string;
  bundle_identity: string | null;
  status:
    | "planned"
    | "publishing"
    | "published"
    | "committed"
    | "compensated"
    | "unknown";
  receipt?: BundleFileReceipt;
  partial_write?: {
    path: string;
    sha256: string;
    length: number;
    file_identity: string;
    bytes_base64: string;
  };
}

interface BundleFileOptions {
  retain?: (bytes: Uint8Array) => string;
  readRetained?: (hash: string) => Uint8Array;
}

export interface BundlePublicationHooks {
  beforePublish?: (operation: BundlePublication) => void;
  beforeCommit?: (operation: BundlePublication) => void;
  fault?: (point: string) => void;
}

interface ObservedFile {
  path: string;
  bytes: Uint8Array;
  sha256: string;
  length: number;
  file_identity: string;
  identity: string;
}

const identity = (stat: NonNullable<ReturnType<typeof lstatSync>>) =>
  `${stat.dev}:${stat.ino}`;

function relativeFile(path: string) {
  requireThat(
    path.length > 0 &&
      path.length <= 500 &&
      !path.includes("\\") &&
      !path.startsWith("/") &&
      path
        .split("/")
        .every(
          (part) =>
            !!part &&
            part !== "." &&
            part !== ".." &&
            !/[\x00-\x1f<>:"|?*]/.test(part) &&
            !/[. ]$/.test(part) &&
            !/^(con|prn|aux|nul|com[1-9]|lpt[1-9])(?:\.|$)/i.test(part),
        ),
    "PERMISSION_DENIED",
    "Bundle files require ordinary relative paths.",
  );
  return path;
}

function text(bytes: Uint8Array) {
  try {
    return new TextDecoder("utf-8", { fatal: true }).decode(bytes);
  } catch {
    throw new CoreError(
      "VALIDATION_ERROR",
      "Bundle text files must contain valid UTF-8.",
    );
  }
}

/** Build a complete version from exact bytes, without running any bundle file. */
export function skillBundleSnapshot(
  input: Record<string, Uint8Array>,
): SkillBundleSnapshot {
  const paths = Object.keys(input).sort();
  requireThat(
    paths.length > 0 && paths.length <= 128,
    "VALIDATION_ERROR",
    "A bundle supports at most 128 files.",
  );
  requireThat(
    input["bundle.json"] && input["SKILL.md"],
    "VALIDATION_ERROR",
    "A bundle needs bundle.json and SKILL.md.",
  );
  const metadata = BundleMetadataSchema.parse(
    JSON.parse(text(input["bundle.json"])),
  );
  const names = new Map<string, string>();
  const fileNames = new Set(paths.map((path) => path.toLowerCase()));
  let total = 0;
  const bytes: Record<string, Uint8Array> = Object.create(null);
  const files = paths.map((path) => {
    relativeFile(path);
    const segments = path.split("/");
    for (let count = 1; count <= segments.length; count++) {
      const prefix = segments.slice(0, count).join("/");
      const lower = prefix.toLowerCase();
      requireThat(
        !names.has(lower) || names.get(lower) === prefix,
        "PERMISSION_DENIED",
        "Bundle path names collide on Windows.",
      );
      requireThat(
        count === segments.length || !fileNames.has(lower),
        "PERMISSION_DENIED",
        "A bundle path is both a file and a directory.",
      );
      names.set(lower, prefix);
    }
    const value = Uint8Array.from(input[path]);
    requireThat(
      value.byteLength <= 256 * 1024,
      "VALIDATION_ERROR",
      "A bundle file exceeds 256 KiB.",
    );
    total += value.byteLength;
    bytes[path] = value;
    const declaredRoles = metadata.file_roles ?? {};
    let role = Object.hasOwn(declaredRoles, path)
      ? declaredRoles[path]
      : "support";
    if (path === "SKILL.md" || path === "bundle.json") role = "text";
    else if (
      path.startsWith("scripts/") ||
      /\.(?:[cm]?[jt]s|[jt]sx|ps1|py|sh|bat|cmd|exe|dll|wasm)$/i.test(path)
    )
      role = "executable";
    if (role === "text") text(value);
    return { path, length: value.byteLength, sha256: bytesHash(value), role };
  });
  requireThat(
    total <= 1024 * 1024 && input["SKILL.md"].byteLength <= 64000,
    "VALIDATION_ERROR",
    "The bundle or entry instructions exceed their byte bound.",
  );
  for (const path of Object.keys(metadata.file_roles ?? {}))
    requireThat(
      paths.includes(path),
      "VALIDATION_ERROR",
      "A declared file role has no corresponding bundle file.",
    );
  const body = { format: 1 as const, skill_id: metadata.skill_id, files };
  const manifest = BundleManifestSchema.parse({
    ...body,
    content_hash: bytesHash(canonical(body)),
  });
  return { metadata, manifest, bytes };
}

function sameInventory(files: ObservedFile[], manifest: BundleManifest | null) {
  return manifest === null
    ? files.length === 0
    : files.length === manifest.files.length &&
        files.every((file, index) => {
          const expected = manifest.files[index];
          return (
            file.path === expected.path &&
            file.length === expected.length &&
            file.sha256 === expected.sha256
          );
        });
}

export function bundlePublicationDigest(
  operationId: string,
  path: string,
  before: BundleManifest | null,
  after: BundleManifest,
) {
  return bytesHash(
    canonical({ operation_id: operationId, path, before, after }),
  );
}

/** The caller owns Core authority and consumer-scope reservations through commit.
 * Publication is qualified for a local window without external editor writes. */
export class SkillBundleFiles {
  readonly project: string;
  readonly root: string;
  private readonly local: string;
  private readonly projectIdentity: string;

  constructor(
    project: string,
    private readonly options: BundleFileOptions = {},
  ) {
    requireThat(
      isAbsolute(project) && !project.startsWith("\\\\"),
      "PERMISSION_DENIED",
      "A bundle workspace must be an absolute local directory.",
    );
    this.project = resolve(project);
    safePath(this.project, this.project, true);
    requireThat(
      lstatSync(this.project).isDirectory(),
      "PERMISSION_DENIED",
      "The bundle workspace must exist.",
    );
    this.projectIdentity = identity(lstatSync(this.project));
    this.root = join(this.project, "skills/personal");
    this.local = join(this.project, ".local/skill-bundles");
  }

  path(relative: string) {
    requireThat(
      identity(lstatSync(this.project)) === this.projectIdentity,
      "PERMISSION_DENIED",
      "Bundle workspace identity changed.",
    );
    relativeFile(relative);
    const path = safePath(this.project, join(this.project, relative));
    requireThat(
      path.startsWith(this.root + "/") || path.startsWith(this.root + "\\"),
      "PERMISSION_DENIED",
      "Personal bundles must be below skills/personal.",
    );
    return path;
  }

  private observe(root: string): ObservedFile[] {
    safePath(this.project, root);
    if (!existsSync(root)) return [];
    requireThat(
      lstatSync(root).isDirectory(),
      "PERMISSION_DENIED",
      "A bundle root must be a directory.",
    );
    const rootIdentity = identity(lstatSync(root));
    const names = new Map<string, string>();
    const files: ObservedFile[] = [];
    const visit = (directory: string, prefix: string) => {
      for (const name of readdirSync(directory).sort()) {
        const relative = prefix + name;
        relativeFile(relative);
        const lower = relative.toLowerCase();
        requireThat(
          !names.has(lower),
          "PERMISSION_DENIED",
          "Bundle names collide on Windows.",
        );
        names.set(lower, relative);
        const path = safePath(this.project, join(root, relative));
        const before = lstatSync(path, { bigint: true });
        requireThat(
          !before.isSymbolicLink(),
          "PERMISSION_DENIED",
          "Bundle links and reparse points are unsupported.",
        );
        if (before.isDirectory()) {
          visit(path, relative + "/");
          continue;
        }
        requireThat(
          before.isFile() && before.nlink === 1n && before.size <= 256n * 1024n,
          "PERMISSION_DENIED",
          "Bundle files must be bounded single-link regular files.",
        );
        const fd = openSync(path, "r");
        let value: Buffer;
        try {
          const opened = fstatSync(fd, { bigint: true });
          requireThat(
            opened.dev === before.dev &&
              opened.ino === before.ino &&
              opened.nlink === 1n,
            "REVISION_CONFLICT",
            "Bundle file identity changed while opening.",
          );
          value = readFileSync(fd);
          const after = fstatSync(fd, { bigint: true });
          requireThat(
            after.size === before.size &&
              after.mtimeNs === before.mtimeNs &&
              after.ctimeNs === before.ctimeNs &&
              BigInt(value.length) === before.size,
            "REVISION_CONFLICT",
            "Bundle file changed during capture.",
          );
        } finally {
          closeSync(fd);
        }
        files.push({
          path: relative,
          bytes: value,
          sha256: bytesHash(value),
          length: value.length,
          file_identity: `${before.dev}:${before.ino}`,
          identity: `${before.dev}:${before.ino}:${before.size}:${before.mtimeNs}:${before.ctimeNs}`,
        });
        requireThat(
          files.length <= 128,
          "VALIDATION_ERROR",
          "A bundle supports at most 128 files.",
        );
      }
    };
    visit(root, "");
    requireThat(
      identity(lstatSync(root)) === rootIdentity,
      "REVISION_CONFLICT",
      "Bundle root changed during capture.",
    );
    return files.sort((a, b) => (a.path < b.path ? -1 : 1));
  }

  snapshot(relative: string): SkillBundleSnapshot {
    const root = this.path(relative);
    const first = this.observe(root);
    const bytes: Record<string, Uint8Array> = Object.create(null);
    for (const file of first) bytes[file.path] = file.bytes;
    const snapshot = skillBundleSnapshot(bytes);
    const second = this.observe(root);
    requireThat(
      first.length === second.length &&
        first.every(
          (file, index) =>
            file.path === second[index].path &&
            file.identity === second[index].identity &&
            file.sha256 === second[index].sha256,
        ),
      "REVISION_CONFLICT",
      "The complete bundle changed during capture.",
    );
    return snapshot;
  }

  withChanges(
    snapshot: SkillBundleSnapshot,
    changes: Record<string, Uint8Array | null>,
  ) {
    const bytes: Record<string, Uint8Array> = Object.assign(
      Object.create(null),
      snapshot.bytes,
    );
    for (const [path, value] of Object.entries(changes)) {
      relativeFile(path);
      if (value === null) delete bytes[path];
      else bytes[path] = value;
    }
    const changed = skillBundleSnapshot(bytes);
    requireThat(
      changed.metadata.skill_id === snapshot.metadata.skill_id,
      "VALIDATION_ERROR",
      "A bundle edit cannot change its skill identity.",
    );
    return changed;
  }

  private localPath(relative: string, createParent = false) {
    const path = safePath(this.project, join(this.local, relative));
    if (createParent) {
      mkdirSync(dirname(path), { recursive: true });
      safePath(this.project, path);
    }
    return path;
  }

  private journalPath(operationId: string) {
    requireThat(
      operationId.length > 0 && operationId.length <= 4000,
      "VALIDATION_ERROR",
      "A bundle operation identity is required.",
    );
    return this.localPath(`operations/${bytesHash(operationId)}.json`);
  }

  private journal(operationId: string): BundlePublication {
    const path = this.journalPath(operationId);
    requireThat(
      existsSync(path),
      "REFERENCE_NOT_FOUND",
      "Bundle operation was not found.",
    );
    requireThat(
      lstatSync(path).isFile() && lstatSync(path).nlink === 1,
      "PERMISSION_DENIED",
      "Bundle journal must be a single-link file.",
    );
    const operation = JSON.parse(
      readFileSync(path, "utf8"),
    ) as BundlePublication;
    requireThat(
      operation.format === 1 &&
        operation.operation_id === operationId &&
        operation.project_identity === identity(lstatSync(this.project)),
      "STORE_UNAVAILABLE",
      "Bundle journal identity does not match the workspace.",
    );
    this.path(operation.path);
    BundleManifestSchema.parse(operation.after);
    if (operation.before) BundleManifestSchema.parse(operation.before);
    requireThat(
      operation.digest ===
        bundlePublicationDigest(
          operationId,
          operation.path,
          operation.before,
          operation.after,
        ),
      "STORE_UNAVAILABLE",
      "Bundle operation digest does not match its exact effect.",
    );
    return operation;
  }

  private save(operation: BundlePublication) {
    this.localPath("operations/.directory", true);
    atomicJSON(this.journalPath(operation.operation_id), operation);
  }

  private retain(snapshot: SkillBundleSnapshot) {
    for (const file of snapshot.manifest.files) {
      const bytes = snapshot.bytes[file.path];
      requireThat(
        bytes &&
          bytes.byteLength === file.length &&
          bytesHash(bytes) === file.sha256,
        "VALIDATION_ERROR",
        "Snapshot material does not match its manifest.",
      );
      if (this.options.retain) {
        requireThat(
          this.options.retain(bytes) === file.sha256,
          "STORE_UNAVAILABLE",
          "Retained bundle material has an unexpected hash.",
        );
      } else {
        const path = this.localPath(`materials/${file.sha256}`, true);
        if (!existsSync(path)) durableNew(path, bytes);
        requireThat(
          lstatSync(path).nlink === 1 &&
            bytesHash(readFileSync(path)) === file.sha256,
          "STORE_UNAVAILABLE",
          "Retained bundle material is corrupt.",
        );
      }
    }
  }

  retained(manifest: BundleManifest): SkillBundleSnapshot {
    BundleManifestSchema.parse(manifest);
    const bytes: Record<string, Uint8Array> = Object.create(null);
    for (const file of manifest.files) {
      let value: Uint8Array;
      if (this.options.readRetained)
        value = this.options.readRetained(file.sha256);
      else {
        const path = this.localPath(`materials/${file.sha256}`);
        requireThat(
          existsSync(path),
          "CONTENT_NOT_RETAINED",
          "Exact bundle material is unavailable.",
        );
        const stat = lstatSync(path);
        requireThat(
          stat.isFile() && stat.nlink === 1,
          "PERMISSION_DENIED",
          "Retained material must be a single-link regular file.",
        );
        value = readFileSync(path);
      }
      requireThat(
        value.length === file.length && bytesHash(value) === file.sha256,
        "CONTENT_NOT_RETAINED",
        "Exact bundle material is missing or changed.",
      );
      bytes[file.path] = value;
    }
    const snapshot = skillBundleSnapshot(bytes);
    requireThat(
      canonical(snapshot.manifest) === canonical(manifest),
      "CONTENT_NOT_RETAINED",
      "Retained bundle inventory does not match the selected version.",
    );
    return snapshot;
  }

  plan(
    operationId: string,
    relative: string,
    beforeHash: string | null,
    after: SkillBundleSnapshot,
  ) {
    return this.lease(() => {
      const root = this.path(relative);
      const checked = skillBundleSnapshot(after.bytes);
      requireThat(
        canonical(checked.manifest) === canonical(after.manifest),
        "VALIDATION_ERROR",
        "Proposed bundle bytes do not match the manifest.",
      );
      const path = this.journalPath(operationId);
      if (existsSync(path)) {
        const existing = this.journal(operationId);
        requireThat(
          existing.path === relative &&
            (existing.before?.content_hash ?? null) === beforeHash &&
            existing.after.content_hash === after.manifest.content_hash,
          "REVISION_CONFLICT",
          "The bundle operation identity already names a different change.",
        );
        return existing;
      }
      const before = existsSync(root) ? this.snapshot(relative) : null;
      requireThat(
        (before?.manifest.content_hash ?? null) === beforeHash,
        "APPROVAL_STALE",
        "The working bundle changed before publication planning.",
      );
      if (before)
        requireThat(
          before.metadata.skill_id === after.metadata.skill_id,
          "VALIDATION_ERROR",
          "Publication cannot replace the skill identity.",
        );
      if (before) this.retain(before);
      this.retain(after);
      const operation: BundlePublication = {
        format: 1,
        operation_id: operationId,
        digest: bundlePublicationDigest(
          operationId,
          relative,
          before?.manifest ?? null,
          after.manifest,
        ),
        path: relative,
        before: before?.manifest ?? null,
        after: after.manifest,
        project_identity: identity(lstatSync(this.project)),
        bundle_identity: existsSync(root) ? identity(lstatSync(root)) : null,
        status: "planned",
      };
      this.pendingConflict(operation);
      this.save(operation);
      return operation;
    });
  }

  private lease<T>(callback: () => T): T {
    const path = this.localPath("publication.sqlite", true);
    if (existsSync(path))
      requireThat(
        lstatSync(path).isFile() && lstatSync(path).nlink === 1,
        "PERMISSION_DENIED",
        "Bundle publication lease must be a single-link file.",
      );
    const db = new DatabaseSync(path);
    try {
      try {
        db.exec("PRAGMA busy_timeout=0; BEGIN EXCLUSIVE");
      } catch (error) {
        const sqlite = error as { code?: string; errcode?: number };
        if (sqlite.code === "SQLITE_BUSY" || sqlite.errcode === 5)
          throw new CoreError(
            "STORE_BUSY",
            "Another bundle publication owns the local file lease.",
          );
        throw error;
      }
      const result = callback();
      db.exec("COMMIT");
      return result;
    } finally {
      db.close();
    }
  }

  private pendingConflict(operation: BundlePublication) {
    const directory = dirname(this.journalPath(operation.operation_id));
    if (!existsSync(directory)) return;
    for (const file of readdirSync(directory)) {
      if (!/^[a-f0-9]{64}\.json$/.test(file)) continue;
      const path = safePath(this.project, join(directory, file));
      requireThat(
        lstatSync(path).isFile() && lstatSync(path).nlink === 1,
        "PERMISSION_DENIED",
        "A bundle journal must be a single-link regular file.",
      );
      const other = JSON.parse(readFileSync(path, "utf8")) as BundlePublication;
      requireThat(
        other.operation_id === operation.operation_id ||
          other.path !== operation.path ||
          ["planned", "committed", "compensated"].includes(other.status),
        "STORE_BUSY",
        "The bundle has another unsettled publication. Inspect its original operation.",
      );
    }
  }

  private writeExisting(
    target: string,
    value: Uint8Array,
    expected: Pick<ObservedFile, "sha256" | "file_identity">,
    operation: BundlePublication,
    relative: string,
    fault?: (point: string) => void,
  ) {
    safePath(this.project, target);
    const before = lstatSync(target);
    requireThat(
      before.isFile() &&
        before.nlink === 1 &&
        identity(before) === expected.file_identity,
      "PERMISSION_DENIED",
      "Bundle edits require an existing single-link regular file.",
    );
    const fd = openSync(target, "r+");
    let mutated = false;
    try {
      const opened = fstatSync(fd);
      requireThat(
        identity(opened) === identity(before) &&
          opened.nlink === 1 &&
          bytesHash(readFileSync(fd)) === expected.sha256,
        "APPROVAL_STALE",
        "Bundle file identity or bytes changed before the guarded edit.",
      );
      let offset = 0;
      while (offset < value.length) {
        mutated = true;
        const count = writeSync(
          fd,
          value,
          offset,
          Math.min(64 * 1024, value.length - offset),
          offset,
        );
        requireThat(
          count > 0,
          "STORE_UNAVAILABLE",
          "A bundle edit made no write progress.",
        );
        offset += count;
        fault?.(`after_write_chunk:${relative}:${offset}`);
      }
      mutated = true;
      ftruncateSync(fd, value.length);
      fsyncSync(fd);
      requireThat(
        identity(fstatSync(fd)) === identity(before) &&
          identity(lstatSync(target)) === identity(before),
        "REVISION_CONFLICT",
        "The edited bundle target identity changed.",
      );
      requireThat(
        bytesHash(readFileSync(target)) === bytesHash(value),
        "REVISION_CONFLICT",
        "The guarded bundle edit did not produce the exact requested bytes.",
      );
    } catch (error) {
      if (mutated) {
        // Matching observed bytes establish state, never which process wrote them.
        try {
          const observed = fstatSync(fd);
          const actual = lstatSync(target);
          if (
            identity(observed) === identity(before) &&
            identity(actual) === identity(before) &&
            actual.isFile() &&
            actual.nlink === 1 &&
            actual.size <= 256 * 1024
          ) {
            const bytes = readFileSync(target);
            operation.partial_write = {
              path: relative,
              sha256: bytesHash(bytes),
              length: bytes.length,
              file_identity: identity(actual),
              bytes_base64: bytes.toString("base64"),
            };
          }
        } catch {
          // Unobserved partial outcomes retain the ordinary UNKNOWN barrier.
        }
      }
      throw error;
    } finally {
      closeSync(fd);
    }
  }

  publish(
    operationId: string,
    hooks: BundlePublicationHooks = {},
  ): BundleFileReceipt {
    return this.lease(() => {
      const operation = this.journal(operationId);
      if (operation.status === "committed") return operation.receipt!;
      requireThat(
        operation.status === "planned",
        "STORE_BUSY",
        "Inspect and reconcile the original bundle publication before retrying.",
      );
      this.pendingConflict(operation);
      const root = this.path(operation.path);
      requireThat(
        sameInventory(this.observe(root), operation.before) &&
          (operation.bundle_identity === null ||
            identity(lstatSync(root)) === operation.bundle_identity),
        "APPROVAL_STALE",
        "The working bundle changed after preview.",
      );
      const after = this.retained(operation.after);
      hooks.beforePublish?.(operation);
      hooks.fault?.("admitted");
      const admitted = this.observe(root);
      requireThat(
        sameInventory(admitted, operation.before) &&
          (operation.bundle_identity === null ||
            identity(lstatSync(root)) === operation.bundle_identity),
        "APPROVAL_STALE",
        "The working bundle changed before publication admission.",
      );
      operation.status = "publishing";
      this.save(operation);
      try {
        const paths = [
          ...new Set([
            ...(operation.before?.files.map((file) => file.path) ?? []),
            ...operation.after.files.map((file) => file.path),
          ]),
        ].sort();
        for (const relative of paths) {
          const target = safePath(this.project, join(root, relative));
          const previous = operation.before?.files.find(
            (file) => file.path === relative,
          );
          const next = operation.after.files.find(
            (file) => file.path === relative,
          );
          if (previous?.sha256 === next?.sha256) continue;
          hooks.fault?.(`before_write:${relative}`);
          if (existsSync(target))
            requireThat(
              lstatSync(target).isFile() &&
                lstatSync(target).nlink === 1 &&
                bytesHash(readFileSync(target)) === previous?.sha256,
              "APPROVAL_STALE",
              "Bundle target changed before writing.",
            );
          else
            requireThat(
              !previous,
              "APPROVAL_STALE",
              "Bundle target disappeared before writing.",
            );
          if (next) {
            mkdirSync(dirname(target), { recursive: true });
            safePath(this.project, target);
            if (previous)
              this.writeExisting(
                target,
                after.bytes[relative],
                admitted.find((file) => file.path === relative)!,
                operation,
                relative,
                hooks.fault,
              );
            else durableNew(target, after.bytes[relative]);
          } else unlinkSync(target);
          hooks.fault?.(`after_write:${relative}`);
        }
        requireThat(
          sameInventory(this.observe(root), operation.after),
          "REVISION_CONFLICT",
          "Published bundle bytes differ from the planned complete version.",
        );
        operation.status = "published";
        this.save(operation);
        hooks.fault?.("after_files");
        hooks.beforeCommit?.(operation);
        hooks.fault?.("after_registry");
        const receipt: BundleFileReceipt = {
          operation_id: operationId,
          path: operation.path,
          content_hash: operation.after.content_hash,
          previous_content_hash: operation.before?.content_hash ?? null,
          committed: true,
        };
        operation.receipt = receipt;
        operation.status = "committed";
        this.save(operation);
        return receipt;
      } catch (error) {
        operation.status = "unknown";
        this.save(operation);
        throw error;
      }
    });
  }

  inspect(operationId: string) {
    const operation = this.journal(operationId);
    const actual = this.observe(this.path(operation.path));
    return {
      operation,
      matches_before: sameInventory(actual, operation.before),
      matches_after: sameInventory(actual, operation.after),
      actual: actual.map(({ path, length, sha256 }) => ({
        path,
        length,
        sha256,
      })),
    };
  }

  /** Rebuild only the journal from a trusted retained Core effect after restore. */
  restoreOperation(
    operationId: string,
    relative: string,
    before: BundleManifest | null,
    after: BundleManifest,
    expectedDigest = bundlePublicationDigest(
      operationId,
      relative,
      before,
      after,
    ),
  ) {
    return this.lease(() => {
      const root = this.path(relative);
      BundleManifestSchema.parse(after);
      if (before) {
        BundleManifestSchema.parse(before);
        requireThat(
          before.skill_id === after.skill_id,
          "VALIDATION_ERROR",
          "A restored bundle effect cannot change skill identity.",
        );
        this.retained(before);
      }
      this.retained(after);
      const digest = bundlePublicationDigest(
        operationId,
        relative,
        before,
        after,
      );
      requireThat(
        digest === expectedDigest,
        "REVISION_CONFLICT",
        "The retained operation digest differs from the requested recovery effect.",
      );
      if (existsSync(this.journalPath(operationId))) {
        const existing = this.journal(operationId);
        requireThat(
          existing.digest === digest,
          "REVISION_CONFLICT",
          "Another exact effect already owns this bundle operation identity.",
        );
        return existing;
      }
      if (existsSync(root)) this.observe(root);
      const operation: BundlePublication = {
        format: 1,
        operation_id: operationId,
        digest,
        path: relative,
        before,
        after,
        project_identity: this.projectIdentity,
        bundle_identity: existsSync(root) ? identity(lstatSync(root)) : null,
        status: "unknown",
      };
      this.pendingConflict(operation);
      this.save(operation);
      return operation;
    });
  }

  /** Trusted caller first reconciles Core's registration/receipt for this operation. */
  reconcile(operationId: string, outcome: "committed" | "compensated") {
    return this.lease(() => {
      const inspection = this.inspect(operationId);
      requireThat(
        outcome === "committed"
          ? inspection.matches_after
          : inspection.matches_before,
        "REVISION_CONFLICT",
        "Actual bundle bytes do not establish the selected reconciliation outcome.",
      );
      const operation = inspection.operation;
      requireThat(
        !["committed", "compensated"].includes(operation.status) ||
          operation.status === outcome,
        "REVISION_CONFLICT",
        "A settled bundle publication cannot be reclassified by reconciliation.",
      );
      operation.status = outcome;
      if (outcome === "committed")
        operation.receipt = {
          operation_id: operationId,
          path: operation.path,
          content_hash: operation.after.content_hash,
          previous_content_hash: operation.before?.content_hash ?? null,
          committed: true,
        };
      this.save(operation);
      return operation;
    });
  }

  /** A qualified caller supplies Core's exact historical committed receipt.
   * Settlement records that result without asserting the current file bytes. */
  settleFromRegistry(
    operationId: string,
    receipt: Pick<
      BundleFileReceipt,
      "operation_id" | "content_hash" | "committed"
    >,
  ) {
    return this.lease(() => {
      const operation = this.journal(operationId);
      requireThat(
        receipt.committed === true &&
          receipt.operation_id === operationId &&
          receipt.content_hash === operation.after.content_hash,
        "REVISION_CONFLICT",
        "The Core receipt does not confirm this exact bundle publication.",
      );
      requireThat(
        operation.status !== "compensated",
        "REVISION_CONFLICT",
        "A compensated bundle operation cannot be settled as a historical commit.",
      );
      operation.receipt = {
        operation_id: operationId,
        path: operation.path,
        content_hash: operation.after.content_hash,
        previous_content_hash: operation.before?.content_hash ?? null,
        committed: true,
      };
      operation.status = "committed";
      this.save(operation);
      return operation;
    });
  }

  compensate(operationId: string) {
    return this.lease(() => {
      const operation = this.journal(operationId);
      requireThat(
        operation.status !== "committed",
        "PERMISSION_DENIED",
        "A committed version needs a newly authorized rollback publication.",
      );
      this.pendingConflict(operation);
      const root = this.path(operation.path);
      const actual = this.observe(root);
      const partial = operation.partial_write;
      if (partial) {
        const retainedPartial = Buffer.from(partial.bytes_base64, "base64");
        requireThat(
          partial.length <= 256 * 1024 &&
            retainedPartial.length === partial.length &&
            bytesHash(retainedPartial) === partial.sha256,
          "STORE_UNAVAILABLE",
          "The observed partial bundle state is invalid.",
        );
      }
      const paths = [
        ...new Set([
          ...(operation.before?.files.map((file) => file.path) ?? []),
          ...operation.after.files.map((file) => file.path),
        ]),
      ].sort();
      requireThat(
        actual.every((file) => paths.includes(file.path)),
        "REVISION_CONFLICT",
        "Compensation preserves additional owner files.",
      );
      for (const relative of paths) {
        const file = actual.find((item) => item.path === relative);
        const before = operation.before?.files.find(
          (item) => item.path === relative,
        );
        const after = operation.after.files.find(
          (item) => item.path === relative,
        );
        requireThat(
          file
            ? file.sha256 === before?.sha256 ||
                file.sha256 === after?.sha256 ||
                (partial?.path === relative &&
                  partial.sha256 === file.sha256 &&
                  partial.length === file.length &&
                  partial.file_identity === file.file_identity)
            : !before || !after,
          "REVISION_CONFLICT",
          "Compensation preserves later owner edits or deletions.",
        );
      }
      const before = operation.before ? this.retained(operation.before) : null;
      try {
        for (const relative of paths) {
          const target = safePath(this.project, join(root, relative));
          const value = before?.bytes[relative];
          if (value) {
            if (
              existsSync(target) &&
              bytesHash(readFileSync(target)) === bytesHash(value)
            )
              continue;
            mkdirSync(dirname(target), { recursive: true });
            safePath(this.project, target);
            const observed = actual.find((file) => file.path === relative);
            if (observed)
              this.writeExisting(target, value, observed, operation, relative);
            else durableNew(target, value);
          } else if (existsSync(target)) {
            const observed = actual.find((file) => file.path === relative);
            const current = lstatSync(target);
            requireThat(
              observed &&
                current.isFile() &&
                current.nlink === 1 &&
                identity(current) === observed.file_identity &&
                bytesHash(readFileSync(target)) === observed.sha256,
              "REVISION_CONFLICT",
              "Compensation preserves a changed target before removal.",
            );
            unlinkSync(target);
          }
        }
        requireThat(
          sameInventory(this.observe(root), operation.before),
          "REVISION_CONFLICT",
          "Compensation did not restore the complete prior bundle.",
        );
        operation.status = "compensated";
        this.save(operation);
        return operation;
      } catch (error) {
        operation.status = "unknown";
        this.save(operation);
        throw error;
      }
    });
  }

  materialize(
    invocationId: string,
    manifest: BundleManifest,
  ): BundleVersionView {
    requireThat(
      invocationId.length > 0 && invocationId.length <= 4000,
      "VALIDATION_ERROR",
      "An invocation identity is required.",
    );
    const snapshot = this.retained(manifest);
    const path = this.localPath(
      `views/${bytesHash(invocationId)}/${manifest.content_hash}/.ready`,
      true,
    );
    const root = dirname(path);
    for (const file of manifest.files) {
      const target = safePath(this.project, join(root, file.path));
      mkdirSync(dirname(target), { recursive: true });
      safePath(this.project, target);
      if (!existsSync(target)) durableNew(target, snapshot.bytes[file.path]);
      requireThat(
        lstatSync(target).isFile() &&
          lstatSync(target).nlink === 1 &&
          bytesHash(readFileSync(target)) === file.sha256,
        "REVISION_CONFLICT",
        "Selected-version materialization changed or is incomplete.",
      );
    }
    const view: BundleVersionView = {
      invocation_id: invocationId,
      path: root,
      manifest,
    };
    this.verifyView(view);
    return view;
  }

  verifyView(view: BundleVersionView) {
    BundleManifestSchema.parse(view.manifest);
    const expected = dirname(
      this.localPath(
        `views/${bytesHash(view.invocation_id)}/${view.manifest.content_hash}/.ready`,
      ),
    );
    requireThat(
      view.path === expected,
      "PERMISSION_DENIED",
      "Selected-version view belongs to another invocation or workspace.",
    );
    requireThat(
      sameInventory(this.observe(view.path), view.manifest),
      "REVISION_CONFLICT",
      "Selected-version files differ from the retained exact bundle.",
    );
    return view.manifest;
  }
}

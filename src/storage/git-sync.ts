import { spawn, spawnSync } from "node:child_process";
import { createHash, randomUUID } from "node:crypto";
import {
  closeSync,
  existsSync,
  fsyncSync,
  lstatSync,
  mkdirSync,
  openSync,
  readFileSync,
  readdirSync,
  realpathSync,
  renameSync,
  unlinkSync,
  watch,
  writeFileSync,
  type FSWatcher,
} from "node:fs";
import { dirname, isAbsolute, join, relative, resolve, sep } from "node:path";
import { DatabaseSync } from "node:sqlite";

export const DEFAULT_SYNC_EXCLUSIONS = [
  ".runtime/",
  "node_modules/",
  ".pi/git/",
  ".local/memory/zara.sqlite",
  ".local/memory/zara.sqlite-wal",
  ".local/memory/zara.sqlite-shm",
  ".local/memory/zara.sqlite-journal",
  ".local/memory/projection.sqlite",
  ".local/memory/projection.sqlite-wal",
  ".local/memory/projection.sqlite-shm",
  ".local/memory/projection.sqlite-journal",
  ".local/memory/coordination.sqlite",
  ".local/memory/coordination.sqlite-journal",
  ".local/memory/runtimes/",
  ".local/memory/staging/",
  ".local/memory/git-sync/",
  ".local/memory/writer.lock",
  ".local/memory/active.json",
  ".local/memory/workspace.json",
  ".local/memory/projection.instance",
] as const;
export const GIT_BLOB_LIMIT = 100 * 1024 * 1024;
export interface SyncBinding {
  format: 1;
  repoId: number;
  repository: string;
  remote: string;
  remoteUrl: string;
  branch: "main";
}
export interface SyncRevision {
  workspaceId: string;
  epoch: string;
  revision: number | string;
}
export type SyncCode =
  | "LOCAL_SAVED"
  | "LOCAL_COMMITTED"
  | "REMOTE_CONFIRMED"
  | "GIT_BUSY"
  | "STAGING_CONFLICT"
  | "REMOTE_DIVERGED"
  | "PENDING_OFFLINE"
  | "REMOTE_UNVERIFIED"
  | "GIT_OPERATION_PENDING"
  | "MANUAL_CHECKPOINT_REQUIRED"
  | "CANONICAL_ATTRIBUTES_REQUIRED"
  | "BRANCH_MISMATCH"
  | "POLICY_MIGRATION_REQUIRED"
  | "WORKTREE_CHANGED"
  | "OVERSIZED_BLOB"
  | "CHECKPOINT_MISMATCH"
  | "GIT_ERROR"
  | "UNCONFIGURED";
export interface SyncStatus {
  format: 1;
  code: SyncCode;
  pending: boolean;
  updatedAt: string;
  workspace?: SyncRevision;
  commit?: string;
  remoteCommit?: string;
  message?: string;
  retryAt?: string;
  localGateMs?: number;
}
export interface RemoteIdentity {
  repoId: number;
  repository: string;
  private: boolean;
}
export interface SyncOptions {
  projectRoot: string;
  runtimeRoot: string;
  binding: SyncBinding;
  getRevision: () => SyncRevision;
  withSnapshot?: <T>(callback: () => T) => T | Promise<T>;
  verifyRemote?: (binding: SyncBinding) => Promise<RemoteIdentity>;
  notify?: (status: SyncStatus) => void;
  exclusions?: readonly string[];
  debounceMs?: number;
  commandTimeoutMs?: number;
  maxBlobBytes?: number;
  requiredPaths?: () => readonly string[];
  pollIntervalMs?: number;
  retryBaseMs?: number;
  localPhaseTimeoutMs?: number;
  /** Synthetic fault/race injection; no tool argument exposes it. */
  onPhase?: (phase: string) => void | Promise<void>;
}
interface Result {
  code: number;
  stdout: string;
  stderr: string;
}
interface Capture {
  revision: SyncRevision;
  head: string;
  files: Map<string, { hash: string; rawHash: string; mode: string }>;
  requests: Map<string, string>;
  stagePaths: string[];
}
class SyncFailure extends Error {
  constructor(
    readonly code: SyncCode,
    message: string,
  ) {
    super(message);
  }
}
const slash = (s: string) => s.split(sep).join("/");
const hash = (s: string | Buffer) =>
  createHash("sha256").update(s).digest("hex");
const equalRevision = (a: SyncRevision | undefined, b: SyncRevision) =>
  !!a &&
  a.workspaceId === b.workspaceId &&
  a.epoch === b.epoch &&
  a.revision === b.revision;
function atomic(path: string, value: unknown) {
  mkdirSync(dirname(path), { recursive: true });
  const temp = path + "." + randomUUID() + ".tmp";
  const fd = openSync(temp, "wx");
  try {
    writeFileSync(fd, JSON.stringify(value, null, 2));
    fsyncSync(fd);
  } finally {
    closeSync(fd);
  }
  renameSync(temp, path);
}
function readJSON<T>(path: string): T | undefined {
  return existsSync(path)
    ? (JSON.parse(readFileSync(path, "utf8")) as T)
    : undefined;
}
export function validateSyncBinding(value: unknown): SyncBinding {
  const b = value as SyncBinding;
  if (
    !b ||
    b.format !== 1 ||
    !Number.isSafeInteger(b.repoId) ||
    b.repoId <= 0 ||
    !/^[A-Za-z0-9_.-]+\/[A-Za-z0-9_.-]+$/.test(b.repository) ||
    !/^[A-Za-z0-9_.-]+$/.test(b.remote) ||
    b.branch !== "main" ||
    typeof b.remoteUrl !== "string" ||
    !b.remoteUrl ||
    /[\0\r\n]/.test(b.remoteUrl)
  )
    throw new SyncFailure(
      "UNCONFIGURED",
      "An exact trusted private-repository binding is required.",
    );
  return {
    format: 1,
    repoId: b.repoId,
    repository: b.repository,
    remote: b.remote,
    remoteUrl: b.remoteUrl,
    branch: "main",
  };
}
export function syncBindingPath(runtimeRoot: string) {
  return join(runtimeRoot, "git-sync", "binding.json");
}
export function loadSyncBinding(runtimeRoot: string): SyncBinding | undefined {
  const value = readJSON<unknown>(syncBindingPath(runtimeRoot));
  return value === undefined ? undefined : validateSyncBinding(value);
}
/** Trusted setup only. Never expose binding/remote approval as a model tool argument. */
export function saveSyncBinding(runtimeRoot: string, binding: SyncBinding) {
  atomic(syncBindingPath(runtimeRoot), validateSyncBinding(binding));
}
function githubRepository(url: string) {
  const m =
    /^(?:https:\/\/github\.com\/|git@github\.com:|ssh:\/\/git@github\.com\/)([A-Za-z0-9_.-]+\/[A-Za-z0-9_.-]+?)(?:\.git)?\/?$/.exec(
      url,
    );
  return m?.[1].toLowerCase();
}
function busy(error: unknown) {
  const e = error as { errcode?: number; message?: string };
  return (
    (e.errcode !== undefined && [5, 6].includes(e.errcode & 255)) ||
    /database (?:is )?(?:locked|busy)/i.test(e.message ?? "")
  );
}
export class GitSynchronizer {
  readonly projectRoot: string;
  readonly runtimeRoot: string;
  readonly binding: SyncBinding;
  private readonly root: string;
  private readonly leasePath: string;
  private readonly statePath: string;
  private readonly requestPath: string;
  private readonly exclusions: readonly string[];
  private readonly limit: number;
  private readonly timeout: number;
  private readonly controller = new AbortController();
  private timer?: ReturnType<typeof setTimeout>;
  private poll?: ReturnType<typeof setInterval>;
  private watcher?: FSWatcher;
  private running?: Promise<SyncStatus>;
  private closed = false;
  private started = false;
  private lastSignature = "";
  private failures = 0;
  private localDeadline = 0;
  private localGateMs = 0;
  constructor(private readonly options: SyncOptions) {
    this.projectRoot = realpathSync(resolve(options.projectRoot));
    this.runtimeRoot = resolve(options.runtimeRoot);
    this.binding = validateSyncBinding(options.binding);
    this.root = join(this.runtimeRoot, "git-sync");
    this.statePath = join(this.root, "status.json");
    this.requestPath = join(this.root, "requests", randomUUID() + ".json");
    const ownRuntime = slash(relative(this.projectRoot, this.root));
    this.exclusions = [
      ...(options.exclusions ?? DEFAULT_SYNC_EXCLUSIONS),
      ...(!ownRuntime.startsWith("..") && !isAbsolute(ownRuntime)
        ? [ownRuntime + "/"]
        : []),
    ];
    if (
      this.exclusions.some(
        (p) =>
          p === "memory/" ||
          p === "activities/" ||
          p === ".local/" ||
          p === "." ||
          p.startsWith("../") ||
          isAbsolute(p),
      )
    )
      throw new SyncFailure(
        "UNCONFIGURED",
        "Broad data exclusions are not a runtime-only policy.",
      );
    this.limit = Math.min(
      options.maxBlobBytes ?? GIT_BLOB_LIMIT,
      GIT_BLOB_LIMIT,
    );
    this.timeout = options.commandTimeoutMs ?? 15_000;
    const common = resolve(
      this.projectRoot,
      this.git(["rev-parse", "--git-common-dir"]).trim(),
    );
    const leaseRoot = join(common, "zaratustra-sync");
    mkdirSync(leaseRoot, { recursive: true });
    this.leasePath = join(leaseRoot, "lease.sqlite");
    mkdirSync(join(this.root, "requests"), { recursive: true });
  }
  private excluded(path: string) {
    const p = slash(path).replace(/^\.\//, "");
    return (
      p === ".git" ||
      p.startsWith(".git/") ||
      p.split("/").includes("node_modules") ||
      this.exclusions.some((x) =>
        x.endsWith("/") ? p === x.slice(0, -1) || p.startsWith(x) : p === x,
      )
    );
  }
  private assertLocalDeadline() {
    if (this.localDeadline && Date.now() >= this.localDeadline)
      throw new SyncFailure(
        "GIT_BUSY",
        "Local checkpoint exceeded its bounded admission window; no network is held inside it.",
      );
  }
  private sync(args: string[], input?: string): Result {
    this.assertLocalDeadline();
    const r = spawnSync("git", ["-C", this.projectRoot, ...args], {
      encoding: "utf8",
      input,
      windowsHide: true,
      timeout: this.localDeadline
        ? Math.max(1, Math.min(this.timeout, this.localDeadline - Date.now()))
        : this.timeout,
      maxBuffer: 64 * 1024 * 1024,
    });
    if (r.error) throw new SyncFailure("GIT_ERROR", r.error.message);
    return {
      code: r.status ?? -1,
      stdout: r.stdout ?? "",
      stderr: r.stderr ?? "",
    };
  }
  private git(args: string[], input?: string) {
    const r = this.sync(args, input);
    if (r.code !== 0)
      throw new SyncFailure(
        /index\.lock|another git process/i.test(r.stderr)
          ? "GIT_BUSY"
          : "GIT_ERROR",
        "A local Git operation failed; inspect the repository with ordinary Git tools.",
      );
    return r.stdout;
  }
  private async command(command: string, args: string[]): Promise<Result> {
    return await new Promise((resolveResult, reject) => {
      const child = spawn(command, args, {
        cwd: this.projectRoot,
        windowsHide: true,
        stdio: ["ignore", "pipe", "pipe"],
        signal: this.controller.signal,
      });
      let stdout = "",
        stderr = "";
      const timer = setTimeout(() => child.kill(), this.timeout);
      child.stdout.on("data", (d) => {
        stdout += String(d);
      });
      child.stderr.on("data", (d) => {
        stderr += String(d);
      });
      child.on("error", (e) => {
        clearTimeout(timer);
        reject(e);
      });
      child.on("close", (code) => {
        clearTimeout(timer);
        resolveResult({ code: code ?? -1, stdout, stderr });
      });
    });
  }
  private async remoteIdentity() {
    const b = this.binding;
    const actual = this.git(["remote", "get-url", b.remote]).trim();
    if (
      actual !== b.remoteUrl &&
      (!githubRepository(actual) ||
        githubRepository(actual) !== githubRepository(b.remoteUrl))
    )
      throw new SyncFailure(
        "REMOTE_UNVERIFIED",
        "Configured remote URL changed.",
      );
    if (
      !this.options.verifyRemote &&
      (githubRepository(actual) !== b.repository.toLowerCase() ||
        githubRepository(b.remoteUrl) !== b.repository.toLowerCase())
    )
      throw new SyncFailure(
        "REMOTE_UNVERIFIED",
        "Only the approved GitHub repository may receive an automatic push.",
      );
    const pushUrls = this.git([
      "remote",
      "get-url",
      "--push",
      "--all",
      b.remote,
    ])
      .trim()
      .split("\n")
      .filter(Boolean);
    if (
      pushUrls.length !== 1 ||
      (pushUrls[0] !== b.remoteUrl &&
        (!githubRepository(pushUrls[0]) ||
          githubRepository(pushUrls[0]) !== githubRepository(b.remoteUrl)))
    )
      throw new SyncFailure(
        "REMOTE_UNVERIFIED",
        "Push URL differs from the exact approved private destination.",
      );
    const verifiedPushUrl = pushUrls[0];
    let identity: RemoteIdentity;
    if (this.options.verifyRemote)
      identity = await this.options.verifyRemote(b);
    else {
      let result: Result;
      try {
        result = await this.command("gh", [
          "api",
          "--hostname",
          "github.com",
          `repos/${b.repository}`,
          "--jq",
          "{repoId:.id,repository:.full_name,private:.private}",
        ]);
      } catch {
        throw new SyncFailure(
          "REMOTE_UNVERIFIED",
          "Private repository identity could not be verified through authenticated gh.",
        );
      }
      if (result.code !== 0)
        throw new SyncFailure(
          "REMOTE_UNVERIFIED",
          "Private repository identity could not be verified through authenticated gh.",
        );
      try {
        identity = JSON.parse(result.stdout) as RemoteIdentity;
      } catch {
        throw new SyncFailure(
          "REMOTE_UNVERIFIED",
          "Repository identity response was invalid.",
        );
      }
    }
    if (
      !identity.private ||
      identity.repoId !== b.repoId ||
      identity.repository.toLowerCase() !== b.repository.toLowerCase()
    )
      throw new SyncFailure(
        "REMOTE_UNVERIFIED",
        "Repository identity or private visibility differs from the trusted binding.",
      );
    if (
      this.git(["remote", "get-url", "--push", "--all", b.remote]).trim() !==
      verifiedPushUrl
    )
      throw new SyncFailure(
        "REMOTE_UNVERIFIED",
        "Push destination changed during identity verification.",
      );
  }
  /** Local Git hooks, signing and content filters may run arbitrary native I/O. */
  private assertNoLocalPrograms() {
    const defer = (reason: string): never => {
      throw new SyncFailure(
        "MANUAL_CHECKPOINT_REQUIRED",
        reason +
          " Automatic checkpoint is deferred; native Git configuration is preserved for a manual checkpoint.",
      );
    };
    const configured = (key: string) => {
      const result = this.sync(["config", "--get", key]);
      if (result.code !== 0 && result.code !== 1)
        throw new SyncFailure(
          "GIT_ERROR",
          "Git configuration could not be checked safely.",
        );
      return result.code === 0 ? result.stdout.trim() : undefined;
    };
    if (configured("core.hooksPath") !== undefined)
      defer("A custom hooks directory is configured.");
    const hooks = resolve(
      this.projectRoot,
      this.git(["rev-parse", "--git-path", "hooks"]).trim(),
    );
    if (
      existsSync(hooks) &&
      readdirSync(hooks).some(
        (name) =>
          !name.endsWith(".sample") &&
          (lstatSync(join(hooks, name)).isFile() ||
            lstatSync(join(hooks, name)).isSymbolicLink()),
      )
    )
      defer("An active local Git hook is installed.");
    const signing = this.sync([
      "config",
      "--type=bool",
      "--get",
      "commit.gpgsign",
    ]);
    if (signing.code !== 0 && signing.code !== 1)
      defer("Commit signing configuration cannot be interpreted safely.");
    if (signing.code === 0 && signing.stdout.trim() === "true")
      defer("Native GPG or SSH commit signing is enabled.");
    const monitor = configured("core.fsmonitor");
    if (
      monitor !== undefined &&
      !["false", "0", "no", "off"].includes(monitor.toLowerCase())
    )
      defer("A native Git filesystem monitor is enabled.");
    const filters = this.sync([
      "config",
      "--null",
      "--get-regexp",
      "^filter\\..*\\.(clean|process)$",
    ]);
    if (filters.code !== 0 && filters.code !== 1)
      throw new SyncFailure(
        "GIT_ERROR",
        "Content filter configuration could not be checked safely.",
      );
    const drivers = new Set(
      filters.stdout
        .split("\0")
        .filter(Boolean)
        .map((row) =>
          row
            .slice(0, row.indexOf("\n"))
            .replace(/^filter\./i, "")
            .replace(/\.(clean|process)$/i, ""),
        ),
    );
    if (!drivers.size) return;
    const names = this.git([
      "ls-files",
      "-z",
      "--cached",
      "--others",
      "--exclude-standard",
    ])
      .split("\0")
      .filter((path) => path && !this.excluded(path));
    if (!names.length) return;
    const attributes = this.git(
      ["check-attr", "-z", "--stdin", "filter"],
      names.join("\0") + "\0",
    ).split("\0");
    for (let i = 0; i + 2 < attributes.length; i += 3) {
      if (drivers.has(attributes[i + 2]))
        defer("A clean or process content filter applies to checkpoint files.");
    }
  }
  private preflight(expectedHead?: string) {
    this.assertNoLocalPrograms();
    const top = this.git(["rev-parse", "--show-toplevel"]).trim();
    if (realpathSync(top) !== this.projectRoot)
      throw new SyncFailure(
        "BRANCH_MISMATCH",
        "Project root is not the bound Git checkout root.",
      );
    if (this.git(["branch", "--show-current"]).trim() !== this.binding.branch)
      throw new SyncFailure(
        "BRANCH_MISMATCH",
        "Automatic checkpoint requires the approved main branch.",
      );
    for (const name of [
      "MERGE_HEAD",
      "CHERRY_PICK_HEAD",
      "REVERT_HEAD",
      "rebase-merge",
      "rebase-apply",
      "sequencer",
    ]) {
      const p = this.git(["rev-parse", "--git-path", name]).trim();
      if (existsSync(resolve(this.projectRoot, p)))
        throw new SyncFailure(
          "GIT_OPERATION_PENDING",
          "An unfinished manual Git operation is present.",
        );
    }
    const staged = this.sync(["diff", "--cached", "--quiet", "--exit-code"]);
    if (staged.code === 1)
      throw new SyncFailure(
        "STAGING_CONFLICT",
        "Existing staged or partially staged changes are preserved; automatic commit is deferred.",
      );
    if (staged.code !== 0)
      throw new SyncFailure("GIT_BUSY", "Git index could not be checked.");
    const head = this.git(["rev-parse", "HEAD"]).trim();
    if (expectedHead && head !== expectedHead)
      throw new SyncFailure(
        "WORKTREE_CHANGED",
        "HEAD changed while preparing the checkpoint.",
      );
    const tracked = this.git(["ls-files", "-z"]).split("\0").filter(Boolean);
    if (tracked.some((p) => this.excluded(p)))
      throw new SyncFailure(
        "POLICY_MIGRATION_REQUIRED",
        "Runtime files are still tracked; the approved one-time index migration must complete first.",
      );
    return head;
  }
  private visibleStatus() {
    return this.git(["status", "--porcelain=v1", "-z", "--untracked-files=all"])
      .split("\0")
      .filter(Boolean)
      .filter((entry) => !this.excluded(entry.slice(3)))
      .join("\0");
  }
  private remoteHead() {
    return this.command("git", [
      "-C",
      this.projectRoot,
      "ls-remote",
      "--refs",
      this.binding.remoteUrl,
      `refs/heads/${this.binding.branch}`,
    ]);
  }
  private async fetchRemote(): Promise<string | undefined> {
    let result: Result;
    try {
      result = await this.remoteHead();
    } catch {
      throw new SyncFailure(
        "PENDING_OFFLINE",
        "Remote branch could not be read; data remains local.",
      );
    }
    if (result.code !== 0)
      throw new SyncFailure(
        "PENDING_OFFLINE",
        "Remote branch could not be read; data remains local.",
      );
    const oid = result.stdout.trim().split(/\s+/)[0];
    if (!oid) return undefined;
    if (!/^[a-f0-9]{40,64}$/.test(oid))
      throw new SyncFailure(
        "REMOTE_UNVERIFIED",
        "Invalid remote branch identity.",
      );
    const fetch = await this.command("git", [
      "-C",
      this.projectRoot,
      "fetch",
      "--no-tags",
      "--no-write-fetch-head",
      this.binding.remoteUrl,
      `refs/heads/${this.binding.branch}`,
    ]);
    if (fetch.code !== 0)
      throw new SyncFailure(
        "PENDING_OFFLINE",
        "Remote objects could not be read; no history was rewritten.",
      );
    return oid;
  }
  private assertAncestor(ancestor: string, descendant: string) {
    if (
      this.sync(["merge-base", "--is-ancestor", ancestor, descendant]).code !==
      0
    )
      throw new SyncFailure(
        "REMOTE_DIVERGED",
        "Remote main has changes that need explicit reconciliation; automatic rebase is disabled.",
      );
  }
  private checkOutgoing(head: string, remote?: string) {
    const objects = this.git([
      "rev-list",
      "--objects",
      head,
      ...(remote ? ["^" + remote] : []),
    ]).trim();
    if (!objects) return;
    const ids = objects.split("\n").map((line) => line.split(" ")[0]);
    const sizes = this.git(
      ["cat-file", "--batch-check=%(objectname) %(objecttype) %(objectsize)"],
      ids.join("\n") + "\n",
    );
    for (const line of sizes.trim().split("\n")) {
      const [, type, length] = line.split(" ");
      if (type === "blob" && Number(length) > this.limit)
        throw new SyncFailure(
          "OVERSIZED_BLOB",
          "An outgoing commit contains a blob above the ordinary Git limit, including possible unpushed parent history.",
        );
    }
  }
  private requests() {
    return new Map(
      readdirSync(join(this.root, "requests"))
        .filter((x) => x.endsWith(".json"))
        .map((name) => {
          const path = join(this.root, "requests", name);
          return [path, hash(readFileSync(path))];
        }),
    );
  }
  private capture(): Capture {
    const head = this.preflight();
    const names = [
      ...new Set(
        this.git([
          "ls-files",
          "-z",
          "--cached",
          "--others",
          "--exclude-standard",
        ])
          .split("\0")
          .filter(Boolean),
      ),
    ]
      .filter((p) => !this.excluded(p))
      .sort();
    const files = new Map<
      string,
      { hash: string; rawHash: string; mode: string }
    >();
    const modes = new Map(
      this.git(["ls-files", "--stage", "-z"])
        .split("\0")
        .filter(Boolean)
        .map((row) => {
          const split = row.indexOf("\t");
          return [row.slice(split + 1), row.slice(0, split).split(" ")[0]];
        }),
    );
    const fileMode = this.sync(["config", "--bool", "core.filemode"]);
    const honorMode =
      fileMode.code === 0
        ? fileMode.stdout.trim() === "true"
        : process.platform !== "win32";
    const present: string[] = [];
    for (const path of names) {
      this.assertLocalDeadline();
      if (/[\r\n]/.test(path))
        throw new SyncFailure(
          "GIT_ERROR",
          "A working filename requires explicit Git handling.",
        );
      const absolute = resolve(this.projectRoot, path);
      const rel = relative(this.projectRoot, absolute);
      if (rel.startsWith("..") || isAbsolute(rel))
        throw new SyncFailure(
          "GIT_ERROR",
          "Working path escaped the approved project.",
        );
      if (!existsSync(absolute)) continue;
      const stat = lstatSync(absolute);
      if (!stat.isFile() || stat.isSymbolicLink())
        throw new SyncFailure(
          "GIT_ERROR",
          "Embedded repositories and link aliases require explicit handling.",
        );
      if (stat.size > this.limit)
        throw new SyncFailure(
          "OVERSIZED_BLOB",
          "A working file exceeds the ordinary Git blob limit.",
        );
      files.set(path, {
        hash: "",
        rawHash: hash(readFileSync(absolute)),
        mode: honorMode
          ? stat.mode & 0o111
            ? "100755"
            : "100644"
          : (modes.get(path) ?? "100644"),
      });
      present.push(path);
    }
    if (present.length) {
      const values = this.git(
        ["hash-object", "--stdin-paths"],
        present.map((p) => JSON.stringify(p)).join("\n") + "\n",
      )
        .trim()
        .split("\n");
      if (values.length !== present.length)
        throw new SyncFailure(
          "CHECKPOINT_MISMATCH",
          "Git normalized content hashes do not cover the captured file set.",
        );
      present.forEach((p, i) => {
        files.get(p)!.hash = values[i];
      });
    }
    const requiredPaths = (this.options.requiredPaths?.() ?? []).map(
      (required) =>
        slash(
          isAbsolute(required)
            ? relative(this.projectRoot, required)
            : required,
        ),
    );
    for (const path of requiredPaths) {
      if (!files.has(path))
        throw new SyncFailure(
          "CHECKPOINT_MISMATCH",
          "A required canonical file is missing or excluded by Git policy.",
        );
    }
    this.assertCanonicalAttributes(requiredPaths, files);
    this.assertBytes(files);
    return {
      head,
      files,
      revision: this.options.getRevision(),
      requests: this.requests(),
      stagePaths: names,
    };
  }
  /** Canonical hash manifests require clone-stable raw bytes, not text normalization. */
  private assertCanonicalAttributes(paths: string[], files: Capture["files"]) {
    if (!paths.length) return;
    const refuse = (): never => {
      throw new SyncFailure(
        "CANONICAL_ATTRIBUTES_REQUIRED",
        "Canonical corpus needs a committed -text policy with EOL, encoding and filters unset; trusted setup must preserve its exact bytes.",
      );
    };
    // A local-only override cannot establish the behavior of a fresh clone.
    const info = resolve(
      this.projectRoot,
      this.git(["rev-parse", "--git-path", "info/attributes"]).trim(),
    );
    if (
      existsSync(info) &&
      readFileSync(info, "utf8")
        .split(/\r?\n/)
        .some((line) => line.trim() && !line.trim().startsWith("#"))
    )
      refuse();
    if (!files.has(".gitattributes")) refuse();
    const policies = readFileSync(
      join(this.projectRoot, ".gitattributes"),
      "utf8",
    )
      .split(/\r?\n/)
      .map((line) => line.trim().split(/\s+/))
      .filter((parts) => !parts[0].startsWith("#") && parts.includes("-text"));
    for (const path of paths) {
      const portable = policies.some(([pattern]) => {
        if (["*", "**", "/**"].includes(pattern)) return true;
        const prefix = pattern.replace(/^\//, "");
        return prefix.endsWith("/**") && path.startsWith(prefix.slice(0, -2));
      });
      if (!portable) refuse();
    }
    const values = this.git(
      [
        "check-attr",
        "-z",
        "--stdin",
        "text",
        "eol",
        "working-tree-encoding",
        "filter",
      ],
      paths.join("\0") + "\0",
    ).split("\0");
    if (values.length !== paths.length * 12 + 1) refuse();
    for (let i = 0; i + 2 < values.length; i += 3) {
      const attribute = values[i + 1],
        value = values[i + 2];
      if (
        attribute === "text"
          ? value !== "unset"
          : !["unset", "unspecified"].includes(value)
      )
        refuse();
    }
  }
  private assertBytes(files: Capture["files"]) {
    for (const [p, value] of files) {
      this.assertLocalDeadline();
      const absolute = join(this.projectRoot, p);
      if (
        !existsSync(absolute) ||
        hash(readFileSync(absolute)) !== value.rawHash
      )
        throw new SyncFailure(
          "WORKTREE_CHANGED",
          "Working files changed during the checkpoint; recapture is required.",
        );
    }
  }
  private indexFiles() {
    const map = new Map<string, string>();
    for (const row of this.git(["ls-files", "--stage", "-z"])
      .split("\0")
      .filter(Boolean)) {
      const split = row.indexOf("\t"),
        [mode, oid, stage] = row.slice(0, split).split(" "),
        path = row.slice(split + 1);
      if (stage !== "0" || mode === "160000")
        throw new SyncFailure(
          "CHECKPOINT_MISMATCH",
          "Index has an unresolved or embedded repository entry.",
        );
      map.set(path, mode + " " + oid);
    }
    return map;
  }
  private matches(actual: Map<string, string>, expected: Capture["files"]) {
    return (
      actual.size === expected.size &&
      [...expected].every(([p, v]) => actual.get(p) === v.mode + " " + v.hash)
    );
  }
  private committedFiles(commit: string) {
    const map = new Map<string, string>();
    for (const row of this.git(["ls-tree", "-r", "-z", commit])
      .split("\0")
      .filter(Boolean)) {
      const split = row.indexOf("\t"),
        [mode, type, oid] = row.slice(0, split).split(" ");
      if (type !== "blob")
        throw new SyncFailure(
          "CHECKPOINT_MISMATCH",
          "Checkpoint contains an unsupported Git object.",
        );
      map.set(row.slice(split + 1), mode + " " + oid);
    }
    return map;
  }
  private localCommit(capture: Capture) {
    this.preflight(capture.head);
    this.assertBytes(capture.files);
    if (capture.stagePaths.length)
      this.git(
        ["add", "--all", "--pathspec-from-file=-", "--pathspec-file-nul"],
        capture.stagePaths.map((p) => ":(top,literal)" + p).join("\0") + "\0",
      );
    if (!this.matches(this.indexFiles(), capture.files))
      throw new SyncFailure(
        "CHECKPOINT_MISMATCH",
        "Actual staged tree differs from capture; index is preserved for inspection.",
      );
    this.assertBytes(capture.files);
    if (!equalRevision(capture.revision, this.options.getRevision()))
      throw new SyncFailure(
        "WORKTREE_CHANGED",
        "Workspace generation changed during capture.",
      );
    const changes = this.sync(["diff", "--cached", "--quiet", "--exit-code"]);
    const assertHead = () => {
      if (
        this.git(["branch", "--show-current"]).trim() !== this.binding.branch ||
        this.git(["rev-parse", "HEAD"]).trim() !== capture.head
      )
        throw new SyncFailure(
          "WORKTREE_CHANGED",
          "Branch or HEAD changed before local commit; index is preserved.",
        );
    };
    assertHead();
    if (changes.code === 1) {
      this.git(["commit", "-m", "Save Zaratustra workspace"]);
    } else if (changes.code !== 0)
      throw new SyncFailure(
        "GIT_BUSY",
        "Staged checkpoint could not be verified.",
      );
    const commit = this.git(["rev-parse", "HEAD"]).trim();
    if (
      this.git(["branch", "--show-current"]).trim() !== this.binding.branch ||
      (changes.code === 1
        ? this.git(["rev-list", "--parents", "-n", "1", commit])
            .trim()
            .split(" ")
            .slice(1)
            .join(" ") !== capture.head
        : commit !== capture.head)
    )
      throw new SyncFailure(
        "WORKTREE_CHANGED",
        "Actual commit parent or branch differs from captured HEAD; push is blocked.",
      );
    if (!this.matches(this.committedFiles(commit), capture.files))
      throw new SyncFailure(
        "CHECKPOINT_MISMATCH",
        "Actual committed tree differs from capture; automatic push is blocked.",
      );
    return commit;
  }
  private publish(value: Omit<SyncStatus, "format" | "updatedAt">) {
    const status: SyncStatus = {
      format: 1,
      updatedAt: new Date().toISOString(),
      ...value,
      localGateMs: this.localGateMs,
    };
    if (
      ["PENDING_OFFLINE", "GIT_BUSY", "REMOTE_UNVERIFIED"].includes(status.code)
    ) {
      this.failures++;
      status.retryAt = new Date(
        Date.now() +
          Math.min(
            300_000,
            (this.options.retryBaseMs ?? 30_000) *
              2 ** Math.min(this.failures - 1, 4),
          ),
      ).toISOString();
    } else if (status.code === "REMOTE_CONFIRMED") this.failures = 0;
    atomic(this.statePath, status);
    try {
      this.options.notify?.(status);
    } catch {
      /* Presentation cannot change a durable checkpoint outcome. */
    }
    return status;
  }
  status(): SyncStatus {
    let stored: SyncStatus | undefined;
    try {
      stored = readJSON<SyncStatus>(this.statePath);
    } catch {
      return {
        format: 1,
        code: "GIT_ERROR",
        pending: true,
        updatedAt: new Date().toISOString(),
        message:
          "Checkpoint status is invalid; memory remains local and the original status file is preserved.",
      };
    }
    const current = this.options.getRevision();
    const pendingRequests = this.requests().size > 0;
    let workingChanges = false;
    if (stored) {
      try {
        workingChanges =
          !!this.visibleStatus() ||
          this.git(["rev-parse", "HEAD"]).trim() !== stored.commit ||
          this.git(["branch", "--show-current"]).trim() !== this.binding.branch;
      } catch {
        workingChanges = true;
      }
    }
    if (!stored)
      return {
        format: 1,
        code: "LOCAL_SAVED",
        pending: true,
        updatedAt: new Date().toISOString(),
        workspace: current,
      };
    if (
      !equalRevision(stored.workspace, current) ||
      pendingRequests ||
      workingChanges
    )
      return {
        ...stored,
        code: stored.code === "REMOTE_CONFIRMED" ? "LOCAL_SAVED" : stored.code,
        pending: true,
      };
    return stored;
  }
  request(reason = "meaningful_save") {
    if (this.closed) return;
    atomic(this.requestPath, { reason, requestedAt: new Date().toISOString() });
    if (this.timer) clearTimeout(this.timer);
    this.timer = setTimeout(() => {
      this.timer = undefined;
      void this.flush().catch(() => {});
    }, this.options.debounceMs ?? 2000);
    this.timer.unref();
  }
  start() {
    if (this.closed || this.started) return;
    this.started = true;
    this.request("startup");
    try {
      this.watcher = watch(
        this.projectRoot,
        { recursive: true },
        (_event, name) => {
          if (name && !this.excluded(name.toString()))
            this.request("working_file_changed");
        },
      );
      this.watcher.unref();
    } catch {
      /* Polling is the supported fallback. */
    }
    this.poll = setInterval(() => {
      if (this.running) return;
      try {
        const signature =
          this.visibleStatus() +
          this.git(["rev-parse", "HEAD"]).trim() +
          this.git(["branch", "--show-current"]).trim() +
          JSON.stringify(this.options.getRevision());
        const pending = readJSON<SyncStatus>(this.statePath);
        const retryDue =
          !!pending?.pending &&
          !!pending.retryAt &&
          Date.parse(pending.retryAt) <= Date.now();
        if (signature !== this.lastSignature || retryDue) {
          this.lastSignature = signature;
          this.request("working_file_scan");
        }
      } catch {
        /* A later normal event retries without claiming success. */
      }
    }, this.options.pollIntervalMs ?? 30_000);
    this.poll.unref();
  }
  private lease(): DatabaseSync | undefined {
    const db = new DatabaseSync(this.leasePath);
    try {
      db.exec(
        "PRAGMA journal_mode=DELETE; PRAGMA busy_timeout=0; PRAGMA synchronous=FULL; BEGIN IMMEDIATE;",
      );
      db.exec(
        "CREATE TABLE IF NOT EXISTS checkpoint_lease(singleton INTEGER PRIMARY KEY CHECK(singleton=1));",
      );
      return db;
    } catch (e) {
      db.close();
      if (busy(e)) return undefined;
      throw e;
    }
  }
  private async checkpoint(): Promise<SyncStatus> {
    let captured: Capture | undefined, commit: string | undefined;
    let lease: DatabaseSync | undefined;
    try {
      lease = this.lease();
    } catch (error) {
      return this.publish({
        code: "GIT_ERROR",
        pending: true,
        workspace: this.options.getRevision(),
        message:
          error instanceof Error
            ? error.message
            : "Checkpoint lease is unavailable; preserve its files.",
      });
    }
    if (!lease)
      return {
        ...this.status(),
        code: "GIT_BUSY",
        pending: true,
        message: "Another live process owns the repository checkpoint lease.",
      };
    try {
      this.preflight();
      await this.remoteIdentity();
      const remote = await this.fetchRemote();
      const before = this.git(["rev-parse", "HEAD"]).trim();
      if (remote) this.assertAncestor(remote, before);
      this.checkOutgoing(before, remote);
      await this.options.onPhase?.("before_capture");
      this.assertNoLocalPrograms();
      const local = () => {
        const started = Date.now();
        this.localDeadline =
          started + (this.options.localPhaseTimeoutMs ?? 10_000);
        try {
          captured = this.capture();
          commit = this.localCommit(captured);
        } finally {
          this.localGateMs = Date.now() - started;
          this.localDeadline = 0;
        }
      };
      await (this.options.withSnapshot
        ? this.options.withSnapshot(local)
        : local());
      this.publish({
        code: "LOCAL_COMMITTED",
        pending: true,
        workspace: captured!.revision,
        commit,
      });
      this.checkOutgoing(commit!, remote);
      await this.options.onPhase?.("before_push");
      await this.remoteIdentity();
      this.preflight(commit);
      const pushed = await this.command("git", [
        "-C",
        this.projectRoot,
        "push",
        this.binding.remoteUrl,
        `${commit}:refs/heads/${this.binding.branch}`,
      ]);
      if (pushed.code !== 0)
        throw new SyncFailure(
          /non-fast-forward|fetch first|rejected/i.test(pushed.stderr)
            ? "REMOTE_DIVERGED"
            : "PENDING_OFFLINE",
          "Remote confirmation is pending; the local checkpoint is preserved.",
        );
      await this.options.onPhase?.("after_push");
      await this.remoteIdentity();
      const confirmed = await this.fetchRemote();
      if (!confirmed)
        throw new SyncFailure(
          "REMOTE_UNVERIFIED",
          "Remote branch is missing after push.",
        );
      this.assertAncestor(commit!, confirmed);
      if (!this.matches(this.committedFiles(confirmed), captured!.files))
        throw new SyncFailure(
          "CHECKPOINT_MISMATCH",
          "Current remote descendant no longer contains the captured checkpoint tree.",
        );
      const now = this.options.getRevision();
      const sameEpoch =
        now.workspaceId === captured!.revision.workspaceId &&
        now.epoch === captured!.revision.epoch;
      if (!sameEpoch)
        return {
          ...this.status(),
          code: "LOCAL_SAVED",
          pending: true,
          message:
            "An old-epoch callback cannot confirm the current workspace.",
        };
      for (const [path, digest] of captured!.requests)
        if (existsSync(path) && hash(readFileSync(path)) === digest)
          unlinkSync(path);
      const clean = this.visibleStatus().length === 0;
      return this.publish({
        code: "REMOTE_CONFIRMED",
        pending:
          this.git(["rev-parse", "HEAD"]).trim() !== commit ||
          this.git(["branch", "--show-current"]).trim() !==
            this.binding.branch ||
          !clean ||
          !equalRevision(captured!.revision, now) ||
          this.requests().size > 0,
        workspace: captured!.revision,
        commit,
        remoteCommit: confirmed,
      });
    } catch (error) {
      const code = error instanceof SyncFailure ? error.code : "GIT_ERROR";
      return this.publish({
        code,
        pending: true,
        workspace: captured?.revision ?? this.options.getRevision(),
        commit,
        message:
          error instanceof Error
            ? error.message
            : "Automatic Git checkpoint failed.",
      });
    } finally {
      try {
        lease.exec("ROLLBACK");
      } finally {
        lease.close();
      }
    }
  }
  flush(): Promise<SyncStatus> {
    if (this.running) return this.running;
    this.running = (async () => {
      let value = await this.checkpoint();
      if (value.code === "REMOTE_CONFIRMED" && value.pending && !this.closed)
        value = await this.checkpoint();
      return value;
    })().finally(() => {
      this.running = undefined;
    });
    return this.running;
  }
  async close() {
    if (this.closed) return this.status();
    this.closed = true;
    if (this.timer) clearTimeout(this.timer);
    if (this.poll) clearInterval(this.poll);
    this.watcher?.close();
    const timer = setTimeout(() => this.controller.abort(), this.timeout);
    try {
      return await this.flush();
    } finally {
      clearTimeout(timer);
    }
  }
}

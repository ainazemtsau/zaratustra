import test from "node:test";
import { createHash } from "node:crypto";
import { DatabaseSync } from "node:sqlite";
import { FileCorpus } from "../src/storage/index.ts";
import assert from "node:assert/strict";
import { execFileSync } from "node:child_process";
import {
  mkdtempSync,
  mkdirSync,
  writeFileSync,
  readFileSync,
  existsSync,
  renameSync,
  unlinkSync,
  symlinkSync,
  readdirSync,
  rmdirSync,
} from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import {
  GitSynchronizer,
  loadSyncBinding,
  saveSyncBinding,
  type SyncBinding,
  type SyncRevision,
} from "../src/storage/git-sync.ts";
import { createGitAutosave, publicSyncStatus } from "../src/extension/sync.ts";

function git(root: string, args: string[]) {
  return execFileSync("git", ["-C", root, ...args], {
    encoding: "utf8",
    windowsHide: true,
  }).trim();
}
function fixture() {
  const base = mkdtempSync(join(tmpdir(), "zara-git-sync-")),
    work = join(base, "work"),
    remote = join(base, "remote.git");
  mkdirSync(work);
  mkdirSync(remote);
  git(work, ["init", "-b", "main"]);
  git(remote, ["init", "--bare"]);
  git(work, ["config", "user.name", "Synthetic Sync Test"]);
  git(work, ["config", "user.email", "sync@example.invalid"]);
  writeFileSync(join(work, ".gitignore"), "/.local/memory/git-sync/\n");
  writeFileSync(join(work, "document.md"), "Initial document\n");
  git(work, ["add", "--all"]);
  git(work, ["commit", "-m", "Synthetic initial state"]);
  git(work, ["remote", "add", "origin", remote]);
  git(work, ["push", "origin", "main"]);
  const binding: SyncBinding = {
    format: 1,
    repoId: 42,
    repository: "synthetic/project",
    remote: "origin",
    remoteUrl: remote,
    branch: "main",
  };
  let revision: SyncRevision = {
    workspaceId: "synthetic-workspace",
    epoch: "epoch-1",
    revision: 1,
  };
  let gate = false;
  const options = {
    projectRoot: work,
    runtimeRoot: join(work, ".local", "memory"),
    binding,
    getRevision: () => revision,
    withSnapshot: <T>(callback: () => T) => {
      gate = true;
      try {
        return callback();
      } finally {
        gate = false;
      }
    },
    verifyRemote: async () => {
      assert.equal(gate, false);
      return { repoId: 42, repository: "synthetic/project", private: true };
    },
    commandTimeoutMs: 5000,
  };
  return {
    base,
    work,
    remote,
    binding,
    options,
    advance: () => {
      revision = { ...revision, revision: Number(revision.revision) + 1 };
    },
    epoch: () => {
      revision = { ...revision, epoch: "epoch-2" };
    },
    gate: () => gate,
  };
}

test("native checkpoint saves the exact full working set; network is outside snapshot gate", async () => {
  const f = fixture();
  writeFileSync(join(f.work, "document.md"), "Updated α 😀\n");
  writeFileSync(
    join(f.work, "untracked report.md"),
    "Another important document\n",
  );
  f.advance();
  const sync = new GitSynchronizer({
    ...f.options,
    onPhase: (phase) => {
      if (phase === "before_push") assert.equal(f.gate(), false);
    },
  });
  const state = await sync.flush();
  assert.equal(state.code, "REMOTE_CONFIRMED", state.message);
  assert.equal(state.pending, false);
  assert.equal(git(f.remote, ["show", "main:document.md"]), "Updated α 😀");
  assert.equal(
    git(f.remote, ["show", "main:untracked report.md"]),
    "Another important document",
  );
  assert.equal(git(f.work, ["diff", "--cached", "--name-only"]), "");
});

test("manual partial staging is preserved, without creating a commit", async () => {
  const f = fixture();
  writeFileSync(join(f.work, "document.md"), "Staged part\n");
  git(f.work, ["add", "document.md"]);
  writeFileSync(
    join(f.work, "document.md"),
    "Working part must remain separate\n",
  );
  const before = git(f.work, ["rev-parse", "HEAD"]),
    index = git(f.work, ["show", ":document.md"]);
  const state = await new GitSynchronizer(f.options).flush();
  assert.equal(state.code, "STAGING_CONFLICT");
  assert.equal(git(f.work, ["rev-parse", "HEAD"]), before);
  assert.equal(git(f.work, ["show", ":document.md"]), index);
  assert.equal(
    readFileSync(join(f.work, "document.md"), "utf8"),
    "Working part must remain separate\n",
  );
});

test("tracked runtime databases require explicit one-time index migration", async () => {
  const f = fixture();
  mkdirSync(join(f.work, ".local", "memory"), { recursive: true });
  writeFileSync(
    join(f.work, ".local", "memory", "zara.sqlite"),
    "synthetic database",
  );
  git(f.work, ["add", ".local/memory/zara.sqlite"]);
  git(f.work, ["commit", "-m", "Synthetic legacy tracking"]);
  const state = await new GitSynchronizer(f.options).flush();
  assert.equal(state.code, "POLICY_MIGRATION_REQUIRED");
  assert.equal(
    readFileSync(join(f.work, ".local", "memory", "zara.sqlite"), "utf8"),
    "synthetic database",
  );
});

test("unverified privacy stops before local staging or push", async () => {
  const f = fixture();
  writeFileSync(join(f.work, "document.md"), "Private change\n");
  const before = git(f.work, ["rev-parse", "HEAD"]);
  const state = await new GitSynchronizer({
    ...f.options,
    verifyRemote: async () => ({
      repoId: 42,
      repository: "synthetic/project",
      private: false,
    }),
  }).flush();
  assert.equal(state.code, "REMOTE_UNVERIFIED");
  assert.equal(git(f.work, ["rev-parse", "HEAD"]), before);
  assert.equal(git(f.work, ["diff", "--cached", "--name-only"]), "");
});

test("oversized blob in unpushed parent history blocks even when current tree is small", async () => {
  const f = fixture();
  writeFileSync(join(f.work, "large.txt"), "x".repeat(2048));
  git(f.work, ["add", "large.txt"]);
  git(f.work, ["commit", "-m", "Synthetic large parent"]);
  git(f.work, ["rm", "large.txt"]);
  git(f.work, ["commit", "-m", "Synthetic remove from latest tree"]);
  const before = git(f.work, ["rev-parse", "HEAD"]);
  const state = await new GitSynchronizer({
    ...f.options,
    maxBlobBytes: 1024,
  }).flush();
  assert.equal(state.code, "OVERSIZED_BLOB");
  assert.equal(git(f.work, ["rev-parse", "HEAD"]), before);
  assert.notEqual(git(f.remote, ["rev-parse", "refs/heads/main"]), before);
});

test("remote advance is deferred without automatic pull or rebase", async () => {
  const f = fixture(),
    other = join(f.base, "other");
  git(f.base, ["clone", "--branch", "main", f.remote, other]);
  git(other, ["config", "user.name", "Other Synthetic Writer"]);
  git(other, ["config", "user.email", "other@example.invalid"]);
  writeFileSync(join(other, "other.txt"), "Concurrent remote result\n");
  git(other, ["add", "--all"]);
  git(other, ["commit", "-m", "Other remote work"]);
  git(other, ["push", "origin", "main"]);
  writeFileSync(join(f.work, "document.md"), "Local change\n");
  const before = git(f.work, ["rev-parse", "HEAD"]);
  const state = await new GitSynchronizer(f.options).flush();
  assert.equal(state.code, "REMOTE_DIVERGED");
  assert.equal(git(f.work, ["rev-parse", "HEAD"]), before);
});

test("lost push acknowledgement retries the existing commit instead of creating another", async () => {
  const f = fixture();
  writeFileSync(join(f.work, "document.md"), "Saved despite response loss\n");
  f.advance();
  let once = true;
  const sync = new GitSynchronizer({
    ...f.options,
    onPhase: (phase) => {
      if (phase === "after_push" && once) {
        once = false;
        throw new Error("Synthetic reply lost");
      }
    },
  });
  const first = await sync.flush();
  assert.equal(first.pending, true);
  assert.notEqual(first.code, "REMOTE_CONFIRMED");
  const committed = git(f.work, ["rev-parse", "HEAD"]);
  assert.equal(git(f.remote, ["rev-parse", "main"]), committed);
  const next = await sync.flush();
  assert.equal(next.code, "REMOTE_CONFIRMED", next.message);
  assert.equal(next.commit, committed);
});

test("late old-epoch completion never marks the new epoch remotely confirmed", async () => {
  const f = fixture();
  writeFileSync(join(f.work, "document.md"), "Old epoch result\n");
  f.advance();
  const sync = new GitSynchronizer({
    ...f.options,
    onPhase: (phase) => {
      if (phase === "after_push") f.epoch();
    },
  });
  const result = await sync.flush();
  assert.equal(result.code, "LOCAL_SAVED");
  assert.equal(result.pending, true);
  assert.notEqual(sync.status().code, "REMOTE_CONFIRMED");
});

test("a live checkpoint lease is not stolen; ordinary working data can still change during network", async () => {
  const f = fixture();
  writeFileSync(join(f.work, "document.md"), "First result\n");
  f.advance();
  let release: () => void = () => {},
    admitted: () => void = () => {};
  const blocked = new Promise<void>((resolve) => {
      release = resolve;
    }),
    ready = new Promise<void>((resolve) => {
      admitted = resolve;
    });
  const first = new GitSynchronizer({
    ...f.options,
    onPhase: async (phase) => {
      if (phase === "before_push") {
        assert.equal(f.gate(), false);
        admitted();
        await blocked;
      }
    },
  });
  const running = first.flush();
  const reached = await Promise.race([
    ready.then(() => "ready"),
    running.then((result) => result.code),
  ]);
  assert.equal(
    reached,
    "ready",
    "First checkpoint must reach the injected network phase.",
  );
  const second = await new GitSynchronizer({
    ...f.options,
    runtimeRoot: join(f.base, "other-runtime"),
  }).flush();
  assert.equal(second.code, "GIT_BUSY");
  release();
  const final = await running;
  assert.equal(final.code, "REMOTE_CONFIRMED", final.message);
});

test("trusted binding is distinct from tool arguments; unconfigured adapter cannot approve a remote", async () => {
  const f = fixture();
  assert.equal(loadSyncBinding(f.options.runtimeRoot), undefined);
  const adapter = createGitAutosave({ ...f.options });
  assert.equal(adapter.configured, false);
  const state = await adapter.action({ action: "retry" });
  assert.equal(state.code, "UNCONFIGURED");
  saveSyncBinding(f.options.runtimeRoot, f.binding);
  assert.deepEqual(loadSyncBinding(f.options.runtimeRoot), f.binding);
  assert.equal(
    existsSync(join(f.options.runtimeRoot, "git-sync", "binding.json")),
    true,
  );
  await assert.rejects(
    adapter.action({ action: "retry", remoteUrl: "https://example.invalid" }),
  );
});

test("a separate pushurl cannot bypass private remote identity", async () => {
  const f = fixture(),
    other = join(f.base, "unapproved.git");
  mkdirSync(other);
  git(other, ["init", "--bare"]);
  git(f.work, ["remote", "set-url", "--push", "origin", other]);
  writeFileSync(join(f.work, "document.md"), "Must remain local\n");
  const before = git(f.work, ["rev-parse", "HEAD"]);
  const result = await new GitSynchronizer(f.options).flush();
  assert.equal(result.code, "REMOTE_UNVERIFIED");
  assert.equal(git(f.work, ["rev-parse", "HEAD"]), before);
});

test("branch changes during a checkpoint block automatic publication", async () => {
  const f = fixture();
  writeFileSync(join(f.work, "document.md"), "A snapshot\n");
  f.advance();
  const original = git(f.remote, ["rev-parse", "main"]);
  const sync = new GitSynchronizer({
    ...f.options,
    onPhase: (phase) => {
      if (phase === "before_push") git(f.work, ["switch", "-c", "manual-work"]);
    },
  });
  const result = await sync.flush();
  assert.equal(result.code, "BRANCH_MISMATCH");
  assert.equal(git(f.remote, ["rev-parse", "main"]), original);
});

test("status detects ordinary file changes without a semantic revision increment", async () => {
  const f = fixture(),
    sync = new GitSynchronizer(f.options);
  assert.equal((await sync.flush()).code, "REMOTE_CONFIRMED");
  writeFileSync(join(f.work, "document.md"), "External working edit\n");
  assert.equal(sync.status().pending, true);
  assert.equal(sync.status().code, "LOCAL_SAVED");
});

test("ignored canonical inventory cannot be called a complete checkpoint", async () => {
  const f = fixture();
  mkdirSync(join(f.work, "memory"));
  writeFileSync(join(f.work, "memory", "corpus.json"), "{}\n");
  writeFileSync(
    join(f.work, ".gitignore"),
    "/.local/memory/git-sync/\n/memory/\n",
  );
  const before = git(f.work, ["rev-parse", "HEAD"]);
  const result = await new GitSynchronizer({
    ...f.options,
    requiredPaths: () => ["memory/corpus.json"],
  }).flush();
  assert.equal(result.code, "CHECKPOINT_MISMATCH");
  assert.equal(git(f.work, ["rev-parse", "HEAD"]), before);
});

test("remote descendant altering captured content is not confirmed", async () => {
  const f = fixture();
  writeFileSync(join(f.work, "document.md"), "Captured result\n");
  f.advance();
  const sync = new GitSynchronizer({
    ...f.options,
    onPhase: (phase) => {
      if (phase !== "after_push") return;
      const other = join(f.base, "descendant");
      git(f.base, ["clone", "--branch", "main", f.remote, other]);
      git(other, ["config", "user.name", "Other Synthetic Writer"]);
      git(other, ["config", "user.email", "other@example.invalid"]);
      writeFileSync(
        join(other, "document.md"),
        "A conflicting remote descendant\n",
      );
      git(other, ["add", "--all"]);
      git(other, ["commit", "-m", "Synthetic remote change"]);
      git(other, ["push", "origin", "main"]);
    },
  });
  const result = await sync.flush();
  assert.equal(result.code, "CHECKPOINT_MISMATCH");
  assert.equal(result.pending, true);
  assert.notEqual(sync.status().code, "REMOTE_CONFIRMED");
});

test("corrupt checkpoint lease is reported and never reset", async () => {
  const f = fixture(),
    leaseDir = join(f.work, ".git", "zaratustra-sync");
  mkdirSync(leaseDir, { recursive: true });
  const file = join(leaseDir, "lease.sqlite");
  writeFileSync(file, "Synthetic corrupt lease bytes");
  const result = await new GitSynchronizer(f.options).flush();
  assert.equal(result.code, "GIT_ERROR");
  assert.equal(readFileSync(file, "utf8"), "Synthetic corrupt lease bytes");
});

test("a bounded metadata snapshot cannot exceed its admission window", async () => {
  const f = fixture();
  writeFileSync(join(f.work, "document.md"), "A local result\n");
  const result = await new GitSynchronizer({
    ...f.options,
    localPhaseTimeoutMs: 1,
    getRevision: () => {
      Atomics.wait(new Int32Array(new SharedArrayBuffer(4)), 0, 0, 5);
      return f.options.getRevision();
    },
  }).flush();
  assert.notEqual(result.code, "REMOTE_CONFIRMED");
  assert.equal(result.pending, true);
  assert.ok(typeof result.localGateMs === "number");
});

test("public sync status does not expose the global private revision", () => {
  const result = publicSyncStatus({
    format: 1,
    code: "REMOTE_CONFIRMED",
    pending: false,
    updatedAt: "2026-10-29T00:00:00.000Z",
    workspace: { workspaceId: "workspace", epoch: "epoch", revision: 999 },
  });
  assert.deepEqual(result.workspace, {
    workspaceId: "workspace",
    epoch: "epoch",
  });
  assert.equal(JSON.stringify(result).includes("999"), false);
});

test("invalid local Git configuration leaves memory-facing adapter available", async () => {
  const f = fixture(),
    dir = join(f.options.runtimeRoot, "git-sync");
  mkdirSync(dir, { recursive: true });
  writeFileSync(join(dir, "binding.json"), "{invalid-json");
  const adapter = createGitAutosave(f.options);
  assert.equal(adapter.configured, false);
  assert.equal(
    (await adapter.action({ action: "status" })).code,
    "UNCONFIGURED",
  );
  assert.equal(
    readFileSync(join(dir, "binding.json"), "utf8"),
    "{invalid-json",
  );
});

test("pending offline checkpoint retries after network restoration without another semantic save", async () => {
  const f = fixture(),
    offline = f.remote + ".offline";
  writeFileSync(join(f.work, "document.md"), "Pending local data\n");
  f.advance();
  renameSync(f.remote, offline);
  let restored = false,
    resolveConfirmed: () => void = () => {};
  const confirmed = new Promise<void>((resolve) => {
    resolveConfirmed = resolve;
  });
  const sync = new GitSynchronizer({
    ...f.options,
    pollIntervalMs: 100,
    retryBaseMs: 10,
    debounceMs: 5,
    notify: (status) => {
      if (status.code === "PENDING_OFFLINE" && !restored) {
        renameSync(offline, f.remote);
        restored = true;
      }
      if (status.code === "REMOTE_CONFIRMED" && !status.pending)
        resolveConfirmed();
    },
  });
  sync.start();
  let timeout: ReturnType<typeof setTimeout> | undefined;
  try {
    await Promise.race([
      confirmed,
      new Promise<never>((_resolve, reject) => {
        timeout = setTimeout(
          () => reject(new Error("Offline retry did not finish")),
          30000,
        );
      }),
    ]);
    assert.equal(restored, true);
    assert.equal(
      git(f.remote, ["show", "main:document.md"]),
      "Pending local data",
    );
  } finally {
    if (timeout) clearTimeout(timeout);
    await sync.close();
    if (existsSync(offline)) renameSync(offline, f.remote);
  }
});

test("a clean branch switch at the same HEAD invalidates confirmed status", async () => {
  const f = fixture(),
    sync = new GitSynchronizer(f.options);
  assert.equal((await sync.flush()).code, "REMOTE_CONFIRMED");
  git(f.work, ["checkout", "-b", "manual-branch"]);
  assert.equal(sync.status().pending, true);
  assert.equal(sync.status().code, "LOCAL_SAVED");
});

test("fetch configuration mutation during verification cannot redirect bound confirmation", async () => {
  const f = fixture();
  git(f.work, ["remote", "set-url", "--push", "origin", f.remote]);
  const other = join(f.base, "unapproved.git");
  mkdirSync(other);
  git(other, ["init", "--bare"]);
  writeFileSync(join(f.work, "document.md"), "Frozen destination data\n");
  let calls = 0;
  const result = await new GitSynchronizer({
    ...f.options,
    verifyRemote: async () => {
      calls++;
      if (calls === 3) git(f.work, ["remote", "set-url", "origin", other]);
      return { repoId: 42, repository: "synthetic/project", private: true };
    },
  }).flush();
  assert.equal(result.code, "REMOTE_CONFIRMED", result.message);
  assert.equal(
    git(f.remote, ["show", "main:document.md"]),
    "Frozen destination data",
  );
  assert.equal(git(other, ["for-each-ref", "--format=%(objectname)"]), "");
});

test("invalid checkpoint status is reported without erasing the original", () => {
  const f = fixture(),
    sync = new GitSynchronizer(f.options);
  const path = join(f.options.runtimeRoot, "git-sync", "status.json");
  writeFileSync(path, "{bad-status");
  assert.equal(sync.status().code, "GIT_ERROR");
  assert.equal(readFileSync(path, "utf8"), "{bad-status");
});

test("a custom memory home never checkpoints its own autosave runtime", async () => {
  const f = fixture();
  writeFileSync(join(f.work, "document.md"), "Custom memory home result\n");
  const sync = new GitSynchronizer({
    ...f.options,
    runtimeRoot: join(f.work, "custom", "memory"),
  });
  const result = await sync.flush();
  assert.equal(result.code, "REMOTE_CONFIRMED", result.message);
  assert.equal(result.pending, false);
  assert.equal(
    git(f.remote, ["ls-tree", "-r", "--name-only", "main"]).includes(
      "git-sync/",
    ),
    false,
  );
  assert.equal(sync.status().pending, false);
});

test("owner hooks signing and content filters defer before the snapshot or native programs", async () => {
  for (const variant of [
    "hook",
    "hooksPath",
    "signing",
    "clean",
    "process",
    "fsmonitor",
  ]) {
    const f = fixture(),
      marker = join(f.work, "native-dispatch.txt");
    const before = git(f.work, ["rev-parse", "HEAD"]);
    const beforeIndex = readFileSync(join(f.work, ".git", "index"));
    const command = "printf 'unexpected-native-dispatch' > native-dispatch.txt";
    if (variant === "hook")
      writeFileSync(
        join(f.work, ".git", "hooks", "pre-commit"),
        "#!/bin/sh\n" + command + "\n",
      );
    else if (variant === "hooksPath") {
      mkdirSync(join(f.work, "owner-hooks"));
      git(f.work, ["config", "core.hooksPath", "owner-hooks"]);
    } else if (variant === "fsmonitor")
      git(f.work, ["config", "core.fsmonitor", command]);
    else if (variant === "signing")
      git(f.work, ["config", "commit.gpgsign", "true"]);
    else {
      git(f.work, ["config", "filter.synthetic." + variant, command]);
      writeFileSync(
        join(f.work, ".gitattributes"),
        "document.md filter=synthetic\n",
      );
    }
    writeFileSync(join(f.work, "document.md"), "Pending owner working data\n");
    let admissions = 0,
      networkChecks = 0;
    const result = await new GitSynchronizer({
      ...f.options,
      withSnapshot: <T>(cb: () => T) => {
        admissions++;
        return cb();
      },
      verifyRemote: async () => {
        networkChecks++;
        return { repoId: 42, repository: "synthetic/project", private: true };
      },
    }).flush();
    assert.equal(
      result.code,
      "MANUAL_CHECKPOINT_REQUIRED",
      variant + ": " + result.message,
    );
    assert.equal(result.pending, true);
    assert.equal(admissions, 0, variant);
    assert.equal(networkChecks, 0, variant);
    assert.equal(existsSync(marker), false, variant);
    assert.equal(git(f.work, ["rev-parse", "HEAD"]), before, variant);
    assert.deepEqual(
      readFileSync(join(f.work, ".git", "index")),
      beforeIndex,
      variant,
    );
    if (variant === "signing")
      assert.equal(git(f.work, ["config", "--get", "commit.gpgsign"]), "true");
    if (variant === "hook")
      assert.equal(
        readFileSync(
          join(f.work, ".git", "hooks", "pre-commit"),
          "utf8",
        ).includes(command),
        true,
      );
  }
});

test("canonical corpus refuses autocrlf normalization then clones and rebuilds exact bytes with portable attributes", async () => {
  const f = fixture();
  git(f.work, ["config", "core.autocrlf", "true"]);
  mkdirSync(f.options.runtimeRoot, { recursive: true });
  const db = new DatabaseSync(":memory:");
  db.exec(
    "CREATE TABLE meta(json TEXT NOT NULL); CREATE TABLE records(id TEXT PRIMARY KEY,kind TEXT,activity_id TEXT,json TEXT); CREATE TABLE revisions(id TEXT,revision INTEGER,json TEXT,PRIMARY KEY(id,revision));",
  );
  db.prepare("INSERT INTO meta VALUES(?)").run(
    JSON.stringify({
      workspace_id: "synthetic-workspace",
      epoch: "epoch-1",
      schema_version: 10,
    }),
  );
  const source = JSON.stringify({
    id: "synthetic-source",
    revision: 1,
    kind: "evidence",
    data: { retained_excerpt: "Portable source α🙂\nSecond line\n" },
  });
  db.prepare("INSERT INTO records VALUES(?,'evidence',NULL,?)").run(
    "synthetic-source",
    source,
  );
  db.prepare("INSERT INTO revisions VALUES(?,?,?)").run(
    "synthetic-source",
    1,
    source,
  );
  const corpus = new FileCorpus(join(f.work, "memory"));
  let cloned: FileCorpus | undefined;
  try {
    corpus.publish(db, f.options.runtimeRoot, true);
    const inventory = corpus.checkpoint();
    const requiredPaths = () =>
      inventory.files.map((file) => "memory/" + file.path);
    const sync = new GitSynchronizer({ ...f.options, requiredPaths });
    const before = git(f.work, ["rev-parse", "HEAD"]);
    const refused = await sync.flush();
    assert.equal(
      refused.code,
      "CANONICAL_ATTRIBUTES_REQUIRED",
      refused.message,
    );
    assert.equal(git(f.work, ["rev-parse", "HEAD"]), before);
    assert.equal(git(f.work, ["diff", "--cached", "--name-only"]), "");
    writeFileSync(
      join(f.work, ".gitattributes"),
      "/memory/** -text -eol -working-tree-encoding -filter\n",
    );
    const saved = await sync.flush();
    assert.equal(saved.code, "REMOTE_CONFIRMED", saved.message);
    assert.equal(saved.pending, false);
    const clone = join(f.base, "portable-clone");
    git(f.base, [
      "-c",
      "core.autocrlf=true",
      "clone",
      "--branch",
      "main",
      f.remote,
      clone,
    ]);
    for (const file of inventory.files)
      assert.deepEqual(
        readFileSync(join(clone, "memory", file.path)),
        readFileSync(join(f.work, "memory", file.path)),
        file.path,
      );
    cloned = new FileCorpus(join(clone, "memory"));
    const restored = new DatabaseSync(":memory:");
    try {
      restored.exec(
        "CREATE TABLE meta(json TEXT); CREATE TABLE records(id TEXT PRIMARY KEY,kind TEXT,activity_id TEXT,json TEXT); CREATE TABLE revisions(id TEXT,revision INTEGER,json TEXT,PRIMARY KEY(id,revision)); CREATE TABLE corpus_projection(singleton INTEGER PRIMARY KEY,revision INTEGER); INSERT INTO corpus_projection VALUES(1,0); CREATE TABLE corpus_dirty(collection TEXT,identity TEXT);",
      );
      cloned.restoreRows(restored);
      assert.equal(
        restored
          .prepare("SELECT json FROM records WHERE id=?")
          .get("synthetic-source")?.json,
        source,
      );
      assert.equal(cloned.checkpoint().files.length, inventory.files.length);
    } finally {
      restored.close();
    }
  } finally {
    cloned?.close();
    corpus.close();
    db.close();
  }
});

test("cached canonical inventory validates raw bytes exact membership and exclusions without a history scan", async () => {
  const f = fixture(),
    root = join(f.work, "memory");
  mkdirSync(root);
  const original = Buffer.from('{\n  "source": "Canonical α🙂"\n}\n');
  const file = join(root, "corpus.json");
  writeFileSync(file, original);
  writeFileSync(
    join(f.work, ".gitattributes"),
    "/memory/** -text -eol -working-tree-encoding -filter\n",
  );
  const snapshot = {
    root,
    files: [
      {
        path: "corpus.json",
        sha256: createHash("sha256").update(original).digest("hex"),
      },
    ],
  };
  let inventoryReads = 0;
  const options = {
    ...f.options,
    canonicalSnapshot: () => {
      inventoryReads++;
      return snapshot;
    },
  };
  const sync = new GitSynchronizer(options);
  const saved = await sync.flush();
  assert.equal(saved.code, "REMOTE_CONFIRMED", saved.message);
  assert.equal(saved.pending, false);
  assert.equal(inventoryReads, 1);
  const before = git(f.work, ["rev-parse", "HEAD"]);
  const assertRejected = async (active: GitSynchronizer) => {
    const result = await active.flush();
    assert.equal(result.code, "CHECKPOINT_MISMATCH", result.message);
    assert.equal(result.pending, true);
    assert.equal(git(f.work, ["rev-parse", "HEAD"]), before);
    assert.equal(git(f.work, ["diff", "--cached", "--name-only"]), "");
    assert.equal(git(f.remote, ["rev-parse", "main"]), before);
  };
  unlinkSync(file);
  await assertRejected(sync);
  writeFileSync(file, "Changed outside the canonical authority\n");
  await assertRejected(sync);
  writeFileSync(file, original);
  const extra = join(root, "extra.json");
  writeFileSync(extra, "{}\n");
  await assertRejected(sync);
  unlinkSync(extra);
  writeFileSync(
    join(f.work, ".gitignore"),
    "/.local/memory/git-sync/\n/memory/ignored.json\n",
  );
  const ignored = join(root, "ignored.json");
  writeFileSync(ignored, "{}\n");
  await assertRejected(sync);
  unlinkSync(ignored);
  const excludedBytes = Buffer.from("New canonical version\n");
  writeFileSync(join(root, "new-version.json"), excludedBytes);
  await assertRejected(
    new GitSynchronizer({
      ...options,
      canonicalSnapshot: () => ({
        ...snapshot,
        files: [
          ...snapshot.files,
          {
            path: "new-version.json",
            sha256: createHash("sha256").update(excludedBytes).digest("hex"),
          },
        ],
      }),
      exclusions: [".local/memory/git-sync/", "memory/new-version.json"],
    }),
  );
  unlinkSync(join(root, "new-version.json"));
  await assertRejected(
    new GitSynchronizer({
      ...options,
      canonicalSnapshot: () => ({ ...snapshot, root: f.base }),
    }),
  );
});

test("cached canonical inventory refuses a nested junction with byte-identical outside content", async () => {
  const f = fixture(),
    root = join(f.work, "memory"),
    outside = join(f.base, "outside-copy");
  mkdirSync(root);
  mkdirSync(outside);
  const bytes = Buffer.from("Byte-identical canonical source\n");
  writeFileSync(join(outside, "corpus.json"), bytes);
  symlinkSync(outside, join(root, "nested"), "junction");
  writeFileSync(
    join(f.work, ".gitattributes"),
    "/memory/** -text -eol -working-tree-encoding -filter\n",
  );
  const before = git(f.work, ["rev-parse", "HEAD"]),
    index = readFileSync(join(f.work, ".git", "index"));
  const result = await new GitSynchronizer({
    ...f.options,
    canonicalSnapshot: () => ({
      root,
      files: [
        {
          path: "nested/corpus.json",
          sha256: createHash("sha256").update(bytes).digest("hex"),
        },
      ],
    }),
  }).flush();
  assert.equal(result.code, "CHECKPOINT_MISMATCH", result.message);
  assert.equal(result.pending, true);
  assert.equal(git(f.work, ["rev-parse", "HEAD"]), before);
  assert.equal(git(f.remote, ["rev-parse", "main"]), before);
  assert.deepEqual(readFileSync(join(f.work, ".git", "index")), index);
});

test("frozen metadata and delta staging use short gates while hashing commit and network stay outside", async () => {
  const f = fixture(),
    root = join(f.work, "memory"),
    file = join(root, "corpus.json");
  mkdirSync(root);
  writeFileSync(file, "Original canonical bytes\n");
  writeFileSync(
    join(f.work, ".gitattributes"),
    "/memory/** -text -eol -working-tree-encoding -filter\n",
  );
  git(f.work, ["add", "--all"]);
  git(f.work, ["commit", "-m", "Seed mature synthetic corpus"]);
  git(f.work, ["push", "origin", "main"]);
  const bytes = Buffer.from("Updated canonical bytes α🙂\n");
  writeFileSync(file, bytes);
  f.advance();
  const original = {
    root,
    files: [
      {
        path: "corpus.json",
        sha256: createHash("sha256").update(bytes).digest("hex"),
      },
    ],
  };
  const required = ["memory/corpus.json"],
    commands: { gate: number; name: string; input?: string }[] = [];
  let gate = 0,
    currentGate = 0,
    inventoryCalls = 0;
  const sync = new GitSynchronizer({
    ...f.options,
    withSnapshot: <T>(callback: () => T) => {
      currentGate = ++gate;
      try {
        return f.options.withSnapshot(callback);
      } finally {
        currentGate = 0;
      }
    },
    canonicalSnapshot: () => {
      assert.equal(currentGate, 1);
      assert.equal(f.gate(), true);
      inventoryCalls++;
      return original;
    },
    requiredPaths: () => {
      assert.equal(currentGate, 1);
      return required;
    },
    getRevision: () => {
      assert.equal(f.gate(), true, "revision reads require a short admission");
      return f.options.getRevision();
    },
    onGitCommand: (args, input) => {
      const name = args[0];
      commands.push({ gate: currentGate, name, input });
      if (currentGate) {
        assert.equal(
          currentGate,
          2,
          "only delta staging may invoke Git in a memory gate",
        );
        assert.ok(
          [
            "config",
            "rev-parse",
            "branch",
            "diff",
            "ls-files",
            "check-attr",
            "add",
          ].includes(name),
          name,
        );
      }
      if (["hash-object", "commit", "push", "fetch"].includes(name))
        assert.equal(currentGate, 0, name);
    },
    onPhase: (phase) => {
      if (phase === "after_snapshot") {
        assert.equal(f.gate(), false);
        original.files[0].sha256 = "0".repeat(64);
        required.push("memory/absent.json");
      }
    },
  });
  const result = await sync.flush();
  assert.equal(result.code, "REMOTE_CONFIRMED", result.message);
  assert.equal(result.pending, false);
  assert.equal(inventoryCalls, 1);
  const staged = commands.filter((entry) => entry.name === "add");
  assert.equal(staged.length, 1);
  assert.equal(staged[0].gate, 2);
  assert.equal(staged[0].input, ":(top,literal)memory/corpus.json\0");
  assert.ok(
    commands.some((entry) => entry.name === "hash-object" && entry.gate === 0),
  );
  assert.ok(
    commands.some((entry) => entry.name === "commit" && entry.gate === 0),
  );
  assert.equal(
    commands.some((entry) => entry.gate === 1),
    false,
  );
  assert.ok((result.localGateMs ?? 10000) < 10000);
  assert.equal(
    git(f.remote, ["show", "main:memory/corpus.json"]),
    bytes.toString("utf8").trim(),
  );
});

test("a revision change after capture defers before staging the frozen older state", async () => {
  const f = fixture();
  writeFileSync(join(f.work, "document.md"), "Captured result\n");
  f.advance();
  const before = git(f.work, ["rev-parse", "HEAD"]);
  const result = await new GitSynchronizer({
    ...f.options,
    onPhase: (phase) => {
      if (phase === "after_capture") f.advance();
    },
  }).flush();
  assert.equal(result.code, "WORKTREE_CHANGED", result.message);
  assert.equal(result.workspace?.revision, 2);
  assert.equal(git(f.work, ["diff", "--cached", "--name-only"]), "");
  assert.equal(git(f.work, ["rev-parse", "HEAD"]), before);
  assert.equal(git(f.remote, ["rev-parse", "main"]), before);
});

test("a coherent staged older tree commits while newer work remains pending for the next pass", async () => {
  const f = fixture();
  writeFileSync(join(f.work, "document.md"), "First coherent result\n");
  f.advance();
  let changed = false,
    pushes = 0;
  const confirmed: {
    revision: number | string | undefined;
    pending: boolean;
  }[] = [];
  const result = await new GitSynchronizer({
    ...f.options,
    notify: (status) => {
      if (status.code === "REMOTE_CONFIRMED")
        confirmed.push({
          revision: status.workspace?.revision,
          pending: status.pending,
        });
    },
    onPhase: (phase) => {
      if (phase === "after_stage" && !changed) {
        assert.equal(f.gate(), false);
        changed = true;
        writeFileSync(join(f.work, "document.md"), "Newer ongoing work\n");
        f.advance();
      }
      if (phase === "after_push" && ++pushes === 1)
        assert.equal(
          git(f.remote, ["show", "main:document.md"]),
          "First coherent result",
        );
    },
  }).flush();
  assert.equal(result.code, "REMOTE_CONFIRMED", result.message);
  assert.equal(result.pending, false);
  assert.deepEqual(confirmed, [
    { revision: 2, pending: true },
    { revision: 3, pending: false },
  ]);
  assert.equal(
    git(f.remote, ["show", "main:document.md"]),
    "Newer ongoing work",
  );
  assert.equal(git(f.work, ["diff", "--cached", "--name-only"]), "");
});

test("an epoch change before push preserves the local checkpoint without confirming the restored workspace", async () => {
  const f = fixture();
  writeFileSync(join(f.work, "document.md"), "Older epoch checkpoint\n");
  f.advance();
  const before = git(f.remote, ["rev-parse", "main"]);
  const result = await new GitSynchronizer({
    ...f.options,
    onPhase: (phase) => {
      if (phase === "before_push") f.epoch();
    },
  }).flush();
  assert.equal(result.code, "WORKTREE_CHANGED", result.message);
  assert.equal(result.pending, true);
  assert.equal(git(f.remote, ["rev-parse", "main"]), before);
  assert.equal(
    git(f.work, ["show", "HEAD:document.md"]),
    "Older epoch checkpoint",
  );
});

test("an uncoordinated file change during delta add preserves ambiguous staging and reports its pending reason", async () => {
  const f = fixture();
  writeFileSync(join(f.work, "document.md"), "Captured working result\n");
  f.advance();
  const before = git(f.work, ["rev-parse", "HEAD"]);
  let changed = false;
  const sync = new GitSynchronizer({
    ...f.options,
    onGitCommand: (args) => {
      if (args[0] === "add" && !changed) {
        assert.equal(f.gate(), true);
        changed = true;
        writeFileSync(
          join(f.work, "document.md"),
          "Uncoordinated external change\n",
        );
      }
    },
  });
  const result = await sync.flush();
  assert.equal(result.code, "CHECKPOINT_MISMATCH", result.message);
  assert.equal(result.pending, true);
  assert.equal(
    git(f.work, ["show", ":document.md"]),
    "Uncoordinated external change",
  );
  assert.equal(git(f.work, ["rev-parse", "HEAD"]), before);
  assert.equal(git(f.remote, ["rev-parse", "main"]), before);
  const retry = await sync.flush();
  assert.equal(retry.code, "STAGING_CONFLICT");
  assert.equal(
    git(f.work, ["show", ":document.md"]),
    "Uncoordinated external change",
  );
});

test("manual staging after the stage gate is preserved and refused before an automatic commit", async () => {
  const f = fixture();
  writeFileSync(join(f.work, "document.md"), "Prepared checkpoint result\n");
  f.advance();
  const before = git(f.work, ["rev-parse", "HEAD"]);
  let manualIndex: Buffer | undefined;
  const result = await new GitSynchronizer({
    ...f.options,
    onPhase: (phase) => {
      if (phase !== "after_stage") return;
      assert.equal(f.gate(), false);
      writeFileSync(
        join(f.work, "owner-manual.txt"),
        "Owner staged material\n",
      );
      git(f.work, ["add", "owner-manual.txt"]);
      manualIndex = readFileSync(join(f.work, ".git", "index"));
    },
  }).flush();
  assert.equal(result.code, "CHECKPOINT_MISMATCH", result.message);
  assert.equal(result.pending, true);
  assert.equal(git(f.work, ["rev-parse", "HEAD"]), before);
  assert.equal(git(f.remote, ["rev-parse", "main"]), before);
  assert.equal(
    git(f.work, ["show", ":owner-manual.txt"]),
    "Owner staged material",
  );
  assert.equal(
    git(f.work, ["show", ":document.md"]),
    "Prepared checkpoint result",
  );
  assert.deepEqual(readFileSync(join(f.work, ".git", "index")), manualIndex);
});

test("successful delta add settles outside an expired gate without stranding its staged checkpoint", async () => {
  const f = fixture();
  writeFileSync(
    join(f.work, "document.md"),
    "Coherent timeout-settled checkpoint\n",
  );
  f.advance();
  const realNow = Date.now;
  let offset = 0,
    addStarted = false,
    expired = false;
  Date.now = () => realNow() + offset;
  try {
    const result = await new GitSynchronizer({
      ...f.options,
      onGitCommand: (args) => {
        if (args[0] === "add") addStarted = true;
        if (
          addStarted &&
          !expired &&
          args[0] === "ls-files" &&
          args.includes("--stage")
        ) {
          assert.equal(f.gate(), true);
          expired = true;
          offset = 20_000;
        }
      },
    }).flush();
    assert.equal(expired, true);
    assert.equal(result.code, "REMOTE_CONFIRMED", result.message);
    assert.equal(result.pending, false);
    assert.equal(git(f.work, ["diff", "--cached", "--name-only"]), "");
    assert.equal(
      git(f.remote, ["show", "main:document.md"]),
      "Coherent timeout-settled checkpoint",
    );
    assert.equal(
      git(f.remote, ["rev-parse", "main"]),
      git(f.work, ["rev-parse", "HEAD"]),
    );
  } finally {
    Date.now = realNow;
  }
});

test("confirmed polling and clean close preserve remote confirmation without another capture commit or push", async () => {
  const f = fixture();
  writeFileSync(join(f.work, "document.md"), "Confirmed before closing\n");
  f.advance();
  const commands: readonly string[][] = [];
  const observed: string[][] = commands as string[][];
  const sync = new GitSynchronizer({
    ...f.options,
    debounceMs: 60000,
    pollIntervalMs: 100,
    onGitCommand: (args) => observed.push([...args]),
  });
  sync.start();
  const confirmed = await sync.flush();
  assert.equal(confirmed.code, "REMOTE_CONFIRMED", confirmed.message);
  assert.equal(confirmed.pending, false);
  observed.length = 0;
  try {
    for (let i = 0; i < 100; i++) {
      if (observed.filter((args) => args[0] === "branch").length >= 2) break;
      await new Promise<void>((resolve) => setTimeout(resolve, 20));
    }
    assert.ok(
      observed.filter((args) => args[0] === "branch").length >= 2,
      "The real poll interval must scan the confirmed checkpoint",
    );
    assert.equal(
      readdirSync(join(f.options.runtimeRoot, "git-sync", "requests")).length,
      0,
      "The synchronizer's own confirmed commit must not enqueue another scan",
    );
    assert.equal(sync.status().pending, false);
  } finally {
    await sync.close();
  }
  const closed = sync.status();
  assert.equal(closed.code, "REMOTE_CONFIRMED");
  assert.equal(closed.pending, false);
  assert.equal(closed.commit, confirmed.commit);
  assert.equal(closed.remoteCommit, confirmed.remoteCommit);
  assert.ok(
    observed.every((args) =>
      ["status", "rev-parse", "branch"].includes(args[0]),
    ),
    JSON.stringify(observed),
  );
  assert.equal(
    git(f.remote, ["show", "main:document.md"]),
    "Confirmed before closing",
  );
});

test("real watcher ignores runtime journals and owned temporary siblings but retains working file changes and deletion", async () => {
  const f = fixture(),
    queue = join(f.options.runtimeRoot, "git-sync", "requests");
  const sync = new GitSynchronizer({
    ...f.options,
    debounceMs: 60000,
    pollIntervalMs: 60000,
  });
  const requests = () =>
    readdirSync(queue).filter((name) => name.endsWith(".json"));
  const pause = (ms: number) =>
    new Promise<void>((resolve) => setTimeout(resolve, ms));
  const wait = async (check: () => boolean) => {
    for (let i = 0; i < 50; i++) {
      if (check()) return;
      await pause(20);
    }
    assert.fail("Expected watcher request was not observed");
  };
  try {
    sync.start();
    const initial = await sync.flush();
    assert.equal(initial.code, "REMOTE_CONFIRMED", initial.message);
    await pause(100);
    assert.equal(requests().length, 0);
    const journal = join(f.options.runtimeRoot, "coordination.sqlite-journal"),
      tmp = join(
        f.options.runtimeRoot,
        "workspace.json.12345678-1234-4234-8234-123456789abc.tmp",
      );
    writeFileSync(journal, "runtime journal");
    writeFileSync(tmp, "atomic runtime control");
    await pause(100);
    unlinkSync(journal);
    unlinkSync(tmp);
    await pause(150);
    assert.equal(
      requests().length,
      0,
      "runtime events must not enqueue another checkpoint",
    );
    assert.equal(sync.status().pending, false);
    const activity = join(f.work, "Activity");
    mkdirSync(activity);
    await wait(() => requests().length > 0);
    const request = join(queue, requests()[0]);
    assert.ok(readFileSync(request, "utf8").includes("working_file_changed"));
    const expectRequest = async (change: () => void) => {
      const before = readFileSync(request, "utf8");
      await pause(20);
      change();
      await wait(() => readFileSync(request, "utf8") !== before);
    };
    const note = join(activity, "working-note.md"),
      workingTemp =
        join(f.work, "working-note.md") +
        ".12345678-1234-4234-8234-123456789abc.tmp",
      notes = join(f.options.runtimeRoot, "ordinary-notes");
    await expectRequest(() => writeFileSync(note, "Ordinary working file\n"));
    await expectRequest(() => unlinkSync(note));
    await expectRequest(() => rmdirSync(activity));
    await expectRequest(() =>
      writeFileSync(workingTemp, "Meaningful temporary file"),
    );
    await expectRequest(() => unlinkSync(workingTemp));
    await expectRequest(() => mkdirSync(notes));
    await expectRequest(() => rmdirSync(notes));
    const settled = await sync.flush();
    assert.equal(settled.code, "REMOTE_CONFIRMED", settled.message);
    assert.equal(settled.pending, false);
  } finally {
    await sync.close();
  }
});

import test from "node:test";
import assert from "node:assert/strict";
import {
  chmodSync,
  existsSync,
  linkSync,
  lstatSync,
  mkdirSync,
  mkdtempSync,
  readFileSync,
  rmSync,
  symlinkSync,
  writeFileSync,
} from "node:fs";
import { tmpdir } from "node:os";
import { dirname, join } from "node:path";
import { randomUUID } from "node:crypto";
import {
  SkillBundleFiles,
  skillBundleSnapshot,
} from "../src/storage/skill-bundles.ts";

const relative = "skills/personal/synthetic-procedure";

function fixture(t: { after(action: () => void): void }) {
  const project = mkdtempSync(join(tmpdir(), "zara-bundle-files-"));
  t.after(() => rmSync(project, { recursive: true, force: true }));
  const root = join(project, relative);
  const bytes: Record<string, Uint8Array> = {
    "bundle.json": Buffer.from(
      JSON.stringify({
        format: 1,
        skill_id: randomUUID(),
        name: "Synthetic procedure",
        entry: "SKILL.md",
        file_roles: { "references/steps.md": "text" },
      }),
    ),
    "SKILL.md": Buffer.from(
      "\uFEFF# Synthetic procedure\r\n\r\nRead references/steps.md.\r\n",
    ),
    "references/steps.md": Buffer.from("Keep the marker A-71.\r\n"),
    "references/sample.bin": Uint8Array.from([0, 255, 1, 3]),
    "scripts/example.ps1": Buffer.from("Write-Output 'synthetic-only'\r\n"),
  };
  for (const [path, value] of Object.entries(bytes)) {
    const target = join(root, path);
    mkdirSync(dirname(target), { recursive: true });
    writeFileSync(target, value);
  }
  const files = new SkillBundleFiles(project);
  return { project, root, files, bytes };
}

function code(expected: string) {
  return (error: unknown) =>
    !!error &&
    typeof error === "object" &&
    "code" in error &&
    error.code === expected;
}

test("complete bundle snapshots preserve exact bytes and include supporting scripts", (t) => {
  const f = fixture(t);
  const first = f.files.snapshot(relative);
  assert.deepEqual(
    first.manifest.files.map((file) => file.path),
    Object.keys(f.bytes).sort(),
  );
  assert.deepEqual(
    first.bytes["SKILL.md"],
    Uint8Array.from(f.bytes["SKILL.md"]),
  );
  assert.equal(
    first.manifest.files.find((file) => file.path === "scripts/example.ps1")!
      .role,
    "executable",
  );
  assert.equal(
    first.manifest.files.find((file) => file.path === "references/sample.bin")!
      .role,
    "support",
  );
  writeFileSync(
    join(f.root, "scripts/example.ps1"),
    "Write-Output 'changed-only'\r\n",
  );
  const changed = f.files.snapshot(relative);
  assert.notEqual(changed.manifest.content_hash, first.manifest.content_hash);
  assert.equal(
    changed.manifest.files.find((file) => file.path === "SKILL.md")!.sha256,
    first.manifest.files.find((file) => file.path === "SKILL.md")!.sha256,
  );
  assert.throws(
    () =>
      f.files.withChanges(first, {
        "references/steps.md": Uint8Array.from([255]),
      }),
    code("VALIDATION_ERROR"),
  );
  const literalNames: Record<string, Uint8Array> = Object.create(null);
  literalNames["__proto__"] = Buffer.from("ordinary support bytes");
  literalNames["constructor"] = Buffer.from("another support file");
  const named = f.files.withChanges(first, literalNames);
  assert.equal(
    named.manifest.files.some((file) => file.path === "__proto__"),
    true,
  );
  assert.equal(
    named.manifest.files.find((file) => file.path === "constructor")!.role,
    "support",
  );
});

test("bundle construction rejects ambiguous Windows trees and bounds", (t) => {
  const f = fixture(t);
  const additions: Record<string, Uint8Array>[] = [
    { "Refs/a.md": Buffer.from("a"), "refs/b.md": Buffer.from("b") },
    {
      references: Buffer.from("file"),
      "references/a.md": Buffer.from("nested"),
    },
    { "../outside.md": Buffer.from("escape") },
    { "references/NUL.txt": Buffer.from("alias") },
    { "references/file.txt:stream": Buffer.from("stream") },
  ];
  for (const addition of additions)
    assert.throws(
      () => skillBundleSnapshot({ ...f.bytes, ...addition }),
      code("PERMISSION_DENIED"),
    );
  assert.throws(
    () =>
      skillBundleSnapshot({
        ...f.bytes,
        "references/huge.bin": new Uint8Array(256 * 1024 + 1),
      }),
    code("VALIDATION_ERROR"),
  );
  const many = { ...f.bytes };
  for (let index = 0; index < 128; index++)
    many[`references/${index}.txt`] = Buffer.from("a");
  assert.throws(() => skillBundleSnapshot(many), code("VALIDATION_ERROR"));
  const large = { ...f.bytes };
  for (let index = 0; index < 5; index++)
    large[`references/${index}.bin`] = new Uint8Array(256 * 1024);
  assert.throws(() => skillBundleSnapshot(large), code("VALIDATION_ERROR"));
});

test("snapshot refuses hardlinks and directory junctions", async (t) => {
  await t.test("hardlink", (child) => {
    const f = fixture(child);
    linkSync(
      join(f.root, "references/steps.md"),
      join(f.root, "references/linked.md"),
    );
    assert.throws(() => f.files.snapshot(relative), code("PERMISSION_DENIED"));
  });
  await t.test("junction", (child) => {
    const f = fixture(child);
    const outside = join(f.project, "another-directory");
    mkdirSync(outside);
    writeFileSync(join(outside, "private.md"), "synthetic-marker");
    symlinkSync(outside, join(f.root, "linked-directory"), "junction");
    assert.throws(() => f.files.snapshot(relative), code("PERMISSION_DENIED"));
    assert.equal(
      readFileSync(join(outside, "private.md"), "utf8"),
      "synthetic-marker",
    );
  });
});

test("publication retains versions and selected views isolate working support changes", (t) => {
  const f = fixture(t);
  const before = f.files.snapshot(relative);
  const after = f.files.withChanges(before, {
    "SKILL.md": Buffer.from(
      "# Synthetic procedure\n\nUse the updated instructions.\n",
    ),
  });
  const plan = f.files.plan(
    "apply-synthetic",
    relative,
    before.manifest.content_hash,
    after,
  );
  assert.equal(plan.status, "planned");
  let registrations = 0;
  const receipt = f.files.publish(plan.operation_id, {
    beforeCommit: () => registrations++,
  });
  assert.equal(receipt.content_hash, after.manifest.content_hash);
  assert.equal(registrations, 1);
  assert.deepEqual(f.files.publish(plan.operation_id), receipt);
  assert.equal(
    f.files.plan(
      plan.operation_id,
      relative,
      before.manifest.content_hash,
      after,
    ).status,
    "committed",
  );
  const view = f.files.materialize("invocation-original", before.manifest);
  assert.equal(
    readFileSync(join(view.path, "SKILL.md")).equals(
      Buffer.from(before.bytes["SKILL.md"]),
    ),
    true,
  );
  writeFileSync(
    join(f.root, "scripts/example.ps1"),
    "Write-Output 'later-owner-edit'",
  );
  assert.equal(
    readFileSync(join(view.path, "scripts/example.ps1")).equals(
      Buffer.from(before.bytes["scripts/example.ps1"]),
    ),
    true,
  );
  assert.deepEqual(f.files.verifyView(view), before.manifest);
  writeFileSync(
    join(view.path, "references/steps.md"),
    "tampered local materialization",
  );
  assert.throws(() => f.files.verifyView(view), code("REVISION_CONFLICT"));
  assert.throws(
    () => f.files.materialize("invocation-original", before.manifest),
    code("REVISION_CONFLICT"),
  );
  const current = f.files.snapshot(relative);
  f.files.plan(
    "rollback-synthetic",
    relative,
    current.manifest.content_hash,
    before,
  );
  const rollback = f.files.publish("rollback-synthetic");
  assert.equal(rollback.content_hash, before.manifest.content_hash);
  assert.equal(
    f.files.snapshot(relative).manifest.content_hash,
    before.manifest.content_hash,
  );
});

test("stale admission preserves owner work without blocking a fresh preview", (t) => {
  const f = fixture(t);
  const before = f.files.snapshot(relative);
  const after = f.files.withChanges(before, {
    "SKILL.md": Buffer.from("# Proposed edit\n"),
  });
  f.files.plan("stale", relative, before.manifest.content_hash, after);
  writeFileSync(join(f.root, "SKILL.md"), "# Later owner edit\n");
  assert.throws(() => f.files.publish("stale"), code("APPROVAL_STALE"));
  assert.equal(
    readFileSync(join(f.root, "SKILL.md"), "utf8"),
    "# Later owner edit\n",
  );
  const current = f.files.snapshot(relative);
  assert.equal(
    f.files.plan(
      "replacement",
      relative,
      current.manifest.content_hash,
      current,
    ).status,
    "planned",
  );
  assert.throws(() => f.files.compensate("stale"), code("REVISION_CONFLICT"));
  assert.equal(
    readFileSync(join(f.root, "SKILL.md"), "utf8"),
    "# Later owner edit\n",
  );
});

test("interrupted multi-file publication requires original-operation reconciliation", (t) => {
  const f = fixture(t);
  const before = f.files.snapshot(relative);
  const after = f.files.withChanges(before, {
    "SKILL.md": Buffer.from("# Corrected instructions\n"),
    "references/steps.md": Buffer.from("A second guarded text edit.\n"),
  });
  f.files.plan("interrupted", relative, before.manifest.content_hash, after);
  assert.throws(
    () =>
      f.files.publish("interrupted", {
        fault: (point) => {
          if (point === "after_write:SKILL.md")
            throw new Error("synthetic interruption");
        },
      }),
    /synthetic interruption/,
  );
  const interrupted = f.files.inspect("interrupted");
  assert.equal(interrupted.operation.status, "unknown");
  assert.equal(interrupted.matches_before, false);
  assert.equal(interrupted.matches_after, false);
  const mixed = f.files.snapshot(relative);
  assert.throws(
    () =>
      f.files.plan("replacement", relative, mixed.manifest.content_hash, mixed),
    code("STORE_BUSY"),
  );
  assert.throws(() => f.files.publish("interrupted"), code("STORE_BUSY"));
  assert.equal(f.files.compensate("interrupted").status, "compensated");
  assert.equal(
    f.files.snapshot(relative).manifest.content_hash,
    before.manifest.content_hash,
  );
  f.files.plan(
    "retry-after-compensation",
    relative,
    before.manifest.content_hash,
    after,
  );
  assert.equal(f.files.publish("retry-after-compensation").committed, true);
});

test("lost registry result settles without redispatch and the local lease excludes publication", (t) => {
  const f = fixture(t);
  const before = f.files.snapshot(relative);
  const after = f.files.withChanges(before, {
    "SKILL.md": Buffer.from("# Published result\n"),
  });
  f.files.plan("lost-result", relative, before.manifest.content_hash, after);
  let registrations = 0;
  assert.throws(
    () =>
      f.files.publish("lost-result", {
        beforeCommit: () => {
          registrations++;
          assert.throws(
            () => new SkillBundleFiles(f.project).publish("lost-result"),
            code("STORE_BUSY"),
          );
        },
        fault: (point) => {
          if (point === "after_registry") throw new Error("lost reply");
        },
      }),
    /lost reply/,
  );
  assert.equal(f.files.inspect("lost-result").matches_after, true);
  assert.equal(registrations, 1);
  f.files.reconcile("lost-result", "committed");
  assert.equal(f.files.publish("lost-result").committed, true);
  assert.equal(registrations, 1);
  assert.equal(
    existsSync(join(f.project, ".local/skill-bundles/publication.sqlite")),
    true,
  );
});

test("restore reconstructs an unknown journal from retained exact effect without dispatch", (t) => {
  const f = fixture(t);
  const before = f.files.snapshot(relative);
  const after = f.files.withChanges(before, {
    "SKILL.md": Buffer.from("# Restored pending result\n"),
  });
  const plan = f.files.plan(
    "restored-operation",
    relative,
    before.manifest.content_hash,
    after,
  );
  assert.throws(
    () =>
      f.files.publish(plan.operation_id, {
        fault: (point) => {
          if (point === "after_files")
            throw new Error("synthetic lost registration");
        },
      }),
    /synthetic lost registration/,
  );
  const published = readFileSync(join(f.root, "SKILL.md"));
  rmSync(join(f.project, ".local/skill-bundles/operations"), {
    recursive: true,
  });
  assert.throws(
    () =>
      f.files.restoreOperation(
        plan.operation_id,
        relative,
        before.manifest,
        after.manifest,
        "0".repeat(64),
      ),
    code("REVISION_CONFLICT"),
  );
  const restored = f.files.restoreOperation(
    plan.operation_id,
    relative,
    before.manifest,
    after.manifest,
    plan.digest,
  );
  assert.equal(restored.status, "unknown");
  assert.equal(restored.receipt, undefined);
  assert.equal(readFileSync(join(f.root, "SKILL.md")).equals(published), true);
  assert.equal(f.files.inspect(plan.operation_id).matches_after, true);
  assert.throws(() => f.files.publish(plan.operation_id), code("STORE_BUSY"));
  f.files.reconcile(plan.operation_id, "committed");
  assert.equal(f.files.publish(plan.operation_id).committed, true);
});

test("guarded publication and compensation preserve existing file identity and mode", (t) => {
  const f = fixture(t);
  const target = join(f.root, "references/steps.md");
  chmodSync(target, 0o640);
  const initialIdentity = lstatSync(target, { bigint: true });
  const before = f.files.snapshot(relative);
  const after = f.files.withChanges(before, {
    "references/steps.md": Buffer.from("A shorter instruction.\n"),
  });
  f.files.plan(
    "preserve-existing-file",
    relative,
    before.manifest.content_hash,
    after,
  );
  f.files.publish("preserve-existing-file");
  const publishedIdentity = lstatSync(target, { bigint: true });
  assert.equal(publishedIdentity.dev, initialIdentity.dev);
  assert.equal(publishedIdentity.ino, initialIdentity.ino);
  assert.equal(publishedIdentity.mode, initialIdentity.mode);
  assert.equal(
    readFileSync(target).equals(
      Buffer.from(after.bytes["references/steps.md"]),
    ),
    true,
  );

  const candidate = f.files.withChanges(after, {
    "references/steps.md": Buffer.from(
      "A considerably longer candidate instruction awaiting registration.\n",
    ),
  });
  f.files.plan(
    "compensate-existing-file",
    relative,
    after.manifest.content_hash,
    candidate,
  );
  assert.throws(
    () =>
      f.files.publish("compensate-existing-file", {
        fault: (point) => {
          if (point === "after_files")
            throw new Error("synthetic registration interruption");
        },
      }),
    /synthetic registration interruption/,
  );
  f.files.compensate("compensate-existing-file");
  const compensatedIdentity = lstatSync(target, { bigint: true });
  assert.equal(compensatedIdentity.dev, initialIdentity.dev);
  assert.equal(compensatedIdentity.ino, initialIdentity.ino);
  assert.equal(compensatedIdentity.mode, initialIdentity.mode);
  assert.equal(
    readFileSync(target).equals(
      Buffer.from(after.bytes["references/steps.md"]),
    ),
    true,
  );
});

test("observed partial writes remain UNKNOWN and recover only while exact partial bytes match", (t) => {
  const f = fixture(t);
  const target = join(f.root, "references/steps.md");
  const initialIdentity = lstatSync(target, { bigint: true });
  const before = f.files.snapshot(relative);
  const after = f.files.withChanges(before, {
    "references/steps.md": Buffer.alloc(100000, 0x41),
  });
  const interrupt = (point: string) => {
    if (point === "after_write_chunk:references/steps.md:65536")
      throw new Error("synthetic partial-write failure");
  };
  f.files.plan("partial-write", relative, before.manifest.content_hash, after);
  assert.throws(
    () => f.files.publish("partial-write", { fault: interrupt }),
    /synthetic partial-write failure/,
  );
  const observed = f.files.inspect("partial-write");
  assert.equal(observed.operation.status, "unknown");
  assert.equal(observed.matches_before, false);
  assert.equal(observed.matches_after, false);
  assert.equal(observed.operation.partial_write!.length, 65536);
  assert.equal(
    readFileSync(target).equals(
      Buffer.from(observed.operation.partial_write!.bytes_base64, "base64"),
    ),
    true,
  );
  assert.throws(() => f.files.publish("partial-write"), code("STORE_BUSY"));
  f.files.compensate("partial-write");
  assert.equal(
    readFileSync(target).equals(
      Buffer.from(before.bytes["references/steps.md"]),
    ),
    true,
  );
  assert.equal(lstatSync(target, { bigint: true }).ino, initialIdentity.ino);

  f.files.plan(
    "partial-then-owner-edit",
    relative,
    before.manifest.content_hash,
    after,
  );
  assert.throws(
    () => f.files.publish("partial-then-owner-edit", { fault: interrupt }),
    /synthetic partial-write failure/,
  );
  writeFileSync(target, "Later owner instructions must survive.\n");
  assert.throws(
    () => f.files.compensate("partial-then-owner-edit"),
    code("REVISION_CONFLICT"),
  );
  assert.equal(
    readFileSync(target, "utf8"),
    "Later owner instructions must survive.\n",
  );
  assert.equal(
    f.files.inspect("partial-then-owner-edit").operation.status,
    "unknown",
  );
});

test("a verified historical Core receipt settles a lost reply while preserving current drift", (t) => {
  const f = fixture(t);
  const before = f.files.snapshot(relative);
  const after = f.files.withChanges(before, {
    "SKILL.md": Buffer.from("# Verified historical result\n"),
  });
  f.files.plan(
    "historical-settlement",
    relative,
    before.manifest.content_hash,
    after,
  );
  assert.throws(
    () =>
      f.files.publish("historical-settlement", {
        fault: (point) => {
          if (point === "after_registry")
            throw new Error("synthetic lost journal reply");
        },
      }),
    /synthetic lost journal reply/,
  );
  writeFileSync(join(f.root, "SKILL.md"), "# A later owner edit\n");
  assert.throws(
    () => f.files.reconcile("historical-settlement", "committed"),
    code("REVISION_CONFLICT"),
  );
  assert.throws(
    () =>
      f.files.settleFromRegistry("historical-settlement", {
        operation_id: "historical-settlement",
        content_hash: "0".repeat(64),
        committed: true,
      }),
    code("REVISION_CONFLICT"),
  );
  const settled = f.files.settleFromRegistry("historical-settlement", {
    operation_id: "historical-settlement",
    content_hash: after.manifest.content_hash,
    committed: true,
  });
  assert.equal(settled.status, "committed");
  assert.equal(f.files.inspect("historical-settlement").matches_after, false);
  assert.equal(
    readFileSync(join(f.root, "SKILL.md"), "utf8"),
    "# A later owner edit\n",
  );
  const current = f.files.snapshot(relative);
  assert.equal(
    f.files.plan(
      "next-reviewed-operation",
      relative,
      current.manifest.content_hash,
      current,
    ).status,
    "planned",
  );
});

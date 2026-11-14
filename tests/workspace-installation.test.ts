import test from "node:test";
import assert from "node:assert/strict";
import {
  existsSync,
  chmodSync,
  cpSync,
  linkSync,
  lstatSync,
  mkdirSync,
  mkdtempSync,
  readFileSync,
  symlinkSync,
  writeFileSync,
} from "node:fs";
import { join, resolve } from "node:path";
import { createHash, randomUUID } from "node:crypto";
import { createRequire } from "node:module";
import { Coordination } from "../src/storage/index.ts";
import {
  WorkspaceInstaller,
  attachPi,
  getWorkspaceProduct,
  inspectWorkspace,
  inspectPiAttachment,
  loadWorkspaceGuidance,
  readWorkspaceManifest,
} from "../src/workspace/index.ts";
import { PRODUCT_SKILLS } from "../src/workspace/templates.ts";

const testArea = resolve("_scratch/workspace-tests");
mkdirSync(testArea, { recursive: true });
const product = { version: "0.7.7-test", revision: "synthetic-product-a" };
const nextProduct = { version: "0.7.8-test", revision: "synthetic-product-b" };

function directory() {
  return mkdtempSync(join(testArea, "installation-"));
}

function fixturePackage() {
  const root = directory();
  writeFileSync(
    join(root, "package.json"),
    JSON.stringify({ version: "0.7.7-test" }),
  );
  for (const name of PRODUCT_SKILLS) {
    mkdirSync(join(root, "skills", name), { recursive: true });
    writeFileSync(
      join(root, "skills", name, "SKILL.md"),
      `---\nname: ${name}\ndescription: Synthetic workflow\n---\n\nRead source files and create the specified ordinary result.\n`,
    );
  }
  return root;
}

function installer(
  root: string,
  overrides: ConstructorParameters<typeof WorkspaceInstaller>[1] = {},
) {
  return new WorkspaceInstaller(root, { product, ...overrides });
}

function code(value: string) {
  return (error: unknown) => (error as { code?: string }).code === value;
}

test("portable installation creates visible guidance without Pi and repeat preserves owner bytes", () => {
  const root = directory();
  const first = installer(root).initialize();
  assert.equal(first.state, "committed");
  const manifest = readWorkspaceManifest(root)!;
  assert.equal(manifest.layout_format, 1);
  assert.equal(existsSync(join(root, "memory/corpus.json")), false);
  assert.equal(existsSync(join(root, ".local/memory/active.json")), false);
  assert.ok(
    readFileSync(join(root, "AGENTS.md"), "utf8").split(/\r?\n/).filter(Boolean)
      .length <= 30,
  );
  assert.equal(
    manifest.managed_files.filter((file) => file.kind === "generated").length,
    4,
  );
  const owner = Buffer.from("\uFEFF# Owner rules\r\nKeep exact bytes.\r\n");
  writeFileSync(join(root, "instructions/workspace.md"), owner);
  mkdirSync(join(root, "activities/old-path"), { recursive: true });
  writeFileSync(join(root, "activities/old-path/result.md"), owner);
  const second = installer(root).initialize();
  assert.equal(second.state, "unchanged");
  assert.equal(
    readWorkspaceManifest(root)!.installation_id,
    manifest.installation_id,
  );
  assert.deepEqual(
    readFileSync(join(root, "instructions/workspace.md")),
    owner,
  );
  assert.deepEqual(
    readFileSync(join(root, "activities/old-path/result.md")),
    owner,
  );
  assert.equal(inspectWorkspace(root).state, "current");
});

test("owner root guidance is preserved until an exact reviewed integration", () => {
  const root = directory();
  const owner = "\uFEFF# Existing owner\r\nPersonal guidance.\r\n";
  writeFileSync(join(root, "AGENTS.md"), owner);
  chmodSync(join(root, "AGENTS.md"), 0o600);
  const beforeIdentity = lstatSync(join(root, "AGENTS.md"));
  const result = installer(root).initialize();
  assert.equal(result.state, "pending");
  assert.equal(readFileSync(join(root, "AGENTS.md"), "utf8"), owner);
  assert.equal(readWorkspaceManifest(root), undefined);
  assert.ok("plan" in result);
  const plan = result.plan!;
  assert.equal(
    plan.entries.find((entry) => entry.path === "AGENTS.md")!.conflict,
    true,
  );
  const applied = installer(root).apply(plan.plan_id);
  assert.equal(applied.state, "committed");
  assert.ok(readFileSync(join(root, "AGENTS.md"), "utf8").startsWith(owner));
  assert.match(
    readFileSync(join(root, "AGENTS.md"), "utf8"),
    /instructions\/system.md/,
  );
  const afterIdentity = lstatSync(join(root, "AGENTS.md"));
  assert.equal(afterIdentity.ino, beforeIdentity.ino);
  assert.equal(afterIdentity.dev, beforeIdentity.dev);
  assert.equal(afterIdentity.mode, beforeIdentity.mode);
});

test("update detects drift and binds accepted before bytes while preserving private owner areas", () => {
  const root = directory();
  installer(root).initialize();
  const modified = "# Local modification\n";
  writeFileSync(join(root, "instructions/system.md"), modified);
  const update = installer(root, { product: nextProduct });
  const plan = update.plan();
  assert.equal(
    plan.entries.find((entry) => entry.path === "instructions/system.md")!
      .conflict,
    true,
  );
  assert.equal(readWorkspaceManifest(root)!.product.revision, product.revision);
  const receipt = update.apply(plan.plan_id);
  assert.equal(receipt.product.revision, nextProduct.revision);
  const retainedPlan = update.inspectOperation(plan.plan_id).plan;
  assert.equal(
    Buffer.from(
      retainedPlan.entries.find(
        (entry) => entry.path === "instructions/system.md",
      )!.before!,
      "base64",
    ).toString(),
    modified,
  );
  assert.equal(inspectWorkspace(root).state, "current");
});

test("a stale target refuses admission and a new plan can preserve the later edit", () => {
  const root = directory();
  installer(root).initialize();
  const update = installer(root, { product: nextProduct });
  const plan = update.plan();
  const path = plan.entries[0].path;
  writeFileSync(join(root, path), "Owner edited after the plan\n");
  assert.throws(() => update.apply(plan.plan_id), code("REVISION_CONFLICT"));
  assert.equal(
    readFileSync(join(root, path), "utf8"),
    "Owner edited after the plan\n",
  );
  assert.equal(update.inspectOperation(plan.plan_id).journal.state, "refused");
  assert.throws(
    () => update.recover(plan.plan_id, "complete"),
    code("REVISION_CONFLICT"),
  );
  assert.ok(
    update.plan().entries.find((entry) => entry.path === path)!.conflict,
  );
});

test("interrupted multi-file publication is inspected and completed through its original operation", () => {
  const root = directory();
  let stopped = false;
  const interrupted = installer(root, {
    fault(point) {
      if (point === "after_file" && !stopped) {
        stopped = true;
        throw new Error("Synthetic interruption");
      }
    },
  });
  const plan = interrupted.plan();
  assert.throws(
    () => interrupted.apply(plan.plan_id),
    /Synthetic interruption/,
  );
  assert.equal(readWorkspaceManifest(root), undefined);
  const resumed = installer(root);
  const inspection = resumed.inspectOperation(plan.plan_id);
  assert.ok(inspection.targets.some((target) => target.state === "after"));
  assert.ok(inspection.targets.some((target) => target.state === "before"));
  assert.throws(() => resumed.apply(plan.plan_id), code("STORE_BUSY"));
  assert.throws(() => resumed.plan(), code("STORE_BUSY"));
  const receipt = resumed.recover(plan.plan_id, "complete");
  assert.equal(receipt.state, "committed");
  assert.equal(inspectWorkspace(root).state, "current");
  assert.deepEqual(resumed.apply(plan.plan_id), receipt);
});

test("reply loss after manifest or receipt settles without redispatch", () => {
  for (const phase of ["after_manifest", "after_receipt"]) {
    const root = directory();
    const interrupted = installer(root, {
      fault(point) {
        if (point === phase) throw new Error("Synthetic lost reply");
      },
    });
    const plan = interrupted.plan();
    assert.throws(
      () => interrupted.apply(plan.plan_id),
      /Synthetic lost reply/,
    );
    const firstGuidance = readFileSync(join(root, "AGENTS.md"));
    const resumed = installer(root);
    const recovered = resumed.recover(plan.plan_id, "complete");
    assert.equal(recovered.state, "committed");
    assert.deepEqual(readFileSync(join(root, "AGENTS.md")), firstGuidance);
    assert.deepEqual(resumed.apply(plan.plan_id), recovered);
    assert.equal(inspectWorkspace(root).pending_operations.length, 0);
    assert.equal(resumed.plan().entries.length, 0);
  }
});

test("guarded compensation restores original bytes and refuses later owner changes", () => {
  for (const ownerChanges of [false, true]) {
    const root = directory();
    installer(root).initialize();
    const before = readFileSync(join(root, "zaratustra.json"));
    let writtenPath = "";
    const interrupted = installer(root, {
      product: nextProduct,
      fault(point, path) {
        if (point === "after_file") {
          writtenPath = path!;
          throw new Error("Synthetic interrupted update");
        }
      },
    });
    const plan = interrupted.plan();
    assert.throws(
      () => interrupted.apply(plan.plan_id),
      /Synthetic interrupted update/,
    );
    const resumed = installer(root, { product: nextProduct });
    if (ownerChanges) {
      writeFileSync(join(root, writtenPath), "Later owner work\n");
      assert.throws(
        () => resumed.recover(plan.plan_id, "rollback"),
        code("REVISION_CONFLICT"),
      );
      assert.equal(
        readFileSync(join(root, writtenPath), "utf8"),
        "Later owner work\n",
      );
    } else {
      const receipt = resumed.recover(plan.plan_id, "rollback");
      assert.equal(receipt.state, "rolled_back");
      assert.deepEqual(readFileSync(join(root, "zaratustra.json")), before);
      assert.equal(inspectWorkspace(root).state, "current");
    }
  }
});

test("competing installers serialize their publication reservations", () => {
  const root = directory();
  installer(root).initialize();
  const competitor = installer(root, { product: nextProduct });
  const competingPlan = competitor.plan();
  let observedBusy = false;
  const first = installer(root, {
    product: nextProduct,
    fault(point) {
      if (point === "before_publish") {
        assert.throws(
          () => competitor.apply(competingPlan.plan_id),
          code("STORE_BUSY"),
        );
        observedBusy = true;
      }
    },
  });
  const plan = first.plan();
  first.apply(plan.plan_id);
  assert.equal(observedBusy, true);
  assert.equal(inspectWorkspace(root).state, "current");
});

test("installation refuses linked files, redirected directories and device names before publication", () => {
  const hardlinkRoot = directory();
  const source = join(directory(), "owner.md");
  writeFileSync(source, "External exact owner bytes\n");
  linkSync(source, join(hardlinkRoot, "AGENTS.md"));
  assert.throws(
    () => installer(hardlinkRoot).initialize(),
    code("PERMISSION_DENIED"),
  );
  assert.equal(readFileSync(source, "utf8"), "External exact owner bytes\n");
  const redirected = directory();
  const other = directory();
  mkdirSync(join(redirected, "skills"));
  symlinkSync(other, join(redirected, "skills/system"), "junction");
  assert.throws(
    () => installer(redirected).initialize(),
    code("PERMISSION_DENIED"),
  );
  assert.equal(existsSync(join(other, "zaratustra-work")), false);
  assert.throws(
    () => new WorkspaceInstaller(join(directory(), "NUL")),
    code("PERMISSION_DENIED"),
  );
});

test("Activity guidance resolves explicit IDs from root and replaces rather than merges selections", () => {
  const root = directory();
  installer(root).initialize();
  mkdirSync(join(root, "activities/legacy-path"));
  writeFileSync(
    join(root, "activities/legacy-path/AGENTS.md"),
    "Verify Health dates.\n",
  );
  writeFileSync(join(root, "activities/other.md"), "Use another procedure.\n");
  const manifest = readWorkspaceManifest(root)!;
  manifest.activities = [
    {
      key: "health-key",
      label: "Synthetic Health",
      guidance_path: "activities/legacy-path/AGENTS.md",
      core_ref: { id: "activity-health" },
    },
    {
      key: "other-key",
      label: "Another Activity",
      guidance_path: "activities/other.md",
      core_ref: { id: "activity-other" },
    },
  ];
  writeFileSync(
    join(root, "zaratustra.json"),
    JSON.stringify(manifest, null, 2) + "\n",
  );
  const health = loadWorkspaceGuidance(root, {
    core_activity_id: "activity-health",
    product_revision: product.revision,
  })!;
  assert.equal(health.activity!.key, "health-key");
  assert.match(health.activity!.text, /Health dates/);
  const other = loadWorkspaceGuidance(root, { activity_id: "other-key" })!;
  assert.match(other.activity!.text, /another procedure/);
  assert.doesNotMatch(other.activity!.text, /Health dates/);
  assert.equal(health.workspace.text, other.workspace.text);
  const missing = loadWorkspaceGuidance(root, { activity_id: "unknown" })!;
  assert.equal(missing.activity, null);
  assert.equal(missing.warnings.length, 1);
  assert.throws(
    () => loadWorkspaceGuidance(root, { product_revision: "different" }),
    code("REVISION_CONFLICT"),
  );
});

test("personal discovery routes point to one canonical bundle and preserve Activity scope", () => {
  const root = directory();
  installer(root).initialize();
  mkdirSync(join(root, "skills/personal/health-summary"));
  writeFileSync(
    join(root, "skills/personal/health-summary/SKILL.md"),
    "Summarize synthetic Health records.\n",
  );
  const manifest = readWorkspaceManifest(root)!;
  manifest.personal_skills = [
    {
      name: "health-summary",
      description: "Synthetic summary",
      path: "skills/personal/health-summary/SKILL.md",
      activity_key: "health-key",
    },
  ];
  writeFileSync(
    join(root, "zaratustra.json"),
    JSON.stringify(manifest, null, 2) + "\n",
  );
  const update = installer(root);
  const plan = update.plan();
  update.apply(plan.plan_id);
  for (const adapter of [".agents"]) {
    const route = readFileSync(
      join(root, adapter, "skills/health-summary/SKILL.md"),
      "utf8",
    );
    assert.match(
      route,
      /\.\.\/\.\.\/\.\.\/skills\/personal\/health-summary\/SKILL.md/,
    );
    assert.match(route, /Activity "health-key"/);
  }
  assert.equal(
    existsSync(join(root, ".pi/skills/health-summary/SKILL.md")),
    false,
  );
  writeFileSync(
    join(root, ".agents/skills/health-summary/SKILL.md"),
    "Modified generated entry\n",
  );
  assert.equal(
    update
      .plan()
      .entries.find(
        (entry) => entry.path === ".agents/skills/health-summary/SKILL.md",
      )!.conflict,
    true,
  );
});

test("shared discovery retires only unchanged recorded Pi copies", () => {
  for (const changed of [false, true]) {
    const root = directory();
    installer(root).initialize();
    const manifest = readWorkspaceManifest(root)!;
    const oldPath = ".pi/skills/zaratustra-work/SKILL.md";
    const bytes = readFileSync(
      join(root, ".agents/skills/zaratustra-work/SKILL.md"),
    );
    mkdirSync(join(root, ".pi/skills/zaratustra-work"), { recursive: true });
    writeFileSync(join(root, oldPath), bytes);
    manifest.managed_files.push({
      path: oldPath,
      kind: "generated",
      sha256: createHash("sha256").update(bytes).digest("hex"),
    });
    writeFileSync(join(root, "zaratustra.json"), JSON.stringify(manifest));
    mkdirSync(join(root, ".pi/skills/owner-tool"), { recursive: true });
    const ownerPath = join(root, ".pi/skills/owner-tool/SKILL.md");
    writeFileSync(ownerPath, "Owner procedure\n");
    if (changed) writeFileSync(join(root, oldPath), "Owner-edited Pi route\n");
    const update = installer(root);
    const plan = update.plan();
    const retired = plan.entries.find((entry) => entry.path === oldPath)!;
    assert.equal(retired.after, null);
    assert.equal(retired.conflict, changed);
    if (changed) {
      assert.equal(update.initialize().state, "pending");
      assert.equal(
        readFileSync(join(root, oldPath), "utf8"),
        "Owner-edited Pi route\n",
      );
    } else {
      update.apply(plan.plan_id);
      assert.equal(existsSync(join(root, oldPath)), false);
      assert.equal(
        readWorkspaceManifest(root)!.installation_id,
        manifest.installation_id,
      );
    }
    assert.equal(readFileSync(ownerPath, "utf8"), "Owner procedure\n");
    assert.deepEqual(
      readFileSync(join(root, ".agents/skills/zaratustra-work/SKILL.md")),
      bytes,
    );
  }
});

test("Pi-only and Codex-only adapters use the same single discovery route", () => {
  for (const adapters of [["pi"], ["codex"], ["pi", "codex"]] as const) {
    const root = directory();
    installer(root).initialize();
    const manifest = readWorkspaceManifest(root)!;
    manifest.adapters = [...adapters];
    writeFileSync(join(root, "zaratustra.json"), JSON.stringify(manifest));
    installer(root).initialize();
    const generated = readWorkspaceManifest(root)!.managed_files.filter(
      (file) => file.kind === "generated",
    );
    assert.equal(generated.length, 4);
    assert(generated.every((file) => file.path.startsWith(".agents/skills/")));
    assert.equal(
      existsSync(join(root, ".pi/skills/zaratustra-work/SKILL.md")),
      false,
    );
  }
});

test("native local Pi attachment preserves unrelated settings and exact package objects", () => {
  const packageRoot = fixturePackage();
  const root = directory();
  new WorkspaceInstaller(root, { packageRoot }).initialize();
  const oldPackage = {
    source: "npm:synthetic-extension",
    skills: ["only-one"],
  };
  const before = { theme: "synthetic", packages: [oldPackage] };
  writeFileSync(join(root, ".pi/settings.json"), JSON.stringify(before));
  let installed = "";
  const result = attachPi(root, {
    packageRoot,
    runInstall(source, cwd) {
      installed = source;
      assert.equal(cwd, root);
      writeFileSync(
        join(root, ".pi/settings.json"),
        JSON.stringify({ ...before, packages: [oldPackage, source] }),
      );
    },
  });
  assert.equal(installed, packageRoot);
  assert.equal(result.state, "pending_native_trust");
  assert.equal(
    result.product.revision,
    getWorkspaceProduct(packageRoot).revision,
  );
  assert.equal(existsSync(join(root, ".local/memory/active.json")), false);
  assert.deepEqual(
    JSON.parse(readFileSync(join(root, ".pi/settings.json"), "utf8")),
    { ...before, packages: [oldPackage, { source: packageRoot, skills: [] }] },
  );
  assert.throws(
    () =>
      attachPi(root, {
        packageRoot,
        runInstall(source) {
          writeFileSync(
            join(root, ".pi/settings.json"),
            JSON.stringify({
              ...before,
              packages: [{ source: oldPackage.source, skills: [] }, source],
            }),
          );
        },
      }),
    code("REVISION_CONFLICT"),
  );
});

test("own Pi package normalization retains its other filters and repeats safely", () => {
  const packageRoot = fixturePackage();
  const root = directory();
  new WorkspaceInstaller(root, { packageRoot }).initialize();
  const owner = {
    source: packageRoot,
    autoload: true,
    extensions: ["only-extension.ts"],
    prompts: ["owner-prompt.md"],
  };
  const foreign = { source: "npm:foreign", skills: ["selected"] };
  const before = {
    theme: "owner-theme",
    thinkingLevel: "low",
    packages: [foreign, owner],
  };
  const path = join(root, ".pi/settings.json");
  writeFileSync(path, JSON.stringify(before));
  const identity = lstatSync(path).ino;
  let dispatches = 0;
  const runInstall = () => {
    dispatches++;
  };
  attachPi(root, { packageRoot, runInstall });
  const expected = { ...before, packages: [foreign, { ...owner, skills: [] }] };
  assert.deepEqual(JSON.parse(readFileSync(path, "utf8")), expected);
  assert.equal(lstatSync(path).ino, identity);
  attachPi(root, { packageRoot, runInstall });
  assert.equal(dispatches, 2);
  assert.deepEqual(JSON.parse(readFileSync(path, "utf8")), expected);
});

test("explicit own skill filters and autoload deltas refuse before native dispatch", () => {
  for (const filter of [
    { skills: ["chosen"] },
    { autoload: false },
    { autoload: false, skills: [] },
  ]) {
    const packageRoot = fixturePackage();
    const root = directory();
    new WorkspaceInstaller(root, { packageRoot }).initialize();
    const path = join(root, ".pi/settings.json");
    const before = JSON.stringify({
      theme: "owner",
      packages: [{ source: packageRoot, ...filter }],
    });
    writeFileSync(path, before);
    let dispatches = 0;
    assert.throws(
      () =>
        attachPi(root, {
          packageRoot,
          runInstall() {
            dispatches++;
          },
        }),
      code("REVISION_CONFLICT"),
    );
    assert.equal(dispatches, 0);
    assert.equal(readFileSync(path, "utf8"), before);
    assert.equal(inspectWorkspace(root).pending_attachments.length, 0);
  }
});

test("journaled skill-filter publication settles its original operation without reinstall", () => {
  for (const stop of ["before_skill_filter", "after_skill_filter"]) {
    const packageRoot = fixturePackage();
    const root = directory();
    new WorkspaceInstaller(root, { packageRoot }).initialize();
    const path = join(root, ".pi/settings.json");
    const foreign = { source: "npm:owner", skills: ["selected"] };
    writeFileSync(
      path,
      JSON.stringify({ theme: "owner", packages: [foreign] }),
    );
    let dispatches = 0;
    assert.throws(
      () =>
        attachPi(root, {
          packageRoot,
          runInstall(source) {
            dispatches++;
            writeFileSync(
              path,
              JSON.stringify({ theme: "owner", packages: [foreign, source] }),
            );
          },
          fault(point) {
            if (point === stop)
              throw new Error("Synthetic filter interruption");
          },
        }),
      /Synthetic filter interruption/,
    );
    const pending = inspectWorkspace(root).pending_attachments[0];
    assert.equal(pending.state, "unknown");
    assert(pending.settings_filter);
    const observed = readFileSync(path);
    assert.equal(
      createHash("sha256").update(observed).digest("hex"),
      stop === "before_skill_filter"
        ? pending.settings_filter.before_hash
        : pending.settings_filter.after_hash,
    );
    const settled = attachPi(root, {
      packageRoot,
      operation_id: pending.operation_id,
      runInstall() {
        dispatches++;
      },
    });
    assert.equal(settled.operation_id, pending.operation_id);
    assert.equal(dispatches, 1);
    assert.deepEqual(JSON.parse(readFileSync(path, "utf8")), {
      theme: "owner",
      packages: [foreign, { source: packageRoot, skills: [] }],
    });
    assert.equal(inspectWorkspace(root).pending_attachments.length, 0);
  }
});

test("owner drift after recorded native settings stops filter recovery without redispatch", () => {
  const packageRoot = fixturePackage();
  const root = directory();
  new WorkspaceInstaller(root, { packageRoot }).initialize();
  const path = join(root, ".pi/settings.json");
  let dispatches = 0;
  assert.throws(
    () =>
      attachPi(root, {
        packageRoot,
        runInstall(source) {
          dispatches++;
          writeFileSync(path, JSON.stringify({ packages: [source] }));
        },
        fault(point) {
          if (point === "before_skill_filter")
            throw new Error("Synthetic filter stop");
        },
      }),
    /Synthetic filter stop/,
  );
  const pending = inspectWorkspace(root).pending_attachments[0];
  const owner = JSON.stringify({
    packages: [packageRoot],
    theme: "Later owner edit",
  });
  writeFileSync(path, owner);
  assert.throws(
    () =>
      attachPi(root, {
        packageRoot,
        operation_id: pending.operation_id,
        runInstall() {
          dispatches++;
        },
      }),
    code("REVISION_CONFLICT"),
  );
  assert.equal(dispatches, 1);
  assert.equal(readFileSync(path, "utf8"), owner);
  assert.deepEqual(
    inspectWorkspace(root).pending_attachments[0].settings_filter,
    pending.settings_filter,
  );
});

test("a confirmed attachment never republishes its recorded settings after owner restoration", () => {
  const packageRoot = fixturePackage();
  const root = directory();
  new WorkspaceInstaller(root, { packageRoot }).initialize();
  const path = join(root, ".pi/settings.json");
  let dispatches = 0;
  const result = attachPi(root, {
    packageRoot,
    runInstall(source) {
      dispatches++;
      writeFileSync(path, JSON.stringify({ packages: [source] }));
    },
  });
  const intent = inspectPiAttachment(root, result.operation_id).intent;
  assert(intent.settings_filter);
  const receiptPath = join(
    root,
    ".local/workspace/attachments",
    result.operation_id + ".json",
  );
  const receipt = readFileSync(receiptPath);
  const replay = attachPi(root, {
    packageRoot,
    operation_id: result.operation_id,
    runInstall() {
      dispatches++;
    },
  });
  assert.deepEqual(replay, result);
  assert.deepEqual(readFileSync(receiptPath), receipt);
  const identity = lstatSync(path).ino;
  const original = Buffer.from(intent.settings_filter.before, "base64");
  writeFileSync(path, original);
  assert.equal(lstatSync(path).ino, identity);
  assert.throws(
    () =>
      attachPi(root, {
        packageRoot,
        operation_id: result.operation_id,
        runInstall() {
          dispatches++;
        },
      }),
    code("REVISION_CONFLICT"),
  );
  assert.equal(dispatches, 1);
  assert.deepEqual(readFileSync(path), original);
  assert.deepEqual(readFileSync(receiptPath), receipt);
});

test("native attachment resolves the declared CLI of a hoisted import-only Pi peer", (t) => {
  const parent = directory();
  const packageRoot = join(parent, "node_modules/zaratustra");
  const fixture = fixturePackage();
  cpSync(fixture, packageRoot, { recursive: true });
  const peer = join(parent, "node_modules/@earendil-works/pi-coding-agent");
  mkdirSync(join(peer, "dist/bundle"), { recursive: true });
  writeFileSync(
    join(peer, "package.json"),
    JSON.stringify({
      name: "@earendil-works/pi-coding-agent",
      version: "1.5.2",
      type: "module",
      bin: { pi: "dist/bundle/cli.js" },
      exports: {
        ".": { types: "./dist/index.d.ts", import: "./dist/index.js" },
      },
    }),
  );
  writeFileSync(join(peer, "dist/index.js"), "export {};\n");
  writeFileSync(join(peer, "dist/index.d.ts"), "export {};\n");
  assert.throws(
    () =>
      createRequire(join(packageRoot, "package.json")).resolve(
        "@earendil-works/pi-coding-agent",
      ),
    (error: unknown) =>
      (error as { code?: string }).code === "ERR_PACKAGE_PATH_NOT_EXPORTED",
  );
  writeFileSync(
    join(peer, "dist/bundle/cli.js"),
    `import {readFileSync,writeFileSync} from 'node:fs';
import {join} from 'node:path';
const path=join(process.cwd(),'.pi/settings.json');
const before=JSON.parse(readFileSync(path,'utf8'));
writeFileSync(path,JSON.stringify({...before,packages:[process.argv.at(-1)]}));\n`,
  );
  const root = directory();
  new WorkspaceInstaller(root, { packageRoot }).initialize();
  writeFileSync(
    join(root, ".pi/settings.json"),
    JSON.stringify({ theme: "owner" }),
  );
  const oldPath = process.env.PATH;
  t.after(() => {
    if (oldPath === undefined) delete process.env.PATH;
    else process.env.PATH = oldPath;
  });
  process.env.PATH = "";
  attachPi(root, { packageRoot });
  assert.deepEqual(
    JSON.parse(readFileSync(join(root, ".pi/settings.json"), "utf8")),
    {
      theme: "owner",
      packages: [{ source: packageRoot, skills: [] }],
    },
  );
});

test("uncertain native Pi attachment settles original observed state without reinstalling", () => {
  const packageRoot = fixturePackage();
  const root = directory();
  new WorkspaceInstaller(root, { packageRoot }).initialize();
  let dispatches = 0;
  assert.throws(
    () =>
      attachPi(root, {
        packageRoot,
        runInstall(source) {
          dispatches++;
          writeFileSync(
            join(root, ".pi/settings.json"),
            JSON.stringify({ packages: [source] }),
          );
          throw new Error("Synthetic lost native reply");
        },
      }),
    /Synthetic lost native reply/,
  );
  const pending = inspectWorkspace(root).pending_attachments;
  assert.equal(pending.length, 1);
  assert.equal(pending[0].state, "unknown");
  assert.throws(
    () =>
      attachPi(root, {
        packageRoot,
        runInstall() {
          dispatches++;
        },
      }),
    code("STORE_BUSY"),
  );
  assert.throws(
    () => new WorkspaceInstaller(root, { packageRoot }).plan(),
    code("STORE_BUSY"),
  );
  const observed = inspectPiAttachment(root, pending[0].operation_id);
  assert.ok(observed.observed_settings_hash);
  const settled = attachPi(root, {
    packageRoot,
    operation_id: pending[0].operation_id,
    runInstall() {
      dispatches++;
    },
  });
  assert.equal(settled.operation_id, pending[0].operation_id);
  assert.equal(settled.state, "pending_native_trust");
  assert.equal(dispatches, 1);
  assert.equal(inspectWorkspace(root).pending_attachments.length, 0);
});

test("incomplete native attachment preserves uncertainty and exact prior settings", () => {
  const packageRoot = fixturePackage();
  const root = directory();
  new WorkspaceInstaller(root, { packageRoot }).initialize();
  const original = Buffer.from('{"theme":"synthetic","packages":[]}\r\n');
  writeFileSync(join(root, ".pi/settings.json"), original);
  assert.throws(
    () =>
      attachPi(root, {
        packageRoot,
        runInstall() {
          throw new Error("Synthetic native interruption");
        },
      }),
    /Synthetic native interruption/,
  );
  const pending = inspectWorkspace(root).pending_attachments[0];
  assert.deepEqual(Buffer.from(pending.settings_before!, "base64"), original);
  assert.throws(
    () => attachPi(root, { packageRoot, operation_id: pending.operation_id }),
    code("STORE_UNAVAILABLE"),
  );
  assert.deepEqual(readFileSync(join(root, ".pi/settings.json")), original);
  assert.equal(inspectWorkspace(root).pending_attachments[0].state, "unknown");
});

test("explicit alternate managed home binds native coordination, identity and epoch", () => {
  const root = directory();
  const managedHome = directory();
  const native = new Coordination(
    managedHome,
    "synthetic-native-" + randomUUID(),
    { create: true },
  );
  const epoch = randomUUID();
  const control = {
    format: 3,
    workspace_id: randomUUID(),
    epoch,
    generation: ".",
    restoration: null,
    coordination_id: native.identity,
    coordination_protocol: 1,
  };
  writeFileSync(join(managedHome, "active.json"), JSON.stringify(control));
  const operationId = randomUUID();
  native.sync("mutate", () =>
    native.reserve({
      operation_id: operationId,
      epoch,
      kind: "synthetic-core-workspace-race",
      digest: "synthetic-native-reservation",
      resources: ["workspace:layout"],
    }),
  );
  const selected = installer(root, { managedHome });
  const blocked = selected.plan();
  assert.equal(blocked.managed_context.state, "managed");
  assert.equal(blocked.managed_context.home, managedHome);
  assert.throws(() => selected.apply(blocked.plan_id), code("STORE_BUSY"));
  assert.equal(readWorkspaceManifest(root), undefined);
  native.sync("settle", () => native.release(operationId), { operationId });
  const plan = selected.plan();
  assert.throws(
    () => installer(root).apply(plan.plan_id),
    code("REVISION_CONFLICT"),
  );
  const receipt = selected.apply(plan.plan_id);
  assert.equal(receipt.state, "committed");
  const next = installer(root, { managedHome, product: nextProduct });
  const nextPlan = next.plan();
  writeFileSync(
    join(managedHome, "active.json"),
    JSON.stringify({ ...control, epoch: randomUUID() }),
  );
  assert.throws(() => next.apply(nextPlan.plan_id), code("REVISION_CONFLICT"));
  writeFileSync(join(managedHome, "active.json"), JSON.stringify(control));
  const operationFile = join(
    root,
    ".local/workspace/operations",
    `${nextPlan.operation_id}.journal.json`,
  );
  const journal = JSON.parse(readFileSync(operationFile, "utf8"));
  writeFileSync(
    operationFile,
    JSON.stringify({
      ...journal,
      managed_context: { ...journal.managed_context, home: directory() },
    }),
  );
  assert.throws(
    () => next.recover(nextPlan.plan_id, "complete"),
    code("REVISION_CONFLICT"),
  );
  const packageRoot = fixturePackage();
  const attachedRoot = directory();
  new WorkspaceInstaller(attachedRoot, {
    packageRoot,
    managedHome,
  }).initialize();
  const attachRace = randomUUID();
  native.sync("mutate", () =>
    native.reserve({
      operation_id: attachRace,
      epoch,
      kind: "synthetic-native-attach-race",
      digest: "synthetic-native-attach-reservation",
      resources: ["workspace:layout"],
    }),
  );
  let installs = 0;
  const runInstall = (source: string) => {
    installs++;
    writeFileSync(
      join(attachedRoot, ".pi/settings.json"),
      JSON.stringify({ packages: [source] }),
    );
  };
  assert.throws(
    () => attachPi(attachedRoot, { packageRoot, managedHome, runInstall }),
    code("STORE_BUSY"),
  );
  assert.equal(installs, 0);
  native.sync("settle", () => native.release(attachRace), {
    operationId: attachRace,
  });
  const attached = attachPi(attachedRoot, {
    packageRoot,
    managedHome,
    runInstall,
  });
  assert.equal(installs, 1);
  assert.equal(
    inspectPiAttachment(attachedRoot, attached.operation_id, { managedHome })
      .intent.managed_context.home,
    managedHome,
  );
  assert.throws(
    () =>
      attachPi(attachedRoot, {
        packageRoot,
        operation_id: attached.operation_id,
        runInstall,
      }),
    code("REVISION_CONFLICT"),
  );
  native.close();
  assert.throws(
    () => installer(directory(), { managedHome: "relative-home" }),
    code("VALIDATION_ERROR"),
  );
  assert.throws(
    () => installer(directory(), { managedHome: directory() }).plan(),
    code("STORE_UNAVAILABLE"),
  );
});

test("source fingerprint is independent of dist and compiled mode rejects stale runtime", () => {
  const packageRoot = fixturePackage();
  const source = getWorkspaceProduct(packageRoot);
  mkdirSync(join(packageRoot, "dist/cli"), { recursive: true });
  const compiled = "Synthetic compiled runtime bytes\n";
  writeFileSync(join(packageRoot, "dist/cli/index.js"), compiled);
  const hash = (bytes: string) =>
    createHash("sha256").update(bytes).digest("hex");
  const files = [{ path: "dist/cli/index.js", sha256: hash(compiled) }];
  assert.deepEqual(getWorkspaceProduct(packageRoot), source);
  assert.throws(
    () => getWorkspaceProduct(packageRoot, { runtime: "compiled" }),
    code("RUNTIME_UNSUPPORTED"),
  );
  writeFileSync(
    join(packageRoot, "dist/build-manifest.json"),
    JSON.stringify({
      format: 1,
      source_revision: source.revision,
      runtime_revision: "sha256:" + hash(JSON.stringify(files)),
      files,
    }),
  );
  assert.deepEqual(
    getWorkspaceProduct(packageRoot, { runtime: "compiled" }),
    source,
  );
  writeFileSync(
    join(packageRoot, "dist/cli/index.js"),
    compiled + "Changed runtime\n",
  );
  assert.throws(
    () => getWorkspaceProduct(packageRoot, { runtime: "compiled" }),
    code("REVISION_CONFLICT"),
  );
  writeFileSync(join(packageRoot, "dist/cli/index.js"), compiled);
  writeFileSync(
    join(packageRoot, "skills/zaratustra-work/SKILL.md"),
    "Changed source instructions\n",
  );
  assert.throws(
    () => getWorkspaceProduct(packageRoot, { runtime: "compiled" }),
    code("REVISION_CONFLICT"),
  );
});

test("owner guidance with invalid UTF8 or UTF16 bytes is preserved before integration", () => {
  const invalid = [
    Buffer.from([0xc3, 0x28]),
    Buffer.concat([
      Buffer.from([0xff, 0xfe]),
      Buffer.from("Owner guidance", "utf16le"),
    ]),
    Buffer.from("Owner guidance", "utf16le"),
  ];
  for (const bytes of invalid) {
    const root = directory();
    writeFileSync(join(root, "AGENTS.md"), bytes);
    assert.throws(() => installer(root).initialize(), code("VALIDATION_ERROR"));
    assert.deepEqual(readFileSync(join(root, "AGENTS.md")), bytes);
    assert.equal(readWorkspaceManifest(root), undefined);
    assert.equal(existsSync(join(root, "instructions/system.md")), false);
  }
});

test("a torn staged technical journal preserves valid recovery metadata and original receipt", () => {
  const root = directory();
  let stopped = false;
  const interrupted = installer(root, {
    fault(point, path, temporaryPath) {
      if (
        point !== "before_internal_publish" ||
        !path?.endsWith(".journal.json") ||
        stopped
      )
        return;
      const staged = JSON.parse(readFileSync(temporaryPath!, "utf8"));
      if (staged.state !== "committed") return;
      stopped = true;
      writeFileSync(temporaryPath!, '{"format":1,"state":');
      throw new Error("Synthetic torn staged journal");
    },
  });
  const plan = interrupted.plan();
  assert.throws(
    () => interrupted.apply(plan.plan_id),
    /Synthetic torn staged journal/,
  );
  const resumed = installer(root);
  const observed = resumed.inspectOperation(plan.plan_id);
  assert.equal(observed.journal.state, "publishing");
  assert.equal(observed.receipt!.state, "committed");
  assert.equal(observed.manifest_state, "after");
  const originalReceipt = observed.receipt;
  const recovered = resumed.recover(plan.plan_id, "complete");
  assert.deepEqual(recovered, originalReceipt);
  assert.equal(
    resumed.inspectOperation(plan.plan_id).journal.state,
    "committed",
  );
  assert.equal(inspectWorkspace(root).pending_operations.length, 0);
  assert.equal(inspectWorkspace(root).state, "current");
  assert.deepEqual(resumed.apply(plan.plan_id), originalReceipt);
});

test("a torn target manifest remains inspectable through its original plan without guessing recovery", () => {
  const root = directory();
  installer(root).initialize();
  const partial = Buffer.from('{"layout_format":1,"installation_id":');
  const interrupted = installer(root, {
    product: nextProduct,
    fault(point) {
      if (point === "before_manifest") {
        writeFileSync(join(root, "zaratustra.json"), partial);
        throw new Error("Synthetic torn target manifest");
      }
    },
  });
  const plan = interrupted.plan();
  assert.throws(
    () => interrupted.apply(plan.plan_id),
    /Synthetic torn target manifest/,
  );
  const resumed = installer(root, { product: nextProduct });
  const observed = resumed.inspectOperation(plan.plan_id);
  assert.equal(observed.manifest_state, "conflict");
  assert.equal(observed.journal.state, "publishing");
  assert.ok(observed.plan.before_manifest);
  for (const action of ["complete", "rollback"] as const) {
    assert.throws(
      () => resumed.recover(plan.plan_id, action),
      code("REVISION_CONFLICT"),
    );
    assert.deepEqual(readFileSync(join(root, "zaratustra.json")), partial);
  }
  assert.equal(
    resumed.inspectOperation(plan.plan_id).journal.state,
    "publishing",
  );
});

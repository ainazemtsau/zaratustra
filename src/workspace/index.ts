import { randomUUID } from "node:crypto";
import {
  existsSync,
  lstatSync,
  mkdirSync,
  readFileSync,
  readdirSync,
  realpathSync,
} from "node:fs";
import {
  basename,
  delimiter,
  dirname,
  isAbsolute,
  join,
  resolve,
} from "node:path";
import { fileURLToPath } from "node:url";
import { spawnSync } from "node:child_process";
import { createRequire } from "node:module";
import { z } from "zod";
import {
  Coordination,
  readControl,
  safePath,
  within,
} from "../storage/index.ts";
import {
  InstallationJournalSchema,
  InstallationPlanSchema,
  InstallationReceiptSchema,
  ManagedWorkspaceContextSchema,
  PiAttachmentIntentSchema,
  WorkspaceManifestSchema,
  WorkspaceProductSchema,
  type InstallationPlan,
  type InstallationReceipt,
  type ManagedWorkspaceContext,
  type WorkspaceManifest,
  type WorkspaceProduct,
} from "./contracts.ts";
import {
  canonicalWorkspaceValue,
  ensureWorkspaceDirectory,
  observeWorkspaceFile,
  publishWorkspaceFile,
  workspaceError,
  workspaceHash,
  workspaceIdentity,
  workspaceTarget,
  workspaceUTF8,
  writeWorkspaceJSON,
} from "./files.ts";
import { cleanProductSourceRevision, getWorkspaceProduct } from "./product.ts";
import { ROOT_GUIDANCE, workspaceTemplates } from "./templates.ts";

export * from "./contracts.ts";
export { getWorkspaceProduct } from "./product.ts";

export const workspacePackageRoot = resolve(
  fileURLToPath(new URL("../..", import.meta.url)),
);
const stateRoot = ".local/workspace";
const manifestPath = "zaratustra.json";
const ownerDirectories = [
  ".pi",
  "skills/personal",
  "activities",
  "memory",
  ".local/imports",
  ".local/output",
  ".local/backups",
];

export function readWorkspaceManifest(root: string) {
  root = resolve(root);
  const observed = observeWorkspaceFile(root, manifestPath);
  return observed.bytes
    ? WorkspaceManifestSchema.parse(JSON.parse(observed.bytes.toString("utf8")))
    : undefined;
}

function manifestBytes(manifest: WorkspaceManifest) {
  return Buffer.from(JSON.stringify(manifest, null, 2) + "\n");
}

function planDigest(plan: Omit<InstallationPlan, "plan_id">) {
  return workspaceHash(canonicalWorkspaceValue(plan));
}

function planOperation(planId: string) {
  if (!/^[a-f0-9-]{36}\.[a-f0-9]{64}$/.test(planId))
    workspaceError(
      "VALIDATION_ERROR",
      "Use the exact inspected installation plan ID.",
    );
  return planId.split(".")[0];
}

function operationPath(operationId: string, extension: string) {
  return `${stateRoot}/operations/${operationId}.${extension}.json`;
}

function jsonFile(root: string, path: string): unknown {
  const observed = observeWorkspaceFile(root, path, 8 * 1024 * 1024);
  if (!observed.bytes)
    workspaceError(
      "REFERENCE_NOT_FOUND",
      "Installation operation was not found.",
    );
  return JSON.parse(observed.bytes.toString("utf8"));
}

function readPlan(root: string, planId: string): InstallationPlan {
  const id = planOperation(planId);
  const plan = InstallationPlanSchema.parse(
    jsonFile(root, operationPath(id, "plan")),
  );
  const { plan_id: recordedId, ...payload } = plan;
  if (
    recordedId !== planId ||
    `${id}.${planDigest(payload)}` !== planId ||
    plan.root !== resolve(root)
  )
    workspaceError(
      "REVISION_CONFLICT",
      "Installation plan identity or bytes changed.",
    );
  return plan;
}

function currentHash(root: string, path: string) {
  return observeWorkspaceFile(root, path).hash;
}

function beforeHash(plan: InstallationPlan) {
  return plan.before_manifest === null
    ? null
    : workspaceHash(Buffer.from(plan.before_manifest, "base64"));
}

/** The caller selects an existing trusted alternate home explicitly. */
export function readManagedWorkspaceContext(
  root: string,
  managedHome?: string,
): ManagedWorkspaceContext {
  if (managedHome !== undefined && !isAbsolute(managedHome))
    workspaceError(
      "VALIDATION_ERROR",
      "The trusted managed home must be an explicit absolute path.",
    );
  const requested = managedHome ?? resolve(root, ".local/memory");
  safePath(requested, requested, true);
  const home = existsSync(requested)
    ? realpathSync(requested)
    : resolve(requested);
  if (existsSync(home) && !lstatSync(home).isDirectory())
    workspaceError(
      "STORE_UNAVAILABLE",
      "The managed home must be an ordinary directory.",
    );
  const observed = observeWorkspaceFile(home, "active.json");
  if (!observed.bytes) {
    if (
      managedHome !== undefined ||
      (existsSync(home) && readdirSync(home).length > 0)
    )
      workspaceError(
        "STORE_UNAVAILABLE",
        "The selected managed home has no recognized active control. Inspect it without initializing or resetting it.",
      );
    return ManagedWorkspaceContextSchema.parse({
      state: "absent",
      home,
      home_identity: existsSync(home) ? workspaceIdentity(home) : null,
    });
  }
  let control: ReturnType<typeof readControl>;
  try {
    control = readControl(home);
  } catch {
    workspaceError(
      "STORE_UNAVAILABLE",
      "The selected managed control is unsupported or invalid. Preserve it for inspection.",
    );
  }
  if (!control?.coordination_id)
    workspaceError(
      "STORE_UNAVAILABLE",
      "The selected managed control has no stable coordination identity.",
    );
  if (observeWorkspaceFile(home, "active.json").hash !== observed.hash)
    workspaceError(
      "REVISION_CONFLICT",
      "The managed control changed during context capture.",
    );
  return ManagedWorkspaceContextSchema.parse({
    state: "managed",
    home,
    home_identity: workspaceIdentity(home),
    workspace_id: control.workspace_id,
    coordination_id: control.coordination_id,
    epoch: control.epoch,
    control_hash: observed.hash,
  });
}

export interface WorkspaceInstallerOptions {
  packageRoot?: string;
  product?: WorkspaceProduct;
  managedHome?: string;
  fault?: (point: string, path?: string, temporaryPath?: string) => void;
}

export class WorkspaceInstaller {
  readonly root: string;
  readonly packageRoot: string;
  readonly product: WorkspaceProduct;
  readonly managedHome: string | undefined;
  private readonly fault: NonNullable<WorkspaceInstallerOptions["fault"]>;

  constructor(root: string, options: WorkspaceInstallerOptions = {}) {
    if (options.managedHome !== undefined && !isAbsolute(options.managedHome))
      workspaceError(
        "VALIDATION_ERROR",
        "The trusted managed home must be an explicit absolute path.",
      );
    this.managedHome =
      options.managedHome === undefined
        ? undefined
        : resolve(options.managedHome);
    this.root = resolve(root);
    safePath(this.root, this.root, true);
    mkdirSync(this.root, { recursive: true });
    safePath(this.root, this.root, true);
    if (!lstatSync(this.root).isDirectory())
      workspaceError(
        "PERMISSION_DENIED",
        "Workspace root must be a directory.",
      );
    this.packageRoot = options.packageRoot ?? workspacePackageRoot;
    this.product = WorkspaceProductSchema.parse(
      options.product ?? getWorkspaceProduct(this.packageRoot),
    );
    this.fault = options.fault ?? (() => {});
  }

  private writeJournal(
    plan: InstallationPlan,
    state: z.infer<typeof InstallationJournalSchema>["state"],
    error?: string,
  ) {
    writeWorkspaceJSON(
      this.root,
      operationPath(plan.operation_id, "journal"),
      InstallationJournalSchema.parse({
        format: 1,
        operation_id: plan.operation_id,
        plan_id: plan.plan_id,
        managed_context: plan.managed_context,
        state,
        updated_at: new Date().toISOString(),
        ...(error ? { error } : {}),
      }),
      { fault: this.fault },
    );
  }

  private coordinated<T>(
    plan: InstallationPlan,
    recover: boolean,
    callback: () => T,
  ): T {
    const managed = this.requireManagedContext(plan);
    const home = ensureWorkspaceDirectory(
      this.root,
      `${stateRoot}/coordination`,
    );
    const local = new Coordination(home, "workspace-" + randomUUID(), {
      create: true,
    });
    const coordinators = [local];
    const epochs = new Map<Coordination, string>([
      [local, plan.manifest.installation_id],
    ]);
    const reserved = new Set<Coordination>();
    try {
      if (managed.state === "managed") {
        const native = new Coordination(
          managed.home,
          "workspace-" + randomUUID(),
          {
            expectedId: managed.coordination_id,
            create: false,
          },
        );
        coordinators.push(native);
        epochs.set(native, managed.epoch);
      }
      for (const coordinator of coordinators) {
        coordinator.sync("mutate", () => {
          const operation = coordinator.operation(plan.operation_id);
          if (recover && operation && operation.status !== "settled") {
            coordinator.adopt(plan.operation_id);
          } else if (recover && operation?.status === "settled") {
            return;
          } else {
            coordinator.reserve({
              operation_id: plan.operation_id,
              epoch: epochs.get(coordinator)!,
              kind: "workspace-installation",
              digest: plan.plan_id,
              resources: ["workspace:layout"],
            });
          }
          reserved.add(coordinator);
        });
      }
      this.requireManagedContext(plan);
      const result = callback();
      for (const coordinator of [...coordinators].reverse())
        if (reserved.has(coordinator))
          coordinator.sync(
            "settle",
            () => coordinator.release(plan.operation_id),
            {
              operationId: plan.operation_id,
            },
          );
      return result;
    } catch (error) {
      const journal = InstallationJournalSchema.parse(
        jsonFile(this.root, operationPath(plan.operation_id, "journal")),
      );
      if (journal.state === "planned") {
        this.writeJournal(plan, "refused", (error as Error).message);
        for (const coordinator of [...coordinators].reverse())
          if (reserved.has(coordinator))
            coordinator.sync(
              "settle",
              () => coordinator.release(plan.operation_id),
              {
                operationId: plan.operation_id,
              },
            );
      }
      if (journal.state === "committed" || journal.state === "rolled_back") {
        for (const coordinator of [...coordinators].reverse())
          if (reserved.has(coordinator))
            coordinator.sync(
              "settle",
              () => coordinator.release(plan.operation_id),
              {
                operationId: plan.operation_id,
              },
            );
      }
      throw error;
    } finally {
      for (const coordinator of coordinators.reverse())
        coordinator.close({ poisonUnknown: true });
    }
  }

  plan(): InstallationPlan {
    const inspection = inspectWorkspace(this.root);
    if (inspection.pending_attachments.length)
      workspaceError(
        "STORE_BUSY",
        "Inspect and settle the original Pi attachment before changing the installation.",
      );
    if (
      inspection.pending_operations.some(
        (operation) => operation.state !== "planned",
      )
    )
      workspaceError(
        "STORE_BUSY",
        "Inspect and reconcile the pending installation operation first.",
      );
    const before = observeWorkspaceFile(this.root, manifestPath);
    const existing = readWorkspaceManifest(this.root);
    const manifest: WorkspaceManifest = {
      layout_format: 1,
      installation_id: existing?.installation_id ?? randomUUID(),
      product: this.product,
      managed_files: [],
      activities: existing?.activities ?? [],
      personal_skills: existing?.personal_skills ?? [],
      adapters: existing?.adapters ?? ["codex", "pi"],
    };
    const templates = workspaceTemplates(
      manifest,
      (name) =>
        workspaceUTF8(
          readFileSync(join(this.packageRoot, "skills", name, "SKILL.md")),
          "Product skill",
        ),
      workspaceHash,
      (path) => {
        const source = observeWorkspaceFile(this.root, path, 64000);
        if (!source.bytes)
          workspaceError(
            "REFERENCE_NOT_FOUND",
            "A configured personal skill is missing.",
          );
        return workspaceUTF8(source.bytes, "Personal skill entry");
      },
    );
    const entries: InstallationPlan["entries"] = [];
    for (const template of templates) {
      const current = observeWorkspaceFile(this.root, template.path);
      if (template.kind === "owner" && current.bytes) continue;
      const recorded = existing?.managed_files.find(
        (file) => file.path === template.path,
      );
      const conflict =
        current.bytes !== null && current.hash !== recorded?.sha256;
      let text = template.text;
      if (template.path === "AGENTS.md" && conflict) {
        const original = workspaceUTF8(current.bytes!, "Owner root guidance");
        const start = "<!-- zaratustra-workspace-guidance -->";
        const end = "<!-- zaratustra-workspace-guidance:end -->";
        const startOffset = original.indexOf(start);
        const endOffset = original.indexOf(end);
        text =
          startOffset >= 0 && endOffset > startOffset
            ? original.slice(0, startOffset) +
              start +
              "\n" +
              ROOT_GUIDANCE +
              end +
              original.slice(endOffset + end.length)
            : original + "\n\n" + start + "\n" + ROOT_GUIDANCE + end + "\n";
      }
      const after = Buffer.from(text);
      if (template.kind !== "owner")
        manifest.managed_files.push({
          path: template.path,
          sha256: workspaceHash(after),
          kind: template.kind,
        });
      if (current.hash === workspaceHash(after) && !conflict) continue;
      entries.push({
        path: template.path,
        kind: template.kind,
        before: current.bytes?.toString("base64") ?? null,
        before_hash: current.hash,
        before_identity: current.identity,
        after: after.toString("base64"),
        after_hash: workspaceHash(after),
        conflict,
        reason: conflict
          ? "Existing owner or modified managed file requires an exact replacement decision."
          : current.bytes
            ? "Product-managed update."
            : "Create missing workspace file.",
      });
    }
    const desired = new Set(templates.map((template) => template.path));
    for (const obsolete of existing?.managed_files ?? []) {
      if (desired.has(obsolete.path)) continue;
      const current = observeWorkspaceFile(this.root, obsolete.path);
      if (!current.bytes) continue;
      entries.push({
        path: obsolete.path,
        kind: obsolete.kind,
        before: current.bytes.toString("base64"),
        before_hash: current.hash,
        before_identity: current.identity,
        after: null,
        after_hash: null,
        conflict: current.hash !== obsolete.sha256,
        reason:
          "Retire an obsolete generated or system file after exact review.",
      });
    }
    const paths = entries.map((entry) => entry.path.toLowerCase());
    if (new Set(paths).size !== paths.length)
      workspaceError(
        "VALIDATION_ERROR",
        "Installation contains colliding generated paths.",
      );
    manifest.managed_files.sort((a, b) => a.path.localeCompare(b.path));
    const operationId = randomUUID();
    const payload = {
      format: 1 as const,
      operation_id: operationId,
      root: this.root,
      root_identity: workspaceIdentity(this.root),
      created_at: new Date().toISOString(),
      product: this.product,
      managed_context: readManagedWorkspaceContext(this.root, this.managedHome),
      before_manifest: before.bytes?.toString("base64") ?? null,
      manifest: WorkspaceManifestSchema.parse(manifest),
      entries,
    };
    const plan = InstallationPlanSchema.parse({
      ...payload,
      plan_id: `${operationId}.${planDigest(payload)}`,
    });
    ensureWorkspaceDirectory(this.root, `${stateRoot}/operations`);
    writeWorkspaceJSON(this.root, operationPath(operationId, "plan"), plan);
    this.writeJournal(plan, "planned");
    return plan;
  }

  initialize() {
    const current = readWorkspaceManifest(this.root);
    const plan = this.plan();
    if (plan.entries.some((entry) => entry.conflict))
      return {
        state: "pending" as const,
        plan,
        conflicts: plan.entries.filter((entry) => entry.conflict),
      };
    if (
      current &&
      plan.entries.length === 0 &&
      canonicalWorkspaceValue(current) ===
        canonicalWorkspaceValue(plan.manifest)
    ) {
      this.writeJournal(plan, "rolled_back");
      return {
        state: "unchanged" as const,
        installation_id: current.installation_id,
      };
    }
    return { state: "committed" as const, receipt: this.apply(plan.plan_id) };
  }

  private guardRoot(plan: InstallationPlan) {
    safePath(this.root, this.root, true);
    if (workspaceIdentity(this.root) !== plan.root_identity)
      workspaceError("REVISION_CONFLICT", "Workspace root identity changed.");
  }

  private requireManagedContext(plan: InstallationPlan) {
    const current = readManagedWorkspaceContext(this.root, this.managedHome);
    if (
      canonicalWorkspaceValue(current) !==
      canonicalWorkspaceValue(plan.managed_context)
    )
      workspaceError(
        "REVISION_CONFLICT",
        "The selected managed home, identity or epoch differs from the installation plan.",
      );
    return current;
  }

  private guardBefore(plan: InstallationPlan) {
    this.guardRoot(plan);
    this.requireManagedContext(plan);
    if (currentHash(this.root, manifestPath) !== beforeHash(plan))
      workspaceError(
        "REVISION_CONFLICT",
        "Workspace manifest changed after planning.",
      );
    for (const entry of plan.entries) {
      const current = observeWorkspaceFile(this.root, entry.path);
      if (
        current.hash !== entry.before_hash ||
        current.identity !== entry.before_identity
      )
        workspaceError(
          "REVISION_CONFLICT",
          `Planned target changed: ${entry.path}`,
        );
    }
  }

  private finish(plan: InstallationPlan, state: "committed" | "rolled_back") {
    const receipt = InstallationReceiptSchema.parse({
      format: 1,
      operation_id: plan.operation_id,
      plan_id: plan.plan_id,
      installation_id: plan.manifest.installation_id,
      product: plan.product,
      state,
      completed_at: new Date().toISOString(),
    });
    writeWorkspaceJSON(
      this.root,
      operationPath(plan.operation_id, "receipt"),
      receipt,
    );
    this.writeJournal(plan, state);
    return receipt;
  }

  apply(planId: string): InstallationReceipt {
    const plan = readPlan(this.root, planId);
    this.requireManagedContext(plan);
    const receiptPath = operationPath(plan.operation_id, "receipt");
    if (observeWorkspaceFile(this.root, receiptPath).bytes)
      return this.coordinated(plan, true, () =>
        this.settleReceipt(
          plan,
          InstallationReceiptSchema.parse(jsonFile(this.root, receiptPath)),
        ),
      );
    const journal = InstallationJournalSchema.parse(
      jsonFile(this.root, operationPath(plan.operation_id, "journal")),
    );
    if (
      canonicalWorkspaceValue(journal.managed_context) !==
      canonicalWorkspaceValue(plan.managed_context)
    )
      workspaceError(
        "REVISION_CONFLICT",
        "The installation journal's managed context differs from its bound plan.",
      );
    if (journal.state !== "planned")
      workspaceError(
        "STORE_BUSY",
        "Inspect the original operation and recover it before any repeat.",
      );
    if (
      canonicalWorkspaceValue(plan.product) !==
      canonicalWorkspaceValue(this.product)
    )
      workspaceError(
        "REVISION_CONFLICT",
        "The product changed after planning.",
      );
    return this.coordinated(plan, false, () => {
      this.guardBefore(plan);
      for (const directory of ownerDirectories)
        ensureWorkspaceDirectory(this.root, directory);
      this.writeJournal(plan, "publishing");
      this.fault("before_publish");
      for (const entry of plan.entries) {
        const current = observeWorkspaceFile(this.root, entry.path);
        if (
          current.hash !== entry.before_hash ||
          current.identity !== entry.before_identity
        )
          workspaceError(
            "REVISION_CONFLICT",
            `Target changed before publication: ${entry.path}`,
          );
        publishWorkspaceFile(
          this.root,
          entry.path,
          entry.after === null ? null : Buffer.from(entry.after, "base64"),
        );
        if (currentHash(this.root, entry.path) !== entry.after_hash)
          workspaceError(
            "REVISION_CONFLICT",
            `Target differs after publication: ${entry.path}`,
          );
        this.fault("after_file", entry.path);
      }
      this.verifyAfter(plan);
      this.fault("before_manifest");
      publishWorkspaceFile(
        this.root,
        manifestPath,
        manifestBytes(plan.manifest),
      );
      this.fault("after_manifest");
      const receipt = this.finish(plan, "committed");
      this.fault("after_receipt");
      return receipt;
    });
  }

  private verifyAfter(plan: InstallationPlan) {
    this.guardRoot(plan);
    this.requireManagedContext(plan);
    for (const file of plan.manifest.managed_files)
      if (currentHash(this.root, file.path) !== file.sha256)
        workspaceError(
          "REVISION_CONFLICT",
          `Installed file differs: ${file.path}`,
        );
    for (const entry of plan.entries)
      if (currentHash(this.root, entry.path) !== entry.after_hash)
        workspaceError(
          "REVISION_CONFLICT",
          `Publication result differs: ${entry.path}`,
        );
  }

  private settleReceipt(plan: InstallationPlan, receipt: InstallationReceipt) {
    if (
      receipt.operation_id !== plan.operation_id ||
      receipt.plan_id !== plan.plan_id ||
      receipt.installation_id !== plan.manifest.installation_id ||
      canonicalWorkspaceValue(receipt.product) !==
        canonicalWorkspaceValue(plan.product)
    )
      workspaceError(
        "REVISION_CONFLICT",
        "The installation receipt differs from its exact original plan.",
      );
    const journal = InstallationJournalSchema.parse(
      jsonFile(this.root, operationPath(plan.operation_id, "journal")),
    );
    if (
      journal.plan_id !== plan.plan_id ||
      journal.operation_id !== plan.operation_id ||
      canonicalWorkspaceValue(journal.managed_context) !==
        canonicalWorkspaceValue(plan.managed_context)
    )
      workspaceError(
        "REVISION_CONFLICT",
        "The installation journal differs from its exact original plan.",
      );
    if (journal.state !== receipt.state) this.writeJournal(plan, receipt.state);
    return receipt;
  }

  inspectOperation(planId: string) {
    const plan = readPlan(this.root, planId);
    const journal = InstallationJournalSchema.parse(
      jsonFile(this.root, operationPath(plan.operation_id, "journal")),
    );
    if (
      canonicalWorkspaceValue(journal.managed_context) !==
      canonicalWorkspaceValue(plan.managed_context)
    )
      workspaceError(
        "REVISION_CONFLICT",
        "The installation journal's managed context differs from its bound plan.",
      );
    const targets = plan.entries.map((entry) => {
      const hash = currentHash(this.root, entry.path);
      return {
        path: entry.path,
        state:
          hash === entry.after_hash
            ? "after"
            : hash === entry.before_hash
              ? "before"
              : "conflict",
        observed_hash: hash,
      };
    });
    const currentManifestHash = currentHash(this.root, manifestPath);
    const receiptPath = operationPath(plan.operation_id, "receipt");
    return {
      plan,
      journal,
      targets,
      manifest_state:
        currentManifestHash === workspaceHash(manifestBytes(plan.manifest))
          ? "after"
          : currentManifestHash === beforeHash(plan)
            ? "before"
            : "conflict",
      receipt: observeWorkspaceFile(this.root, receiptPath).bytes
        ? InstallationReceiptSchema.parse(jsonFile(this.root, receiptPath))
        : null,
    };
  }

  recover(planId: string, action: "complete" | "rollback") {
    const inspected = this.inspectOperation(planId);
    this.requireManagedContext(inspected.plan);
    if (inspected.journal.state === "refused")
      workspaceError(
        "REVISION_CONFLICT",
        "The operation was refused before publication. Create a new reviewed plan.",
      );
    if (inspected.receipt) {
      const wanted = action === "complete" ? "committed" : "rolled_back";
      if (inspected.receipt.state !== wanted)
        workspaceError(
          "REVISION_CONFLICT",
          "The operation is already settled. Create a new reviewed plan for another change.",
        );
      return this.coordinated(inspected.plan, true, () =>
        this.settleReceipt(inspected.plan, inspected.receipt!),
      );
    }
    const plan = inspected.plan;
    return this.coordinated(plan, true, () => {
      this.guardRoot(plan);
      const actual = this.inspectOperation(planId);
      if (
        actual.manifest_state === "conflict" ||
        actual.targets.some((target) => target.state === "conflict")
      )
        workspaceError(
          "REVISION_CONFLICT",
          "Recovery encountered later edits; preserve them for a new decision.",
        );
      if (action === "complete") {
        this.writeJournal(plan, "publishing");
        for (const entry of plan.entries) {
          const observed = currentHash(this.root, entry.path);
          if (observed === entry.after_hash) continue;
          if (observed !== entry.before_hash)
            workspaceError(
              "REVISION_CONFLICT",
              "Recovery target changed after inspection.",
            );
          publishWorkspaceFile(
            this.root,
            entry.path,
            entry.after === null ? null : Buffer.from(entry.after, "base64"),
          );
        }
        this.verifyAfter(plan);
        publishWorkspaceFile(
          this.root,
          manifestPath,
          manifestBytes(plan.manifest),
        );
        return this.finish(plan, "committed");
      }
      this.writeJournal(plan, "compensating");
      for (const entry of [...plan.entries].reverse()) {
        const observed = currentHash(this.root, entry.path);
        if (observed === entry.before_hash) continue;
        if (observed !== entry.after_hash)
          workspaceError(
            "REVISION_CONFLICT",
            "Compensation target changed after inspection.",
          );
        publishWorkspaceFile(
          this.root,
          entry.path,
          entry.before === null ? null : Buffer.from(entry.before, "base64"),
        );
      }
      const manifestHash = currentHash(this.root, manifestPath);
      if (manifestHash !== beforeHash(plan)) {
        if (manifestHash !== workspaceHash(manifestBytes(plan.manifest)))
          workspaceError("REVISION_CONFLICT", "Compensation manifest changed.");
        publishWorkspaceFile(
          this.root,
          manifestPath,
          plan.before_manifest === null
            ? null
            : Buffer.from(plan.before_manifest, "base64"),
        );
      }
      return this.finish(plan, "rolled_back");
    });
  }
}

export function inspectWorkspace(root: string) {
  root = resolve(root);
  const manifest = readWorkspaceManifest(root);
  const files = (manifest?.managed_files ?? []).map((file) => ({
    path: file.path,
    expected_hash: file.sha256,
    observed_hash: currentHash(root, file.path),
  }));
  const operations = workspaceTarget(root, `${stateRoot}/operations`);
  const pending: z.infer<typeof InstallationJournalSchema>[] = [];
  const coordinationHome = workspaceTarget(root, `${stateRoot}/coordination`);
  const unsettled = new Set<string>();
  if (existsSync(join(coordinationHome, "coordination.sqlite"))) {
    const coordinator = new Coordination(
      coordinationHome,
      "workspace-inspect-" + randomUUID(),
      { create: false },
    );
    try {
      for (const operation of coordinator.sync("read", () =>
        coordinator.pending(),
      ))
        unsettled.add(operation.operation_id);
    } finally {
      coordinator.close();
    }
  }
  if (existsSync(operations)) {
    for (const name of readdirSync(operations).filter((name) =>
      name.endsWith(".journal.json"),
    )) {
      const journal = InstallationJournalSchema.parse(
        jsonFile(root, `${stateRoot}/operations/${name}`),
      );
      if (
        unsettled.has(journal.operation_id) ||
        !["committed", "rolled_back", "refused"].includes(journal.state)
      )
        pending.push(journal);
    }
  }
  return {
    root,
    manifest,
    state: !manifest
      ? "uninitialized"
      : files.some((file) => file.expected_hash !== file.observed_hash)
        ? "drift"
        : "current",
    files,
    pending_operations: pending,
    pending_attachments: readAttachmentIntents(root).filter(
      (intent) =>
        intent.state !== "confirmed" || unsettled.has(intent.operation_id),
    ),
    capabilities: {
      ordinary_file_workflows: !!manifest,
      managed_core: "requires-qualified-adapter",
      external_editor_publication: "single-writer-window",
    },
  };
}

export interface WorkspaceGuidanceOptions {
  activity_id?: string;
  core_activity_id?: string;
  product_revision?: string;
}

export function loadWorkspaceGuidance(
  root: string,
  options: WorkspaceGuidanceOptions = {},
) {
  const manifest = readWorkspaceManifest(root);
  if (!manifest) return undefined;
  if (
    options.product_revision &&
    manifest.product.revision !== options.product_revision
  )
    workspaceError(
      "REVISION_CONFLICT",
      "Installed workspace guidance and runtime product revision differ.",
    );
  const readGuidance = (path: string) => {
    const observed = observeWorkspaceFile(root, path, 64000);
    if (!observed.bytes)
      workspaceError(
        "REFERENCE_NOT_FOUND",
        `Workspace guidance is missing: ${path}`,
      );
    return {
      path,
      text: workspaceUTF8(observed.bytes, "Workspace guidance"),
      sha256: observed.hash!,
    };
  };
  const system = readGuidance("instructions/system.md");
  const expected = manifest.managed_files.find(
    (file) => file.path === system.path,
  );
  if (!expected || expected.sha256 !== system.sha256)
    workspaceError(
      "REVISION_CONFLICT",
      "System guidance differs from its installed version.",
    );
  const workspace = readGuidance("instructions/workspace.md");
  const warnings: string[] = [];
  let activity: {
    path: string;
    text: string;
    sha256: string;
    key: string;
    core_ref?: { id: string; revision?: number };
  } | null = null;
  if (options.activity_id || options.core_activity_id) {
    const matches = manifest.activities.filter((item) =>
      options.core_activity_id
        ? item.core_ref?.id === options.core_activity_id
        : item.key === options.activity_id,
    );
    if (matches.length !== 1)
      warnings.push(
        "Selected Activity guidance has no unique explicit binding.",
      );
    else {
      const binding = matches[0];
      try {
        if (!/^activities\/.+\.md$/i.test(binding.guidance_path))
          workspaceError(
            "PERMISSION_DENIED",
            "Activity guidance must be Markdown below activities.",
          );
        activity = {
          ...readGuidance(binding.guidance_path),
          key: binding.key,
          ...(binding.core_ref ? { core_ref: binding.core_ref } : {}),
        };
      } catch (error) {
        warnings.push(
          `Selected Activity guidance is unavailable: ${(error as Error).message}`,
        );
      }
    }
  }
  return { manifest, system, workspace, activity, warnings };
}

export interface AttachPiOptions {
  source?: string;
  packageRoot?: string;
  managedHome?: string;
  runInstall?: (source: string, cwd: string) => void;
  operation_id?: string;
  fault?: (point: string) => void;
}

function attachmentPath(operationId: string) {
  z.string().uuid().parse(operationId);
  return `${stateRoot}/attachments/${operationId}.json`;
}

function readAttachmentIntents(root: string) {
  const directory = workspaceTarget(root, `${stateRoot}/attachments`);
  if (!existsSync(directory)) return [];
  return readdirSync(directory)
    .filter((name) => /^[a-f0-9-]{36}\.json$/.test(name))
    .map((name) =>
      PiAttachmentIntentSchema.parse(
        jsonFile(root, `${stateRoot}/attachments/${name}`),
      ),
    );
}

export function inspectPiAttachment(
  root: string,
  operationId: string,
  options: { managedHome?: string } = {},
) {
  const intent = PiAttachmentIntentSchema.parse(
    jsonFile(root, attachmentPath(operationId)),
  );
  const managed = readManagedWorkspaceContext(root, options.managedHome);
  return {
    intent,
    observed_settings_hash: currentHash(root, ".pi/settings.json"),
    managed_context: managed,
    managed_context_matches:
      canonicalWorkspaceValue(managed) ===
      canonicalWorkspaceValue(intent.managed_context),
  };
}

const piPackage = "@earendil-works/pi-coding-agent";

function declaredPiCLI(packageRoot: string) {
  try {
    const root = realpathSync(packageRoot);
    const metadata = JSON.parse(
      readFileSync(join(root, "package.json"), "utf8"),
    ) as { name?: string; bin?: { pi?: string } };
    const bin = metadata?.bin?.pi;
    if (
      metadata?.name !== piPackage ||
      typeof bin !== "string" ||
      !bin ||
      isAbsolute(bin)
    )
      return;
    const path = resolve(root, bin);
    if (!within(root, path)) return;
    const actual = realpathSync(path);
    if (within(root, actual) && lstatSync(actual).isFile()) return actual;
  } catch {
    // A missing or unusable installation leaves other candidates available.
  }
}

function nativePiCLI(packageRoot: string) {
  for (const directory of (process.env.PATH ?? "").split(delimiter)) {
    if (!isAbsolute(directory)) continue;
    if (process.platform === "win32") {
      if (!existsSync(join(directory, "pi.cmd"))) continue;
      const modules =
        basename(directory) === ".bin"
          ? dirname(directory)
          : join(directory, "node_modules");
      const cli = declaredPiCLI(join(modules, piPackage));
      if (cli) return cli;
      continue;
    }
    let executable: string;
    try {
      executable = realpathSync(join(directory, "pi"));
    } catch {
      continue;
    }
    let candidate = dirname(executable);
    while (dirname(candidate) !== candidate) {
      if (existsSync(join(candidate, "package.json"))) {
        if (declaredPiCLI(candidate) === executable) return executable;
        break;
      }
      candidate = dirname(candidate);
    }
  }
  // Resolve npm package directories without loading the import-only SDK.
  const requireFromPackage = createRequire(join(packageRoot, "package.json"));
  for (const directory of requireFromPackage.resolve.paths(piPackage) ?? []) {
    const cli = declaredPiCLI(join(directory, piPackage));
    if (cli) return cli;
  }
  return workspaceError(
    "RUNTIME_UNSUPPORTED",
    "Pi CLI not found. Install @earendil-works/pi-coding-agent on PATH or as an npm peer before attaching its adapter.",
  );
}

function piSourceKey(source: string, root: string) {
  if (source.startsWith("git:") || source.startsWith("npm:")) return source;
  return resolve(root, ".pi", source).toLowerCase();
}

const PiPackageSchema = z.union([
  z.string(),
  z.object({ source: z.string() }).passthrough(),
]);
type PiPackage = z.infer<typeof PiPackageSchema>;

function piPackages(settings: Record<string, unknown>) {
  return z.array(PiPackageSchema).parse(settings.packages ?? []);
}

function piPackageSource(entry: PiPackage) {
  return typeof entry === "string" ? entry : entry.source;
}

function assertPortablePiFilter(entry: PiPackage) {
  if (
    typeof entry === "object" &&
    ((entry.autoload !== undefined && entry.autoload !== true) ||
      (entry.skills !== undefined &&
        (!Array.isArray(entry.skills) || entry.skills.length !== 0)))
  )
    workspaceError(
      "REVISION_CONFLICT",
      "The product package has an explicit owner skill filter or autoload delta. Review that filter before selecting shared workspace skills.",
    );
}

function ownPiPackage(
  settings: Record<string, unknown>,
  root: string,
  source: string,
) {
  const own = piPackages(settings).filter(
    (entry) =>
      piSourceKey(piPackageSource(entry), root) === piSourceKey(source, root),
  );
  if (own.length > 1)
    workspaceError(
      "REVISION_CONFLICT",
      "Several project package entries identify this product; review their filters before attachment.",
    );
  if (own[0]) assertPortablePiFilter(own[0]);
  return own[0];
}

function assertPiSettingsPreserved(
  before: Record<string, unknown>,
  after: Record<string, unknown>,
  root: string,
  source: string,
) {
  for (const [key, value] of Object.entries(before)) {
    if (
      key !== "packages" &&
      canonicalWorkspaceValue(after[key]) !== canonicalWorkspaceValue(value)
    )
      workspaceError(
        "REVISION_CONFLICT",
        "Native installation changed unrelated Pi settings; inspect before continuing.",
      );
  }
  const foreign = (settings: Record<string, unknown>) =>
    piPackages(settings).filter(
      (entry) =>
        piSourceKey(piPackageSource(entry), root) !== piSourceKey(source, root),
    );
  if (
    canonicalWorkspaceValue(foreign(before)) !==
    canonicalWorkspaceValue(foreign(after))
  )
    workspaceError(
      "REVISION_CONFLICT",
      "Native installation changed another Pi package entry or its order.",
    );
  const original = ownPiPackage(before, root, source);
  const installed = ownPiPackage(after, root, source);
  if (!installed)
    workspaceError(
      "STORE_UNAVAILABLE",
      "Native Pi settings do not contain the requested exact source.",
    );
  if (original) {
    const comparable = (entry: PiPackage) => {
      const value: Record<string, unknown> =
        typeof entry === "string"
          ? { source: piSourceKey(entry, root) }
          : { ...entry, source: piSourceKey(entry.source, root) };
      // This is the only owned delta, including normalization of a prior string.
      delete value.skills;
      return value;
    };
    if (
      canonicalWorkspaceValue(comparable(original)) !==
      canonicalWorkspaceValue(comparable(installed))
    )
      workspaceError(
        "REVISION_CONFLICT",
        "Native installation changed the product's existing package filters.",
      );
  }
}

function portablePiSettings(
  settings: Record<string, unknown>,
  root: string,
  source: string,
) {
  const own = ownPiPackage(settings, root, source);
  if (!own)
    workspaceError("STORE_UNAVAILABLE", "Native Pi product source is missing.");
  return {
    ...settings,
    packages: piPackages(settings).map((entry) =>
      piSourceKey(piPackageSource(entry), root) === piSourceKey(source, root)
        ? {
            ...(typeof entry === "string" ? { source: entry } : entry),
            skills: [],
          }
        : entry,
    ),
  };
}

export function attachPi(root: string, options: AttachPiOptions = {}) {
  root = resolve(root);
  const manifest = readWorkspaceManifest(root);
  if (!manifest)
    workspaceError(
      "MIGRATION_REQUIRED",
      "Initialize and inspect the portable workspace first.",
    );
  const packageRoot = resolve(options.packageRoot ?? workspacePackageRoot);
  const product = getWorkspaceProduct(packageRoot);
  const managed = readManagedWorkspaceContext(root, options.managedHome);
  if (product.revision !== manifest.product.revision)
    workspaceError(
      "REVISION_CONFLICT",
      "Attach the product matching the installed workspace revision.",
    );
  const existing = options.operation_id
    ? inspectPiAttachment(root, options.operation_id, {
        managedHome: options.managedHome,
      }).intent
    : undefined;
  if (
    existing &&
    (existing.installation_id !== manifest.installation_id ||
      canonicalWorkspaceValue(existing.product) !==
        canonicalWorkspaceValue(product) ||
      existing.package_root !== packageRoot)
  )
    workspaceError(
      "REVISION_CONFLICT",
      "The original Pi attachment belongs to another installation or product.",
    );
  if (
    existing &&
    canonicalWorkspaceValue(existing.managed_context) !==
      canonicalWorkspaceValue(managed)
  )
    workspaceError(
      "REVISION_CONFLICT",
      "Recovery requires the original managed home, identity and epoch.",
    );
  if (!existing && inspectWorkspace(root).pending_attachments.length)
    workspaceError(
      "STORE_BUSY",
      "Inspect and settle the original Pi attachment before any new native installation.",
    );
  if (existing && options.source && options.source !== existing.source)
    workspaceError(
      "REVISION_CONFLICT",
      "Recovery must keep the original Pi install source.",
    );
  const commit = cleanProductSourceRevision(packageRoot);
  const source =
    existing?.source ??
    options.source ??
    (commit ? `git:github.com/ainazemtsau/zaratustra@${commit}` : packageRoot);
  const commitSource =
    /^git:github\.com\/ainazemtsau\/zaratustra@[a-f0-9]{40}$/.test(source);
  if (!commitSource && resolve(source) !== packageRoot)
    workspaceError(
      "VALIDATION_ERROR",
      "Attach a local exact package path or a commit-pinned product source.",
    );
  const settings = observeWorkspaceFile(root, ".pi/settings.json");
  if (
    existing?.state === "confirmed" &&
    (settings.hash !== existing.settings_after_hash ||
      (existing.settings_filter &&
        (settings.hash !== existing.settings_filter.after_hash ||
          settings.identity !== existing.settings_filter.identity)))
  )
    workspaceError(
      "REVISION_CONFLICT",
      "The confirmed attachment no longer matches its recorded settings. Prepare a new reviewed attachment instead of replaying the old effect.",
    );
  const originalSettings = existing
    ? existing.settings_before === null
      ? null
      : Buffer.from(existing.settings_before, "base64")
    : settings.bytes;
  const settingsBefore = originalSettings
    ? (JSON.parse(originalSettings.toString("utf8")) as Record<string, unknown>)
    : {};
  ownPiPackage(settingsBefore, root, source);
  const nativeCLI =
    !existing && !options.runInstall ? nativePiCLI(packageRoot) : undefined;
  const runner =
    options.runInstall ??
    ((installSource: string, cwd: string) => {
      const result = spawnSync(
        process.execPath,
        [nativeCLI!, "install", "--local", "--approve", installSource],
        {
          cwd,
          stdio: ["inherit", "pipe", "inherit"],
          windowsHide: true,
          ...(commitSource ? {} : { env: { ...process.env, PI_OFFLINE: "1" } }),
        },
      );
      if (result.error || result.status !== 0)
        workspaceError(
          "STORE_UNAVAILABLE",
          "Native Pi local installation did not complete; inspect Pi settings before retrying.",
        );
    });
  const request = {
    installation_id: manifest.installation_id,
    source,
    package_root: packageRoot,
    product,
    managed_context: managed,
    settings_before: originalSettings?.toString("base64") ?? null,
  };
  const requestHash = workspaceHash(canonicalWorkspaceValue(request));
  if (existing && existing.request_hash !== requestHash)
    workspaceError(
      "REVISION_CONFLICT",
      "The original Pi attachment request changed.",
    );
  const operationId = existing?.operation_id ?? randomUUID();
  let intent = PiAttachmentIntentSchema.parse({
    format: 1,
    operation_id: operationId,
    ...request,
    request_hash: requestHash,
    state: existing?.state ?? "dispatched",
    created_at: existing?.created_at ?? new Date().toISOString(),
    updated_at: new Date().toISOString(),
    ...(existing?.settings_filter
      ? { settings_filter: existing.settings_filter }
      : {}),
  });
  ensureWorkspaceDirectory(root, `${stateRoot}/attachments`);
  const coordinator = new Coordination(
    ensureWorkspaceDirectory(root, `${stateRoot}/coordination`),
    "workspace-attach-" + randomUUID(),
    { create: true },
  );
  const coordinators = [coordinator];
  const reserved = new Set<Coordination>();
  try {
    if (managed.state === "managed")
      coordinators.push(
        new Coordination(managed.home, "workspace-attach-" + randomUUID(), {
          expectedId: managed.coordination_id,
          create: false,
        }),
      );
    for (const current of coordinators)
      current.sync("mutate", () => {
        const previous = current.operation(operationId);
        if (previous && previous.status !== "settled")
          current.adopt(operationId);
        else if (!previous)
          current.reserve({
            operation_id: operationId,
            epoch:
              current === coordinator
                ? manifest.installation_id
                : managed.state === "managed"
                  ? managed.epoch
                  : manifest.installation_id,
            kind: "workspace-pi-attachment",
            digest: requestHash,
            resources: ["workspace:layout"],
          });
        else return;
        reserved.add(current);
      });
    if (
      canonicalWorkspaceValue(
        readManagedWorkspaceContext(root, options.managedHome),
      ) !== canonicalWorkspaceValue(managed)
    )
      workspaceError(
        "REVISION_CONFLICT",
        "Managed context changed before native attachment admission.",
      );
    if (!existing) {
      const actual = observeWorkspaceFile(root, ".pi/settings.json");
      if (
        actual.hash !== settings.hash ||
        actual.identity !== settings.identity
      )
        workspaceError(
          "REVISION_CONFLICT",
          "Pi settings changed before native installation admission.",
        );
      writeWorkspaceJSON(root, attachmentPath(operationId), intent);
      options.fault?.("before_native_install");
      runner(source, root);
      options.fault?.("after_native_install");
    }
    let after = observeWorkspaceFile(root, ".pi/settings.json");
    if (!after.bytes)
      workspaceError(
        "STORE_UNAVAILABLE",
        "Native Pi installation produced no project settings.",
      );
    let settingsAfter = JSON.parse(after.bytes.toString("utf8")) as Record<
      string,
      unknown
    >;
    assertPiSettingsPreserved(settingsBefore, settingsAfter, root, source);
    const resolvedPackage = commitSource
      ? workspaceTarget(root, ".pi/git/github.com/ainazemtsau/zaratustra")
      : packageRoot;
    if (!existsSync(join(resolvedPackage, "package.json")))
      workspaceError(
        "STORE_UNAVAILABLE",
        "The native installed product package is unavailable for verification.",
      );
    const resolvedProduct = getWorkspaceProduct(resolvedPackage, {
      runtime: "source",
    });
    if (resolvedProduct.revision !== product.revision)
      workspaceError(
        "REVISION_CONFLICT",
        "The native installed product fingerprint differs from the workspace installation.",
      );
    if (
      commitSource &&
      cleanProductSourceRevision(resolvedPackage) !==
        source.slice(source.lastIndexOf("@") + 1)
    )
      workspaceError(
        "REVISION_CONFLICT",
        "The native installed checkout does not match the requested clean source revision.",
      );
    const normalized = portablePiSettings(settingsAfter, root, source);
    if (
      !intent.settings_filter &&
      canonicalWorkspaceValue(normalized) !==
        canonicalWorkspaceValue(settingsAfter)
    ) {
      const bytes = Buffer.from(JSON.stringify(normalized, null, 2) + "\n");
      intent = PiAttachmentIntentSchema.parse({
        ...intent,
        settings_filter: {
          before: after.bytes!.toString("base64"),
          before_hash: after.hash!,
          after: bytes.toString("base64"),
          after_hash: workspaceHash(bytes),
          identity: after.identity!,
        },
        updated_at: new Date().toISOString(),
      });
      writeWorkspaceJSON(root, attachmentPath(operationId), intent);
    }
    const filter = intent.settings_filter;
    if (filter) {
      const beforeBytes = Buffer.from(filter.before, "base64");
      const afterBytes = Buffer.from(filter.after, "base64");
      const nativeSettings = JSON.parse(beforeBytes.toString("utf8")) as Record<
        string,
        unknown
      >;
      assertPiSettingsPreserved(settingsBefore, nativeSettings, root, source);
      const intended = Buffer.from(
        JSON.stringify(
          portablePiSettings(nativeSettings, root, source),
          null,
          2,
        ) + "\n",
      );
      if (
        workspaceHash(beforeBytes) !== filter.before_hash ||
        workspaceHash(afterBytes) !== filter.after_hash ||
        !afterBytes.equals(intended)
      )
        workspaceError(
          "REVISION_CONFLICT",
          "The recorded package-skill selection differs from its exact native settings.",
        );
      if (existing?.state !== "confirmed")
        options.fault?.("before_skill_filter");
      const observed = observeWorkspaceFile(root, ".pi/settings.json");
      if (
        observed.identity !== filter.identity ||
        (existing?.state === "confirmed"
          ? observed.hash !== filter.after_hash
          : observed.hash !== filter.before_hash &&
            observed.hash !== filter.after_hash)
      )
        workspaceError(
          "REVISION_CONFLICT",
          "Pi settings changed after the package-skill selection was recorded.",
        );
      if (
        existing?.state !== "confirmed" &&
        observed.hash === filter.before_hash
      )
        publishWorkspaceFile(root, ".pi/settings.json", afterBytes);
      if (existing?.state !== "confirmed")
        options.fault?.("after_skill_filter");
      after = observeWorkspaceFile(root, ".pi/settings.json");
      if (
        after.hash !== filter.after_hash ||
        after.identity !== filter.identity
      )
        workspaceError(
          "REVISION_CONFLICT",
          "The package-skill selection could not be verified after publication.",
        );
      settingsAfter = JSON.parse(after.bytes!.toString("utf8")) as Record<
        string,
        unknown
      >;
    }
    assertPiSettingsPreserved(settingsBefore, settingsAfter, root, source);
    if (
      canonicalWorkspaceValue(settingsAfter) !==
      canonicalWorkspaceValue(portablePiSettings(settingsAfter, root, source))
    )
      workspaceError(
        "REVISION_CONFLICT",
        "Native Pi must select the shared workspace skills for this product.",
      );
    const result = {
      installation_id: manifest.installation_id,
      source,
      product,
      resolved_package: resolvedPackage,
      operation_id: operationId,
      state: "pending_native_trust" as const,
      next_step:
        "Run Pi in this workspace and accept native project trust. The runtime verifies the resolved product fingerprint before managed processing.",
    };
    if (
      canonicalWorkspaceValue(
        readManagedWorkspaceContext(root, options.managedHome),
      ) !== canonicalWorkspaceValue(managed)
    )
      workspaceError(
        "REVISION_CONFLICT",
        "Managed context changed before native attachment settlement.",
      );
    if (existing?.state !== "confirmed")
      writeWorkspaceJSON(root, attachmentPath(operationId), {
        ...intent,
        state: "confirmed",
        updated_at: new Date().toISOString(),
        settings_after_hash: after.hash,
      });
    for (const current of [...coordinators].reverse())
      if (reserved.has(current))
        current.sync("settle", () => current.release(operationId), {
          operationId,
        });
    reserved.clear();
    options.fault?.("after_attachment_receipt");
    return result;
  } catch (error) {
    const recorded = observeWorkspaceFile(
      root,
      attachmentPath(operationId),
    ).bytes;
    const saved = recorded
      ? PiAttachmentIntentSchema.parse(JSON.parse(recorded.toString("utf8")))
      : undefined;
    const confirmed = saved?.state === "confirmed";
    if (recorded && !confirmed)
      writeWorkspaceJSON(root, attachmentPath(operationId), {
        ...saved!,
        state: "unknown",
        updated_at: new Date().toISOString(),
        error: (error as Error).message,
      });
    else if (reserved.size) {
      for (const current of [...coordinators].reverse())
        if (reserved.has(current))
          current.sync("settle", () => current.release(operationId), {
            operationId,
          });
      reserved.clear();
    }
    throw error;
  } finally {
    for (const current of coordinators.reverse())
      current.close({ poisonUnknown: true });
  }
}

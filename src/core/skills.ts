import { createHash } from "node:crypto";
import { z } from "zod";
import { canonical, requireThat, SkillReferenceSchema } from "./contracts.ts";
import type { CallContext, RecordRow, StoragePort } from "./contracts.ts";
import type { Approvals } from "./approval.ts";

const hash = (value: unknown) =>
  createHash("sha256").update(canonical(value)).digest("hex");
const sha = z.string().regex(/^[a-f0-9]{64}$/);
export const BundlePathSchema = z
  .string()
  .min(1)
  .max(500)
  .refine(
    (path) =>
      !path.includes("\\") &&
      !path.includes(":") &&
      !path.startsWith("/") &&
      path
        .split("/")
        .every(
          (part) =>
            !!part &&
            part !== "." &&
            part !== ".." &&
            !/[. ]$/.test(part) &&
            !/[\x00-\x1f<>:"|?*]/.test(part) &&
            !/^(con|prn|aux|nul|com[1-9]|lpt[1-9])(?:\.|$)/i.test(part),
        ),
    "Use an unambiguous relative bundle path.",
  );
export const BundleRoleSchema = z.enum([
  "text",
  "support",
  "executable",
  "execution_input",
]);
export const BundleMetadataSchema = z.strictObject({
  format: z.literal(1),
  skill_id: z.string().uuid(),
  name: z.string().min(1).max(200),
  entry: z.literal("SKILL.md"),
  file_roles: z.record(BundlePathSchema, BundleRoleSchema).optional(),
});
export const BundleFileSchema = z.strictObject({
  path: BundlePathSchema,
  length: z
    .number()
    .int()
    .nonnegative()
    .max(256 * 1024),
  sha256: sha,
  role: BundleRoleSchema,
});
export const BundleManifestSchema = z
  .strictObject({
    format: z.literal(1),
    skill_id: z.string().uuid(),
    files: z.array(BundleFileSchema).min(2).max(128),
    content_hash: sha,
  })
  .superRefine((manifest, ctx) => {
    const paths = manifest.files.map((file) => file.path);
    const prefixes = new Map<string, string>();
    for (const path of paths) {
      const parts = path.split("/");
      for (let index = 1; index <= parts.length; index++) {
        const prefix = parts.slice(0, index).join("/");
        if (
          (prefixes.has(prefix.toLowerCase()) &&
            prefixes.get(prefix.toLowerCase()) !== prefix) ||
          (index < parts.length &&
            paths.some(
              (candidate) => candidate.toLowerCase() === prefix.toLowerCase(),
            ))
        )
          ctx.addIssue({
            code: "custom",
            message: "Bundle path prefixes collide on Windows.",
          });
        prefixes.set(prefix.toLowerCase(), prefix);
      }
    }
    if (
      new Set(paths.map((path) => path.toLowerCase())).size !== paths.length ||
      paths.some((path, index) => index > 0 && paths[index - 1] >= path)
    )
      ctx.addIssue({
        code: "custom",
        message: "Bundle inventory must be sorted with unique Windows paths.",
      });
    if (
      !paths.includes("SKILL.md") ||
      !paths.includes("bundle.json") ||
      manifest.files.reduce((total, file) => total + file.length, 0) >
        1024 * 1024
    )
      ctx.addIssue({
        code: "custom",
        message:
          "Bundle needs its entry and metadata within the complete byte bound.",
      });
    for (const file of manifest.files) {
      if (
        (["SKILL.md", "bundle.json"].includes(file.path) &&
          file.role !== "text") ||
        ((file.path.startsWith("scripts/") ||
          /\.(?:[cm]?[jt]sx?|py|ps1|psm1|bat|cmd|sh|exe|com|dll|vbs|rb|pl)$/i.test(
            file.path,
          )) &&
          file.role !== "executable") ||
        (file.path === "SKILL.md" && file.length > 64000)
      )
        ctx.addIssue({
          code: "custom",
          message: "Bundle file role or entry size is invalid.",
        });
    }
    if (manifest.content_hash !== bundleContentHash(manifest))
      ctx.addIssue({
        code: "custom",
        message: "Complete bundle content hash does not match its inventory.",
      });
  });
export type BundleManifest = z.infer<typeof BundleManifestSchema>;
export type BundleMetadata = z.infer<typeof BundleMetadataSchema>;
export function bundleContentHash(
  manifest: Omit<BundleManifest, "content_hash">,
) {
  return hash({
    format: manifest.format,
    skill_id: manifest.skill_id,
    files: manifest.files,
  });
}
export { SkillReferenceSchema } from "./contracts.ts";
export const SelectedSkillVersionSchema = z.strictObject({
  skill_id: z.string().uuid(),
  revision: z.number().int().positive(),
  content_hash: sha,
  manifest: BundleManifestSchema,
});
export type SkillReference = z.infer<typeof SkillReferenceSchema>;
export type SelectedSkillVersion = z.infer<typeof SelectedSkillVersionSchema>;
export const SkillsSchemaSQL = `
CREATE TABLE IF NOT EXISTS skill_bundles(skill_id TEXT PRIMARY KEY,json TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS skill_versions(skill_id TEXT NOT NULL,revision INTEGER NOT NULL,json TEXT NOT NULL,PRIMARY KEY(skill_id,revision));
CREATE TABLE IF NOT EXISTS skill_operations(operation_id TEXT PRIMARY KEY,json TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS skill_delegations(skill_id TEXT PRIMARY KEY,json TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS skill_reservations(skill_id TEXT PRIMARY KEY,json TEXT NOT NULL);`;
export const SkillsCollections = [
  { table: "skill_bundles", keyColumns: ["skill_id"] },
  { table: "skill_versions", keyColumns: ["skill_id", "revision"] },
  { table: "skill_operations", keyColumns: ["operation_id"] },
  { table: "skill_delegations", keyColumns: ["skill_id"] },
  { table: "skill_reservations", keyColumns: ["skill_id"] },
];
export const SkillActivationSchema = z.strictObject({
  operation_id: z.string().min(1).max(200),
  path: BundlePathSchema,
  metadata: BundleMetadataSchema,
  manifest: BundleManifestSchema,
  visibility: z.enum(["workspace", "restricted"]),
  activity_ids: z.array(z.string().min(1)).max(30),
  general_exposure: z.boolean(),
  before_revision: z.number().int().positive().nullable(),
  expected_working_hash: sha.nullable(),
  before_manifest: BundleManifestSchema.nullable().optional(),
  discovery_hash: sha.optional(),
  adopt_export: z
    .strictObject({
      path: z.string().min(1),
      export_request_id: z.string().min(1),
      retire_original: z.boolean().optional(),
      method_ref: z.strictObject({
        id: z.string().min(1),
        revision: z.number().int().positive(),
        content_version: z.number().int().positive().optional(),
      }),
    })
    .optional(),
});
export type SkillActivation = z.infer<typeof SkillActivationSchema>;
export const SkillLocalGuardSchema = z.strictObject({
  skill_id: z.string().uuid(),
  activity_id: z.string().min(1),
  before_revision: z.number().int().positive(),
  before_hash: sha,
  delegation_revision: z.number().int().positive(),
  consumer_digest: sha,
  allowed_paths: z.array(BundlePathSchema).min(1).max(128),
  max_bytes: z
    .number()
    .int()
    .positive()
    .max(1024 * 1024),
  activity_revision: z.number().int().positive(),
  discovery_hash: sha.optional(),
});
export type SkillLocalGuard = z.infer<typeof SkillLocalGuardSchema>;
export const SkillDelegationSchema = z.strictObject({
  request_id: z.string().min(1).max(200),
  skill_id: z.string().uuid(),
  activity_id: z.string().min(1),
  allowed_paths: z.array(BundlePathSchema).min(1).max(128),
  max_bytes: z
    .number()
    .int()
    .positive()
    .max(1024 * 1024),
  enabled: z.boolean(),
  expected_revision: z.number().int().nonnegative(),
});
type Delegation = z.infer<typeof SkillDelegationSchema> & { revision: number };
export interface SkillBundle {
  skill_id: string;
  path: string;
  metadata: BundleMetadata;
  revision: number;
  content_hash: string;
  visibility: "workspace" | "restricted";
  activity_ids: string[];
  general_exposure: boolean;
  discovery_hash?: string;
}
export interface SkillOperation {
  operation_id: string;
  request: SkillActivation;
  digest: string;
  status: "prepared" | "unknown" | "completed" | "compensated";
  consumer_digest: string;
  local_guard?: SkillLocalGuard;
  authority: "owner" | "delegated-sleep";
  runtime_id: string;
  session_id: string;
  epoch: string;
  activity_refs: { id: string; revision: number }[];
  consumer_refs: { id: string; revision: number }[];
  receipt?: {
    committed: true;
    operation_id: string;
    skill_id: string;
    revision: number;
    content_hash: string;
  };
}

interface SkillHooks {
  authorize(write?: boolean): void;
  record(id: string, revision?: number): RecordRow;
  restricted(id: string, revision?: number): boolean;
  methodClosure(root: RecordRow, staged?: RecordRow[]): RecordRow[];
}
interface RetainedSkillVersion extends SelectedSkillVersion {
  visibility?: string;
  activity_refs?: { id: string; revision: number }[];
  adopted_export?: { ref?: { method_ref?: { id: string; revision: number } } };
}

/** Exact bundle metadata and authority. Byte effects belong to the storage adapter. */
export class SkillRegistry {
  private localPermits = new WeakMap<
    object,
    { guard: SkillLocalGuard; after: string }
  >();
  private discoveryReader?: () => string;
  constructor(
    private storage: StoragePort,
    private context: CallContext,
    private approvals: Approvals,
    private hooks: SkillHooks,
  ) {}

  private command<T>(write: boolean, action: () => T): T {
    const run = () => {
      this.hooks.authorize(write);
      requireThat(
        this.storage.workspace.schema_version >= 11,
        "MIGRATION_REQUIRED",
        "Personal bundles require the verified workspace transition.",
      );
      return action();
    };
    return this.storage.withCommandSync
      ? this.storage.withCommandSync(run, write ? "mutate" : "read")
      : run();
  }
  private transaction<T>(action: () => T): T {
    this.storage.exec("BEGIN IMMEDIATE");
    try {
      const result = action();
      this.storage.exec("COMMIT");
      return result;
    } catch (error) {
      this.storage.exec("ROLLBACK");
      throw error;
    }
  }
  private row<T>(table: string, key: string, value: string): T | undefined {
    const row = this.storage.get<{ json: string }>(
      `SELECT json FROM ${table} WHERE ${key}=?`,
      value,
    );
    return row ? (JSON.parse(row.json) as T) : undefined;
  }
  private bundle(skillId: string, write = false): SkillBundle {
    const bundle = this.row<SkillBundle>("skill_bundles", "skill_id", skillId);
    requireThat(
      bundle &&
        (bundle.visibility !== "restricted" ||
          this.context.scopes?.includes("restricted:read")),
      "REFERENCE_NOT_FOUND",
      "Skill unavailable.",
    );
    requireThat(
      bundle.skill_id === skillId &&
        bundle.metadata?.skill_id === skillId &&
        Number.isSafeInteger(bundle.revision) &&
        bundle.revision > 0,
      "STORE_UNAVAILABLE",
      "Skill bundle identity differs from its canonical key.",
    );
    let effectiveRestricted = bundle.visibility === "restricted";
    for (const activity of bundle.activity_ids) {
      this.hooks.record(activity);
      effectiveRestricted ||= this.hooks.restricted(activity);
    }
    const active = this.versionRecord(skillId, bundle.revision);
    requireThat(
      active.content_hash === bundle.content_hash,
      "STORE_UNAVAILABLE",
      "Current skill pointer differs from its retained complete version.",
    );
    const groundsRestricted = this.versionGrounds(active);
    effectiveRestricted ||= groundsRestricted;
    requireThat(
      !write ||
        !effectiveRestricted ||
        this.context.scopes?.includes("restricted:write"),
      "PERMISSION_DENIED",
      "Restricted skill writes require trusted setup scope.",
    );
    return bundle;
  }
  private versionGrounds(version: {
    visibility?: string;
    activity_refs?: { id: string; revision: number }[];
    adopted_export?: {
      ref?: { method_ref?: { id: string; revision: number } };
    };
  }) {
    let restricted = version.visibility === "restricted";
    requireThat(
      !restricted || this.context.scopes?.includes("restricted:read"),
      "REFERENCE_NOT_FOUND",
      "Selected skill version unavailable.",
    );
    const refs = [
      ...(version.activity_refs ?? []),
      ...(version.adopted_export?.ref?.method_ref
        ? [version.adopted_export.ref.method_ref]
        : []),
    ];
    for (const ref of refs) {
      this.hooks.record(ref.id, ref.revision);
      restricted ||= this.hooks.restricted(ref.id, ref.revision);
    }
    return restricted;
  }
  inspect(skillId: string) {
    return this.command(false, () => structuredClone(this.bundle(skillId)));
  }
  inspectCandidate(inputPath: string, skillId?: string): SkillBundle | null {
    return this.command(false, () => {
      const path = BundlePathSchema.parse(inputPath);
      const lower = path.toLowerCase();
      const rows = this.storage.all<{ json: string }>(
        "SELECT json FROM skill_bundles",
      );
      for (const row of rows) {
        const existing = JSON.parse(row.json) as SkillBundle;
        const registeredPath = existing.path.toLowerCase();
        if (
          registeredPath === lower ||
          registeredPath.startsWith(lower + "/") ||
          lower.startsWith(registeredPath + "/")
        ) {
          const accessible = this.bundle(existing.skill_id);
          requireThat(
            registeredPath === lower &&
              (!skillId || skillId === existing.skill_id),
            "REVISION_CONFLICT",
            "Bundle path has a different registered authority.",
          );
          return structuredClone(accessible);
        }
      }
      for (const row of this.storage.all<{
        operation_id: string;
        json: string;
      }>(
        "SELECT operation_id,json FROM skill_operations WHERE json_extract(json,'$.status') IN ('prepared','unknown')",
      )) {
        const pending = JSON.parse(row.json) as SkillOperation;
        const pendingPath = pending.request.path.toLowerCase();
        if (
          pendingPath === lower ||
          pendingPath.startsWith(lower + "/") ||
          lower.startsWith(pendingPath + "/")
        ) {
          this.operationRaw(row.operation_id);
          requireThat(
            pendingPath === lower &&
              (!skillId || pending.request.metadata.skill_id === skillId),
            "REVISION_CONFLICT",
            "Bundle path has an unresolved authority transition.",
          );
        }
      }
      if (
        skillId &&
        this.row<SkillBundle>("skill_bundles", "skill_id", skillId)
      ) {
        this.bundle(skillId);
        requireThat(
          false,
          "REVISION_CONFLICT",
          "Skill identity already belongs to another path.",
        );
      }
      return null;
    });
  }
  bindDiscoveryReader(reader: () => string) {
    this.discoveryReader = reader;
  }
  version(skillId: string, revision?: number): SelectedSkillVersion {
    return this.command(false, () => {
      const bundle = this.bundle(skillId);
      const retained = this.versionRecord(skillId, revision ?? bundle.revision);
      this.versionGrounds(retained);
      const version = SelectedSkillVersionSchema.parse({
        skill_id: retained.skill_id,
        revision: retained.revision,
        content_hash: retained.content_hash,
        manifest: retained.manifest,
      });
      this.verifyRetained(version.manifest);
      return version;
    });
  }
  private versionRecord(
    skillId: string,
    revision: number,
  ): RetainedSkillVersion {
    const row = this.storage.get<{ json: string }>(
      "SELECT json FROM skill_versions WHERE skill_id=? AND revision=?",
      skillId,
      revision,
    );
    requireThat(
      row,
      "CONTENT_NOT_RETAINED",
      "Selected complete skill version is unavailable.",
    );
    const retained = JSON.parse(row.json) as RetainedSkillVersion;
    requireThat(
      retained.skill_id === skillId &&
        retained.revision === revision &&
        retained.manifest?.skill_id === skillId &&
        retained.content_hash === retained.manifest.content_hash,
      "STORE_UNAVAILABLE",
      "Retained skill version differs from its canonical key or complete content hash.",
    );
    const parsed = SelectedSkillVersionSchema.safeParse({
      skill_id: retained.skill_id,
      revision: retained.revision,
      content_hash: retained.content_hash,
      manifest: retained.manifest,
    });
    requireThat(
      parsed.success,
      "STORE_UNAVAILABLE",
      "Retained complete skill manifest is invalid.",
    );
    return retained;
  }
  private verifyRetained(manifest: BundleManifest) {
    for (const file of manifest.files) {
      const bytes =
        this.storage.readMaterialBytes?.(file.sha256) ??
        Buffer.from(this.storage.readMaterial(file.sha256));
      requireThat(
        bytes.byteLength === file.length &&
          createHash("sha256").update(bytes).digest("hex") === file.sha256,
        "CONTENT_NOT_RETAINED",
        "Complete selected skill bytes are unavailable.",
      );
    }
  }
  private retainedBytes(hash: string) {
    return (
      this.storage.readMaterialBytes?.(hash) ??
      Buffer.from(this.storage.readMaterial(hash))
    );
  }
  private scope(skillId: string) {
    const bundle = this.row<SkillBundle>("skill_bundles", "skill_id", skillId);
    const records = this.storage
      .all<{
        json: string;
      }>("SELECT json FROM records WHERE kind IN ('method','activity')")
      .map((row) => JSON.parse(row.json) as RecordRow);
    const methods = records.filter(
      (record) =>
        record.kind === "method" &&
        record.storage !== "tombstone" &&
        record.data.state !== "deprecated",
    );
    const activities = records.filter(
      (record) =>
        record.kind === "activity" &&
        record.storage !== "tombstone" &&
        record.data.status !== "closed" &&
        record.data.status !== "merged",
    );
    let complete = true;
    const methodScopes: {
      id: string;
      revision: number;
      selected_methods: { id: string; revision: number }[];
      activities: string[];
    }[] = [];
    for (const method of methods) {
      let closure: RecordRow[];
      try {
        closure = this.hooks.methodClosure(method);
      } catch {
        complete = false;
        continue;
      }
      if (
        !closure.some((selected) =>
          ((selected.data.skill_refs ?? []) as SkillReference[]).some(
            (ref) => ref.skill_id === skillId,
          ),
        )
      )
        continue;
      methodScopes.push({
        id: method.id,
        revision: method.revision,
        selected_methods: closure.map((selected) => ({
          id: selected.id,
          revision: selected.revision,
        })),
        activities: activities
          .filter((activity) => {
            const contract = activity.data.contract as
              | { procedure_refs?: { id: string }[] }
              | undefined;
            return contract?.procedure_refs?.some(
              (ref) => ref.id === method.id,
            );
          })
          .map((activity) => activity.id)
          .sort(),
      });
    }
    const value = {
      binding: bundle
        ? {
            activity_ids: [...bundle.activity_ids].sort(),
            general_exposure: bundle.general_exposure,
          }
        : null,
      methods: methodScopes.sort((a, b) => a.id.localeCompare(b.id)),
      complete,
    };
    return { ...value, digest: hash(value) };
  }
  consumers(skillId: string) {
    return this.command(false, () => {
      this.bundle(skillId);
      const scope = this.scope(skillId);
      return {
        skill_id: skillId,
        consumer_digest: scope.digest,
        shared:
          !scope.complete ||
          !!scope.binding?.general_exposure ||
          (scope.binding?.activity_ids.length ?? 0) > 1 ||
          scope.methods.length > 1,
        coverage: scope.complete
          ? ("complete" as const)
          : ("incomplete" as const),
      };
    });
  }
  private available(skillId: string, operationId?: string) {
    const reservation = this.row<{ operation_id: string }>(
      "skill_reservations",
      "skill_id",
      skillId,
    );
    requireThat(
      !reservation || reservation.operation_id === operationId,
      "STORE_BUSY",
      "Skill scope has an unresolved publication. Inspect its original operation.",
    );
  }
  assertConsumerMutation(rows: RecordRow[]) {
    if (
      this.storage.workspace.schema_version < 11 ||
      !rows.some((row) => ["method", "activity"].includes(row.kind))
    )
      return;
    const reservations = this.storage.all<{ skill_id: string }>(
      "SELECT skill_id FROM skill_reservations",
    );
    for (const reservation of reservations) {
      const scope = this.scope(reservation.skill_id);
      const held = this.row<{ operation_id: string }>(
        "skill_reservations",
        "skill_id",
        reservation.skill_id,
      );
      const operation = held
        ? this.row<SkillOperation>(
            "skill_operations",
            "operation_id",
            held.operation_id,
          )
        : undefined;
      const affected = rows.some((row) => {
        if (row.kind === "method") {
          if (
            !scope.complete ||
            scope.methods.some((method) =>
              method.selected_methods.some(
                (selected) => selected.id === row.id,
              ),
            )
          )
            return true;
          try {
            return this.hooks
              .methodClosure(row, rows)
              .some((selected) =>
                ((selected.data.skill_refs ?? []) as SkillReference[]).some(
                  (ref) => ref.skill_id === reservation.skill_id,
                ),
              );
          } catch {
            return true;
          }
        }
        return (
          operation?.request.activity_ids.includes(row.id) ||
          scope.binding?.activity_ids.includes(row.id) ||
          scope.methods.some((method) => method.activities.includes(row.id)) ||
          (
            (row.data.contract as { procedure_refs?: { id: string }[] })
              ?.procedure_refs ?? []
          ).some((ref) => scope.methods.some((method) => method.id === ref.id))
        );
      });
      requireThat(
        !affected,
        "STORE_BUSY",
        "Skill consumer scope is reserved by an unresolved publication.",
      );
    }
  }
  prepare(input: unknown, consequence: string, alternatives: string) {
    return this.command(true, () => {
      const request = this.activation(input);
      const current = this.row<SkillBundle>(
        "skill_bundles",
        "skill_id",
        request.metadata.skill_id,
      );
      const dependencies = [
        ...new Set([...request.activity_ids, ...(current?.activity_ids ?? [])]),
      ].map((id) => {
        const record = this.hooks.record(id);
        return { id, revision: record.revision };
      });
      if (request.adopt_export) {
        const original = this.hooks.record(request.adopt_export.method_ref.id);
        dependencies.push({ id: original.id, revision: original.revision });
      }
      const exact = this.activationExact(
        request,
        this.scope(request.metadata.skill_id).digest,
      );
      this.authorizeConsumers(request.metadata.skill_id);
      return {
        request,
        preview: this.approvals.draft(
          "skill_activation",
          exact,
          dependencies,
          consequence,
          alternatives,
        ),
      };
    });
  }
  private activation(input: unknown): SkillActivation {
    const request = SkillActivationSchema.parse(input);
    this.inspectCandidate(request.path, request.metadata.skill_id);
    requireThat(
      request.metadata.skill_id === request.manifest.skill_id,
      "VALIDATION_ERROR",
      "Bundle identity differs from its complete manifest.",
    );
    if (request.before_manifest) {
      requireThat(
        request.before_manifest.skill_id === request.metadata.skill_id &&
          request.expected_working_hash ===
            request.before_manifest.content_hash,
        "VALIDATION_ERROR",
        "Before bundle manifest differs from the guarded working state.",
      );
      this.verifyRetained(request.before_manifest);
    }
    requireThat(
      new Set(request.activity_ids).size === request.activity_ids.length,
      "VALIDATION_ERROR",
      "Duplicate Activity bindings.",
    );
    for (const id of request.activity_ids)
      requireThat(
        this.hooks.record(id).kind === "activity",
        "REFERENCE_TYPE_MISMATCH",
        "Skill scope requires Activity identities.",
      );
    requireThat(
      !request.activity_ids.some((id) => this.hooks.restricted(id)) ||
        this.context.scopes?.includes("restricted:write"),
      "PERMISSION_DENIED",
      "Inherited restricted skill writes require trusted setup scope.",
    );
    const old = this.row<SkillBundle>(
      "skill_bundles",
      "skill_id",
      request.metadata.skill_id,
    );
    if (old) this.bundle(old.skill_id, true);
    requireThat(
      (old?.revision ?? null) === request.before_revision,
      "REVISION_CONFLICT",
      "The registered skill version changed.",
    );
    requireThat(
      !old || old.path === request.path,
      "VALIDATION_ERROR",
      "Move a registered skill through a separately reviewed identity transition.",
    );
    requireThat(
      request.visibility !== "restricted" ||
        this.context.scopes?.includes("restricted:write"),
      "PERMISSION_DENIED",
      "Restricted skill writes require trusted setup scope.",
    );
    requireThat(
      !old || old.visibility === request.visibility,
      "PERMISSION_DENIED",
      "Bundle activation cannot change access boundaries.",
    );
    this.available(request.metadata.skill_id, request.operation_id);
    this.verifyRetained(request.manifest);
    const metadataFile = request.manifest.files.find(
      (file) => file.path === "bundle.json",
    )!;
    const metadata = BundleMetadataSchema.parse(
      JSON.parse(
        new TextDecoder("utf-8", { fatal: true }).decode(
          this.retainedBytes(metadataFile.sha256),
        ),
      ),
    );
    requireThat(
      canonical(metadata) === canonical(request.metadata),
      "VALIDATION_ERROR",
      "Registered metadata differs from the retained bundle.json bytes.",
    );
    if (request.adopt_export) this.adoption(request);
    return request;
  }
  private authorizeConsumers(skillId: string) {
    for (const consumer of this.scope(skillId).methods)
      for (const selected of consumer.selected_methods)
        this.hooks.record(selected.id, selected.revision);
  }
  private activationExact(request: SkillActivation, consumerDigest: string) {
    const { before_manifest, ...fields } = request;
    const { file_roles, ...metadata } = request.metadata;
    void before_manifest;
    void file_roles;
    const current = this.row<SkillBundle>(
      "skill_bundles",
      "skill_id",
      request.metadata.skill_id,
    );
    const exact = {
      request: { ...fields, metadata },
      request_digest: hash(request),
      consumer_digest: consumerDigest,
      consumer_coverage: this.scope(request.metadata.skill_id).complete
        ? "complete"
        : "incomplete",
      binding_before: current
        ? {
            revision: current.revision,
            activity_ids: current.activity_ids,
            visibility: current.visibility,
            general_exposure: current.general_exposure,
          }
        : null,
    };
    const displayBudget = Math.max(
      0,
      248000 - Buffer.byteLength(canonical(exact)),
    );
    return {
      ...exact,
      bundle_preview: this.previewContents(
        request.manifest,
        displayBudget,
        request.before_manifest ?? undefined,
      ),
    };
  }
  previewContents(
    input: unknown,
    displayBudget = 96000,
    before?: BundleManifest,
  ) {
    const manifest = BundleManifestSchema.parse(input);
    const previous = new Map(
      before?.files.map((file) => [file.path, file.sha256]),
    );
    const priority = (file: BundleManifest["files"][number]) => {
      const changed = previous.get(file.path) !== file.sha256;
      if (changed && file.role === "executable") return 0;
      if (file.path === "SKILL.md") return 1;
      if (changed) return 2;
      return 3;
    };
    const files = [...manifest.files].sort(
      (a, b) => priority(a) - priority(b) || a.path.localeCompare(b.path),
    );
    const inventory = files.map((file) => ({
      ...file,
      text: "",
      text_complete: false,
    }));
    let remaining = Math.max(
      0,
      Math.min(96000, displayBudget - Buffer.byteLength(canonical(inventory))),
    );
    return files.map((file) => {
      const bytes =
        this.storage.readMaterialBytes?.(file.sha256) ??
        Buffer.from(this.storage.readMaterial(file.sha256));
      let text: string | null = null;
      try {
        text = new TextDecoder("utf-8", { fatal: true }).decode(bytes);
      } catch {
        /* Binary files are described by their exact inventory. */
      }
      if (text === null) return { ...file, text: null, text_complete: true };
      let preview = "";
      for (const character of text) {
        const encoded = Buffer.byteLength(JSON.stringify(character)) - 2;
        if (encoded > remaining) break;
        preview += character;
        remaining -= encoded;
      }
      return { ...file, text: preview, text_complete: preview === text };
    });
  }
  private adoption(request: SkillActivation) {
    const adoption = request.adopt_export!;
    const row = this.storage.get<{ json: string }>(
      "SELECT json FROM intents WHERE request_id=?",
      adoption.export_request_id,
    );
    const effect = row
      ? (JSON.parse(row.json) as {
          kind: string;
          status: string;
          payload: {
            target: string;
            method_export?: { method_ref: unknown };
            arguments?: { content?: string };
          };
          export_retired_by?: string;
        })
      : undefined;
    requireThat(
      effect?.kind === "managed_file" &&
        effect.payload.target === adoption.path &&
        effect.payload.method_export &&
        canonical(effect.payload.method_export.method_ref) ===
          canonical(adoption.method_ref),
      "REFERENCE_NOT_FOUND",
      "Original managed Method export unavailable.",
    );
    this.hooks.record(adoption.method_ref.id);
    requireThat(
      !this.hooks.restricted(
        adoption.method_ref.id,
        adoption.method_ref.revision,
      ) || this.context.scopes?.includes("restricted:write"),
      "PERMISSION_DENIED",
      "Adopting protected Method grounds requires trusted restricted-write scope.",
    );
    const retainedMethod = this.storage.get<{ json: string }>(
      "SELECT json FROM revisions WHERE id=? AND revision=?",
      adoption.method_ref.id,
      adoption.method_ref.revision,
    );
    requireThat(
      retainedMethod &&
        (JSON.parse(retainedMethod.json) as RecordRow).storage !== "tombstone",
      "CONTENT_NOT_RETAINED",
      "Original exact Method version is unavailable.",
    );
    const bundleTarget = this.storage.skillBundlePath?.(request.path);
    if (bundleTarget) {
      const normalized = (path: string) =>
        path.replaceAll("\\", "/").replace(/\/+$/, "").toLowerCase();
      const sameTarget =
        normalized(adoption.path) === normalized(bundleTarget + "/SKILL.md");
      requireThat(
        !sameTarget || adoption.retire_original === true,
        "APPROVAL_REQUIRED",
        "Same-path adoption must retire the export writer in the exact confirmed transition.",
      );
    }
    requireThat(
      !effect.export_retired_by ||
        effect.export_retired_by === request.operation_id,
      "REVISION_CONFLICT",
      "Export target already has a personal authority transition.",
    );
    const unresolved = this.storage
      .all<{
        json: string;
      }>(
        "SELECT json FROM intents WHERE json_extract(json,'$.kind')='managed_file' AND json_extract(json,'$.payload.target')=?",
        adoption.path,
      )
      .some((item) => {
        const observed = JSON.parse(item.json) as {
          status: string;
          superseded_by?: string;
          document_superseded_by?: string;
        };
        return (
          ["requested", "unknown"].includes(observed.status) &&
          !observed.superseded_by &&
          !observed.document_superseded_by
        );
      });
    requireThat(
      !unresolved && effect.status === "confirmed",
      "UNKNOWN_EFFECT",
      "Reconcile original export effects before adopting their target.",
    );
    requireThat(
      typeof effect.payload.arguments?.content === "string",
      "CONTENT_NOT_RETAINED",
      "Original exact textual export bytes are unavailable.",
    );
    return effect;
  }
  assertExportTarget(target: string) {
    if (this.storage.workspace.schema_version < 11) return;
    const retired = this.storage.get(
      "SELECT request_id FROM intents WHERE json_extract(json,'$.kind')='managed_file' AND json_extract(json,'$.payload.target')=? COLLATE NOCASE AND json_extract(json,'$.export_retired_by') IS NOT NULL LIMIT 1",
      target,
    );
    requireThat(
      !retired,
      "PERMISSION_DENIED",
      "This export target now belongs to a personal bundle authority transition.",
    );
    const adopting = this.storage.get(
      "SELECT operation_id FROM skill_operations WHERE json_extract(json,'$.status') IN ('prepared','unknown') AND json_extract(json,'$.request.adopt_export.path')=? COLLATE NOCASE LIMIT 1",
      target,
    );
    requireThat(
      !adopting,
      "STORE_BUSY",
      "Export target authority transition is awaiting reconciliation.",
    );
  }
  private beginRequest(
    request: SkillActivation,
    authority: SkillOperation["authority"],
    consumerDigest: string,
    localGuard?: SkillLocalGuard,
  ) {
    const previous = this.row<SkillOperation>(
      "skill_operations",
      "operation_id",
      request.operation_id,
    );
    const digest = hash(request);
    if (previous) {
      requireThat(
        previous.digest === digest,
        "IDEMPOTENCY_CONFLICT",
        "Skill operation identity belongs to different values.",
      );
      requireThat(
        previous.status === "completed",
        "UNKNOWN_EFFECT",
        "Inspect and reconcile the original skill publication before further dispatch.",
      );
      return previous;
    }
    const activityRefs = new Map<string, { id: string; revision: number }>();
    const current = this.row<SkillBundle>(
      "skill_bundles",
      "skill_id",
      request.metadata.skill_id,
    );
    for (const activityId of [
      ...request.activity_ids,
      ...(current?.activity_ids ?? []),
    ]) {
      const activity = this.hooks.record(activityId);
      const ref = { id: activity.id, revision: activity.revision };
      activityRefs.set(canonical(ref), ref);
    }
    if (request.before_revision !== null) {
      const original = this.versionRecord(
        request.metadata.skill_id,
        request.before_revision,
      );
      this.versionGrounds(original);
      for (const ref of original.activity_refs ?? [])
        activityRefs.set(canonical(ref), ref);
    }
    const operation: SkillOperation = {
      operation_id: request.operation_id,
      request,
      digest,
      status: "prepared",
      consumer_digest: consumerDigest,
      authority,
      runtime_id: this.context.runtime_id,
      session_id: this.context.session_id,
      epoch: this.context.epoch,
      activity_refs: [...activityRefs.values()],
      consumer_refs: [
        ...new Map(
          this.scope(request.metadata.skill_id)
            .methods.flatMap((method) => method.selected_methods)
            .map((ref) => [canonical(ref), ref]),
        ).values(),
      ],
      ...(localGuard ? { local_guard: localGuard } : {}),
    };
    for (const consumer of operation.consumer_refs)
      this.hooks.record(consumer.id, consumer.revision);
    this.storage.run(
      "INSERT INTO skill_operations VALUES(?,?)",
      operation.operation_id,
      JSON.stringify(operation),
    );
    this.storage.run(
      "INSERT INTO skill_reservations VALUES(?,?)",
      request.metadata.skill_id,
      JSON.stringify({
        operation_id: operation.operation_id,
        epoch: this.context.epoch,
      }),
    );
    return operation;
  }
  begin(input: unknown, previewRef: string) {
    return this.command(true, () =>
      this.transaction(() => {
        const raw = SkillActivationSchema.parse(input);
        const previous = this.row<SkillOperation>(
          "skill_operations",
          "operation_id",
          raw.operation_id,
        );
        if (previous) {
          this.operationRaw(raw.operation_id);
          requireThat(
            previous.digest === hash(raw),
            "IDEMPOTENCY_CONFLICT",
            "Skill operation identity belongs to different values.",
          );
          requireThat(
            previous.status === "completed",
            "UNKNOWN_EFFECT",
            "Inspect and reconcile the original skill publication before further dispatch.",
          );
          return previous;
        }
        const request = this.activation(raw);
        const consumerDigest = this.scope(request.metadata.skill_id).digest;
        this.approvals.consume(
          previewRef,
          "skill_activation",
          this.activationExact(request, consumerDigest),
          request.operation_id,
        );
        return this.beginRequest(request, "owner", consumerDigest);
      }),
    );
  }
  complete(operationId: string, observed: unknown) {
    return this.command(true, () =>
      this.transaction(() => {
        const operation = this.operationRaw(operationId, true);
        if (operation.receipt) return operation.receipt;
        requireThat(
          operation.status !== "compensated",
          "INVALID_TRANSITION",
          "Compensated publication cannot activate.",
        );
        const manifest = BundleManifestSchema.parse(observed);
        requireThat(
          canonical(manifest) === canonical(operation.request.manifest),
          "REVISION_CONFLICT",
          "Observed complete bundle differs from the authorized result.",
        );
        this.activation(operation.request);
        requireThat(
          this.scope(manifest.skill_id).digest === operation.consumer_digest,
          "REVISION_CONFLICT",
          "Skill consumer scope changed before activation.",
        );
        if (operation.local_guard) this.assertLocalGuard(operation.local_guard);
        const revision = (operation.request.before_revision ?? 0) + 1;
        const adoption = operation.request.adopt_export
          ? this.adoption(operation.request)
          : undefined;
        const original = adoption?.payload.arguments?.content;
        const originalRef =
          original === undefined
            ? undefined
            : this.storage.writeMaterialBytes?.(Buffer.from(original));
        const version = {
          skill_id: manifest.skill_id,
          revision,
          content_hash: manifest.content_hash,
          manifest,
          visibility: operation.request.visibility,
          activity_refs: operation.request.activity_ids.map((activityId) => {
            const activity = this.hooks.record(activityId);
            return { id: activity.id, revision: activity.revision };
          }),
          hashes: [
            ...manifest.files.map((file) => file.sha256),
            ...(originalRef ? [originalRef] : []),
          ],
          ...(adoption
            ? {
                adopted_export: {
                  ref: operation.request.adopt_export,
                  ...(originalRef
                    ? { blob_ref: originalRef }
                    : { original_text: original }),
                },
              }
            : {}),
        };
        const bundle: SkillBundle = {
          skill_id: manifest.skill_id,
          path: operation.request.path,
          metadata: operation.request.metadata,
          revision,
          content_hash: manifest.content_hash,
          visibility: operation.request.visibility,
          activity_ids: operation.request.activity_ids,
          general_exposure: operation.request.general_exposure,
          ...(operation.request.discovery_hash
            ? { discovery_hash: operation.request.discovery_hash }
            : {}),
        };
        this.storage.run(
          "INSERT INTO skill_versions VALUES(?,?,?)",
          bundle.skill_id,
          revision,
          JSON.stringify(version),
        );
        this.storage.run(
          "INSERT INTO skill_bundles VALUES(?,?) ON CONFLICT(skill_id) DO UPDATE SET json=excluded.json",
          bundle.skill_id,
          JSON.stringify(bundle),
        );
        if (adoption && operation.request.adopt_export?.retire_original) {
          adoption.export_retired_by = operationId;
          this.storage.run(
            "UPDATE intents SET json=? WHERE request_id=?",
            JSON.stringify(adoption),
            operation.request.adopt_export!.export_request_id,
          );
        }
        operation.status = "completed";
        operation.receipt = {
          committed: true,
          operation_id: operationId,
          skill_id: bundle.skill_id,
          revision,
          content_hash: bundle.content_hash,
        };
        this.storage.run(
          "UPDATE skill_operations SET json=? WHERE operation_id=?",
          JSON.stringify(operation),
          operationId,
        );
        this.storage.run(
          "DELETE FROM skill_reservations WHERE skill_id=?",
          bundle.skill_id,
        );
        return operation.receipt;
      }),
    );
  }
  private operationRaw(operationId: string, write = false): SkillOperation {
    const operation = this.row<SkillOperation>(
      "skill_operations",
      "operation_id",
      operationId,
    );
    requireThat(
      operation,
      "REFERENCE_NOT_FOUND",
      "Skill operation unavailable.",
    );
    const bundle = this.row<SkillBundle>(
      "skill_bundles",
      "skill_id",
      operation.request.metadata.skill_id,
    );
    for (const activityId of operation.request.activity_ids)
      this.hooks.record(activityId);
    requireThat(
      Array.isArray(operation.activity_refs),
      "STORE_UNAVAILABLE",
      "Original skill operation access grounds are unavailable.",
    );
    for (const activity of operation.activity_refs)
      this.hooks.record(activity.id, activity.revision);
    for (const consumer of operation.consumer_refs ?? [])
      this.hooks.record(consumer.id, consumer.revision);
    if (operation.request.adopt_export)
      this.hooks.record(
        operation.request.adopt_export.method_ref.id,
        operation.request.adopt_export.method_ref.revision,
      );
    if (bundle) this.bundle(bundle.skill_id, write);
    else
      requireThat(
        operation.request.visibility !== "restricted" ||
          this.context.scopes?.includes("restricted:read"),
        "REFERENCE_NOT_FOUND",
        "Skill operation unavailable.",
      );
    if (operation.request.before_revision !== null)
      this.versionGrounds(
        this.versionRecord(
          operation.request.metadata.skill_id,
          operation.request.before_revision,
        ),
      );
    if (operation.receipt) {
      requireThat(
        operation.receipt.skill_id === operation.request.metadata.skill_id,
        "STORE_UNAVAILABLE",
        "Skill receipt identity differs from its original operation.",
      );
      const selected = this.versionRecord(
        operation.receipt.skill_id,
        operation.receipt.revision,
      );
      requireThat(
        selected.content_hash === operation.receipt.content_hash,
        "STORE_UNAVAILABLE",
        "Skill receipt differs from its retained complete version.",
      );
      this.versionGrounds(selected);
    }
    if (write)
      requireThat(
        (operation.request.visibility !== "restricted" &&
          !operation.request.activity_ids.some((id) =>
            this.hooks.restricted(id),
          ) &&
          ![...operation.activity_refs, ...operation.consumer_refs].some(
            (ref) => this.hooks.restricted(ref.id, ref.revision),
          ) &&
          !(
            operation.request.adopt_export &&
            this.hooks.restricted(
              operation.request.adopt_export.method_ref.id,
              operation.request.adopt_export.method_ref.revision,
            )
          )) ||
          this.context.scopes?.includes("restricted:write"),
        "PERMISSION_DENIED",
        "Protected skill operation writes require trusted setup scope.",
      );
    return operation;
  }
  operation(operationId: string) {
    return this.command(false, () =>
      structuredClone(this.operationRaw(operationId)),
    );
  }
  unknown(operationId: string) {
    return this.command(true, () => {
      const operation = this.operationRaw(operationId, true);
      if (["prepared", "unknown"].includes(operation.status)) {
        operation.status = "unknown";
        this.storage.run(
          "UPDATE skill_operations SET json=? WHERE operation_id=?",
          JSON.stringify(operation),
          operationId,
        );
      }
      return operation;
    });
  }
  rejectUndispatched(operationId: string, observedBeforeHash: string | null) {
    return this.command(true, () =>
      this.transaction(() => {
        const operation = this.operationRaw(operationId, true);
        requireThat(
          operation.status === "prepared" &&
            operation.runtime_id === this.context.runtime_id &&
            operation.session_id === this.context.session_id &&
            operation.epoch === this.context.epoch,
          "UNKNOWN_EFFECT",
          "Only the preparing runtime can settle its proven undispatched publication.",
        );
        const current = this.row<SkillBundle>(
          "skill_bundles",
          "skill_id",
          operation.request.metadata.skill_id,
        );
        requireThat(
          observedBeforeHash === operation.request.expected_working_hash &&
            (current?.revision ?? null) === operation.request.before_revision,
          "REVISION_CONFLICT",
          "Undispatched rejection requires the exact original working and registered state.",
        );
        operation.status = "compensated";
        this.storage.run(
          "UPDATE skill_operations SET json=? WHERE operation_id=?",
          JSON.stringify({ ...operation, resolution: "not-dispatched" }),
          operationId,
        );
        this.storage.run(
          "DELETE FROM skill_reservations WHERE skill_id=?",
          operation.request.metadata.skill_id,
        );
        return operation;
      }),
    );
  }
  prepareCompensation(
    operationId: string,
    consequence: string,
    alternatives: string,
  ) {
    return this.command(true, () => {
      const operation = this.operationRaw(operationId, true);
      requireThat(
        ["prepared", "unknown"].includes(operation.status),
        "INVALID_TRANSITION",
        "Only an unresolved publication can be compensated.",
      );
      const request = this.compensationExact(operation);
      return {
        request,
        preview: this.approvals.draft(
          "skill_compensation",
          request,
          [
            ...new Set(
              [...operation.activity_refs, ...operation.consumer_refs].map(
                (ref) => ref.id,
              ),
            ),
          ].map((id) => {
            const record = this.hooks.record(id);
            return { id, revision: record.revision };
          }),
          consequence,
          alternatives,
        ),
      };
    });
  }
  private compensationExact(operation: SkillOperation) {
    return {
      operation_id: operation.operation_id,
      operation_digest: operation.digest,
      expected_working_hash: operation.request.expected_working_hash,
      skill_id: operation.request.metadata.skill_id,
      path: operation.request.path,
      visibility: operation.request.visibility,
      activity_refs: operation.activity_refs,
      consumer_refs: operation.consumer_refs,
      ...(operation.request.adopt_export
        ? { method_ref: operation.request.adopt_export.method_ref }
        : {}),
    };
  }
  verifyCompensation(operationId: string, previewRef: string) {
    return this.command(true, () => {
      const operation = this.operationRaw(operationId, true);
      requireThat(
        ["prepared", "unknown"].includes(operation.status) &&
          !operation.receipt,
        "INVALID_TRANSITION",
        "Only an unresolved publication can be compensated.",
      );
      this.approvals.verify(
        previewRef,
        "skill_compensation",
        this.compensationExact(operation),
      );
    });
  }
  compensate(
    operationId: string,
    observedContentHash: string | null,
    previewRef: string,
  ) {
    return this.command(true, () =>
      this.transaction(() => {
        const operation = this.operationRaw(operationId, true);
        if (operation.status === "compensated") return operation;
        requireThat(
          !operation.receipt &&
            observedContentHash === operation.request.expected_working_hash,
          "REVISION_CONFLICT",
          "Compensation must prove the exact pre-publication working state.",
        );
        const current = this.row<SkillBundle>(
          "skill_bundles",
          "skill_id",
          operation.request.metadata.skill_id,
        );
        requireThat(
          (current?.revision ?? null) === operation.request.before_revision,
          "REVISION_CONFLICT",
          "Registered version changed after the unresolved publication.",
        );
        this.available(operation.request.metadata.skill_id, operationId);
        this.approvals.consume(
          previewRef,
          "skill_compensation",
          this.compensationExact(operation),
          operationId + ":compensate",
        );
        operation.status = "compensated";
        this.storage.run(
          "UPDATE skill_operations SET json=? WHERE operation_id=?",
          JSON.stringify(operation),
          operationId,
        );
        this.storage.run(
          "DELETE FROM skill_reservations WHERE skill_id=?",
          operation.request.metadata.skill_id,
        );
        return operation;
      }),
    );
  }
  prepareDelegation(input: unknown, consequence: string, alternatives: string) {
    return this.command(true, () => {
      const request = SkillDelegationSchema.parse(input);
      this.bundle(request.skill_id, true);
      this.available(request.skill_id);
      const activity = this.hooks.record(request.activity_id);
      requireThat(
        activity.kind === "activity",
        "REFERENCE_TYPE_MISMATCH",
        "Delegation requires an Activity.",
      );
      return {
        request,
        preview: this.approvals.draft(
          "skill_delegation",
          { request },
          [{ id: activity.id, revision: activity.revision }],
          consequence,
          alternatives,
        ),
      };
    });
  }
  delegate(input: unknown, previewRef: string) {
    return this.command(true, () =>
      this.transaction(() => {
        const request = SkillDelegationSchema.parse(input);
        this.bundle(request.skill_id, true);
        this.available(request.skill_id);
        const old = this.row<Delegation>(
          "skill_delegations",
          "skill_id",
          request.skill_id,
        );
        requireThat(
          (old?.revision ?? 0) === request.expected_revision,
          "REVISION_CONFLICT",
          "Skill delegation changed.",
        );
        this.approvals.consume(
          previewRef,
          "skill_delegation",
          { request },
          request.request_id,
        );
        const delegation = { ...request, revision: (old?.revision ?? 0) + 1 };
        this.storage.run(
          "INSERT INTO skill_delegations VALUES(?,?) ON CONFLICT(skill_id) DO UPDATE SET json=excluded.json",
          request.skill_id,
          JSON.stringify(delegation),
        );
        return delegation;
      }),
    );
  }
  localGuard(skillId: string, activityId: string): SkillLocalGuard {
    return this.command(false, () => {
      const bundle = this.bundle(skillId, true);
      const delegation = this.row<Delegation>(
        "skill_delegations",
        "skill_id",
        skillId,
      );
      const scope = this.scope(skillId);
      const activity = this.hooks.record(activityId);
      requireThat(
        activity.kind === "activity" && activity.data.status === "active",
        "INVALID_TRANSITION",
        "Delegated Activity must be active.",
      );
      requireThat(
        delegation?.enabled &&
          scope.complete &&
          delegation.activity_id === activityId &&
          bundle.activity_ids.length === 1 &&
          bundle.activity_ids[0] === activityId &&
          !bundle.general_exposure &&
          scope.methods.length <= 1 &&
          scope.methods.every(
            (method) =>
              method.activities.length === 1 &&
              method.activities[0] === activityId,
          ),
        "APPROVAL_REQUIRED",
        "Skill scope or delegation requires owner review.",
      );
      if (bundle.discovery_hash)
        requireThat(
          this.discoveryReader &&
            this.discoveryReader() === bundle.discovery_hash,
          "APPROVAL_REQUIRED",
          "Skill discovery changed and requires owner review.",
        );
      return {
        skill_id: skillId,
        activity_id: activityId,
        before_revision: bundle.revision,
        before_hash: bundle.content_hash,
        delegation_revision: delegation.revision,
        consumer_digest: scope.digest,
        allowed_paths: delegation.allowed_paths,
        max_bytes: delegation.max_bytes,
        activity_revision: activity.revision,
        ...(bundle.discovery_hash
          ? { discovery_hash: bundle.discovery_hash }
          : {}),
      };
    });
  }
  private assertLocalGuard(input: SkillLocalGuard) {
    const guard = SkillLocalGuardSchema.parse(input);
    requireThat(
      canonical(guard) ===
        canonical(this.localGuard(guard.skill_id, guard.activity_id)),
      "REVISION_CONFLICT",
      "Skill delegation, Activity, bundle or consumers changed.",
    );
  }
  validateLocalChange(input: unknown, proposed: unknown) {
    return this.command(false, () => {
      const guard = SkillLocalGuardSchema.parse(input),
        after = BundleManifestSchema.parse(proposed);
      this.assertLocalGuard(guard);
      const before = this.version(
        guard.skill_id,
        guard.before_revision,
      ).manifest;
      requireThat(
        after.skill_id === guard.skill_id &&
          after.files.length === before.files.length,
        "APPROVAL_REQUIRED",
        "Local text maintenance cannot change bundle identity or file inventory.",
      );
      let changedBytes = 0,
        changed = false;
      for (let index = 0; index < before.files.length; index++) {
        const old = before.files[index],
          next = after.files[index];
        requireThat(
          old.path === next.path && old.role === next.role,
          "APPROVAL_REQUIRED",
          "Local maintenance cannot change file paths or roles.",
        );
        if (old.sha256 !== next.sha256 || old.length !== next.length) {
          changed = true;
          changedBytes += next.length;
          requireThat(
            guard.allowed_paths.includes(next.path) &&
              ["text", "support"].includes(next.role) &&
              next.path !== "bundle.json",
            "APPROVAL_REQUIRED",
            "Changed skill files require owner confirmation.",
          );
        }
      }
      requireThat(
        changed && changedBytes <= guard.max_bytes,
        "LIMIT_EXCEEDED",
        "Local skill change exceeds its delegated bound or changes no content.",
      );
      const permit = Object.freeze({});
      this.localPermits.set(permit, { guard, after: after.content_hash });
      return permit;
    });
  }
  beginLocal(input: unknown, inputGuard: unknown, permit: object) {
    return this.command(true, () =>
      this.transaction(() => {
        const guard = SkillLocalGuardSchema.parse(inputGuard),
          request = this.activation(input);
        const authorization = this.localPermits.get(permit);
        requireThat(
          authorization &&
            canonical(authorization.guard) === canonical(guard) &&
            authorization.after === request.manifest.content_hash,
          "APPROVAL_REQUIRED",
          "No trusted exact local skill permit.",
        );
        this.assertLocalGuard(guard);
        const bundle = this.bundle(guard.skill_id);
        requireThat(
          !request.adopt_export &&
            request.expected_working_hash === guard.before_hash &&
            request.metadata.skill_id === guard.skill_id &&
            request.before_revision === guard.before_revision &&
            request.path === bundle.path &&
            request.visibility === bundle.visibility &&
            canonical(request.activity_ids) ===
              canonical(bundle.activity_ids) &&
            request.general_exposure === bundle.general_exposure &&
            request.discovery_hash === bundle.discovery_hash &&
            canonical(request.metadata) === canonical(bundle.metadata),
          "APPROVAL_REQUIRED",
          "Local skill publication cannot change identity, binding, access or metadata.",
        );
        const operation = this.beginRequest(
          request,
          "delegated-sleep",
          guard.consumer_digest,
          guard,
        );
        this.localPermits.delete(permit);
        return operation;
      }),
    );
  }
  select(methods: RecordRow[]): SelectedSkillVersion[] {
    return this.command(false, () => {
      const selections = new Map<string, SelectedSkillVersion>();
      for (const method of methods)
        for (const raw of (method.data.skill_refs ?? []) as unknown[]) {
          const ref = SkillReferenceSchema.parse(raw);
          this.available(ref.skill_id);
          const version = this.version(ref.skill_id, ref.revision);
          if (ref.revision === undefined) {
            const bundle = this.bundle(ref.skill_id);
            requireThat(
              this.storage.inspectSkillBundle,
              "SOURCE_MISSING",
              "Inspect working bundle bytes before selecting the current version.",
            );
            requireThat(
              this.storage.inspectSkillBundle(bundle.path).content_hash ===
                version.content_hash,
              "REVISION_CONFLICT",
              "Working skill files have pending drift. Reconcile them or explicitly select a retained version.",
            );
          }
          selections.set(version.skill_id + ":" + version.revision, version);
        }
      requireThat(
        selections.size <= 30,
        "LIMIT_EXCEEDED",
        "Method skill selection exceeds thirty complete versions.",
      );
      return [...selections.values()];
    });
  }
}

import { z } from "zod";

const hash = z.string().regex(/^[a-f0-9]{64}$/);
export const WorkspacePathSchema = z
  .string()
  .min(1)
  .max(500)
  .refine(
    (value) =>
      !value.includes("\\") &&
      !value.startsWith("/") &&
      value
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
    "Use an ordinary relative workspace path.",
  );

export const WorkspaceProductSchema = z.strictObject({
  version: z.string().min(1).max(100),
  revision: z.string().min(1).max(200),
  source_revision: z
    .string()
    .regex(/^[a-f0-9]{40}$/)
    .optional(),
});
export type WorkspaceProduct = z.infer<typeof WorkspaceProductSchema>;

export const WorkspaceActivitySchema = z.strictObject({
  key: z.string().min(1).max(200),
  label: z.string().min(1).max(200),
  guidance_path: WorkspacePathSchema.refine((value) =>
    /^activities\/.+\.md$/i.test(value),
  ),
  core_ref: z
    .strictObject({
      id: z.string().min(1).max(200),
      revision: z.number().int().positive().optional(),
    })
    .optional(),
});
export const WorkspacePersonalSkillSchema = z.strictObject({
  name: z.string().regex(/^[a-z0-9][a-z0-9-]{0,79}$/),
  description: z.string().min(1).max(400),
  path: WorkspacePathSchema.refine((value) =>
    /^skills\/personal\/.+\/SKILL\.md$/.test(value),
  ),
  activity_key: z.string().min(1).max(200).optional(),
});

export const WorkspaceManifestSchema = z
  .strictObject({
    layout_format: z.literal(1),
    installation_id: z.string().uuid(),
    product: WorkspaceProductSchema,
    managed_files: z
      .array(
        z.strictObject({
          path: WorkspacePathSchema.refine(
            (value) =>
              value === "AGENTS.md" ||
              value === "instructions/system.md" ||
              /^adapters\/(?:pi|codex)\.md$/.test(value) ||
              /^skills\/system\/zaratustra-(?:work|memory|documents|sleep)\/SKILL\.md$/.test(
                value,
              ) ||
              /^\.(?:agents|pi)\/skills\/[a-z0-9][a-z0-9-]{0,79}\/SKILL\.md$/.test(
                value,
              ),
          ),
          sha256: hash,
          kind: z.enum(["system", "generated"]),
        }),
      )
      .max(512),
    activities: z.array(WorkspaceActivitySchema).max(256),
    personal_skills: z.array(WorkspacePersonalSkillSchema).max(128).optional(),
    adapters: z.array(z.enum(["codex", "pi"])).max(2),
  })
  .superRefine((manifest, context) => {
    const unique = (values: string[], label: string) => {
      if (new Set(values).size !== values.length)
        context.addIssue({ code: "custom", message: `Duplicate ${label}.` });
    };
    unique(
      manifest.managed_files.map((file) => file.path.toLowerCase()),
      "managed file path",
    );
    unique(
      manifest.activities.map((activity) => activity.key),
      "Activity key",
    );
    unique(
      manifest.activities.flatMap((activity) =>
        activity.core_ref ? [activity.core_ref.id] : [],
      ),
      "Core Activity binding",
    );
    unique(manifest.adapters, "adapter");
    unique(
      (manifest.personal_skills ?? []).map((skill) => skill.name),
      "personal skill name",
    );
  });
export type WorkspaceManifest = z.infer<typeof WorkspaceManifestSchema>;

export const InstallationEntrySchema = z.strictObject({
  path: WorkspacePathSchema,
  kind: z.enum(["system", "generated", "owner"]),
  before: z.string().nullable(),
  before_hash: hash.nullable(),
  before_identity: z.string().nullable(),
  after: z.string().nullable(),
  after_hash: hash.nullable(),
  conflict: z.boolean(),
  reason: z.string(),
});
export const ManagedWorkspaceContextSchema = z.discriminatedUnion("state", [
  z.strictObject({
    state: z.literal("absent"),
    home: z.string().min(1),
    home_identity: z.string().nullable(),
  }),
  z.strictObject({
    state: z.literal("managed"),
    home: z.string().min(1),
    home_identity: z.string().min(1),
    workspace_id: z.string().min(1),
    coordination_id: z.string().min(1),
    epoch: z.string().min(1),
    control_hash: hash,
  }),
]);
export type ManagedWorkspaceContext = z.infer<
  typeof ManagedWorkspaceContextSchema
>;

export const InstallationPlanSchema = z.strictObject({
  format: z.literal(1),
  operation_id: z.string().uuid(),
  plan_id: z.string().regex(/^[a-f0-9-]{36}\.[a-f0-9]{64}$/),
  root: z.string().min(1),
  root_identity: z.string().min(1),
  created_at: z.iso.datetime(),
  product: WorkspaceProductSchema,
  managed_context: ManagedWorkspaceContextSchema,
  before_manifest: z.string().nullable(),
  manifest: WorkspaceManifestSchema,
  entries: z.array(InstallationEntrySchema).max(512),
});
export type InstallationPlan = z.infer<typeof InstallationPlanSchema>;

export const InstallationReceiptSchema = z.strictObject({
  format: z.literal(1),
  operation_id: z.string().uuid(),
  plan_id: z.string(),
  installation_id: z.string().uuid(),
  product: WorkspaceProductSchema,
  state: z.enum(["committed", "rolled_back"]),
  completed_at: z.iso.datetime(),
});
export type InstallationReceipt = z.infer<typeof InstallationReceiptSchema>;

export const InstallationJournalSchema = z.strictObject({
  format: z.literal(1),
  operation_id: z.string().uuid(),
  plan_id: z.string(),
  managed_context: ManagedWorkspaceContextSchema,
  state: z.enum([
    "planned",
    "publishing",
    "committed",
    "compensating",
    "rolled_back",
    "conflict",
    "refused",
  ]),
  updated_at: z.iso.datetime(),
  error: z.string().optional(),
});

export const PiAttachmentIntentSchema = z.strictObject({
  format: z.literal(1),
  operation_id: z.string().uuid(),
  installation_id: z.string().uuid(),
  source: z.string().min(1),
  package_root: z.string().min(1),
  product: WorkspaceProductSchema,
  managed_context: ManagedWorkspaceContextSchema,
  settings_before: z.string().nullable(),
  request_hash: hash,
  state: z.enum(["dispatched", "confirmed", "unknown"]),
  created_at: z.iso.datetime(),
  updated_at: z.iso.datetime(),
  settings_after_hash: hash.nullable().optional(),
  settings_filter: z
    .strictObject({
      before: z.string(),
      before_hash: hash,
      after: z.string(),
      after_hash: hash,
      identity: z.string().min(1),
    })
    .optional(),
  error: z.string().optional(),
});

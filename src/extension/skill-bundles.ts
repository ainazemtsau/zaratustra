import type { ExtensionContext } from "@earendil-works/pi-coding-agent";
import { existsSync, lstatSync, readFileSync, readdirSync } from "node:fs";
import { join, resolve } from "node:path";
import { z } from "zod";
import {
  BundlePathSchema,
  BundleManifestSchema,
  SkillActivationSchema,
  SkillDelegationSchema,
  canonical,
  digest,
  requireThat,
} from "../core/index.ts";
import type {
  Core,
  SkillActivation,
  SleepProposal,
  SleepSkillChange,
  SleepState,
} from "../core/index.ts";
import {
  SkillBundleFiles,
  skillBundleSnapshot,
  safePath,
} from "../storage/index.ts";
import type { DiskStorage, SkillBundleSnapshot } from "../storage/index.ts";
import { readWorkspaceManifest } from "../workspace/index.ts";
import { assertSleepSkillAllowed } from "../core/index.ts";

type Register = (
  name: string,
  description: string,
  schema: z.ZodType,
  action: (input: Record<string, unknown>, ctx: ExtensionContext) => unknown,
) => void;

type State = {
  core: () => Core;
  disk: () => DiskStorage;
  begin: () => () => void;
};

/** Discovery routes are guarded independently from editable bundle contents. */
export function workspaceDiscoveryHash(project: string) {
  const root = resolve(project);
  const inventory: { path: string; hash: string }[] = [];
  const visit = (relative: string) => {
    const path = safePath(root, join(root, relative));
    if (!existsSync(path)) return;
    const stat = lstatSync(path);
    requireThat(
      !stat.isSymbolicLink(),
      "PERMISSION_DENIED",
      "Assistant discovery cannot traverse a link.",
    );
    if (stat.isDirectory()) {
      for (const name of readdirSync(path).sort()) visit(relative + "/" + name);
      return;
    }
    requireThat(
      stat.isFile() && stat.nlink === 1 && stat.size <= 256 * 1024,
      "PERMISSION_DENIED",
      "Assistant discovery requires bounded single-link files.",
    );
    requireThat(
      inventory.length < 1024,
      "LIMIT_EXCEEDED",
      "Assistant discovery inventory exceeds its bound.",
    );
    inventory.push({ path: relative, hash: digest(readFileSync(path)) });
  };
  readWorkspaceManifest(root);
  for (const relative of [
    "AGENTS.md",
    "zaratustra.json",
    "instructions/system.md",
    "instructions/workspace.md",
    "adapters",
    ".agents/skills",
    ".pi/skills",
    ".pi/settings.json",
  ])
    visit(relative);
  return digest(canonical(inventory));
}

/** Core owns permission and versions. The bundle service owns checked bytes. */
export function registerSkillBundles(register: Register, state: State) {
  const inFlight = new Set<string>();
  const files = (ctx: Pick<ExtensionContext, "cwd">) => {
    const disk = state.disk();
    const core = state.core();
    core.skills.bindDiscoveryReader(() => workspaceDiscoveryHash(ctx.cwd));
    return new SkillBundleFiles(ctx.cwd, {
      retain: (bytes) => disk.writeMaterialBytes(bytes),
      readRetained: (hash) => disk.readMaterialBytes(hash),
    });
  };
  const pin = (
    disk: DiskStorage,
    id: string,
    snapshot: SkillBundleSnapshot,
    before?: SkillBundleSnapshot,
  ) =>
    disk.pinSource("skill-bundle:" + id, [
      ...new Set(
        [...snapshot.manifest.files, ...(before?.manifest.files ?? [])].map(
          (file) => file.sha256,
        ),
      ),
    ]);
  const current = (core: Core, disk: DiskStorage) =>
    requireThat(
      state.core() === core && state.disk() === disk,
      "STORE_UNAVAILABLE",
      "Bundle runtime changed. Inspect the original operation before continuing.",
    );
  const reserve = (core: Core, disk: DiskStorage, request: SkillActivation) => {
    const operationId = "skill:" + request.operation_id;
    const old = disk.coordination.operation(operationId);
    const operationDigest = digest(canonical(request));
    if (old)
      requireThat(
        old.status === "active" &&
          old.runtime_id === core.context.runtime_id &&
          old.epoch === core.context.epoch &&
          old.digest === operationDigest,
        "UNKNOWN_EFFECT",
        "Bundle reservation requires original-operation recovery.",
      );
    return disk.coordination.reserve({
      operation_id: operationId,
      epoch: core.context.epoch,
      session_id: core.context.session_id,
      kind: "skill-bundle",
      digest: operationDigest,
      resources: [
        "workspace:layout",
        "skill:" + request.metadata.skill_id,
        "skill-scope:" + request.metadata.skill_id,
        "bundle-path:" + request.path.toLowerCase(),
      ],
      metadata: { request },
    });
  };
  const confirmDiscovery = (request: SkillActivation, ctx: ExtensionContext) =>
    requireThat(
      request.discovery_hash === workspaceDiscoveryHash(ctx.cwd),
      "REVISION_CONFLICT",
      "Assistant discovery or workspace mapping changed. Review the bundle scope again.",
    );

  const inspectOperation = async (
    operationId: string,
    ctx: ExtensionContext,
  ) => {
    const core = state.core(),
      disk = state.disk(),
      service = files(ctx);
    return disk.withOperation(
      "settle",
      () => {
        current(core, disk);
        const operation = core.skills.operation(operationId);
        if (operation.status === "compensated")
          return { operation, requires_reconciliation: false };
        requireThat(
          !inFlight.has(operationId),
          "STORE_BUSY",
          "The original bundle publication is still in flight.",
        );
        const reservation = disk.coordination.operation("skill:" + operationId);
        if (reservation && reservation.status !== "settled")
          disk.coordination.adopt(reservation.operation_id);
        try {
          service.inspect(operationId);
        } catch (error) {
          if ((error as { code?: string }).code !== "REFERENCE_NOT_FOUND")
            throw error;
          requireThat(
            operation.request.before_manifest !== undefined,
            "SOURCE_MISSING",
            "Original bundle before manifest is unavailable for restored recovery.",
          );
          service.restoreOperation(
            operationId,
            operation.request.path,
            operation.request.before_manifest,
            operation.request.manifest,
          );
        }
        if (operation.receipt) {
          service.settleFromRegistry(operationId, operation.receipt);
          if (reservation && reservation.status !== "settled")
            disk.coordination.release(reservation.operation_id);
          disk.unpinSource("skill-bundle:" + operationId);
          return { receipt: operation.receipt, historical: true };
        }
        const observed = service.snapshot(operation.request.path);
        if (
          observed.manifest.content_hash !==
          operation.request.manifest.content_hash
        ) {
          core.skills.unknown(operationId);
          if (reservation && reservation.status !== "settled")
            disk.coordination.unknown(reservation.operation_id);
          return {
            operation: core.skills.operation(operationId),
            observed_hash: observed.manifest.content_hash,
            requires_reconciliation: true,
          };
        }
        confirmDiscovery(operation.request, ctx);
        const receipt = core.skills.complete(operationId, observed.manifest);
        service.reconcile(operationId, "committed");
        if (reservation && reservation.status !== "settled")
          disk.coordination.release(reservation.operation_id);
        disk.unpinSource("skill-bundle:" + operationId);
        return { receipt, observed_hash: observed.manifest.content_hash };
      },
      { operationId: "skill:" + operationId },
    );
  };

  const publish = async (
    request: SkillActivation,
    ctx: ExtensionContext,
    authorize: (core: Core) => unknown,
    beforeDispatch?: (core: Core, disk: DiskStorage) => void,
  ) => {
    const core = state.core(),
      disk = state.disk(),
      service = files(ctx);
    requireThat(
      !inFlight.has(request.operation_id),
      "STORE_BUSY",
      "Bundle publication is already in flight.",
    );
    const done = state.begin();
    inFlight.add(request.operation_id);
    let admitted = false;
    let dispatchAdmitted = false;
    try {
      return await disk.withOperation(
        "mutate",
        () => {
          current(core, disk);
          confirmDiscovery(request, ctx);
          const actual = service.snapshot(request.path);
          requireThat(
            actual.manifest.content_hash === request.expected_working_hash,
            "APPROVAL_STALE",
            "Working bundle changed after preview.",
          );
          reserve(core, disk, request);
          try {
            authorize(core);
          } catch (error) {
            disk.coordination.release("skill:" + request.operation_id);
            throw error;
          }
          admitted = true;
          let receipt: ReturnType<Core["skills"]["complete"]> | undefined;
          service.publish(request.operation_id, {
            beforePublish: () => {
              current(core, disk);
              confirmDiscovery(request, ctx);
              beforeDispatch?.(core, disk);
              dispatchAdmitted = true;
            },
            beforeCommit: () => {
              current(core, disk);
              confirmDiscovery(request, ctx);
              receipt = core.skills.complete(
                request.operation_id,
                service.snapshot(request.path).manifest,
              );
            },
          });
          requireThat(
            receipt,
            "UNKNOWN_EFFECT",
            "Bundle publication has no verified registration receipt.",
          );
          disk.coordination.release("skill:" + request.operation_id);
          disk.unpinSource("skill-bundle:" + request.operation_id);
          return { receipt, path: request.path };
        },
        { operationId: "skill:" + request.operation_id },
      );
    } catch (error) {
      if (admitted)
        await disk.withOperation(
          "settle",
          () => {
            const observed = service.inspect(request.operation_id);
            if (
              !dispatchAdmitted &&
              observed.operation.status === "planned" &&
              observed.matches_before
            ) {
              core.skills.rejectUndispatched(
                request.operation_id,
                request.expected_working_hash,
              );
              service.compensate(request.operation_id);
              disk.coordination.adopt("skill:" + request.operation_id);
              disk.coordination.release("skill:" + request.operation_id);
              disk.unpinSource("skill-bundle:" + request.operation_id);
              return;
            }
            core.skills.unknown(request.operation_id);
            const reservation = disk.coordination.operation(
              "skill:" + request.operation_id,
            );
            if (reservation && reservation.status !== "settled")
              disk.coordination.unknown(reservation.operation_id);
          },
          { operationId: "skill:" + request.operation_id },
        );
      throw error;
    } finally {
      inFlight.delete(request.operation_id);
      done();
    }
  };

  register(
    "zara_skill_bundle_inspect",
    "Inspect a personal bundle, exact retained version or original pending operation. Reads never activate external edits or execute scripts.",
    z.strictObject({
      skill_id: z.string().uuid().optional(),
      path: BundlePathSchema.optional(),
      operation_id: z.string().optional(),
      revision: z.number().int().positive().optional(),
    }),
    async (input, ctx) => {
      if (input.operation_id)
        return inspectOperation(input.operation_id as string, ctx);
      const core = state.core(),
        disk = state.disk(),
        service = files(ctx);
      return disk.withOperation("read", () => {
        core.authorizeImport();
        if (input.skill_id) {
          const registered = core.skills.inspect(input.skill_id as string);
          const selected = core.skills.version(
            registered.skill_id,
            input.revision as number | undefined,
          );
          const observed = service.snapshot(registered.path);
          return {
            registered,
            selected,
            observed: observed.manifest,
            drift: observed.manifest.content_hash !== registered.content_hash,
            consumers: core.skills.consumers(registered.skill_id),
          };
        }
        requireThat(
          input.path,
          "VALIDATION_ERROR",
          "Select a skill, path or operation.",
        );
        core.skills.inspectCandidate(input.path as string);
        const observed = service.snapshot(input.path as string);
        const registered = core.skills.inspectCandidate(
          input.path as string,
          observed.metadata.skill_id,
        );
        return {
          metadata: observed.metadata,
          observed: observed.manifest,
          registered: registered ?? false,
          ...(registered
            ? {
                drift:
                  registered.content_hash !== observed.manifest.content_hash,
              }
            : {}),
        };
      });
    },
  );

  register(
    "zara_skill_bundle_preview",
    "Prepare exact personal bundle registration, text/script change, rollback or explicit Method-export adoption. Review full selected files through bundle_read, confirm natively, then apply the returned request.",
    z.strictObject({
      operation_id: z.string().min(1).max(200),
      path: BundlePathSchema,
      changes: z
        .array(
          z.strictObject({
            path: BundlePathSchema,
            content: z
              .string()
              .max(256 * 1024)
              .nullable(),
          }),
        )
        .max(128)
        .optional(),
      restore_revision: z.number().int().positive().optional(),
      visibility: z.enum(["workspace", "restricted"]).optional(),
      activity_ids: z.array(z.string()).max(30).optional(),
      general_exposure: z.boolean().optional(),
      adopt_export: SkillActivationSchema.shape.adopt_export,
      consequence: z.string().min(1).max(4000),
      alternatives: z.string().min(1).max(4000),
    }),
    (input, ctx) => {
      const core = state.core(),
        disk = state.disk(),
        service = files(ctx);
      return disk.withOperation("mutate", () => {
        core.authorizeImport();
        core.skills.inspectCandidate(input.path as string);
        const before = service.snapshot(input.path as string);
        const registered = core.skills.inspectCandidate(
          input.path as string,
          before.metadata.skill_id,
        );
        requireThat(
          !(input.changes && input.restore_revision),
          "VALIDATION_ERROR",
          "Choose an edit or retained rollback version.",
        );
        const after = input.restore_revision
          ? service.retained(
              core.skills.version(
                before.metadata.skill_id,
                input.restore_revision as number,
              ).manifest,
            )
          : input.changes
            ? service.withChanges(
                before,
                Object.fromEntries(
                  (
                    input.changes as { path: string; content: string | null }[]
                  ).map((change) => [
                    change.path,
                    change.content === null
                      ? null
                      : Buffer.from(change.content),
                  ]),
                ),
              )
            : before;
        service.plan(
          input.operation_id as string,
          input.path as string,
          before.manifest.content_hash,
          after,
        );
        pin(disk, input.operation_id as string, after, before);
        const request = SkillActivationSchema.parse({
          operation_id: input.operation_id,
          path: input.path,
          metadata: after.metadata,
          manifest: after.manifest,
          visibility: input.visibility ?? registered?.visibility ?? "workspace",
          activity_ids: input.activity_ids ?? registered?.activity_ids ?? [],
          general_exposure:
            input.general_exposure ?? registered?.general_exposure ?? true,
          before_revision: registered?.revision ?? null,
          expected_working_hash: before.manifest.content_hash,
          before_manifest: before.manifest,
          discovery_hash: workspaceDiscoveryHash(ctx.cwd),
          ...(input.adopt_export ? { adopt_export: input.adopt_export } : {}),
        });
        const prepared = core.skills.prepare(
          request,
          input.consequence as string,
          input.alternatives as string,
        );
        return {
          ...prepared,
          next_tool: "zara_skill_bundle_apply",
          instruction:
            "Confirm preview.request_id through zara_confirm, then apply this exact request.",
        };
      });
    },
  );

  register(
    "zara_skill_bundle_apply",
    "Apply a natively confirmed exact bundle request once, or inspect/reconcile an original operation after an uncertain reply. Never executes bundle scripts.",
    z.strictObject({
      request: SkillActivationSchema.optional(),
      preview_ref: z.string().optional(),
      operation_id: z.string().optional(),
    }),
    async (input, ctx) => {
      if (!input.request) {
        requireThat(
          input.operation_id,
          "VALIDATION_ERROR",
          "Select the original operation or confirmed request.",
        );
        return inspectOperation(input.operation_id as string, ctx);
      }
      const request = input.request as SkillActivation;
      const core = state.core();
      try {
        const existing = core.skills.operation(request.operation_id);
        requireThat(
          canonical(existing.request) === canonical(request),
          "IDEMPOTENCY_CONFLICT",
          "Operation identity belongs to another request.",
        );
        return inspectOperation(request.operation_id, ctx);
      } catch (error) {
        if ((error as { code?: string }).code !== "REFERENCE_NOT_FOUND")
          throw error;
      }
      requireThat(
        input.preview_ref,
        "APPROVAL_REQUIRED",
        "Confirm the exact bundle preview first.",
      );
      await state.disk().withOperation("read", () => {
        const preview = core.approvals.read(input.preview_ref as string);
        requireThat(
          preview.payload.exact.request_digest === digest(canonical(request)),
          "APPROVAL_STALE",
          "Native preview names another exact bundle request.",
        );
        core.approvals.verify(
          input.preview_ref as string,
          "skill_activation",
          preview.payload.exact,
        );
      });
      return publish(request, ctx, (currentCore) =>
        currentCore.skills.begin(request, input.preview_ref as string),
      );
    },
  );

  register(
    "zara_skill_bundle_compensation_preview",
    "Prepare exact owner recovery of an unresolved bundle publication to its retained before bytes. Current later edits cause refusal.",
    z.strictObject({
      operation_id: z.string(),
      consequence: z.string().min(1).max(4000),
      alternatives: z.string().min(1).max(4000),
    }),
    (input) =>
      state
        .core()
        .skills.prepareCompensation(
          input.operation_id as string,
          input.consequence as string,
          input.alternatives as string,
        ),
  );
  register(
    "zara_skill_bundle_compensation_apply",
    "Restore the exact original pre-publication bytes under native confirmation and settle its unresolved registration. Never discards later owner edits.",
    z.strictObject({ operation_id: z.string(), preview_ref: z.string() }),
    (input, ctx) => {
      const core = state.core(),
        disk = state.disk(),
        service = files(ctx);
      const operationId = input.operation_id as string;
      return disk.withOperation(
        "settle",
        () => {
          current(core, disk);
          const operation = core.skills.operation(operationId);
          requireThat(
            !operation.receipt,
            "INVALID_TRANSITION",
            "A completed activation uses a new guarded rollback revision.",
          );
          requireThat(
            !inFlight.has(operationId),
            "STORE_BUSY",
            "Original bundle publication remains in flight.",
          );
          const reservation = disk.coordination.operation(
            "skill:" + operationId,
          );
          if (reservation && reservation.status !== "settled")
            disk.coordination.adopt(reservation.operation_id);
          core.skills.verifyCompensation(
            operationId,
            input.preview_ref as string,
          );
          service.compensate(operationId);
          const observed = service.snapshot(operation.request.path);
          const result = core.skills.compensate(
            operationId,
            observed.manifest.content_hash,
            input.preview_ref as string,
          );
          if (reservation && reservation.status !== "settled")
            disk.coordination.release(reservation.operation_id);
          disk.unpinSource("skill-bundle:" + operationId);
          return result;
        },
        { operationId: "skill:" + operationId },
      );
    },
  );

  register(
    "zara_skill_bundle_read",
    "Read a bounded chunk from an exact retained bundle file. A version view preserves relative support/script paths; materialization grants no execution authority.",
    z.strictObject({
      skill_id: z.string().uuid().optional(),
      preview_ref: z.string().optional(),
      revision: z.number().int().positive().optional(),
      path: BundlePathSchema.default("SKILL.md"),
      offset: z.number().int().nonnegative().default(0),
      limit: z.number().int().min(1).max(16000).default(8000),
      invocation_id: z.string().min(1).max(200).optional(),
    }),
    (input, ctx) => {
      const core = state.core(),
        disk = state.disk(),
        service = files(ctx);
      return disk.withOperation("read", () => {
        if (input.preview_ref) {
          const preview = core.approvals.read(input.preview_ref as string);
          requireThat(
            preview.payload.action === "skill_activation",
            "VALIDATION_ERROR",
            "Selected preview is not a personal skill activation.",
          );
          requireThat(
            !input.invocation_id,
            "VALIDATION_ERROR",
            "A pending source preview is not an invocation selection.",
          );
          const request = preview.payload.exact.request as {
            manifest: unknown;
          };
          const manifest = BundleManifestSchema.parse(request.manifest);
          const file = manifest.files.find((item) => item.path === input.path);
          requireThat(
            file,
            "REFERENCE_NOT_FOUND",
            "Selected pending bundle file is unavailable.",
          );
          const points = Array.from(
            new TextDecoder("utf-8", { fatal: true }).decode(
              disk.readMaterialBytes(file.sha256),
            ),
          );
          const offset = input.offset as number,
            limit = input.limit as number;
          return {
            preview_ref: input.preview_ref,
            pending_activation: true,
            skill_id: manifest.skill_id,
            manifest_hash: manifest.content_hash,
            path: file.path,
            offset,
            text: points.slice(offset, offset + limit).join(""),
            has_more: offset + limit < points.length,
            next_offset: offset + limit < points.length ? offset + limit : null,
          };
        }
        requireThat(
          input.skill_id,
          "VALIDATION_ERROR",
          "Select a registered skill or an exact pending preview.",
        );
        const selected = core.skills.version(
          input.skill_id as string,
          input.revision as number | undefined,
        );
        const file = selected.manifest.files.find(
          (file) => file.path === input.path,
        );
        requireThat(
          file,
          "REFERENCE_NOT_FOUND",
          "Selected bundle file is unavailable.",
        );
        const bytes = disk.readMaterialBytes(file.sha256);
        const points = Array.from(
          new TextDecoder("utf-8", { fatal: true }).decode(bytes),
        );
        const offset = input.offset as number,
          limit = input.limit as number;
        if (input.invocation_id) {
          const invocation = core.read(input.invocation_id as string).data as {
            kind?: string;
            data?: {
              selected_skill_versions?: {
                skill_id: string;
                revision: number;
                content_hash: string;
              }[];
            };
          };
          requireThat(
            invocation.kind === "invocation" &&
              invocation.data?.selected_skill_versions?.some(
                (version) =>
                  version.skill_id === selected.skill_id &&
                  version.revision === selected.revision &&
                  version.content_hash === selected.content_hash,
              ),
            "VALIDATION_ERROR",
            "The invocation did not select this exact bundle version.",
          );
        }
        const view = input.invocation_id
          ? service.materialize(
              input.invocation_id as string,
              selected.manifest,
            )
          : undefined;
        if (view) service.verifyView(view);
        return {
          selected,
          path: file.path,
          offset,
          text: points.slice(offset, offset + limit).join(""),
          has_more: offset + limit < points.length,
          next_offset: offset + limit < points.length ? offset + limit : null,
          ...(view ? { version_view: view } : {}),
        };
      });
    },
  );

  register(
    "zara_skill_delegation_preview",
    "Prepare an exact owner delegation for bounded reversible local text maintenance. File location alone grants no Sleep authority.",
    z.strictObject({
      request: SkillDelegationSchema,
      consequence: z.string().min(1).max(4000),
      alternatives: z.string().min(1).max(4000),
    }),
    (input) =>
      state
        .core()
        .skills.prepareDelegation(
          input.request,
          input.consequence as string,
          input.alternatives as string,
        ),
  );
  register(
    "zara_skill_delegation_apply",
    "Apply an exact natively confirmed skill delegation or withdrawal.",
    z.strictObject({ request: SkillDelegationSchema, preview_ref: z.string() }),
    (input) =>
      state.core().skills.delegate(input.request, input.preview_ref as string),
  );

  return {
    bind(ctx: ExtensionContext) {
      files(ctx);
    },
    validateSleep(change: SleepSkillChange, cycle: SleepState) {
      try {
        requireThat(
          change.guard,
          "APPROVAL_REQUIRED",
          "This skill change requires owner review.",
        );
        requireThat(
          !cycle.activity_id || cycle.activity_id === change.guard.activity_id,
          "APPROVAL_REQUIRED",
          "Skill maintenance belongs to another Activity review.",
        );
        const core = state.core();
        const registered = core.skills.inspect(change.guard.skill_id);
        requireThat(
          registered.discovery_hash,
          "APPROVAL_REQUIRED",
          "Skill discovery scope needs owner-reviewed registration.",
        );
        const before = core.skills.version(
          change.guard.skill_id,
          change.guard.before_revision,
        );
        const bytes: Record<string, Uint8Array> = Object.create(null);
        for (const file of before.manifest.files)
          bytes[file.path] = state.disk().readMaterialBytes(file.sha256);
        for (const item of change.changes) {
          requireThat(
            bytes[item.path],
            "APPROVAL_REQUIRED",
            "Automatic maintenance preserves the file inventory.",
          );
          new TextDecoder("utf-8", { fatal: true }).decode(bytes[item.path]);
          bytes[item.path] = Buffer.from(item.content);
        }
        requireThat(
          canonical(skillBundleSnapshot(bytes).manifest) ===
            canonical(change.after_manifest),
          "VALIDATION_ERROR",
          "Changed text does not match the complete proposed bundle.",
        );
        core.skills.validateLocalChange(change.guard, change.after_manifest);
        return {
          allowed: true,
          reason: "Exact delegated local text scope verified.",
        };
      } catch (error) {
        return {
          allowed: false,
          reason:
            error instanceof Error ? error.message : "Skill validation failed.",
          owner_review: true,
        };
      }
    },
    readSleep(
      input: {
        skill_id: string;
        revision?: number;
        path?: string;
        offset?: number;
        limit?: number;
      },
      ctx: ExtensionContext,
    ) {
      const core = state.core(),
        service = files(ctx);
      const registered = core.skills.inspect(input.skill_id);
      const selected = core.skills.version(input.skill_id, input.revision);
      const file = selected.manifest.files.find(
        (file) => file.path === (input.path ?? "SKILL.md"),
      );
      requireThat(
        file,
        "REFERENCE_NOT_FOUND",
        "Selected skill file is unavailable.",
      );
      const snapshot = service.retained(selected.manifest);
      const points = Array.from(
        new TextDecoder("utf-8", { fatal: true }).decode(
          snapshot.bytes[file.path],
        ),
      );
      const offset = input.offset ?? 0,
        limit = Math.min(input.limit ?? 8000, 16000);
      let guard = null;
      if (registered.activity_ids.length === 1) {
        try {
          const currentGuard = core.skills.localGuard(
            input.skill_id,
            registered.activity_ids[0],
          );
          if (currentGuard.before_revision === selected.revision)
            guard = currentGuard;
        } catch {
          /* The exact selection remains available for owner review. */
        }
      }
      const data = {
        manifest: selected.manifest,
        path: file.path,
        offset,
        text: points.slice(offset, offset + limit).join(""),
        has_more: offset + limit < points.length,
        next_offset: offset + limit < points.length ? offset + limit : null,
        guard,
        selection: {
          skill_id: selected.skill_id,
          revision: selected.revision,
          manifest_hash: selected.content_hash,
        },
      };
      return {
        skill_id: selected.skill_id,
        revision: selected.revision,
        manifest_hash: selected.content_hash,
        visibility: registered.visibility,
        data,
      };
    },
    receipt(operationId: string) {
      try {
        const receipt = state.core().skills.operation(operationId).receipt;
        return receipt
          ? {
              operation_id: receipt.operation_id,
              skill_id: receipt.skill_id,
              revision: receipt.revision,
              manifest_hash: receipt.content_hash,
              result_refs: [],
            }
          : null;
      } catch {
        return null;
      }
    },
    async applySleep(
      change: SleepSkillChange,
      proposal: SleepProposal,
      cycle: SleepState,
      ctx: ExtensionContext,
    ) {
      requireThat(
        change.guard,
        "APPROVAL_REQUIRED",
        "A review-only skill proposal cannot dispatch automatically.",
      );
      const core = state.core(),
        disk = state.disk(),
        service = files(ctx);
      const operationId =
        "sleep-skill:" + digest(canonical([cycle.id, proposal.id]));
      const before = service.snapshot(
        core.skills.inspect(change.guard.skill_id).path,
      );
      requireThat(
        before.manifest.content_hash === change.guard.before_hash,
        "REVISION_CONFLICT",
        "Working skill changed before Sleep application.",
      );
      const after = service.withChanges(
        before,
        Object.fromEntries(
          change.changes.map((item) => [item.path, Buffer.from(item.content)]),
        ),
      );
      requireThat(
        canonical(after.manifest) === canonical(change.after_manifest),
        "VALIDATION_ERROR",
        "Proposed skill text does not match its complete manifest.",
      );
      const registered = core.skills.inspect(change.guard.skill_id);
      const request = SkillActivationSchema.parse({
        operation_id: operationId,
        path: registered.path,
        metadata: after.metadata,
        manifest: after.manifest,
        visibility: registered.visibility,
        activity_ids: registered.activity_ids,
        general_exposure: registered.general_exposure,
        before_revision: change.guard.before_revision,
        expected_working_hash: before.manifest.content_hash,
        before_manifest: before.manifest,
        discovery_hash: registered.discovery_hash,
      });
      service.plan(
        operationId,
        registered.path,
        before.manifest.content_hash,
        after,
      );
      pin(disk, operationId, after, before);
      const permit = core.skills.validateLocalChange(
        change.guard,
        after.manifest,
      );
      const result = await publish(
        request,
        ctx,
        (currentCore) =>
          currentCore.skills.beginLocal(request, change.guard, permit),
        (currentCore, currentDisk) =>
          assertSleepSkillAllowed(
            currentDisk,
            currentCore.context,
            change,
            operationId,
          ),
      );
      return {
        operation_id: result.receipt.operation_id,
        skill_id: result.receipt.skill_id,
        revision: result.receipt.revision,
        manifest_hash: result.receipt.content_hash,
        result_refs: [],
      };
    },
  };
}

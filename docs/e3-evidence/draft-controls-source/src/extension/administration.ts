import { z } from "zod";
import type { ExtensionContext } from "@earendil-works/pi-coding-agent";
import { requireThat, StorageActionSchema } from "../core/index.ts";
import type { Core } from "../core/index.ts";
import { fullAccess } from "../storage/index.ts";
import type {
  Administration,
  DiskStorage,
  OutputBoundary,
} from "../storage/index.ts";

type Register = (
  name: string,
  description: string,
  schema: z.ZodType,
  action: (input: Record<string, unknown>, ctx: ExtensionContext) => unknown,
) => void;
export function registerAdministration(
  register: Register,
  a: {
    core: () => Core;
    admin: () => Administration;
    disk: () => DiskStorage | undefined;
    output: () => OutputBoundary | undefined;
    reopen: (ctx: ExtensionContext) => void;
  },
) {
  register(
    "zara_backup",
    "Create and disk-verify a consistent SQLite snapshot, exact raw managed originals/derivatives and versioned JSON export. Full-read trusted setup required. Missing/corrupt blobs refuse completeness. No arbitrary source paths.",
    z.strictObject({ hold_live_pin: z.boolean().optional() }),
    async (p) => {
      const admin = a.admin();
      fullAccess(admin.context);
      const disk = a.disk();
      requireThat(
        disk,
        "STORE_UNAVAILABLE",
        "Current memory is unavailable; restore a verified bundle instead.",
      );
      return admin.backup(disk, (p.hold_live_pin as boolean) ?? false);
    },
  );
  register(
    "zara_backups",
    "List at most 50 designated backup directories under fixed full-read setup. Listing does not prove completeness.",
    z.strictObject({}),
    () => a.admin().list(),
  );
  register(
    "zara_backup_verify",
    "Verify the actual designated bundle, snapshot refs/versions and raw materials under fixed full-read setup.",
    z.strictObject({ backup: z.string() }),
    (p) => {
      const v = a.admin().verify(p.backup as string);
      return { identity: v.identity, complete: true, manifest: v.manifest };
    },
  );
  register(
    "zara_restore_preview",
    "Prepare verified quarantine from an exact designated backup, even when current DB is missing/corrupt. Fixed full-read/write setup. Explain coverage, loss of later DB history and mandatory reconciliation. Original memory remains preserved. Confirm preview with zara_confirm, then zara_restore.",
    z.strictObject({
      backup: z.string(),
      consequence: z.string().min(1).max(4000),
      alternatives: z.string().min(1).max(4000),
    }),
    (p) =>
      a
        .admin()
        .restorePreview(
          p.backup as string,
          p.consequence as string,
          p.alternatives as string,
        ),
  );
  register(
    "zara_restore",
    "Switch only the exact approved verified quarantine. A new authoritative external epoch invalidates old claims/handles/approvals/callbacks. Every restored Work/step must reconcile current-world effects, even with no receipt.",
    z.strictObject({ preview_ref: z.string() }),
    (p, ctx) => {
      try {
        return a.admin().restore(p.preview_ref as string, a.disk());
      } finally {
        a.reopen(ctx);
      }
    },
  );
  register(
    "zara_storage_preview",
    "Preview exact archive/tombstone/library-retain/release of up to ten current records. Tombstone covers ALL retained versions and technical payload copies; reverse dependencies/unknown effects/library pins refuse with addressed reasons. Archive remains discoverable and is not deletion. External backups/transcripts/exports are separate copies.",
    z.strictObject({
      request: StorageActionSchema,
      consequence: z.string().min(1).max(4000),
      alternatives: z.string().min(1).max(4000),
    }),
    (p) =>
      a
        .core()
        .storagePreview(
          p.request,
          p.consequence as string,
          p.alternatives as string,
        ),
  );
  register(
    "zara_storage_apply",
    "Commit only exact natively confirmed archive/tombstone/retention targets after fresh version/dependency/access checks. No frequency-based forgetting. Tombstones cannot return old body through history/index/technical APIs. Blob cleanup is separately bounded and previewed.",
    z.strictObject({ preview_ref: z.string() }),
    (p) => a.core().applyStorage(p.preview_ref as string),
  );
  const disk = () => {
    const d = a.disk();
    requireThat(d, "STORE_UNAVAILABLE", "Current memory unavailable.");
    return d;
  };
  register(
    "zara_cleanup_preview",
    "Prepare exact bounded cleanup of unreferenced/unpinned current managed materials and expired staging. Full-read/write setup; honors pending imports, shared blobs, history and held backups. No semantic forgetting or recursive directory removal.",
    z.strictObject({
      consequence: z.string().min(1).max(4000),
      alternatives: z.string().min(1).max(4000),
    }),
    (p) =>
      a
        .admin()
        .cleanupPreview(
          disk(),
          p.consequence as string,
          p.alternatives as string,
        ),
  );
  register(
    "zara_cleanup",
    "Remove only the exactly confirmed cleanup file set after fresh reference/pin/hash/identity checks. Partial failure remains unknown with retained progress.",
    z.strictObject({ preview_ref: z.string() }),
    (p) => a.admin().cleanup(p.preview_ref as string, disk()),
  );
  register(
    "zara_backup_pin_release_preview",
    "Prepare release of an explicitly held live backup pin only after verifying its independent bundle. This does not delete the bundle.",
    z.strictObject({
      key: z.string(),
      consequence: z.string().min(1).max(4000),
      alternatives: z.string().min(1).max(4000),
    }),
    (p) =>
      a
        .admin()
        .releasePinPreview(
          disk(),
          p.key as string,
          p.consequence as string,
          p.alternatives as string,
        ),
  );
  register(
    "zara_backup_pin_release",
    "Release only the exactly confirmed live pin, preserving the verified independent backup bundle.",
    z.strictObject({ preview_ref: z.string() }),
    (p) => a.admin().releasePin(p.preview_ref as string, disk()),
  );
  const observation = (path: string, ctx: ExtensionContext) => {
    const output = a.output();
    requireThat(
      output,
      "PERMISSION_DENIED",
      "A designated output root is required for file reconciliation.",
    );
    const o = output.inspect(path, ctx.cwd);
    return {
      target: o.target,
      hash: o.hash,
      byte_length: o.byte_length,
      boundary: o.boundary,
    };
  };
  register(
    "zara_recovery_inspect",
    "Inspect actual controlled output for a restored Work/step even with NO receipt/intent. Returns current bytes/hash/length, never author attribution. Does not repeat effects or clear barriers.",
    z.strictObject({
      work_id: z.string(),
      step_id: z.string().nullable().optional(),
      path: z.string(),
    }),
    (p, ctx) => {
      const c = a.core();
      c.authorizeImport();
      const o = observation(p.path as string, ctx);
      const result = c.recoveryInspect(
        p.work_id as string,
        (p.step_id as string) ?? null,
        o,
      );
      return {
        ...result,
        current_text:
          a
            .output()!
            .inspect(p.path as string, ctx.cwd)
            .bytes?.toString("utf8") ?? null,
      };
    },
  );
  register(
    "zara_reconcile_preview",
    "Prepare a named fresh reconciliation after current-world inspection. observed_satisfied requires matching expected_hash and establishes current state, never prior execution/author. risky_repeat explicitly accepts unknown prior execution. Explain disposition and obtain a fresh native decision; no global clearance.",
    z.strictObject({
      work_id: z.string(),
      step_id: z.string().nullable().optional(),
      disposition: z.enum(["observed_satisfied", "risky_repeat"]),
      expected_hash: z.string().nullable(),
      explanation: z.string().min(1).max(4000),
      consequence: z.string().min(1).max(4000),
      alternatives: z.string().min(1).max(4000),
    }),
    (p) =>
      a
        .core()
        .prepareReconciliation(
          p.work_id as string,
          (p.step_id as string) ?? null,
          p.disposition as "observed_satisfied" | "risky_repeat",
          p.expected_hash as string | null,
          p.explanation as string,
          p.consequence as string,
          p.alternatives as string,
        ),
  );
  register(
    "zara_reconcile",
    "Commit the exact approved named reconciliation after rechecking current output bytes, Work revision, epoch, scopes and authority. No file is dispatched/repeated.",
    z.strictObject({ preview_ref: z.string() }),
    (p, ctx) => {
      const c = a.core(),
        v = c.approvals.read(p.preview_ref as string),
        o = v.payload.exact.inspection as { target: string };
      return c.finishReconciliation(
        p.preview_ref as string,
        observation(o.target, ctx),
      );
    },
  );
}

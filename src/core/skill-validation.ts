import { createHash } from "node:crypto";
import { z } from "zod";
import {
  canonical,
  requireThat,
  SelectedSkillRefSchema,
  SkillReferenceSchema,
} from "./contracts.ts";
import type { StoragePort } from "./contracts.ts";
import {
  BundleMetadataSchema,
  SelectedSkillVersionSchema,
  SkillActivationSchema,
  SkillDelegationSchema,
  SkillLocalGuardSchema,
} from "./skills.ts";

const sha = z.string().regex(/^[a-f0-9]{64}$/);
const revision = z.number().int().positive();
const StateSchema = SkillActivationSchema.pick({
  path: true,
  metadata: true,
  visibility: true,
  activity_ids: true,
  general_exposure: true,
  discovery_hash: true,
}).extend({ skill_id: z.string().uuid(), revision, content_hash: sha });
const ReceiptSchema = z.strictObject({
  committed: z.literal(true),
  operation_id: z.string(),
  skill_id: z.string().uuid(),
  revision,
  content_hash: sha,
});
const OperationSchema = z.strictObject({
  operation_id: z.string(),
  request: SkillActivationSchema,
  digest: sha,
  status: z.enum(["prepared", "unknown", "completed", "compensated"]),
  consumer_digest: sha,
  local_guard: SkillLocalGuardSchema.optional(),
  authority: z.enum(["owner", "delegated-sleep"]),
  runtime_id: z.string(),
  session_id: z.string(),
  epoch: z.string(),
  activity_refs: z.array(z.strictObject({ id: z.string(), revision })),
  consumer_refs: z.array(z.strictObject({ id: z.string(), revision })),
  receipt: ReceiptSchema.optional(),
  resolution: z.literal("not-dispatched").optional(),
});
const ReservationSchema = z.strictObject({
  operation_id: z.string(),
  epoch: z.string(),
});

/** Validate durable skill relationships without granting runtime authority or
 * interpreting pending filesystem effects as complete. */
export function validateSkills(storage: StoragePort, materials = true) {
  if (storage.workspace.schema_version < 11) return;
  const bundles = new Map(
    storage
      .all<{
        skill_id: string;
        json: string;
      }>("SELECT skill_id,json FROM skill_bundles")
      .map((row) => {
        const bundle = StateSchema.parse(JSON.parse(row.json));
        requireThat(
          bundle.skill_id === row.skill_id &&
            bundle.metadata.skill_id === row.skill_id,
          "STORE_UNAVAILABLE",
          "Skill bundle identity differs from its canonical key.",
        );
        return [row.skill_id, bundle] as const;
      }),
  );
  const versions = new Map<
    string,
    z.infer<typeof SelectedSkillVersionSchema>
  >();
  for (const row of storage.all<{
    skill_id: string;
    revision: number;
    json: string;
  }>("SELECT skill_id,revision,json FROM skill_versions")) {
    const stored = JSON.parse(row.json);
    const version = SelectedSkillVersionSchema.parse({
      skill_id: stored.skill_id,
      revision: stored.revision,
      content_hash: stored.content_hash,
      manifest: stored.manifest,
    });
    requireThat(
      version.skill_id === row.skill_id &&
        version.revision === row.revision &&
        version.manifest.skill_id === row.skill_id &&
        version.content_hash === version.manifest.content_hash &&
        bundles.has(row.skill_id),
      "STORE_UNAVAILABLE",
      "Retained skill version identity or complete manifest differs.",
    );
    if (stored.hashes !== undefined) z.array(sha).parse(stored.hashes);
    const provenance = z
      .object({
        visibility: z.enum(["workspace", "restricted"]),
        activity_refs: z
          .array(z.strictObject({ id: z.string(), revision }))
          .max(30),
      })
      .parse(stored);
    requireThat(
      provenance.visibility === bundles.get(row.skill_id)!.visibility &&
        new Set(provenance.activity_refs.map((ref) => ref.id)).size ===
          provenance.activity_refs.length,
      "STORE_UNAVAILABLE",
      "Retained skill access provenance differs from its registered authority.",
    );
    const grounds = provenance.activity_refs.map((ref) => ({
      ...ref,
      kind: "activity",
      content_version: undefined as number | undefined,
    }));
    if (stored.adopted_export !== undefined) {
      const adopted = z
        .strictObject({
          ref: SkillActivationSchema.shape.adopt_export.unwrap(),
          blob_ref: sha.optional(),
          original_text: z.string().optional(),
        })
        .parse(stored.adopted_export);
      requireThat(
        adopted.blob_ref !== undefined || adopted.original_text !== undefined,
        "STORE_UNAVAILABLE",
        "Adopted skill version lost its exact original export.",
      );
      grounds.push({
        ...adopted.ref.method_ref,
        kind: "method",
        content_version: adopted.ref.method_ref.content_version,
      });
    }
    for (const ref of grounds) {
      const retained = storage.get<{ json: string }>(
        "SELECT json FROM revisions WHERE id=? AND revision=?",
        ref.id,
        ref.revision,
      );
      const ground = retained && JSON.parse(retained.json);
      requireThat(
        ground &&
          ground.kind === ref.kind &&
          ground.storage !== "tombstone" &&
          (ref.content_version === undefined ||
            ground.data.content_version === ref.content_version),
        "STORE_UNAVAILABLE",
        "Retained skill version lost its exact access or adoption grounds.",
      );
    }
    versions.set(row.skill_id + ":" + row.revision, version);
    if (materials)
      for (const file of version.manifest.files) {
        const bytes =
          storage.readMaterialBytes?.(file.sha256) ??
          Buffer.from(storage.readMaterial(file.sha256));
        requireThat(
          bytes.byteLength === file.length &&
            createHash("sha256").update(bytes).digest("hex") === file.sha256,
          "STORE_UNAVAILABLE",
          "Retained skill material differs from its complete manifest.",
        );
      }
  }
  const paths = [...bundles.values()].map((bundle) =>
    bundle.path.toLowerCase(),
  );
  requireThat(
    new Set(paths).size === paths.length &&
      !paths.some((path, index) =>
        paths.some(
          (other, otherIndex) =>
            index !== otherIndex && path.startsWith(other + "/"),
        ),
      ),
    "STORE_UNAVAILABLE",
    "Registered skill roots have overlapping authority.",
  );
  for (const bundle of bundles.values()) {
    const selected = versions.get(bundle.skill_id + ":" + bundle.revision);
    requireThat(
      selected && selected.content_hash === bundle.content_hash,
      "STORE_UNAVAILABLE",
      "Current skill pointer has no matching retained version.",
    );
    if (materials) {
      const metadataFile = selected.manifest.files.find(
        (file) => file.path === "bundle.json",
      )!;
      const bytes =
        storage.readMaterialBytes?.(metadataFile.sha256) ??
        Buffer.from(storage.readMaterial(metadataFile.sha256));
      const metadata = BundleMetadataSchema.parse(
        JSON.parse(new TextDecoder("utf-8", { fatal: true }).decode(bytes)),
      );
      requireThat(
        canonical(metadata) === canonical(bundle.metadata),
        "STORE_UNAVAILABLE",
        "Current skill metadata differs from its retained bundle bytes.",
      );
    }
  }
  for (const row of storage.all<{ json: string }>(
    "SELECT json FROM records WHERE kind='method' UNION ALL SELECT json FROM revisions WHERE json_extract(json,'$.kind')='method'",
  )) {
    const method = JSON.parse(row.json);
    if (method.storage === "tombstone") continue;
    const references = z
      .array(SkillReferenceSchema)
      .max(30)
      .parse(method.data.skill_refs ?? []);
    for (const ref of references) {
      const bundle = bundles.get(ref.skill_id);
      const selected =
        bundle &&
        versions.get(ref.skill_id + ":" + (ref.revision ?? bundle.revision));
      requireThat(
        selected,
        "STORE_UNAVAILABLE",
        "Method references an unavailable complete skill version.",
      );
    }
  }
  const operations = new Map(
    storage
      .all<{
        operation_id: string;
        json: string;
      }>("SELECT operation_id,json FROM skill_operations")
      .map((row) => {
        const operation = OperationSchema.parse(JSON.parse(row.json));
        requireThat(
          operation.operation_id === row.operation_id &&
            operation.request.operation_id === row.operation_id &&
            operation.request.metadata.skill_id ===
              operation.request.manifest.skill_id &&
            (!operation.request.before_manifest ||
              (operation.request.before_manifest.skill_id ===
                operation.request.manifest.skill_id &&
                operation.request.before_manifest.content_hash ===
                  operation.request.expected_working_hash)) &&
            operation.digest ===
              createHash("sha256")
                .update(canonical(operation.request))
                .digest("hex"),
          "STORE_UNAVAILABLE",
          "Skill operation identity or exact request digest differs.",
        );
        if (operation.request.before_revision !== null)
          requireThat(
            versions.has(
              operation.request.manifest.skill_id +
                ":" +
                operation.request.before_revision,
            ),
            "STORE_UNAVAILABLE",
            "Skill operation lost its exact predecessor version.",
          );
        for (const ref of [
          ...operation.activity_refs.map((ref) => ({
            ...ref,
            kind: "activity",
          })),
          ...operation.consumer_refs.map((ref) => ({ ...ref, kind: "method" })),
        ]) {
          const retained = storage.get<{ json: string }>(
            "SELECT json FROM revisions WHERE id=? AND revision=?",
            ref.id,
            ref.revision,
          );
          const ground = retained && JSON.parse(retained.json);
          requireThat(
            ground &&
              ground.kind === ref.kind &&
              ground.storage !== "tombstone",
            "STORE_UNAVAILABLE",
            "Skill operation lost its exact Activity or Method grounds.",
          );
        }
        if (operation.status === "completed") {
          const receipt = operation.receipt;
          const selected =
            receipt && versions.get(receipt.skill_id + ":" + receipt.revision);
          requireThat(
            receipt &&
              receipt.operation_id === operation.operation_id &&
              receipt.skill_id === operation.request.manifest.skill_id &&
              receipt.revision ===
                (operation.request.before_revision ?? 0) + 1 &&
              selected?.content_hash === receipt.content_hash &&
              receipt.content_hash === operation.request.manifest.content_hash,
            "STORE_UNAVAILABLE",
            "Completed skill operation has no exact retained receipt version.",
          );
        } else
          requireThat(
            !operation.receipt,
            "STORE_UNAVAILABLE",
            "Unresolved skill operation carries a completion receipt.",
          );
        return [row.operation_id, operation] as const;
      }),
  );
  const reservations = new Map(
    storage
      .all<{
        skill_id: string;
        json: string;
      }>("SELECT skill_id,json FROM skill_reservations")
      .map((row) => {
        const reservation = ReservationSchema.parse(JSON.parse(row.json));
        const operation = operations.get(reservation.operation_id);
        requireThat(
          operation &&
            ["prepared", "unknown"].includes(operation.status) &&
            operation.epoch === reservation.epoch &&
            operation.request.manifest.skill_id === row.skill_id,
          "STORE_UNAVAILABLE",
          "Skill reservation has no matching unresolved effect.",
        );
        return [row.skill_id, reservation] as const;
      }),
  );
  for (const operation of operations.values())
    if (["prepared", "unknown"].includes(operation.status))
      requireThat(
        reservations.get(operation.request.manifest.skill_id)?.operation_id ===
          operation.operation_id,
        "STORE_UNAVAILABLE",
        "Unresolved skill effect lost its consumer-scope reservation.",
      );
  for (const row of storage.all<{ skill_id: string; json: string }>(
    "SELECT skill_id,json FROM skill_delegations",
  )) {
    const delegation = SkillDelegationSchema.extend({ revision }).parse(
      JSON.parse(row.json),
    );
    requireThat(
      delegation.skill_id === row.skill_id && bundles.has(row.skill_id),
      "STORE_UNAVAILABLE",
      "Skill delegation has no matching registered bundle.",
    );
  }
  for (const row of storage.all<{ json: string }>(
    "SELECT json FROM experience_rows WHERE kind='invocation' UNION ALL SELECT json FROM experience_versions WHERE json_extract(json,'$.kind')='invocation'",
  )) {
    const invocation = JSON.parse(row.json);
    const selected = z
      .array(SelectedSkillRefSchema)
      .max(30)
      .parse(invocation.data.selected_skill_versions ?? []);
    const references: { skill_id: string; revision?: number }[] = [];
    for (const methodRef of invocation.data.selected_versions) {
      const method = storage.get<{ json: string }>(
        "SELECT json FROM revisions WHERE id=? AND revision=?",
        methodRef.id,
        methodRef.revision,
      );
      requireThat(
        method,
        "STORE_UNAVAILABLE",
        "Skill selection lost its exact Method version.",
      );
      references.push(...(JSON.parse(method.json).data.skill_refs ?? []));
    }
    requireThat(
      new Set(selected.map((version) => version.skill_id)).size ===
        selected.length &&
        selected.length === new Set(references.map((ref) => ref.skill_id)).size,
      "STORE_UNAVAILABLE",
      "Invocation skill selection differs from its Method closure.",
    );
    for (const ref of selected) {
      const registered = versions.get(ref.skill_id + ":" + ref.revision);
      requireThat(
        registered?.content_hash === ref.content_hash &&
          references.some((reference) => reference.skill_id === ref.skill_id) &&
          references
            .filter((reference) => reference.skill_id === ref.skill_id)
            .every(
              (reference) =>
                reference.revision === undefined ||
                reference.revision === ref.revision,
            ),
        "STORE_UNAVAILABLE",
        "Invocation references an unavailable or different complete skill version.",
      );
    }
  }
}

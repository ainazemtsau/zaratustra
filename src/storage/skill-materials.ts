import { BundleManifestSchema } from "../core/index.ts";

/** Only typed canonical skill fields introduce file-inventory material references.
 * Ordinary document inventories can contain hashes without retained bytes. */
export function skillMaterialHashes(
  collection: string,
  value: unknown,
): string[] {
  const row = value as {
    kind?: string;
    manifest?: unknown;
    hashes?: unknown[];
    request?: { manifest?: unknown; before_manifest?: unknown };
    payload?: {
      action?: string;
      exact?: { request?: { manifest?: unknown; before_manifest?: unknown } };
    };
  };
  const manifests: unknown[] = [];
  const hashes = new Set<string>();
  if (collection === "skill_versions") {
    manifests.push(row.manifest);
    for (const hash of row.hashes ?? [])
      if (typeof hash === "string" && /^[a-f0-9]{64}$/.test(hash))
        hashes.add(hash);
  }
  const request =
    collection === "skill_operations"
      ? row.request
      : collection === "intents" &&
          row.kind === "preview" &&
          row.payload?.action === "skill_activation"
        ? row.payload.exact?.request
        : undefined;
  if (request) {
    manifests.push(request.manifest);
    if (request.before_manifest) manifests.push(request.before_manifest);
  }
  for (const manifest of manifests)
    for (const file of BundleManifestSchema.parse(manifest).files)
      hashes.add(file.sha256);
  return [...hashes];
}

import { execFileSync } from "node:child_process";
import { existsSync, lstatSync, readFileSync, readdirSync } from "node:fs";
import { join, resolve } from "node:path";
import { z } from "zod";
import { WorkspaceProductSchema, type WorkspaceProduct } from "./contracts.ts";
import {
  canonicalWorkspaceValue,
  workspaceError,
  workspaceHash,
} from "./files.ts";

function productInventory(packageRoot: string, roots: string[]) {
  const inventory: { path: string; sha256: string }[] = [];
  const visit = (path: string) => {
    if (path === "dist/build-manifest.json") return;
    const absolute = join(packageRoot, path);
    const info = lstatSync(absolute);
    if (info.isSymbolicLink())
      throw new Error("Product resources must be ordinary package files.");
    if (info.isDirectory()) {
      for (const name of readdirSync(absolute).sort()) visit(`${path}/${name}`);
      return;
    }
    if (info.isFile())
      inventory.push({
        path,
        sha256: workspaceHash(readFileSync(absolute)),
      });
  };
  for (const directory of roots)
    if (existsSync(join(packageRoot, directory))) visit(directory);
  return inventory;
}

const BuildManifestSchema = z.strictObject({
  format: z.literal(1),
  source_revision: z.string().regex(/^sha256:[a-f0-9]{64}$/),
  runtime_revision: z.string().regex(/^sha256:[a-f0-9]{64}$/),
  files: z.array(
    z.strictObject({
      path: z.string(),
      sha256: z.string().regex(/^[a-f0-9]{64}$/),
    }),
  ),
});

/** Source identity is portable across Pi source loading and verified compiled CLI. */
export function getWorkspaceProduct(
  packageRoot: string,
  options: { runtime?: "source" | "compiled" } = {},
): WorkspaceProduct {
  packageRoot = resolve(packageRoot);
  const packageJSON = JSON.parse(
    readFileSync(join(packageRoot, "package.json"), "utf8"),
  ) as { version: string };
  const sourceRoots = ["package.json", "src", "instructions", "skills"];
  const inventory = productInventory(packageRoot, sourceRoots);
  const revision =
    "sha256:" + workspaceHash(canonicalWorkspaceValue(inventory));
  const runtime =
    options.runtime ??
    (import.meta.url.endsWith(".js") ? "compiled" : "source");
  if (runtime === "compiled") {
    const manifestPath = join(packageRoot, "dist/build-manifest.json");
    if (!existsSync(manifestPath))
      workspaceError(
        "RUNTIME_UNSUPPORTED",
        "The compiled product needs a current build manifest. Build the package before using the CLI.",
      );
    const manifest = BuildManifestSchema.parse(
      JSON.parse(readFileSync(manifestPath, "utf8")),
    );
    const files = productInventory(packageRoot, ["dist"]);
    if (
      manifest.source_revision !== revision ||
      manifest.runtime_revision !==
        "sha256:" + workspaceHash(canonicalWorkspaceValue(files)) ||
      canonicalWorkspaceValue(manifest.files) !== canonicalWorkspaceValue(files)
    )
      workspaceError(
        "REVISION_CONFLICT",
        "Compiled runtime, build manifest and current product sources differ. Rebuild before using the CLI.",
      );
  }
  if (
    canonicalWorkspaceValue(productInventory(packageRoot, sourceRoots)) !==
    canonicalWorkspaceValue(inventory)
  )
    workspaceError(
      "REVISION_CONFLICT",
      "Product sources changed during fingerprint capture.",
    );
  return WorkspaceProductSchema.parse({
    version: packageJSON.version,
    revision,
  });
}

/** A Git commit identifies an install source only for a clean exact checkout. */
export function cleanProductSourceRevision(packageRoot: string) {
  try {
    const git = (...arguments_: string[]) =>
      execFileSync("git", ["-C", packageRoot, ...arguments_], {
        encoding: "utf8",
        stdio: ["ignore", "pipe", "pipe"],
        windowsHide: true,
      }).trim();
    if (
      resolve(git("rev-parse", "--show-toplevel")).toLowerCase() !==
        resolve(packageRoot).toLowerCase() ||
      git("status", "--porcelain") !== ""
    )
      return undefined;
    const revision = git("rev-parse", "HEAD");
    return /^[a-f0-9]{40}$/.test(revision) ? revision : undefined;
  } catch {
    return undefined;
  }
}

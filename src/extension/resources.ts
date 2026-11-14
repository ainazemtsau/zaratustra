import { existsSync, readFileSync } from "node:fs";
import { resolve } from "node:path";
import { getWorkspaceProduct } from "../workspace/index.ts";

/** Preserve the same build-input provenance in source and installed packages. */
export function readDependencyLock(packageRoot: string): Buffer {
  const source = resolve(packageRoot, "package-lock.json");
  if (existsSync(source)) return readFileSync(source);

  // npm does not ship the root lockfile. The build retains its exact bytes
  // under an ordinary resource name, covered by the compiled inventory.
  getWorkspaceProduct(packageRoot, { runtime: "compiled" });
  return readFileSync(resolve(packageRoot, "dist/dependency-lock.json"));
}

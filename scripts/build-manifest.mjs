import { createHash } from "node:crypto";
import { execFileSync } from "node:child_process";
import {
  copyFileSync,
  existsSync,
  lstatSync,
  mkdirSync,
  readFileSync,
  readdirSync,
  writeFileSync,
} from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const root = fileURLToPath(new URL("..", import.meta.url));
const hash = (bytes) => createHash("sha256").update(bytes).digest("hex");

function inventory(paths, excluded = new Set()) {
  const files = [];
  const visit = (path) => {
    if (excluded.has(path)) return;
    const absolute = join(root, path);
    const info = lstatSync(absolute);
    if (info.isSymbolicLink())
      throw new Error(
        "Build inputs and outputs must be ordinary package files.",
      );
    if (info.isDirectory()) {
      for (const name of readdirSync(absolute).sort()) visit(`${path}/${name}`);
    } else if (info.isFile()) {
      files.push({ path, sha256: hash(readFileSync(absolute)) });
    }
  };
  for (const path of paths) if (existsSync(join(root, path))) visit(path);
  return files;
}

// Inventory fields are emitted in canonical key order for the runtime verifier.
const sourcePaths = ["package.json", "src", "instructions", "skills"];
const sourceRevision = () =>
  "sha256:" + hash(JSON.stringify(inventory(sourcePaths)));
const dependencyLock = readFileSync(join(root, "package-lock.json"));
const before = sourceRevision();
execFileSync(
  process.execPath,
  [join(root, "node_modules/typescript/bin/tsc"), "-p", "tsconfig.build.json"],
  { cwd: root, stdio: "inherit", windowsHide: true },
);

for (const file of inventory(["src"])) {
  if (!file.path.endsWith(".mjs")) continue;
  const target = join(root, "dist", file.path.slice("src/".length));
  mkdirSync(dirname(target), { recursive: true });
  copyFileSync(join(root, file.path), target);
}
writeFileSync(join(root, "dist/dependency-lock.json"), dependencyLock, {
  flush: true,
});
if (
  sourceRevision() !== before ||
  !readFileSync(join(root, "package-lock.json")).equals(dependencyLock)
)
  throw new Error(
    "Product sources or dependency lock changed during compilation. Run build again after edits settle.",
  );

const files = inventory(["dist"], new Set(["dist/build-manifest.json"]));
writeFileSync(
  join(root, "dist/build-manifest.json"),
  JSON.stringify(
    {
      format: 1,
      source_revision: before,
      runtime_revision: "sha256:" + hash(JSON.stringify(files)),
      files,
    },
    null,
    2,
  ) + "\n",
  { flush: true },
);

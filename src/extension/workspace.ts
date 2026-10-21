import type { ExtensionContext } from "@earendil-works/pi-coding-agent";
import {
  existsSync,
  lstatSync,
  mkdirSync,
  readFileSync,
  writeFileSync,
} from "node:fs";
import { dirname, isAbsolute, join, resolve } from "node:path";
import { requireThat } from "../core/index.ts";
import { resolvedLocation, safePath, within } from "../storage/index.ts";

/** Native cwd and trust choose defaults; model arguments never select memory. */
export function workspacePaths(
  ctx: Pick<ExtensionContext, "cwd" | "isProjectTrusted">,
  packageRoot: string,
  agentDir: string,
  env: NodeJS.ProcessEnv = process.env,
) {
  const explicit = env.ZARATUSTRA_HOME !== undefined;
  if (explicit) {
    requireThat(
      !!env.ZARATUSTRA_HOME && isAbsolute(env.ZARATUSTRA_HOME),
      "STORE_UNAVAILABLE",
      "ZARATUSTRA_HOME must be an absolute trusted setup path; no fallback memory was opened.",
    );
    return {
      profile: "explicit" as const,
      home: env.ZARATUSTRA_HOME,
      backup: env.ZARATUSTRA_BACKUP_ROOT,
      output: env.ZARATUSTRA_OUTPUT_ROOT,
      imports: env.ZARATUSTRA_IMPORT_ROOTS ?? "[]",
    };
  }
  requireThat(
    ![
      "ZARATUSTRA_BACKUP_ROOT",
      "ZARATUSTRA_OUTPUT_ROOT",
      "ZARATUSTRA_IMPORT_ROOTS",
    ].some((key) => env[key] !== undefined),
    "STORE_UNAVAILABLE",
    "Partial directory configuration requires an explicit absolute ZARATUSTRA_HOME. Unset all directory overrides to use this project's .local defaults; no fallback memory was opened.",
  );
  requireThat(
    ctx.isProjectTrusted(),
    "PERMISSION_DENIED",
    "Trust this project through native Pi before Zaratustra creates or opens .local memory.",
  );
  const project = resolve(ctx.cwd),
    local = join(project, ".local");
  const paths = ["memory", "imports", "output", "backups"].map((name) =>
    join(local, name),
  );
  // Validate the whole layout before the first write. Links/junctions and device
  // aliases cannot silently select another project's memory or package cache.
  safePath(project, local);
  for (const path of paths) {
    safePath(project, path);
    const real = resolvedLocation(path);
    requireThat(
      [packageRoot, agentDir, join(project, ".pi")].every(
        (blocked) =>
          !within(resolvedLocation(blocked), real) &&
          !within(real, resolvedLocation(blocked)),
      ),
      "PERMISSION_DENIED",
      "Project defaults must be outside package and Pi configuration/cache storage.",
    );
    requireThat(
      !existsSync(path) || lstatSync(path).isDirectory(),
      "PERMISSION_DENIED",
      "Each project-local root must be an ordinary directory.",
    );
  }
  for (let parent = project; ; parent = dirname(parent)) {
    requireThat(
      !existsSync(join(parent, "zara.sqlite")) &&
        !(
          existsSync(join(parent, "active.json")) &&
          existsSync(join(parent, "workspace.json"))
        ),
      "PERMISSION_DENIED",
      "Project defaults cannot be created inside an existing memory/control directory.",
    );
    if (dirname(parent) === parent) break;
  }
  const ignore = safePath(project, join(local, ".gitignore"));
  if (existsSync(ignore)) {
    const stat = lstatSync(ignore);
    requireThat(
      stat.isFile() && stat.nlink === 1 && stat.size <= 64000,
      "PERMISSION_DENIED",
      "The .local ignore file must be a bounded ordinary file.",
    );
    // Leading whitespace is meaningful to Git. Accept only exact blanket rules;
    // trimming could mistake " *" for protection of every local file.
    const lines = readFileSync(ignore, "utf8").split(/\r?\n/);
    requireThat(
      lines.some((line) => line === "*" || line === "/*") &&
        !lines.some((line) => line.startsWith("!")),
      "PERMISSION_DENIED",
      "Existing .local/.gitignore does not protect all local data. Preserve it and configure protection before retrying; Zaratustra will not overwrite it.",
    );
  } else {
    mkdirSync(local, { recursive: true });
    // Exclusive creation preserves existing user content, including races.
    writeFileSync(ignore, "*\n", { flag: "wx" });
  }
  for (const path of paths) mkdirSync(path, { recursive: true });
  return {
    profile: "project-local" as const,
    home: paths[0],
    imports: JSON.stringify([paths[1]]),
    output: paths[2],
    backup: paths[3],
  };
}

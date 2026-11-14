import type { ExtensionContext } from "@earendil-works/pi-coding-agent";
import { existsSync, lstatSync, mkdirSync } from "node:fs";
import { dirname, isAbsolute, join, resolve } from "node:path";
import { requireThat } from "../core/index.ts";
import { resolvedLocation, safePath, within } from "../storage/index.ts";
import {
  loadWorkspaceGuidance,
  readWorkspaceManifest,
} from "../workspace/index.ts";

export const PORTABLE_GUIDANCE_SECTIONS = [
  "zaratustra_system",
  "zaratustra_workspace",
  "zaratustra_activity",
] as const;

export function assertPortableRevision(project: string, revision: string) {
  const manifest = readWorkspaceManifest(project);
  requireThat(
    !manifest || manifest.product.revision === revision,
    "PRODUCT_VERSION_MISMATCH",
    "Installed workspace guidance and the active Pi extension have different product revisions. Inspect the workspace update or attach the matching package before managed processing.",
  );
  if (manifest) loadWorkspaceGuidance(project, { product_revision: revision });
}

/** Only explicit owner guidance is loaded here. Core snapshots remain data. */
export function portableGuidance(
  ctx: Pick<ExtensionContext, "cwd" | "isProjectTrusted">,
  productRevision: string,
  activityId?: string,
) {
  if (!ctx.isProjectTrusted()) return { sections: {}, warnings: [], files: [] };
  const guidance = loadWorkspaceGuidance(ctx.cwd, {
    core_activity_id: activityId,
    product_revision: productRevision,
  });
  if (!guidance) return { sections: {}, warnings: [], files: [] };
  const sections: Record<string, string> = {};
  const files: { path: string; sha256: string }[] = [];
  for (const [section, file] of [
    ["zaratustra_system", guidance.system],
    ["zaratustra_workspace", guidance.workspace],
    ["zaratustra_activity", guidance.activity],
  ] as const) {
    if (!file) continue;
    sections[section] =
      `<${section}>\nCurrent guidance from ${file.path}\nSHA-256 ${file.sha256}\n${file.text}\n</${section}>`;
    files.push({ path: file.path, sha256: file.sha256 });
  }
  if (guidance.warnings.length)
    sections.zaratustra_activity = `<zaratustra_activity>\nActivity guidance is unresolved. ${guidance.warnings.join(" ")}\n</zaratustra_activity>`;
  return { sections, warnings: guidance.warnings, files };
}

/** Section patches leave every host and foreign extension message intact. */
export function replacePortableGuidance<T extends { role: string }>(
  messages: T[],
  sections: Record<string, string>,
) {
  return [
    ...messages,
    {
      role: "system" as const,
      content: "",
      sections: Object.fromEntries(
        PORTABLE_GUIDANCE_SECTIONS.map((key) => [key, sections[key] ?? null]),
      ),
      timestamp: Date.now(),
    },
  ];
}

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
  for (let parent = local; ; parent = dirname(parent)) {
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
  // Git tracking/exclusion policy belongs to the owner. Never inspect, create,
  // change or remove ignore files to make project startup succeed.
  for (const path of paths) mkdirSync(path, { recursive: true });
  return {
    profile: "project-local" as const,
    home: paths[0],
    imports: JSON.stringify([paths[1]]),
    output: paths[2],
    backup: paths[3],
  };
}

#!/usr/bin/env node
import { parseArgs } from "node:util";
import { pathToFileURL } from "node:url";
import {
  WorkspaceInstaller,
  attachPi,
  inspectPiAttachment,
  inspectWorkspace,
  readManagedWorkspaceContext,
} from "../workspace/index.ts";

export const WORKSPACE_HELP = `Zaratustra portable workspace

zaratustra workspace init --path <directory>
zaratustra workspace inspect --path <directory>
zaratustra workspace update --path <directory>
zaratustra workspace update --path <directory> --apply <exact-plan-id>
zaratustra workspace inspect --path <directory> --operation <exact-plan-id>
zaratustra workspace update --path <directory> --operation <exact-plan-id> --recover complete|rollback
zaratustra adapter attach pi --path <directory> [--source <local-package-path-or-commit-pinned-source>]
zaratustra adapter inspect pi --path <directory> --operation <attachment-operation-id>
zaratustra adapter attach pi --path <directory> --operation <attachment-operation-id>

Initialization works before Pi is installed. Update first creates an exact plan.
Review conflicts and before/after bytes before applying its returned plan ID.
Keep external editors closed for affected files during the publication window.
After interruption inspect the original operation before explicit recovery.
Pi attachment uses native local installation and requires native project trust.
CLI installation acceptance supplies no protected Core or Sleep authority.
Existing deployments with another managed home use --managed-home <absolute-existing-home>.
The plan binds that home's control identity and epoch for apply and recovery.
`;

export function runWorkspaceCLI(arguments_: string[]) {
  const { values, positionals } = parseArgs({
    args: arguments_,
    allowPositionals: true,
    strict: true,
    options: {
      path: { type: "string" },
      apply: { type: "string" },
      operation: { type: "string" },
      recover: { type: "string" },
      source: { type: "string" },
      "managed-home": { type: "string" },
      help: { type: "boolean", short: "h" },
    },
  });
  if (values.help || positionals.length === 0) return WORKSPACE_HELP;
  if (!values.path)
    throw new Error("Select a workspace with --path <directory>.");
  if (positionals.join(" ") === "adapter attach pi") {
    if (values.apply || values.recover)
      throw new Error(
        "Installation recovery options apply to workspace operations.",
      );
    return attachPi(values.path, {
      source: values.source,
      operation_id: values.operation,
      managedHome: values["managed-home"],
    });
  }
  if (positionals.join(" ") === "adapter inspect pi") {
    if (!values.operation || values.source || values.apply || values.recover)
      throw new Error(
        "Inspect the original attachment with --operation <attachment-operation-id>.",
      );
    return inspectPiAttachment(values.path, values.operation, {
      managedHome: values["managed-home"],
    });
  }
  if (
    positionals.length !== 2 ||
    positionals[0] !== "workspace" ||
    !["init", "inspect", "update"].includes(positionals[1]) ||
    values.source
  )
    throw new Error("Use a command shown in --help.");
  const command = positionals[1];
  if (command === "inspect" && !values.operation) {
    if (values.apply || values.recover)
      throw new Error(
        "Inspect reads state. Use workspace update to apply or recover.",
      );
    const inspection = inspectWorkspace(values.path);
    return values["managed-home"]
      ? {
          ...inspection,
          managed_context: readManagedWorkspaceContext(
            values.path,
            values["managed-home"],
          ),
        }
      : inspection;
  }
  const installer = new WorkspaceInstaller(values.path, {
    managedHome: values["managed-home"],
  });
  if (values.operation) {
    if (values.apply || command === "init")
      throw new Error("Use inspect or update with one original operation ID.");
    if (command === "inspect") {
      if (values.recover)
        throw new Error("Use update for explicit operation recovery.");
      return installer.inspectOperation(values.operation);
    }
    if (values.recover !== "complete" && values.recover !== "rollback")
      throw new Error(
        "Choose --recover complete or --recover rollback after inspection.",
      );
    return installer.recover(values.operation, values.recover);
  }
  if (values.recover)
    throw new Error("Recovery requires the original --operation ID.");
  if (values.apply) {
    if (command !== "update")
      throw new Error("Use workspace update --apply <plan-id>.");
    return installer.apply(values.apply);
  }
  return command === "init" ? installer.initialize() : installer.plan();
}

if (
  process.argv[1] &&
  import.meta.url === pathToFileURL(process.argv[1]).href
) {
  try {
    const result = runWorkspaceCLI(process.argv.slice(2));
    process.stdout.write(
      typeof result === "string"
        ? result
        : JSON.stringify(result, null, 2) + "\n",
    );
  } catch (error) {
    const value = error as Error & { code?: string };
    process.stderr.write(
      JSON.stringify({
        error: value.code ?? "WORKSPACE_ERROR",
        message: value.message,
      }) + "\n",
    );
    process.exitCode = 1;
  }
}

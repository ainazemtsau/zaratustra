import {
  GitSynchronizer,
  loadSyncBinding,
  type SyncOptions,
  type SyncStatus,
} from "../storage/index.ts";
import { z } from "zod";

export const SyncToolSchema = z.strictObject({
  action: z.enum(["status", "retry"]).default("status"),
});
export type PublicSyncStatus = Omit<SyncStatus, "workspace"> & {
  workspace?: { workspaceId: string; epoch: string };
};
/** Global revision is internal bookkeeping, not a lower-scope record count. */
export function publicSyncStatus(status: SyncStatus): PublicSyncStatus {
  const { workspace, ...rest } = status;
  return {
    ...rest,
    ...(workspace
      ? {
          workspace: {
            workspaceId: workspace.workspaceId,
            epoch: workspace.epoch,
          },
        }
      : {}),
  };
}
export interface GitAutosave {
  readonly configured: boolean;
  request(reason?: string): void;
  action(input: unknown): Promise<PublicSyncStatus>;
  close(): Promise<PublicSyncStatus | undefined>;
}
/** Host integration: binding comes from trusted setup, never tool arguments. */
export function createGitAutosave(
  options: Omit<SyncOptions, "binding">,
): GitAutosave {
  let sync: GitSynchronizer | undefined;
  let unavailable = "Private Git autosave has not been bound by trusted setup.";
  try {
    const binding = loadSyncBinding(options.runtimeRoot);
    if (binding) sync = new GitSynchronizer({ ...options, binding });
  } catch {
    unavailable =
      "Trusted Git autosave configuration is unavailable or invalid; memory remains usable and no destination was approved.";
  }
  if (!sync)
    return {
      configured: false,
      request: () => {},
      action: async (input) => {
        SyncToolSchema.parse(input);
        return {
          format: 1,
          code: "UNCONFIGURED",
          pending: true,
          updatedAt: new Date().toISOString(),
          message: unavailable,
        };
      },
      close: async () => undefined,
    };
  const active = sync;
  active.start();
  return {
    configured: true,
    request: (reason) => active.request(reason),
    action: async (input) => {
      const request = SyncToolSchema.parse(input);
      return publicSyncStatus(
        request.action === "retry" ? await active.flush() : active.status(),
      );
    },
    close: async () => publicSyncStatus(await active.close()),
  };
}

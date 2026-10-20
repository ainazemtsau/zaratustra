import type { ExtensionContext } from "@earendil-works/pi-coding-agent";
import { requireThat } from "../core/index.ts";
/** UI availability is not identity. RPC/SDK dialog responses require trusted setup registration. */
export function dialogAuthority(
  ctx: Pick<ExtensionContext, "mode" | "hasUI">,
  controller: string | undefined,
) {
  requireThat(
    ctx.hasUI && (ctx.mode === "tui" || !!controller),
    "APPROVAL_REQUIRED",
    "Native confirmation requires the trusted local TUI channel or an explicitly registered synthetic controller. Unregistered RPC/SDK UI grants no owner authority.",
  );
  return {
    channel_identity: controller ?? "trusted-local-desktop-owner",
    principal: controller
      ? "synthetic-controller:" + controller
      : "trusted-local-desktop-owner",
    mode: ctx.mode,
  };
}

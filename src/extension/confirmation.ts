import type { ExtensionContext } from "@earendil-works/pi-coding-agent";
import type { JsonObject } from "../core/index.ts";
import { renderApproval } from "./preview.ts";

type Proposal = Parameters<typeof renderApproval>[0];

// Keep terminal control sequences visible as data, never executable styling/input.
export const approvalText = (s: string) =>
  s.replace(
    /[\x00-\x09\x0b-\x1f\x7f\u202a-\u202e\u2066-\u2069]/g,
    (c) => `\\u${c.charCodeAt(0).toString(16).padStart(4, "0")}`,
  );
const short = (value: unknown, size: number) => {
  const chars = Array.from(
    approvalText(String(value ?? "")).replace(/\s+/g, " "),
  );
  return chars.length > size
    ? chars.slice(0, size - 1).join("") + "…"
    : chars.join("");
};

/** Presentation only: no new authority, digest, proposal or inferred execution. */
export function approvalSummary(p: Proposal): string {
  const e = p.exact;
  let action: string;
  if (p.action === "managed_file") {
    action = `${e.before_hash === null ? "Create file" : "Replace/edit file"}: ${short(e.target, 100)}`;
  } else if (p.action === "commit") {
    const ops = (e.ops ?? []) as JsonObject[];
    action =
      `${ops.length} record operation(s):\n` +
      ops
        .slice(0, 3)
        .map(
          (op) =>
            `• ${short(String(op.op).replaceAll("_", " "), 30)}${op.title ? `: ${short(op.title, 55)}` : ""}`,
        )
        .join("\n");
    if (ops.length > 3) action += `\n+ ${ops.length - 3} more (see details)`;
  } else {
    action = `${short(p.action.replaceAll("_", " "), 40)}: ${short(e.action ?? e.work_title ?? e.backup ?? "selected resources", 100)}`;
  }
  return `${action}\n${short(p.consequence, 160)}\nD: full details · No/Esc: cancel\nApplies only to this exact proposal.`;
}

export function requiresApprovalReview(p: Proposal): boolean {
  if (p.consequence.length > 160) return true;
  if (p.action === "managed_file") return String(p.exact.target).length > 100;
  if (p.action !== "commit") return true;
  const ops = (p.exact.ops ?? []) as JsonObject[];
  return (
    ops.length > 3 ||
    ops.some(
      (op) =>
        String(op.title ?? "").length > 55 ||
        !["create_record", "import_evidence"].includes(String(op.op)),
    )
  );
}

/** Preserve content/indentation; add only visual wrapping and page boundaries.
 * Six lines of <=24 code points also fit ordinary narrow/wide-character terminals.
 */
export function approvalPages(text: string): string[] {
  const lines: string[] = [];
  for (const line of approvalText(text).split("\n")) {
    const chars = Array.from(line);
    if (!chars.length) lines.push("");
    for (let start = 0; start < chars.length; start += 24)
      lines.push(chars.slice(start, start + 24).join(""));
  }
  const pages: string[] = [];
  for (let start = 0; start < lines.length; start += 6)
    pages.push(lines.slice(start, start + 6).join("\n"));
  return pages;
}

async function review(
  ctx: ExtensionContext,
  details: string,
): Promise<boolean> {
  const pages = approvalPages(details);
  let page = 0;
  for (;;) {
    const next =
      page + 1 < pages.length ? "Next page" : "Return to confirmation";
    const choice = await ctx.ui.select(
      `Exact proposal details — ${page + 1}/${pages.length}\n${pages[page]}`,
      [next, ...(page ? ["Previous page"] : []), "Cancel proposal"],
    );
    if (choice === "Next page") page++;
    else if (choice === "Previous page") page--;
    else return choice === "Return to confirmation";
  }
}

/** Only ctx.ui.confirm's actual affirmative answer can authorize the proposal.
 * D dismisses the pending native dialog to review details, never approves it.
 * Non-TUI clients retain the full existing native-dialog presentation.
 */
export async function confirmApproval(
  ctx: ExtensionContext,
  p: Proposal,
): Promise<boolean> {
  const details = approvalText(renderApproval(p));
  if (ctx.mode !== "tui")
    return ctx.ui.confirm("Confirm these exact changes?", details);
  if (requiresApprovalReview(p) && !(await review(ctx, details))) return false;
  for (;;) {
    const controller = new AbortController();
    let detailsRequested = false;
    const off = ctx.ui.onTerminalInput((data) => {
      if (data !== "d" && data !== "D") return;
      detailsRequested = true;
      controller.abort();
      return { consume: true };
    });
    let yes: boolean;
    try {
      yes = await ctx.ui.confirm("Allow these changes?", approvalSummary(p), {
        signal: controller.signal,
      });
    } finally {
      off();
    }
    if (!detailsRequested) return yes;
    if (!(await review(ctx, details))) return false;
  }
}

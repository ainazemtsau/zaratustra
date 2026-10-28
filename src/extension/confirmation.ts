import type { ExtensionContext } from "@earendil-works/pi-coding-agent";
import { askQuestion } from "./questions.ts";
import { renderApproval } from "./preview.ts";

type Proposal = Parameters<typeof renderApproval>[0];

export const approvalText = (s: string) =>
  s.replace(
    /[\x00-\x09\x0b-\x1f\x7f-\x9f\u202a-\u202e\u2066-\u2069]/g,
    (c) => `\\u${c.charCodeAt(0).toString(16).padStart(4, "0")}`,
  );

/** Complete finite projection for the ordinary chat transcript, never a dialog. */
export const approvalDetails = (p: Proposal) => approvalText(renderApproval(p));

/** The caller first publishes full details in chat and observes Pi's message_end.
 * Choice/custom text is not authority. Only the separate native confirm result
 * may approve; custom text instead declines this immutable proposal.
 */
export async function confirmApproval(
  ctx: ExtensionContext,
  p: Proposal,
  onCustomAnswer: (text: string) => void = () => {},
): Promise<boolean> {
  if (ctx.mode !== "tui")
    return ctx.ui.confirm("Confirm these exact changes?", approvalDetails(p));
  const ru = /[а-яё]/i.test(p.consequence);
  const confirm = ru ? "Подтвердить" : "Confirm";
  const answer = await askQuestion(ctx, ru ? "Что сделать?" : "Next action?", [
    confirm,
    ru ? "Отмена" : "Cancel",
  ]);
  if (answer.kind === "custom") {
    onCustomAnswer(answer.answer);
    return false;
  }
  if (answer.kind !== "choice" || answer.answer !== confirm) return false;
  return ctx.ui.confirm(
    ru ? "Подтвердить?" : "Confirm?",
    ru ? "Только предложение в чате." : "Only the proposal in chat.",
  );
}

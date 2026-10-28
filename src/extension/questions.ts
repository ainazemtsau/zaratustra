import type { ExtensionContext } from "@earendil-works/pi-coding-agent";
import { visibleWidth } from "@earendil-works/pi-tui";

export type QuestionAnswer =
  | { kind: "choice" | "custom"; answer: string }
  | { kind: "cancelled" };

/** Long explanations belong in ordinary chat before calling this function.
 * These native selection/input results are data, never action permission.
 */
export async function askQuestion(
  ctx: ExtensionContext,
  question: string,
  choices: string[],
): Promise<QuestionAnswer> {
  const ru = /[а-яё]/i.test(question);
  const custom = ru ? "Свой ответ…" : "Other answer…";
  if (
    !question.trim() ||
    visibleWidth(question) > 52 ||
    /[\x00-\x1f\x7f-\x9f]/.test(question) ||
    choices.length < 1 ||
    choices.length > 5 ||
    new Set(choices).size !== choices.length ||
    choices.some(
      (choice) =>
        !choice.trim() ||
        visibleWidth(choice) > 26 ||
        /[\x00-\x1f\x7f-\x9f]/.test(choice) ||
        choice === custom,
    )
  )
    throw new Error(
      "Use a short question and 1–5 unique short labels; put the explanation in chat.",
    );
  const selected = await ctx.ui.select(question, [...choices, custom]);
  if (selected === custom) {
    const answer = await ctx.ui.input(ru ? "Ваш ответ" : "Your answer");
    if (!answer?.trim()) return { kind: "cancelled" };
    if (answer.length > 4000)
      throw new Error(
        "Custom answer exceeds 4000 characters; no action was approved.",
      );
    return { kind: "custom", answer };
  }
  return selected !== undefined && choices.includes(selected)
    ? { kind: "choice", answer: selected }
    : { kind: "cancelled" };
}

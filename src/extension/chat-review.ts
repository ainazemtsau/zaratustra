import type { ExtensionAPI } from "@earendil-works/pi-coding-agent";
import { randomUUID } from "node:crypto";

export const PROPOSAL_MESSAGE = "zaratustra.proposal";

/** sendMessage is deferred during a tool turn. Do not open a question until Pi
 * actually emits the matching message in the transcript on a later turn.
 * This is presentation bookkeeping, never consent or execution authority.
 */
export function chatReview(pi: ExtensionAPI) {
  const entries = new Map<
    string,
    {
      owner: object;
      text: string;
      nonce: string;
      displayed: boolean;
    }
  >();
  pi.on("message_end", (event) => {
    const message = event.message;
    if (
      message.role !== "custom" ||
      message.customType !== PROPOSAL_MESSAGE ||
      message.display !== true
    )
      return;
    const details = message.details as
      | { preview?: string; nonce?: string }
      | undefined;
    const entry = details?.preview ? entries.get(details.preview) : undefined;
    if (
      entry &&
      entry.nonce === details?.nonce &&
      message.content === entry.text
    )
      entry.displayed = true;
  });
  pi.on("session_shutdown", () => {
    entries.clear();
  });
  return {
    ensure(owner: object, ref: string, text: string): boolean {
      const previous = entries.get(ref);
      if (previous?.owner === owner && previous.text === text)
        return previous.displayed;
      const entry = { owner, text, nonce: randomUUID(), displayed: false };
      entries.set(ref, entry);
      try {
        pi.sendMessage(
          {
            customType: PROPOSAL_MESSAGE,
            content: text,
            display: true,
            details: { preview: ref, nonce: entry.nonce },
          },
          { triggerTurn: false },
        );
      } catch (error) {
        entries.delete(ref);
        throw error;
      }
      return false;
    },
  };
}

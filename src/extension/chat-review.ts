import type {
  ExtensionAPI,
  ExtensionContext,
} from "@earendil-works/pi-coding-agent";
import { randomUUID } from "node:crypto";

export const PROPOSAL_MESSAGE = "zaratustra.proposal";

/** Pi defers context-only custom messages until the tool turn ends. Those messages
 * reach the public UI listeners, but not extension message_end hooks in Pi 1.4.
 * Match their exact entry in the current session branch before asking a question.
 * Transcript delivery is presentation bookkeeping, never proof of reading or consent.
 */
export function chatReview(pi: ExtensionAPI) {
  const entries = new Map<
    string,
    { owner: object; text: string; nonce: string }
  >();
  pi.on("session_shutdown", () => {
    entries.clear();
  });
  pi.on("session_tree", () => {
    entries.clear();
  });
  return {
    ensure(
      owner: object,
      ref: string,
      text: string,
      session: Pick<ExtensionContext["sessionManager"], "getBranch">,
    ): boolean {
      const previous = entries.get(ref);
      if (previous?.owner === owner && previous.text === text) {
        return session.getBranch().some((entry) => {
          if (
            entry.type !== "custom_message" ||
            entry.customType !== PROPOSAL_MESSAGE ||
            entry.display !== true ||
            entry.content !== text
          )
            return false;
          const details = entry.details as
            | { preview?: string; nonce?: string }
            | undefined;
          return details?.preview === ref && details.nonce === previous.nonce;
        });
      }
      const entry = { owner, text, nonce: randomUUID() };
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

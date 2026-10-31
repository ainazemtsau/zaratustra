# Native confirmation delivery correction — 0.7.6

Pi 1.4.0 sends context-only custom message events to public UI subscribers but
not to extension message_end hooks. Zaratustra incorrectly awaited such a hook
before opening its native confirmation question. A delivered proposal could
therefore remain review_in_chat forever. Earlier tests fabricated that missing
extension event instead of exercising the actual session branch.

The adapter now checks the public current session branch for its exact delivered
custom message: type, display flag, proposal reference, fresh nonce and full text.
It cannot accept a sibling branch, old runtime, changed text or another proposal.
A queued proposal still is not delivered during its own tool turn. The next
confirmation call can proceed once Pi appends the actual transcript entry.
Tool instructions explicitly request continuation on the next tool turn, without
waiting for another user prompt. Transcript delivery does not prove user reading
or grant authority: actual native confirmation, current guards and exact payload
binding remain unchanged. No file change is dispatched by this presentation check.

This correction does not change memory, schema, control protocol, runtime or
application data. An already loaded Pi session needs /reload, then should prepare
or re-read its current exact proposal and request native confirmation normally.
No model or paid API conversation is used for this patch.

Validation: 14 confirmation tests and four focused native TUI adapter scenarios
passed, covering queued delivery, exact current-branch matching, fresh nonce after
branch navigation/reload, real confirmation versus custom text, and cancellation.
The pre-fix committed module reproduced the missing acknowledgment with a real
SessionManager append. One cancellation-fixture assertion was corrected to the
existing declined/answer contract before its successful rerun. Types, targeted
lint/format, build and dependency boundaries passed; focused source review found
no remaining blocker. These are mechanical SDK/adapter checks, not a model
conversation or an observed interaction in the owner's running terminal.

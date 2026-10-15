# Ordinary material reading and query contracts — audit checkpoint

## Status and scope

The owner approved implementing this common contract on 2026-10-15. Target
release 0.25.4 keeps Core schema 18. Implementation and observed verification
are recorded separately from owner acceptance in the release result.

Audit of the installed 0.25.3 ordinary reading path, 2026-10-15. This is not an
implementation, release, or acceptance claim. The earlier ordinary selection
correction remains distinct: the new selected Work now starts, then encounters
these reading/query boundaries. Preserve existing Activity, Work, originals,
outputs, accounting and acceptance. Exporters and private Git remain excluded.

The owner requires agreement before a new structural contract. The proposal
below concerns material/query interfaces beyond the approved execution handoff.
No schema change, new execution graph, queue or background service is proposed.

## Confirmed defects and limits

1. Exact references can name both ordinary Artifact and knowledge records.
   `zara_memory.open` and explicit memory batches only support the knowledge
   family. An existing authorized Artifact therefore produces a family-specific
   `not_found`, which the agent can mistake for a lost material. Search does not
   cover ordinary Artifacts or Work/procedure packets either.
2. Four runtime contracts expose definition-local selectors: `current_activity`,
   `format_keys`, `use_period`. Core intentionally rejects unresolved aliases.
   Affected contracts: `data.query_entries`, `memory.catalog`, `memory.read_batch`,
   `memory.prepare_cache`. The native inline memory tool also needs the same
   executable contract. Fixing only the data endpoint leaves the mismatch.
3. Search accepts raw FTS5 expressions. A normal punctuation-bearing string such
   as `Pacific/Chatham` is invalid grammar. Empty search or a successful empty
   DataEntry query cannot establish absence of all saved working information.
4. Transport refusal and missing context are separate observations. Pi session
   auto-retry is independent of provider stream `maxRetries`. TCP exceptions,
   HTTP errors and SSE errors have different cleanup paths. The native runner
   can catch a context-hook error and continue toward the provider; our final
   readiness guard then refuses HTTP with a secondary generic error. Preserve
   that guard and diagnose the first error. The exact preceding refusal in the
   reported live sequence is not established by the visible tail alone.

A disposable installed-wheel reproduction confirmed the first three boundaries:
ordinary Artifact open fails while exact Artifact read succeeds; each of the
three advertised local selectors is rejected; punctuation search fails. All
six observations changed zero Core revisions and used zero model requests.
The runtime catalogs independently advertised the unsupported fields in all
four operations. Two initial harness problems (missing development dependency
in the ordinary tool environment and an incorrect helper method name) are not
product evidence; the final reproduction used the isolated wheel environment.

## Proposed common correction

### Addressed materials

Make content-bearing Artifact and knowledge material readable through an explicit
typed boundary. A returned reference must disclose its actual kind and supported
reader, revision, availability and bounded continuation. Keep existing persisted
reference JSON and hashes unchanged; attach navigation metadata to new adapter
responses, not historical originals.

Use public Core reads and their current rights. Wrong family must not imply
global absence, and permission refusal must not expose hidden kind/content.
Preserve exact revisions, start/end bounds, UTF-8 byte windows, hashes and only
actually delivered exposure. Do not turn one window into whole-document reading.
Do not search the whole workspace to rediscover an already addressed input.

### Executable selectors

Separate process-definition selectors from executable runtime selectors.
Definitions keep local keys, current-Activity binding and procedure-period
binding. Runtime tools advertise exact Activity IDs, exact format versions and
explicit time/date bounds that Core can execute. The model gets those addresses
from the selected Work's pinned structure and the existing describe operation.

Apply this boundary consistently to native memory, integrations memory and typed
data. Do not resolve aliases using the last Activity opened anywhere in the
space, and do not guess a period in a free conversation. Preserve all old saved
definitions and their checksums. New invalid runtime inputs receive field-level
diagnostics before retaining a selection.

### Search

Expose ordinary text search and explicit advanced FTS as distinct modes. Encode
plain text as literal search input; do not interpret user intentions, domains or
keywords. Preserve the existing low-level FTS API and historical definition
semantics. Bind continuation cursors to both query and mode. Distinguish index
coverage from a claim that information does not exist in other addressed inputs.

### Failed provider/context preparation

First reproduce HTTP failure, TCP loss, SSE failure and context-hook failure as
separate native cases. Preserve the original refusal through the final guarded
provider boundary so the owner sees the actual next action. Follow the existing
unknown-send contract: retain accounting and effects, do not mark unknown as
unsent/successful, and do not regenerate an already saved result or effect.
SDK auto-retry and explicit owner continuation must retain distinct origins.
No new execution/delivery status authority is needed.

## Regression and installed-Pi proof

| Risk | Required observation |
| --- | --- |
| Mixed Source and Artifact bases | Both exact originals readable; full packet continues without inventing missing data |
| Wrong kind, revoked rights, deleted material | Accurate typed refusal; no disclosure or fallback that bypasses rights |
| Fragmented/multibyte material | Exact bytes/revisions and continuation; unread bytes never claimed exposed |
| Runtime versus definition selectors | All four contracts and native memory agree; old definitions remain byte-compatible |
| Two Activity with identical local keys | Exact format/scope selection; no ambient-focus leakage |
| Old Work after structure change | Pinned old format read; current structure does not silently replace it |
| Runtime query | Contract → real populated fictional query → exact returned entry; not only schema inspection |
| Punctuation and FTS | Slash, hyphen, quotes, colon, brackets, Cyrillic and operator words as text; explicit FTS/cursor checks separately |
| Empty search/query | Coverage accurately limited; retained input remains discoverable through its address |
| HTTP/TCP/SSE/context failure | Native retry/context events, first error, actual HTTP, manifests, effects and receipts observed |
| Close/reopen after effect and error | Saved effect remains; no replay; ordinary explanation/continuation from Core |

Use ordinary installed Pi outside checkout, mixed exact fictional bases, actual
provider packets and raw replies. Read the advertised contracts and execute the
queries in that same native scenario. Scripted replies must no longer bypass
these boundaries by supplying only pre-resolved inputs. Existing setup,
selection, recovery and maintenance coverage remains.

After implementation: affected checks, one existing full native gate, affected
repeats for concrete fixes, final wheel byte proof, one bounded read-only
evaluator and the installed scenarios above. No real subscription/paid model
calls are authorized by this diagnostic plan. Report failed trials separately.

## Instance continuation

Do not recreate Activity or ask the owner to dictate earlier answers again.
After verified package delivery, read the previously inaccessible original and
re-evaluate any dependent proposed draft through normal versioned operations.
Do not accept it merely because it was saved. A transport-unknown invocation
remains unknown; any addressed maintenance requires its proper owner authority.
Keep instance paths, IDs, raw texts and operational receipts private.

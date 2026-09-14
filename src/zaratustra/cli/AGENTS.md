# CLI
Public API is main in __init__.py, installed as zara. argparse handles presentation;
init/status/migrate/records/mutate/receipt/history/artifacts/projections/handoff call public Core. Console delivery
uses public zaratustra.local, permissions remain in Core. No SQL/authority rules here.
Explicit path defaults to cwd; do not discover or select another workspace implicitly.
JSON reports persisted facts, never permission or runtime approval inferred from CLI input.
records create accepts initial draft fields only; handoff import uses the Core parser
and the same apply_mutation. File or bounded UTF-8 stdin is data, never permission.
mutate/receipt accept a JSON value, then separate exact terminal confirmation. No
approval flag or piped confirmation. --content-file supplies only bytes for an exact
confirmed digest/size; it is not a Handoff importer. artifacts read emits verified
base64 bytes with metadata. A post-commit rebuild failure emits the stored receipt
and rebuild_required with exit 2. Other refusals use exit 1. stdin import gets
exact approval from a separate controlling console after EOF. No auto-retry/rebase.
handoff list is owner-local saved acceptance audit, not Work 6 context delivery.
work open requires explicit identity/revision/budget, confirms the exact ContextQuery
through the existing local console, calls public open_work and writes its full exact
bytes to stdout. No partial context on refusal; no implicit output file or workspace
mutation. A saved packet cannot replace a current query.
Failures go to stderr with nonzero exit.
result submit takes a bounded request file through the Core parser and confirms
the complete request before submit_result. result read confirms an exact ReceiptQuery
and discovers saved Result/next under current rights. Neither text nor a result-read
response authorizes future opening; use work open with explicit current revision
and budget. Migration6 is opt-in; default4 remains.
entry add/find/relocate use the explicit installed discovery catalog. entry read
resolves one exact row, confirms its exact ProcessQuery, and emits the complete
generic Core metadata package. Catalog rows and aliases never count as authority.
entry intake retains its exact plan and stage receipts below the selected workspace
inbox. A repeated invocation obtains a new exact confirmation, recovers authoritative
Core receipts and runs only a missing valid stage; it never rebases the original plan.
entry start creates one generic unbound graph, catalogs it and uses four exact standard
mutations to establish an accepted initial basis; its retained plan grants no rights.
entry open resolves the current ContextQuery by designation. entry request saves one
non-overwriting provider-neutral context snapshot, and entry receive preserves that
snapshot's revision/basis while wrapping returned text for the ordinary intake preview.
entry create keeps draft/research/proposal stages separate, accepts an authored generic
definition, and confirms one complete activation preview before standard Core writes.
Research files are data, never permission; status rechecks Core before claiming rights.
entry create prose builds that same persisted draft from ordinary strings and the
installed capability producer. entry resume separately confirms the exact Process
state read. entry later-work retains one exact no-current intent and confirms its
Pack-compatible Core request. entry change uses the existing exact review/decision/
Result continuation; saved intent never grants Core permission.
entry ready adds program/connection-file diagnostics around that same onboarding
read and exact confirmation. Unknown/refused is never no-current. entry connection
exports instruction-only skills into a NEW explicitly chosen chat root; matching
files do not prove agent session loading. __main__ delegates to this same main.
END_OF_FILE: src/zaratustra/cli/AGENTS.md

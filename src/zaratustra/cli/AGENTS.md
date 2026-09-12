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
END_OF_FILE: src/zaratustra/cli/AGENTS.md

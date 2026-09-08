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
END_OF_FILE: src/zaratustra/cli/AGENTS.md

# CLI
Public API is main in __init__.py, installed as zara. argparse handles presentation;
init/status/migrate/records/mutate/receipt/history call public Core. Console delivery
uses public zaratustra.local, permissions remain in Core. No SQL/authority rules here.
Explicit path defaults to cwd; do not discover or select another workspace implicitly.
JSON reports persisted facts, never permission or runtime approval inferred from CLI input.
records create accepts initial draft fields only; no Handoff/actor/approved/import interface.
mutate/receipt accept a JSON value, then separate exact terminal confirmation. No
approval flag or piped confirmation; no Handoff file/stdin importer in Work 3.
Failures go to stderr with nonzero exit.
END_OF_FILE: src/zaratustra/cli/AGENTS.md

# CLI
Public API is main in __init__.py, installed as zara. argparse handles presentation;
init/status/migrate/records call only the public Core API. No SQL or authority logic here.
Explicit path defaults to cwd; do not discover or select another workspace implicitly.
JSON reports persisted facts, never permission or runtime approval inferred from CLI input.
records create accepts initial draft fields only; no Handoff/actor/approved/import interface.
Failures go to stderr with nonzero exit.
END_OF_FILE: src/zaratustra/cli/AGENTS.md

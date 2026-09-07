# CLI
Public API is main in __init__.py, installed as zara. argparse handles presentation;
init/status call only the public Core API. No SQL or authority logic belongs here.
Explicit path defaults to cwd; do not discover or select another workspace implicitly.
JSON reports persisted bootstrap facts. Failures go to stderr with nonzero exit.
END_OF_FILE: src/zaratustra/cli/AGENTS.md

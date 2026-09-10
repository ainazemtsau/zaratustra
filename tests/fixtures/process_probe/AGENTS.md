# Process rule probe
T1 only: explicit trusted rule selection, no registry or full M1 capabilities.
Public surface is __init__.py. runner.py opens real Core context and returns a
proposal; it never authorizes or writes. Rules see Work and verified observation
data, not a workspace path or caller. All state changes belong to Core.
Core must not depend on this module. Fictional examples are not product templates.
This fixture is development-only and must never enter the installed product.
END_OF_FILE: tests/fixtures/process_probe/AGENTS.md

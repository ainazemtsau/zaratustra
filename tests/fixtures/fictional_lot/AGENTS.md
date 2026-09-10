# Fictional lot Process — T4 verification package
This module owns only the finite KITE inspection/disposition rules and derived
seven-answer selection. It is not a user template. Public surface: __init__.py.
Use only Core and process_packs public APIs; no local/CLI/tools imports, state IO,
authority issuance, clocks, discovery or mutable runtime registry.
inspect requires every named check; decide binds the exact prior inspection digest.
closed is a non-executable continuation; the trusted host explicitly cancels it
through Core. Never claim it completed a third Result. Unknown state fails closed.
Views describe only supplied metadata scope; context references grant no authority.
This fixture is development-only and must never enter the installed product.
END_OF_FILE: tests/fixtures/fictional_lot/AGENTS.md

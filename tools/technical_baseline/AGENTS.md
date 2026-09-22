# Core v0.1 technical gates

This subtree is a development-only, localhost-only probe for G07-1 and G08-1.
It owns no product state and must not be imported by installed Zaratustra code.

- Require a NEW output directory below this checkout's ignored `_scratch`.
- Use only synthetic identifiers and payloads.
- Never discover credentials or use a real provider/model endpoint.
- Keep `core.sqlite3` and `executor.sqlite3` separate.
- A probe observation is evidence only for the exact pinned build and command.
- Stop after both gate outcomes; do not add Core v0.1 domain implementation here.

END_OF_FILE: tools/technical_baseline/AGENTS.md

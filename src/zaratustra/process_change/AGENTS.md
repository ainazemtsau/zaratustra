# Safe process change coordinator

This installed coordinator owns one reviewed future definition-edition transition.
Its adjacent journal is non-authoritative: Core records, immutable Pack bindings,
history, exact content and receipts remain authoritative. Resolve the actual Work
only through committed Result lineage. Approval retains intent but grants no Core
permission and is not a committed effect. The existing exact-confirmed Core Result
mutation is the sole effect and creates the first Work governed by the new edition.
No provider calls, implicit latest lookup, Pack rebind, Core migration, SQL or
development-fixture dependency belongs here.
END_OF_FILE: src/zaratustra/process_change/AGENTS.md

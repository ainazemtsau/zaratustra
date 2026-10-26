# Storage boundary

Public API: index.ts. Own node:sqlite, workspace identity, WAL, stable coordination
and OS-backed runtime leases, immutable bytes and addressed extracted text. No Pi imports.
One local workspace admits short complete commands; no lifetime database owner or TTL
lease stealing. Reserve async resources durably and keep the runtime OS lease through
all callbacks. Never reset damaged storage. Schema 9/control 2 fence predecessor writers.
E3 owns consistent backup/raw bytes, pinned imports and quarantine generations. Runtime
lease files and coordination identity stay outside replaceable generations. Preserve
unknown resource barriers across restore; control pointer is the switch commit point.

END_OF_FILE: src/storage/AGENTS.md

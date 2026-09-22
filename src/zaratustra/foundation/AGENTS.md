# Core v0.1 domain foundation

This package is the independent Core v0.1 subject foundation. It never imports the
legacy `zaratustra.core` package or higher product surfaces. Its public contract is
`__init__.py`; internal modules share only explicit typed models.

`runtime.py` admits the exact supported SQLite build before stdlib `sqlite3` loads.
`storage.py` owns the `.zara-core` layout, initial schema, checked connections,
backup/restore and deletion sanitation. `operations.py` is the sole domain mutation
path after space creation and owns current Decision/Grant checks. `models.py` owns
frozen wire/domain values and must not become an unvalidated JSON bag.

Domain content exists once in `managed_content`. Revisions, audit and receipts may
retain identifiers and permitted outcome metadata but never copy managed payload.
Historical reads are exact and never fall forward. Restore stays quarantined until a
fresh trusted-local recovery operation establishes the new epoch.

No Pi, DBOS, scheduler, dispatcher, Activity/Work runtime, memory or Sleep dependency
belongs here. Stage/check numbers stay in documentation and tests, not product module
names.

END_OF_FILE: src/zaratustra/foundation/AGENTS.md

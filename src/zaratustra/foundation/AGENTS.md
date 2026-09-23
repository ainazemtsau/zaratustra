# Core v0.1 domain foundation

This package is the independent Core v0.1 subject foundation. It never imports the
legacy `zaratustra.core` package or higher product surfaces. Its public contract is
`__init__.py`; internal modules share only explicit typed models.

`runtime.py` admits the exact supported SQLite build before stdlib `sqlite3` loads.
`storage.py` owns the `.zara-core` layout, schema definitions, checked connections,
backup/restore and deletion sanitation. `operations.py` owns the authorized
additive schema 2 upgrade, the sole domain mutation path after space creation,
and current Decision/Grant checks. `execution.py` owns the explicit schema 3
upgrade, resource/Attempt/invocation state, the explicit schema 4 continuation
upgrade and addressed execution reads. `models.py` owns frozen wire/domain values
and must not become an unvalidated JSON bag.

Artifact bytes exist once in `managed_content`; Activity/Work prose lives in
`subject_content`. Revisions, audit and receipts may
retain identifiers and permitted outcome metadata but never copy managed payload.
Historical reads are exact and never fall forward. Stage 3 Activity/Work content
uses `subject_content` and the same operation/audit/receipt path. Work acceptance
is a separate authorized operation after exact output checks; Activity remains
independent of a Work outcome. Restore stays quarantined until a
fresh trusted-local recovery operation establishes the new epoch.

The foundation stores Work execution records but never imports Pi or runs a model.
Schema 4 adds durable assignment, addressed wait/answer, a saved remainder,
stop state and pending/cancelled outbox records in the same operation/receipt path.
The Work remains proposed until its exact result is separately accepted. Recovery
closes old-epoch waits and cancels old outbox; unknown stop retains the resource.
Deletion purges these managed rows and payload in affected backups/live SQLite.
Schema 4 backup may also carry a checked DBOS SQLite snapshot and managed Pi RPC
home; restore keeps them inert in the new epoch. Core requires a technical cleanup
adapter before completing deletion when such data exists. The package still does
not import DBOS, Pi, a scheduler, dispatcher, memory or Sleep.
Stage/check numbers stay in documentation and tests, not product module names.

END_OF_FILE: src/zaratustra/foundation/AGENTS.md

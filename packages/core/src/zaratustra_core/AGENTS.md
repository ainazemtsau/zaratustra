# Independent restart core

Owns SQLite authority and wire/v1. No legacy, app, Pi or development imports. Public imports only through zaratustra_core. Explicit new data-root; no import-time I/O. Read root STOP/STEER before mutation. Accepted revision 2 A is technically owner-accepted; B continuation is owner-authorized in docs/restart/PACKAGE-B-RETURN.md. Current rights and short transactional admission are mandatory.

Package C is authorized by the later exact owner words in root AGENTS.md and
docs/restart/PACKAGE-C-RETURN.md. Sleep uses ordinary Work/Attempt and data records,
not another run engine. read_history has immutable event-bound source hashes and
finite cutoff/pages; progress checks structure, lineage, scope and reservations,
never the truth or value of model analysis. Non-human memory/Method writes need
explicit write:<kind>:<scope> rights in addition to operation rights.

END_OF_FILE: AGENTS.md

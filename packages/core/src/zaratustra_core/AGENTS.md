# Independent restart core

Owns SQLite authority and wire/v1. No legacy, app, Pi or development imports. Public imports only through zaratustra_core. Explicit new data-root; no import-time I/O. Read root STOP/STEER before mutation. Accepted revision 2 A is technically owner-accepted; B continuation is owner-authorized in docs/restart/PACKAGE-B-RETURN.md. Current rights and short transactional admission are mandatory.

END_OF_FILE: AGENTS.md

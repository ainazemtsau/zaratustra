# Typed journal and revisions

Registered types validate payloads and declare allowed transitions. All canonical
revisions are immutable Process materials written via public Core save_process_material:
one snapshot, links and existing mutation audit commit together. No second domain
database or direct Core-table writes. FTS is an in-memory derived index.
Scope is one Process or the explicitly selected Home shared area. References are
version-pinned and never expand scope. Decision adoption/replacement/revocation
are separate operations; ordinary episode/document correction changes no decision.
Exports contain data and schemas, never executable handlers. Read packages without
extracting paths or evaluating schemas. No live import or automatic synchronization.
END_OF_FILE: src/zaratustra/journal/AGENTS.md

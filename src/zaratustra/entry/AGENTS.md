# Entry catalog adapter
This installed adapter owns only explicit catalog persistence, designation matching,
source-path validation and construction of an exact one-Work ProcessQuery. It may
read public Core state but never grants Core authority, executes Packs, opens content,
scans directories or mutates a workspace. CLI owns presentation and local confirmation.
Catalog rewrites are atomic and identity-preserving; unavailable rows are isolated.
Cooperating catalog mutations hold the stable-path advisory lock across the
authoritative load, validation and replacement. The retained lock file is not state.
END_OF_FILE: src/zaratustra/entry/AGENTS.md

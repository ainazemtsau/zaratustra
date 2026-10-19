# Storage boundary

Public API: `index.ts`. Own node:sqlite, workspace identity, WAL, one-process writer lease,
immutable UTF-8 material bytes and readback. No Pi imports. Never reset a damaged store.
An interrupted import may leave an orphan; no GC/backup/restore promise in this block.

END_OF_FILE: src/storage/AGENTS.md

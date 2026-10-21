# Storage boundary

Public API: `index.ts`. Own node:sqlite, workspace identity, WAL, one-process writer lease,
immutable original bytes and versioned extracted text and readback. No Pi imports. Never reset a damaged store.
E3 owns consistent backup/raw bytes, pinned imports/cleanup and quarantine generations.
The control root and writer lock stay stable; no writable partial restore or empty replacement.

END_OF_FILE: src/storage/AGENTS.md

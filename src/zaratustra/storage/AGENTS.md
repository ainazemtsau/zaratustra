# Portable file storage

Confirmed immutable JSON operation packages and their content files are the durable
authority. SQLite is a disposable materialization of that authority. Never execute
SQL or code supplied by a package: schemas come from installed factory functions.
Publish complete packages before atomically advancing HEAD. Preserve exact historical
text and bytes. Validate the full confirmed chain before serving a cache. Locks are
local OS locks, never synchronized ownership claims. Git operations belong to the owner.

END_OF_FILE: src/zaratustra/storage/AGENTS.md

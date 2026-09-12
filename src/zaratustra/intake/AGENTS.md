# Incoming material coordinator
This installed coordinator parses one bounded external text envelope, validates an
explicit selected Work through public Core reads, and prepares an exact two-operation
publication/acceptance preview. It may execute only those standard Core mutations
after a trusted adapter supplies approval bound to the unchanged complete preview.
It never grants authority from input, refreshes the envelope's original revision,
completes Work, executes Packs, scans sources, or writes Core state directly.
Partial effects across the two Core invocations are retained in one exact coordinator
journal. Recovery uses current authorized Core receipt reads and verified bytes, never
journal claims alone or a refreshed original revision. One stable per-intake lock
serializes cooperating retries. The journal grants no authority; no-confirmation
inspection discloses only unverified stage names and the preview hash.
END_OF_FILE: src/zaratustra/intake/AGENTS.md

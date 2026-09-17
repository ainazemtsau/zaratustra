# Home Registry

Home owns registration, locations, aliases, groups and typed relations. Process
state and materials remain in Core workspaces. Read sources through public Core.
All Home changes and their operation receipts commit in one local transaction.
Reads never repair, select an ambiguous name, migrate or register a source.
Use bounded indexed queries; cached metadata is explicitly labelled with its
source revision and observation time. A failed source stays registered.
No agent, subject-specific rules, schedules or workflow engine belongs here.
Schema2 adds the Home vocabulary and explicit approval-bound creation. Portable
storage preserves all registry receipts and makes SQLite disposable. A read can
rebuild cache from confirmed files, never fix canonical source damage. Relative
internal locations and explicitly mapped external identities support new devices.

END_OF_FILE: src/zaratustra/home/AGENTS.md

# Zaratustra — concurrent workspace

Current owner assignment, 26 October 2026: implement the approved parallel-agent plan.
Base 4f31e3088a95fdad41457418d4b18963b4c69488; branch codex/concurrent-workspace.
One local shared workspace, Pi 1.4.0, isolated verification Node 24.22.1.
Preserve all domain identities/history and existing trust/approval/restore boundaries.
The new owner assignment supersedes the earlier lifetime-single-writer restriction.

Use stable SQLite coordination, short complete Core phases, runtime OS leases,
durable narrow resource reservations, schema 9 and fenced maintenance. No daemon,
server, model/planner, per-Activity SQL tables, runtime Git or owner ignore edits.
Core stays portable behind StoragePort. Native Pi owns actual text writes.
Independent implementers may own disjoint modules; one root integrator owns shared
interfaces and commits. Never revert another writer's changes. Read module AGENTS;
references there to a lifetime writer are superseded by this assignment.

Run focused mechanical concurrency/recovery/privacy tests, types, lint, build and
review. Owner amendment: stop 100-process qualification; use at most ten processes and
short necessary checks. Preserve failed larger attempts; no more heavy growth runs. No paid
model/API conversations, full historical check/deliver/scale sweeps or invented live
acceptance. Preserve failures and report measured limits. Do not read or modify
private ZT/Health, credentials, Direction OS live state or archives. Keep global
Node/Pi unchanged; verify with a downloaded, checksum-checked isolated runtime.

Publish checked source normally, no force push or foreign-ref changes. Hand back
exact commit, checks, limitations, zero model calls and pinned owner update command.
The owner updates private ZT after closing old sessions; no automatic migration of
real personal data during development.

END_OF_FILE: AGENTS.md

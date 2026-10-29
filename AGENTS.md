# Current assignment — file-primary memory, Activity and bounded Sleep

Owner-approved plan, 29 October 2026, supersedes conflicting older assignment rules below.
Worktree: C:/projects/zaratustra-memory-sleep-v2; branch codex/memory-activity-sleep-v2.
Files are durable authority; SQLite is a rebuildable transactional projection. Corpus format1,
projection schema10, control3. Preserve existing identities, exact selected versions, trust,
concurrency and unknown-effect recovery. No committed:true before canonical durable commit.
Implement selective memory, common Activity contract, bounded native SDK Sleep (10 cases,
3 improvements, 20 logical generations, 15 minutes), and automatic all-working-project
Git checkpoint/push to approved private main. The owner explicitly authorized that runtime Git
and precise runtime-only ignore/index changes supersede the earlier prohibitions.

Do not touch private ZT/Health during development. Only root coordinates late cold backup,
verified quarantine migration, installation and private publication after old sessions close.
No forced process termination or semantic deletion of legacy data. Global Node/Pi stay as-is.
Use Pi1.4.0/Node24.22.1. At most ten stress processes and focused tests, not full history sweeps.
Only one tightly bounded final model check on a private copy when it proves actual behavior;
no worker may invoke paid models. Public tests/evidence must be synthetic and anonymous.

Ownership: storage worker owns storage/index/control/administration/corpus modules;
memory worker owns core/memory-index/memory/lifecycle and a separate policy module;
Sleep worker owns new core/sleep-v2 + extension/sleep modules;
Git worker owns new storage/git-sync + extension/sync modules. Root alone integrates
core/contracts.ts, core/index.ts, extension/index.ts, skills, instructions and release docs.
Do not edit shared files without root handoff; send required changes instead.
Everyone shares this worktree: preserve others' edits and adjust to their interfaces.

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

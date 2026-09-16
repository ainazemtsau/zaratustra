# Stage 2B: versioned skills and session context

Owner approval: «ДА», following review of
Zaratustra_Stage_2B_Implementation_Brief.md supplied from the planning session.
This continues Stage2A fc696332dfdd2eb998809059f0065e5574370376. It does not
close an older Direction-OS task or authorize Stage3. Product version: 0.20.0.

## Data and operations

The installed process_skills module registers skill and skill_bindings through the
2A TypeSpec mechanism. Existing Core schema10, material transaction, immutable
revisions, source references, scope rules, search and export remain the foundation.
No new database or separately synchronized log is introduced. Typed payload links
participate in the same export closure as explicit links.

Skills have Agent Skills-compatible name/description/body, declared dependencies,
supported non-secret settings and optional exact derived_from. record.create/revise
stores the canonical complete text, reason, available authority and source. Previous
versions remain readable. A skill.load result presents that exact version as
name/SKILL.md with YAML frontmatter and Markdown body. There is no editable second
copy. See the official [Agent Skills format](https://agentskills.io/specification).
Installed resource dependencies require an exact distribution version. No saved
schema/body executes code or installs a handler.

Each Process has one deterministic configuration record and up to16 role slots.
A slot selects one exact skill reference and supported settings. skill.bind requires
expected_configuration_revision, reference, slot and reason; skill.unbind removes
the slot in a new configuration revision. Binding an older skill revision rolls
back. Generic record operations refuse managed configuration writes. Selection and
its audit are one existing Core transaction; save-and-apply are two explicit steps.
If saving succeeds but applying fails, the saved version remains available and
the previous selection remains active. Exact retries return the committed result.

Two slots cannot activate the same identity or a declared original/variant family.
Replacing the existing slot makes a local variant the sole implementation of that
function. Unrelated method conflicts are the agent's responsibility; no semantic
keyword classifier or automatic merge is introduced.

## Common context and Pi

context.read compiles identity, configuration revision/stamp, exact selected skill
metadata, readiness, settings, links and actual command/type/resource registrations.
Optional loaded_slots includes full bodies only for relevant ready slots. A missing
version never follows latest. skill.catalog lists scoped saved skills with pagination;
skill.load reads an exact selected slot. Other hosts use this same implementation.

Pi 0.85.1 was checked against its installed extensions/types, runner and session
code. session_start/session_tree restore the branch's host-owned selection. The
context hook runs before every model request, replaces only customType
zaratustra-active messages and refreshes binding changes without a restart. Full
bodies load on request. zaratustra-context-delivery session entries record the
actually supplied references, body-presence flags and SHA256 hashes. Session data
never changes .zara-context.json or another chat's active Process.

process.open commits a session switch only after target state and context compile.
Calls are serialized, and all calls produced by one model request retain its
selection/generation. A queued or serially executed stale call after a switch is
refused. Already dispatched work keeps its original target. Host envelope guard
also compares the prepared Process/configuration stamp before a common operation;
Core revision checks still protect writes. The next model boundary refreshes state.

Pi catches context-hook exceptions. The adapter therefore returns an explicit
unavailable block and gates Process tools on failure instead of relying on a thrown
exception. It retains recovery reads and process.open. Existing conversation/tool
history is not erased. These guarantees are not a hostile-agent sandbox.

Codex's supplied skill documents the shared invocation envelope: session_process
and guard live in that host's session, outside the model's command schema. Codex
UI integration is not independently implemented; the common API is the shared path.

## Catalog, scopes and limits

Commands come from the command schema; types from the installed registry; resources
from installed package metadata; skills/configuration from the selected stores.
Required failures prevent activation. Optional failures remain visible without
blocking supported work. Missing settings are named; unknown/error checks are not
reported as absence. External access is explicitly not_checked. Settings contain
non-secret preferences only; credentials/environment secrets are never inspected.

The shipped instruction logs a substantial capability gap as an ordinary 2A episode
within the agreed journal rule. It offers existing means, a local addition, an
explicit Development request or deferral. It does not implement the missing tool,
launch an executor, publish an issue or invent personal Development rules.

Shared skills can retain pointers to local grounds without loading those grounds
in another Process. Exports follow selected scopes and list excluded sources.
Readiness is a configuration check, not proof of an external action or a semantic
quality judgment. Existing FTS5/Russian morphology limits remain. Histories are
loaded through the existing 2A snapshot implementation; large-scale performance is
unmeasured. No background coordinator, automatic updates, marketplace or stage3.

END_OF_FILE: docs/stage2b/IMPLEMENTATION.md

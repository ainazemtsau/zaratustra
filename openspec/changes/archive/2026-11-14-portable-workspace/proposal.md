# Proposal

## Why

Zaratustra currently enters a user's project through a Pi extension, leaving its essential instructions and workflows inside the installed package. The owner wants a workspace that another file-capable assistant can understand and use, with Pi providing the first integration with Core.

## What Changes

- Add standalone workspace initialization, inspection and update using the versioned product package on Windows x64 and Node 24.22.1. Initialization works with Pi absent and creates visible guidance, system skills and owner areas.
- Keep a short root `AGENTS.md` that routes to system instructions, owner guidance, Activity guidance and skills. Define explicit Activity loading from the workspace root and replacement of the previous Activity's guidance when focus changes.
- Separate product-owned system files, owner-owned personal bundles and generated adapter discovery files. Record installation ownership and exact versions, preserve owner bytes, and report conflicts before replacement.
- Let a Method reference an existing personal file skill. Version the complete bundle, including references and scripts, and retain the exact bundle selected for a managed invocation. The personal files are the editable authority. Core records verified versions, bindings and execution history.
- Preserve the existing Core-canonical textual Method export workflow for its registered exports. Conversion of an export to a personal bundle is an explicit transition with one editable authority.
- Extend bounded Sleep with validated, reversible text changes to explicitly delegated local skills. Shared skills and script changes use owner confirmation. Recheck consumers and delegation at application time and retain rollback bytes.
- Connect Pi to the same portable workspace using its existing extension and native trust lifecycle. Codex is the first acceptance example for instruction-led work over ordinary workspace files. Managed Core writes by another assistant require its separately qualified adapter.
- Resolve the Pi executable from the installed package's declared CLI, using the Pi on `PATH` before a local npm peer. Check attachment, confirmation, rollback and bounded Sleep with the owner's Pi 1.5.2 in an isolated workspace.
- Qualify creation, repeat installation, update, recovery and a populated synthetic transition. Plan a later owner-authorized real ZT migration with a verified backup, Activity-by-Activity comparison and preserved Health/Web document paths.
- **BREAKING through explicit opt-in transition**. The proposed new managed storage generation fences predecessor writers. Ordinary package installation preserves populated predecessor storage until its verified transition is approved.

### Current behavior and agreed direction

The shipped 0.7.7 package declares one Pi extension and four product skills. It injects package bootstrap guidance, maintains file-primary memory through a portable Core, exports textual Methods with drift detection, and runs bounded Sleep. Activity `AGENTS.md` loading and file-authoritative personal bundles are additions proposed here.

The owner accepted Pi-independent workspace creation, instruction-led use in Codex followed by Pi on the same files, Methods that reference file skills, and the Sleep authority boundary above. Command names, exact layout, version registration and conflict recovery in the design are proposed implementation choices for review.

## Capabilities

### New Capabilities

- `workspace-installation` covers portable initialization, ownership-aware updates, optional Pi attachment, recovery and synthetic transition qualification.
- `workspace-guidance` covers short entry instructions, owner guidance, Activity discovery and instruction-led assistant use.
- `skill-bundles` covers personal file authority, whole-bundle versions, Method references, exact invocation history and existing textual export compatibility.
- `sleep-skill-maintenance` covers delegated text maintenance, shared-consumer checks, owner confirmation, validation and reversible application.

### Modified Capabilities

The repository has no existing capability specifications. These delta specs introduce requirements for the affected behaviors. Existing unrelated product behavior remains governed by its implementation and tests.

## Impact

- Product areas include package entry points, `instructions/bootstrap.md`, the four `skills/zaratustra-*` bundles, `src/extension/index.ts`, `src/extension/workspace.ts` and `src/extension/sleep.ts`.
- Core work includes optional Method skill references, version selection, dependency checks and the bounded Sleep policy in `src/core/`. Filesystem operations and immutable bytes stay behind portable storage contracts implemented in `src/storage/`.
- A small assistant-independent workspace module and command entry point will own installation plans and receipts. The product keeps the current dependency versions and adds no paid service requirement.
- Persistent additions require a fenced storage upgrade and backup/rebuild coverage. Package installation alone cannot upgrade a populated workspace. Existing IDs, revisions, selected sources, document paths, access boundaries and UNKNOWN effects must survive the explicit transition.
- Acceptance uses isolated synthetic workspaces and focused mechanical checks. Instruction usability and owner acceptance are recorded separately. A full Codex Core adapter, real ZT migration and public release need their own subsequent authorization.

# Portable workspace discussion handoff

## Purpose and present status

The owner wants an installed Zaratustra workspace that carries enough visible,
portable instructions and skills for assistants to understand and continue work.
A workspace can support long-lived Activities and additional assistant adapters.

This document carries the discussion into a fresh product chat. OpenSpec tooling
is installed. The next step is exploration and a proposed change. The portable
workspace behavior described below has not been implemented or released.

The product starting point is 0.7.7, commit
`73572ee2041aecf47d01e5dd352f370d37fa50d8`. It uses a portable Core, Pi extension,
four product skills, file-primary memory, managed Activity documents, bounded
Sleep and private Git synchronization. Read source and tests before making
claims about individual guarantees.

## Owner's accepted direction

- Installation should materialize assistant-facing workspace guidance and skills
  in the user's project. Pi remains the first runtime adapter.
- Root AGENTS.md should be very short. Activity-specific guidance can live in a
  short Activity AGENTS.md when useful. Explicit loading must support an active
  Activity even when the assistant's current directory is the project root.
- Separate product-owned system guidance from owner-owned workspace guidance,
  personal skills and Activity-specific procedures. Define update ownership and
  conflict handling before changing existing owner files.
- Product runtime mechanisms remain a versioned package. Instructions and skills
  needed to understand the workspace should have a portable representation.
- Skills may contain SKILL.md, references and scripts as needed. Version and
  validate the complete bundle whenever executable or supporting files matter.
- Sleep may make authorized reversible improvements to delegated local
  procedures. Shared consumers, permissions, goals, commitments, executable code
  and irreversible operations require their appropriate scope and validation.
- A second assistant should be able to read the workspace. Full managed writes
  need a Core adapter and verification of that assistant's trust and lifecycle.
- Preserve Health content, exact sources, selected history, existing document
  paths and the ChatGPT Web reading workflow during any future transition.
- A clean isolated installation can be inspected before existing Activities are
  migrated and inspected one by one. Preserve the original workspace and a
  verified backup through cutover.

## Proposed layout to evaluate

```text
AGENTS.md
zaratustra.json
instructions/
  system.md
  workspace.md
adapters/
  pi.md
skills/
  system/
  personal/
activities/
  <activity>/
    AGENTS.md
    <existing working documents>
memory/
.pi/
.local/
```

This is the design sketch from discussion. Resolve exact paths, discovery,
ownership and migration in the change rather than treating this sketch as a
shipped format. Small Activities can remain lightweight.

## Load-bearing current contract

`instructions/bootstrap.md` currently defines managed skill files as versioned
exports and says Core remains canonical. A file-authoritative personal skill
bundle is a proposed change to that contract. Define a single editable authority,
metadata references, bundle versions, external edits and recovery explicitly.
Existing product skill directories must also be distinguished from personal
bundles and generated assistant integrations.

## Decisions for the next chat

- What exact authority and import behavior apply to personal skill bundles.
- Which second-assistant capability is included now, and what adapter work is
  separately scheduled.
- How product-managed guidance upgrades coexist with owner edits.
- Which minimal install and migration operations create and update the structure.
- Which Sleep changes are delegated, checked, activated and reversible.

## Required transition evidence

Use isolated fixtures to show clean installation, repeat installation, upgrade,
preservation of owner files, Activity guidance discovery from the root, bundle
versioning and authorized Sleep changes. Restore a populated representative
workspace and preserve IDs, revisions, source bytes, documents and shared links.
Inspect existing Health documents and Web paths privately at the authorized
migration stage. Product development uses synthetic data.

The owner requested short necessary checks, up to ten concurrent processes when
relevant, and no long synthetic model conversations. Product usefulness and
owner acceptance are reported separately from mechanical checks.

## First instruction for the successor chat

Read root AGENTS.md, docs/OPENSPEC.md and this handoff. Use openspec-explore to
inspect existing installation, skill export, guidance loading and Sleep paths.
Explain the current behavior and the proposed transition in Russian. Resolve
only decisions that affect the scope. When the owner asks for the proposal,
prepare `portable-workspace` artifacts and stop for approval before implementing.

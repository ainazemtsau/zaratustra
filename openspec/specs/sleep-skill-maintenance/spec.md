# sleep-skill-maintenance Specification

## Purpose

Allow bounded Sleep to improve explicitly delegated local file skills with exact validation, appropriate authority and recoverable version history.

## Requirements

### Requirement: Explicit local delegation

Automatic Sleep skill maintenance SHALL require a current owner delegation binding one Activity, one personal bundle, allowed text paths and byte limits. The skill SHALL have at most one live Method consumer in that Activity and no shared Activity or general adapter use. Unknown or incomplete consumer coverage SHALL require owner confirmation.

#### Scenario: Delegated local text change

- **WHEN** Sleep proposes an in-bounds text correction to a skill delegated to the active Activity with one live Method consumer
- **THEN** the change is eligible for the bounded validation and application pipeline

#### Scenario: Location alone supplies no delegation

- **WHEN** a skill exists under `skills/personal/` without an applicable explicit delegation
- **THEN** Sleep leaves its files unchanged and presents any proposed maintenance for owner review

### Requirement: Shared and executable changes require confirmation

Sleep SHALL obtain exact owner confirmation for changes to a shared skill or any executable bundle file. Autonomous text maintenance SHALL preserve scripts, permissions, delegation, goals, commitments and product guidance. Reclassification of a file SHALL not bypass confirmation.

#### Scenario: Shared skill correction

- **WHEN** two Methods use the same skill and Sleep proposes a text improvement
- **THEN** Sleep records a pending proposal requiring owner confirmation before publication
- **AND** existing consumers continue to resolve the previous verified version

#### Scenario: Script changed by a text proposal

- **WHEN** a proposed bundle diff changes a script, its executable declaration or a text file declared as an execution input
- **THEN** the autonomous text permit is refused even if the changed file contains readable text

### Requirement: Exact validation and admission guards

Validation SHALL bind the full proposed bundle, before version, Activity and delegation revisions, consumer scope and allowed paths. At admission and activation the runtime SHALL recheck those grounds and current file state. Changed grounds SHALL invalidate admission. External editors SHALL observe the documented single-writer publication window.

#### Scenario: Consumer added after validation

- **WHEN** another Method begins using the skill after Sleep validates a local proposal
- **THEN** automatic application is refused and the proposal requires renewed validation and owner review

#### Scenario: Owner edits after validation

- **WHEN** the owner edits any bundle file after validation and the edit is observed before publication admission
- **THEN** Sleep preserves those bytes and reports the proposal as stale

#### Scenario: Delegation withdrawn

- **WHEN** the owner withdraws or narrows delegation before dispatch
- **THEN** the prior validation cannot authorize publication

#### Scenario: Consumer changes during publication

- **WHEN** a qualified consumer or delegation mutation races an admitted Sleep publication
- **THEN** the operations serialize or one receives a conflict through activation and receipt publication
- **AND** the applied result retains the exact consumer and delegation grounds under which it was authorized

### Requirement: Bounded reversible publication

Sleep SHALL retain complete before and after bundles before activating a change. Publication SHALL register a new verified version and a durable result linked to the Sleep proposal. Guarded rollback SHALL restore retained content as a new version and preserve intervening owner edits through a conflict refusal.

#### Scenario: Restore an applied version

- **WHEN** an authorized rollback is requested and the working and active versions still match the applied result
- **THEN** the previous retained content is published as a new version with a rollback receipt linked to the original application
- **AND** the original version and application history remain readable

#### Scenario: Rollback meets later owner work

- **WHEN** a rollback encounters subsequent owner changes or a different active version
- **THEN** it reports the conflict and preserves the later state for a new decision

### Requirement: Interrupted application reconciliation

An interrupted skill application SHALL be inspected through its original operation identity and actual file and registration state. UNKNOWN publication outcomes SHALL block automatic repeat until reconciled. Runtime replacement or restart SHALL preserve existing budgets and effect barriers.

#### Scenario: Lost application result

- **WHEN** a Sleep application stops after possible file publication
- **THEN** resume inspects that operation and reports its confirmed or unresolved outcome
- **AND** a new request identity cannot dispatch the same unresolved change

### Requirement: Existing Sleep bounds and benefit evidence

Skill maintenance SHALL use the existing Sleep phases and limits of ten cases, three improvements, twenty logical model generations and fifteen minutes. Each applied bundle change SHALL consume one improvement slot. Validation, application and later demonstrated usefulness SHALL be recorded separately.

#### Scenario: Improvement budget exhausted

- **WHEN** a cycle has already applied three improvements
- **THEN** another skill application is refused within that cycle even after restart

#### Scenario: Successful publication with an open benefit check

- **WHEN** a skill version is applied and its bytes and registration are verified
- **THEN** Sleep records application success and a concrete future benefit check
- **AND** it waits for later real grounds before recording demonstrated usefulness

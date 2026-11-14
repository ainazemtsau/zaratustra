# workspace-installation Specification

## Purpose

Provide a versioned assistant-independent workspace installation that preserves owner files and can later attach qualified runtime adapters.

## Requirements

### Requirement: Initialize without an assistant runtime

The product SHALL initialize a portable workspace on the qualified Node runtime with Pi absent. It SHALL materialize entry guidance, system instructions and skills, owner areas and installation metadata. Initialization SHALL report the created paths and supported operating modes.

#### Scenario: Clean installation without Pi

- **WHEN** the owner initializes an empty synthetic directory on Windows x64 with Node 24.22.1 and Pi absent
- **THEN** the directory contains readable workspace instructions and skills usable by a file-capable assistant
- **AND** initialization completes without starting an assistant, calling a model or creating managed conversation history

### Requirement: Recorded ownership and repeat installation

The installer SHALL record the product version and exact hashes of product-owned files. Repeating a completed installation of the same version SHALL preserve owner bytes and existing identities and SHALL report an unchanged installation when its managed files match.

#### Scenario: Repeat initialization

- **WHEN** initialization is repeated after the owner adds personal skills, Activity documents and workspace guidance
- **THEN** those files remain byte-identical and the existing installation identity is retained
- **AND** matching system files are reported as current

### Requirement: Conflict-aware updates

An update SHALL replace only files whose observed bytes match the recorded installation state or an explicitly accepted replacement plan. Existing owner files and modified system or generated files SHALL be reported as conflicts before activation. Conflict decisions SHALL bind the exact before and after bytes.

#### Scenario: Existing root guidance

- **WHEN** installation encounters an owner-created root `AGENTS.md`
- **THEN** it preserves the file and presents a proposed integration with the portable entry instructions
- **AND** it reports guidance integration as pending until the owner accepts an exact edit

#### Scenario: Drift during update

- **WHEN** a system file differs from its installed hash or changes after an update plan is accepted
- **THEN** the update reports a conflict and preserves the newly observed bytes
- **AND** the new installation version is not reported as fully active

### Requirement: Recoverable installation publication

Installation mutations SHALL use durable operation identities, checked paths and before-state guards. Concurrent qualified mutations SHALL serialize. External editors SHALL observe a documented single-writer publication window. Interrupted operations SHALL produce a verifiable installation or an explicit recoverable state. Retrying SHALL inspect the original operation before further writes.

#### Scenario: Lost update reply

- **WHEN** an update stops after writing files and before its completion reply
- **THEN** inspection reports the operation's actual file state and receipt
- **AND** recovery settles that operation or reports unresolved state before admitting a replacement

#### Scenario: Concurrent installer and editor

- **WHEN** another installer or editor changes a planned target and the change is observed at guarded admission
- **THEN** stale writes are refused and the other writer's bytes are preserved

### Requirement: Workspace path containment

Installation and bundle discovery SHALL operate inside the explicitly selected workspace. Paths that escape it through traversal, reparse points, hardlink aliases or conflicting Windows names SHALL be refused before affected publication.

#### Scenario: Redirected skill directory

- **WHEN** a planned skill path traverses a junction to another project
- **THEN** installation refuses the affected plan and preserves the external project

### Requirement: Optional Pi attachment

The product SHALL support explicit Pi attachment to an initialized portable workspace. Attachment SHALL preserve its owner files and installation identity, use the versioned Pi package and native project trust, and bind the same workspace to Core. Managed operations SHALL require the adapter's existing authority checks.

#### Scenario: Use the owner's installed Pi

- **WHEN** the owner attaches Pi and an installed Pi package on `PATH` declares a usable native CLI
- **THEN** attachment invokes that package's CLI even if its version differs from the development SDK
- **AND** attachment falls back to the installed optional npm peer when no supported `PATH` layout supplies the CLI
- **AND** if neither supplies a valid Pi CLI, attachment reports the missing runtime before dispatch

#### Scenario: Instruction-led work followed by Pi

- **WHEN** an assistant completes an ordinary synthetic file workflow and Pi is subsequently attached to that directory
- **THEN** Pi discovers the same Activity guidance and skill files
- **AND** the earlier ordinary documents remain available at their existing paths

#### Scenario: Untrusted Pi project

- **WHEN** Pi opens the attached directory before native project trust is accepted
- **THEN** managed storage creation and processing remain subject to the native trust refusal

#### Scenario: Portable package discovery policy

- **WHEN** attachment configures its exact product package without an explicit owner skill filter
- **THEN** it disables only that package's fallback skill discovery while the shared workspace routes remain discoverable
- **AND** unrelated packages, their filters and other settings retain their existing values
- **AND** an explicit conflicting owner filter or package delta is reported before native installation rather than silently overwritten

#### Scenario: Interrupted package discovery configuration

- **WHEN** attachment loses its reply before or after publishing its recorded package-filter change
- **THEN** the original operation retains its exact before and intended after configuration
- **AND** settlement accepts only that original configuration transition without redispatching native installation or overwriting later edits

#### Scenario: Standalone Pi package

- **WHEN** the product package is used without a materialized portable workspace
- **THEN** its existing package skills remain discoverable from the package declaration

#### Scenario: Pi loads an installed product archive

- **WHEN** the product archive is installed through npm without a root source lockfile and the qualified Pi loader opens its extension
- **THEN** all required extension resources are available from the installed package and its inventory-verified build resources
- **AND** the recorded dependency-lock input hash matches the original build input without requiring a source checkout

### Requirement: Explicit populated-workspace transition

Installing product files SHALL require an explicit verified transition before upgrading populated managed storage. Transition SHALL preserve IDs, historical revisions, selected source bytes, document paths, access boundaries and unresolved external effects. The qualification for this change SHALL use synthetic data.

#### Scenario: Populated synthetic transition

- **WHEN** a verified copy containing Activities, legacy Methods, exports, documents, restricted records and UNKNOWN effects is transitioned
- **THEN** comparison proves preservation of existing identities, versions, sources, document bytes and links
- **AND** an independent rebuild from the resulting corpus and retained bundle bytes reproduces the expected state

#### Scenario: Package update encounters old managed storage

- **WHEN** an updated package encounters a populated predecessor workspace without an approved verified transition
- **THEN** it reports the required transition and preserves the predecessor generation
- **AND** predecessor writers are fenced before any upgraded generation becomes active

### Requirement: Future personal migration evidence

The transition plan SHALL require owner authorization, a verified full backup, isolated rehearsal, Activity-by-Activity comparison and an explicit cutover decision for a real personal workspace. Its checklist SHALL cover Health content and existing ChatGPT Web document links.

#### Scenario: Personal cutover readiness

- **WHEN** a later personal migration is considered
- **THEN** readiness requires verified backup and comparison evidence for the specific workspace and its existing document paths
- **AND** synthetic qualification alone does not establish personal cutover readiness

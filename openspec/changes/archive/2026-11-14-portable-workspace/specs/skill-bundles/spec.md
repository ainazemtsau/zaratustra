# Spec Delta

## Purpose

Give personal skills a portable editable file authority while retaining verified complete bundle versions for Method use and historical inspection.

## ADDED Requirements

### Requirement: Personal file authority

A personal skill SHALL have one editable workspace bundle containing `SKILL.md` and its supporting files. Core SHALL register verified versions and references to that bundle. Product updates SHALL preserve owner bundle bytes, and generated discovery files SHALL identify the canonical bundle.

#### Scenario: Edit a personal skill

- **WHEN** an owner edits the personal bundle's `SKILL.md`
- **THEN** the edited file is discoverable as the working personal source
- **AND** inspection distinguishes those bytes from the previously verified active version

### Requirement: Complete bundle versions

Each verified version SHALL identify its complete sorted file inventory, relative paths, lengths, content hashes and exact retained bytes. Any included file addition, removal or byte change SHALL change the bundle version. Version capture SHALL reject unsafe paths, ambiguous names and concurrent inconsistent reads.

#### Scenario: Supporting file changes

- **WHEN** a reference or script changes while `SKILL.md` stays byte-identical
- **THEN** the new verified bundle has a different version and complete manifest
- **AND** both versions' retained files remain individually readable

#### Scenario: Unsafe or unstable capture

- **WHEN** capture encounters a link, Windows case collision, escaping path or file changing during the snapshot
- **THEN** registration fails without publishing an apparently complete version

### Requirement: Explicit verified activation

External edits SHALL be reported as pending validation and activation. A qualified adapter SHALL validate the complete bundle and obtain appropriate authority before changing its registered active version. Invalid, missing or unretained bytes SHALL block managed invocation of the requested version.

#### Scenario: External edit with an existing Method

- **WHEN** another assistant changes a bundle referenced by a Method
- **THEN** managed invocation reports the pending drift until it is explicitly reconciled
- **AND** selecting a retained historical version remains distinguishable from using the working files

#### Scenario: No script execution during registration

- **WHEN** a proposed bundle version contains scripts
- **THEN** validation inventories and retains the scripts without executing them
- **AND** execution requires its own applicable tool authority

### Requirement: Methods reference reusable skills

A Method SHALL support explicit skill references alongside its existing instructions and Method dependencies. References SHALL identify the stable skill and select either a pinned verified version or its current verified version at invocation. Legacy inline Methods SHALL remain readable and usable without skill references.

#### Scenario: Two Methods reuse a skill

- **WHEN** two Methods reference the same registered skill
- **THEN** each resolves that skill without creating another editable copy
- **AND** the skill is classified as shared for automatic Sleep maintenance

#### Scenario: Legacy Method

- **WHEN** a pre-transition Method has inline instructions and no skill references
- **THEN** it keeps its ID, revisions, content versions, instructions and supported invocation behavior

### Requirement: Exact invocation selection

A managed Method invocation SHALL retain the selected Method closure and every selected skill identity, complete bundle version and manifest hash. Current selections SHALL resolve once before application. Later edits or activation SHALL preserve the exact prior invocation's readable grounds.

#### Scenario: Update after an invocation

- **WHEN** a skill is updated after a Method invocation selected its verified version
- **THEN** inspection of that invocation returns the original selected bundle and bytes
- **AND** a later current-version invocation explicitly records its own selection

#### Scenario: Missing pinned bytes

- **WHEN** an invocation requests a version whose complete retained bytes are unavailable
- **THEN** it reports the missing material and refuses to substitute current working bytes

#### Scenario: Working support file changes after selection

- **WHEN** a working reference or script changes after an invocation has selected its bundle version
- **THEN** that invocation resolves relative files from the retained selected version
- **AND** managed use refuses missing or modified selected material instead of substituting the working file

### Requirement: Consumer scope and access boundaries

Registration SHALL record Activity scope, Method consumers, general adapter exposure and explicit delegation. Trusted maintenance checks SHALL consider consumers across access boundaries without exposing protected identities. Ordinary skill retrieval SHALL enforce current access to the skill and retained sources.

#### Scenario: Hidden additional consumer

- **WHEN** a skill has another registered consumer hidden from the requesting session
- **THEN** automatic local maintenance is refused with a scope reason that does not reveal that consumer's identity or content

#### Scenario: Restricted skill discovery

- **WHEN** an assistant lacks access to a registered restricted skill or its retained grounds
- **THEN** its ordinary discovery and reads do not expose the protected content through bundle metadata or history

### Requirement: Existing Method export compatibility

Existing managed textual exports SHALL retain their Core-canonical contract, exact metadata and explicit drift import or regeneration workflow. Adopting an export as a personal file skill SHALL require an explicit authority transition that preserves the old Method and original export evidence.

#### Scenario: Inspect an existing export

- **WHEN** a pre-transition managed export is edited
- **THEN** inspection reports export drift and the original Method version remains canonical for that export
- **AND** the edit is not silently registered as a personal bundle

#### Scenario: Explicit adoption as a personal skill

- **WHEN** the owner confirms adoption of an export into a named personal bundle
- **THEN** the new bundle identity and authority are recorded along with the export's exact original bytes
- **AND** the prior export target is retired from regeneration at that adopted path or the personal bundle uses a separate path

### Requirement: Durable recovery and retention

Bundle registration and activation SHALL be durable and recoverable with exact operation receipts. Verified versions referenced by Methods, invocations, pending changes or unresolved effects SHALL remain retained. Backup, restore and independent corpus rebuild SHALL preserve bundle identities, manifests and exact bytes.

#### Scenario: Rebuild without the prior projection

- **WHEN** a verified synthetic backup is restored and its SQLite projection is rebuilt independently
- **THEN** registered bundle versions, selected invocation versions and their bytes agree with the pre-backup state

#### Scenario: Interrupted activation

- **WHEN** activation loses its reply after a possible file or registration change
- **THEN** inspection determines the original operation's actual state or preserves an unresolved barrier
- **AND** automatic repeat cannot bypass that barrier with a new request identity

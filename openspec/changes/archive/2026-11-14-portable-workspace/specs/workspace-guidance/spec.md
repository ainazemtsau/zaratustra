# Spec Delta

## Purpose

Let file-capable assistants discover workspace rules and the selected Activity's procedures from a small portable entry document.

## ADDED Requirements

### Requirement: Short portable entry instructions

The installed root `AGENTS.md` SHALL route to system guidance, owner guidance, the Activity map and applicable skills. A clean installation's entry document SHALL contain at most 30 nonblank lines. Detailed workflows SHALL live in referenced files.

#### Scenario: Discover a workflow from the root

- **WHEN** an assistant reads the root entry instructions in a clean synthetic workspace
- **THEN** it can locate the Activity map, owner rules and a named skill using relative workspace paths
- **AND** the product entry document meets its stated size bound

### Requirement: Explicit Activity guidance binding

Each configured Activity guidance path SHALL bind to a stable Activity identity. Selecting an Activity SHALL resolve that binding independently of the current directory. A missing or ambiguous binding SHALL be reported before the assistant claims that Activity guidance was loaded.

#### Scenario: Select Health while remaining at the root

- **WHEN** the active Activity is synthetic Health and the current directory is the workspace root
- **THEN** the qualified Pi adapter loads the guidance explicitly mapped to that Activity
- **AND** it identifies the guidance path and exact observed version

#### Scenario: Legacy document path

- **WHEN** an Activity has a document outside a directory named after that Activity
- **THEN** guidance resolution uses the explicit Activity mapping and preserves the document's path and references

#### Scenario: Unavailable guidance

- **WHEN** a mapped guidance file is missing, unreadable or outside the permitted workspace
- **THEN** the adapter reports the unresolved guidance and does not substitute another Activity's file

### Requirement: Guidance replacement and instruction authority

On Activity change the qualified adapter SHALL replace its active Activity guidance and preserve workspace guidance. Historical tool results and retrieved sources SHALL retain their data status. Owner guidance and personal skills SHALL operate within runtime trust, access and confirmation requirements.

#### Scenario: Switch Activities

- **WHEN** Pi switches from synthetic Health to another Activity
- **THEN** the next request's active guidance identifies the newly selected Activity
- **AND** the prior Activity's instructions are absent from the adapter's active guidance section while earlier transcript content remains historical

#### Scenario: Skill requests broader access

- **WHEN** a personal skill or Activity file requests access beyond the current runtime scope
- **THEN** existing runtime permission and confirmation checks remain enforced
- **AND** the file content supplies no additional authority

### Requirement: Instruction-led use by another assistant

The portable guidance SHALL describe a complete workflow over ordinary workspace files for an assistant without a Core adapter. It SHALL explain Activity selection, skill loading and result placement. It SHALL identify which operations require an adapter and distinguish ordinary file edits from committed Core operations.

#### Scenario: Codex baseline walkthrough

- **WHEN** Codex reads a freshly initialized workspace and follows a synthetic Activity's skill without a Zaratustra Core adapter
- **THEN** it can produce the specified ordinary document at the documented path
- **AND** the walkthrough records instruction usability separately from managed persistence and mechanical test results

#### Scenario: Existing managed document edited externally

- **WHEN** an assistant without an adapter changes a previously managed document
- **THEN** the guidance requires inspection and explicit reconciliation through a qualified adapter before claiming updated managed history

### Requirement: Adapter guidance and discoverability

Each assistant integration SHALL declare its available capabilities and reference canonical workspace guidance and bundles. Generated discovery files SHALL record their origin and version and follow installation conflict rules. A generic reader SHALL be given an explicit entry-file loading instruction when automatic discovery is unavailable.

#### Scenario: Two assistant discovery surfaces

- **WHEN** Pi and Codex discovery entries reference the same personal skill
- **THEN** both resolve to the canonical bundle and generated entries are identifiable as product-managed integration files
- **AND** editing a generated entry is detected as a conflict before regeneration

#### Scenario: Native Pi discovers the installed portable workspace

- **WHEN** the installed archive is attached to a workspace with both Pi and Codex discovery enabled
- **THEN** native Pi discovery selects one shared generated route for each system and configured personal skill
- **AND** it reports no collisions between product-owned workspace routes and that same package's fallback skills
- **AND** the shared route identifies the exact canonical source path and hash for both assistants

#### Scenario: Real owner collision remains visible

- **WHEN** an independently owned skill conflicts with a product skill name
- **THEN** native discovery retains its genuine conflict diagnostic
- **AND** the adapter does not suppress warnings or remove owner skills by name during prompt preparation

#### Scenario: Retire an obsolete generated Pi route

- **WHEN** an update replaces separate generated Pi and Codex routes with their shared route
- **THEN** it removes only obsolete files whose identity and bytes match their recorded generated state
- **AND** modified or independently owned Pi files remain explicit conflicts or untouched owner files

# Personal skill bundles

Personal skills live in `skills/personal/<name>/`. Their files are the editable
original. A Method can refer to the registered skill while keeping its own
applicability, input and output contracts and inline instructions.

```text
skills/personal/summary/
  bundle.json
  SKILL.md
  references/checks.md
  scripts/check.js
```

`bundle.json` gives the bundle its stable identity and entry point.

```json
{
  "format": 1,
  "skill_id": "8820d7be-6728-4c80-987c-4e3557a88dd8",
  "name": "Synthetic summary",
  "entry": "SKILL.md",
  "file_roles": {
    "references/checks.md": "support",
    "scripts/check.js": "executable"
  }
}
```

The complete bundle includes its metadata, instructions, references and scripts.
Capture preserves exact bytes, including line endings and BOM. The inventory
records sorted relative paths, lengths, roles and SHA-256 hashes. Each registered
revision has its own number and complete content hash. Restoring older content
creates a new revision with the earlier content hash.

A bundle supports up to 128 regular files, 256 KiB per file and 1 MiB total.
`SKILL.md` is limited to 64,000 UTF-8 bytes. Paths must be ordinary relative paths
without links, Windows aliases, case collisions or file/directory collisions.
Scripts and declared execution inputs keep their protected roles. Registration
inventories and retains scripts without executing them.

## Registration and owner edits

In Pi, `zara_skill_bundle_inspect` compares the working files with registered
versions. `zara_skill_bundle_preview`, native confirmation and
`zara_skill_bundle_apply` activate exact reviewed bytes. A preview binds the
complete inventory and content hash. Large textual display excerpts are labelled
as incomplete and `zara_skill_bundle_read` provides bounded retained reads.

Editing a working file creates pending drift. A managed invocation using the
current version requires reconciliation before it proceeds. An explicitly pinned
historical revision reads the retained selected version. Product installation and
updates preserve personal files.

Publication uses a documented single-writer window for external editors. The
runtime guards and inspects actual before and after bytes, journals multi-file
effects, and keeps an unresolved operation reserved through reconciliation. After
a lost reply, inspect the original operation. Its UNKNOWN state requires
reconciliation before another dispatch. Owner-confirmed compensation verifies
the exact previous working content and preserves later conflicting edits.

## Methods and selected versions

The optional Method `skill_refs` field supports current or pinned selection.

```json
{
  "skill_refs": [
    {
      "skill_id": "8820d7be-6728-4c80-987c-4e3557a88dd8"
    },
    {
      "skill_id": "1bcd5d42-dc6c-4cbb-aee9-d45ca9435c30",
      "revision": 3
    }
  ]
}
```

An absent revision selects the current verified version once at invocation.
An exact revision selects that retained historical version. Invocation history
stores `selected_skill_versions` alongside the exact Method closure. Legacy
Methods with inline instructions remain usable, with absent skill references
resolved as an empty list while their retained bytes remain intact.

An invocation-specific version view contains all selected supporting files at
their relative paths. Working-file edits cannot substitute new references or
scripts into the old selection. Native script execution still requires its
applicable tool authority. A selected manifest establishes the input version,
while observed tool results establish what actually happened.

## Delegated Sleep maintenance

Owner confirmation through `zara_skill_delegation_preview` and
`zara_skill_delegation_apply` binds one Activity, one skill, allowed text paths and
a byte limit. Local eligibility requires at most one live Method consumer in that
Activity and no shared Activity or unrestricted adapter exposure. The check
covers protected consumers and reports a generic scope refusal when owner review
is required.

Consumer discovery follows the complete Method dependency closure, including
selected historical revisions and content versions. A Method that uses a skill
through another Method counts as a consumer. Qualified dependency edits and
archive operations participate in the same publication gate.

Sleep can apply a validated text change under that exact delegation. Scripts,
execution inputs, metadata, permissions, goals, commitments and product guidance
remain outside that automatic text permit. Shared skills and executable changes
require their appropriate owner review. Core mutations of consumers and
delegation participate in the same reservation through activation and receipt.

Rollback publishes retained prior content as a new revision and refuses later
owner drift. One applied bundle consumes one existing Sleep improvement slot.
Application success and later evidence of usefulness remain separate records.

## Existing textual exports

`zara_skill_export_preview`, `zara_skill_inspect` and
`zara_skill_import_preview` continue to operate on Core-canonical Method exports.
Editing such an export creates explicit drift. Personal-bundle adoption names
the original exact export and preserves its Method and source bytes. Same-path
adoption retires that target's export regeneration authority in the exact owner
decision. Separate-path adoption keeps the original export usable unless the
owner explicitly includes its retirement in the reviewed transition.

## Preservation and access

Managed bundle metadata uses projection schema 11 and control format 4 with corpus
envelope format 1. A populated predecessor workspace requires the verified
transition described in [workspace migration](WORKSPACE-MIGRATION.md).

Backups include canonical bundle/version/operation/delegation metadata and all
retained file bytes. An independent projection rebuild restores exact historical
selections. Retained skill lineage and unresolved publications pin their Method
and Activity grounds during managed cleanup.

Managed reads enforce the current skill and Activity access boundaries. Ordinary
filesystem readers operate under their local process and OS permissions.

Each registered version also retains its original Activity and adopted Method
grounds. A later binding change can activate a separately reviewed version while
historical versions keep their original access dependencies. Method and invocation
catalogs, search, exact reads and native previews use the derived access graph to
honor later restrictions without rewriting canonical historical records.

# Portable workspace

Zaratustra initializes a readable project before an assistant adapter is installed.
Use Windows x64 and Node 24.22.1. From a local product checkout, build once and run
the standalone entry point against a separate project directory.

```powershell
npm run build
node C:/projects/zaratustra/dist/cli/index.js workspace init --path C:/work/example-zt
node C:/projects/zaratustra/dist/cli/index.js workspace inspect --path C:/work/example-zt
```

The package also exposes the `zaratustra` binary. A packaged installation must
include its compiled runtime, source resources, instructions and system skills.
The portable product fingerprint covers source and resource bytes and agrees
between Pi source loading and the standalone CLI. Compiled commands additionally
verify `dist/build-manifest.json` against the current sources and every compiled
runtime file. Rebuild after source changes before using the compiled entry point.
An exact Git revision identifies a public source only when the checkout is clean.

## Visible structure and ownership

The clean root `AGENTS.md` routes to detailed guidance in at most 30 nonblank lines.
Read it explicitly in a client that does not discover it automatically.

| Path                                  | Ownership and purpose                                                                        |
| ------------------------------------- | -------------------------------------------------------------------------------------------- |
| `zaratustra.json`                     | Installation identity, product fingerprint, installed hashes and Activity/discovery mappings |
| `instructions/system.md`              | Versioned product guidance                                                                   |
| `instructions/workspace.md`           | Owner preferences and workspace-wide agreements                                              |
| `adapters/pi.md`, `adapters/codex.md` | Product instructions for supported operating modes                                           |
| `skills/system/`                      | Versioned product workflows                                                                  |
| `skills/personal/`                    | Owner-editable complete skill bundles                                                        |
| `activities/`                         | Existing Activity guidance and ordinary or managed documents                                 |
| `.agents/skills/`                     | Shared Codex/Pi discovery routes to the canonical skill files                                |
| `memory/`                             | Canonical memory when managed storage is initialized                                         |
| `.local/workspace/`                   | Installation plans, exact before/after bytes, receipts and local coordination                |

Initialization prepares owner areas and system files. Native Pi trust gates the
first managed open. Existing Core storage is detected by its adapter, and its
explicit storage transition follows the separate migration procedure.

An existing owner `AGENTS.md` is preserved while initialization returns a pending
plan with the proposed exact integration. Existing owner guidance and personal
files are preserved on repeat installation. Modified system and generated files
become conflicts for review.

Pi and Codex both discover the shared `.agents/skills/` entries. Updates retire
only unchanged, recorded product-generated `.pi/skills/` copies. An owner-edited
old copy remains a conflict, and unrelated owner Pi skills remain untouched.

## Activity guidance from the root

The manifest's `activities` list maps a stable key to a guidance path. A managed
binding can additionally identify an exact Core Activity. Folder names supply no
identity. The following synthetic mapping preserves an existing document layout.

```json
{
  "key": "synthetic-health",
  "label": "Synthetic Health",
  "guidance_path": "activities/legacy-health/AGENTS.md",
  "core_ref": { "id": "the-existing-core-activity-id" }
}
```

The assistant reads this mapped guidance while staying in the project root. On
Activity change Pi replaces its owned Activity guidance section and retains
workspace rules. Earlier transcript text remains historical data. Missing or unsafe
guidance is reported explicitly. System guidance drift and product fingerprint
mismatch stop its qualified loading until the installation is reconciled.

## Ordinary file workflow

In Codex or another file-capable assistant, read the root instructions, choose the
Activity, load its guidance and read the named canonical skill. Follow its source
and output paths and produce the ordinary result. The skill's references and
scripts are part of its bundle. Script execution uses the client's applicable
tool authority.

Managed Core commits, exact history, protected operations and bounded Sleep use a
qualified adapter. After an external edit to a registered skill or managed
document, inspect and reconcile through that adapter before claiming updated
managed history. Canonical memory envelopes are maintained through Core.

The optional `personal_skills` list creates discovery routes to the same editable
bundle in both assistant surfaces. A local route declares its Activity scope.
General discovery is shared use for managed maintenance policy.

```json
{
  "name": "health-summary",
  "description": "Summarize synthetic dated records",
  "path": "skills/personal/health-summary/SKILL.md",
  "activity_key": "synthetic-health"
}
```

Update regenerates those routes with canonical source paths and hashes. The
complete managed bundle version, activation and Method-selection contracts are
described by the qualified Core tools.

## Update, conflicts and recovery

Create a finite update plan, inspect its entries and exact before/after bytes,
then apply its complete returned ID.

```powershell
zaratustra workspace update --path C:/work/example-zt
zaratustra workspace update --path C:/work/example-zt --apply <exact-plan-id>
```

An accepted plan binds the product fingerprint, resolved directory identity,
manifest, paths and observed bytes. Close external editors for the affected files
through publication. Qualified installer operations serialize using local OS-backed
coordination and participate in existing managed workspace coordination. This is
the supported single-writer publication window for external tools.

The installer verifies published bytes and writes the manifest last. A stopped
operation keeps its durable original identity and before/after files. Inspect it
before choosing completion or compensation.

Internal plans, journals, receipts and attachment intents publish complete staged
JSON atomically. Owner-facing target files retain their existing file identity and
permissions. An unrecognized partial target is reported as a conflict. The original
plan and journal remain available for targeted inspection, including when the root
manifest cannot be parsed.

```powershell
zaratustra workspace inspect --path C:/work/example-zt --operation <exact-plan-id>
zaratustra workspace update --path C:/work/example-zt --operation <exact-plan-id> --recover complete
zaratustra workspace update --path C:/work/example-zt --operation <exact-plan-id> --recover rollback
```

Completion publishes only targets still matching the original before state and
verifies the resulting installation. Compensation restores only bytes still
matching this operation's result. Later edits stop both paths for a new decision.
A settled receipt is returned for the same requested outcome. Another outcome
requires a new reviewed plan and preserves the original receipt.

An existing deployment can name its trusted managed storage explicitly with
`--managed-home <absolute-existing-home>` on workspace and adapter commands. This value is
selected by trusted setup. The installer uses the named home's stable native
coordination, and binds its path, filesystem identity, workspace ID, coordination
ID and epoch into the exact plan and journal. Apply and recovery require that
same home and context. An invalid or unknown home stops the operation for
inspection. Ambient personal environment variables never select this location.
Pi attachment participates in the same selected native coordination and retains
the exact managed context in its durable intent. Attachment settlement requires
the original trusted home option.

```powershell
zaratustra workspace update --path C:/work/example-zt --managed-home C:/work/example-storage
zaratustra workspace update --path C:/work/example-zt --managed-home C:/work/example-storage --apply <exact-plan-id>
```

## Attach Pi

Attach uses the native local package installation of Pi found on `PATH` in a
standard npm layout, with the installed optional npm peer as a fallback. It
reads the CLI entry from Pi's package metadata and checks preservation of
unrelated settings and existing package filters. A local development package
can be attached by its absolute path.

The explicit attach command passes Pi's command-scoped `--approve` for the requested
local package configuration. Native trust for the later managed session is checked
separately.

Portable attachment selects the shared workspace skills and disables raw skill
discovery only for its own exact product package by recording `skills: []` in
that package's project entry. Other settings, packages and resource filters keep
their values and order. The original package continues to ship its skills for
ordinary standalone Pi installations without a portable workspace. Existing
explicit product skill filters or `autoload: false` deltas require review before
attachment; they are never silently replaced.

```powershell
zaratustra adapter attach pi --path C:/work/example-zt --source C:/projects/zaratustra
```

The default source is the exact clean public commit when available, otherwise the
local package path. A caller-supplied public source must be pinned to an exact
commit. The installed checkout and product fingerprint are verified after native
installation. The result reports pending native trust. Open Pi in the same
workspace and accept its project trust before managed processing. Pi checks the
resolved runtime against the installed guidance fingerprint.

Native attachment records its exact request and original Pi settings before
dispatch. A lost result keeps an unresolved operation and blocks a fresh install.
Inspect the reported attachment operation, then settle that same operation by
checking the actual settings and resolved package. Settlement does not run the
native installer again. If the observed state is incomplete, preserve the intent
while reconciling the native package state.

The package-skill selection has its own exact before/after settings in that same
attachment intent. A lost result can finish only that recorded configuration
delta when current bytes and file identity still match its before or after
state. Later owner edits stop recovery for inspection.

```powershell
zaratustra adapter inspect pi --path C:/work/example-zt --operation <attachment-operation-id>
zaratustra adapter attach pi --path C:/work/example-zt --operation <attachment-operation-id>
```

Installing or updating these project files supplies installation authority.
Protected Core writes, skill activation and Sleep delegation use their existing
exact confirmation flow.

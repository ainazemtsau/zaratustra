# Design

## Context

See `proposal.md` for the problem and agreed direction. This design is proposed for owner review.

The current package's `pi` declaration loads `src/extension/index.ts` and four package skills. The extension injects `instructions/bootstrap.md` in `before_agent_start`, while its `context` hook supplies request-local Core data. `workspacePaths` creates `.local` directories after native trust. It does not materialize the proposed portable workspace guidance.

`MethodData` is strict and contains inline instructions and Method dependencies. `invoke_method` records a selected Method closure. `Core.methodExport` renders one textual `SKILL.md` and the extension's export/import tools keep Core canonical. These exports have a different authority contract from the proposed personal bundles.

Activity focus is session-local. Existing document bindings have an explicit Activity reference and an independent path below `activities/`. A folder name cannot supply Activity identity. `StoragePort` exposes portable storage operations, while `DocumentFiles`, output checks and coordination own filesystem effects. Corpus restoration compiles a fixed projection schema, so registering a new collection alone cannot make it restorable.

Sleep already has finite proposals, read premises, validation, one-use application permits, exact document effects and reconciliation. Its local Method policy checks an explicit Activity binding but does not prove absence of other consumers. The SDK excludes general filesystem tools and unrelated extensions.

## Goals / Non-Goals

### Goals

- Provide a useful file workflow before an assistant adapter is installed.
- Keep a single editable original for each personal bundle and exact immutable selections for managed history.
- Use the existing Core/storage/adapter boundaries, native confirmation and bounded Sleep controller.
- Make interrupted installation, bundle publication and storage transition inspectable and recoverable.

### Non-Goals

- A qualified Codex Core adapter, universal automatic skill discovery or cross-machine concurrent merge.
- Automatic conversion of existing Methods or exports into personal bundles.
- Executing arbitrary bundle scripts during installation or registration.
- Personal ZT cutover, public publication or paid model qualification within this change.

## Decisions

### 1. Workspace commands are independent of Pi

Add a small `src/workspace/` module with a public `index.ts` and a `src/cli/` command entry point. The package exposes a `zaratustra` binary built through the existing TypeScript build. Pi-related peer requirements become optional for the standalone entry point. Development retains the qualified pinned versions. CLI imports must not eagerly load Pi, typebox or extension code.

The proposed command surface is `zaratustra workspace init --path <directory>`, `workspace inspect`, `workspace update` and `adapter attach pi`, with the same explicit path option. `init` creates a clean layout. `update` produces a finite plan by default, and an explicit `--apply <plan-id>` accepts the reviewed installation mutations. An existing owner file makes the affected integration pending until such a decision. CLI installation acceptance supplies no authority for protected Core commits or Sleep delegation.

Attach invokes the existing Pi local package installation mechanism for an exact product revision, preserves other Pi settings and reports the subsequent native trust step. It checks the manifest's product revision against the resolved extension. Standalone usage is documented from a locally built or commit-pinned package. Registry publication and a launcher are separate distribution decisions.

Implementation qualification uses one source/resource inventory for the product revision across source-loaded Pi and the compiled CLI. The build records a separate complete compiled inventory in `dist/build-manifest.json` and verifies that source inputs stayed stable during compilation. The compiled entry checks both inventories before use. A Pi Git clone can therefore share the source identity while loading TypeScript directly.

The alternative of entering solely through `pi install` was considered. A product-owned CLI supplies the agreed Pi-absent acceptance path and can share its installation service with Pi setup. A standalone daemon adds an unnecessary runtime lifecycle for this scope.

### 2. Separate visible ownership from durable runtime state

The proposed layout is below. Existing Activity document paths are preserved.

```text
AGENTS.md
zaratustra.json
instructions/
  system.md
  workspace.md
adapters/
  pi.md
  codex.md
skills/
  system/<product-skill>/SKILL.md
  personal/<skill>/bundle.json
  personal/<skill>/SKILL.md
  personal/<skill>/references/
  personal/<skill>/scripts/
activities/<existing-paths>
memory/
.agents/skills/<generated-discovery>/SKILL.md
.pi/
.local/
```

`zaratustra.json` has layout format 1, an installation UUID, product revision, installed file hashes and explicit Activity mappings. It also records selected adapter discovery outputs. Runtime processing rights, native approvals and Sleep delegation are never granted by editing it. A later verified managed binding associates the installation with its corpus identity. These two identities have distinct purposes.

The package is the source of product-owned `system.md`, system skill templates and adapter guidance. Installed system files are tracked exports of that exact product revision. `workspace.md`, Activity guidance and personal bundles are owner-owned. Generated assistant entries point to canonical files and record their source hash. Owner edits to any generated or system file are conflicts to review.

The root entry file is product-managed when created by installation and limited to 30 nonblank lines. If it already exists, the installer preserves it and presents an exact addition referencing portable guidance. The size limit applies to the clean product template, not to an existing owner's document.

The manifest and layout version are independent of corpus/storage formats. Initialization can reserve an empty `memory/` area without initializing Core. Pi performs the first managed open under native trust. The current `.local/memory`, imports, output and backups defaults remain the adapter's storage locations unless a verified existing deployment explicitly binds others.

Keeping only package-resident instructions was considered. Visible versioned exports make ordinary file reading portable and give updates a measurable before-state. Separate hand-edited copies for every assistant would introduce conflicting originals.

### 3. Installation is a guarded plan with a durable receipt

The workspace service inventories paths, ownership and exact bytes before planning. Plans bind the resolved workspace, product revision, operation UUID, before hashes and proposed after hashes. They validate the entire target layout before publication. A conflict blocks activation of the new installation version while inspection reports any already published files.

Use existing containment, no-alias and durable-write primitives behind the storage public API. A local installation operation has a durable journal under `.local/workspace/`, a single workspace mutation reservation and staged before/after bytes. On an existing Core workspace it also participates in stable runtime coordination. On a standalone workspace it uses an exclusive local installer lock whose dead-owner recovery is checked. The CLI owns its lock through publication and receipt verification.

Publish files under the reservation, verify actual bytes and commit the installation manifest last. A manifest commit certifies the complete installed set. Partial publication remains pending and inspection reconciles each target against the journal. Compensation restores only targets still matching this operation's after bytes. A changed target becomes a conflict. Recovery never overwrites a later edit or treats a lost reply as proof of non-execution.

Filesystem inspection and staging happen outside long database transactions. Reuse short coordination phases and exact operation identities. External editors do not participate in these locks, so document the qualified single-writer publication window. Recheck bytes immediately before each write and afterward, retain before bytes, and expose any observed race. The design makes no OS-wide compare-and-swap guarantee against arbitrary simultaneous writers.

Existing file publication uses a checked descriptor to preserve file identity, ACL and mode. It writes at explicit positions, truncates and flushes. New files are created exclusively at their target parent. A partial file write remains an explicit unresolved state. Compensation requires the exact retained observed partial state or a recognized before/after state and preserves subsequent owner edits.

Unconditional copying and root file merging were considered. Exact plans preserve unknown owner files and make repeat installation and conflict recovery testable.

### 4. Guidance loading follows explicit Activity selection

The manifest maps a stable portable Activity key to its guidance path, display label and optional exact Core Activity reference. Existing Activities retain their Core IDs. A file-only Activity can acquire a Core binding through a reviewed import later. Display names and directory slugs never substitute for identity. Mapping edits are ordinary owner configuration until a qualified adapter validates and binds them.

The root entry routes to system guidance, owner guidance, the Activity map and the applicable skill index. A generic reader explicitly chooses the Activity in its conversation, reads the mapped guidance, then loads the named skill and necessary references. The file workflow explains how to produce ordinary documents and how to inspect external edits once a managed registry is present. Direct canonical-envelope editing is excluded by the workspace instructions.

Pi keeps package bootstrap for runtime contracts and adds separately owned workspace and Activity sections. It resolves guidance through storage using the session's current focus before the next request. On a focus change it replaces the owned Activity section and reports missing guidance. It preserves other extensions' sections. Prior transcript content remains historical data, so the adapter identifies the currently effective Activity and exact guidance hash.

Adapter guidance declares available capabilities. Codex's first mode is instruction-led file work. Generated `.agents/skills` or Pi discovery entries are small route files, with canonical paths and hashes. An Activity-local entry declares its Activity scope. An entry advertising unrestricted general use makes the bundle shared. Clients without native discovery receive the explicit root-file instruction.

The four existing system skills need portable instructions for relevant ordinary file workflows and capability-gated sections for Core tools. The Sleep skill describes its qualified runtime requirement. Avoid duplicate automatic loading of both installed system exports and package skill bodies in Pi.

Native Pi 1.4 and the separately observed 1.5 both discover `.agents/skills` as well as `.pi/skills`. Generate one shared `.agents` route for either supported discovery surface. Existing recorded unchanged `.pi` routes become guarded obsolete entries; edited owner files remain conflicts. Portable attachment records its exact own package with `skills: []` so its fallback package bodies do not duplicate the shared routes. Keep the package's skill declaration for standalone or legacy installations. Preserve all unrelated settings and package filters; conflicting explicit own filters and `autoload: false` deltas require review before dispatch.

The attachment's original durable intent binds this policy through its product fingerprint. Record the exact observed native-after settings and intended filter result before publishing the configuration delta. Lost replies remain UNKNOWN; original-operation settlement accepts exact before or after bytes and never redispatches native installation. Real owner skill collisions remain visible. A prompt-time name filter cannot qualify discovery, because native diagnostics are already recorded before the prompt hook.

Packaged acceptance therefore checks extension, skill, prompt and theme diagnostics and selected canonical routes through the actual installed archive. Record the SDK version used. Observing startup/discovery on Pi 1.5 does not by itself extend the qualified managed-runtime contract beyond 1.4.0.

For new attachments, prefer the installed Pi on `PATH` and fall back to an optional npm peer, including a hoisted peer. Validate the npm package identity and resolve the executable from its declared `pi` bin. Keep the development SDK pinned for reproducible checks and allow the compatible Pi 1.x API line from 1.4 in npm peer metadata. Record observed compatibility by operation and actual version.

Relying on directory inheritance alone was considered. Explicit loading supports the agreed root-current-directory workflow and independent legacy document paths.

### 5. Personal bundles have complete versions and reviewed activation

A personal bundle's `bundle.json` contains format 1, a stable skill UUID, name, fixed `SKILL.md` entry point and declared roles for supporting files. The files are the editable source. Core owns registered version metadata, active-version selection, access and execution history. This is one editable content authority with immutable historical snapshots.

Capture includes all regular files under the bundle root, including the metadata file. Use a sorted inventory of relative path, length and SHA-256. Its canonical hash identifies the complete content. Registered versions also have a monotonic revision within the stable skill UUID, so a rollback can publish old content under a new revision with the same content hash. Repeating a completed registration returns its original receipt. Preserve original bytes including BOM and line endings. Initial limits are 128 files, 256 KiB per file and 1 MiB total, with `SKILL.md` limited to 64,000 UTF-8 bytes. These are proposed bounded defaults for this version.

Reject traversal, reparse points, hardlinks, device aliases, Windows case collisions and unstable snapshots. Scripts and support bytes are retained as binary-capable immutable material. Validation checks inventory, UTF-8 text roles and declared references. It does not execute scripts. Executable declarations, known script paths and declared execution inputs receive the confirmation boundary even when their bytes are text.

Introduce a public storage-side bundle service patterned after `DocumentFiles`, with strict portable manifest schemas in Core. It snapshots bytes, stages publication and supplies immutable addressed material. Extend the portable storage contract for binary reads where needed. Core imports neither filesystem implementations nor Pi types.

Add canonical bundle/version/binding metadata collections and their trusted projection definitions. A qualified adapter offers inspect, preview, activation and rollback operations using the existing exact preview/native-confirmation pattern. External edits become pending drift. Ordinary managed invocation refuses working/active mismatch until reconciliation or explicit selection of a retained version. Initial registration and protected activation require owner authority. A valid local Sleep permit supplies only its specifically delegated change authority.

Pending operations retain and pin complete before and after manifests, including an unregistered externally edited before version. Retention, checkpoint and cleanup share typed material-reference discovery for skill records. Ordinary source inventories containing hashes do not select those sources for retention. Backup validation checks registry pointers, exact version relationships, pending effects and required material.

Reusing managed textual document records for bundle effects was considered. Their Markdown identity, path and single-file native-write contracts do not cover a complete executable/support bundle. Reusing their coordination and recovery patterns avoids changing those contracts.

### 6. Methods select skills and invocations freeze the selection

Add optional `skill_refs` to Method data. Each reference identifies a registered skill and either pins a complete version or requests its current verified version. Existing inline instructions and Method dependencies retain their semantics. Resolution treats absent references as an empty list and preserves the exact stored bytes of legacy revisions.

At managed invocation preparation, resolve the Method closure and all skill selections, verify access, check working-file drift, and retain the complete selected manifests and bytes. Extend invocation data with exact `selected_skill_versions`. The selection is frozen once for that invocation. Current-version resolution makes later accepted local improvements usable without changing every Method. Pinned references provide reproducible procedures. Neither selection mode changes old invocation grounds.

The resolver supplies a complete verified version view under an invocation-specific local materialization directory, with relative support and script paths resolving inside that view. It reads retained immutable material rather than the live editable bundle. Validate the materialized inventory before each managed use and refuse drift or missing bytes. Script execution still uses applicable native tool authority and observed results. Materialization grants no execution permission or stronger provenance for opaque shell calls. A managed application cannot attribute a current working script to a previously selected old version.

Persist compact skill identity/revision/hash selections in invocation records to respect the existing 64,000-byte supporting-record limit. Complete manifests remain in their retained version rows. Historical version rows retain original access grounds, and the derived access index links Method, invocation and technical history to both current skill bindings and selected-version grounds. Later restrictions therefore affect discovery and history reads without rewriting canonical history.

Core's reverse-consumer check includes current Method references, Activity bindings and general adapter exposure. Multiple live Methods classify a skill as shared even within one Activity, matching the owner's accepted boundary. Historical invocations retain bytes but do not alone make a new version shared. The trusted check covers hidden consumers and fails closed with a generic reason if coverage or access is incomplete. Ordinary retrieval continues to filter restricted records. Filesystem access remains governed by the trusted local process and OS permissions.

Always pinning every Method to one version was considered. A current-version reference supports delegated improvements, while exact invocation capture supplies historical reproducibility. Unversioned path-only references cannot supply that history or shared-consumer check.

### 7. Existing textual exports keep their own contract

Retain `zara_skill_export_preview`, `zara_skill_inspect` and `zara_skill_import_preview` for registered Method exports. Their paths remain Core-canonical and drift remains explicit. Update bootstrap wording to name this export category specifically and introduce the separate personal-bundle authority contract.

Adoption creates a personal bundle through a preview that names its new identity and retains the old Method and export bytes. Use a separate personal path by default. Same-path adoption requires retiring that target's regeneration binding in the same authority transition. The same path cannot have both an active export writer and personal-bundle writer.

Silently treating every `SKILL.md` as a personal bundle was considered. Explicit adoption preserves existing metadata, confirmations and uncertain file effects.

### 8. Sleep gets a typed skill change within its existing pipeline

Add `skill_change` beside the current finite commit and document-change proposal forms, and an adapter `applySkill` callback beside `applyDocument`. Keep `sleep_propose` and `sleep_apply` as the SDK entry points. Skill reading exposes bounded complete manifest/text chunks from the selected accessible snapshot, rather than general shell or filesystem access.

An owner-confirmed delegation binds the Activity, skill UUID, allowed text paths, limits, delegation revision and permitted automatic activation. It is stored as trusted Core metadata. File location and owner-editable frontmatter cannot create it. Automatic admission requires one or zero live Method consumers within that Activity, no other Activity binding and no general-use discovery exposure. The full consumer set is checked again immediately before dispatch.

A proposal binds exact before and after manifests, selected grounds, Activity state, delegation revision, consumer-set revision/digest, allowed path diff and request hash. Validation rejects changes to scripts, execution inputs, tool permissions, identity, goals, commitments, product instructions or delegation. Shared or executable proposals become pending owner-review candidates. Confirmation uses a fresh ordinary qualified Pi preview over the exact bundle and consumers, without granting an unrestricted Sleep permit.

Stage and retain both complete versions before mutation. Acquire the existing coordinated reservation for the bundle and binding resources, recheck all guards, then publish allowed text changes and verify the entire resulting inventory. Registration activation and receipt publication are the final managed commit point. Until that point managed invocation rejects a working/registered mismatch. Multi-file publication is journaled and recoverable, with the qualified single-writer limitation from decision 3.

Every qualified mutation of Method skill references, Activity bindings, delegations or adapter exposure must honor the same skill consumer-scope resource reservation. Hold it through activation and receipt publication, and recheck the consumer/delegation digest at that final commit. A competing binding mutation waits or receives a conflict. Out-of-band owner edits to discovery configuration invalidate the captured configuration hash and require reconciliation before managed activation. The consumer check and activation therefore form one coordinated admission across the full publication interval.

Bundle publication, installer updates and native adapter attachment also reserve the shared workspace layout resource. This serializes qualified discovery changes across their complete publication interval. Installer plans bind the selected managed home's path, identity, coordination identity and epoch, including an explicitly configured alternate home.

Rollback is a guarded publication of retained previous bytes as a new version. It requires the same delegation or owner authority and exact current-state guards. A later owner edit stops rollback. Recovery inspects original operation and actual bytes, preserves UNKNOWN barriers and never repeats an uncertain dispatch automatically. One bundle application consumes one of the existing three improvement slots. Future usefulness remains a later evidence check.

A general write tool in Sleep was considered. The typed proposal and private exact permit retain the current controller's bounded lifecycle and authority model.

### 9. Persistent compatibility requires an explicit fenced generation

Layout format 1 can be installed without Core. For new managed bundle metadata and invocation fields, propose projection schema 11 and control format 4 while retaining corpus envelope format 1. The corpus manifest's schema becomes 11. Update all compiled projection, validation, administration and rebuild paths, not only table registration. Predecessor readers reject schema 11 and control 4.

The new runtime detects populated schema-10/control-3 stores and requires the explicit verified transition. Maintenance drains active managed sessions and establishes a stable fence before activation. Migration operates on a verified quarantine copy, preserves existing rows and material byte-for-byte, adds empty new collections and produces comparison evidence. The source and backup remain available through cutover. Qualified older stores first use their already supported explicit transition path to schema 10.

Allowing old writers to open additive metadata was considered. Their strict Method contracts and fixed corpus schema could discard or misunderstand bundle selections. Explicit fencing makes the compatibility boundary observable. The proposed next format numbers are review choices, not statements about the currently qualified runtime.

## Risks / Trade-offs

- Text procedures influence future actions. Runtime trust, tool authority and native confirmations continue to gate protected actions, and delegation is restricted to exact bundle paths and scope.
- A filesystem reader can access local files under its OS permissions. Core filtering applies to managed reads and supplies no additional OS isolation. Personal guidance must describe this boundary.
- External editors can race file publication. Use the qualified single-writer window, before/after inspection, retained bytes and explicit conflict recovery. Detecting a race cannot prove which process wrote matching bytes.
- A shared-consumer registry can become incomplete if adapters bypass registration. General native discovery is shared by default unless a validated Activity restriction is declared. Unknown scope requires confirmation.
- The storage transition affects backup and rebuild. Gate managed activation on synthetic populated preservation, missing-projection rebuild and predecessor-writer refusal.
- Copying system guidance can drift from package mechanisms. Installed hashes and product revision checks make drift visible, and Pi refuses a runtime/guidance capability mismatch before managed application.

## Migration Plan

1. Implement and inspect a clean standalone layout using synthetic files, including repeat initialization and conflicting owner guidance.
2. Qualify the new storage generation and bundle retention through a populated synthetic schema-10 copy. Compare every retained existing canonical collection, revision and selected source, allowing only declared generation/epoch metadata and additive collections to differ.
3. Restore the candidate into a separate synthetic directory and rebuild its projection from corpus and retained material without the original database. Exercise explicit old-export adoption, external drift and UNKNOWN reconciliation.
4. Demonstrate the same synthetic Activity/skill workflow first through file instructions and then through trusted Pi. Record any manual usability walkthrough separately from mechanical evidence. Existing document paths and synthetic Web links are comparison fixtures.
5. Present implementation results and remaining acceptance limits to the owner. The later real ZT operation needs separate authorization and a specific verified full cold backup. Rehearse in a copy, inspect Activities individually, compare Health and Web paths privately and make an explicit cutover decision.
6. Before cutover, rollback means preserving the original generation and abandoning the candidate. After new managed writes, a rollback needs a fresh comparison and verified restore or forward repair. Never open a schema-11 generation with a predecessor writer or discard later work to claim rollback success.

## Open Questions

Only naming and presentation details remain deferrable, such as command help wording and the sample ordinary workflow's display name. The command surface, ownership, activation rules, storage transition and evidence gates above are proposed decisions for this review.

# Stage 1: Home, registry and standalone Processes

## Scope and boundaries

Owner-authorized Stage 1 is a usable installed product path through Pi: create,
find and open standalone Processes, groups, typed relationships, basic materials,
and read the same data in a new chat. It does not close the older installation task
in Direction OS or create the owner's personal content.

- **Core / Process** owns identity, title/purpose, materials and mutation history.
  Schema10 is explicit and additive. Released migrations and legacy records remain
  compatible; standalone bootstrap never creates a Work.
- **Home** owns registrations, locations, aliases, group membership, relations
  and transactional receipts. Its SQLite schema1 is independent of Process schema10.
  Cached title/revision/time are observations, not current Process state.
  Unavailable imported sources have no fabricated cache.
- **Commands** resolve human names, select configured context and call public APIs.
  They bind exact local authorization to Core requests and preserve operation IDs.
  Pi's shipped TypeScript extension and Codex's skill share this Python implementation.

The model interprets conversation and asks for missing title/purpose or ambiguous
selection. Code owns IDs, validation, writes and journals. An explicit complete
owner request authorizes creation; stored documents and agent suggestions do not.
W21's trusted local OS user remains the boundary, not an adversarial agent sandbox.

## Installed operation surface

`zara-home setup` connects a selected existing folder to Home or directly to one
Process. No scanning/global config edits. `zara-home run` accepts UTF-8 JSON
`{command, source_ref}` on stdin and returns JSON. Nonzero exit/ok:false means
failure. `zara-home schema` supplies typed input. Technical arguments belong to
the agent, not the end user.

Actions: home.read; process.list/create/register/open/relocate/aliases;
group.create/list/membership; relation.set/delete/list; material.save/read;
catalog.import; workspace.upgrade. Process lists support query/group/limit/offset.
Group lists include member counts; process.list with group returns members.
List pages contain at most100 rows. Material content is separately selected and
paged: character offsets for UTF-8 text, byte offsets for base64 binary chunks.

Exact UUIDs take priority over names. Duplicate human names/aliases return choices.
A Process may belong to multiple groups. Relations store source/target/type;
neither grouping nor linking grants authority. No mandatory parent tree/coordinator.

Creation reserves exact intent in Home before Process-folder effects, and uses
a derived separate operation ID for registration. Changed-path repeats refuse
before creating another workspace. Creation and registration use two databases.
Registry failure reports the retained
Process identity/path and process.register recovery. Exact retries preserve identity;
changed content under the same operation ID refuses. Material writes and immutable
audit records use the existing Core transaction. Reads never repair or migrate.

## Compatibility and recovery

Legacy import preserves names, aliases, identities and paths; work_id is not Home
addressing. Original catalog bytes remain intact. A retirement marker is installed
atomically under the old writer's lock after exact intent reservation and before
import. Changed-operation conflicts occur before retirement. Interrupted import retries
into the same Home. Updated legacy APIs refuse retired catalogs. Old binaries cannot
understand this marker: stop using them to write a retired catalog.

Explicit workspace.upgrade uses SQLite backup before migration. Schema9 records
and restored backup reads are verified. A general multi-release installer/rollback
coordinator is outside this stage. Keep the old environment and backup for recovery;
do not open schema10 databases with old code.

Connection update requires --update-connection and a hash matching the prior export.
Owner-edited connection files refuse; unrelated settings remain untouched. If setup
is interrupted, inspect retained files; a failure is never a successful connection.
Direct setup uses --workspace and the same Home/Process without duplicating data.

## Verification boundary

Tests cover zero Works, material replay/pages/files, groups/relations, missing,
mismatched and moved sources, ambiguity, rollback, read-only database bytes,
registration failure recovery, duplicate legacy designations/unavailable import,
old records/backup restore and connection updates preserving owner settings.

Pi0.85.1 uses the installed @earendil-works/pi-coding-agent API. A first real
fictional conversation created two Processes, two groups, three memberships, one
relation and a material, then read them back. See RESULT.md for final installed-wheel
fresh-chat evidence and full native checks, separate from owner acceptance.
No credentials or personal content belong in public fixtures/reports.

## Exclusions

No semantic memory, decision lifecycle, extension-handler registry, planning engine,
coordinator, autonomous development workers, Telegram or graphical interface. No
automatic creation of Development or migration of old Solmax. Legacy features
remain available but are not Stage 1 prerequisites.

END_OF_FILE: docs/stage1/IMPLEMENTATION.md

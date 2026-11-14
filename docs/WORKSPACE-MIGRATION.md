# Portable workspace storage transition

The portable folder layout uses layout format 1. Managed personal bundles require
projection schema 11 and control format 4. Corpus envelope format remains 1.
These are independent formats. Installing ordinary workspace guidance does not
authorize a populated storage transition.

## New workspaces

The standalone installer creates readable instructions and owner areas. The first
trusted managed open initializes schema 11/control 4. Pi native project trust is
required before its adapter creates managed storage.

Complete personal bundles retain exact binary bytes for `SKILL.md`, metadata,
references and scripts. Core versions and pending operations reference the
complete inventory. Corpus backup includes those bytes and can rebuild the
projection without the previous SQLite database. Runtime material directories
alone are insufficient as a backup.

## Existing schema-10 workspaces

An ordinary new-runtime open reports `MIGRATION_REQUIRED` for a populated schema-10
corpus. The source generation remains available. Operator tools can open a
verified isolated predecessor copy with the explicit `generation: 10` option.
This option supplies no permission to migrate personal data.

The public `migratePortableWorkspace` storage entry point accepts an already-open
quarantine whose project root matches its explicitly designated quarantine root.
Its caller must first verify a full cold copy. The transition preserves existing
canonical rows and exact selected material, adds the new compiled collections,
and changes only the current generation metadata and epoch. The changed epoch
invalidates old runtime authority. Schema 11 and control 4 fence predecessor
writers.

The transition uses a stable maintenance fence, a verified predecessor SQLite
snapshot and an exact durable descriptor. It publishes the upgraded corpus before
the new control pointer. A crash resumes the recorded transition under that same
fence after proving the old runtime dead. An unknown external effect remains an
unknown effect through the transition.

The resulting report compares existing canonical rows and independently rebuilds
a projection from the corpus. Historical rows, IDs and revisions retain their
original representations. Transient source handles remain runtime state. The
original working document paths and external reading links are outside the
schema transition and require their own byte/path comparison.

## Personal cutover checklist

1. Obtain authorization for the specific personal workspace and close its old
   sessions.
2. Make and verify a full cold backup including canonical corpus, retained
   selected sources, Activity documents, skills, configuration and existing
   reading links.
3. Rehearse the explicit transition in an isolated copy. Preserve the original
   workspace and verified backup through cutover.
4. Compare every Activity individually. Verify Health source bytes, document
   identities, revisions, current paths and the ChatGPT Web reading workflow
   privately.
5. Verify backup and restore into a second directory, then rebuild the projection
   without its previous SQLite database.
6. Review the evidence and make an explicit cutover decision. Preserve the old
   generation. After new writes, rollback requires fresh comparison and verified
   restore or forward repair so later work is accounted for.

Public development and mechanical qualification use isolated synthetic data.

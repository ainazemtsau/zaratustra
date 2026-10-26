# Ordinary project startup and owner-controlled Git tracking

Current amendment: concurrent local sessions use schema 9/control 2 and require
Pi 1.4 with Node 24.16+ (qualified 24.22.1). Close predecessor Pi sessions once
before upgrading. Runtime OS leases and short command coordination replace the
lifetime single-writer restriction below. See [current concurrency](CONCURRENCY.md).
Historical verification retains its original labels and versions.

The ordinary startup and owner Git policy below remain current. Its verification
section records the predecessor startup task and its exact versions. The later
Sleep candidate uses the same extension and defaults, adds a third entry skill and
schema 7, and has separate current evidence in
[SLEEP-VALIDATION.md](SLEEP-VALIDATION.md). Historical startup results are not
relabelled as Sleep results.

Install the selected published ref once in the intended project root, then use
ordinary Pi there:

```powershell
pi install --local git:github.com/ainazemtsau/zaratustra@<published-corrected-ref>
pi
```

Review the package and grant native Pi project trust. No launcher, per-launch
Zaratustra environment variables, extra project AGENTS file or disabled peer
extensions are required. Native cwd chooses the project; there is no Git-root
search and model tool arguments cannot choose memory. A fresh process in the same
folder reopens its memory; another folder has separate defaults.

| Persistent path relative to native cwd | Contents                                                                                                               |
| -------------------------------------- | ---------------------------------------------------------------------------------------------------------------------- |
| `.local/memory`                        | SQLite records, Work/plans, versions, Changes, receipts, control/manifest and retained original/derived material blobs |
| `.local/imports`                       | Input/source files; imports also retain managed originals                                                              |
| `.local/output`                        | Generated work results, using existing native preview/confirmation controls                                            |
| `.local/backups`                       | Existing designated bundle destination; creation does not grant administrative scopes                                  |

`.local` means persistent local work data. It does not mean disposable or ignored.
All saved files are available to ordinary Git versioning and the owner's private
GitHub workflow. Git tracks files, so empty directories need no placeholder and
are recreated on startup. The product does not create, inspect, modify or remove
`.gitignore` rules or `.git/info/exclude`, and does not automatically commit or push
user data. Existing owner rules can exclude data; the owner decides whether to
change them. This policy supersedes the earlier preview's automatic ignore policy.
An old preview's `.local/.gitignore` is preserved, not silently removed.

The owner wants access to saved files if a machine dies. This change does not add
synchronization, multi-computer working recovery, automatic backup/export machinery,
a second export format, Git hooks or a running-system restore workflow. Those
outcomes remain deferred. Existing separately implemented administrative tools and
their permissions are unchanged.

## Compatibility and boundaries

An explicitly present absolute `ZARATUSTRA_HOME` retains its legacy profile and
cwd-independent identity. Optional import roots default to `[]`; output/backup
roots remain optional. Empty/relative homes and directory overrides without a home
refuse rather than opening fallback memory. No migration or relocation occurs.

Default preflight checks the destination layout and every ancestor starting at
`project/.local`, not merely at the project root. A `zara.sqlite` or the existing
control/manifest pair there refuses nested initialization before any new roots are
created. This fixes the reviewed case where a legacy `.local` store could otherwise
contain a different fresh `.local/memory`. Normal `.local/memory` reuse remains
valid. A benign standalone `workspace.json` in `.local` or the project remains valid.
Links/junctions, device aliases, package/Pi-cache overlap and known corrupt/missing
stores retain refusal behavior. Removing all identity/control metadata manually is
outside the supported recovery protocol.

Scopes remain `[]` by default. Full backup/export and restore retain existing
explicit administrative scope requirements. Native protected-action confirmations
are unchanged; RPC `hasUI` alone is insufficient. Input remains
`observed_stage_only`, with `original_keystrokes:false` and no owner-feedback
eligibility. Explicit first-untransformed deployments retain their existing
contract. Other extensions' transformations and messages remain intact. These are
managed local controls for one trusted writer, not OS isolation or arbitrary-command
deduplication.

## Predecessor startup verification and version boundaries

Windows 11 x64, Node 22.19.0, npm 11.6.2 and official Pi 1.3.0 are the exercised
profile. Core/storage/schema/approvals/dependencies are unchanged from
`1806881d0b560903a642e098031c5843f0dc42a5`. The previous complete `deliver-3` result
was 132 tests: 130 passed, 0 failed, 2 inherited Windows skips on runtime candidate
`ac662c0383f025c4e04cfb6fd9d8cbb90dd34b54` (unchanged runtime at `1806881`). That is
prior evidence, not a full-suite run on this corrected revision.

The corrected source has 9 startup tests passed, no failures/skips, plus 1 existing
snapshot regression and 1 existing provenance regression passed. It is checked with
formatting, ESLint, types, dependency boundaries, build and RESULT structure checks. The exact executed counts and logs are in
`C:/projects/zaratustra-v1-startup-tracking-evidence-20261021`. The reviewed overlap
and a fresh executor RED are retained; GREEN controls use actual DiskStorage and
native package-discovered tools. No old evidence is rewritten.

```powershell
npx tsx --test tests/startup.test.ts
npx tsx --test tests/extension.test.ts
npx tsx --test --test-name-pattern="provenance" tests/experience.test.ts
npm run format:check
npm run lint
npm run types
npm run boundary
npm run build
node scripts/deliver.mjs
```

The synthetic Git proof runs after SDK session shutdown and SQLite connections
close. It observes the actual open/closed writer-lock and WAL/SHM lifecycle. It
never excludes WAL blindly: any remaining file is inventoried and included. With
fixture-only Pi/cache exclusion and no `.local` exclusion, ordinary `git status`
and `git add -A` expose the data. `git cat-file` verifies actual indexed blobs match
SQLite, control/manifest, retained originals/materials, inputs and outputs byte for
byte. The test disables line-ending conversion/global exclusions only for its own
synthetic Git commands; it changes no owner configuration. There is no fixture
remote, commit or push. This is mechanical closed-file versioning evidence, not a
safe live SQLite Git-commit or multi-machine restore claim, and adds no daily launch
requirement.

Source reports and formatting are finished before the corrected publication.
Afterward the exact public ref is installed normally in a fresh synthetic project
and the existing native test project. No `--no-extensions`, explicit extension path,
checkout fallback, copied credentials or model call is used. Post-publication
identity, negative/positive controls, reused workspace identity and Git-object proof
are recorded only in the new external `FINAL-READBACK.json`; this document does not
attempt to contain its own final commit SHA. Native npm's known six `peer:true`
lockfile metadata removals are recorded separately from version/integrity changes.

No independent PASS, owner acceptance, full R1/F/T31, Codex or Sleep claim is made.

next: solmax

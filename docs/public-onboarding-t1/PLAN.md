# Public onboarding T1 — recovery boundary decision

Status: T1 technical PLAN evidence at public product 0.15.1. This page does not
claim a released updater, Codex/Claude onboarding, owner acceptance, or an
independent user's installation.

## Decision

Keep releases immutable and versioned. Before a supported update, fence all
cooperating product writers and retain two things together:

1. the exact old program/connection release bytes and compatibility identity;
2. one complete recovery root containing the selected workspace plus its catalog,
   coordinator journals, saved exchange packages, artifact bytes, and other
   load-bearing files.

Run migrations on an isolated data copy first. Only after preflight and a complete
recovery root may a later updater migrate the selected path. Until postflight proves
the same workspace identity and current continuation, keep the exact old pair. A
fault restores the whole old root to the same path and resumes with the old release;
it never runs an arbitrary old program against a newer database.

This is the smallest survivor of the T1 probe. T5 still has to implement the lock,
manifest, compatibility matrix, checkpoints, restore command, and a real transition
between two pinned releases.

## Current mutable carriers outside SQLite

| Carrier | Current seam | Recovery disposition |
|---|---|---|
| Required workspace layout | `core/workspace.py`: `processes/`, `artifacts/`, `projections/`, `inbox/` | Preserve the selected root and same path. Empty directories are layout facts. |
| Registered artifact content | `core/artifacts.py`: immutable blobs plus possible staging, quarantine, or unregistered orphan files | Include all bytes. DB metadata alone cannot satisfy verified content reads. |
| Overview projection | `core/projections.py`: `projections/overview.md` | Derived and rebuildable, never authority. It may be regenerated after restore, but preserving it makes the pair manifest exact. |
| First-use plan | `first_use/__init__.py`: `inbox/first-use/plan.json` | Include. It is non-authoritative, but after Core advances its loss truthfully blocks recovery instead of being reconstructed. |
| Material-transfer recovery | `intake/__init__.py`: `inbox/transfers/<intake-id>.json` | Include. It binds the immutable preview to Core receipts and exact same-intent recovery. |
| Entry catalog | `entry/__init__.py`: caller-selected catalog JSON | Include with its stable path. It carries designation, workspace identity/path, Process and Work selection. |
| Creation journal | `process_creation/__init__.py`: `<catalog>.process-creations/<designation-hash>.json` | Include with the catalog. It retains draft/research/proposal/activation progress outside Core. |
| Change journal | `process_change/__init__.py`: `<catalog>.process-changes/<designation-hash>.json` | Include with the catalog. It retains review/decision/planned Result progress outside Core. |
| Saved exchange outputs | `first_use.save_external_chat_request` and `process_creation.save_research_request`: caller-selected write-once files | Include when the current unfinished stage refers to them, or require their exact re-supply before updating. The probe places its request inside the recovery root. |
| Catalog/intake/creation/change lock files | adjacent `.lock` files | Retained coordination files, explicitly not state or authority. Preserve safely; the later updater must acquire a product-wide fence rather than infer state from lock bytes. |

CLI input drafts, responses, and proposals can remain outside the managed root. They
are not authoritative after their complete content/provenance is retained by the
applicable journal/Core record. If an unfinished stage still needs an external file,
preflight must either add that exact file to the recovery root or refuse with its
path; it must not silently drop the stage.

Pack registrations are currently runtime configuration rather than mutable product
state. Their immutable reference is stored in Core, so the program/connection release
slot must still contain the exact compatible adapter and Pack implementation.

## Exact reuse matches

1. Entry: `entry.resolve_entry`, `source_path`, `prepare_entry_read`, and atomic
   catalog replacement already preserve one explicit selection and identity. A future
   readiness surface should read this seam; it must not create another registry.
2. Constructor/change: `process_creation` and `process_change` already retain staged
   intent outside Core, re-read current state, require exact review/confirmation, and
   route the effect through public Core. Combined onboarding should compose these
   stages rather than duplicate their state machines.
3. Core/Mutation: `core.workspace_connection` owns checked transactions,
   `migrate_workspace` owns the released sequential migration chain, and
   `core.mutations.apply_mutation` owns expected revision, rights, idempotency,
   journal event, and receipt. Update orchestration may fence/copy/restore around
   these APIs but cannot become a second domain mutation path.

## Options compared

| Option | Result |
|---|---|
| DB-only backup plus in-place package replacement | Rejected. Artifact bytes, catalog, first-use and transfer/creation/change journals are outside SQLite. The injected missing-plan fault produced `progress_unavailable`; restoring only the DB cannot restore that stage. |
| Two always-live full A/B installations with separate runtime, connection, and data paths | Technically plausible but not selected. It maximizes pre-switch isolation, yet current catalogs/journals can carry path-bound facts, storage doubles, and path portability has not been proven. It is more mechanism than T1 evidence requires. |
| Immutable release slots plus a fenced, complete same-path recovery root and migration-on-copy preflight | Selected. The installed probe preserved exact program/CLI identity, migrated a copy without changing the source, falsified DB-only recovery, and restored the complete pair to the same path with the same stage and receipts. |

The selected option is conditional on T5 proving a cross-process write fence and a
real two-release compatibility transition. Without those, the product must refuse
update before the first write.

## W18–W25 and A03 dispositions

| ID | Current files/seams | PLAN disposition |
|---|---|---|
| W18 | `pyproject.toml`, `uv.lock`, `README.md`, `tools.probe_install` | T4 must name one public artifact/pin, install command, bootstrap checks, and README-only evidence. T1 uses the built wheel hash only as risk evidence. |
| W19 | `core.read_workspace/read_records/read_history`, entry reads, first-use selected context | T2 adds one read-only readiness/resume projection and vocabulary. No Boolean ready file, auto-latest selection, or read-side effect. |
| W20 | Current `zara=zaratustra.cli:main`; no shipped Codex/Claude assets | T4 supplies thin standard assets and explicit README fallback. The T1 console-script identity is not agent-adapter proof. |
| W21 | `process_creation` draft/research/proposal APIs and `process_packs.construction.SUPPORTED_CAPABILITIES` | T3 connects prose to a readable persisted draft and the existing capability producer; semantic choices and create/change permission stay human. |
| W22 | First-use plan; intake, creation, and change journals; Core events/receipts | T2 defines shared stage/receipt reconciliation; T3 composes setup/create/research/change continuation. Journals stay non-authoritative and effects stay in Mutation. |
| W23 | `core.init_workspace`; current first-use new-workspace path; process-creation collision refusals | T2 defines and tests initialized-empty/occupied/foreign/corrupt/incompatible admission, repeat init, and activation revalidation without a hidden workspace. |
| W24 | `core.migrate_workspace`; no installed updater/backup/recovery API | T5 implements the selected immutable-release/full-root topology, compatibility manifest, fence, checkpoints, deterministic resume/restore, and refusal. |
| W25 | Existing product probes plus `tools.probe_public_onboarding_t1` | T6 builds the full user-like fictional release matrix. T1's installed technical probe is not independent-user or release evidence. |
| A03 | Migration copy plus full-pair restore in this probe | Answered for PLAN: select immutable release slots plus complete same-path recovery root. Still conditional on T5's real old/new transition and write exclusion; arbitrary downgrade remains forbidden. |

No W01–W17 acceptance or K01–K11 behavior changes here.

## Probe result

Run from the repository into a new ignored directory:

```text
uv run --locked python -m tools.probe_public_onboarding_t1 --output _scratch/public-onboarding-t1-02
```

Observed installed wheel: version `0.15.1`, SHA-256
`34b8a3889ceb741fbc5f7576558751c7b85a1f678aad41731b3c61a2b76bb7f5`;
connection entry point `zara=zaratustra.cli:main`, SHA-256
`f02862fad3c926d6982364bb453dc1b29c12bf9e39353547eb5f0f313303b58d`.

The migration copy went schema 2 to 7 while its source stayed at 2; workspace
identity, state revision 1, exact record graph, current Work id, and `draft` status
were unchanged. In the richer pair, removing `inbox/first-use/plan.json` after Core
reached revision 7 returned `progress_unavailable`. Restoring the complete quiescent
pair manifest recovered the same workspace id, catalog target, two Core receipts,
and `selected_work_ready` continuation without a new effect.

The exact generated summary, commands, manifests, and receipts are retained only in
ignored `_scratch/public-onboarding-t1-02`; the reproducible tool and runtime assertions
are committed. The first installed attempt failed only because its provenance check
treated the isolated `_scratch` runtime as checkout source; the corrected second run
checks specifically against `src/zaratustra` and passed.

## Remaining sequential product tasks

The accepted order remains T2 readiness/repeat-init admission; T3 prose/draft/manual
research/create/change composition; T4 public pin/README/thin Codex+Claude assets;
T5 installed update/recovery; T6 fictional release gate; T7 fresh binding review.
Each task consumes the preceding exact result. T1 starts none of them and adds no
acceptance.

## Assumptions and cuts

The probe snapshots only after public API calls return and no product operation is
open; this is a bounded quiescent fence, not the future cross-process exclusion.
It uses fictional disposable roots only. It does not test another release, concurrent
writers, a crash during filesystem replacement, platform portability, adapter assets,
private/personal data, release publication, independent use, automatic research,
transport, routing, CI/CD, notifications, or spending.

END_OF_FILE: docs/public-onboarding-t1/PLAN.md

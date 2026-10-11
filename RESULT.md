# Activity setup recovery 0.22.1 — implementation result

## outcome

Implemented durable rejected-result recovery and one shared procedure-operation
catalog in the public product; Core schema remains 15.

## evidence

See [the release report](docs/activity-setup-recovery-0.22.1.md) for the actual
native gate, affected rechecks, installed ordinary Pi, legacy-stage compatibility,
independent send accounting, read-only evaluator finding and wheel SHA-256.

## assumptions

The model interprets user needs; Core checks typed results and permissions.

## cuts

Exports and Git projections are outside this package. No domain templates or
real-model checks. Personal data and reset records stay private.

## cost

Real model and paid API calls: zero. Installed verification: 33 localhost sends.

## manual-acceptance

Checks passed; owner acceptance remains separate and pending real use.

## next

solmax.

---

# Previous release: Activity structures 0.22.0

## outcome

Implemented the owner-audited Activity principles and structure plan in the public
product on `codex/activity-structures`, from
`aa9ffa6888d876a9e24bfba75f6a76924a2773ca`.
Version **0.22.0** explicitly upgrades Core **14 → 15**.

The assistant designs a finite data format and a working process without an
obligatory domain template. Core stores versioned entries, indexed exact
selections, calculations, intake progress, repeatable procedure intents and
reviewed structures. Setup compiles the complete activation manifest before full
review. Existing Activity adoption preserves its address, history and old Work
pins. Procedure execution uses ordinary assigned Pi/DBOS and the selected profile.

Exports and the owner's personal space were not changed. The previous delivery
report is retained in `docs/results/workspace-separation-20261009.md`.

## evidence

### Native checks

| Check | Actual result |
|---|---|
| Addressed Core/setup checks during implementation | 17 passed; the additional composite procedure scenario passed separately |
| Full native gate | 819 passed, 2 failed in 726.81 s; 31 import contracts kept; hygiene/types passed |
| Corrections after the full run | Added the actual `zara_data` tool to ordinary Pi's default list; updated the SQLite failure test double for the registered SQL function |
| Affected native gate after corrections | 20 passed in 17.52 s; build, hygiene, types, 31 boundaries and report structure passed |

The full suite was run once. It is **not** reported as an all-green full gate.
Following the delivery policy, the corrected paths were rerun with the affected
native gate instead of another complete matrix. Logs are retained locally as
`_scratch/activity-structures-native-gate-2.log` and
`_scratch/activity-structures-addressed-gate.log`.

Ten new tests each cover a distinct risk in
`tests/zaratustra/foundation/test_activity_structures.py`:

| Risk | Observed result |
|---|---|
| Composite procedure loses exact inputs or typed output | Child retains the parent input, structure and selection; typed result publishes through the declared binding |
| Migration loses legacy setup or bypasses reviewed format admission | Schema 14 upgrades explicitly; an unreviewed format cannot be installed |
| Repeated/partial intake duplicates events or hides corrections | Delivery resumes, correction retains event address/history, cache/calculations notice changed composition |
| Restart shifts a saved period or creates another Work | Intent is reused across sessions/calendar boundaries; a mismatched raw Core request is rejected |
| Existing Activity adoption/deletion rewrites old history | Existing Work/Activity remain unchanged; removal of the new setup's basis preserves the independent old structure |
| Late data or deleted bases survive in derived inputs | Exact selection becomes stale on late arrival; deletion sanitizes managed input copies |
| Retry silently creates another chain or changes Work pins | Explicit rerun requires its saved basis; a saved Work cannot acquire a later structure |
| Related records, missing values and zero distort calculations | Query roots alone are counted; missing, unknown and zero remain distinct within the period |
| Stop/restore reuses revisions or resets old Work | Restoration preserves editions and the next adoption has a new revision |
| Artifact copies bypass source rights/deletion | Exact provenance is traversed for access and sanitation through ordinary copied Artifacts |

### Ordinary Pi and installed wheel

The successful checkout trace and the final outside-checkout installation trace
each used ordinary **Pi 1.0.4** with a local synthetic provider. The final run
loaded foundation from external installed `site-packages`, not from the source
checkout. Its tool list was the actual ordinary release list.

The installed trace completed with **30 synthetic HTTP sends**, **2 compact
requests** and **3 full review passes**. It exercised:

- interview → saved question → actual user answer; the assistant's question was
  not injected as another user message;
- draft → finding → correction → full review → exact activation;
- typed entry → persisted procedure intent → assigned ordinary Pi Work → typed
  Artifact, with result acceptance still absent;
- compact and a new Pi session using the same exact Work/structure/selection;
- adoption of a monthly structure into fictional existing Development, followed
  by continuation of its pre-upgrade Work with unchanged input and history;
- ContextManifest in every observed provider request and durable send accounting.

Installed CLI upgrade of a separate fictional schema-14 space preserved exact
Activity, Work and input Artifact revisions when read in a new process.
The installed backup/restore check retained the typed entry, ready setup and
unaccepted Work. Restore first quarantined the copy; an explicit normal
`RecoverRequest` preceded those reads. No live user data was used.

One bounded read-only evaluator smoke compared wheel/hash, installed source,
migration evidence, affected gate and final Pi/restore evidence. It found no
additional concrete blocker in those bounded paths. It did not execute another
matrix, product mutation or model call.

Diagnostic failures are retained separately: formatting before tests; a test
harness busy read during a worker write; a restore helper missing the existing
empty destination required by the API. The harness now waits within its deadline
for that known busy read, without repeating model sends. The restore helper
created a new empty destination. Neither failure is claimed as a successful
scenario. Local HTTP shutdown connection-reset traces occurred in the successful
Pi log without invalidating its completed assertions.

### Package

Wheel: `dist/zaratustra-0.22.0-py3-none-any.whl`.

SHA-256:
`FE685F62A6469AAF06CC359952738CE79609CA4C21B10361334300D57D2C57A0`.

Runtime verification: Windows, Python 3.13.7, SQLite 3.53.3, ordinary Pi 1.0.4.
Dependencies were installed with production versions exported from `uv.lock`.

## assumptions

Core SQLite remains domain authority; text exports remain derived views.
Typed contracts describe structure; model reasoning supplies domain meaning.
Closing Pi stops new execution; durable intent allows continuation next session.
There is no scheduler operating while Pi is closed.

The selected model/subscription profile remains authoritative; there is no
automatic paid API fallback. Synthetic verification does not evaluate the
semantic quality of a real model's proposed Health programme.

## cuts

No export writer, Git projection/layout, retention policy, dashboard, sync engine,
external storage or mandatory domain template was changed. No personal Health
deletion/recreation, personal-space upgrade or Git publication was performed.
Future adapters can consume the public typed API; a future UI is not shipped.
Legacy Activity/Work does not acquire a new structure silently.

## cost

The final installed trace observed exactly 30 local synthetic sends. The earlier
successful checkout trace also observed 30. Failed diagnostic traces remain
separate; these counts are not a total over every development attempt.
Real-model and paid-API sends by automated checks: **0**. Other checks, upgrade,
backup, recovery and evaluator inspection were model-free.

## manual-acceptance

Owner acceptance is pending. Review activation and product publication do not
accept a Work result. Existing personal Health and Development remain untouched.
Recreating personal Health requires a separate explicit action; existing
Development can adopt a structure without losing history.

After closing Pi, update the installed package and selected Core:

```text
uv tool install --force --from dist/zaratustra-0.22.0-py3-none-any.whl zaratustra
zaratustra upgrade
zaratustra
```

`upgrade` makes a backup and explicitly upgrades the selected Core; it does not
replace the Python package or recreate Activity. See `docs/activity-structures.md`.

## next

solmax

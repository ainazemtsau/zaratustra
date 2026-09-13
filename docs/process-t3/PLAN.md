# Process creation T3 plan

Basis: CALL `c-solmax-zaratustra-process-t3-20260913`, contract 36 PROBA,
starting commit `3929b2242a000674d8e408b1f6518c5698b70661`. No root STOP or
STEER is present. T3 proves one safe future-edition seam; it does not migrate
already-started Work, rebind Core, or complete the later T4 synthesis.

## Exact edition boundary

Extend the generic construction registration with an optional immutable edition
transition. A transition is pinned to the exact current Work id, original and new
definition bytes/digests, and exact prior snapshot digest. It is admissible only
when the definition id, title, sources and capabilities stay exact, the edition
increments once, every completed/current node stays byte-exact, and replay under
the proposed edition selects the same current Work. Only untouched future nodes
may change or be added.

The current Work continues under its original definition and unchanged immutable
Process/Work Pack reference. When its exact accepted snapshot is later submitted,
the registered rule projects that preserved history onto the explicitly approved
edition and proposes the next Work from it. Core's existing exact-confirmed
`submit_result` remains the first committed effect: its one transaction completes
the old Work and creates the new Work, whose requirements pin the new definition
and transitioned basis. No mutable latest lookup, Core mutation kind, migration,
or Pack rebinding is added.

## Reviewed and recoverable product path

Add a small installed `process_change` coordinator. It resolves the catalog row
only as the Process/initial-Work identity anchor, then follows exact committed
Result `next_work` lineage to the sole tail. An authorized Core context supplies
the exact current basis snapshot; timestamps and the catalog's T2 first-Work
selection never choose continuation.

The readable UTF-8 preview binds the complete old/new definitions, exact structural
diff, current Work invariants, projected old/new next Work, Pack identity, revision,
and the statement that approval is retained intent until Core accepts Result.
Approve or reject requires an exact preview-bound trusted decision. Reject retains
the decision and changes no Core state. Approve atomically retains one pending
transition in a locked adjacent journal; it grants no Core authority.

Once the source Work has an accepted Result snapshot, a separately authorized
context produces and retains one exact `submit_result` request with fixed operation,
next-Work and Artifact identities. A separately authorized Core call applies it.
Status reconciles the journal against Core history, distinguishes pending/planned/
applied/rejected, and recovers a committed reply or journal-save failure without a
second effect. Changed proposal/target, stale revision/snapshot, wrong edition,
missing rights, request collision and terminal divergence refuse without replacement.

## Evidence and limits

Use only the two existing external fictional definition inputs, deriving edition-2
variants in tests/tools without changing their accepted bytes. Prove the difficult
pack transition first, then coordinator behavior for approval, rejection, stale/
wrong/missing-rights siblings, restart, replay and exact preservation of database,
artifacts, records, handoffs, history, bindings and current inputs. A development
probe records before/after manifests, definitions, snapshots, requests and receipts.

Exercise the built wheel from an isolated environment with both fixtures supplied
externally and record every `zaratustra.*` import origin. Run focused tests while
changing code, then one required full `tools.check` and one report-aware `--deliver`,
retaining full logs under new ignored `_scratch/process-t3-*` directories. Increment
the product minor version, commit implementation first, then commit accurate
READOUT/RESULT. Manual acceptance and HOME's fresh binding refutation remain pending;
`next: solmax`.

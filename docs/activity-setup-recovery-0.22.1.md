# Activity setup recovery — 0.22.1

## outcome

Implemented on `codex/activity-setup-recovery` from public main
`d8a311182f6cd675b9ecfad71ff7a3439cee14ea`. Core schema stays 15.
Publication and owner acceptance are separate from implementation evidence.

The operation enum, preparation/review packets, compiler and installed adapter
checks share one catalog. It includes `working_set`. Free prose is not converted
to operation names. New setup stages pin `setup_json`; existing stages and
ordinary assigned Work keep their previous envelope.

Completed raw text, including empty text, is retained before JSON validation.
Core stores the rejected Artifact, typed field diagnostics, repair lineage,
counter and next state atomically. The same stage kind is repeated with the whole
packet. Two corrections follow the first response; a consecutive repeated error
stops earlier. Each started review Work also consumes a full-review pass.
Rights, changed bases, storage failures, saved-state corruption and unknown sends
do not authorize a corrective model request.

## evidence

| Check | Observed result |
|---|---|
| One native gate: `uv run --locked python -m tools.check` | 837 tests passed; hygiene, types, 31 module contracts and wheel/sdist build passed |
| Initial targeted setup/bridge/integrations run | 51 passed |
| Affected checks after the empty-publication correction | 52 passed: setup, recovery, structures, execution, Work and bridge |
| Final types after the test helper correction | Seven affected files passed; the corrected empty-publication test passed again |
| Ordinary Pi from checkout, fictional localhost provider | Invalid raw JSON → invalid operation → full draft → blocking full review → whole correction → full review → activation; compact and existing Development continuation passed |
| Wheel installed in a separate temporary venv, `pip check` | Product and executor imported from site-packages outside checkout; dependencies compatible |
| An actual stage created by wheel 0.22.0, resumed by 0.22.1 | Saved JSON and packet checksum unchanged, legacy envelope used; one accounted synthetic send, retained result; no duplicate Work |
| Ordinary Pi 1.0.4 using the installed wheel | Empty raw response retained → addressed operation error → corrected draft → full review/correction/full review → activation; two compact sends; first Work result remained unaccepted; old Development continued |
| Independent accounting in installed Pi scenario | 32 actual localhost HTTP requests; 32 answered Core deliveries |
| Installed Pi renderer/hooks probe | Saved question visible; no phantom user question; both compact parts filter legacy setup notices; no duplicate notifications; zero provider sends |
| One bounded read-only evaluator smoke | Found whitespace/empty-response barriers; fixed and verified through actual publication and installed Pi. No model or user-space execution by evaluator |

Wheel SHA-256:
`6C94EE074FC9E13E2EB2E6B505D0241F6715A2174E69399866FC29174D12188D`.

Development logs and fictional reports were retained in ignored scratch storage:
`_scratch/activity-recovery-native.log`,
`_scratch/activity-recovery-final-focused.log`,
`_scratch/activity-recovery-final-types-2.log`,
`_scratch/activity-recovery-installed.log`,
`_scratch/activity-recovery-ui-20261011/report.json`.

The retained regression tests cover these distinct risks:

| Risk | Observed assertion |
|---|---|
| Short, detailed, forwarded or incomplete input gets discarded | Original Sources and saved question survive reopening; Activity identity is unchanged |
| Malformed, whitespace or empty JSON locks preparation | Raw Artifact survives, draft/manifest are absent, diagnostics and correction lineage survive reopening |
| Operation prose or missing `working_set` blocks compilation | Exact field path and finite allowed names returned; corrected procedure compiles and its public call works |
| Invalid correction/review changes the wrong stage kind | Same kind repeats with full current packet and exact reviewed bases |
| Restart resets counters or repeated failure loops forever | Receipt replay does not duplicate Work; repeated error and third invalid result stop; explicit retry preserves history |
| A malformed fifth review bypasses its limit | Sixth automatic review is refused and the counter remains five |
| Scope refusal or corrupt saved manifest gets called a model typo | No rejection/repair authorization is created; stored setup state remains unchanged |
| Rejected content is omitted from maintenance | Backup/restore retains it; deletion of its basis sanitizes original, setup and diagnostics |
| New optional fields alter old serialized pins | Legacy default fields remain absent from serialized stages |
| Empty publication weakens ordinary Work | New internal setup can retain zero bytes; ordinary Attempt publication refuses zero bytes without creating output |

## assumptions

The model interprets user needs and designs the structure. Deterministic code
validates its typed output and authority; it does not recognize Health or other
domains by words. Existing product design/review guidance remains applicable.

## cuts

No exporters, Git projections, template platform, real Health creation, paid API,
real model calls or general budget changes. Personal reset and preserved originals
are recorded privately. Existing ordinary Work acceptance remains explicit.

Synthetic tests prove transport, saved inputs, recovery and effects. They do not
prove the quality of a real model's interpretation, nutrition/training advice or
absence of every future defect. Local HTTP keep-alive teardown logged connection
resets; completed runs, saved results and send accounting were checked separately.

## cost

Real model calls: 0. Paid API calls: 0.
The outside-checkout compatibility check used one localhost send; the complete
installed Pi scenario used 32. Checkout probes used fictional localhost only.

## manual-acceptance

Implementation checks passed. Owner acceptance is pending real use. No ordinary
Work was automatically accepted, including the fictional first Work.

## next

solmax. Owner creates the real new Activity from a short goal, fuller description
or preserved original answers; questions should concern missing user decisions.

# Process creation T2 plan

Basis: CALL `c-solmax-zaratustra-process-t2-20260913`, contract 36 PROBA,
starting commit `31113d89bd447aa5f485b8735dbc610e7017365a`. No root STOP or
STEER is present. T1's exact construction adapter and fresh verdict are evidence;
they do not complete this task. The owner's no-subagent instruction applies.

## W10/W11 — saved need, clarification and manual research

Add one installed `zaratustra.process_creation` coordinator behind `zara entry
create`. A creation is selected by the existing human catalog path and designation;
the ordinary draft contains only the need, outcomes, constraints, relevant declared
capabilities and necessary clarification questions/reasons/answers. It contains no
Core ids or paths. An incomplete answer remains visibly `draft`; an exact replacement
is allowed only before a research request is fixed.

The coordinator keeps one locked, atomic, non-authoritative journal beside the
explicit catalog. A complete draft produces one non-overwriting format-1 research
request whose readable text mechanically includes the exact need, outcomes,
constraints, answered clarifications and declared capabilities. It is provider
neutral and contacts nothing. The human runs it elsewhere. `receive` saves bounded
UTF-8 return bytes, their digest, source label, and exact request identity/digest.
Returned material is always labelled untrusted research and never approval. Retries
reuse identities; changed request/return bytes under them refuse.

## W14 — supported proposal and confirmed activation

`propose` accepts assistant-authored generic `ProcessDefinition` JSON; the product
does not generate or hardcode a workflow. It uses T1 `evaluate_snapshot` for graph,
recurrence and capability validation. Definition sources must link to the exact saved
research request and exact returned bytes by canonical SHA-256 locators, plus the
declared capability locators. Every node keeps understandable reasons through the T1
source ids. Unknown capabilities refuse explicitly. The exact definition, digest,
source text and reasons remain inspectable in creation status.

`prepare_activation` explicitly selects a new workspace, bootstraps schema 7 and
Core draft records through public APIs, then retains one immutable plan. The product
derives an exact Pack reference from the definition digest and fixes the initial
requirements, empty canonical definition snapshot and six Core requests:
`authorize_work`, `set_work_requirements`, `bind_pack`, `authorize_artifact`,
`publish_artifact`, `accept_handoff`. The accepted empty snapshot is the first Work's
starting basis, not its Result or completion. One canonical activation preview shows
the full proposal/source digests, target identities, immutable binding and requests.
The trusted local console confirms that exact preview once; only then may the
coordinator derive the request-bound Core authorizations and apply the missing suffix.
After authoritative success it adds/repairs the existing common-entry row, and the
first Work must open through the existing designation-based Core context path.

## W15/A03/W17 — recovery, truth and invariant checks

The journal never grants authority or proves a Core effect. Every prepare/status/retry
re-reads public Core records/history, verifies the exact contiguous request prefix,
the exact registered snapshot bytes and accepted Handoff, and reports the current
Work status/scope/binding from Core. A crash before catalog registration is repaired
only after those facts are revalidated. A different workspace, definition, request,
return, operation identity, intervening mutation or catalog target refuses; no rebase
or adoption occurs. Pending request identities and exact current revision remain
stable across restarts.

T1's repaired invariant is retained at the new seam: the first Work requirements pin
the exact empty-snapshot digest; later continuation still requires each prior
canonical snapshot digest, so a full later snapshot cannot rewrite earlier result
data. Tests inspect sibling source/request, publication/acceptance and catalog seams,
including stale rights and recovery after every meaningful prefix.

## Product/test surface and limits

Add the module's nearest `AGENTS.md`, public CLI stages `draft`, `request`, `receive`,
`propose`, `status`, `activate`, a trusted exact-preview console adapter, import
boundaries, mirrored behavioral tests and one development probe. Extend the existing
two development-only `small` and `project` fixtures with synthetic need/research
inputs; no example ships in the wheel. The probe must exercise the installed CLI/API
path in new supported workspaces, retain exact evidence, distinguish dependency/data
and lawful recurrence, and open the activated first Work through common entry.

Run focused checks while changing code, both fictional probes, then one full native
`tools.check` and report-aware `tools.check --deliver`, with full long logs in a new
ignored `_scratch/process-t2-*` directory. Commit implementation first, then exact
READOUT/RESULT evidence in a report commit. T3 retains full safe definition/process
evolution; T4 retains fresh physical installed readers. No provider, external service,
Core/migration semantic change, in-place Pack migration, arbitrary loader, user data,
Direction edit, CI or push is included.

## HOME technical pre-pass disposition

The retained HOME note identified two in-scope faults. Strict Python validation of a
decoded JSON object rejected the JSON arrays emitted by a valid frozen tuple model;
the boundary now performs duplicate-key/UTF-8/size checks and then uses Pydantic's
strict JSON validator. The exact `CreationDraft.model_dump_json().encode()` regression
passes.

The wrong-target case was reproduced independently with the new regression and the
preflight guard temporarily absent: activation refused eventually, but had already
migrated an unrelated schema-2 workspace to schema 7. The repaired order refuses an
already initialized target before saving an activation reservation, initialization or
migration. Only a catalog-adjacent target reservation created while the selected path
has no managed state may proceed; the resulting Core workspace id is durably pinned
before migration and revalidated on recovery. The same regression then passed with
both `WorkspaceInfo` and the full public records snapshot unchanged.

The later HOME presentation pre-pass found that the first activation preview bound
only proposal/source digests, not the proposal a human needed to understand. The same
single confirmation object now contains the full bounded supported definition, the
evaluated first Work including reasons, and the exact readable request/research source
texts with distinct trust labels. Its confirmation bytes use real UTF-8 without
Unicode escape reconstruction. No second approval or digest-only substitute exists.
The CLI research-request command still saves the canonical transport file and now
also emits its exact copyable request as plain stdout; technical save metadata goes to
stderr. Focused behavior, CLI presentation and Cyrillic UTF-8 regressions pass.

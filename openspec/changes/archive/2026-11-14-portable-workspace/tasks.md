# Tasks

The owner approved implementation on 2026-11-04. The coordinator owns shared schemas, public module APIs, persistent formats, integration and release evidence. Workers receive exclusive module ownership and preserve concurrent edits. Use at most ten processes and isolated synthetic workspaces.

## 1. Shared portable contracts

- [x] 1.1 Coordinator defines layout format 1, installation plan/receipt and Activity mapping contracts at the new workspace public entry point. Verify types and documented examples for empty, existing-owner-file and invalid-path cases.
- [x] 1.2 Coordinator defines complete bundle manifests, revision/hash identity, optional Method skill references, selected invocation versions and delegation/consumer guards through Core's public contracts. Verify schema fixtures include legacy absent fields without rewriting retained records, and document the distinct personal-bundle and Method-export authorities.

## 2. Standalone installation and Pi attachment

This group depends on group 1 and works before managed storage initialization. Its worker owns `src/workspace/`, `src/cli/` and installation templates. The coordinator integrates package entry points and storage public primitives.

- [x] 2.1 Add the built `zaratustra` CLI and optional Pi peers while retaining dependency versions. Verify the packaged CLI can initialize a clean synthetic directory with Pi absent and no extension imports or model calls. Document the exact local or commit-pinned package entry command and run it as written.
- [x] 2.2 Materialize the short root entry, system instructions/skills, owner areas, adapter guides and installation manifest. Verify clean installation and repeat installation preserve installation identity, personal bytes and owner-created files, including an existing root `AGENTS.md`.
- [x] 2.3 Implement exact update plans, conflict acceptance, full path checks and the qualified single-writer publication window. Verify refusal for stale bytes, junctions, hardlinks and Windows collisions, plus preservation of conflicting owner and generated files. Document conflict review and publication limits in command help and workspace guidance.
- [x] 2.4 Implement durable installation journals, local/managed coordination, manifest-last activation and operation inspection. Verify competing installers, interruption at publication boundaries, reply loss and compensation encountering later edits. Document recovery using the original operation identity.
- [x] 2.5 Implement explicit Pi attachment through the native local package mechanism and exact revision checks. Verify existing Pi settings survive, native trust remains required and the same ordinary Activity documents and personal bundle are discovered after attachment. Document the attachment and trust steps.

## 3. Persistent generation and portable material

This group depends on group 1. The storage worker owns `src/storage/` behind its public entry point. The coordinator owns matching Core contracts and format integration.

- [x] 3.1 Add projection schema 11/control format 4 handling, trusted compiled collections and predecessor-writer fencing while keeping corpus envelope format 1. Verify populated predecessor stores require explicit transition, old writers refuse the upgraded generation and ordinary layout initialization leaves populated storage untouched. Document the format boundary.
- [x] 3.2 Implement the schema-10 quarantine transition and comparison report. Verify all existing canonical rows, revisions, exact selected material, document paths and UNKNOWN barriers survive except declared generation metadata, and verify interruption keeps the source generation usable. Document the synthetic rehearsal and later personal cutover checklist.
- [x] 3.3 Add binary-capable retained bundle material, pins and backup/restore coverage. Verify complete before/after manifests and bytes restore into a separate synthetic workspace and rebuild without the prior SQLite projection, including restricted material and open effects. Document the required backup components.

## 4. Bundle registration, publication and export compatibility

This group depends on groups 1 and 3. Its Core worker owns a bounded skill module and the storage worker owns bundle filesystem operations. The coordinator integrates public adapter operations.

- [x] 4.1 Implement full safe snapshot capture, content hashes, monotonically increasing registered revisions and declared file roles. Verify reference/script-only changes, additions/removals, BOM/CRLF, unstable reads, size bounds and unsafe-path refusal. Document bundle layout and validation errors.
- [x] 4.2 Implement inspect/preview/activation through exact native confirmation and durable registration receipts. Verify external edits remain pending drift, stale previews fail, scripts are retained without execution and repeat registration returns the original result. Document owner edits and activation.
- [x] 4.3 Implement journaled guarded bundle publication, rollback as a new revision and original-operation reconciliation. Verify interrupted multi-file publication, UNKNOWN replay refusal, restoration of old content with a new revision and rollback conflicts after later owner edits. Document supported recovery.
- [x] 4.4 Preserve the managed textual export/import tools and implement explicit adoption with one active writer per target. Run the focused existing export-drift case and new separate-path/same-path adoption cases, proving retained old Method/export bytes and refusal while an uncertain export effect remains. Update bootstrap's two authority contracts.

## 5. Method use and Activity guidance

Method use depends on group 4. Guidance depends on groups 1 and 2 and joins managed focus after group 3. The coordinator owns `src/core/contracts.ts`, invocation integration and consumer-scope coordination. The Pi worker owns extension loading and generated discovery. Product skill edits stay with that worker.

- [x] 5.1 Resolve current and pinned skill references at invocation and persist exact selected versions with the Method closure. Verify legacy inline Methods, two Methods sharing one bundle, missing versions, access refusal and a new activation preserving old invocation grounds. Document selection behavior.
- [x] 5.2 Supply invocation-specific complete version views with relative supporting paths. Verify changing working references/scripts after selection cannot substitute their bytes, and modified or missing selected material blocks managed use. Document native execution authority and opaque-command provenance limits.
- [x] 5.3 Implement explicit Activity-key/Core-reference guidance mapping and per-session Pi guidance replacement from the root. Verify synthetic Health, a second Activity, concurrent session focus, missing guidance, legacy document paths and preservation of other extension sections. Document selection and the ordinary-file workflow.
- [x] 5.4 Adapt the four system skills and generate scoped Codex/Pi discovery routes to canonical files. Verify the 30-line clean root bound, same-bundle routing, modified-wrapper conflicts, absence of duplicate Pi loading and runtime/guidance revision mismatch refusal. Document capabilities available with and without a Core adapter. Reopened after real native discovery exposed three owned sources; completed after actual archive/native discovery and guarded migration checks, replacing the ineffective prompt-time filter.
- [x] 5.5 Implement the trusted reverse-consumer view and shared resource gate for Method references, Activity bindings, delegation and discovery exposure. Verify hidden consumers remain opaque, unknown coverage requires review, multiple Methods classify as shared and competing binding mutations serialize through activation. Document what qualifies a local skill.

## 6. Delegated Sleep skill maintenance

This group depends on groups 4 and 5. Its worker owns `src/core/sleep-v2.ts` and `src/extension/sleep.ts`, with the coordinator integrating the shared bundle effect contract.

- [x] 6.1 Add the typed skill proposal, bounded selected-source reads and `applySkill` integration through the existing SDK surface. Verify the SDK tool allowlist stays bounded and existing phase, deadline, generation and improvement-budget tests pass. Update the Sleep skill with this lifecycle.
- [x] 6.2 Add exact owner delegation, text-path/byte limits, executable-role protection and shared-consumer classification. Verify one delegated local skill can apply a text change, while undelegated, shared, hidden-consumer, script and permission changes require the proper review or refusal. Document granting and withdrawing delegation.
- [x] 6.3 Bind validation and admission to complete before/after versions, Activity/delegation state, consumer digest and exact diff. Verify owner edits observed before admission, revoked delegation and consumer additions before and during publication cannot bypass renewed validation. Verify the scope gate remains held through activation and receipt.
- [x] 6.4 Integrate retained rollback, original-operation reconciliation and later benefit checks. Verify lost results, restart budget preservation, rollback revision identity, conflict with later owner edits and application success with usefulness still pending. Document those result distinctions.

## 7. Integration and acceptance evidence

The coordinator owns this group after the preceding groups. Focused tests above remain each group's responsibility.

- [x] 7.1 Produce a synthetic end-to-end installation and transition report covering repeat/update/conflict recovery, populated preservation, independent restore/rebuild and old-writer refusal. Verify source/document hashes and synthetic Web paths against the recorded before inventory, including a managed document edited externally.
- [x] 7.2 Deliver a reviewable Codex instruction-led walkthrough and subsequent trusted Pi walkthrough over the same synthetic Activity and skill, recording the ordinary result and exact discovery paths. Verify actual observation separately from harness results and leave owner usefulness acceptance explicit. Use the existing interactive session or a manual walkthrough without paid automated model qualification.
- [x] 7.3 Run `npm run openspec -- validate portable-workspace --strict`, formatting, types, lint, dependency boundaries and build, plus the focused suites exercised by this change. Review the final diff and record actual commands, outcomes, remaining limitations and pending acceptance before proposing integration.
- [x] 7.4 Repair packaged Pi startup when npm omits the root lockfile. Retain the exact dependency-lock build input as an inventory-verified packaged resource, preserve source-checkout loading without a build, and verify the actual installed tarball through the native Pi loader with model/network dispatch disabled. Recheck compiled provenance corruption refusal and record the packaging regression separately from the earlier source walkthrough.
- [x] 7.5 Repair the existing native compensation regression discovered during startup checks: verify the complete current Core compensation payload before filesystem dispatch, retain final exact consumption, and prove valid native compensation succeeds while stale or mismatched authorization cannot change files.
- [x] 7.6 Add a repeatable packaged-startup acceptance command which checks extension errors and native skill/prompt/theme diagnostics, effective canonical routes, personal/foreign skills, legacy package discovery and genuine owner collisions. Verify the qualified Pi 1.4.0 path and separately observe discovery on the installed Pi 1.5.0 without claiming full managed-runtime qualification. Review before updating the personal workspace.
- [x] 7.7 Remove the exact Pi version requirement from native attachment and resolve the installed package's declared CLI. Verify packaged startup, exact native approval and refusal, guarded rollback and a bounded Sleep review with the actual Pi 1.5.2 SDK in an isolated fixture. Retain Pi 1.4.0 regression checks and record observed coverage.

## Workflow follow-up

- The owner approved implementation on 2026-11-04 and the apply workflow completed its tracked tasks.
- After implementation and supported acceptance, sync verified capability deltas and archive the change through the project-local OpenSpec workflow.
- Schedule real ZT migration only through a separate explicitly authorized operation with its verified backup, private Health/Web comparison and cutover decision.
- Public release and any additional assistant's managed Core adapter need their own reviewed scope and qualification.

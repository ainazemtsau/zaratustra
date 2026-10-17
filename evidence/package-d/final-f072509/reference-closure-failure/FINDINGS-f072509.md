# Independent checkpoint: f072509 is NOT READY

This is a preserved negative checkpoint, not the final review. Product bytes were not changed by this reviewer. Source `f07250996d861404728c5892fa1f3b0a6a07bba4`; accepted C `7d211480d1dd5067bf52c3a654cc1a713368310d`.

## F-D-01 — Required G15 reference closure is incomplete

Priority: important / release blocker for the mandatory G15 criterion. Exact source: `packages/core/src/zaratustra_core/maintenance.py:24` (`integrity`), called by restore at line 111. The function checks outer record refs and Work inputs/Method only. It does not validate the retained Attempt reference graph or typed Sleep progress references.

Reproduction is independent and uses both installed wheels from the pinned owner archive, outside all Git checkouts. `installed_probe.py` installs the exact owner archive, makes a good backup through the real installed entrypoint, edits only copies of the disposable backup, recomputes the outer database size/SHA256, then calls installed `Core.restore_quarantined`. `reference_class_sweep.py` repeats the corrupted-copy restores and preserves exact database bytes, manifests and before/after diffs.

The good baseline restores. `PRAGMA integrity_check` is `ok`, `foreign_key_check` is empty, and the recomputed external hash matches in each corruption. A missing `records.body.source_refs` target is rejected with `backup.reference_closure`; missing Work input is rejected with `backup.work_closure`. But an Attempt `profile_ref` pointing to `{id:missing, revision:999}`, its copied Method's missing ID/revision, and an input manifest sequence changed to 999 all restore successfully. A new Core client observes the broken profile ref and exact read refuses it. This is successful publication of an incoherent restore, not a checksum failure, import error, or merely a scanner observation.

Class sweep `history_sleep_sweep.py` also establishes a good typed Sleep backup and accepts separately corrupted `sleep-progress/v1` `method_ref`, `analysis_result_refs`, and `selected_source_refs`. Their exact database/manifest bytes and diffs are under `closure-sweep-evidence`. These belong to the same missing structured-reference validation class.

Required related-case protection: historical pins must resolve to their original saved revisions even after current heads advance. The independent positive case advanced Method/profile/data to revision 2 while the Attempt kept revision 1. Backup/restore retained all original exact bytes and pins. A correction must not use current-head admission to reject legitimate historical copies or rebase their content.

Quarantine still refused a fully new valid mutation; old token and old epoch/new token were separately refused. No immediate execution escape is claimed. The defect violates C12/G15's promised complete restore reference closure and preservation, and prevents READY.

Evidence: `independent-installed-checks.json`, `reference-class-sweep.json`, `reference-corruption-evidence/*/mutant-diff.json`, `history-sleep-class-sweep.json`, `closure-sweep-evidence/*/mutant-diff.json`. Scripts and raw outputs are retained alongside them.

## Other completed reviewer checks

- Exact contents: 397 scoped source files; 18 production Python/TS/MJS files identical to wheel, sdist and two supplied installations; dependency wheels match uv.lock and installed dependency bytes. `byte-verification.json` has 545 successful assertions. No LF/CRLF normalization was used for this comparison.
- Own scoped run: 279 PASS, one harness failure because the reviewer did not precreate the evidence directory. The unchanged failed wheel test passed in a separate corrected run. This is a combined scoped result, not a single all-green run. The earlier sandbox-denied temporary-directory run is also preserved as a setup failure.
- Independent owner-archive offline install, actual executable diagnostics/artifact/backup/restore, exact artifact reread in a new process after physical interruption, old credential/epoch/quarantine barriers, preserved unknown observations/actions/reservations, no runnable restored intents.
- Seven native SDK cases with fictional credentials and controlled responses: baseline, concurrent no-op OAuth replacement, concurrent API-key refusal, refresh-error sanitization, unavailable selected auth path despite ambient key, failed upstream request, concurrent physical send cap. Earlier harness failures are separately retained; no real auth file was read by these cases and external network was blocked.
- Nine Windows sharing/fence checks, including actual transient reader release and permanent reader hold, preservation of existing destination, primary error preservation with failed cleanup, and grant/revoke/accept/artifact/input writer refusals in the real inventory-to-snapshot window. The first fence harness attempted client connection inside the fence; its error is separately retained and corrected by preconnecting idle clients.

## Live-model boundary

The independent rubric chosen for f072509 is preserved unchanged and has never been executed. Reviewer-side account preflight was rejected by auto-review before process creation. Main-chat root later executed the exact unchanged bounded script through normal approval with the owner's direct grant: one public Responses Luna send, HTTP 200, `OK`, 10 input + 5 output tokens, no refresh. Root was transport only. Exact original rejection, command, script hashes and result remain in this directory. G14 must use a newly selected rubric after the corrected source/build freeze, per the owner's steering. No live call is being retried by this reviewer.

Owner acceptance is pending and cannot be issued by this reviewer.

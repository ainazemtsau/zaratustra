# F10 compatible update closure — independent negative baseline

Failing exact source: `23719117016ea4bb975db6772396938906bba279`. Backup/recovery as a user workflow remains deferred. This defect concerns the existing mandatory automatic pre-update verification, not a new recovery gate.

`reproduce-update-closure-237.py` uses exact frozen237 wheels and public Core/NativeSession APIs to complete two fictional ordinary turns in the same conversation/Activity. Second-turn Attempts validly pin explicit optional prior history as empty (`context_coverage.mode=explicit`, selection prior_message_sequences=[]), while original_cursor=1 and one older message remains retained. Public `Core.prepare_update` fails `invalid_request/backup.reference_closure` at frozen `backup_refs.py:293`, which unconditionally compares saved prior_messages against ALL earlier messages. Original database bytes remain equal; no source/SQL mutation or real model call. Evidence: `update-closure-2371911-reproduction.json` and `.log`.

Recheck after the next exact freeze:

1. The same two-turn public-API fixture must pass compatible update preparation with all original state/Activity/message/result bytes and identities preserved. Test a real installed package update on retained native explicit-context history, not only a first-turn legacy fixture.
2. Explicit prior-message selection empty and nonempty must bind exactly to the selected same-conversation sequences <=original_cursor, retaining exact raw bytes/fingerprints. Pending input range/manifest remains complete and independently strict.
3. Corrupt selected raw bytes, omit a declared selected message, add an undeclared saved message, select a missing/foreign/future sequence, duplicate or mistype IDs/sequences: verification must refuse. Preserve strict JSON type distinctions rather than Python bool/int equality.
4. Without explicit coverage metadata, legacy full-prior-message closure remains required. Removing coverage to excuse an omitted prior message must fail.
5. Explicit catalog/prior-result/prior-wait bindings remain typed, scoped and version/cutoff-bound; if touched, verify both admitted selections and focused wrong-family/cross-conversation/dangling mismatch controls. Do not replace exact checks with unconditional acceptance of any subset.
6. Old source history, receipts, exact Work/Attempt pins and cached optional selection stay immutable. Do not repair the database, regenerate old outcomes, drop history or weaken reference verification to make the installed update succeed.
7. Re-run actual same-home new-runtime activation: failed237 update left the old selected runtime unchanged. New Core wheel bytes change runtime identity; do not claim merely an extension-only update. Preserve the still-ready unclaimed Sleep Work/cutoff775/old Method and allow its bounded recovery only once the new exact package is admitted.

Reuse: the237 bounded Sleep mechanical tests, stranded old-f2 -> new237 fixture, CAS/rights controls and exact unchanged app/component proof retain their original scope. If only the closure validator and its tests change, those Sleep mechanics can be reused after byte comparison; actual successful installed update and actual Sleep/post-Sleep proof must come from the final new package. Final native gate remains mandatory and cannot be supplied by old stopped/pending runs. Owner acceptance remains separate.

next: solmax

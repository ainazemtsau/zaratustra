# Independent bounded-delivery assessment after32db2ac

outcome: the observed failure is outside F11. F11's two correction cases and seven fatal-boundary cases independently pass. Actual new Sleep still fails after a lawful read because a row-count limit does not bound returned bytes. A bounded adapter-delivery plan is justified; no product edit is authorized by this assessment.

## Minimal counterexample

`reproduce-read-growth32.py` uses exact32 wheels, fresh fictional Core and public NativeSession/Core APIs only, with0 model calls and no source/SQL edits. Sixteen retained native read observations each contain50KiB, the familiar ordinary native read-output scale used in the earlier F9 counterexample. Sleep prepares successfully with8 whole sources and652,935-byte pinned context under the unchanged1MiB guard. Then:

| Legal operation | Core result bytes | Native result with duplicated details |
|---|---:|---:|
| read_history scope=subject, limit=100 | 1,262,302 | 2,537,341 |
| read_page observations, limit=100 | 1,210,063 | 2,421,490 |
| read_exact one retained50KiB data record | 52,986 | 107,708 |
| zara_context repeated current Sleep context | 653,318 | separate repeat of already pinned sources |

Both pages report all rows returned. The counterexample proves byte growth despite valid initial pinning and valid arguments; it does not emulate a model token limit. Results are in `read-growth32-reproduction.json`.

Actual independent trace/readonly-Core correlation in `actual-sleep32-inspection.json` confirms15 facts: same expected Python runtime identity; exact new extension; old Work publicly cancelled/fenced with progress/result history retained; one new Work at cutoff930; successful read_history returns82 exact whole sources,4,780,970wire bytes; identical material in text/details; two model sends and HTTP200 responses, with the second stream explicitly returning context-window error; new Work blocked/Attempt unknown; no analysis/Result/adaptation and unchanged fictional source/checker bytes. SDK context measurement grows902,721→10,497,809bytes. These SDK structure sizes are not exact provider token counts, and details duplication is not independently proven to be sent verbatim to the provider. Duplication is proven in native tool delivery/retained observations and contributes to later history growth.

## Scope to retain

- Keep Core APIs, complete source/history/receipt bytes, pinned references, grants, CAS, update verification and unknown-Attempt fences unchanged. This is adapter model-context delivery admission, not a production call/token/money cap or semantic source rewrite.
- One adapter delivery rule must cover the model-facing Sleep payloads that can carry retained bytes: history pages, table pages, exact reads, zara_context, and initial/command context. Inspect change/result acknowledgements and subsequent context injection for the same problem. A special case for this one read_history literal leaves read_page and repeated zara_context counterexamples open. Broad changes to ordinary-tool contracts require the explicit approved plan rather than implicit scope expansion.
- Keep one full material representation in admitted tool content. Details should carry bounded references/coverage/diagnostics rather than a second raw copy. This reduces amplification but alone does not make a4.8MB content block admissible.
- An individual response cap alone is insufficient: two or more individually admissible reads, repeated context and an existing large prompt may together exhaust the window. Account for the assembled request and continuation headroom, or explicitly stop before another send when capacity is not established. An approximate byte/token estimator must report its limits; do not assert exact model fit from chars/4. The provider's terminal error remains authoritative.

## Whole-source and paging requirements

- Return a deterministic ordered prefix of complete source units at the exact requested cutoff, with actual last-delivered cursor, has_more and explicit omitted/not-delivered coverage. Never retain the original end cursor or has_more=false after removing a tail. Preserve sequence/index tie ordering. Missing a first source cannot silently advance past it to later sources.
- For read_page preserve the original filter/columns/snapshot token binding and native cursor semantics. Do not fabricate a cursor from an unrelated page or silently read a newer snapshot. Pure read re-admission, if used, must retain identity and current rights checks; transport/persistence failures do not become automatic retries.
- If one complete source/row/exact object cannot fit, return explicit NOT_DELIVERED with its exact reference/hash and reason. Do not present an empty/truncated body as an examined source. Give no analysis/consumption credit, do not move progress past it and do not imply completion. An honest stop on such a source is a limitation to report, not proof that the whole Sleep criterion passed.
- Delivery and analysis remain different facts. Bounded context alone cannot declare Memory/Method adaptation, source analysis, Work completion or owner acceptance. Progress advances only through the existing exact analysis/checkpoint contract.

## Bounded recheck surface after an approved implementation/freeze

1. Aggregate ordinary-size sources: source bytes and source hashes unchanged; smaller whole prefix; exact cutoff/cursor/has_more; subsequent pages deliver omitted refs exactly once, including multiple indices at one event sequence. No later source crosses cutoff.
2. Single oversized first source: explicit NOT_DELIVERED, unchanged cursor/progress/analysis, no silent skip/truncation or automatic provider retry. Distinguish this from an empty completed page.
3. Alternate routes: oversized read_page observations, read_exact, repeated zara_context and duplicate details; assembled request after multiple successful reads remains subject to admission. The fixture above is reusable without model sends.
4. Rights revoked between reads, incompatible snapshot, foreign/private namespace, genuine transport/persistence failure and write/CAS errors retain their existing exact refusal. Preserve all9 independently passed F11 cases.
5. New exact package alignment, explicit handling of the preserved blocked/unknown actual Attempt through separately authorized public operations, then actual Sleep/adaptation and the still-unexecuted stdin task. No source/history reset, ledger reset, hidden model instructions or simulated adaptation evidence.

assumptions: a concrete delivery threshold/representation and recovery policy belong in the owner-approved plan. This review identifies counterexamples and invariants without imposing an arbitrary new numeric product limit.

cuts: read-only product review; scratch-only scripts/reports. No real calls, secrets, product edits, cancellation, retry or ordinary task by reviewer. Full native gate remains pending. Actual cumulative29/46, per-chain8; production unlimited.

manual-acceptance: PENDING.

next: solmax — approve a bounded adapter-delivery plan before implementation; preserve current unknown Attempt and prior evidence.

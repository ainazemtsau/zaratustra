# Independent technical review — 32db2ac

outcome: **F11 correction PASS in independently exercised scope; overall release/live criterion FAIL — F12/P1, byte-unbounded native read delivery exhausts the actual model context.** Exact source `32db2acf436c060dae71d91523f2f8665c25a6cd`; package `delivery/zaratustra-pi-0.2.0-32db2ac`; treeSHA256 `4a572fed7b81b04697ba0c90d57c26bd66cb0239f3e0af1fee7b2c1e887bd5ef`; ZIP SHA256 `43247d82e1577aa0dbd115d7f42b030ea83d81c9d9412acbd4fe2451c08384f2`. Owner acceptance PENDING; no READY claim. Previous reports/failures/stopped gates remain preserved.

## Exact alignment and retained evidence

`freeze-32db2ac.json`: all66 frozen source/package entries and full package tree match. `reuse-alignment-32db2ac.json`: exact ZIP/all9 members match. Source delta from158617f is extension plus its two test files; package byte delta is extension.ts only. Both wheels, bootstrap, README, package.json, release.json, requirements and wheel hashes are identical to158617f. The initial alignment script incorrectly expected release.json to change, then corrected that fixture expectation to the observed extension-only delta; this was not a product failure.

F10's72 focused tests/two independent corruption controls and actual supported update proof remain attributed to158617f's unchanged Core wheel. F9's10 focused tests and independent bounded-prefix/CAS/rights controls retain2371911 attribution. Earlier review/FIFO/cancel/reopen proof retains its original source scope. None is relabelled as a new32 full gate.

## F11 — nine independent actual SDK cases PASS

Exact packaged extension and frozen wheels run under actual installed Pi1.3 AgentSessionRuntime with fictional localhost responses; reviewer real model calls0. Evidence: `read-boundary-contract-32db2ac.json`, per-case `native-32db2ac-*-summary.json`, raw stdout/provider requests, `read-error-contract-32db2ac.json`.

Two correction cases PASS: the original unsupported read_history conversation argument, and a schema-valid future high_watermark rejected by Core. Each requests exactly5 scripted responses: route, bad read, a NEW corrected read, result metadata, actual final text. Both finish with exact completed delivery, idle current mapping, no abort, and durable original/corrected call and completion observations. The original158 case stopped after2 responses; comparison is retained. This is normal model correction, not automatic RPC/network replay.

Seven fatal-boundary cases PASS: actual public grant/connect/revoke yields denied/read; Python bridge process exits29; generic invalid_request/payload; invalid_request/wire; unclassified invalid_request field; a whitelisted history field attached to read_exact; the same field attached to change. Each stops after2 model responses, invokes its declared fault once, aborts, retains the unresolved Attempt and delivers no result. No error is relabelled recoverable. For denied, a real Core revocation is used. Protocol field cases use a declared Python fault seam; the packaged extension is copied unchanged and its hash independently checked in every case. These negative fixtures prove the boundary, not a naturally occurring protocol fault.

Builder's16-case run remains builder evidence, separate from these9 independent cases. The new schemas correspond to current Core argument shapes; the recoverable field set is operation-specific. No generic invalid_request catch or unknown-effect retry was introduced.

## Actual new Sleep and F12/P1

`actual-sleep32-inspection.json` independently confirms15 facts from the raw live trace (SHA256 `26c8bf973e720816e68474ee452d9540bdbf442b6719f096876039bfcf180bd1`) and read-only noncredential fictional Core records:

- Correct extension loaded; unchanged Python runtime identity `0afd3b6bdaa37c5d82c8e2281920892ac11e95f214e255c0b7c564a844c28c51` is expected because both wheels/bootstrap are unchanged.
- Public cancel leaves old69cc Work cancelled and its Attempt fenced; old progress/result fingerprints survive. Exactly one new Sleep Work `native-sleep-work:cdf1a605182c41e6af08ac90e616611f` starts at current cutoff930. This is not old Attempt replay.
- First provider response makes valid read_history(scope=fictional-label-utility, high_watermark=930, limit=100). It succeeds and returns82 exact whole sources,4,780,970wire bytes. Exact material hashes independently resolve against retained Core sources. Cursor `[930,2147483647]`, has_more=false is truthful for the Core query; it supplies no model-capacity guarantee.
- Identical history is present in native text and details; native result serializes to9,611,511bytes. SDK request-context measurement grows902,721→10,497,809bytes. Those are structure-byte measurements, not exact provider tokens, and this review does not assume details are sent verbatim to the provider.
- Two actual sends receive HTTP200, but the second stream explicitly ends `Your input exceeds the context window of this model`. HTTP200 is not completion. New Work remains blocked and Attempt unknown, with no analysis/Result/adaptation. Fictional label.py/check_label.py bytes are unchanged.

Location/mechanism: `zaratustra_app.native_session.NativeSession.tool` returns unrestricted read result after current public Core admission; `pi-package/extension.ts` tool execute returns JSON.stringify(result) plus the full result again in details. F9 bounded preparation does not admit later tool outputs. Lawful row count is insufficient to bound bytes. Unknown Attempt fencing is working and must remain.

Independent model-free minimal counterexample `reproduce-read-growth32.py` / `read-growth32-reproduction.json`: fresh exact wheels, public APIs only,16 ordinary native read observations each50KiB. Sleep prepares8 whole sources with652,935-byte context below unchanged1MiB guard. Then legal read_history(limit100) returns1,262,302bytes and read_page(observations,limit100) returns1,210,063bytes. Native duplicated representations exceed2.4MB. zara_context repeats653,318bytes of current pinned data; one exact50KiB record is also readable. This reproduces the byte-admission gap without model calls or inventing a provider token threshold.

`NATIVE-DELIVERY-RECHECK-BOUNDARY.md` records the minimal proposed scope and counterexamples for the owner's pending plan: adapter whole-source delivery admission across relevant Sleep outputs, exact cutoff/cursor/has_more, explicit single-source NOT_DELIVERED, bounded details and assembled-request accounting. It rejects source/history/receipt rewriting, silent truncation/skip, false analysis and production budget caps. A history-only literal patch or deleting details alone leaves counterexamples. Repeated individually bounded reads can still overflow their assembled context; that case needs explicit admission or an honest stop. Ordinary tool-contract expansion needs the approved plan, not an implicit scope change. No product change was made or authorized by reviewer.

## Current criteria

| Criterion | Verdict |
|---|---|
| Exact source/package/tree/ZIP and unchanged wheels | PASS |
| F11 original correction + known argument admission | PASS independent actual SDK |
| Denied/transport/generic field/other-operation/write fatal boundary | PASS7 independent controls |
| Public cancellation and preserved old evidence; one new current-cutoff Sleep | PASS independently inspected |
| Bounded later native delivery / successful actual Sleep | FAIL F12: actual context-window error; independent byte-growth counterexample |
| Actual analysis, Memory/Method adaptation, subsequent use | PENDING/unproved |
| Post-Sleep stdin task | PENDING/unexecuted; independently rebound after32 freeze |
| Exact full native gate | PENDING/NOT STARTED; no earlier stopped gate supplies PASS |
| Owner acceptance | PENDING |

evidence: named artifacts above. `live-task-32db2ac-prompt.txt` and hidden rubric preserve the same independent task; model receives prompt only. Prompt SHA256 `57da25640a185b87d1c4ab5eaaaf788df03fe2678eded2ce20a88dd048901929`. Task requires actual whole multiline stdin behavior, prior argument/import compatibility, unchanged checker execution and exact same-Activity Core result/context correlation. It has not run. No prescribed memory prose or simulated adaptation is credited.

assumptions: F12 repair needs a concrete approved plan and a new exact freeze. Byte/token heuristics cannot prove universal model fit. Actual stream error establishes this failure; source reading establishes control-path alignment only.

cuts: product read-only, writes confined to assigned scratch; no product fix, source/index/commit/push/publication, cancellation/retry or ordinary live task by reviewer. No personal auth/secrets; fictional operational records read-only. Excluded recovery/source-loss/platform/sync requirements stay excluded; production unlimited.

cost:9 fictional localhost actual-SDK cases, one model-free public-API size fixture, package alignment and retained-trace/Core inspections. Reviewer real model calls0. Actual chain cumulative29/46, per-chain8, halted; prior ledgers preserved. Focused controls are not summed into a full gate.

manual-acceptance: PENDING.

next: solmax — approve bounded adapter-delivery plan before implementation; retain blocked/unknown new Attempt. Refreeze and recheck exact whole-source/aggregate/single-source/alternate-output/fatal boundaries, then use separately authorized public continuation to prove actual Sleep/adaptation and the unexecuted task before the full native gate.

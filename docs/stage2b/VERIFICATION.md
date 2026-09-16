# Stage 2B verification — 2026-09-16

Candidate 0.20.0 on Stage2A fc696332. Scope approval is distinct from final owner
acceptance. Developer-run proof is not an independent binding G5 review.

## Completed technical checks

- 34 focused tests across skills/journal/commands passed; subsequently all 9 skill
  tests passed including the dependency-readiness replay regression.
- Ruff, strict mypy over 150 files and hygiene passed before the full native gate.
- Installed Pi 0.85.1 loader invoked the actual exported extension and isolated
  Python package through subprocesses. It confirmed independent active selections,
  A-to-B switch, persisted selection restoration, queued and sequential old-target
  refusal, failed-target retention, one owned active block, unchanged arbitrary
  user text and body-delivery entries. Source: tests/zaratustra/process_skills/pi-adapter.mjs.
- One bounded read-only review found the committed-retry issue; fixed and tested.
  This was an in-session smoke, not a separate binding G5 session.

## Real Pi scenario

Used installed Pi 0.85.1 in RPC mode, explicit openai-codex/gpt-5.6-sol, separate
Python runtime under site-packages and fictional Home. tools.probe_stage2b created
A/B, journal sources and shared v1 through public operations. The expected behavior
was not inserted into overview check prompts. Requests that created/changed a
method did explicitly describe the desired change.

| Session | User turns | Tool calls | Observed result |
| --- | ---: | ---: | --- |
| Main | 8 | 77 | v1, create v2 without apply, A-only apply, local B variant, A→B→A, grounds, rollback, disable, missing capability |
| Independent B | 2 | 15 | Kept Process B while main switched; adopted B's explicitly changed binding |
| Fresh A | 1 | 12 | Loaded shared v2 and used its distinct behavior without previous conversation |

All 104 tool calls completed without a reported tool error. v1 began with completed
work; v2 began with unfinished work and blockers and cited source revisions. B's
local variant produced a three-column table. Returning to A restored v2's behavior;
rollback restored v1's behavior. Missing imaginary.send-report remained unavailable:
the agent saved a draft, inspected the catalog and autonomously logged the gap under
the standing journal rule. No external send or developer execution was attempted.
Readable excerpts: [DEMO.md](DEMO.md).

Common installed API verification (invoked by Codex) checked:

- A configuration history: shared v1 → shared v2 → shared v1 → disabled.
- B configuration: shared v1 → complete local variant with exact shared-v1 origin.
- Both common skill revisions remain readable; v2 points to the original episode.
- B cannot open that local A episode: scope_unavailable.
- Missing-dependency draft is not selected or ready; the gap episode exists.
- 15 full-body delivery hashes equal the exact stored skill-version Markdown.
  Delivery entries: main 20, independent B 4, fresh A 3. Metadata-only deliveries
  are distinct from supplied full text. Main selections collapse to A→B→A;
  independent selection remains B.
- Previous fictional Stage1 and Stage2A Homes each retain two readable Processes
  and zero historical Works. Their existing installations and connections were
  not replaced.

This checks the common Codex API and generated connection, not a fresh Codex UI
conversation. Pi tests exercised installed hooks/RPC; no manual TUI acceptance is
claimed. Credentials and external-access readiness were not inspected or verified.

## Native delivery gate

The first full native gate passed formatting, Ruff, mypy and all 24 import contracts;
pytest reported 472 passes and one failure in the unchanged legacy test
test_relocation_preserves_concurrently_added_independent_row (an error result lacked
designation). A focused native python -m pytest invocation passed without code
changes. Two earlier diagnostic pytest-console invocations could not import tests
in Windows spawn children; they were invocation errors, not further product findings.
The second complete native gate passed: 473 tests in 276.76s, 177 formatted files,
Ruff, strict mypy over 150 files, all 24 import contracts, hygiene, report structure,
source distribution and wheel builds. No change was made to the old catalog test
or implementation to obtain the pass. The initial error cause is not established;
it remains a recorded intermittent observation, not silently discarded evidence.
All 59 Python/TypeScript files in the demonstration installation match this checkout.

## Retained local evidence

Raw traces remain local and ignored because they include host paths and provider
metadata. These hashes identify retained developer evidence; they are not public
independent proof. Paths are relative to the product checkout's .tmp directory.

| File | SHA-256 |
| --- | --- |
| final-stage2b-check.log | e32cdbeda1efaadce4cd6b7110d6e5b2e7e71dcbec3ebb2ec64db1795cb17d35 |
| stage2b-check-first-failed.log | 7d30f676431ad0daf71533a127351dc1217086dbfef06cef18f7e1b2ffb38b69 |
| stage2b-pi/summary.jsonl | 50d81971203b35418a65d75005f20a2eac6ba396c5e0e1c53c24a1156ec8d465 |
| stage2b-pi/stage2b-main.jsonl | e7556c15c92e0304ed95c3aacbd7d46c184e8aa7f4147c26544edf077b56bd4c |
| stage2b-pi/stage2b-independent.jsonl | 48aad2664f94515f288fd4e53a40c95890bc6096daa582e8353c54d975041762 |
| stage2b-pi/stage2b-fresh-a.jsonl | 350d43425ad2a1f77e47d0fb22d26a0ceb7259a30c890bcc564f18a3d78faa4c |
| stage2b-installed-verification.json | 7d26b5218963920feb93dc01be89e2af8e9df6ca16b42870a0e063b786546efe |

Session-owned selection and delivery entries also persist under the fictional
Home's .pi/stage2b-main, .pi/stage2b-independent and .pi/stage2b-fresh-a folders.
The failed first gate is retained as .tmp/stage2b-check-first-failed.log.

## Limits

The owner has not personally accepted this behavior. Context replacement does not
erase model history. Readiness is configuration evidence, not proof of external
success. Settings are non-secret preferences; there is no new credential manager.
Large-history performance and broad Russian semantic retrieval are not measured.
No automatic upgrade, executor, Stage3 development, public publication or live
export import occurred.

END_OF_FILE: docs/stage2b/VERIFICATION.md

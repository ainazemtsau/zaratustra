# Stage 2A verification — 2026-09-16

Candidate 0.19.0, based on Stage1 079bf616. Scope was approved; no final owner
acceptance is inferred from these developer-run checks.

## Predefined Russian retrieval cases

Fictional Home: «Разбор отчёта», «Другие заметки». Before invoking the fresh search
sessions, selected exact question (check02), paraphrase (why hold off changing how
the report is stored, including decision basis) and absent answer (cloud transfer).
Fixture contains two unrelated work episodes plus the report-check log.
No target record id or exact record title appears in these fresh user prompts.

## Observed installed Pi passes

Pi0.85.1 with openai-codex/gpt-5.6-sol; standalone wheel under site-packages,
separate fictional Home and fresh session directories without prior chat history.

- Work session: owner establishes a standing journal rule and asks to read a failed
  check and save an explicitly chosen decision. Agent saves the meaningful episode
  without another reminder, then proposes and adopts the exact decision.
  Two parallel writes meet a Core revision conflict: one refuses; Pi retries the
  same operation id and succeeds. No duplicate. This refusal is retained in evidence.
- Exact fresh question: query02 finds the episode, record.read opens its version1,
  source.read opens the pinned original material version2.
- Paraphrase: agent reformulates to «смена формат исходник», finds decision and
  episode, opens both and their original source, explains the reason for deferral.
- Absent answer: several cloud/server/storage queries find no corresponding
  decision. Agent also reads the one accepted decision and source. It reports no
  decision found in this Process; the product explicitly warns absence is not proof.
- Correction: owner-supplied clarification is saved as a separate immutable material;
  episode becomes revision2 with both source links. Agent reopens history and the
  still-accepted decision at unchanged revision2. No actual file check was invented.
- Explicit change: record.replace creates decision revision3 with the changed scope
  (one future source-file check, no transfer of other reports) and reason, pointing
  to episode revision2. Previous accepted decision remains readable at revision2.
- Explicit sharing: new Home document contains only the requested short conclusion
  «Перед диагностикой формата проверь доступность файла» and a reference to local
  episode revision2. No source log content was copied.
- Exports: local package contains seven entries (episode1–2, decision1–3, two exact
  source materials); no missing sources. Shared package contains one record and
  schema, and declares the local episode source as scope_unavailable.
- Fresh other-Process chat: finds and reads the shared conclusion. source.read of
  its local basis returns scope_unavailable. No Process switch or writes occur.

| Session | Tool attempts | Refused attempts |
| --- | ---: | ---: |
| Work and automatic episode | 9 | 1 |
| Exact fresh retrieval | 6 | 0 |
| Paraphrase and decision basis | 7 | 0 |
| Absent answer | 17 | 0 |
| Episode correction | 14 | 0 |
| Decision change, sharing and export | 18 | 1 |
| Other Process shared read | 5 | 0 |

The second refusal occurred when a local operation observed the shared workspace
between initialization and its identity bootstrap. It returned shared_identity_mismatch;
the agent reread/retried the same operation and succeeded. No content was disclosed
and no duplicate decision was created. Initial shared setup can briefly be unavailable
to concurrent readers. Neither this nor the earlier Core conflict is hidden as a success.

Installed common API (also invoked by Codex) independently verified revision numbers,
accepted states, historical content, exact links, unique operation ids, both package
inventories and zero historical Works. Standalone `inspect-export --limit 1` ran
from the program environment, where no .zara-context.json exists: seven entries,
one record on page1 and next_offset=1. No live import was attempted.

## Native checks and bounded review

Full delivery gate passed: 464 tests in 230.28s, 168 formatted files, Ruff clean,
strict mypy over 143 files, all 22 import boundaries, hygiene, report structure,
source distribution and wheel build. Core/Stage1 regression tests remain included.
No Core source or released migration changed.

One read-only in-session evaluator found missing standalone CLI page arguments and
unbounded export link inventory. Both were confirmed and fixed. Regression covers
22 records/672 links; re-review opened the second/last pages and confirmed a
limit=1 response of 2526 bytes. It is not a binding fresh Direction G5 review.

## Retained local evidence

Raw traces stay local because they include host paths and provider metadata. These
SHA-256 hashes identify retained evidence; they are not public independent proof.

| File | SHA-256 |
| --- | --- |
| final-stage2a-check.log | 754987f90cedecfe76336857e82f8d32f8937784f0b599332d776b48b658d1a4 |
| stage2a-pi-work.jsonl | 3390009428caa2bf4329ec33ef1c850de92b120dfde14053d3953d3b838c72d6 |
| stage2a-pi-exact.jsonl | c6f471bc07b546df354415781cd7cbbf2c991a72df653d2413baf1bd5a2b64d4 |
| stage2a-pi-paraphrase.jsonl | aafc3d4ff2ff2d46f4cf64412815dba73be16d028a54ee2339618eb591ffce6a |
| stage2a-pi-missing.jsonl | 80a0d1e0f6bf2ba8588dd2d65ac397baf8a2e2716d0941fd3a6747ba1da03014 |
| stage2a-pi-correction.jsonl | 0ddd6763ec393e2cf53fd9c815e2cf8cf0f10ef67f230997187a00afe6d26be1 |
| stage2a-pi-change-export.jsonl | 9661560ed7db416d966e68cd4447e188e3c32201cc621264c3f4302fdbf212e9 |
| stage2a-pi-shared-read.jsonl | de1d91a5f40ba1074b31c057294367e9b88cb08d5dd8a6cc4fb3a7fd72ae7695 |
| stage2a-installed-verification.json | 962f87a235cc43f4b3dd9f0d86f5ecf082e82679a0d91bc6b550bb2cac8c7ec3 |
| stage2a-standalone.json | 3bf8845de7e195270bffc5bbec5f66259eed241e6b7c331b5491ef25782390f1 |

## Scope of proof

These are developer-run fictional host conversations, not personal owner acceptance.
The search is lexical and agent-assisted, not a measured semantic search system.
Unknown/missing sources and failures remain visible. Codex uses the same command
implementation; fresh Codex skill-discovery UI is not claimed. Later stages are
excluded and no old Direction task is closed.

END_OF_FILE: docs/stage2a/VERIFICATION.md

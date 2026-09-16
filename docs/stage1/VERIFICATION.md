# Stage 1 verification — 2026-09-16

## Actual installed behavior

The wheel was installed with locked runtime dependencies into a dedicated Python
environment outside the source checkout. Module location was verified under that
environment's site-packages. A separate fictional Home was prepared with the
shipped setup command, and Pi auto-loaded the shipped project extension.

Pi0.85.1, model openai-codex/gpt-5.6-sol, separate fresh sessions:

1. Owner-style instruction explicitly authorized two fictional Processes with title
   and purpose, no tasks, Learning/Personal groups, three memberships, related_to
   and the exact supplied material. Twelve tool calls succeeded.
2. A fresh Home chat was given only “show Learning, open Study Notes and show its
   saved material; change nothing.” It returned both Processes and the exact text.
   A malformed group.membership call was explicitly refused before mutation; the
   model recovered by using process.list with group. This observed refusal is not
   hidden or counted as a successful call.
3. Another fresh Pi chat from the configured Process folder was given no Process
   name. It returned the current Process and same material in three successful reads.

Observed user-visible result (Russian fixture):

> В группе «Учёба»: «Практические пробы» и «Учебные заметки».
> В «Учебных заметках» материал «Первый источник»:
> «Проверочный материал: свежий чат читает сохранённые данные».

Installed API verification additionally checked two Processes with zero historical
Works, three memberships, one relation and exact material content; moved one
contained fictional folder, observed unavailability, then relocated the registration
and verified unchanged identity. Codex used the same installed command adapter and
read both Processes. No personal Process or source was read or created.

## Native checks

Final native delivery gate passed after the two review fixes:448 tests in174.06s,
159 formatted Python files, Ruff, strict mypy136 source files, 21 import contracts,
wheel/source build and report structure. Both old Core/entry regressions and new
Stage1 behavior are included. In-session review was read-only and its bounded
recheck found no material issues. No binding fresh Direction review is claimed.

## Retained local evidence hashes

Raw traces remain local because they contain host paths and provider metadata.
These SHA-256 digests identify the retained files, not public independent evidence.

| Local evidence name | SHA-256 |
| --- | --- |
| final-check.log | 212a0af541bd7906d0de4a819ad468127506ed091cfcf3139fe69b9cbbe0b6a9 |
| installed-create.jsonl | 2d64032fb5eb2a43723cd57b8f78cab6c36a14c7ec0ea2bd6f8cbcc5522008c7 |
| installed-fresh.jsonl | 4aa586b19f6de8cd4cc230ff888c7aafb2d50302b42d0e9152d4de95601ab6db |
| installed-direct.jsonl | 732460f802869620b2655f105f206c3eb2ae8081e2ef860f640a5ea0380b5301 |
| installed-verification.json | 62a9eb6d19f124f7d89af14882de238e0b605c96cb5e8fecf1364b6b733b1559 |

## Limits

Developer-run fictional scenarios demonstrate the actual host and installed code;
they are not personal owner acceptance. Pi was tested on the installed Windows
version above. New Codex skill discovery in a separately launched UI, other hosts,
large-scale data, semantic memory and later plan stages are not claimed. Public
publication is separate from this local delivery. Existing personal installations
and old Direction tasks are unchanged.

END_OF_FILE: docs/stage1/VERIFICATION.md

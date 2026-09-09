# T3 — единый read/context contract Process

## outcome

REPORT HOME на c-solmax-zaratustra-m1-capabilities-20260909-exec; pin36, PROBA.
Техническая реализация и авторские проверки T3 готовы. Owner acceptance T3 и
binding fresh physical G5 pending; завершение PROBA, Direction T3 и M1 не заявляется.

Product0.9.0/schema7 возвращает семь derived ответов из разрешённого Core snapshot.
Пустой поддержанный ответ, отказ и недоступность различаются. Exact ProcessQuery
раскрывает только явно выбранные Work metadata; counts относятся только к ответу.
Отдельный ContextQuery ограничивает содержимое selected Work и её точными Core grants.
Core сериализует чтение с managed writers и перепроверяет входы перед возвратом.
Общий Mutation API и прежняя семантика состояния не меняются.

## evidence

- Basis: a5efbb15c7c39e52072f4fb1593a294ebe109a80 — чистая принятая T2 review-версия.
- PLAN + retained baseline до implementation: 9eb43fa.
- Implementation/source: d0cb354807ab16b1d917d500a4e3d1d46f59ad3e.
- REPORT/evidence — последующий docs-only commit; точный SHA в финальном handback.
- Execution: C:/projects/zaratustra/_scratch/m1-capabilities-20260909,
  branch codex/m1-capabilities-20260909. Source/pin/stamp/свободные path/branch/STOP/STEER
  проверены на запуске. live/** и исходные Work/пакеты/G5 не редактировались.

| Исходный done_when | Evidence | Предел |
|---|---|---|
| 1. Семь возможностей через единый контракт | docs/m1-capabilities/PLAN.md, public read_capabilities, CapabilitySelection, exact ProcessQuery; contract.zip показывает ready7, attention/open decision/blocked8, important Result10 и контекст выбранной next Work. | Общий API и fictional contract fixture; два полных процесса и renderer остаются T4–T6. |
| 2. Empty/denied/unavailable, scope/revisions, metadata/counts, state и изоляция | 31 новый Core-backed test; full native204 PASS. Read tests проверяют bytes/layout; invalid scopes/rights/queries не вызывают adapter. Контекст равен прежнему open_work; foreign reference отвергается; hidden Result не раскрывается в metadata; exact inherited grounds допустимы; loss bytes не даёт partial output; managed writer ждёт завершения snapshot. | Не hostile same-user Python sandbox, power-loss доказательство или fresh G5. |
| 3. Exact version/checks, derived ответы и отсутствие M2 prerequisite | runtime.json: source d0cb354, source diff пустой. contract.zip/manifest сохраняют exact queries/callers/output/state/history/mutations/backups. В новой папке восстановлен before-result и записан настоящий Core Result7→8. source-verification связывает wheel с source и 37 неизменными файлами. | Нет нового persistence/projection writer, schema migration, зависимостей или M2 компонентов. |

Артефакты в docs/m1-capabilities/evidence/: baseline.whl, baseline-trial.zip и
baseline-files-manifest.json; native-02.txt (204 PASS, pytest62.98s), финальный
check-deliver.txt; contract.zip/contract-manifest.json, summary/runtime,
source.diff/source-verification, exact0.9.0 wheel, raw focused01/02 и остановленного
native01. manifest.json содержит SHA256/размеры. Повтор/rollback: REPRODUCE.md.

Released migrations1–7, context/records/results/artifacts, все старые tests,
local/CLI, T1 rules, validation.config и tools.check сохранены. В mutations.py
расширены только типы authorization query; новый read seam — Core/process_read.py,
external meaning — process_packs. Lock меняет только собственную версию продукта.
Сравнение source — byte evidence; поведение подтверждают реальные Core tests.

Development self-check: focused01 выявил потерю точного PackError code на границе
Core context manager. Invariant/class: read-error-envelope-preservation.
sweep: новые missing/incompatible/reader failure/invalid selection/budget paths —
closed общей обработкой внутри Core boundary; final revalidation сохранена.
Старый propose_result разрешает pack вне Core context manager — n/a. Focused02:
31 PASS, весь native204 PASS. Это не review artifact или fresh refutation.

Исполнительский сбой: native01 остановлен из-за пропущенного explicit scratch
basetemp; pytest успел начать в default temporary directory. Exact path не записан;
полная изоляция того прогона не заявляется. Ничего там не очищалось. Native02 и
Deliver задают явно новые execution _scratch папки. Raw сохранён; native01 не PASS.

## assumptions

- W16 HOW выбран до code и сверен по owner-ack:solmax-plan-conforming-20260907
  с Direction plan §§8/30/40, shape T3, C03/C04/C05. Новая реплика approval не выдумана.
- Explicit metadata scope — один Process/workspace. Anchor и каждый visible
  member требуют current metadata rights; terminal Work только metadata.
  Нет hidden counts; глобальная revision явно разрешена envelope.
- Status/attention/open questions/importance выводит adapter из текущих metadata;
  он не получает DB/path/caller/content. Вопрос fixture — metadata-маркер,
  не новое хранилище решений. Available — candidate по правилам pack/metadata,
  actual context и mutation отдельно проверяются Core.
- Context requirements не выдают прав. Exact references ограничены выбранной Work
  и inherited grants; содержимое требует отдельного caller на точный ContextQuery.
  Внешние текстовые ссылки не разыменовываются. Retained answer — historical.
- Byte budget ограничивает успешные данные; даже при max_bytes=1 возвращается
  небольшой фиксированный error envelope без metadata/counts.
- Registry — trusted Python, без code attestation/latest/migration; reader identity
  входит в collision. Повторно использованы fictional входы T2; новые операции
  текущего T3 runner имеют отдельные exact confirmations на RUN этого CALL.

## cuts

Новых cuts T3 нет. W15 exact T2 lifecycle сохранён; W16 реализован по PLAN.
W17: T3 — общая подготовка; обе гарантии P§30 «без изменения основной семантики
Core» и P§40 «без изменения Core» сохранены. Final placement и baseline перед
вторым OPEN T4/T5; один Process/workspace не объявляется окончательным M1.
W18 — полная fictional пара OPEN T4/T5; W19 — renderer OPEN T6; W20 — T3 evidence
сохранено, оба полных сценария/итоговая проверка OPEN T4–T7. Исходные rewrites
сохранены в CALL.md. M0 partial; Work8 не читался/не повторялся. T4/M2+ не запускались.

## cost

Одна авторская сессия, без подагентов. Baseline173 PASS; focused01 7 failed/24 passed,
focused02 31 PASS; native204 PASS и обязательный final Deliver. Исправлялись также
форматирование/типы; один native запуск остановлен. Полный wall-clock/token cost
не измерен; новых внешних/денежных действий не было.

## manual-acceptance

Показ: docs/m1-capabilities/READOUT.md; exact answers — contract.zip; команды того
же runner и восстановление — REPRODUCE.md. Actual owner words о T3: pending.
Слова «да» относятся к принятой T2; RUN текущего CALL разрешает исполнение,
не является приёмкой T3. Binding fresh physical G5: pending. Авторские проверки
не заменяют её. Этот REPORT не является Direction close.

## next

solmax

REPORT HOME на исходный CALL. Остаются отдельная свежая physical G5 и
реальная приёмка предъявленной T3. Direction сама ведёт продолжение.
Successor CALL/T4 не создавался; live/** не менялся.

END_OF_FILE: RESULT.md

CALL c-solmax-zaratustra-m0-mutation-20260908-work3
to: executor
kind: engineering
direction: solmax
node: g-zara-m0-continuity
task: t-zara-m0-mutation
repo: C:/projects/zaratustra
engineering_contract: 36
mode: PROBA
surface: cli
goal: |
  Управляемое изменение состояния Zaratustra оставляет один согласованный
  и прослеживаемый эффект, включая повтор, устаревшее основание и сбой.
context: |
  Work 3 — Mutation protocol, план §41; существующая T2 после закрытой T1.
  Setup, Work 1 и Work 2 приняты с binding close evidence всей T1:
  Direction root C:/my_global_workflow_worktrees/solmax;
  от него live/solmax/work/zaratustra-m0-work2-acceptance-2026-09-08.md,
  live/solmax/work/evidence/zaratustra-m0-work2-20260908/retained-trials.md,
  live/solmax/NOW.md, live/solmax/CHARTER.md,
  live/solmax/cards/t-zara-m0-mutation.md,
  live/solmax/cards/closed/t-zara-m0-foundation.md,
  live/solmax/cards/bet-g-zara-m0-continuity.md.
  Product basis/report fe064773dccb2d1f818f1004962043df2ef1edd9;
  implementation ce8ae68cf555f05864c9dd6b82cfbfd9babe61b1; version 0.2.0.
  Фактическая ветка при допуске codex/work2-core-records; remote нет.
  Перед зависимым изменением проверить actual repo state; не переинициализировать.
  Product-local: AGENTS.md, validation.config (36/PROBA), полный RESULT.md,
  docs/work2/RECORDS.md, docs/work2/INSTALL.md, docs/work2/evidence/,
  docs/work1/FOUNDATION.md, docs/setup/OWNER-DECISION-20260907.md.
  Принятый план live/solmax/work/zaratustra-architecture-plan-2026-09-05.md,
  §§3–7,26–29,41, SHA-256 4f90d19fc742ab616301b6b4121880f76c75faaeb1f606c8190a84853d8b3e0e.
  live/solmax/work/converge-g-zara-m0-continuity-verification-input-20260907.md;
  live/solmax/work/converge-g-zara-m0-continuity-arch.md — design evidence,
  не выбранная реализация; knowledge (в live/solmax/knowledge/):
  zaratustra-plan-conforming-approval-2026-09-07.md,
  zaratustra-local-no-automation-2026-09-07.md.
  Стек Python 3.13, uv, sqlite3, Pydantic v2, pytest, ruff, SHA-256.
  Work 2 реализует только initial quartet/revision=1, draft Work без authority,
  declared Artifact без bytes/active_version. Это не готовый mutation protocol.
  До зависимых решений PLAN отвечает на W19/W20/W21 и нужные W22/W24/W27.
  Технический HOW принадлежит продукту; варианты архитектурной бумаги не authority.
boundaries: |
  Только Work 3/T2. Один общий Core Mutation API и буквальный порядок §5:
  schema → Work/authority → expected_revision → duplicate → referenced artifacts
  → DB mutation + event → receipt → affected projections.
  Файловая публикация/projections Work 4, Handoff file/stdin Work 5,
  context Work 6, submit_result/next Work 7 и full demo Work 8 не реализуются этим
  допуском и не считаются доказанными. Неподдержанные зависимости не обходятся:
  PLAN явно ограничивает допустимые операции Work 3, сохраняя обязанности §5.
  Initial bootstrap не становится параллельным updater или будущим grant.
  Нельзя молча выбрать duplicate-first, переоткрывать terminal Work или считать
  approved/actor/exact_text/free CLI flag доверенным свидетельством владельца.
  Необходимое расхождение либо owner-owned выбор возвращается владельцу.
  Сохранить принятые 0.1.0/0.2.0 wheels/workspaces, перечисленные в retained-trials.md;
  работать на новых копиях. Schema changes только explicit migrations.
  Ручная правка DB/state Markdown для прохождения/восстановления запрещена.
  Только fictional data, без второго полного Process, реального Process,
  постоянного личного workspace, изменений Direction OS/старых repos/чтения archive.
  CI/CD, GitHub Actions, notifications, setup и test push исключены до отдельного
  слова владельца: оба owner-ack из указанного no-automation knowledge сохраняются.
  Не допущены product remote/account/publication, расходы, external/irreversible
  effects, M1+, MCP, independent external install/upgrade и полный переезд.
  PROBA v36; OPORA не выбрана. Делегация подтверждать соответствующее плану
  не доказывает owner runtime PASS. M0 остаётся active, показ после Work 8 обязателен.
done_when: |
  1. После Work 2 единственный Mutation API реализует принятый порядок §5 и
     актуальную проверку Work/authority; operation_id, expected_revision,
     изменение, event и receipt прослеживаются по сохранённым данным.
  2. Failure tests подтверждают один эффект повторной операции, conflict
     устаревшей revision и отказ без прав. Варианты ответа на replay определены
     PLAN по W19 без молчаливого изменения §5.
  3. При сбоях DB-части mutation/event/receipt остаются согласованными; журнал
     восстанавливает actor, основание и изменение. Точная проверенная установленная
     версия, артефакты и raw evidence сохранены; native build/hygiene/types/boundaries
     и hidden-state checks проходят. Файловая публикация проверяется следующей задачей.
return: |
  HOME solmax: полный Product RESULT по трём done_when — commits/diff, version,
  существующие artifacts, raw native и installed outputs, assumptions/cuts/cost/
  manual-acceptance/next: solmax, поимённые W19–W27 dispositions и ограничения.
  Actual checks отдельно от точных слов владельца. Product не закрывает Direction
  CALL/T2/M0 и не выдаёт следующий Direction CALL. Close route T2 — binding fresh
  physical G5; старые receipts лишь для совпавших claims/inputs. Light возможен
  только если фактически выполнено правило work, не по числу зелёных тестов.
  Неполнота, нужный выход за scope/нерешённая authority или неподтверждённый размер
  возвращаются конкретным полным blocker; acceptance и W19–W27 не снимаются.
budget: одно минимальное приращение Work 3 в существующей T2; калибровка до половины фокусного рабочего дня, без нового срока/расхода; PLAN проверяет размер до исполнения

## PLAN agenda — W19–W27

| ID | Принято в Work 2 / оставшийся ответчик и момент решения | rewrites: |
|---|---|---|
| W19 | Только initial revisions/create-once. PLAN до решений Work 3, затем 5/7: duplicate/stale/terminal/payload collision, current authority и disclosure старого receipt; единица Result/next Work effect. Буквальный §5 сохранён. | importer, receipts, linkage, failure tests/migrations; ≤1 дня не доказано. |
| W20 | DB migration и initial transaction измерены; active content отсутствует. PLAN до зависимых решений Work 3/4/7: DB commit/event/receipt, lost reply, publication, orphan/recovery/rebuild, late artifact availability. | durable references, recovery/evidence/migrations; дешёвый stub не доказан. |
| W21 | Draft Work без rights; локальный bootstrap не выдаёт grants. PLAN до general mutations Work 3, затем 5/6/7: реально trusted caller/receipt, binding Work/content/scope, current/revoked rights и receipt-read; payload сам не authority. | trust adapter, import paths и permission checks; ≤1 дня не доказано. |
| W22 | Whole initial graph snapshot и object/global initial revisions. PLAN до зависимых решений Work 3/4/6: revisions решений/прав/membership, scoped references, freshness, budget и delivered manifest. | snapshot/context contracts и проверки; freshness/scope/budget не cut. |
| W23 | Clean-chat proof не проводился. PLAN протокол до Work 6/8, exact delivered input и реальный отдельный ответ в Work 8 по пяти фактам. | протокол/повтор показа; прежняя оценка ≤1 дня при доступной поверхности; недоказуемая чистота — blocker. |
| W24 | Schema v2/typed values/UUID/time/initial revisions/CLI/transactions/BUSY измерены. PLAN в Work 3 для operation identity/fingerprint, новых форматов/revisions; последующие recovery/cleanup до зависимости. | локальные механики/tests; смена семантики возвращается W19–W22. |
| W25 | Fictional observatory и dangling foreign-id fixture; это link integrity, не context isolation. PLAN до Work 5/6/8: минимальный отрицательный чужой context без второго полного Process. | fixtures/checks/demo; прежняя оценка ≤1 дня. |
| W26 | Repo/path/no-remote, отдельная 0.2.0 install и сохранённая 0.1.0 проверены. PLAN подтверждает изменяемые факты; постоянная папка, hosting, external install/upgrade остаются future admissions. | package/layout/docs; пересмотреть после внешних зависимостей. |
| W27 | Только initial Core seams; PLAN перед публичным решением Work 3 и будущих потребителей сохраняет E1/E2/E3/E6/E8/E9/E10/E11. E4/E5/E7/E12 не получают выдуманный direct M0 API. Входящих M1+ prerequisites нет. | public Core/data и consumer migrations; дешёвая замена не доказана. |

## Exact M0 acceptance — контекст последующих Works



Это критерии ставки; текущий допуск ограничен тремя done_when Work 3 выше.

1. В выбранной пустой папке создаются workspace, один вымышленный Process и Work. Состояние сохраняется между запусками.
2. Владелец проходит цепочку: обсуждение в ChatGPT → принятый результат через Handoff → импорт в Codex → записанный результат с квитанцией → следующая Work. Импорт поддерживает file/stdin.
3. Отдельный чистый чат получает только актуальный пакет контекста и правильно называет решение, его основание, действовавшую revision, полученный результат и следующий шаг.
4. Проверки подтверждают: повтор Handoff даёт один эффект; устаревшая revision вызывает conflict; сбой сохраняет согласованность; операция без прав отклоняется; чужой контекст не попадает в Work.
5. Журнал позволяет восстановить, кто, на каком основании и что изменил. Производные представления пересоздаются из сохранённого состояния; сценарий проходит без ручной правки DB/state Markdown, предметных исключений в Core и доверия устаревшему контексту.
6. После Work 8 владельцу предъявлен работающий сценарий, выполнение остановлено перед M1.

END_OF_FILE: live/solmax/work/calls/c-solmax-zaratustra-m0-mutation-20260908-work3.md

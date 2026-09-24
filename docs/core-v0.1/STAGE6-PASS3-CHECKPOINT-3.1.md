# Core v0.1 Stage 6, проход 3 — контрольная точка 3.1: schema 7 и исходы Work

## Основание и граница

Владелец 2026-09-24 принял решения по `STAGE6-PASS3-PLAN.md` (раздел «Решения
владельца») и разрешил от `40fc5557eade00b1a83af1704bc026a6fcad5d84` реализовать только
часть 3.1: явный upgrade, предметные исходы `failed`, `cancelled`, `stale`, их операции и
чтения, повтор и права, обслуживание новых данных и предусмотренные проверки. После 3.1
работа остановлена для технического review. Это не отдельная приёмка schema 7 и не
приёмка прохода 3. Часть 3.2 не начата. Спецификация
`Zaratustra_Core_Specification_v0.1.md` сверена по SHA-256
`1DDCBF9DBFD58426781F61A67A170D3CE85FCD2BA27B17549773ED3356F9428D`.

Все данные синтетические. Реальной модели, миграции разработки и изменений Pi-адаптера
нет. Принятый путь прохода 2 сохранён: пространства schema 5–6 работают как прежде, а
новые варианты данных появляются только после явного upgrade.

**Контрольная точка, а не выпуск.** По решению владельца 2 schema 7 одна на весь
проход 3, а части — контрольные точки разработки. На точке 3.1 schema 7 не добавляет
таблиц: исходы хранятся в ревизиях Work, а версия отгораживает новые варианты от прежнего
кода. Запись миграции — `core-v0.1-plan-revision-7` с SHA-256 пустого набора DDL
`E3B0C44298FC1C149AFBF4C8996FB92427AE41E4649B934CA495991B7852B855`. Следующие части
дополнят DDL, и checksum изменится. Тестовые пространства, повышенные кодом 3.1,
одноразовые: код следующей части откажет им `unsupported_schema` («Schema history does
not match installed code»), и миграции для них не будет. После выпуска прохода 3 DDL и
checksum schema 7 неизменяемы.

## Контракт

### Upgrade

`upgrade_plan_revision_space(path, authority)` повышает только активную schema 6 до 7 с
правом `maintenance.backup` и записывает миграцию и событие обслуживания. На schema 7
вызов ничего не меняет, а schema 5 и ниже он отклоняет `unsupported_schema`. Чтение схему
не повышает. `SpaceInfo` и `BackupManifest` допускают schema 7.

### Запись исхода

`WorkState.status` принимает `proposed`, `succeeded`, `failed`, `cancelled` и `stale`.
У `succeeded` по-прежнему только `WorkAcceptance`. У трёх новых исходов есть ровно одна
запись `WorkClosure` в ревизии Work:

- исход и id операции;
- основание и источник полномочия (`source_ref` локального подтверждения);
- время;
- у `stale` — точные адреса изменившихся предпосылок (`premises` для Artifact,
  `decision_premises` для Decision).

Валидатор модели требует, чтобы запись была у закрытого Work и только у него и совпадала
с его исходом, а предпосылки назывались только у `stale`. Пустое поле `closure` не входит
в канонический JSON (`exclude_if`). Поэтому полезные нагрузки, fingerprint запросов и
checksum Method прохода 2 не меняются. Тест закрепляет пять значений, вычисленных кодом
принятого `d33b676`.

### Операция `close_work`

`CloseWorkRequest`: `work_id`, `expected_revision`, `outcome`, `basis`; у `stale` —
непустые уникальные `premises` и/или `decision_premises`, у других исходов они пусты.
Операция идёт общим путём `apply_operation`, с той же транзакцией, audit и квитанцией.

| Проверка | Поведение |
|---|---|
| Схема | Ниже 7 — `unsupported_schema` (и в диспетчере, и в общем составном gate). |
| Право | `work.accept` на этот Work. Для ребёнка добавляется `method.use` Method родителя, для составного родителя — `method.use` его Method, в области Activity. Decision и Grant проверяются заново в транзакции каждой операции. |
| Принадлежность | Ребёнок должен входить в текущий план родителя (`wrong_work`). При санированном плане решает запись принадлежности. Готовность не требуется: Work может завершиться неуспехом, быть отменён или устареть до запуска. |
| Составной родитель | Закрывается, только когда закрыт каждый его ребёнок. Иначе `open_children` со списком `роль:work_id` всех детей в `proposed`. Каскада нет. |
| Ревизия и исход | Неверная `expected_revision` — `stale_revision`. Уже закрытый или принятый Work — `work_closed`. |
| `stale` | Каждая названная предпосылка проверяется. Она должна входить в предпосылки этого Work, иначе `premise_mismatch`. Она должна быть неактуальной: Artifact пересмотрен или удалён, Decision пересмотрен или отозван. Иначе `premise_current` с адресом. На каждую нужен текущий `record.read`. |
| Удержание | То же, что при принятии, общей функцией `_hold_work_execution`. Интерактивная Attempt прерывается. Назначение переходит в `stop_requested`, открытые вопросы закрываются, pending outbox отменяется. Допущенные и отправленные вызовы становятся `unknown`, резерв и ресурс остаются удержаны. События — `close_work_interrupt_attempt` и `close_work_hold_assignment`. |
| Квитанция | `{record_id, revision, status}`. Цели — ревизия Work и адреса названных предпосылок. Текста основания в квитанции и audit нет. Точный повтор возвращает прежнюю квитанцию. |

Предпосылки Work — это входы его текущей ревизии. У составного ребёнка к ним добавляются
входы родителя, основание текущего плана и листы `artifact_current`/`decision_active` его
готовности. У составного родителя — основание его плана и такие же листы условия
завершения. После санирования плана его основание и листы проверить нельзя. Тогда
`stale` с такой предпосылкой отказывает `premise_mismatch`, а `failed`/`cancelled`
доступны. Core никогда не присваивает `stale` сам. До явной записи устаревший Work
читается как в проходе 2: простой — `blocked:stale_input`, составной ребёнок или родитель —
`blocked:stale_basis`.

### Закрытый Work

- Отказывают с `work_closed`:
  - связь выхода, принятие, повторное закрытие, выдача ребёнка;
  - назначение и запуск Attempt, создание ресурса;
  - новые эффекты Attempt. Для составного Work отказывает общий gate. Для простого Work
    отказывает проверка основания Attempt, а интерактивная Attempt уже прервана.
- Запрос и запись остановки, а также учёт уже отправленного вызова остаются доступны.
- Ревизии Work, запись исхода, Artifact, вопросы и история читаются, как прежде.

### Производное состояние

- Закрытый Work читается своим исходом. Пока действующая Attempt ждёт записи
  остановки, причина — `stop_requested`. Пока назначение `unknown`, причина —
  `outcome_unknown`. Обе причины несут адрес Attempt. После записанной остановки причин
  нет. `succeeded` не меняется.
- Лист `accepted_output` или `work_succeeded` над закрытым ребёнком даёт
  `dependency_closed` с ролью и адресом Work. Отказ операции называет ребёнка и исход.
- `all` с закрытым членом даёт `dependency_closed`: закрытый член важнее прочих отказов.
  `any` даёт `dependency_closed`, только если закрыт каждый член, иначе
  `dependency_open`. В производном состоянии `any` скрывает члены, закрытые навсегда,
  пока другой член ещё может выполниться. Если закрыты все, показываются все.
- Родитель, которому закрытый ребёнок нужен для условия завершения, обязательства или
  привязки выхода, — `blocked:dependency_closed(роль)`. Это блокирующая предпосылка по
  правилу прохода 2: она показывается раньше фаз детей.
- Ребёнок закрытого родителя — `blocked:work_closed`, как в проходе 2.

### Activity

Activity можно завершить, когда каждый её Work в `succeeded`, `failed`, `cancelled` или
`stale` (или удалён).

## Изменения принятого поведения

Коды и записи меняются только там, где закрытые исходы существуют, то есть после явного
upgrade до schema 7. В пространствах schema 5–6 они прежние.

1. Лист над закрытым ребёнком — `dependency_closed` вместо `dependency_open` (пункт 2
   раздела плана «Изменения принятого поведения»).
2. Завершение Activity считает закрытые исходы (пункт 6 того же раздела).
3. Проверка `all` вычисляет все члены и отдаёт предпочтение `dependency_closed`. Без
   закрытых членов первым отказом остаётся тот же, что прежде.
4. Тексты отказов `work_closed` называют фактический исход вместо «accepted». Коды не
   изменились.
5. Удержание при принятии вынесено в общую функцию. Его SQL-операции и виды событий при
   принятии прежние.

## Обслуживание данных

- Запись исхода — часть ревизии субъекта Work (`subject_content`). Она читается точно по
  ревизии, входит в SQLite-снимок Core при backup (manifest schema 7) и сохраняется
  карантинным restore. Recover прерывает удержанное назначение, но не открывает Work
  заново и ничего не возобновляет: новое назначение в новой эпохе — `work_closed`.
- Удаление Work санирует основание исхода вместе с содержимым Work и выводит его
  квитанции из повтора, как основание принятия. Маркер основания отсутствует в live
  SQLite и новом backup; старый пакет удалён.
- После удаления предпосылки `stale` её адрес читается в `unavailable_refs` тем же
  механизмом, что входы, без скопированного содержимого.
- Новых таблиц и технических копий нет. Удержание меняет только статусы; DBOS и Pi текста
  исхода не получают.

## Воспроизведение

`tests/zaratustra/foundation/test_work_outcomes.py`, 11 тестов без модели:

- `test_schema_7_upgrade_is_explicit_and_keeps_pass2_replay` — пять канонических
  констант прохода 2; upgrade из schema 5 отклонён; `close_work` на schema 6 —
  `unsupported_schema`, чтение схему не меняет; upgrade идемпотентен; повтор создания
  составного Work возвращает прежнюю квитанцию; checksum Method проверяется.
- `test_failed_plain_work_is_terminal_with_exact_history_and_rights` — без
  `work.accept` — `permission_denied`, ничего не записано; `failed` прерывает
  интерактивную Attempt; повтор — прежняя квитанция, основания в квитанции нет; неверная
  ревизия — `stale_revision`; связь, принятие, повторное закрытие и новая Attempt —
  `work_closed`; точные ревизии `proposed` и `failed` с записью исхода.
- `test_cancel_assigned_child_holds_execution_until_stop_is_recorded` — ребёнок с
  открытым вопросом; без `method.use` — отказ; `cancelled` → назначение `stop_requested`,
  вопрос закрыт, outbox отменён, `cancelled:stop_requested`; новый эффект —
  `work_closed`; после записанной остановки `cancelled` без причин; новое назначение —
  `work_closed`; вопрос читается.
- `test_cancelled_child_with_sent_call_keeps_unknown_reserve_and_resource` — отправленный
  вызов становится `unknown`; удержано 5 единиц резерва; `cancelled:outcome_unknown`;
  назначение другого Work на тот же исключительный корень — `resource_busy`.
- `test_stale_plain_work_names_only_changed_own_premises` — `premise_current`, затем
  `premise_mismatch` для чужого Artifact; до записи — `blocked:stale_input`; после
  ревизии входа — `stale` с адресом старой ревизии.
- `test_stale_child_names_a_revised_decision_leaf` — до пересмотра `premise_current`; после
  отзыва Decision ребёнок `blocked` с `stale_basis` на Decision@1 и остаётся `proposed`;
  затем `stale` по листу `decision_active`.
- `test_stale_parent_needs_closed_children_and_its_own_premise` — родитель
  `blocked:stale_basis`; `stale` родителя при открытых детях — `open_children` с обоими;
  после закрытия детей чужая предпосылка — `premise_mismatch`, собственная — `stale`.
- `test_sanitized_plan_keeps_membership_but_not_unverifiable_premises` — после
  санирования текущего плана `stale` по его основанию — `premise_mismatch`; `cancelled`,
  `failed` детей и родителя проходят по записи принадлежности.
- `test_closed_child_blocks_dependents_and_parent_waits_for_open_children` — после
  `failed` у A выдача B — `dependency_closed` с адресом A; B и родитель —
  `blocked:dependency_closed(a)`; закрытие родителя — `open_children` только с B;
  завершение Activity — `dependent_work`, после закрытия B и родителя — проходит.
- `test_any_condition_closes_only_when_every_member_is_closed` — `any(a, c)`: после
  `failed` у A — `dependency_open`, причина только `c`; после `cancelled` у C —
  `dependency_closed` с обоими членами; выдача закрытого C — `work_closed`.
- `test_outcomes_survive_restore_and_are_deleted_with_their_work` — backup/restore/Recover
  сохраняют исходы и не возобновляют отменённого ребёнка; новый процесс читает те же
  исходы; удаление предпосылки даёт `unavailable_refs`; удаление Work санирует маркер в
  live SQLite и новом backup, старый пакет удалён.

Код и тесты — коммит `aa26b31`; уточнения плана и исправление атрибуции — `d08ea38`.
Проверки ниже запускались на чистом дереве `d08ea38`. Коммит с этим документом меняет
только Markdown-файлы. Среди них `src/zaratustra/foundation/AGENTS.md`, который входит в
wheel, поэтому SHA-256 wheel этого коммита отличается от проверенного; Python-код и тесты
совпадают.

## Проверки в Linux-контейнере

Сессия работала в облачном Linux-контейнере, а не на Windows. Эти прогоны — обратная
связь, а не доказательство выпуска. Обязательный полный gate — независимый
Windows-прогон, результат которого передаёт владелец.

- `pytest tests -q` на `d08ea38`, conda-forge Python 3.13.7 с SQLite 3.53.3 и FTS5:
  561 прошёл, 1 упал. Это 551 тест `d33b676` и 11 новых. Единственное падение —
  ожидаемое на Linux `test_import_refuses_unfixed_sqlite_runtime_in_a_fresh_process`,
  как на `d33b676`.
- `uv run --locked mypy --platform win32 src tools tests` — ошибок нет (171 файл).
- `uv run --locked lint-imports --no-cache` — 21 контракт сохранён, 0 нарушено.
- `uv run --locked python -m tools.check --deliver` — hygiene, структура отчёта, Ruff
  format (197 файлов) и Ruff lint прошли. Затем остановка на mypy: 35 ошибок в 11
  файлах, все про атрибуты, существующие только на Windows. 3.1 эти файлы не меняла.
- `tools.probe_stage6_rpc` (checkout), `tools.probe_install_stage6` (wheel SHA-256
  `4BD3BDFCB28DD513632021C46D25C12F759EC80B68D733F6B193801A4E010FE3` в новом venv вне
  checkout, `source_tree_dirty: false`) и `tools.probe_stage5_rpc` на обычном Pi 0.87.0
  RPC с синтетическим localhost-провайдером — `passed`. Stage 6 — по 3 HTTP. Stage 5 —
  2 вызова провайдера, отказ до отправки без HTTP, restore в эпоху 2 и санация при
  удалении. Эти probe идут путём schema 5–6 и подтверждают, что
  принятый путь сохранён. Поведение 3.1 в Pi они не проверяют: его видимость относится
  к 3.10. Отчёты — `_scratch/stage6-pass3-31-rpc`, `_scratch/stage6-pass3-31-installed`,
  `_scratch/stage6-pass3-31-stage5` (игнорируются git).

Команды для Windows-проверки — те же, что в `STAGE6-PASS2-IMPLEMENTATION.md`, с новыми
каталогами вывода:

```powershell
$env:UV_CACHE_DIR = Join-Path (Get-Location) '_scratch\stage5-plan-uv-cache'
$env:ZARATUSTRA_SQLITE_DLL = Join-Path (Get-Location) '_scratch\stage4-interactive-20260923-a\sqlite\sqlite3.dll'
$env:PYTHONPATH = Join-Path (Get-Location) 'tools\sqlite_bootstrap'
uv run --locked python -m tools.check --deliver
uv run --locked python -m tools.probe_stage6_rpc --output _scratch\stage6-pass3-31-rpc --pi-runtime '_scratch\stage4-pi-runtime'
uv run --locked python -m tools.probe_install_stage6 --output _scratch\stage6-pass3-31-installed --pi-runtime '_scratch\stage4-pi-runtime' --sqlite-dll $env:ZARATUSTRA_SQLITE_DLL
```

## Пределы

- Pi-адаптер не менялся. `/zara-status` печатает новый исход как строку состояния. Pi не
  предлагает закрыть Work: bridge не пропускает `close_work`. Отдельное представление
  исходов в Pi относится к 3.10.
- Не начаты части 3.2–3.10, отдельный срез исполнения родителя и обязательства в том же
  Work, проход 4 с матрицей сбоев.
- Предпосылки санированного плана не проверяются по его индексу адресов: в индексе
  сохранены только id Artifact без ревизий.

## Ограничения Linux-проверок

Gates не ослаблены: `tools/check.py`, `validation.config`, `REVIEW.md` и прежние тесты не
менялись.

- `tools.check --deliver` на Linux останавливается на mypy по платформенной причине
  (см. выше). Остальные шаги выполнены отдельно, `mypy --platform win32` чист.
- `test_import_refuses_unfixed_sqlite_runtime_in_a_fresh_process` на Linux падает: тест
  ожидает неподдерживаемый встроенный SQLite, а conda-forge Python уже содержит точный
  3.53.3.
- Хук `.githooks/pre-commit` вызывает `#!/usr/bin/env python`. В контейнере это системный
  Python 3.11, поэтому коммиты делались с Python 3.13.7 первым в `PATH`.
- Pi 0.87.0 (`@earendil-works/pi-coding-agent` и верхнеуровневый
  `@earendil-works/pi-ai`) установлен из npm в игнорируемый
  `_scratch/stage6-pass3-pi-runtime`. Это окружение, а не продукт.

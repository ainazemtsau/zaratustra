# Core v0.1 Stage 6, проход 2 — составной Work на Stage 5 Attempt

## Основание и граница

Владелец 2026-09-24 принял первый проход Stage 6 на
`29d887d41f1639dc6ddb354a2039603cb1a30d94` (`STAGE6-PASS1-ACCEPTANCE.md`) и
разрешил реализацию только второго прохода `STAGE6-PLAN.md` от этого коммита.
Спецификация `Zaratustra_Core_Specification_v0.1.md` сверена по SHA-256
`1DDCBF9DBFD58426781F61A67A170D3CE85FCD2BA27B17549773ED3356F9428D`. Рабочий план —
`STAGE6-PASS2-WORKING-PLAN.md`. Все данные синтетические, модельные ответы даёт
localhost fixture; настоящей модели, миграции разработки и проходов 3–4 нет.
Новый dispatcher не создан: выдачу и ожидание по-прежнему несут Core outbox,
DBOS queue/`send`/`recv` и обычный Pi RPC из Stage 5.

## Сохраняемый контракт

`upgrade_child_execution_space` явно повышает только активную schema 5 до
schema 6; чтение старой схемы её не меняет. Schema 6 добавляет одну таблицу
`execution_plan_pins`: для назначенной дочерней Attempt — родитель, роль,
ревизия плана и точные id/версия/checksum Method, operation id и время. Это
адреса и закреплённые версии, а не копия плана. Содержимое плана остаётся только
в его ревизии `work_plan_revisions`; Outbox и вход DBOS workflow по-прежнему несут
лишь Work/Attempt/epoch/generation.

Общий gate `apply_operation` для дочернего Work в schema 6:

| Операция | Поведение |
|---|---|
| `AssignAttemptRequest` | Заново проверяет выдачу ребёнка в текущей ревизии плана, что родитель ещё не принят (`proposed`), материализацию обязательств, текущие основания/входы, условие готовности с точными входами и `method.use` в области Activity. В той же транзакции создаёт Attempt, назначение, `launch` outbox и закрепление плана; квитанция содержит `plan`. Ребёнок без выдачи получает `child_not_issued` без Attempt/outbox. |
| Launch claim, вопрос, ответ, prepare/admit/send, публикация | Те же проверки плюс совпадение закрепления Attempt с текущими родителем, ролью, ревизией плана и Method (`stale_plan`). Поэтому старое поколение не применяет эффект или результат к другому плану, а предметный отказ до `send` не создаёт HTTP. |
| Запрос/запись остановки и исхода вызова | Доступны без проверки плана: остановка и учёт уже отправленного вызова не должны ждать актуального плана. `unknown` и удержание резерва/ресурса остаются правилами Stage 5. |
| Ресурс ребёнка | Создание и ревизия разрешены; это настройка, не эффект. |
| Интерактивная Stage 4 Attempt, исполнение родителя | По-прежнему `unsupported_composite_execution`. Schema 5 без явного upgrade также отказывает дочернему исполнению. |
| `LinkWorkOutputRequest`, `AcceptWorkRequest` | Прежний прямой путь первого прохода; принятие результата остаётся отдельной операцией. Правила принятия родителя собраны в `check_parent_acceptance` без изменения порядка проверок и прав; тот же код без actor задаёт производное `acceptance_pending`. |

Путь `method="none"` и прежние ревизии не меняются: ни закрепления, ни поля
`plan` в его квитанциях нет.

## Производные состояния Work

`read_work_status` и новые поля `ExecutionSnapshot.status` /
`ExecutionSnapshot.composition` вычисляют состояние в той же читающей транзакции из
записей, которые допускают или отклоняют действия. Отдельного редактируемого
поля статуса нет; `WorkState.status` по-прежнему хранит только предметный исход
`proposed/succeeded`.

| Состояние | Когда |
|---|---|
| `succeeded` | Работа отдельно принята. |
| `blocked` | Назначение `unknown` (исход внешнего вызова не установлен, ресурс удержан); не выполнено условие готовности, текущий вход/основание, выдача в текущем плане или закрепление Attempt; план или вход недоступны после удаления. У родителя — устаревшие основание, вход, связанный выход, лист условия завершения (Artifact или Decision) либо результат ребёнка для привязки или обязательства. Причины адресные: Artifact/Decision с ревизией или Work роли (`dependency_open`, `stale_basis`, `stale_plan`, `content_unavailable`, `outcome_unknown`, …). |
| `waiting` | У действующей Attempt открыт адресный вопрос; указан `wait_id`. |
| `running` | Launch claim зафиксирован, либо после ответа той же Attempt записан новый эффект; интерактивная Stage 4 Attempt активна; остановка запрошена, но её исход ещё не записан (`stop_requested`: попытка идёт, ресурс удержан, новые эффекты отклоняются). |
| `ready` | Можно запускать: выдан и готов, назначен до claim (`launch_pending`), либо ответ сделал продолжение готовым (`continuation_ready`). У родителя — доступен следующий шаг, в том числе `output_link_pending` с адресом точного принятого результата ребёнка для слота, или `acceptance_pending`, только если структурные правила принятия Core выполнены. |
| `proposed` | Ребёнок ещё не выдан, но его условие выполнено (`issue_pending`), либо результат опубликован и ждёт отдельного принятия (`result_proposed`). |

Состояние родителя выводится по тем же правилам Core, что и его операции:

1. Устаревшая предпосылка даёт `blocked` с адресом раньше состояний детей. Такими
   предпосылками считаются основание, входы, связанные выходы, листы условия
   завершения, а также результаты детей для привязок выхода и обязательств.
   Их Core отклоняет при принятии (`stale_basis`, `content_unavailable`, …).
   Ещё не выполненный лист (`dependency_open`) предпосылку не блокирует.
   Условие `any` блокирует, только если ни один его член уже не может выполниться.
2. `waiting`/`running`, если такова хотя бы одна ветвь.
3. `ready:acceptance_pending`, только если проходит `check_parent_acceptance`:
   те же правила, что и в `AcceptWorkRequest`, но без actor. Права `work.accept`
   и `method.use` по-прежнему проверяет сама операция принятия, а принятие
   остаётся отдельной операцией.
4. Иначе `ready`, если доступен следующий шаг: выдача, запуск, принятие
   ребёнка, подтверждение обязательства или связь выхода (`output_link_pending`).
5. Иначе `blocked`.

Невыданный ребёнок получает адресные причины из тех же проверок, что и
`IssueChildWorkRequest`: текущие основание, входы родителя и собственные входы
ребёнка. `CompositionView` содержит только адреса, закрепления, состояния детей
и обязательств. `failed/cancelled/stale` не вводятся: они относятся к проходу 3.

## Pi-адаптер

- Назначенный Pi RPC работает в schema 4–6; интерактивный bridge — в schema 3–6.
- Перед launch claim runner не делает отдельной оценки: claim является Core gate.
  Если он отказывает дочернему Work по предметной причине, runner записывает
  наблюдаемую остановку (процесса Pi не было), освобождая ресурс; технические
  отказы (`busy`, `storage`, `deletion_pending`, …) назначение не закрывают.
- Перед каждым prompt runner заново читает Core; для ребёнка
  `read_assigned_control` проверяет закрепление, выдачу, зависимости и
  `method.use`. Тот же контроль раз в 0,5 с использует монитор остановки Stage 5.
- Контекст Pi получает `status` и `composition` (адреса и версии, без текста
  плана). Интерактивный `/zara-status` показывает строку состояния, план с
  ревизией и ролью, состояния детей и обязательств, затем полный снимок Core.
  `/zara-work` не запускает интерактивную Attempt для составного Work, а `select`
  не создаёт для него ресурс.

## Обслуживание новых данных

- Закрепления входят в тот же снимок Core при backup (manifest schema 6),
  сохраняются в карантинном restore как история и не возобновляют старые
  назначения: Recover прерывает Attempt, закрывает вопросы и отменяет outbox.
- Удаление дочернего Work удаляет его закрепления вместе с Attempt/назначениями;
  обязательства родителя остаются. Удаление входного Artifact прерывает
  затронутую Attempt, очищает текст вопроса и оставляет адрес закрепления до
  удаления самого ребёнка. Родителя можно удалить только после детей;
  разделяемый Method не удаляется молча.
- DBOS workflows и Pi RPC homes дочерних Attempt очищаются тем же адресным
  механизмом Stage 5; инертные восстановленные архивы удаляются при
  обслуживании восстановленного пространства. Проверено, что эти технические копии
  не содержали текста плана, вопроса, ответа или результата.

## Воспроизведение

Модельно-независимые регрессии: `tests/zaratustra/foundation/test_child_execution.py`
(явный upgrade и прежние пути; закрепление, переходы состояний, разблокировка B;
устаревшее закрепление и потерянная зависимость без новых эффектов, но с
остановкой; restore/удаление; состояние родителя; последовательная санация с
перезапуском процесса) и `tests/zaratustra/pi_adapter/test_child_assigned.py`
(интерактивный и назначенный bridge, дубль доставки — один DBOS workflow,
адресная очистка, предметный отказ до запуска без процесса Pi и HTTP). Проверка
устаревшего закрепления использует явную fault injection в SQLite, поскольку в
этом проходе публичной ревизии плана после выдачи нет.

Две регрессии проверяют родителя после принятия A и B, подтверждения
обязательств и связи выхода:

- `test_parent_blocks_when_its_input_revision_changes`: повышена ревизия
  входного Artifact.
- `test_parent_blocks_when_its_completion_decision_is_revoked`: отозван Decision
  из условия завершения.

В обоих случаях `read_work_status` и `read_execution(...).status` дают `blocked`
с единственной причиной `stale_basis`, адресованной этому Artifact/Decision
ревизии 1. `AcceptWorkRequest` отклоняется `stale_basis`, и Work остаётся
`proposed`. До связи выхода родитель показывает `output_link_pending`, а
преждевременное принятие отклоняется `output_mismatch`.
`test_unissued_child_and_parent_show_the_issue_refusal_address` меняет вход до
выдачи: невыданный ребёнок и родитель — `blocked` с `stale_basis` на этом
Artifact, и выдача отклоняется тем же кодом.

Живой сценарий `tools.probe_stage6_rpc` использует обычный Pi 0.87.0 RPC, DBOS
3.0.0 и localhost SSE provider. `tools.probe_install_stage6` собирает wheel,
ставит его в новый venv вне checkout и запускает тот же файл изолированно.

Каждый изолированный дочерний Python (reopen, перезапуск между удалениями и
внешний процесс установленного wheel) запускается как `python -I -X utf8`.
`-I` игнорирует `PYTHONIOENCODING`, а на Windows вывод в pipe иначе кодируется
ANSI code page, и JSON с кириллицей падает с `UnicodeEncodeError`. Родитель
декодирует stdout как UTF-8. `tests/tools/test_probe_stage6_rpc.py` проверяет,
что с флагами обоих probe изолированный дочерний процесс возвращает точный
не-ASCII JSON.

```powershell
$env:UV_CACHE_DIR = Join-Path (Get-Location) '_scratch\stage5-plan-uv-cache'
$env:ZARATUSTRA_SQLITE_DLL = Join-Path (Get-Location) '_scratch\stage4-interactive-20260923-a\sqlite\sqlite3.dll'
$env:PYTHONPATH = Join-Path (Get-Location) 'tools\sqlite_bootstrap'
uv run --locked python -m tools.probe_stage6_rpc --output _scratch\stage6-pass2-rpc-new --pi-runtime '_scratch\stage4-pi-runtime'
uv run --locked python -m tools.probe_install_stage6 --output _scratch\stage6-pass2-installed-new --pi-runtime '_scratch\stage4-pi-runtime' --sqlite-dll $env:ZARATUSTRA_SQLITE_DLL
```

Расширение импортирует `@earendil-works/pi-ai/providers/openai-codex`, поэтому в
каталоге Pi runtime должен быть разрешим пакет `@earendil-works/pi-ai@0.87.0`.
Опубликованный Pi 0.87.0 содержит `npm-shrinkwrap.json` и вкладывает свои
зависимости; в этой проверке тот же `pi-ai@0.87.0` установлен верхним уровнем в
игнорируемый runtime.

## Наблюдения

Проверка выполнена в облачном Linux-контейнере, а не в рабочем дереве владельца
на Windows. Точный Python 3.13.7 с SQLite 3.53.3 и FTS5 взят из conda-forge
(`python-3.13.7-h2b335a9_100_cp313`, `libsqlite-3.53.3-h0c1763c_0`); на Linux
Core допускает runtime по версии и FTS5, без Windows DLL.

Отчёты по итоговому исходному коду после исправлений ревью:
- `_scratch/stage6-pass2-rpc-d/report.json` — checkout.
- `_scratch/stage6-pass2-installed-d/report.json` — wheel SHA-256
  `9FE6E3A6268D3AEBDDD495BB657EF1BE6C3ACA27A73778D5339812536EFE2D91`, новый venv
  в `/tmp` вне checkout. Сценарий и повторное открытие загрузили Core, DBOS и
  расширение из `site-packages` этого venv.
- `_scratch/stage6-pass2-cp1252-after/report.json` и
  `_scratch/stage6-pass2-cp1252-installed/report.json` — те же сценарии под
  собранной локалью `en_US.CP1252`.

Файл probe из `961e203` под той же локалью упал в `_reopen_in_new_process` с
`UnicodeEncodeError` (`_scratch/stage6-pass2-cp1252-before.log`).
Предыдущие прогоны `-c` относятся к `961e203`.

- План v1 → v2 до запуска, запрос со старой ревизией — `stale_plan`, Method v1
  закреплён. Ранний B: выдача `dependency_open`, назначение `child_not_issued`,
  ноль Attempt/outbox/HTTP.
- Выдача A: повтор той же операции — прежняя квитанция, другая операция —
  `already_issued`. Назначение A закрепило план v2 и Method v1; повтор — прежняя
  квитанция, второе назначение — `stale_attempt`. Повторная доставка launch при
  ожидании A: один DBOS workflow, HTTP не добавился.
- Наблюдаемые состояния A во время Pi RPC: `ready:launch_pending → running →
  waiting → ready:continuation_ready → running → running:stop_requested →
  proposed:result_proposed`. Это выборка опроса раз в 20 мс: короткое окно
  между запросом и записью остановки видно не в каждом прогоне (у B в
  установленном прогоне — `ready:launch_pending → running →
  proposed:result_proposed`).
  Отдельный обычный Pi через `/zara-status` показал `waiting`, вопрос, план `@2`
  и роль `a` без HTTP. Дубль ответа вернул ту же квитанцию; всего 2 HTTP для A,
  digest каждого вызова совпал с телом HTTP.
- Отдельное принятие A через bridge сделало B `proposed:issue_pending`; выдача
  B вставила точный Artifact результата A во входы B. B прошёл Pi RPC одним HTTP
  и был отдельно принят. Преждевременное принятие родителя — `obligation_open`.
  После двух подтверждений родитель показал `ready:output_link_pending`; после
  связи выхода принят, `succeeded`, повтор — прежняя квитанция, Activity
  `ongoing`.
- Независимый составной ребёнок C с изменённым Decision после назначения:
  `run_assigned` → `stale_basis`, 0 HTTP, 0 invocations, назначение `stopped`,
  Attempt `interrupted`, Pi home не создан, состояние `blocked`.
- Новый процесс `python -I` прочитал те же состояния, план, обязательства,
  результаты и квитанции принятия. После reopen обычный Pi показал родителя и
  детей `succeeded`.
- Технические копии (DBOS `executor.sqlite3` и 6 файлов двух Pi RPC home) не
  содержат маркеров плана, вопроса, ответа или результата.
- Backup format 2, schema 6 с DBOS и 6 Pi-файлами; restore в эпоху 2 сохранил
  закрепление, вопрос и состояния, outbox отменён, старая очередь инертна.
- Последовательное удаление: результат A (с перезапуском процесса после
  очистки), затем B и его результат, затем A и частичный Artifact, затем
  родитель. После каждого шага маркеры отсутствовали в live SQLite Core/DBOS, Pi
  homes и новом backup; старые пакеты удалены; независимый C и его план
  остались; удаление Method, закреплённого C, — `method_in_use`.
- Итого 3 HTTP на весь сценарий.

## Пределы

Не проверялись:
- ревизия плана во время исполнения и переход версии Method;
- waiver и inactive/unresolved;
- несколько параллельных детей и вложенный составной Work;
- исходы failed/cancelled/stale;
- аварийная матрица commit/checkpoint/смерти Pi и отзыв права во время хода
  для составного ребёнка;
- реальный provider и изменяющие инструменты.

Интеграцию отдельной Attempt родителя этот проход не вводит: выход родителя
по-прежнему связывается с точным принятым результатом ребёнка. Удаление
управляемых копий не охватывает внешние копии, OS snapshots и provider
retention. Независимая Windows-проверка владельца на
`961e203e0aadf836bf6031b47427fae5fc9bf08c` прошла `tools.check --deliver`
(546 тестов, 21 контракт, типы, сборка; SHA-256 wheel совпал). Оба Windows-probe
прошли полностью только с диагностическим `-X utf8`, который теперь внесён в
probe. Исправления этого раунда на Windows ещё не проверялись.

## Ограничения Linux-проверок

Gates не ослаблены: `tools/check.py`, `validation.config` и существующие тесты
не менялись ради Linux. Сами ограничения:

- `tools.check --deliver` на Linux проходит hygiene, структуру отчёта и Ruff, а
  затем останавливается на mypy: 35 ошибок, все про атрибуты, существующие
  только на Windows (`msvcrt.locking`/`LK_*`, `ctypes.WinDLL`/`get_last_error`).
  Они находятся в 11 файлах, не изменённых с `29d887d`. Остальные шаги
  выполняются отдельно; `mypy --platform win32` чист. Обязательный полный
  прогон — Windows.
- `test_import_refuses_unfixed_sqlite_runtime_in_a_fresh_process` на Linux
  падает. Тест ожидает неподдерживаемый встроенный SQLite, а conda-forge Python
  уже содержит точный 3.53.3. `29d887d` и `961e203` падают так же.
- В Linux-локалях C/POSIX Python и так работает в UTF-8 mode, поэтому
  `tests/tools/test_probe_stage6_rpc.py` здесь не различает отсутствие флага;
  различает Windows. На Linux дефект воспроизведён вручную: локаль
  `en_US.CP1252` собрана glibc `localedef` и подключена через `LOCPATH`.
- Хук `.githooks/pre-commit` вызывает `#!/usr/bin/env python`; в контейнере это
  системный Python 3.11, который не разбирает синтаксис 3.13. Hygiene-хук
  запускался с Python 3.13.7 в `PATH`.
- Pi runtime в игнорируемом `_scratch` дополнен верхнеуровневым
  `@earendil-works/pi-ai@0.87.0` (см. выше).

END_OF_FILE

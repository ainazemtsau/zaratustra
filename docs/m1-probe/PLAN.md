# M1 / T1 — узкая исполнимая проба

CALL: c-solmax-zaratustra-m1-probe-admission-20260909-exec, contract 36, PROBA.
База: a6e6a2e5be90eed111504712c7443b8a907576c1, прямой потомок принятого
05047e38acc7386484223a5feacc510b015b2a85; отличие — пять docs/evidence путей.
Worktree: C:/projects/zaratustra/_scratch/m1-probe-20260909.
Branch: codex/m1-probe-20260909. Source Work7 и Work3 не изменяются.

## Решение перед исполнением

Проверяем только process-rules-outside-core-on-real-m0: предметное решение
о допустимом продолжении принимает внешний Python rule; настоящее M0 открывает
ограниченный context и атомарно сохраняет Result/next Work через Mutation API.
Rule не получает путь к workspace или authority и возвращает лишь предложение.
Доверенный локальный адаптер отдельно подтверждает точный запрос на основании
владельческого RUN и разрешения CALL на новые fictional данные. Это разрешение
исполнения пробы, не owner acceptance продукта.

Конкретная пара: fictional batch требует одновременно observed=true и
recorded=true; fictional cycle требует отметку только текущей фазы, сохранённой
в executor_requirements выбранной Work, и переводит следующую Work в другую
фазу. На одинаковых observed=true, recorded=false первая блокирует продолжение,
вторая переходит observe→record; в фазе record тот же вход блокируется. Затем
recorded=true позволяет record→observe. Для batch также выполняется успешный
случай с обеими отметками. Это различие переходов, не названий.

До фиксации плана рассмотрено разовое завершение без next Work: текущий
ResultSubmission требует next_work. Оно не выбрано сценарием этой пробы;
поддержка терминального Result не заявляется и Core для неё не расширяется.

В M0 один Process на workspace. Здесь каждый процесс получает отдельную новую
workspace; это ограничение раннего T1, не ответ о сосуществовании обоих в M1.
Core, schema и принятые тесты остаются точными bytes базы. Ни §30 «без изменения
основной семантики Core», ни §40 «без изменения Core» не ослабляются.

## Проверка и falsifier

Отказ правила оставляет DB/history неизменными. Успех создаёт один Result и
одну ready next Work с точными данными правила; следующий context содержит их
и исходный accepted artifact. Проверяются отсутствие authority, чужой Process,
устаревшая revision, смена запроса после подтверждения и повтор через Core.
Если для этого нужны предметная ветка Core, прямой state writer или изменение
основания — остановка и HOME с контрпримером. Native tools.check обязателен.
Тесты проверяют ненаблюдаемые authority/state свойства; owner-visible выбор
fictional процесса предъявляется человеку, не объявляется принятым по тестам.

## Версии, evidence и rollback до изменения

Сначала commit общей подготовки + batch; затем отдельный commit подключения
cycle. Сохраняются оба SHA и diff подключения второго, полный diff от M0,
exact JSON inputs/context/proposal/authorization/receipts/history/state,
команды/выводы, runtime и hashes. Это узкая запись W20 до первого прогона.
Производственные файлы идут в пакет process_probe; development runner — tools.
Пробные workspace и exploratory output — только новый ignored _scratch/.
Проверенные отчёты и retained ZIP/manifest копируются в docs/m1-probe/evidence.

Перед каждым сценарием сохраняется quiescent pre-submit snapshot штатным
tools.retain_trial; восстановление — его документированный restore: извлечь
точные сохранённые bytes/layout в НОВУЮ папку, проверить hash всех файлов,
открыть через read_records/read_history/open_work с новым точным разрешением
на путь и снова исполнить тот же запрос. Исходные state и evidence сохраняются.
Это восстановление backup, не SQL/Markdown edits; identity/history не правятся.
В случае отказа сохраняется полное состояние; ни reset/clean, ни стирания данных.
Все прогоны синхронны и локальны; новые процессы пользователя не запускаются.

## W15–W20: частичный ответ и оставшееся open

- W15: для T1 rule — явно выбранный доверенным адаптером Python объект;
  binding/phase — существующие executor_requirements Work, schema6 без миграции;
  неизвестный binding отклоняется. Это probe schema v1, не регистрация M1.
  OPEN: pack/type/instance, registration, сохранённые ссылки и missing/incompatible
  pack, смена версии начатой Work. answerer PLAN; rewrites: registry, manifests,
  привязки Work/context, adapters, сохранённые ссылки и migrations; ≤1 дня не доказано.
- W16: OPEN целиком — все семь capabilities, scope/revisions, empty/denied/
  unavailable, metadata/counts, consistency и изменение прав. answerer PLAN;
  rewrites: публичный контракт, read guards, mapping, context/projections и
  потребители; ≤1 дня не доказано. Существующая Work isolation используется.
- W17: T1 Core неизменен; baseline второго — committed common runner+batch.
  OPEN: полный M1 baseline, совместное размещение, гарантия полного внешнего
  контракта. answerer PLAN; rewrites: границы модулей, refactor, замороженный
  diff/evidence и повтор сценариев; ≤1 дня не доказано. Изменение гарантии → OWNER.
- W18: T1 conjunction vs persisted alternating phase, описанные выше.
  OPEN: полные работающие сценарии двух существенно разных M1 процессов;
  примеры не product templates. answerer PLAN; rewrites: fixtures/сценарии/
  ожидания, обычно обратимо до связанной реализации; после предметного кода
  оценить заново. Новый owner concept/acceptance → OWNER.
- W19: OPEN целиком — единый обзор без нового frontend/assistant. answerer PLAN;
  rewrites: renderer/adapters и проверки вывода; обычно ≤1 дня до фиксации внешнего
  контракта. Семантика остаётся W16.
- W20: T1 exact evidence и граница commits определены выше. OPEN: evidence обоих
  полных сценариев/общего обзора M1. answerer PLAN; rewrites: evidence capture/
  manifest, контрольные состояния и повтор сценариев; до прогона обычно ≤1 дня,
  потерянную provenance после прогона восстановить не гарантировано.

## Источники и owner boundary

Direction live/solmax/work/: zaratustra-architecture-plan-2026-09-05.md §§8,30,40;
zaratustra-m1-shape-2026-09-09.md §4/T1/K1; converge-g-zara-m1-modularity.md
W01–W20/C01–C06; zaratustra-m1-probe-admission-2026-09-09.md.
Планирование HOW не вводит новую owner concept. Действует точное разрешение
«Если нет каких-то расхождений с планом, то я как бы подтверждаю, да, ты можешь
идти.» — knowledge/zaratustra-plan-conforming-approval-2026-09-07.md.
Verdict для этого технического плана: conforms within T1 scope under delegation.
Новая продуктовая приёмка pending; binding fresh Direction G5 не выполнялась.
M0 partial; T1/M1 не закрываются, T2 не запускается; next: solmax.

END_OF_FILE: docs/m1-probe/PLAN.md

# T6 — общий обзор двух процессов, кандидат без проверок

## outcome

CALL c-solmax-zaratustra-m1-overview-20260910-exec, PROBA36, basis
c4b8aea4db38fea4c39a473c47d0d8b82d8552a0. Worktree
C:/projects/zaratustra/_scratch/m1-overview-20260910, branch
codex/m1-overview-20260910, дерево при старте чистое, STOP/STEER отсутствуют,
validation.config сверен: synced_contract_version 36, default_mode PROBA.

Ответ W19: обзор — производный потребитель одного и того же публичного контракта
T3, а не вторая истина и не новая возможность процесса. Добавлен additive модуль
`src/zaratustra/process_packs/overview.py` с `read_overview` и чистой функцией
`overview_lines`; экспорт из `zaratustra.process_packs`. Каждая строка обзора —
ровно один вызов `read_capabilities`, вложенный дословно вместе с эхом
собственного запроса потребителя, SHA-256 точных байтов ответа и проекцией
состояний и counts по тем же семи именам. Envelope прямо фиксирует: строка —
единица согласованности; общей revision и межбазовой транзакции нет; порядок
объявлен вызывающим; представление прав не выдаёт. Отказ одной строки не
отменяет и не скрывает соседнюю; законная пустота остаётся `empty` с count 0.

Поверхность — library плюс development probe, как у T3/T4/T5. Новая CLI-команда
намеренно не добавлена: она потребовала бы установленного загрузчика пакетов по
строке пути модуля, то есть нового механизма выбора исполняемого кода вне
доверенной registration W15, и открыла бы дорогу fictional примерам в
установленный продукт. `tools/probe_overview.py` переиспользует принятый парный
сценарий T5 и после него один раз читает обе явно выбранные fictional workspace
через один registry, сохраняя точные байты, текстовый вид и контрольные обзоры.

Это кандидат. Ни один тест, native gate или сценарий здесь не запускался.

## evidence

PLAN и границы: docs/m1-overview/PLAN.md; наряд: docs/m1-overview/CALL.md;
предъявление и команды: docs/m1-overview/REPRODUCE.md; готовый запуск проверок:
docs/m1-overview/CLAUDE-CHECK.md. Commits: 05398cd PLAN/CALL/baseline,
87db23ae19355e6730c46782535f0db267fee10f source кандидата.

Неизменность записана до реализации в docs/m1-overview/baseline-ids.json.
Ожидаемые после T6 равенства: tree src/zaratustra/core
a93fdbb567c69c14dc1c645bede50157d3c3fc00, tests/fixtures
c8b4594826173680343566049945cac14fad082b, fictional_lot
562949e5984875f50d58c22848a6f279e19821ef, fictional_signal
29708288ddaaadaba45184da8e04385847dca551; blobs capabilities.py 2579131,
capability_models.py f1b2c66, lifecycle.py f5c3c62, runner.py 5ed0d7d.
Под src изменяются только process_packs/__init__.py (строки экспорта),
process_packs/AGENTS.md и новый process_packs/overview.py. Это байтовая
идентичность, а не семантический PASS.

Новые проверки невидимых глазом свойств: tests/zaratustra/process_packs/
test_overview.py — равенство строки собственному ответу T3 и его SHA-256;
проекция как чистая функция ответа; собственные revision у каждой строки при
отсутствии общей; denied/stale/missing pack/missing adapter/absent workspace
рядом с полной соседней строкой; сохранение `empty` против `unavailable`;
неподдержанный ответ адаптера; изоляция выбранного контекста и отказ на чужой
ContextQuery; отсутствие записи в обе workspace; отказ на пустой набор строк,
повтор строки и превышение предела; общий бюджет без частичного ответа;
детерминизм байтов; текстовый вид как чистая функция тех же байтов; эхо запроса
у отказанной строки без данных состояния.

Здесь выполнено только чтение исходников, Git и byte inspection и обычная
commit hygiene: `.githooks/pre-commit` (tools.check hygiene) прошёл на итоговом
дереве, exit 0. Это разбор AST и проверка гигиены, не сборка, не типы, не тесты
и не поведение. Полный `tools.check --deliver` и `tools.probe_overview`
назначены свежему Claude Code; binding G5 — отдельная физическая сессия.

## assumptions

Распределение владельца «Реализация здесь, проверки в Claude Code» сохраняется,
поэтому кандидат предъявляется непроверенным. Замечания форматирования, типов
или импорта возможны и ожидаются как конкретный возврат автору.

Приняты как неизменные W15 и W16: значение семи ответов, scope, права, одна
locked revision и отдельно подтверждаемый selected context. Обзор их не
переопределяет; он ничего не добавляет к ответу строки, кроме проекции
состояний, которые в этом же ответе уже есть.

Общий потребитель получает идентичности строк из публичного Core, а не из
предметных правил: workspace, process, ограниченный набор видимых Work и
текущая revision читаются `read_records`, дальше работает только контракт T3.

Приёмка T5 не является приёмкой T6. Предшествующие G5 относятся к прежней
версии и не покрывают это изменение.

## cuts

Новых cuts нет. Не вводились: новый frontend, assistant, transport, MCP,
установленный загрузчик пакетов и CLI-команда обзора, третий процесс,
дополнительные поверхности, реальные процессы и данные, расписания и
автономность, product remote/push/merge, CI/CD/Actions/уведомления, новые
внешние или денежные права. Core и оба правила не менялись, предметных
исключений нет, гарантии P§30 и P§40 не ослаблены. T7 и M1 не закрываются,
M0 остаётся partial, Direction live/** не изменялся.

Известные пределы кандидата: обзор ограничен шестнадцатью явно выбранными
строками; между строками нет общей транзакции, поэтому соседняя workspace может
измениться между чтениями — это заявлено в envelope, а не скрыто; порядок строк
выбирает потребитель; длинные наборы процессов и любые нефиктивные данные
не проверялись.

## cost

Один additive модуль продукта, один development probe, один файл tests и
документы задачи. Dependencies, schema, package version 0.10.1 и установленный
CLI не менялись. Токены и денежная стоимость не измерялись; новых расходов нет.

## manual-acceptance

T6 pending. Native gates, сценарий и binding fresh G5 не выполнялись здесь и
не заменяются этим отчётом. Owner acceptance и Direction close не объявляются
автором. Actual owner acceptance T5 —
owner-ack:solmax-m1-second-process-accepted-20260910 — относится только к T5.

## next

solmax

Свежий Claude Code: полный `tools.check --deliver`, затем
`tools.probe_overview`, затем binding G5 по docs/m1-overview/CLAUDE-CHECK.md.
FAIL возвращает автору точный raw и воспроизведение; PASS возвращается HOME
вместе с показом самого обзора владельцу. Только HOME продолжает к T7.

END_OF_FILE: RESULT.md

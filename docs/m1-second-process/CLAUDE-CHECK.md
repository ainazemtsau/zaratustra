# Готовое задание для свежего Claude Code — проверки второго процесса и G5

Владелец разрешил: «Реализация здесь, проверки в Claude Code».
Это отдельная физическая reviewer-сессия, не продолжение авторской разработки.
Автор: Codex task 01a08a2a-1109-7211-8aa0-17cc639cf1d7.
Проведи реальные проверки и попытайся опровергнуть все три done_when T5.
Владелец не должен сам собирать команды, выбирать технический порядок или
составлять следующий пакет. Используй этот файл и REPRODUCE.md рядом.

## Точный предмет проверки

Product common repo: C:/projects/zaratustra.
Авторская worktree: C:/projects/zaratustra/_scratch/m1-second-process-20260910.
Авторская branch: codex/m1-second-process-20260910.
Source candidate: **5348690b9d9aa97dc4419ae884885e916d3ba02f**.
PLAN before source: ba1dd8f280ba2bc07fa1f26d2f26a10c0852d5c0.
Before-second: 2df9b286b3b54ac3fabd07db0e7d9b343bc17850;
его source5b145b8bdfb9239939ca118ebe70542ffbb13b68.
Historical: b1e0853f9b405e2910f2085dae6fd7f6100ba009.
Engineering CALL: c-solmax-zaratustra-m1-second-process-20260910-exec, PROBA36.
Вся реализация является UNVERIFIED; автор не запускал native/tests/scenarios.
Не воспринимать старые T4 отчёты как результаты текущего refactor.

Сначала прочитай root AGENTS.md, validation.config, ближайшие AGENTS, STOP/STEER,
этот CALL/PLAN/REPRODUCE и RESULT.md. T4 PLAN определяет выбранную пару;
T5 PLAN реализует её правую колонку. Примеры только в development tests;
в установленном продукте и данных владельца их быть не должно.
Не читать/искать/повторять Work8, original attachment и archive/**.
Манипулятор MAKE THEM LATE — другая задача, не scope этой проверки.

Создай собственную NEW worktree, например
C:/projects/zaratustra/_scratch/g5-m1-second-process-20260910,
branch codex/g5-m1-second-process-20260910. Если имя занято, выбери свежий суффикс,
ничего не очищай и не переключай чужие worktrees.
Начни от handoff commit из сообщения владельца. Если передан только этот файл,
прочитай HEAD авторской ветки: допустим source или его прямой docs-only child,
у которого изменён только docs/m1-second-process/. Иначе остановись с расхождением.
Проверь exact source blobs и CANDIDATE.json, а не доверяй названию ветки.

## Исполнение

1. Managed Python3.13.7, uv sync --locked, PROBA pin/stamp36. Никаких новых
   dependencies, OPORA/frozen-pair/mutation требований. Установленные gates не
   ослаблять. Owner/tool STOP соблюдать. Новые temp/state только в собственной
   ignored _scratch; исходную author worktree, реальные данные и Direction не менять.
2. Выполни полный `uv run --locked python -m tools.check --deliver` с новым
   pytest basetemp и full raw. Это build/hygiene/types/import boundaries/tests,
   не просто pytest. Не заменяй полную проверку выборочными тестами.
3. Выполни `tools.probe_second_process` и `tools.probe_second_install` по
   REPRODUCE.md. Первый выполняет оба полных процесса в одном registry; второй —
   повторяет оба через отдельную wheel-only installation из пустого cwd.
4. Свои refutation probes и чтение полного diff: правила первого процесса
   сохранены; общий host не выдаёт authority от package proposal; чужая workspace
   не меняется и не раскрывается; compare связан с точными accepted bytes;
   state/results/context/pack versions/restore согласованы. Чистая установка не
   создаёт fictional state; внешний fixture не подменяет установленный Core.
   Проверь обе ветви assessment и repeated changed/steady на новых Works,
   незаметную смену stage/binding, отказ revoked/stale/foreign scope.
5. Сопоставь Git baseline/source, full binary diffs в comparison-diffs.zip,
   candidate-source.zip и manifests. Current src/zaratustra целиком совпадает
   с before-second: проверка bytes не подменяет семантическое опровержение
   P§30 «без изменения основной семантики Core» и P§40 «без изменения Core».

Не меняй исходники, авторские tests, PLAN/контракт или RESULT ради прохождения.
Разрешены собственные read-only по отношению к продукту probes и retained
evidence/docs в reviewer-ветке. При FAIL сохрани raw и точное воспроизведение;
верни автору findings, не объявляй исправление и не скрывай неудачный запуск.
Tool/environment failure отделяй от product failure; максимум три повтора одной
упавшей проверки. Проверки, которые не исполнялись, пометь NOT RUN.

## Результат, который вернуть владельцу

Сохрани docs/g5/m1-second-process-20260910/G5-REPORT.md и необходимые доказательства
в собственной ветке, закоммить локально. Без product push/merge, без live/** edits.
Для каждого из трёх done_when CALL: claim, попытка опровержения, конкретное
evidence, PASS/FAIL/UNVERIFIED и ограничения. Отдельно W17/W18/W20, отсутствие
Core/first-rule изменений, shared registry и две независимые workspace revisions.
Нужны exact source/reviewer commits, свежая физическая session identity,
полные команды/raw всех попыток, версии инструментов, входы/выходы обоих
сценариев, snapshots/receipts/restore, installed inventory/wheel и собственные probes.
Хешируй committed bytes, сохрани неудачи; исторический CRLF/LF G5-F01 не повторять.

Ответь владельцу очень просто: что проверено, есть ли ошибки, можно ли переходить
к обсуждению приёмки второго примера; приложи путь к отчёту и commit.
Если FAIL — краткий готовый возврат автору с воспроизведением, без просьбы владельцу
самому составлять CALL. Если PASS — evidence для HOME review, но не автоматическая
приёмка владельца и не Direction close. T5 root остаётся у solmax; T6, T7/M1 и
реальные процессы не запускать. M0 partial сохраняется.

END_OF_FILE: docs/m1-second-process/CLAUDE-CHECK.md

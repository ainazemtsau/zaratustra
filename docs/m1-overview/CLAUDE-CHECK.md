# Свежий Claude Code — проверки T6 и binding G5

Владелец поручил реализацию автору, проверки Claude Code. Кандидат уже закоммичен.
Проведи проверку сам, не проси владельца собирать команды.

Source: 87db23ae19355e6730c46782535f0db267fee10f.
PLAN/baseline commit 05398cd; basis c4b8aea4db38fea4c39a473c47d0d8b82d8552a0.
Авторская worktree C:/projects/zaratustra/_scratch/m1-overview-20260910,
branch codex/m1-overview-20260910; общий Git repo C:/projects/zaratustra.
Принятый предшественник T5: source b4a2aa88, handoff c4b8aea4,
original G5 f4e3a26d85507f76429fc01e53c4dfdc1c4b18c5,
fresh addendum fa4e0796710b8ddcf07a9aada32b2351f7b8ecf7 (235 tests / 11 contracts).
Автор T6 не запускал pytest, native gates и сценарии: он делал только чтение
исходников, Git/byte inspection и обычный commit hygiene. PASS не заявлен.

Начни в свежей физической reviewer-сессии, отдельной от авторской. Прочитай
AGENTS.md, src/zaratustra/process_packs/AGENTS.md, tools/AGENTS.md,
validation.config (PROBA36), STOP/STEER, а рядом CALL.md, PLAN.md, REPRODUCE.md,
baseline-ids.json и корневой RESULT.md. Создай NEW reviewer worktree, например
C:/projects/zaratustra/_scratch/g5-m1-overview-20260910,
branch codex/g5-m1-overview-20260910, от source commit выше. При занятом имени
выбери новый суффикс: не очищай и не переключай чужие worktree и ветки.
Если дан только этот файл, HEAD авторской ветки допустим лишь как прямой потомок
87db23a с изменениями только RESULT.md и docs/m1-overview/; иначе сообщи drift.

## Что проверить

1. **Полный обязательный native gate**, не выборочные инструменты, и **сценарий
   обзора** — точные команды в REPRODUCE.md рядом. Оба под Tee-Object в новый
   basetemp; старые evidence не чистить. Автор не запускал ruff format/lint,
   mypy, import-linter, pytest и probe: механические замечания форматирования и
   типов вероятны и должны быть возвращены автору как конкретный вывод, а не
   исправлены ослаблением проверок. Максимум три повтора одного failed gate.
2. **Три done_when CALL, каждое отдельно.**
   (1) Общий потребитель получает оба процесса через контракт T3 в существующей
   допустимой поверхности и не нуждается в предметных инструкциях для обходного
   чтения состояния. Проверь, что `src/zaratustra/process_packs/overview.py` не
   импортирует ни один пакет, не читает state сам и не содержит предметных веток.
   (2) Представление согласовано с разрешённым state и правилами W16, включая
   пустые и недоступные ответы; выбранная Work сохраняет изоляцию контекста.
   (3) Воспроизводимый вывод exact version сохранён для обоих процессов; новых
   frontend/assistant/transport и установленного загрузчика пакетов нет.
3. **Byte identity** по docs/m1-overview/baseline-ids.json: tree
   src/zaratustra/core, tests/fixtures и обоих fictional пакетов, blobs
   capabilities/capability_models/lifecycle/runner. Изменения ожидаются только в
   process_packs/__init__.py, process_packs/AGENTS.md, новом overview.py, новом
   tools/probe_overview.py, новых tests, AGENTS.md, tools/AGENTS.md и docs.
   Это доказательство идентичности, не семантический PASS.
4. **Binding fresh G5.** Попробуй опровергнуть заявления, а не подтвердить их:
   обзор, читающий состояние в обход контракта; знание пакета внутри обзора;
   denied/unavailable, показанные как законная пустота; утечка скрытых Work,
   counts или чужого контекста; общий revision либо обещание межбазовой
   транзакции; запись в workspace при чтении; полномочия, выданные производным
   представлением; частичный ответ при превышении бюджета. Сохрани полный raw.
   Прежняя G5 T5 не является G5 этого изменения.

Не редактируй продукт, авторские tests или контракт. Разрешены свои probes и
retained evidence/docs в reviewer-ветке. При FAIL верни точное воспроизведение
автору, не исправляй вместо него и не ослабляй проверку. Не читать и не искать
Work8, original attachment, archive/**. Не работать с реальными данными, не
запускать T7, не делать product remote/push/merge, не менять Direction live/**.
Установка, репозиторий и данные владельца этой проверке недоступны.

## Возврат

Сохрани и локально закоммить `docs/g5/m1-overview-20260910/G5-REPORT.md` и полный
raw/evidence. Назови exact source/reviewer commits и свежую session identity.
Отдельные verdict: (а) полный deliver, (б) три done_when, (в) неизменность Core
и обоих правил. Укажи, что выполнено, что NOT RUN и какие ограничения остаются.
Хеши retained evidence считай от committed Git blobs.

Покажи владельцу сам обзор: содержимое `overview.txt` из прогона, коротко —
результат, ошибки если есть, полный путь к отчёту и commit. Owner acceptance T6,
Direction close, T7 и M1 этим отчётом не объявляются: их решает владелец и HOME.

END_OF_FILE: docs/m1-overview/CLAUDE-CHECK.md

# Свежий Claude Code — сверка восьми исправленных мест в документах

Владелец поручил реализацию автору, проверки Claude Code. Правки уже
закоммичены. Проведи проверку сам, без запроса владельцу собирать команды.
Прежние handoff: CLAUDE-CHECK.md к 87db23ae, CLAUDE-RECHECK.md к 4dad08e,
CLAUDE-RECHECK-2.md к 456776a, CLAUDE-RECHECK-3.md к f7bf592.

Проверенный код: 456776a1e346e28952a6da7813a629e4a079a2ba и
f7bf5920efd90b4461c7b2b1610140a4b8a4f620. На обоих обязательный полный
`tools.check --deliver` пройден, exit 0, 252 passed, 11 contracts kept.
Текущий handoff pin: см. сообщение владельца; это прямой потомок f7bf592.
PLAN/baseline 05398cd894be9f0a74730d95bafea7d2961d4f39;
basis c4b8aea4db38fea4c39a473c47d0d8b82d8552a0.
Авторская worktree C:/projects/zaratustra/_scratch/m1-overview-20260910,
branch codex/m1-overview-20260910; общий Git repo C:/projects/zaratustra.
Четыре прошлые G5: 9d46e2e (deliver FAIL, пять возвратов);
31e6a47 (deliver PASS, подделка закрыта, три возврата);
codex/g5-m1-overview-third-20260910, коммиты 969ba40/969895d/000c4a8
(deliver PASS, два возврата); codex/g5-m1-overview-docs-20260910,
коммиты c933abe/11cc05a (deliver PASS, восемь неточностей документов).
Автор снова ничего не запускал, кроме commit hygiene. PASS не заявлен.

Начни в свежей физической reviewer-сессии, отдельной от авторской. Прочитай
AGENTS.md, src/zaratustra/process_packs/AGENTS.md, tools/AGENTS.md,
validation.config (PROBA36), STOP/STEER, а рядом CALL.md, PLAN.md,
FIX-G5-20260910.md, REPRODUCE.md, baseline-ids.json и корневой RESULT.md.
Создай NEW reviewer worktree, например
C:/projects/zaratustra/_scratch/g5-m1-overview-docs2-20260910,
branch codex/g5-m1-overview-docs2-20260910, от handoff pin. При занятом имени
выбери новый суффикс: не очищай и не переключай чужие worktree и ветки.
Прежние четыре отчёта не перезаписывать.

## Почему круг короткий

Ни один файл Python не менялся. Проверь это первым делом:
`git diff --stat f7bf592 HEAD -- src tools tests` должен показывать ровно один
файл, `src/zaratustra/process_packs/AGENTS.md`, и ни одного `.py`. Если
изменён хотя бы один `.py`, круг перестаёт быть коротким: выполняй полную
программу CLAUDE-RECHECK-2.md и сообщи drift.

Полный `tools.check --deliver` всё равно обязателен, потому что RESULT.md
входит в проверку структуры отчёта. Выполни его целиком на новом pin и назови
результат явно. Точные команды — REPRODUCE.md рядом; замени имя scratch на
новое, например `_scratch/t6-docs2-01`. Сценарий и поведенческие проверки
переиспользуй с f7bf592 после подтверждения, что Python не менялся.

## Проверить ровно оставшееся

Восемь возвратов прошлого круга, каждый по своему месту. Таблица с номерами
08–15 и описанием правок — в FIX-G5-20260910.md, последний раздел.

1. Описание проекции совпадает с реализацией в трёх местах сразу:
   `src/zaratustra/process_packs/AGENTS.md`, раздел «Контракт документа» в
   PLAN.md и `_summary` в overview.py. Все три должны называть состояние,
   count и код отказа.
2. Строка PLAN.md про `__init__.py` называет и переписанную строку docstring;
   формулировка «лишь строки экспорта» больше не встречается.
3. В CLAUDE-RECHECK-2.md и REPRODUCE.md нет утверждения, что прежние числа
   тестов относятся к неполному gate. Для 251 gate был полным.
4. RESULT.md не приписывает самому 456776a больше кругов свежей проверки, чем
   он прошёл.
5. FIX-G5-20260910.md не приписывает третьему отчёту требование про
   запись-каталог и его карта разделов совпадает с фактическим числом.
6. Пометка в CLAUDE-RECHECK-2.md говорит точно, что заменены заголовок и три
   строки, а остальной текст не переписан.
7. PLAN.md несёт объявленный раздел поправок и по существу не переписан:
   решение W19, границы, размер и диспозиции W15–W20 те же, что на 05398cd.
8. baseline-ids.json: множество объявленных путей точно равно
   `git diff --name-only c4b8aea HEAD`, заявленное число совпадает с
   фактическим, записей-каталогов нет.
9. Восемь идентификаторов неизменности не изменились; Core и оба fictional
   пакета байтово равны basis.

Не редактируй продукт, авторские tests или контракт. Разрешены свои probes и
retained evidence/docs в reviewer-ветке. При FAIL верни точный вывод автору,
не исправляй вместо него. Перечисли все возвраты явно и пронумеруй.
Не читать и не искать Work8, original attachment, archive/**. Не работать с
реальными данными, не запускать T7, не делать product remote/push/merge,
не менять Direction live/**. Установка владельца этой проверке недоступна.

## Возврат

Сохрани и локально закоммить `docs/g5/m1-overview-docs2-20260910/G5-ADDENDUM.md`
и полный raw. Назови exact source/reviewer commits и свежую session identity.
Отдельные verdict: (а) полный deliver с явным PASS или FAIL, (б) отсутствие
изменений в файлах Python относительно f7bf592, (в) восемь мест выше.
Укажи, что переиспользовано с f7bf592, что выполнено заново и что NOT RUN.

Владельцу коротко: результат, ошибки если есть, полный путь к отчёту и commit.
Owner acceptance T6, Direction close, T7 и M1 этим отчётом не объявляются:
их решает владелец и HOME.

END_OF_FILE: docs/m1-overview/CLAUDE-RECHECK-4.md

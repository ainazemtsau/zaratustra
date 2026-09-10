# Свежий Claude Code — повторная проверка T6 после двух замечаний G5

Владелец поручил реализацию автору, проверки Claude Code. Исправление уже
закоммичено. Проведи проверку сам, без запроса владельцу собирать команды.
Это новый handoff; прежний CLAUDE-CHECK.md относится к source 87db23ae.

Source fix: 4dad08eeaa9eaa2a3064947e0f1ffc2707476006.
Прежний source 87db23ae19355e6730c46782535f0db267fee10f;
PLAN/baseline 05398cd894be9f0a74730d95bafea7d2961d4f39;
basis c4b8aea4db38fea4c39a473c47d0d8b82d8552a0.
Авторская worktree C:/projects/zaratustra/_scratch/m1-overview-20260910,
branch codex/m1-overview-20260910; общий Git repo C:/projects/zaratustra.
Предыдущая G5 9d46e2e8b3af2924d19c17835c0e5647eedd8ff6,
branch codex/g5-m1-overview-20260910,
отчёт docs/g5/m1-overview-20260910/G5-REPORT.md. Её verdict: deliver FAIL,
done_when 1 и 3 выполнены, done_when 2 не выполнено, Core и оба правила PASS.
Автор снова не запускал pytest, native gates и сценарии: только чтение
исходников, Git/byte inspection и обычная commit hygiene. PASS не заявлен.

Начни в свежей физической reviewer-сессии, отдельной от авторской. Прочитай
AGENTS.md, src/zaratustra/process_packs/AGENTS.md, tools/AGENTS.md,
validation.config (PROBA36), STOP/STEER, а рядом CALL.md, PLAN.md,
FIX-G5-20260910.md, REPRODUCE.md, baseline-ids.json и корневой RESULT.md.
Создай NEW reviewer worktree, например
C:/projects/zaratustra/_scratch/g5-m1-overview-recheck-20260910,
branch codex/g5-m1-overview-recheck-20260910, от source fix выше. При занятом
имени выбери новый суффикс: не очищай и не переключай чужие worktree и ветки.
Если дан только этот файл, HEAD авторской ветки допустим лишь как прямой
потомок 4dad08e с изменениями только RESULT.md и docs/m1-overview/;
иначе сообщи drift.

## Проверить ровно оставшееся

1. Изучи diff 87db23a → 4dad08e. Ожидается ровно четыре файла: `_flat` и его
   применение в `overview_lines`, одна строка импорта в tools/probe_overview.py
   плюс её вызовы, новый контроль NOISY и новый тест, строки в module AGENTS.
   Не должно быть ослабления проверок, изменения JSON-документа, изменения
   контракта T3, правил, host и установленного src/zaratustra за пределами
   process_packs/overview.py и process_packs/AGENTS.md.
2. Выполни целиком обязательный native gate на новом pin, не отдельный ruff,
   затем сценарий. Точные команды — REPRODUCE.md рядом; замени имя scratch на
   новое, например `_scratch/t6-recheck-01`. Native должен целиком завершиться
   exit 0: formatting, lint, types, 11 boundaries, tests, build и report
   structure. Прежние 250 tests относятся к старому source и к неполному gate:
   фактическое новое число бери из вывода. Максимум три повтора одного gate.
3. Заново проверь именно done_when 2, которое ты отклонил. Свободный текст
   пакета не должен создавать строку, счётчик или заявление в человекочитаемом
   виде. Воспроизводимый контроль лежит рядом со сценарием:
   `overview-forged-status.txt` и `.json` в папке прогона. Попробуй свою
   собственную подделку, не только авторскую: перенос строки, возврат каретки,
   вертикальная табуляция, U+2028, U+0085, ESC-последовательность, длинный
   статус на границе усечения. Проверь также, что документ по-прежнему хранит
   исходное значение статуса побайтно и что строка обзора остаётся равна
   собственному ответу `read_capabilities`.
4. Done_when 1 и 3 ты уже подтвердил на 87db23a. Переиспользуй тот результат
   после сверки узкой дельты; если увидишь новый риск, проведи только нужную
   дополнительную проверку и сохрани её raw. Неизменность Core и обоих правил
   по baseline-ids.json сверь заново на новом pin.

Не редактируй продукт, авторские tests или контракт. Разрешены свои probes и
retained evidence/docs в reviewer-ветке. При FAIL верни точный вывод автору,
не исправляй вместо него и не ослабляй проверку. Не читать и не искать Work8,
original attachment, archive/**. Не работать с реальными данными, не запускать
T7, не делать product remote/push/merge, не менять Direction live/**.
Установка, репозиторий и данные владельца этой проверке недоступны.

## Возврат

Сохрани и локально закоммить `docs/g5/m1-overview-recheck-20260910/G5-ADDENDUM.md`
и полный raw/evidence. Не перезаписывай исходный FAIL report. Назови exact
source/reviewer commits и свежую session identity. Отдельные verdict:
(а) полный deliver, (б) done_when 2 на новом pin, (в) неизменность Core и обоих
правил. Укажи, что переиспользовано с прошлой G5, что выполнено заново и что
NOT RUN. Хеши retained evidence считай от committed Git blobs.

Покажи владельцу сам обзор: содержимое `overview.txt` из прогона и рядом
`overview-forged-status.txt`, чтобы было видно, что подделанный статус больше
не даёт лишней строки. Коротко: результат, ошибки если есть, полный путь к
отчёту и commit. Owner acceptance T6, Direction close, T7 и M1 этим отчётом
не объявляются: их решает владелец и HOME.

END_OF_FILE: docs/m1-overview/CLAUDE-RECHECK.md

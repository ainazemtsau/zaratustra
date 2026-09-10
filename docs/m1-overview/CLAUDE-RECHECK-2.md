# Свежий Claude Code — третий круг T6 после трёх оставшихся возвратов

Владелец поручил реализацию автору, проверки Claude Code. Исправление уже
закоммичено. Проведи проверку сам, без запроса владельцу собирать команды.
Это новый handoff; CLAUDE-CHECK.md относится к source 87db23ae,
CLAUDE-RECHECK.md — к source 4dad08e.

Source fix: 456776a1e346e28952a6da7813a629e4a079a2ba.
Прежние source 87db23ae19355e6730c46782535f0db267fee10f и
4dad08eeaa9eaa2a3064947e0f1ffc2707476006;
PLAN/baseline 05398cd894be9f0a74730d95bafea7d2961d4f39;
basis c4b8aea4db38fea4c39a473c47d0d8b82d8552a0.
Авторская worktree C:/projects/zaratustra/_scratch/m1-overview-20260910,
branch codex/m1-overview-20260910; общий Git repo C:/projects/zaratustra.
Первая G5 9d46e2e8b3af2924d19c17835c0e5647eedd8ff6,
branch codex/g5-m1-overview-20260910: deliver FAIL, done_when 2 не выполнено,
пять возвратов. Вторая G5 31e6a47056ebc2056327910265bfbd1afe31111a,
branch codex/g5-m1-overview-recheck-20260910: подделка статуса закрыта на
двадцати собственных случаях, три возврата оставлены открытыми.
Автор снова не запускал pytest, native gates и сценарии: только чтение
исходников, Git/byte inspection и обычная commit hygiene. PASS не заявлен.

Начни в свежей физической reviewer-сессии, отдельной от авторской. Прочитай
AGENTS.md, src/zaratustra/process_packs/AGENTS.md, tools/AGENTS.md,
validation.config (PROBA36), STOP/STEER, а рядом CALL.md, PLAN.md,
FIX-G5-20260910.md, REPRODUCE.md, baseline-ids.json и корневой RESULT.md.
Создай NEW reviewer worktree, например
C:/projects/zaratustra/_scratch/g5-m1-overview-third-20260910,
branch codex/g5-m1-overview-third-20260910, от source fix выше. При занятом
имени выбери новый суффикс: не очищай и не переключай чужие worktree и ветки.
Прежние два отчёта не перезаписывать. Если дан только этот файл, HEAD авторской
ветки допустим лишь как прямой потомок 456776a с изменениями только RESULT.md
и docs/m1-overview/; иначе сообщи drift.

## Первым делом — недостающий verdict

Второй отчёт не назвал результат обязательного полного `tools.check --deliver`
на pin 4dad08e. Он не считается пройденным. Выполни его целиком на новом pin,
не отдельные инструменты, и назови результат явно. Точные команды — REPRODUCE.md
рядом; замени имя scratch на новое, например `_scratch/t6-third-01`. Native
должен целиком завершиться exit 0: formatting, lint, types, 11 boundaries,
tests, build и report structure. Прежние числа тестов относятся к прежним
source и к неполному gate: фактическое новое число бери из вывода. Максимум
три повтора одного gate. Затем `tools.probe_overview`.

## Проверить ровно оставшееся

1. Изучи исходную дельту `git diff 4dad08e 456776a`: ровно четыре файла —
   проекция `_summary` с полем `code`, подпись revision и коды в
   `overview_lines`, дополнительные утверждения о stale строке в
   tools/probe_overview.py, обновлённые и новый тест, учёт в baseline-ids.json.
   Не должно быть изменения вложенного ответа T3, контракта, правил и host.
2. Три возврата второго отчёта, каждый отдельно.
   (а) Отказанная строка больше не печатает `revision=` из эха запроса: без
   envelope печатается `requested_revision=`, с envelope — `state_revision`
   самого ответа. Проверь, что у успешной строки вид не изменился.
   (б) Код отказа виден в проекции и в тексте как `state:code`, так что conflict
   и missing_pack различимы. Проверь, что кодов нет у ok и empty ответов и что
   ни один код не приходит из свободного текста пакета.
   (в) `changed_by_design` в baseline-ids.json перечисляет оба AGENTS.md, а
   восемь идентификаторов неизменности не изменились.
3. Проверь, что расширение проекции ничего не раскрыло сверх собственного
   ответа строки: `code` должен присутствовать в том же ответе `response`, а
   строка обзора остаётся байтово равной собственному `read_capabilities`.
4. Убедись, что закрытая подделка статуса не вернулась: прогони свои случаи из
   прошлого круга заново на новом pin, включая ESC и границы усечения.
5. Done_when 1 и 3 переиспользуй после сверки узкой дельты. Неизменность Core
   и обоих правил по baseline-ids.json сверь заново на новом pin.

Не редактируй продукт, авторские tests или контракт. Разрешены свои probes и
retained evidence/docs в reviewer-ветке. При FAIL верни точный вывод автору,
не исправляй вместо него и не ослабляй проверку. Если возвратов несколько,
перечисли их все явно и пронумеруй: прошлый круг сообщил автору два пункта из
пяти. Не читать и не искать Work8, original attachment, archive/**. Не работать
с реальными данными, не запускать T7, не делать product remote/push/merge,
не менять Direction live/**. Установка владельца этой проверке недоступна.

## Возврат

Сохрани и локально закоммить `docs/g5/m1-overview-third-20260910/G5-ADDENDUM.md`
и полный raw/evidence. Назови exact source/reviewer commits и свежую session
identity. Отдельные verdict: (а) полный deliver с явным PASS или FAIL,
(б) три возврата второго отчёта, (в) неизменность Core и обоих правил,
(г) подделка статуса на новом pin. Укажи, что переиспользовано, что выполнено
заново и что NOT RUN. Хеши retained evidence считай от committed Git blobs.

Покажи владельцу сам обзор: `overview.txt`, рядом `overview-forged-status.txt`
и `overview-stale-row.txt`, чтобы были видны и обычный обзор, и обезвреженная
подделка, и честная подпись отказанной строки. Коротко: результат, ошибки если
есть, полный путь к отчёту и commit. Owner acceptance T6, Direction close, T7
и M1 этим отчётом не объявляются: их решает владелец и HOME.

END_OF_FILE: docs/m1-overview/CLAUDE-RECHECK-2.md

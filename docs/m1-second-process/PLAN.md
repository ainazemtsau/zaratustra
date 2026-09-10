# T5 — второй проверочный процесс: раунды сигнала

CALL c-solmax-zaratustra-m1-second-process-20260910-exec. PROBA, pin/stamp 36.
Owner: «Реализация здесь, проверки в Claude Code»; это запуск, не приёмка T5.
Изолированная worktree C:/projects/zaratustra/_scratch/m1-second-process-20260910,
branch codex/m1-second-process-20260910. Начальный HEAD
2df9b286b3b54ac3fabd07db0e7d9b343bc17850, чистый; STOP/STEER отсутствуют.
Основание: принятые T4 PLAN и test-only решение, текущий CALL и shape T5.
Манипулятор MAKE THEM LATE к этой задаче не относится по прямому ответу владельца.

## Правила пары — W18

Конечная партия KITE остаётся inspect → decide → cancelled continuation:
нужны обе отметки у каждого check и отдельное решение с точным digest проверки.
Второй пример реализует уже выбранную в T4 правую колонку: условный сигнал BEACON.
observe=steady создаёт следующий observe, observe=changed создаёт compare,
compare с digest именно принятого changed создаёт следующий observe.
Никаких расписаний, реальных сигналов, фонового исполнения или пользовательских
шаблонов. Число раундов задаёт только ограниченный сценарий запуска; правило не
содержит счётчика, автоматического конца, решения о выпуске или conjunction gate.

Вход observe: kind=observation, signal=BEACON, observation=steady|changed.
Вход compare: kind=comparison, signal=BEACON, observation_sha256 и
assessment=explained|unexplained. Оба ответа сохраняются и возвращают observe;
unexplained не выдумывает отдельного workflow. Digest связывает сравнение с
точными принятыми байтами, а реальные контекстные ссылки наследует общий Core.
Неверный формат, стадия, pack binding или digest → отказ без mutation.
Семь ответов описывают только переданные metadata и разрешённый selected context;
compare требует внимания и ответа, завершённые Results остаются видимыми в scope.

## Размещение и граница — W17

Оба полных пакета регистрируются в одном неизменяемом PackRegistry и используют
одну установленную версию Core. Каждый Process имеет отдельную явно выбранную
fictional workspace. Общего revision и межбазовой транзакции не обещаем.
Shared registry не даёт чужих прав. В обоих направлениях сценарий сохранит
побайтовую неизменность соседней workspace и отказы на чужие query/confirmation.

Пакеты только tests/fixtures/fictional_lot и tests/fixtures/fictional_signal;
не src, не установленный продукт и не пользовательские данные. Dependencies,
schema 7 и product version 0.10.1 не меняются: добавляется внешний dev-пакет.
Из T4 host выделяется общий development ProcessTrial (публикация/Handoff,
подтверждения, snapshots, scoped чтение и replay); LotTrial сохраняет defaults,
SignalTrial передаёт свои initial records/requirements/registration. Предметные
правила не переезжают в host или Core. Два runner используют один этот host.

Границы не переопределяются: historical b1e0853f9b405e2910f2085dae6fd7f6100ba009;
после разрешённой упаковки, ДО второго — source
5b145b8bdfb9239939ca118ebe70542ffbb13b68, docs-only report 2df9b286b3b54ac3fabd07db0e7d9b343bc17850.
Baseline source ZIP и manifest сохраняются из committed blobs до реализации.
После неё сохраняется полный diff от 2df9b28, отдельно от historical b1e0853;
Core/process_packs и первый rule package должны совпасть побайтно с 5b145b8.
Это доказательство идентичности, не семантический PASS по количеству файлов.
Обе гарантии P§30 «без изменения основной семантики Core» и P§40 «без изменения
Core» сохранены. Fresh review ищет предметные обходы в полном diff и поведении.
Необходимость менять гарантии/основание → HOME, не скрытое исключение.

## Подготовить здесь, исполнить в Claude Code — W20

Автор пишет код и meaningful проверки невидимых гарантий, но не запускает новые
тесты, native gates или поведенческие сценарии. Исторический T4 PASS не является
PASS текущего изменения. Разрешены Git/byte inspection и обычный commit hygiene.
До handoff: source commit, docs-only handoff commit с exact source pin,
честный RESULT unverified и готовый текст запуска для владельца.

Claude Code: полный tools.check --deliver; оба сценария через shared registry;
несколько signal раундов (steady → changed → compare → steady) с ready Work в конце;
отрицательные inputs/digest/pack/authority/scope, отдельные подтверждения context;
retained inputs/requests/receipts/versions/история, exact restore и повтор Result;
wheel/sdist вне fictional modules/tests/tools, пустая установленная workspace,
запуск обоих внешних пакетов против той же чистой установки из отдельной папки.
Все новые state/evidence/temp находятся в NEW ignored _scratch, старые не чистить.
Fresh Claude chat делает binding G5: пытается опровергнуть три done_when CALL,
сохраняет full raw, exact commits и ограничения; product source не исправляет.
При FAIL возвращает конкретное воспроизведение автору, без ослабления проверок.

W15/W16 принятые общие contracts неизменны; W17/W18/W20 — проверяются T5;
W19 renderer остаётся T6. T7/M1 не закрываются; M0 partial. Ни live/** изменений,
ни product remote/push/merge, ни новых внешних прав/расходов. Один bounded шаг.
PLAN conforms under owner-ack:solmax-plan-conforming-20260907; новая приёмка
не выдумана. RESULT возвращается next: solmax, T5 root остаётся открытым до review.

END_OF_FILE: docs/m1-second-process/PLAN.md

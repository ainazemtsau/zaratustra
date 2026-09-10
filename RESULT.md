# T4 — выдуманные процессы только для тестов, REPORT HOME

## outcome

Продолжение c-solmax-zaratustra-m1-first-process-20260910-exec, PROBA36.
По уточнению владельца T1 process_probe и T4 fictional_lot перенесены в
tests/fixtures. Устанавливаемая версия 0.10.1 содержит только общие механизмы.
Python-правила перенесены без изменений; development runners явно импортируют
fixtures. Core/process_packs не изменялись. Это product handback, не Direction close.

## evidence

Basis 9c9c97889bb79256ebca7d2409233167f2599a41: отдельная G5 исходного candidate
46718e4da82810e57ba7126c8ec3ef0fc4f57268, PASS трёх done_when, одно P3 замечание
к CRLF/LF хешу CALL в старом manifest. Старые evidence/baseline сохранены.
План и owner words: docs/m1-test-only/PLAN.md, OWNER-DECISION.md.
Source: 5b145b8bdfb9239939ca118ebe70542ffbb13b68, отдельная ветка
codex/m1-test-only-processes-20260910. Native Deliver: PASS, 220 tests (60.61s),
9 import contracts, build/hygiene/types/report structure PASS. Raw: native-03.txt.
Предыдущий native01: 216PASS/1FAIL в подготовке sandbox для boundary gate:
копировался только src. Исправлено на src/tools/tests; реальные отрицательные
импорты CLI/test fixture/tool отвергаются, focused3PASS; native02:219PASS.
Fresh G5 выявила residual-directory эффект на aca494: старые __pycache__ оставляли
в wheel два пустых namespace directories; кода/данных примеров уже не было,
но find_spec видел имена. Собственный test воспроизвёл FAIL и после явного
source-exclude обоих старых src-путей получил PASS. Он проверяет sdist и все ZIP
entries, включая directories. Invariant/class: удалённая test fixture не оставляет
устанавливаемого namespace из cache; sweep обоих бывших модулей. Failed raw сохранён.

Отдельная установка: wheel 0.10.1, SHA256
29b207cb3ad5a752ae4095872c52f1b8d40fcc146c0ecfbbb08198da893b5888.
Все package files сверены с Git source; шесть Python-файлов правил совпадают
с прежними побайтно. Core и generic process_packs diff пуст. Python -I из пустой
папки загрузил только wheel: fictional_lot/process_probe, tests/tools отсутствуют.
Новая база после init/migration7: 0 records, revision0. Затем явно подключена
внешняя fixture из tests и повторён полный release/revision19 с ожидаемыми
отказами. Все загруженные product modules остались из wheel, не src checkout.
Финальная установка: install-02.txt и docs/m1-test-only/evidence/final-install/
(wheel/verification/installed paths/scenario/blank workspace). Install01 на прежнем
source отдельно сохранён в корневом evidence. Повтор: docs/m1-test-only/REPRODUCE.md.

## assumptions

Владелец принимает проверочный смысл T4 и требует исключить выдуманные примеры
из устанавливаемого продукта и своих данных. Проверки используют только NEW
_scratch этой изолированной копии. Пользовательская установка не исследуется.

## cuts

Новых cuts нет. Второй Process/T5, renderer/T6, T7/M1 и Direction close не заявлены.
Remote/merge/push, реальные данные и новые внешние права не использовались.
Старый G5 относится к прежнему candidate, не автоматически к этому переносу.

## cost

Одна локальная поправка упаковки по уточнению владельца; новых зависимостей нет.
План сохранён отдельным коммитом d14a6f3. Денежная стоимость не измерена.

## manual-acceptance

Владелец: «Но если только протестировать, так если, ну, тесты все прошли, если он
прошёл, то окей, я этот шаг принимаю.» Уточнение: «В тестах разработки можно;
в продукте и моих данных — нет». Exact words в docs/m1-test-only/OWNER-DECISION.md.
Граница проверена фактически на новой отдельной установке. Существующая
установка и данные владельца не читались и не менялись. Дополнительная binding
fresh G5 в отдельной reviewer задаче 01a08a4d-cc87-7be2-929a-1b28d577bc63
подтвердила final source 5b145b8: 220tests/9contracts, отсутствие старых
каталогов в wheel при сохранённых caches, пустое начальное состояние и
внешнюю fixture до revision19. Это отдельная проверка переноса; исходный
полный G5 PASS остаётся привязан к 46718e4.
Review commit: af1005b0e2483df9199804d972fe69cdb5bdd45f, прямой docs-only
потомок final source. Addendum:
C:/my_global_workflow/ebf7/zaratustra/docs/g5/m1-test-only-20260910/G5-ADDENDUM.md.
Оба узких критерия PASS, незакрытых relocation findings нет; собственный reviewer
native03:220PASS/69.97s/9contracts. Review сохранён отдельно, не слит в author branch.

## next

solmax

Executor возвращает evidence HOME, не закрывает Direction T4/M1 и не открывает T5.

END_OF_FILE: RESULT.md

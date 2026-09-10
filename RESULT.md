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
Типы и 9 import contracts PASS. Полный native Deliver и отдельная установка
текущих байтов ещё выполняются; результат будет внесён после фактического прогона.

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
Проверка исполнения уточнения завершается отдельно от этих слов.

## next

solmax

Executor возвращает evidence HOME, не закрывает Direction T4/M1 и не открывает T5.

END_OF_FILE: RESULT.md

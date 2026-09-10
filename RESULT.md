# T5 — второй процесс подготовлен, проверки ожидаются

## outcome

CALL c-solmax-zaratustra-m1-second-process-20260910-exec, PROBA36.
Подготовлен development-only fictional_signal: steady → observe,
changed → сравнение с exact digest → observe. Есть shared PackRegistry,
общий host, сценарий обоих процессов и проверка отдельной wheel-установки.
Core, generic process_packs, первые правила и зависимости не менялись.
Статус unverified: владелец поручил реализацию здесь, проверки в Claude Code.
Это передача кандидата, не REPORT PASS, приёмка или закрытие T5.

## evidence

Основание 2df9b286b3b54ac3fabd07db0e7d9b343bc17850; его source
5b145b8bdfb9239939ca118ebe70542ffbb13b68. Historical до поправки упаковки
b1e0853f9b405e2910f2085dae6fd7f6100ba009 сохраняется отдельно.
PLAN и baseline закреплены ДО кода: ba1dd8f280ba2bc07fa1f26d2f26a10c0852d5c0.
docs/m1-second-process/baseline-source.zip содержит 78 committed files;
baseline-manifest.json содержит SHA256/размеры. CALL/PLAN лежат рядом.

Код: tests/fixtures/fictional_signal; tools/probe_process_host.py,
probe_second_process.py, probe_second_install.py. Первый runner использует
выделенный общий host и сохраняет прежнюю последовательность шагов.
tests/tools/test_second_process.py задаёт проверки exact basis, реальных
Results/context/replay, неправильных inputs/stages, missing/incompatible pack,
прав/scope/revision и взаимной изоляции. Это написанные проверки, не результаты.

Автор новых native tests/build/types/lint, scenarios и installed checks не запускал.
Source formatting и Git/byte/commit-hygiene inspection не подменяют эти проверки.
Старый T4 PASS относится к старому source; refactor host требует повторения.
Команды/evidence: docs/m1-second-process/REPRODUCE.md. Отдельный handoff закрепит
source commit, полный diff и готовый Claude CALL. Все три done_when T5 ждут
исполнения и binding fresh G5; гарантии P§30/§40 по байтам не объявляются PASS.

## assumptions

Владелец: «Реализация здесь, проверки в Claude Code». Примеры только в тестах
разработки, вне установленного продукта и его данных. BEACON выдуман;
comparison не вводит реального мониторинга. Оба assessment сохраняются и
возвращают observe согласно PLAN. Четыре действия — ограниченный показ правила,
не гарантия бесконечного роста контекста: общие бюджеты/лимиты Core действуют.

## cuts

Новых cuts нет. Проверки переданы по выбору владельца, не признаны PASS.
Обе формулировки P§30/§40 сохранены; скрытые обходы должен опровергать fresh review.
W15/W16 без изменения, W17/W18/W20 ждут evidence; W19/T6 и T7 не исполнялись.
M1 не закрыта, M0 partial. Нет product push/merge, real data, новых зависимостей,
внешних прав, расписаний или нового интерфейса.

## cost

Одно ограниченное приращение внешнего тестового пакета. Общие операции записи
и контекста взяты из T4; новая версия установленного продукта не требуется.
Проверки исполняются владельцем в Claude Code. Токены/денежная стоимость не измерялись.

## manual-acceptance

T5 pending. Приёмка первого процесса не переносится на второй. После проверок
владелец увидит конечный KITE, четыре результата BEACON и следующий готовый раунд
на одной версии Core, плюс конкретные найденные ограничения.

## next

solmax

Передать exact candidate и готовый текст для свежей проверки в Claude Code.
FAIL → автору raw/воспроизведение; PASS → HOME evidence для review.
Root T5 открыт; закрытие Direction и запуск T6 здесь не заявлены.

END_OF_FILE: RESULT.md

# Core → DBOS → Pi: пакет стабилизации после приёмки Stage 6

## Основание и предел

Владелец принял Stage 6 в согласованном объёме на
`c8a546485e756afc2b0c5c99360e9ea2a42ae84d`; отдельные записи:
`STAGE6-PASS4-PACKAGE3-REVIEW.md` и `STAGE6-ACCEPTANCE.md`. Этот пакет
расследует только прежние `database is locked` и `rpc_transport`.
Спецификация осталась с SHA-256
`1DDCBF9DBFD58426781F61A67A170D3CE85FCD2BA27B17549773ED3356F9428D`.
Исходный кодовый пакет зафиксирован чистым коммитом
`cb569fce96091d716fa1753f1f4d7f401473e41a`; исправление после
независимого review — чистым кодовым коммитом
`dc6414cd1705c64a7761f980576704fbff705af2` той же ветки
`claude/pensive-gates-47w6z7`.

## SQLite: установленный класс блокировки и граница вывода

Исторический отказ был в Core при `_record_stop → read_execution →
_space_info → PRAGMA application_id`. Он не был отказом холодной миграции
отдельной executor SQLite DBOS. `read_execution` последовательно открывает
несколько коротких Core транзакций; `space_connection` закрывает handle в
`finally`. Чтение делает `BEGIN` с отложенным получением read-lock, поэтому
`PRAGMA application_id` — первый запрос, который может встретить занятый WAL.
Активный Pi runner держит `managed_pi_session_lock`; обслуживание использует
исключающий `managed_pi_lock`. DBOS работает с отдельным `executor.sqlite3`.

На Windows с закреплённым SQLite **3.53.3** управляемый барьер воспроизвёл
естественное расписание без искусственного `EXCLUSIVE`: после commit
**175145352 байт WAL** последний writer handle начал `close`/checkpoint;
читатель открыл транзакцию через **5 мс** и на первом
`PRAGMA application_id` получил `SQLITE_BUSY: database is locked` за
**347,001 мс**, пока закрытие writer занимало **460,282 мс**. При задержке
**20 мс** соседняя проба завершила закрытие за **359,246 мс** и чтение
прошло. Вывод о владельце относится к этому контролируемому расписанию:
владелец блокировки — закрывающийся последний WAL handle. Такой случай
предусмотрен [описанием WAL SQLite](https://www.sqlite.org/wal.html#sometimes_queries_return_sqlite_busy_in_wal_mode).
Сохранённая трасса: `_scratch/stabilization-wal-close-pinned.log`.

Исторический журнал не записал другой процесс/handle, время закрытия WAL
и extended SQLite code. Поэтому **не установлено**, что именно это
расписание вызвало прежний отказ; прежняя инъекция искусственного
`EXCLUSIVE` не выдаётся за такое доказательство. Подтверждён отдельный
дефект владения handle: если `_configure` отказывал, `_connect` прежде
выходил без `close`; теперь он закрывает соединение перед отказом.

Исправление для подтверждённого WAL-класса ограничено первым read-only
`PRAGMA application_id`: три попытки с прежним SQLite busy timeout и
короткой паузой. Другие запросы, write-транзакции и общие таймауты не
изменены. Ошибка хранит фазу (`identity`) и имя SQLite error; устойчивый
lock остаётся `storage`, stop не записывается как успех. Регрессии
проверяют одноразовый и устойчивый `SQLITE_BUSY` именно в `_record_stop`,
неизменённое назначение при отказе и закрытие handle при ошибке настройки.

## RPC: установленная граница и неизвестная причина выхода

Сохранённый `_scratch/fix-3.10-stage6.log` показывает отказ при B в
`_rpc_line`, а также `ConnectionResetError` при ответе loopback Bridge.
Прежний код объединял EOF, обрезанную и слишком длинную строку в одно
`rpc_transport` и отправлял stderr Pi в `DEVNULL`; exit code и события
Pi не сохранялись. Чтение старого одноразового Core space показывает
последовательность B: `claim_attempt_launch` в **14:12:12 UTC**,
`prepare_invocation` в **14:12:13**, stop в **14:12:16**. Состояние
вызова осталось `prepared`, операций `admit_invocation` и
`send_invocation` для B нет. Extension вызывает provider `fetch` только
после записанного Core `send_invocation`; счёт localhost HTTP в том
упавшем прогоне не сохранился. По этому основанию отправка B не
подтверждена, а причина выхода Pi всё ещё **не установлена**.

Разделены EOF (с текущим exit code), превышение лимита строки, строка
без newline, неверный JSON и неверный тип события. У `_rpc_line` нет
собственного таймаута, значит его старый немедленный отказ не был
истечением host RPC deadline; provider имеет отдельный timeout.
Ограниченный stderr Pi теперь читается без риска заполнить pipe.
При явном `ZARATUSTRA_RPC_DIAGNOSTICS=1` host пишет одну JSON-запись
на Attempt: committed claim, метаданные RPC-событий без их payload,
ошибку Core monitor, exit до/после host stop, хвост stderr до **16 KiB**,
Core invocation statuses и held units. Это диагностический режим;
строка stderr может содержать данные и потому не включается в обычный
журнал. Ошибка чтения Core monitor по-прежнему останавливает Pi безопасно,
но теперь называется отдельно. Выход процесса, сбой загрузки runtime
и monitor stop остаются конкурирующими гипотезами старого B: без его
stderr/exit/event trace одну выбрать нельзя. `line_limit`/protocol error
также не были различимы старой ошибкой. DBOS migration не объясняет
сохранённую границу B после launch claim.

Регрессия с синтетическим runtime exit **17** после claim сохранила stderr,
получила адресный EOF и не запустила второй Pi process при повторной
доставке. Низкоуровневые регрессии различают EOF, line limit,
обрезанную строку, JSON и event type. Новый живой checkout A/B/P и
установленный wheel дали по **3 localhost HTTP** в одном пространстве;
при продолжении B и P trace сохранил prompt acceptance, RPC events,
`answered` invocation и held **0**. Это успешные сравнительные пробы,
не исправление неизвестной исторической причины.

## Безопасный отказ и фактические проверки

Один повтор Stage 5 аварийной матрицы на том же assigned адаптере прошёл
семь групп. Смерть host после claim: **0 HTTP**, `unknown`, конфликтный
ресурс отказал `resource_busy`, независимый Attempt сохранился.
Потерянный ответ после отправки: **1 HTTP** до и **1** после restart,
invocation/assignment `unknown`, held **1000**, ресурс занят; поздний
результат не публикуется. Второй HTTP автоматически не отправлялся.
Отчёт: `_scratch/stabilization-stage5-faults/report.json`.

Собственный scoped Windows gate четырёх файлов: **42 passed**, format,
Ruff, strict mypy, **21/21** контракт, sdist/wheel; затем отдельная
регрессия handle: **8 passed** для `test_space.py`. Полный Windows
`uv run --locked python -m tools.check --deliver` на чистом кодовом
`cb569fc`: **723 passed за 488,01 с**, те же native gate stages и report
structure; журнал `_scratch/stabilization-deliver-cb569fc.log`.

`tools.probe_install_stage6 --parent-execution` собрал и установил wheel
точного чистого `cb569fc` во внешний venv: SHA-256
`FEF4D89071E8A856EF71096D70D1B410BDB8D13A1ED435666CA8F1CD9A66B492`,
`source_tree_dirty=false`, `outside_checkout=true`, Python 3.13.7,
SQLite 3.53.3, Core/DBOS/Pi extension из `site-packages`. A/B/P дали
**1→2→3 HTTP**, затем backup, карантин, удаление и replay независимой B
остались на **3**; DBOS workflows/Pi homes **3/3→2/2→1/1→0/0**.
Трассы: `_scratch/stabilization-installed-cb569fc/report.json` и
`installed-trial.log` (три RPC diagnostic записи). Checkout trace:
`_scratch/stabilization-checkout-fresh/report.json` и одноимённый log.
Все эти проверки — собственные проверки данного пакета.

## Независимое review и адресное исправление

Отдельное независимое Windows review итогового `6789b98` вернуло **FAIL**:
корректное RPC-событие с `type` длиной **1 МиБ** прошло `_rpc_line`,
после чего `event_type` попал в диагностическую запись длиной
**1 049 279 символов**. Лимит 128 событий не ограничивал байты записи.
Проверенный checkout остался чистым. Отчёт:
`../independent-stabilization-review-archive-6789b98-20260926/READONLY-REVIEW.md`
(отдельный каталог рядом с рабочим checkout). Рецензент независимо получил
**16 PASS** в адресном Windows прогоне; ещё два сценария не стартовали из-за
ACL временной папки pytest. Его localhost A/B/P дал **3 HTTP**, семь групп
аварийных отказов сохранили post-send `unknown`, резерв **1000** и **1→1 HTTP**
после restart. Полный gate **723** и wheel исходного пакета — собственные
проверки реализации, а не результаты рецензента.

В `dc6414c` сохранение события ограничено известными типами Pi и короткими
ASCII-метками; неожиданный тип и прочий текст события заменяются явным
`<omitted>`. Общий след событий ограничен **128 записями / 16 KiB** с
маркером `trace_truncated`; кодированная диагностическая строка ограничена
**128 KiB**. При достижении предела сначала
опускается stderr, затем след и список invocation с явными признаками
опущенных данных. Произвольные тексты ошибок Core и RPC больше не копируются
в запись: остаются код и классификация границы. Stderr по-прежнему выводится
только в явном диагностическом режиме и хранит максимум **16 KiB** входных
байтов. RPC-событие не добавляет свой payload в журнал. Исправление не
меняет отправку, Core/DBOS state или обработку исхода.

Новые wire-level регрессии провели строковый и объектный `type` на **1 МиБ**,
неизвестный короткий тип, ограничение числа/байтов событий и большие ошибки
через реальный путь диагностики. Собственный scoped Windows gate изменённых
файлов: **40 PASS**, Ruff, mypy, **21/21** контракт, sdist/wheel. Полный
Windows `uv run --locked python -m tools.check --deliver` на чистом кодовом
`dc6414c`: **728 PASS за 485,94 с**, format, Ruff, mypy, **21/21** контракт,
sdist/wheel и report structure; журнал
`_scratch/stabilization-deliver-dc6414c.log`. Wheel точного чистого
`dc6414c` установлен вне checkout, SHA-256
`F4AA8343CD82A541D737188F991E94245DA98BE24FE05B06BE06387B55876E20`:
Python 3.13.7, SQLite 3.53.3, Core/DBOS/Pi extension из `site-packages`,
`source_tree_dirty=false`, `outside_checkout=true`. Синтетический localhost
A/B/P дал **1→2→3 HTTP**; backup/restore/deletion и replay независимой B
не добавили отправок, DBOS workflows/Pi homes **3/3→2/2→1/1→0/0**.
Отчёт: `_scratch/stabilization-installed-dc6414c/report.json`.
Это проверки реализации после исправления. Пакет передаётся на повторное
общее независимое review; его результата этот документ не предрешает.

## Оставшиеся ограничения и следующий предметный этап

Исторический владелец Core SQLite lock и причина выхода Pi в прежнем B
неизвестны; новый trace сделает следующий такой отказ различимым, но
отсутствующее старое stderr восстановить нельзя. `stale_basis` внутри
`any` не менялся. Проверки не охватывают реального provider, платный API,
аппаратный отказ носителя, все Windows lock расписания и внешнее
exactly-once. Stage 6 принят в своём объёме, всё ядро и миграция
разработки не приняты. Из спецификации следующим предметным кандидатом
рекомендуется отдельный versioned **Binding** для адресной передачи
принятого результата между Activity; его реализация этим пакетом не
начинается. Исправленный пакет передаётся тому же независимому рецензенту
на повторное общее review.

END_OF_FILE

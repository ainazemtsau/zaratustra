# Stage 6, проход 4, пакет 3 — обслуживание и выпускной отчёт

## Статус и основание

Владелец разрешил только пакет 3 после отдельного закрытия технического
review пакета 2 на `8468fae0e90e8002bfd1d0189c872e43ac711d03`.
Атрибуция того review записана в `STAGE6-PASS4-PACKAGE2-REVIEW.md`:
**45 независимых профильных тестов**, внешний сценарий восстановления,
**три независимые живые пробы**; полный gate **700 тестов** принадлежал
реализации. Эти проверки не объявляются проверками пакета 3.

Этот пакет работает с фиктивными данными, локальным DBOS 3.0.0, обычным
Pi 0.87.0 и localhost provider. Исходный чистый checkout был на
`8468fae0e90e8002bfd1d0189c872e43ac711d03`, ветка
`claude/pensive-gates-47w6z7`; STOP/STEER отсутствовали. Спецификация
совпала с SHA-256
`1DDCBF9DBFD58426781F61A67A170D3CE85FCD2BA27B17549773ED3356F9428D`.
Один ограниченный независимый read-only setup smoke подтвердил это и
доступность `uv`; он не является техническим review пакета.

## Матрица прерываний backup

`tests/zaratustra/foundation/test_pass4_maintenance.py` создаёт отдельное
schema 8 пространство на каждый шаг, закрывает все свои SQLite handles,
добавляет синтетические Core, executor SQLite и Pi RPC файлы. Дочерний
Python-процесс получает `os._exit` только после названной операции; тест
сверяет его **фактический exit code**, каталог пакета, marker, inventory,
публичный `load_backup`/`restore_backup`, исходный receipt и replay. Перед
каждым прерыванием `completed_backups=0`, исходный Artifact и receipt
читались. После каждой аварии новый обычный вызов создавал полный format 2
пакет schema 8, сохранял исходный replay, проверял SHA-256 Core/DBOS/Pi,
переводил restore в эпоху 2. На всех шагах HTTP **0**: провайдер не
запускался, и тест не делает заявлений о внешней сети.

| Фактически достигнутая точка (`exit`) | Пакет после смерти процесса | `load`/`restore` старого пакета | Новый пакет и replay | Предел |
| --- | --- | --- | --- | --- |
| После входа в exclusive maintenance boundary, до Core snapshot (`70`) | Нет `.partial`, inventory planned | Отказ `invalid_backup`, destination пуст | Format 2 и тот же receipt | Управляемый exit до снимка, не физический отказ диска |
| После Core snapshot и SHA (`71`) | Только скрытый `.partial` | Отказ, destination пуст | То же | Не проверяет все страницы SQLite при аппаратном сбое |
| После DBOS SQLite snapshot и SHA (`72`) | Скрытый `.partial` | Отказ, destination пуст | То же | Технический файл синтетический, не запущенный DBOS workflow |
| После копии Pi RPC файла (`73`) | Скрытый `.partial` | Отказ, destination пуст | То же | Синтетический Pi файл, не реальная сессия модели |
| После записи format 2 manifest (`74`) | Скрытый `.partial` с manifest | Отказ, destination пуст | То же | Commit inventory ещё не был достигнут |
| После rename (`75`) | Видимое имя без marker | Отказ, destination пуст | То же | Видимое имя само не объявляет публикацию |
| После marker (`76`) | Видимое имя и marker, inventory planned | Отказ, destination пуст | То же | Требуется согласованный inventory commit |
| После inventory commit, до ответа API (`77`) | Видимое имя, marker, inventory complete | Полный пакет читается | Другой новый пакет; старый уже годен, replay тот же | Exit следует за commit; не моделирует повреждение носителя |

Для опубликованного пакета тест отдельно менял байт в **каждом** из Core
SQLite, executor SQLite и Pi RPC файла в изолированной копии. Все три
`load_backup`/`restore_backup` отказали `invalid_backup`, destination
остался пуст. Manifest, его marker SHA, состав файлов, format 2, schema 8,
epoch и три file SHA проверены у полного пакета. Никакая несработавшая
инъекция не помечена PASS: все восемь завершились ожидаемым `os._exit`.
Предметный текст не записывался напрямую в Core SQLite.

## Карантинный restore и неизвестный исход

В отдельном schema 8 случае собственная Attempt составного родителя
имела `assignment=assigned`, записанную Core отправку
`invocation=sent`, удержание **5** единиц и новый managed executor/Pi home.
Полный backup сохранил технические файлы. Restore создал новую эпоху **2**
и только `executor-restored.sqlite3`/`pi-rpc-home-restored`; старый
`LocalAuthority` отвергнут `permission_denied` и на чтении, и на попытке
replay. После явного `RecoverRequest` новый процесс прочёл тот же
assignment receipt; assignment стал `interrupted`, invocation — `unknown`,
удержание осталось **5**. Здесь `SendInvocationRequest` отмечает локальную
границу Core, но HTTP клиент не запускался (**0 HTTP**); этот случай не
доказывает, что внешний provider получил запрос.

В живом schema 8 сценарии `tools.probe_stage6_rpc --parent-execution`
localhost provider получил A/B/P **1→2→3 HTTP**. После backup и restore
попытка старого обычного `run_assigned` с прежней властью на карантинном
пространстве получила `permission_denied` до создания активного executor
SQLite; HTTP осталось **3**. Явный recover сохранил собственный
`ParentOutputProof`, исторический статус и Method pin; сам restore не
возобновил Attempt. Это проверка старого runner на восстановленной копии,
а не обещание отменить уже отправленный внешний вызов.

## Последовательное удаление и санация

Живой schema 8 сценарий опубликовал выходы A, B и собственный выход P,
отдельно подтвердил обязательство и принял P. После удаления каждой
зависимой пары Work/Artifact `complete_assigned_deletions` оставил
`pending=0`; новый Python-процесс через публичный Core каждый раз прочёл
schema **8**, epoch **1** и `pending_deletions=0`. После A число настоящих
DBOS workflows/Pi homes стало **2/2**, после B **1/1**, после P **0/0**;
localhost HTTP всё время **3**. Точный receipt/replay назначения независимой
ветви B сохранился после удаления A. Старый managed backup удалён как
загрязнённый; новый не содержит уникальный маркер собственного результата.
Удаление Method перед родителем отказало `method_in_use`, после удаления P
прошло с полной санацией.

Core-регрессия `test_nested_own_attempt_full_grandchild_to_parent_acceptance`
проводит G → N → P через собственную Attempt N и принятые G/N/P. Она
удаляет уникальный Artifact результата G, затем G, Artifact собственного
результата N, N, независимый открытый узел `anchor`, P, Method N и Method
P, вызывая `complete_deletions` после каждого шага. Между первым и
следующими удалениями новый процесс подтверждает, что независимый вне
дерева Work и его receipt сохранены. Replay этого receipt проверяется
после каждого удаления. Старый backup исчез, новый backup и закрытая
Core SQLite не содержат уникальный маркер G. Этот Core-сценарий не
создаёт DBOS/Pi; их физическая санация проверена живым случаем выше.

| Достигнутая граница | До → после и чтение новым процессом | HTTP | Receipt/replay | Предел |
| --- | --- | --- | --- | --- |
| Карантин после Core `sent` собственного P | `assigned/sent`, held 5 → epoch 2, после recover `interrupted/unknown`, held 5; новый процесс прочёл оба адреса | 0, HTTP клиент не запускался | Старый authority отказан; прежний assignment receipt читается в новом epoch | Локальная запись send не подтверждает получение provider |
| Старый живой runner на restore A/B/P | 3 answered вызова → карантин без активного executor, `permission_denied` до DBOS launch | 3→3 | История и ParentOutputProof читаются после явного recover; второй runner не доставлен | Не отменяет уже бывший внешний вызов |
| Удаление A и его Artifact | 3 workflows/homes → 2/2, `pending=0` в новом процессе | 3→3 | Receipt назначения B и его точный replay сохранены | B независим в этом плане; не все возможные связи независимы |
| Удаление B и его Artifact | 2/2 → 1/1, `pending=0` в новом процессе | 3→3 | В этой точке replay P отдельно не утверждается | Принятый P теряет зависимые основания адресно |
| Удаление P и собственного Artifact | 1/1 → 0/0, `pending=0` в новом процессе | 3→3 | Receipt удалённых адресов не заявлен сохраняемым | Проверяются только managed Core/DBOS/Pi файлы |
| Удаление Method после P | До P `method_in_use` → после P удаление и санация прошли | 3→3 | Независимый B был проверен ранее; deleted Method не replayable | Не проверяет Method в чужом активном плане |
| G → N → P, с остановкой между вызовами обслуживания | Сначала Artifact G и старый backup исчезли; новый процесс подтвердил независимый Work; затем G, Artifact N, N, anchor, P, Method N/P и чистый новый backup | 0, Core-only без provider | Receipt/replay вне дерева сохранялся после каждого шага | Нет `os._exit` внутри технического cleanup этого дерева |

Прерывания внутри `complete_deletions` по обе стороны compaction и
повтор после них, а также адресная санация Pi/DBOS при межпоточной
вставке другой deletion job проверяются сохранёнными регрессиями
`test_maintenance.py` и `test_assigned.py` в полном gate. Между
предметными удалениями G/N/P прерывалась последовательность вызовов,
но отдельный `os._exit` технического cleanup в этом пакете не ставился;
это предел данной композиционной пробы.

## Проверки и атрибуция

Это собственные проверки сеанса реализации пакета 3, не независимое
review. Сохранённые probes прошли отдельно: Stage 5 RPC **2 HTTP**,
Stage 5 fault probe **7 групп**, Stage 6 child RPC **3 HTTP**, pass 3
**4 HTTP**, schema 8 A/B/P **3 HTTP**. Журналы и одноразовые пространства
находятся в `_scratch/pass4-package3-*`; итоговая schema 8 проба —
`_scratch/pass4-package3-parent-final.log`, raw матрица **10 PASS** —
`_scratch/pass4-package3-matrix.log`, новые fault-тесты —
`test_pass4_maintenance.py`. Scoped gate изменённых файлов дал **20 PASS**,
типы, Ruff, 21 контракт и сборки; это обратная связь, не полный выпускной
gate.

Первый собственный полный Windows
`uv run --locked python -m tools.check --deliver` на рабочем дереве
реализации дал **709 PASS за 521,62 с**, format, Ruff, strict mypy,
**21/21** импортный контракт, sdist/wheel и report structure; журнал
`_scratch/pass4-package3-deliver.log`. После него тестовое ожидание
удержания переведено с конкретной величины на равенство до/после.

Код и матрица зафиксированы на точном чистом коммите
`455def17488d7ca8e54624133875f7843e5cc5a4`. На нём полный
Windows `tools.check --deliver` повторён: **709 PASS за 581,82 с**,
format, Ruff, strict mypy, **21/21** импортный контракт, sdist/wheel и
report structure; журнал `_scratch/pass4-package3-deliver-clean-455def1.log`.
`tools.probe_install_stage6` перед сборкой отвергает dirty tree; его
отчёт `_scratch/pass4-package3-installed-455def1/report.json` записал
`source_tree_dirty=false`, тот же `source_commit`, wheel SHA-256
`21776AE328929113EF8F069E8CF7C19C64B7CEFB93D90DB0695F33B90887AB6F`,
изолированный Python 3.13.7 / SQLite 3.53.3 и `foundation`, DBOS,
Pi extension из внешнего `site-packages`. Установленный schema 8 A/B/P
сценарий дал **3 HTTP**, старому runner отказано в карантине, после
удалений DBOS/Pi **2/2→1/1→0/0**, затем Method удалён. Полный журнал:
`_scratch/pass4-package3-installed-455def1.log`. Последующий коммит
этого отчёта меняет только документацию, не проверенный код.

## Открытые наблюдения и пределы

`database is locked` и `rpc_transport` остаются **OPEN**. Пакет 3 не
установил причины прежних отказов, успешные новые probes их не закрывают.
Управляемые failpoints, фиктивные данные и localhost не доказывают все
межпроцессные расписания, exactly-once во внешней сети, семантическую
правильность модели или сохранность аппаратного носителя. Уже вынесенные
за managed space копии не санируются. Подтверждённого дефекта продукта в
достигнутых окнах пакета 3 пока нет; ошибочные ожидания двух ранних
тестовых прогонов были исправлены по фактическим публичным состояниям
(`.partial` до создания и `interrupted`/`unknown` после recover).

Результат останавливается перед одним общим независимым review. Приёмка
schema 7/8, прохода 3/4 и Stage 6, следующий этап, реальные модели,
миграция разработки и PR не начаты.

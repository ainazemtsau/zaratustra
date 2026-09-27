# Установленный локальный путь

Поддержанная проверенная среда этого пакета: Windows, Python 3.13.7,
Node 22.19.0, SQLite 3.53.3 и обычный Pi 0.87.0. `zara-core setup`
копирует проверенный SQLite DLL и Pi в каталог конфигурации. Если локальные
копии не переданы, он получает закреплённые архив SQLite и npm-пакеты Pi,
проверяет версию/хеш до сохранения конфигурации. Путь к разработческому
checkout для обычного запуска не нужен.

1. Создать отдельные пустое пространство Core, каталог рабочего ресурса и
   каталог установки. Установить собранный wheel в новое окружение Python
   3.13.7: `uv venv --python 3.13.7 <install>/venv`, затем
   `uv pip install --python <install>/venv/Scripts/python.exe <wheel>`.
2. Вызвать `<install>/venv/Scripts/zara-core.exe setup --config <install>/config.json
   --space <space> --workspace <work> --new-space --provider-profile local-completions
   --provider-base-url <local-http-url> --provider-id <id> --model-id <id>
   --context-window <units> --max-tokens <units> --limit-units <units>
   --reserve-units <units>` и подтвердить `SETUP`. Для Codex SSE выбрать
   `codex-sse`, `openai-codex` и конкретную модель; доступ к provider
   настраивается штатным Pi. Существующее пространство выбирают без
   `--new-space`; его схема не меняется от одного выбора.
   Для назначенного Sleep `--reserve-units` должен помещаться в оставшийся
   лимит каждого вызова и рабочего ресурса. Например, при Sleep и ресурсах
   по 1000 единиц и двух ответах по 50 резерв 100 допустим; резерв 1000
   остановит второй вызов до отправки provider.
   Для второго рабочего ресурса сохраните новый конфиг в отдельном каталоге
   установки. На Windows попытка создать его рядом с уже работающим конфигом
   может столкнуться с блокировкой копируемого SQLite DLL (`WinError 5`).
3. `zara-core verify --config <config>` показывает точную версию программы,
   пространство, схему, epoch и Pi. `zara-core run --config <config>`
   запускает обычный Pi после явного `CONNECT`. Выбор Activity/Work возможен
   через `/zara-work` либо адресами запуска. `zara-core assign --config
   <config> --work-id <id> --resource-id <id>` запускает адресный Attempt
   после `ASSIGN`; `/zara-answer` сохраняет ответ ожидающему Work.
4. Для старой схемы `zara-core run/assign` останавливается. Отдельный
   `zara-core upgrade --config <config>` после `UPGRADE` сохраняет проверенный
   backup и только затем выполняет явные миграции. Смена версии самого wheel
   делается отдельно; до запуска проверить `zara-core verify` и совместимость
   схемы. Возврат программы допустим лишь к версии, умеющей читать текущую
   схему; восстановление старого backup не стирает новые события незаметно.
5. `zara-core inspect --config <config> --kind <space|activity|work|development|execution|receipt|application> --id <uuid>`
   читает точный адрес без модели (`space` не требует `--id`).
   `zara-core pulse --config <config>` даёт read-only отчёт. Сохранённый JSON
   можно передать как `--previous-report` для следующего checkpoint.
   `zara-core repair` показывает Pulse, адреса неизвестных внешних исходов
   и открытых ожиданий; при отдельном `DELETE` завершает штатное управляемое
   удаление. Неизвестный ответ не превращается в успех автоматически.
   `backup`, `restore` в новый каталог,
   `recover` с новым epoch и `select` в новый файл конфигурации — отдельные
   шаги. Выбор более старой схемы/истории или копии без исходных операций
   запрещён.

## Предметный рабочий путь

В обычном Pi `zara_activity` показывает список и точное состояние Activity,
а новую Activity создаёт только отдельным подтверждённым действием;
`zara_development` создаёт Method и Work, в том числе составной Work с
отдельными детьми. `zara_grant` выдаёт явно подтверждённое адресное право;
`zara_memory` сохраняет и читает первичные источники, а `zara_binding`
обслуживает передачу результата. Создание Activity само по себе не запускает
Sleep и не создаёт Work или готовую доску задач. Выбранная рабочая папка становится
ресурсом через `create_resource`; `zara-core assign` выдаёт адресный Attempt.
`zara_development(mode=list)` перечисляет записи Sleep/Change и не служит
списком Activity; ответ о текущих Activity берут через `zara_activity(mode=list)`.
Назначенный Pi использует нативные `read/write/edit/bash` вместе с
`zara_development` и `zara_memory`. Пауза с вопросом переживает закрытие Pi:
`/zara-answer` записывает ответ, затем назначение продолжается. Output
сохраняется и связывается с Work отдельно от `/zara-accept`; отрицательный
итог оформляется `close_work`, не подменяется отсутствием ответа.

`zara_sleep` по отдельному запросу создаёт исходный Method и составной Sleep Work. Ограниченное
`list_sleep_sources` выдаёт страницы до зафиксированной границы; каждую позицию
сохраняют через ревизию Sleep. Два дочерних Work получают свои Attempts и
ресурс, доставленные Source отмечаются только после наблюдаемого manifest,
разбор сохраняется в памяти, остаток фиксируется явно. Результаты детей и
родителя принимаются отдельными действиями.

Для существенного изменения Pi сохраняет `ChangeCandidate` с точной целью,
ValidationPlan и основанными на Source результатами, затем действующий
`ChangeDecision` с областью и отдельным Grant. `apply_candidate` применяет
Method/Binding пакет сразу; ProgramChange с полным build ArtifactRef,
SHA-256, resource и relative_path получает `prepared`. Команда
`zara-core change-install --config <config> --application-id <id>` после
`INSTALL` пишет только проверенный файл выбранного ресурса и подтверждает
фактические байты в Core. `change-stop` требует `--reason`,
`--started-works`, `--external-effects` и подтверждение `STOP`;
`change-restore` требует `--reason`, `--data-restoration`,
`--external-effects` и `RESTORE`. История применения не стирается;
несовпадение файла или нового состояния останавливает возврат. Для прежней
версии без текущего допуска результат остаётся `partial`.

Типизированный `ActivityChange` в том же Candidate/Plan/Decision применяет
существенный split/merge и допускает точный stop/restore. Небольшую поправку
принадлежности можно выполнить напрямую `reorganize_activities`. Историческое
происхождение остаётся адресуемым. Текст `binding_disposition`,
`decision_disposition`, `grant_disposition` фиксирует рассмотрение, но не
копирует права или Binding; нужное изменение каждого делается обычной
адресной операцией. Новые Work не назначаются в завершённую Activity.

Этот runbook описывает инженерно проверенный локальный путь. Он не записывает
приёмку всего ядра за владельца и не обещает смысловую пользу модели.

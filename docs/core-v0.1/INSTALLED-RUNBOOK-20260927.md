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
   `zara-core repair` показывает адреса и при отдельном `DELETE` завершает
   штатное управляемое удаление. `backup`, `restore` в новый каталог,
   `recover` с новым epoch и `select` в новый файл конфигурации — отдельные
   шаги. Выбор более старой схемы/истории или копии без исходных операций
   запрещён.

Граница: текущий ChangeCandidate умеет Method и Binding, но не адресуемую
установку программы или составной Change; перестройка Activity также ещё не
выполнена. Этот runbook не объявляет весь первый выпуск принятым.

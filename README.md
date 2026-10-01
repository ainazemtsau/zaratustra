# Zaratustra

Актуальная основа продукта — **Core v0.1 / Activity**. Она включает Activity,
Work, Method, сохраняемые результаты, Memory, Sleep, изменение и восстановление
работы. Предметные данные хранит один SQLite Core; обычный проверенный локальный
интерфейс — Pi 0.87.0 через `zara-core`.

История прежнего main с Home/file-first и история нового Core объединены.
Почему они разошлись, какую версию выбрали и что осталось подключить, записано в
[решении о консолидации](docs/core-v0.1/CONSOLIDATION-20261001.md).
Прежние коммиты и ветка `codex/home-line-retained-20261001` сохраняются.
Старые инструкции `zara`/`zara-agent`, планы Home и навыки прежней реализации
не служат инструкцией запуска текущего Core.

## Установка и работа

Поддержанная проверенная среда: Windows, Python 3.13.7, Node 22.19.0,
SQLite 3.53.3 и обычный Pi 0.87.0. Программа, её конфигурация, предметное
пространство и рабочая папка выбираются отдельно.

Порядок установки wheel, выбора пространства, настройки провайдера и запуска:
[установленный рабочий путь](docs/core-v0.1/INSTALLED-RUNBOOK-20260927.md).
Для существующей установки:

```powershell
<install>/venv/Scripts/zara-core.exe verify --config <install>/config.json
<install>/venv/Scripts/zara-core.exe run --config <install>/config.json
```

Используйте настоящие выбранные пути. `verify` проверяет установленную версию,
пространство и runtime; `run` запускает Pi после `CONNECT`.
`zara_activity` показывает Activity, `zara_development` работает с Method/Work
и Sleep/Change, `zara_memory` — с источниками и памятью. Продолжение назначенной
работы и вопросы описаны в runbook. Обновление программы не является разрешением
перенести или изменить личные данные.

ChatGPT, телефон и актуальные отдельные подключения Codex/Claude ещё требуют
адаптации и реальной проверки. Старые инструкции ChatGPT → GitHub → Home не
подключают новое ядро. Следующий пользовательский сценарий — Health с одним
состоянием для ChatGPT и локального агента.

## Разработка

Начать с [AGENTS.md](AGENTS.md),
[утверждённой спецификации](docs/core-v0.1/Zaratustra_Core_Specification_v0.1.md)
и [политики выпуска](docs/core-v0.1/DELIVERY-POLICY-20260926.md).
Проверки и ограничения последних изменений находятся в [RESULT.md](RESULT.md).
Проверка для целого пакета: `uv run --locked python -m tools.check --deliver`;
закреплённый SQLite runtime передаётся через `ZARATUSTRA_SQLITE_DLL`.

END_OF_FILE: README.md

# Проверки T6 в отдельном Claude Code

Прочитать текущие AGENTS.md, src/zaratustra/process_packs/AGENTS.md, tools/AGENTS.md,
validation.config (PROBA36), STOP/STEER, CALL.md и PLAN.md рядом. Команды ниже
назначены Claude Code; автор их не исполнял. Exact source закреплён в handoff.
Создать новую reviewer worktree от кандидата; старые папки и ветки не очищать.
Команды выполняются из reviewer checkout, имена scratch новые:

```powershell
$ErrorActionPreference = 'Stop'
$env:PYTHONUTF8 = '1'
$env:UV_CACHE_DIR = Join-Path (Get-Location) '_scratch/environment/uv-cache'
uv sync --locked
if ($LASTEXITCODE -ne 0) { throw 'Setup failed' }
New-Item -ItemType Directory -Path '_scratch/t6-review-01' -ErrorAction Stop
$env:PYTEST_ADDOPTS = '--basetemp=_scratch/t6-review-01/pytest'
uv run --locked python -m tools.check --deliver 2>&1 | Tee-Object '_scratch/t6-review-01/native.txt'
if ($LASTEXITCODE -ne 0) { throw 'Native failed; retain raw and return finding' }
uv run --locked python -m tools.probe_overview --output '_scratch/t6-review-01/overview' 2>&1 | Tee-Object '_scratch/t6-review-01/overview.txt'
if ($LASTEXITCODE -ne 0) { throw 'Overview failed; retain raw and return finding' }
```

Managed Python 3.13.7; tool/deps из uv.lock. Native FAIL не означает PASS остальных
проверок. Прежние числа тестов относятся к прежним source: фактическое новое
число берётся из вывода, а не подставляется. Максимум три повтора одного failed gate. Не исправлять
продукт или tests ради PASS; результат возвращается автору. Собственные read-only
probes допустимы с явным статусом исполнения.

Показ владельцу: файл `_scratch/t6-review-01/overview/overview.txt` — это и есть
общий обзор двух процессов в человекочитаемом виде; `overview.json` — те же данные,
`overview.digest.json` — SHA-256 точных байтов.

## Наблюдаемые результаты

- Один registry: fictional.lot 1.0.0 и fictional.signal 1.0.0. Сначала полностью
  отрабатывает прежний парный сценарий T5, затем обзор только читает его результат.
- Обзор состоит из двух строк. Каждая строка — дословный ответ того же
  `read_capabilities`: `signal-row-direct.json` и `lot-row-direct.json` совпадают
  с вложенными `response`, а `response_sha256` — с их байтами.
- У каждой строки собственные workspace, process и state_revision; общей revision
  и общей транзакции в envelope нет. Обе строки описаны одними и теми же семью
  именами и четырьмя состояниями ok/empty/denied/unavailable.
- Общему потребителю не нужны инструкции пакетов: он даёт путь, ProcessQuery и
  подтверждение по каждой строке и один registry. Идентичности берутся из
  публичного Core (`read_records`), не из предметных правил.
- Изоляция контекста: строка signal с отдельно подтверждённым ContextQuery имеет
  context ok; строка lot без выбранной Work — not_requested. Содержимое чужой
  строки не появляется. `overview-metadata-only` показывает ту же строку без
  контекста как not_requested при сохранённых видимых требованиях.
- Контроли: `overview-foreign-caller` (чужое подтверждение) даёт denied строку без
  value/count; `overview-stale-row` — conflict; `overview-missing-pack` —
  missing_pack. В каждом случае соседняя строка остаётся полной. Код отказа виден
  и в проекции строки, и в тексте как `state:code`.
- Отказанная строка в тексте печатает `requested_revision=` — число, которое
  запросил потребитель, потому что revision workspace она не читала. Строка с
  ответом печатает `revision=` из собственного envelope. У успешной строки Core
  требует равенства этих чисел, поэтому её вид не меняется.
- Обе workspace побайтно неизменны до и после всех обзоров:
  `workspaces-before-overview.json` равен `workspaces-after-overview.json`.
- Пустой законный ответ остаётся `empty` с count 0 и не превращается в
  unavailable; скрытая Work не появляется ни в одной строке.
- `overview-forged-status` — контроль после G5-T6-02: пакет возвращает статус с
  переносами строк, поддельной третьей строкой обзора, поддельными counts,
  противоречащим заявлением и ESC-последовательностью. В `.txt` по-прежнему
  ровно две строки обзора, строки с «3.» нет, подделка свёрнута внутрь одной
  строки статуса, ESC отсутствует. В `.json` значение статуса сохранено дословно.

## Evidence и refutation

Сохранить Git commits/status, runtime versions, полный diff от c4b8aea4, точные
байты обзора и его SHA-256, текстовый вид, обе строки запросов и подтверждений,
контрольные обзоры, оба direct-ответа и footprints обеих workspace.
Сверить неизменность по docs/m1-overview/baseline-ids.json: tree src/zaratustra/core
и обоих fictional пакетов, blobs capabilities/capability_models/lifecycle/runner.
Хеши retained files считать от committed Git blobs: Tee-Object пишет CRLF,
Git хранит LF — это известная историческая ошибка G5-F01.

Fresh G5 ищет: обзор, который сам читает state в обход контракта; предметную
ветку или знание пакета внутри обзора; молчаливое превращение denied/unavailable
в пустоту; утечку скрытых Work, counts или чужого контекста; общий revision или
обещание межбазовой транзакции; запись в workspace при чтении; выдачу полномочий
из производного представления; текст пакета, управляющий разметкой вида.
Пустой Core diff — идентичность байтов, а не поведенческий PASS. Все три done_when проверяются отдельно; обе гарантии
P§30/§40 сохраняются. Непроверенное остаётся открытым. T7 и M1 не закрывать.
Отчёт возвращается владельцу и HOME.

END_OF_FILE: docs/m1-overview/REPRODUCE.md

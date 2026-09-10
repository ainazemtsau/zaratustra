# Проверки T5 в отдельном Claude Code

Прочитать текущие AGENTS.md, validation.config (PROBA36), STOP/STEER,
CALL.md и PLAN.md рядом. Команды ниже назначены Claude Code, автор их не исполнял.
Exact source закрепляется в handoff. Создать новую reviewer worktree от кандидата;
старые папки/ветки не очищать. Команды из reviewer checkout, новые имена scratch:

```powershell
$ErrorActionPreference = 'Stop'
$env:PYTHONUTF8 = '1'
$env:UV_CACHE_DIR = Join-Path (Get-Location) '_scratch/environment/uv-cache'
uv sync --locked
if ($LASTEXITCODE -ne 0) { throw 'Setup failed' }
New-Item -ItemType Directory -Path '_scratch/t5-review-01' -ErrorAction Stop
$env:PYTEST_ADDOPTS = '--basetemp=_scratch/t5-review-01/pytest'
uv run --locked python -m tools.check --deliver 2>&1 | Tee-Object '_scratch/t5-review-01/native.txt'
if ($LASTEXITCODE -ne 0) { throw 'Native failed; retain raw and return finding' }
uv run --locked python -m tools.probe_second_process --output '_scratch/t5-review-01/pair' 2>&1 | Tee-Object '_scratch/t5-review-01/pair.txt'
if ($LASTEXITCODE -ne 0) { throw 'Pair failed; retain raw and return finding' }
uv run --locked python -m tools.probe_second_install --output '_scratch/t5-review-01/install' 2>&1 | Tee-Object '_scratch/t5-review-01/install.txt'
if ($LASTEXITCODE -ne 0) { throw 'Installation failed; retain raw and return finding' }
```

Managed Python3.13.7; tool/deps из uv.lock. Native FAIL не означает PASS дальнейших
проверок. Независимые read-only проверки допустимы с явным статусом исполнения.
Не исправлять продукт/tests ради PASS; результат вернуть автору. Не заменять
новый retained probe старым tools.probe_install с удалением temporary directory.

## Наблюдаемые результаты

- Один registry: fictional.lot1.0.0 и fictional.signal1.0.0, exact bindings в state.
- KITE: прежние оба checks, exact basis disposition, два Results, отменённая
  unused continuation; release/revision19 и три прежних ожидаемых отказа.
- BEACON: steady → observe; changed → compare; comparison с текущим digest →
  observe; steady → observe. Четыре Results и следующая ready Work. Неверный сигнал,
  чужой digest и отсутствующий pack отвергнуты. Четыре — число действий сценария,
  не лимит правила; общие бюджеты/лимиты Core продолжают действовать.
- Manifest соседа неизменен в обе стороны; чужие query/confirmation не дают
  metadata/counts/content. Один registry не является общим разрешением.
- Selected metadata/context подтверждаются отдельно; скрытые Work Results не
  раскрываются, законные exact inherited grounds доступны выбранной Work.
- Каждый Result: input/request/authority/receipt/history, pre-Result snapshot;
  restore в новую папку и повтор exact request с новой path-bound confirmation
  дают тот же fingerprint/revision. Все неудачные attempts сохраняются.
- Wheel/sdist без fictional/test/tool namespaces. В чистом Python -I до внешнего
  подключения fixtures отсутствуют; init/migrate7 создаёт 0records/revision0.
  Потом оба сценария используют один wheel, все zaratustra modules из этой venv.

## Evidence и refutation

Сохранить Git commits/status, runtime versions, полный diff от 2df9b28 и b1e0853,
manifest Git blobs Core/process_packs/первых rules. Baseline ZIP сравнивается с
его собственным Git commit, не с изменённым host. Сохранить full raw, wheel/sdist,
inputs/outputs, state ZIP/manifests обоих процессов, own probes и их exact bytes.
Manifest retained files хешировать по committed Git blobs: pre-commit CRLF и
committed LF различаются, это известная историческая ошибка G5-F01.

Fresh G5 ищет скрытые предметные ветки, изменение основной семантики, ошибку
выделения host, ложную изоляцию, чужое основание, authority от pack, подмену wheel
исходниками и fictional данные при установке. Empty Core diff — идентичность
байтов, не поведенческий PASS. Все три done_when и W17/W18/W20 отдельно;
обе гарантии P§30/§40 сохраняются. Непроверенное остаётся открытым.
T6/renderer и T7/M1 не закрывать. Отчёт возвращается владельцу/HOME.

END_OF_FILE: docs/m1-second-process/REPRODUCE.md

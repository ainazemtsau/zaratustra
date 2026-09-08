# Work 6 — открыть актуальный ограниченный контекст

Версия 0.6.0, схема 5; migration для Work 6 не нужна. Только новые копии принятого
fictional Work 5. Чистый чат, пять фактов и пользовательский показ — Work 8.

## Сохранённые факты

Из checkout Work 6:

```powershell
Get-Content docs/work6/evidence/context-identity.json
Get-Content docs/work6/evidence/context-manifest.json
Get-Content docs/work6/evidence/console-checks.json
Get-Content docs/work6/evidence/hidden-checks.json
Get-FileHash docs/work6/evidence/console-open.stdout -Algorithm SHA256
```

Ожидается 12320 bytes / budget 65536, state/Work/authority revision 11,
Process revision 1, Artifact revision 3, две acceptance на revisions 10/11.
Семь источников: Process, Work, Artifact metadata, две acceptance с provenance и
receipt, два exact Artifact contents. Skills/tools/memory_entries пусты.
stdout SHA-256: 438bf8af803b20763c9e904097c7f5f250e2b06f34928720535d7e903604df85.
context-library.json, console-open.stdout и restore-context.stdout совпадают.
Manifest hashes значений относятся к canonical JSON; content — base64 исходных
bytes с собственным SHA-256. Human effort budget Work сохранён без перевода в bytes.
Source revision Handoff историческая; текущая revision открытия дана отдельно.
Все acceptance обязательны; latest-wins/отмена прежнего решения не выдуманы.

## Восстановить в НОВУЮ папку и установить

Используются существующие локальные uv/Python/cache; это локальный restore,
не независимая внешняя установка или upgrade.

```powershell
$backup = Get-Content 'docs/work6/evidence/retained-trial-manifest.json' -Raw | ConvertFrom-Json
$archive = (Resolve-Path $backup.archive).Path
if ((Get-FileHash $archive -Algorithm SHA256).Hash.ToLowerInvariant() -ne $backup.archive_sha256) { throw 'Archive hash mismatch' }
$trial = Join-Path ([IO.Path]::GetTempPath()) ('zaratustra-work6-manual-' + [guid]::NewGuid())
Expand-Archive -LiteralPath $archive -DestinationPath $trial
uv venv --python 3.13 (Join-Path $trial 'venv')
$python = Join-Path $trial 'venv/Scripts/python.exe'
uv pip install --offline --python $python -r (Join-Path $trial 'runtime-requirements.txt') (Join-Path $trial 'zaratustra-0.6.0-py3-none-any.whl')
$zara = Join-Path $trial 'venv/Scripts/zara.exe'
$workspace = Join-Path $trial 'workspace'
& $zara --version
& $zara status $workspace
& $zara handoff list $workspace
& $zara projections status $workspace
```

Выбирается только workspace/. negative-copies/ содержит намеренные отказы,
включая потерю bytes и отзыв прав, и не является рабочей базой. Ничего не достраивайте
вручную. В архиве 75 файлов и 72 каталога, включая пустые inbox/processes/unrelated-cwd.
Все hashes и directory inventory сверены до/после restore read/init/context в
restore-verification.json. Новая venv исключена из retained inventory.

## Публичный open и сохранение точного stdout

```powershell
$q = Get-Content (Join-Path $trial 'query.json') -Raw | ConvertFrom-Json
& $zara work open $q.work_id --workspace $workspace --workspace-id $q.workspace_id --process $q.process_id --expected-revision $q.expected_revision --max-bytes $q.max_bytes
```

После проверки показанных Work, пути и полного query введите `approve <digest>`
из prompt. Файл/model text/CLI flags/piped approval не выдают разрешений. Доверенный
local-chat adapter с фактическим prior permission не требует проверки личности заново.

Включённый driver сохраняет именно raw stdout и запускает четыре отдельных
консольных проверки на этой новой копии:

```powershell
& $python -I (Join-Path $trial 'exercise.py') --console $trial
Get-FileHash (Join-Path $trial 'console-open.stdout') -Algorithm SHA256
Get-Content (Join-Path $trial 'console-checks.json')
```

Подтверждаются open, stale revision 10, budget 5000 и foreign Process. Первый даёт
exact stdout; остальные exit 1 и ноль bytes stdout. Сохраните console-*.stdout,
console-checks.json, console-*-prompt.json, stderr/terminal transcript и свои наблюдения.
В поставленном evidence подтверждения вводил executor, не владелец.

Ожидаются conflict, budget_exceeded (required 12318 / allowed 5000; поле maximum
само влияет на длину) и scope. Installed hidden checks отдельно показывают чужой
exact Artifact ref, revoked/terminal, missing/corrupt, changed decision/rights/
requirements/bytes во время сборки и inert foreign link без чтения sentinel.
Native tests также проверяют BUSY, publication-ref closure, ровно 12320/12319,
request/path binding. Отказы не меняют DB; interleaving fixtures отдельно совершают
настоящую mutation, после которой устаревшее открытие обязано отказать.

Свежесть проверяется при окончательной revalidation. Последующее изменение
инвалидирует пакет; заново прочитайте owner-local records и подтвердите точный
current query. Не обновляйте revision/budget автоматически ради обхода отказа.
Старый manifest/projection/receipt не доказывает текущую доступность bytes.

## Полный повтор исполнительских проверок

```powershell
uv sync --locked --offline
uv run --locked python -m tools.check --deliver
uv run --locked python -m tools.probe_context --accepted-trial 'C:/Users/Anton/AppData/Local/Temp/zaratustra-work5-96nw94ii'
```

Probe сверяет 26 файлов accepted v2, создаёт новую копию только main workspace,
отдельно устанавливает wheel/locked dependencies и выполняет `-I` из unrelated-cwd.
Сохраните названный trial, install/runtime/installed-source, query/context/manifest/
identity, hidden-checks/installed-run. Затем выполните console driver на новом trial.
Если исходный Work 5 trial недоступен, сначала восстановите v2 по docs/work5/INSTALL.md
и передайте его новый путь; fault-workspace и old retained-trial.zip не подходят.

Остановленный trial сохраняется штатным исправленным packer:

```powershell
uv run --locked python -m tools.retain_trial $trial (Join-Path ([IO.Path]::GetTempPath()) ('work6-' + [guid]::NewGuid() + '.zip'))
```

Сохраните stdout manifest рядом с ZIP. Live-DB backup не заявлен. Фактически
исполненный restore driver находится в evidence/evidence-script.txt; при переносе
из исходного _scratch/ задайте root равным checkout. Raw команды установки и
проверок — restore-*.json/stdout/stderr, точный library script — restore-context-script.txt.
Work 8 отдельно свяжет exact delivered input с реальным ответом чистого чата;
сейчас понимание пяти фактов и owner runtime не проверялись.

END_OF_FILE: docs/work6/INSTALL.md

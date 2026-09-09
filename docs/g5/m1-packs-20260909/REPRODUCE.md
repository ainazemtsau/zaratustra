# Воспроизведение fresh G5 M1/T2

Candidate: `25a35b449570caf500cf09fca560b2bb64313169`.
Source: `f728ad6a8645ba04532e1cd74a34ea57c31c4dd8`.
Review task: `01a0869b-59b5-7b62-9e19-e2f8056f4341`.
Original CALL: `docs/m1-packs/CALL.md`. Owner acceptance pending.

## Новый прогон

Нужна НОВАЯ чистая изолированная копия exact candidate. Не использовать чужую
рабочую копию, reset/clean или уже занятый output/basetemp. До каждой операции
прочитать STOP/STEER в выбранной копии и source
`C:/projects/zaratustra/_scratch/m1-packs-20260909`. Их появление требует остановки
и разрешения инструкции владельца. Корневые Work8 attachment files не открывать.

Следующий пример создаёт отдельную detached копию внутри ignored review scratch.
Имена `-repeat-01` должны быть свободны. Для нового повтора выбрать новые имена.
Git worktree metadata/managed Python могут потребовать штатного разрешённого
escalation; не обходить REQUIRED tool STOP.

```powershell
$reviewDocs = 'C:/my_global_workflow/fa61/zaratustra/docs/g5/m1-packs-20260909'
$newCopy = 'C:/my_global_workflow/fa61/zaratustra/_scratch/g5-repeat-copy-01'
git worktree add --detach $newCopy 25a35b449570caf500cf09fca560b2bb64313169
Set-Location -LiteralPath $newCopy
git rev-parse HEAD
git status --short --branch
$run = '_scratch/g5-repeat-01'
New-Item -ItemType Directory -Path $run -ErrorAction Stop
foreach ($name in @('independent','supplemental','provenance_rollback','retained_wheel_worker')) {
    Copy-Item -LiteralPath (Join-Path $reviewDocs ($name + '.py.txt')) -Destination (Join-Path $run ($name + '.py'))
}
uv sync --locked *> "$run/uv-sync.txt"
if ($LASTEXITCODE -ne 0) { throw 'uv sync failed; preserve output' }
$env:PYTEST_ADDOPTS = "--basetemp=$run/pytest-native-01"
uv run --locked python -m tools.check --deliver *> "$run/check-deliver.txt"
if ($LASTEXITCODE -ne 0) { throw 'native check failed; preserve output' }
uv run --locked python "$run/independent.py" "$run/independent-01" *> "$run/independent.txt"
if ($LASTEXITCODE -ne 0) { throw 'independent check failed; preserve output' }
uv run --locked python "$run/supplemental.py" "$run/supplemental-01" "$run/independent-01" *> "$run/supplemental.txt"
if ($LASTEXITCODE -ne 0) { throw 'supplemental check failed; preserve output' }
uv run --locked python "$run/provenance_rollback.py" "$run/provenance-01" *> "$run/provenance.txt"
if ($LASTEXITCODE -ne 0) { throw 'provenance/rollback failed; preserve output' }
```

Scripts сохранены как `.py.txt`, чтобы review evidence не становилось новым
product/test/tool модулем. При выполнении copies находятся только в `_scratch`.
Фикстурное разрешение внутри сохранённых scripts ссылается на исходную G5 и
не является переносимой приёмкой владельца. Новый запуск требует действующего
разрешения на собственные fictional данные; записать его и новую task identity
отдельно, не редактируя исходное evidence.

Ожидание: native 173 PASS; `independent` 72 PASS; `supplemental` 12 PASS;
`provenance` 32 PASS. Числа описывают сохранённый сценарий, не квоту требований.
UUID/timestamps/новые DB hashes отличаются; смысловые проверки и exact
original archive/source hashes должны совпадать. Провал сохраняется с минимальной
уликой; source исправлять в G5 нельзя. Не повторять failed gate больше 3 раз.

## Что именно исполняется

`independent.py` создаёт свои initial records через Core, подтверждает точные
MutationRequest/ContextQuery в разрешённом fictional сценарии, регистрирует внешний
adapter, проверяет отказы, bind/result/next, scope/revision и поздние откаты.
`supplemental.py` импортирует только helpers первого script; первый main не
повторяется. Он создаёт новые отдельные IDs, проверяет некорректные next proposals
и характеризует объявленную trusted-host compatibility boundary.

`provenance_rollback.py` требует HEAD==candidate и native wheel в `dist/`.
Он читает exact Git blobs, manifests, wheel RECORD и ZIP CRC/layout; восстанавливает
original retained backups с помощью существующего
`tools.probe_m1.restore_snapshot` в НОВЫЕ folders. Original pre-bind и pre-result
requests выполняются через публичный Core с новым path-bound подтверждением.
Для legacy6→7 берётся исходное состояние с сохранённым Result; SQL применяется
только как `mode=ro` SELECT для сравнения полных строк таблиц.

`retained_wheel_worker.py` запускается отдельным `python -I`; retained baseline.whl
ставится первым в Python import path. Он проверяет `core.__file__`, schema6,
product 0.7.0, читает original state/history и выполняет исходный Result request
через этот старый Core. Locked venv предоставляет зависимости. Это проверка
старого кода и backup; установка на чужом компьютере не заявляется.

## Сохранённый прогон и rollback

Три архива `independent.zip`, `supplemental.zip`, `provenance.zip` содержат
inputs, exact requests, confirmations, receipts, JSON checks и fictional snapshots.
У каждого есть отдельный `*-manifest.json` с archive SHA-256, всеми member hashes
и directory inventory. Общий `manifest.json` покрывает все review-файлы, кроме
самого себя. `.gitattributes` сохраняет raw bytes/CRLF без Git-нормализации.

Для просмотра оригинальной сохранённой G5 сначала проверить archive SHA-256/CRC
и затем использовать `restore_snapshot(archive, NEW_PATH, manifest)` для **внешнего
evidence-архива**. Это восстановит пакет evidence, а не готовую единственную
рабочую папку. Для выбранного workspace использовать его вложенный ZIP/manifest
и ещё один новый путь. Сравнить полный layout/hash manifest до дальнейших
мутаций. Никакой распаковки поверх существующей workspace.

Внешние archives сохраняют исходные historical absolute paths только как
provenance. Они не разрешают запись туда. Новое разрешение связывается с новым
target path и прежним точным request. Исходные папки, manifest и raw outputs
сохраняются. Schema downgrade7→6 отсутствует: rollback использует pre-migration
backup и retained old wheel в новой папке, а не SQL/Markdown исправление состояния.

`package_review.py.txt` — использованная упаковка **уже завершённых** output folders.
Он привязан к фактическим именам этой review-копии и не нужен для повторной
проверки поведения. Пример выше не запускает его поверх существующих архивов.

REPORT HOME: `next: solmax`. Повтор не принимает T2/M1 и не создаёт T3.

END_OF_FILE: docs/g5/m1-packs-20260909/REPRODUCE.md

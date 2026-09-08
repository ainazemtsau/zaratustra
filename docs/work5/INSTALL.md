# Work 5 — Handoff: установка и walkthrough 0.5.0

Это проверяемый исполнительский результат на копии одного fictional Process.
Личный показ, Work 6–8 и закрытие T4/M0 остаются отдельными шагами Direction.
Точный подготовленный trial, wheel, команда и SHA-256 находятся в RESULT.md и
evidence/installed-manifest.json. Не запускайте mutation на прежних принятых DB.

## Посмотреть подготовленный результат

Откройте PowerShell в этой рабочей копии Product:

```powershell
$manifest = Get-Content docs/work5/evidence/installed-manifest.json -Raw | ConvertFrom-Json
$trial = $manifest.trial
$zara = Join-Path $trial 'venv/Scripts/zara.exe'
$workspace = Join-Path $trial 'workspace'
& $zara --version
& $zara status $workspace
& $zara handoff list $workspace
& $zara projections status $workspace
```

Ожидается версия 0.5.0, schema 5 и две сохранённые Handoff-записи: первая пришла
из файла, вторая из stdin. Каждая хранит accepted_result, result и basis с точными
artifact_id/version_id/sha256, исходную revision, provenance, quoted owner text,
constraints, open_questions, created_by, delivery hash, confirmation и receipt.
created_by/owner_instruction — заявленные данные; confirmation отдельно показывает
канал фактического разрешения этой операции. Рабочая цель/критерии/права не заменены
содержимым Handoff. Следующая Work ещё не создаётся.

Прочитать сохранённый результат с повторной проверкой физических bytes:

```powershell
$accepted = & $zara handoff list $workspace | ConvertFrom-Json
$reference = $accepted[0].handoff.result
$artifact = & $zara artifacts read $workspace $reference.artifact_id --version-id $reference.version_id | ConvertFrom-Json
[Text.Encoding]::UTF8.GetString([Convert]::FromBase64String($artifact.content_base64))
& $zara history $workspace
Get-Content -LiteralPath (Join-Path $workspace 'projections/overview.md')
```

Содержимое — прежняя вымышленная заметка о серебряном ободке луны. История содержит
прежние события и два accept_handoff. Overview пересоздаётся из DB, не служит
ограниченным Work context. Receipt доказывает прошлый эффект, а не доступность
файла сейчас. Каждый artifacts read проверяет текущие bytes заново.

Сохраните stdout этих read-команд и свои наблюдения, если проходите лично.
Подготовленные exact file/stdin inputs: handoff-file.json и handoff-stdin.json
в trial и в evidence/retained-trial-v2.zip. Точные stdout/stderr/exit: cli.json;
консольные previews и введённые подтверждения: evidence/terminal-session.json.

## Восстановить сохранённый sample

Используйте `retained-trial-v2.zip` и `retained-trial-v2-manifest.json`.
Прежний `retained-trial.zip` сохранён для F1: в нём отсутствуют обязательные пустые
каталоги. Его прежняя restore-инструкция опровергнута свежей G5.

В PowerShell из этой рабочей копии Product:

```powershell
$backup = Get-Content docs/work5/evidence/retained-trial-v2-manifest.json -Raw | ConvertFrom-Json
$zip = (Resolve-Path $backup.archive).Path
if ((Get-FileHash -LiteralPath $zip -Algorithm SHA256).Hash.ToLowerInvariant() -ne $backup.archive_sha256) { throw 'Backup hash mismatch' }
$restored = Join-Path ([IO.Path]::GetTempPath()) ('zaratustra-work5-restore-' + [guid]::NewGuid())
Expand-Archive -LiteralPath $zip -DestinationPath $restored
$environment = $restored + '-venv'
uv venv --python 3.13 $environment
$python = Join-Path $environment 'Scripts/python.exe'
uv pip install --offline --python $python --requirement (Join-Path $restored 'runtime-requirements.txt') (Join-Path $restored 'zaratustra-0.5.0-py3-none-any.whl')
$zara = Join-Path $environment 'Scripts/zara.exe'
$workspace = Join-Path $restored 'workspace'
& $zara status $workspace
& $zara handoff list $workspace
& $zara history $workspace
& $zara init $workspace
```

Offline install использует тот же локальный uv cache, что исходный trial; это
локальное восстановление, не независимая внешняя установка. Ожидаются schema 5,
две acceptance и сохранённая history; повторный init ничего не меняет. Result и
basis читаются командами выше. Manifest перечисляет 26 файлов и 15 каталогов,
включая пустые `processes/` и `inbox/` обеих workspace. Не добавляйте каталоги
вручную и не используйте fault-workspace как рабочую базу: в ней намеренно отсутствует
result content. Исторические абсолютные пути в receipts/inputs сохраняют provenance;
для чтения выбирается новый `$workspace`.

Повторяемая упаковка остановленного исходного fictional trial:

```powershell
uv run --locked python -m tools.retain_trial $backup.trial (Join-Path ([IO.Path]::GetTempPath()) ('work5-' + [guid]::NewGuid() + '.zip'))
```

Команда создаёт только новый архив, выводит manifest с hashes и всеми каталогами,
исключает `venv`/`__pycache__`. Проверенное восстановление: evidence/g5-f1-restored.json;
воспроизводящий скрипт: evidence/g5-f1-restore-script.txt. Исходные bytes не изменены.

## Повторить на новой копии принятого Work 4

```powershell
uv sync --locked --offline
uv run --locked python -m tools.check
uv run --locked python -m tools.probe_handoffs --accepted-trial 'C:/Users/Anton/AppData/Local/Temp/zaratustra-work4-viai92mt'
```

Probe создаёт новую временную папку, копирует только fictional workspace, отдельно
устанавливает точный wheel/locked dependencies и запускает Python с -I вне checkout.
Нужна обычная локальная консоль. Четыре раза он показывает полную текущую Work,
путь и запрос: file import, stdin import, старый replay и refreshed replay.
Проверьте, что это выбранная новая fictional копия, затем введите показанное
`approve <digest>`. Третий вызов ожидаемо вернёт conflict, четвёртый — первую
receipt без третьей записи. Первые два импорта добавляют по одному эффекту.
Piped approvals не принимаются. Для stdin JSON заканчивается EOF; подтверждение
читается отдельно из controlling console. Без неё импорт отказывает.

Исходный Work 4 остаётся schema 4 с прежним hash. Его копия проходит только явный
`zara migrate <path> --to 5`. Init и read ничего не мигрируют; совместимый default
`zara migrate` остаётся 4. Released migration source 1–4 не переписан.

Probe сохраняет исходные hashes до/после, новый wheel, installed-source.json,
runtime.json, inputs/prompts, cli.json, acceptances.json и receipt.json. На отдельной
новой fault-копии он проверяет отсутствие permission, откат при отказе записи
accepted_handoffs/COMMIT, сохранённую receipt после отказа projection и явный
rebuild, затем потерю Artifact bytes после импорта. Отрицательный fault sample
намеренно содержит отсутствующий файл; это evidence отказа, не рабочая база.
Его simulated local-chat adapter подписан как executor fixture, не owner runtime.

## Формат и самостоятельная ручная доставка

```text
zara handoff schema
zara handoff import <workspace> <selected-handoff.json>
zara handoff import <workspace> -
zara handoff list <workspace>
```

Файл — JSON UTF-8, optional BOM, максимум 64 KiB. Schema command задаёт полную
структуру; сохранённые два файла служат конкретными примерами. Handoff требует
workspace/Process/Work ids, handoff_id, intent accepted_result, source_revision,
result reference и provenance; дополнительные поля сохраняются по schema.
Нельзя использовать чужие id или mutable path вместо version/hash. `approved`
и неизвестные/повторяющиеся JSON keys отвергаются. Owner text сохраняется точно,
но не выдаёт права. При изменении file после чтения подтверждаются уже прочитанные
bytes и их hash; импорт не перечитывает файл незаметно после permission.

Обычная повторная отправка старого Handoff возвращает conflict: literal §5 проверяет
revision раньше duplicate. Если после проверки текущего состояния нужно узнать
исход уже выполненного импорта через повтор, сохраните исходный Handoff без правок:

```text
zara handoff import <workspace> <same-file> --expected-revision <current-revision>
```

Это новое точное подтверждение delivery, а не смена decision basis. Same id/intent
вернёт сохранённую receipt, даже если bytes позднее недоступны; новый Handoff со
старой source_revision не пройдёт. Изменение смысла при прежнем id даёт collision.
Не меняйте id для неизвестного исхода. Сначала проверьте history/receipt.
Отозванная/terminal Work отказывает раньше revision и duplicate.

После DB commit ошибка projection возвращает JSON с receipt, rebuild_required
и exit 2. Устраните причину и выполните `zara projections rebuild <workspace>`;
это не второй эффект. Другие отказы возвращают exit 1. Для потерянного содержимого
действует прежний exact restore_artifact через общий Mutation API; не чините DB
или generated state Markdown вручную. Orphan/repair/rebuild остаются границей Work 4.

Проверены локальные SQLite/I/O failures, не power/disk/controller loss и не атаки
других процессов того же OS user. Linux/macOS console route не измерялся.
Ни один этот прогон не является независимой внешней установкой или full Work 8
демонстрацией. W19–W27 с ответчиками/моментами/rewrites сохранены в PLAN.md.

END_OF_FILE: docs/work5/INSTALL.md

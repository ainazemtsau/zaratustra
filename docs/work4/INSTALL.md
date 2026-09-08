# Work 4 — установить, посмотреть и восстановить 0.4.0

Это отдельный установленный движок и новая fictional копия принятого Work 3.
Точные пути подготовленной установки и контрольные SHA-256 записаны в RESULT.md
и evidence/installed-manifest.json. Исходные образцы 0.1/0.2/0.3 не изменяются.
Ни одна команда ниже не закрывает Work 4/T3/M0 и не является показом Work 8.

## Посмотреть подготовленный результат

1. Откройте PowerShell. Подставьте installed_command и workspace из RESULT.md
   в две переменные. Это пути новой 0.4.0, а не сохранённой старой установки.

```powershell
$zara = '<installed_command из RESULT.md>'
$workspace = '<installed_workspace из RESULT.md>'
& $zara --version
& $zara records read $workspace
& $zara artifacts inspect $workspace
& $zara projections status $workspace
```

2. Версия — 0.4.0; schema — 4. Один прежний fictional Process и Work сохранены.
   Artifact зарегистрирован с двумя версиями; первая версия осталась доступной,
   вторая активна. `artifacts inspect` проверяет хеш каждой версии. Файл quarantine
   содержит намеренно повреждённые байты диагностического прогона; он не активен.

3. Прочитайте активное содержимое через проверку Core:

```powershell
$snapshot = & $zara records read $workspace | ConvertFrom-Json
$artifact = $snapshot.records | Where-Object kind -eq 'artifact'
$read = & $zara artifacts read $workspace $artifact.id | ConvertFrom-Json
[Text.Encoding]::UTF8.GetString([Convert]::FromBase64String($read.content_base64))
Get-Content -LiteralPath (Join-Path $workspace 'projections/overview.md')
```

Должна появиться вымышленная заметка о серебряном ободке луны в сумерках.
Overview показывает saved revision, source timestamp, Work, версии и provenance.
`generated_at` — время исходного сохранённого события, поэтому повторная генерация
одного состояния даёт те же bytes. Это owner-local обзор, ещё не Work context.

4. Посмотрите историю и сравните с receipt.json из того же retained trial:

```powershell
& $zara history $workspace
```

После трёх старых событий Work 3 идут authorize_work, authorize_artifact,
две publish_artifact и restore_artifact. Восстановление сохраняет id/hash/active
version, оставляет повреждённые bytes в quarantine и получает отдельную receipt.
Actor/local-console описывает канал подтверждения, а не доказательство личности.

Для просмотра достаточно этих read-only команд. Сохраните их stdout, если хотите
приложить свой просмотр; личная runtime-приёмка отсюда автоматически не выводится.

## Воспроизвести на другой новой копии

Из Product worktree:

```powershell
uv sync --locked
uv run --locked python -m tools.check
uv run --locked python -m tools.probe_artifacts --accepted-trial 'C:/Users/Anton/AppData/Local/Temp/zaratustra-work3-gnt5ksg0'
uv run --locked python -m tools.check --deliver
```

Probe создаёт новую временную копию и отдельный venv, печатает retained_trial,
копирует точный wheel и устанавливает locked runtime dependencies. Запускается
в реальной консоли: для пяти displayed операций проверьте workspace/Work,
operation/revision/Artifact/digest и введите показанное `approve <digest>`.
Piped confirmation и `approved` из файла не дают прав. Эти fictional подтверждения
в сохранённом исполнительском прогоне введены исполнителем по development CALL.

Probe проверяет явный переход schema 3 -> 4, две версии и verified reads,
удаление generated overview и его rebuild без DB-изменения, отрицательный случай
повреждения содержимого и восстановление через Core. На отдельной новой копии
installed Core проверяет COMMIT refusal и post-commit rebuild failure с сохранённой
receipt; для этих fault checks используется явно обозначенный trusted local-chat
исполнительский adapter. Ручная DB/state Markdown правка не участвует в успехе.
Оригинал сохраняет hash. Новые wheel, manifest.json, receipt.json, transcript.txt,
workspace, fault-workspace и исходные fictional content files остаются в trial.

Для совместимости доступны прежние probes: probe_install и probe_records.
probe_mutations теперь явно выбирает schema 3 и сохраняет DB-only сценарий Work 3.
Полный native check проверяет сохранённые cases и новые file/rebuild failures.

## Операции и recovery

`zara mutate <workspace> <request-json> --content-file <selected-file>` принимает
обычные bytes отдельно от точного подтверждённого запроса. Это не Handoff importer.
Version 2 request сохраняет operation_id/workspace_id/work_id/expected_revision/
provenance и добавляет для Artifact операций artifact_id/artifact_revision.
publish_artifact требует content_sha256/content_size; restore_artifact также
restore_version. references — массив artifact_id/version_id/sha256 текущей Work.
Version 1 JSON и его старые canonical fingerprints остаются совместимыми.

authorize_work даёт только work_metadata. Отдельная authorize_artifact требует
точного owner authorization и разрешает только единственный Artifact этой Work.
revoke_work снимает обе возможности; terminal Work не переоткрывается. Миграция
ничего не разрешает. Receipt/history содержат exact request и факт принятого эффекта.

Неудачная публикация/DB commit может оставить непривязанный файл или staging.
`artifacts inspect` показывает их; продукт их не активирует и не удаляет.
Повтор той же незафиксированной операции с тем же id проверяет готовый orphan
и может использовать его. При неизвестном результате сначала смотрите history/
receipt; новый id не является способом повторить неизвестный эффект.
Старый expected_revision вызывает conflict раньше duplicate lookup. При свежей
revision и прежнем id/intent возвращается старая receipt после проверки текущих прав.

После committed DB эффекта ошибка проекции возвращает JSON с receipt и
status=rebuild_required, CLI exit 2. Обычный отказ имеет exit 1. Для восстановления:

```text
zara projections status <workspace>
zara projections rebuild <workspace>
```

Rebuild читает последнее DB-состояние под общей writer lock, не меняет revision,
event или receipt. Он восстанавливает также отсутствующий каталог projections.
Проекции не принимаются обратно как state/authority. Их stale/changed bytes
не выдаются `projections status` за current.

Missing/changed Artifact читается с отказом; старая версия не подставляется.
Для repair подайте точную restore_artifact через тот же mutate с корректным
сохранённым содержимым. Core сверяет digest/size с registered descriptor,
сохраняет повреждённый файл и восстанавливает точные bytes. Изменение active_version
для новой редакции требует отдельной publish_artifact. Receipt о прошлой публикации
не доказывает текущую физическую доступность; каждый read проверяет bytes заново.

Проверенная граница — локальные файловые/SQLite отказы, потеря ответа, contention
и rebuild. Power loss/disk loss и hostile same-user races не доказаны. Git не
транзакция Core. Handoff/context/Result/next/clean-chat остаются Works 5–8.
CI/CD, Actions, notifications, remote/publication и внешние права не добавлены.

END_OF_FILE: docs/work4/INSTALL.md

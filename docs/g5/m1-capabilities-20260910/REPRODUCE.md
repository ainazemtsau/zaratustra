# Повтор G5 для точного T3 candidate

Предмет: `73ee71a3282291592040083df64adc9c6567eeda`, source
`d0cb354807ab16b1d917d500a4e3d1d46f59ad3e`, PLAN
`9eb43fabc029931148355007f156123156fcb90b`, accepted T2
`a5efbb15c7c39e52072f4fb1593a294ebe109a80`.

1. В новой чистой review worktree прочитать STOP/STEER, candidate AGENTS.md и
   validation.config до переключения. Использовать свободную review-ветку от
   exact candidate. Source не переключать; не применять reset/clean.
2. Прочитать candidate CALL/PLAN/RESULT/module AGENTS. Проверки используют только
   новые явно выбранные fictional workspace внутри ignored `_scratch` этой копии.
3. Выполнить `uv sync --locked`. Перед native обязательно задать новую basetemp.
   Пример PowerShell из корня новой review worktree:

```powershell
$g5Base = Join-Path (Get-Location) '_scratch/g5-m1-capabilities-20260910'
New-Item -ItemType Directory -Path $g5Base -Force | Out-Null
$g5Temp = '_scratch/g5-m1-capabilities-20260910/pytest-reproduce-01'
if (Test-Path -LiteralPath $g5Temp) { throw 'Choose a NEW basetemp' }
$env:PYTEST_ADDOPTS = "--basetemp=$g5Temp"
uv run --locked python -m tools.check --deliver
```

Сохранить полный raw stdout/stderr и exit code. Native G5-02: 204 PASS, pytest51.82s,
6 import contracts, build/hygiene/types/report PASS. Исторический author native-01
без basetemp не использовать как isolation/PASS evidence. Использовать `/` в
PYTEST_ADDOPTS: незащищённые обратные слеши Windows шлекс-разбор pytest удаляет.
Первый G5 native попал в собственную папку вне `_scratch`; его raw и диагностика
сохранены в native-isolation.json, он не является итоговым isolation evidence.
После повторения проверить, что actual basetemp появилась именно в `_scratch`.

4. Из review commit скопировать `independent-04.py.txt` в
   `_scratch/g5-m1-capabilities-20260910/independent.py` новой копии, затем:

```powershell
uv run --locked python _scratch/g5-m1-capabilities-20260910/independent.py _scratch/g5-m1-capabilities-20260910/reproduce-01
```

Названная папка должна отсутствовать. Runner проверяет STOP/STEER и границу
scratch. Он импортирует Python **из retained 0.9.0 wheel**, оставляя dependencies
из locked venv, независимо сравнивает Python wheel с candidate Git и fresh build,
проверяет manifests, восстанавливает retained before-result через штатный
`tools.probe_m1.restore_snapshot` и работает через public Core. Fixture rule
повторно использует только `FictionalBatchAdapter`; T3 author runner/tests не
вызываются. Ожидается 240/240 именованных проверок, включая auxiliary counters.
Новые UUID/timestamps/path authorization/DB hashes закономерно отличаются.

Для вторичного OS-процесса используется тот же script с внутренним режимом
`writer`; runner запускает его сам. Это reader/writer одного Process workspace.
Файлы input/authority/receipt, state/history, byte footprints, callback faults
и stdout/stderr сохраняются в новой папке. Не запускать runner в прежней папке
и не удалять предыдущий неудачный attempt для повторения.

5. `evidence-audit.py.txt` — исходный дополнительный audit. Он принимает новую
   output-папку в `_scratch`. Его 14/17 первоначальных PASS и три несовпадения
   сохранены намеренно: whitelist docs был слишком узок, два baseline raw
   отличаются LF/CRLF. [audit-dispositions.json](audit-dispositions.json) содержит
   точное разрешение; это не три незакрытых product defect. `package-review.py.txt`
   показывает сравнение обеих версий raw и их сохранение без переписывания.
   Packaging script адресован именам оригинальных attempts; при воспроизведении
   использовать новые имена, не перезаписывать review evidence.

## Открытие точного evidence

`manifest.json` задаёт SHA256/size всех файлов нового review, кроме самого manifest.
Для каждого `*-NN.zip` есть одноимённый `*-manifest.json` со SHA256 каждого
распакованного файла и полным directory inventory. `independent-04.zip` содержит
все запросы/ответы/confirmation/state/history, реальные mutations, исходный
author-contract и восстановленные fictional папки. `independent-01/02/03.zip`
сохраняют прежние partial attempts; raw и точные scripts лежат рядом.

Штатное восстановление snapshot, только в новую выбранную scratch-папку:

```python
from pathlib import Path
import json
from tools.probe_m1 import restore_snapshot

# archive и manifest выбраны из уже проверенного retained evidence.
restore_snapshot(Path(archive), Path(new_target), json.loads(Path(manifest).read_text()))
```

Внешний авторский `contract-manifest.json` хранит `{sha256, bytes}` в каждой записи,
а `restore_snapshot` принимает hash strings. Independent script явно переводит
только эту оболочку после проверки размеров/hashes; вложенные before-result/final
workspace manifests уже имеют штатный формат. Baseline-files-manifest.json —
ещё один явно проверенный формат, mapping names→`{sha256,bytes}` без directories.

Никогда не редактировать DB/state Markdown ради восстановления. Для damaged
artifact используется exact `restore_artifact` с сохранёнными bytes и отдельным
подтверждением. Сохранённые абсолютные пути/старые confirmations — provenance;
новая папка требует нового exact caller, прошлый caller права не переносит.

Матрица verdict и пределы — [G5-REPORT.md](G5-REPORT.md), машинная квитанция —
[receipt.json](receipt.json). Приёмка T3 остаётся pending; next: solmax.

END_OF_FILE: docs/g5/m1-capabilities-20260910/REPRODUCE.md

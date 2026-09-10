# Повтор T4 и baseline перед вторым Process

PLAN/baseline commit: ae7a809 (полный id см. evidence/receipt.json).
Source commit: b1e0853 (полный id см. evidence/receipt.json).
Версия продукта 0.10.0, schema7, fictional.lot 1.0.0, contract1/state1, PROBA36.
Source от accepted T3 review 4e892153200d6fa0b1ef3add0bfeceae06b23331.

## Новый прогон

Создать новую изолированную worktree от source/handback commit. Не переключать
исходную пользовательскую копию. Прочитать CALL, root/module AGENTS, STOP/STEER
и validation.config; отсутствие нужного runtime — STOP, не обход.
`uv sync --locked`, затем из корня копии:

```powershell
if (Test-Path '_scratch/t4-repeat-01') { throw 'Choose a NEW output directory' }
uv run --locked python -m tools.probe_first_process --output _scratch/t4-repeat-01
if (Test-Path '_scratch/t4-native-repeat-01') { throw 'Choose a NEW basetemp' }
$env:PYTEST_ADDOPTS = '--basetemp=_scratch/t4-native-repeat-01'
uv run --locked python -m tools.check --deliver
```

Использовать '/' в PYTEST_ADDOPTS. Убедиться, что actual basetemp внутри ignored
_scratch именно этой копии. В этом запуске cache задана внутри
_scratch/t4-environment/uv-cache, Python — уже установленный managed 3.13.7;
sandbox read требовал reviewed escalation, альтернативного runtime не вводилось.

Input template лежит в docs/m1-first-process/inputs.json. Runner сохраняет exact
template bytes и фактически опубликованные canonical JSON bytes отдельно.
SHA256 inspection подставляется из реально опубликованных bytes, не из примера.
При повторе UUID, timestamps, DB hashes и path-bound confirmations будут новыми.
Структурный результат: неполная inspection → lot_blocked; missing registration →
missing_pack; неправильный digest disposition → lot_blocked; два Results на
revisions11/18, явная отмена пустой continuation на19; bounded context ok.
Эти отказы ожидаемые; до них наблюдения опубликованы законными mutations,
сам отказ не меняет workspace. Все неудачные наблюдения сохраняются в истории.

## Доказательства и восстановление

evidence/scenario.zip содержит runtime/input/events, отдельные exact requests,
confirmations/receipts, семь ответов, query/context, state/history, snapshots до
каждой mutation и две папки восстановленного состояния. scenario-manifest.json
содержит SHA256 каждого файла и directory inventory; внешний manifest.json
фиксирует байты retained artifacts. Не использовать counts как proof модульности.

Штатный retain_trial + restore_snapshot восстанавливает только в новую папку.
После проверки внешнего manifest распаковать scenario.zip в NEW scratch путь
через tools.probe_m1.restore_snapshot и его scenario-manifest.json. Внутри:
events/inspection.snapshot.zip и events/disposition.snapshot.zip с одноимёнными
snapshot-manifest.json. Пример дальнейшего replay из корня новой копии:

```python
import json
from pathlib import Path
from tools.probe_m1 import restore_snapshot
from tools.probe_first_process import confirm
from zaratustra.core import MutationRequest, apply_mutation

evidence = Path('_scratch/unpacked-new/events')
snapshot = evidence / 'inspection.snapshot.zip'
manifest = json.loads((evidence / 'inspection.snapshot-manifest.json').read_bytes())
workspace = restore_snapshot(snapshot, Path('_scratch/restored-new'), manifest)
request = MutationRequest.model_validate_json((evidence / 'inspection.proposal.json').read_bytes())
receipt = apply_mutation(workspace, request, confirm(workspace, request))
print(receipt.model_dump_json())
```

Reproduction confirm допустим только в новой выбранной fictional workspace по
этому CALL; для иных данных это не authority. Старые confirmations сохраняются
как provenance; для нового path нужны новые. Runner также открывает точный
Core context и сравнивает его bytes до replay. Fingerprint/revision совпадают.
Прямые DB/state Markdown edits не нужны. До второго Result по той же процедуре.

Handoff basis разрешает ссылки своей Work; предыдущая inspection поступает через
штатные inherited Result grants. Это сохраняет реальную границу Core. Первый
focused attempt пытался повторно передать предыдущий Artifact в Handoff basis
и получил ожидаемый invalid_artifact; runner исправлен, Core не менялся.
Failed trial/source/raw сохранены в evidence/failed-focused-01.zip и
evidence/handoff-attempt-01.zip. Это не обнаруженный обход authority.

## W17/W20 — сопоставление второго подключения

before-second-source.zip и before-second-source-manifest.json сохраняют exact
committed source/tests/tools/lock/authority/input/PLAN первого пакета; retained
zaratustra-0.10.0-py3-none-any.whl сопоставлен с Python blobs этого commit.
Baseline Git ref B — поле source_commit в receipt.json. Не передвигать B на
будущий ref после правок. Первый full Process — только fictional_lot.

```powershell
git diff B T5 -- src/zaratustra/core src/zaratustra/process_packs
git diff --stat B T5
git diff B T5
```

B/T5 заменить точными сохранёнными commit ids. Сравнить полный path→blob/hash
набор (включая добавления/удаления/переезды), а не число файлов или grep названий.
Раздельно учесть код правил, registry/host, зависимости и документы. Core diff
должен быть пуст; обе гарантии P§30/P§40 сохраняются. Поведенческое доказательство
T5 обязано повторить этот сценарий и будущий второй под одной установкой с обоими
пакетами в одном registry, проверить данные/authority isolation. Одни hashes
доказывают bytes, не достаточность architecture. Fresh G5/T7 судит смысл.

Placement выбран PLAN: отдельная workspace каждого Process, явный список host,
общая установка/Core/контракт. Один authoritative revision на каждый ответ;
никакой общей меж-workspace транзакции не обещано. Общий renderer T6 не реализован.

END_OF_FILE: docs/m1-first-process/REPRODUCE.md

# Повтор T3 на точной версии

Source `d0cb354807ab16b1d917d500a4e3d1d46f59ad3e`, product0.9.0/schema7.
Basis `a5efbb15c7c39e52072f4fb1593a294ebe109a80`, pre-build PLAN `9eb43fa`.
Execution: `C:/projects/zaratustra/_scratch/m1-capabilities-20260909`,
branch `codex/m1-capabilities-20260909`. Дальнейший отчёт меняет только документы.

## Повтор штатными командами

Использовать эту копию либо новую isolated копию exact source. Прочитать её
STOP/STEER. Выбрать НОВЫЕ имена папок; существующее evidence не удалять.
Новые fixture writes разрешает текущий запуск владельца, не исторический caller.

```powershell
uv sync --locked
$env:PYTEST_ADDOPTS = '--basetemp=_scratch/pytest-owner-t3-new'
uv run --locked python -m tools.check --deliver
uv run --locked python -m tools.probe_capabilities --output _scratch/owner-t3-new
```

tools.probe_capabilities отвергает занятый output и путь вне ignored _scratch
именно выбранной execution-копии. Все новые workspace и evidence остаются там.
Это контрактный fictional пример с metadata-маркером выбора, не полный процесс T4/T5.
Не открывать Work8 файлы/старые папки ради этого повтора.

Смотреть `ready.response.json`, `blocked.response.json`, `continued.response.json`,
`next-only.response.json`, `denied.response.json`, `missing-pack.response.json`,
`missing-reader.response.json`, `stale.response.json`, `revoked.response.json`.
Тот же runner создаёт каждую `.query.json`, `.authority.json`, `.state.json`,
`.history.json`, optional context query/authority и все мутации в `events/`.
`runtime.json` связывает запуск с Git source; для acceptance нужен пустой source diff.

Ожидаемая цепочка исходного прогона: ready revision7, вопрос/blocked8,
возвращённая готовность9, Result/next10, revoke11. Новые UUID, timestamps и DB
hashes при повторе отличаются. Для exact исходных bytes открыть `evidence/contract.zip`
и проверить каждый файл по `contract-manifest.json`.

## Использование API

Внешний pack явно регистрирует reader вместе с прежними reference/rule:
`PackRegistration(reference, rule, reader)`. Reader реализует
`describe(ProcessMetadata) -> CapabilitySelection`. Примеры значений находятся
в `tools/probe_capabilities.py:FixtureReader`; исходный adapter только для проверки.

Trusted consumer формирует `ProcessQuery` с явными visible_work_ids, optional
selected_work_id и текущей revision. После разрешения на exact query он вызывает
`read_capabilities(path, query, caller, registry)`. Ответ — immutable bytes,
семь именованных `answers` и общий envelope. Adapter не получает path или caller.

Для actual context сначала читают требования, затем отдельно подтверждают
`ContextQuery` на ту же selected Work/process/revision и exact requirements.references.
Повторяют read_capabilities с `context_query`/`context_caller`. Core использует
существующий context compiler, включая полный byte budget и проверку closure.
Metadata authorization нельзя передать вместо context или mutation caller.
При смене revision/прав перечитать; не считать сохранённый ответ текущим.

## Законное восстановление

`evidence/contract.zip` содержит before-result.zip/manifest и final-workspace.zip/manifest.
Штатный `tools.probe_m1.restore_snapshot` проверяет SHA256 каждого файла и layout
и восстанавливает только в НОВУЮ папку. Runner уже восстановил before-result,
прочитал его через T3 и записал настоящий Result с новой exact path authorization.
Чтение и запись через Core; не исправлять DB или state Markdown.

Pre-build `baseline-trial.zip` сохраняет исходную T2-пробу, её три backups и
восстановленные папки; `baseline-files-manifest.json` проверяет все исходные файлы.
`baseline.whl` — прежний0.8.0; для установки скопировать в новую папку под именем
`zaratustra-0.8.0-py3-none-any.whl`. Schema7 не менялась. Возврат — retained old
wheel плюс новая восстановленная копия baseline, не чистка рабочих папок.

## Доказательственные границы

`source-verification.json` и `source.diff` — сравнение Git bytes, не behavioral scanner.
37 прежних files, включая validation/native oracle, released migrations1–7,
старые tests, context/records/results/artifacts, local/CLI и probe rules неизменны.
Lock меняет только версию собственного package; Python bytes wheel точно равны source.
`manifest.json` хранит hashes/размеры всех evidence файлов, кроме себя.

Native-01 остановлен исполнителем: не был указан PYTEST basetemp внутри execution
scratch, поэтому pytest начал использовать свою временную папку по умолчанию.
Её точный путь этим запуском не записан; этот прогон не evidence PASS и не claim
соблюдения изоляции. Чужие/временные папки не очищались. Native-02 и финальный
Deliver явно задают новую `_scratch` basetemp; полный успешный вывод сохранён.
Focused-01 сохранил семь несовпадений кодов ошибок; focused-02 — 31 PASS после
исправления их нормализации. Финальный native покрывает типы и весь набор.

Binding fresh physical G5 и actual owner acceptance pending. Это author self-check,
не fresh review. Один Process/workspace сохраняется; окончательный placement,
baseline перед вторым Process и обе гарантии Proof C остаются W17/T4–T5.
Отчёт HOME на исходный CALL; никакого successor/T4 здесь не выдаётся.

END_OF_FILE: docs/m1-capabilities/REPRODUCE.md

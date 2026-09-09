# Повтор T2 и восстановление

Source: f728ad6a8645ba04532e1cd74a34ea57c31c4dd8, Zaratustra 0.8.0.
Basis: f67959e7c1a412c202ebb0d6e67938ec4355042f.
Pre-BUILD PLAN/backup: 8dfaa5c50faa6c50bd6e67d357ee7bcef3dbf200.
Execution: C:/projects/zaratustra/_scratch/m1-packs-20260909,
branch codex/m1-packs-20260909. Последующие commits только docs/evidence.

## Native check и полный lifecycle

Из этой или новой изолированной копии exact source, после чтения STOP/STEER:

```powershell
uv sync --locked
$env:PYTEST_ADDOPTS = '--basetemp=_scratch/pytest-owner-new'
uv run --locked python -m tools.check --deliver
uv run --locked python -m tools.probe_packs --output _scratch/owner-packs-new
```

Выбирать новые имена. tools.probe_packs отвергает занятой путь и пути вне
ignored _scratch именно этой execution-копии. Последний вызов создаёт только
вымышленные workspace, не реальные процессы; он не является owner acceptance.
Каждое новое ручное повторение требует явного выбора собственной папки.

Ожидаемый summary: binding 3→4, Result 7→8, exact 1.0.0 в Process/Work/next;
missing и v2-only дают missing_pack, несовместимый contract/state — incompatible_pack;
in-place switch — permission_denied. Все эти отказы оставляют DB/history прежними.
Новый independent Process выбирает 2.0.0 и исполняет тот же lifecycle.
IDs/timestamps и hashes повторного прогона новые; первичные exact значения
сохранены в evidence/lifecycle.zip и связаны с source в runtime.json.

## Что сохранено

- evidence/check-deliver.txt — полный native запуск на clean source: 173 PASS.
- evidence/lifecycle.zip + lifecycle-manifest.json — все исходные inputs,
  requests/authorization/receipts, contexts, states, history, pre-migration,
  pre-bind, pre-result backups и восстановленные workspace с новым path-bound
  подтверждением. Каждый archive member и directory inventory перепроверены.
- evidence/summary.json — читаемый машинный итог того же прогона.
- evidence/source-verification.json + source.diff — связь с Git и проверка
  unchanged released migrations, прежних tests и T1 rules; это byte evidence,
  не доказательство поведения посредством source scanner.
- evidence/restart-read.json — отдельный Python процесс повторно читает сохранённую
  ready Work, открывает новый authorized context и заново разрешает exact registry.
  Код этого чтения — evidence/restart_read.py.txt; не физическая G5-сессия.
- evidence/zaratustra-0.8.0-py3-none-any.whl — сборка проверенной реализации.
- evidence/baseline.whl + baseline-trial.zip/manifest — проверенная версия0.7.0
  и тестовое состояние до изменений. Для установки сохранить baseline.whl в НОВОЙ
  папке под стандартным именем zaratustra-0.7.0-py3-none-any.whl.
- evidence/manifest.json — hashes/размеры всех сохранённых evidence файлов,
  кроме самого manifest. Не подменяет native/runtime checks.

## Законный rollback

Остановить писателей выбранной тестовой workspace. Из retained lifecycle.zip
извлечь before-migration.zip, before-bind.zip или before-result.zip и их manifest.
Применить существующий tools.probe_m1.restore_snapshot в НОВУЮ папку: он проверяет
каждый SHA-256 и весь layout. Не распаковывать поверх старой workspace.
read_records/read_history/read_workspace открывают восстановленную папку через Core.
Для повторной записи получить новое точное подтверждение на новый путь;
operation/request сохраняет прежние ids/содержание. tools.probe_packs уже
исполняет эти три восстановления; pre-bind и pre-result воспроизводят mutation.
Ничего не исправлять прямыми SQL или Markdown edits. Старые folders/evidence
сохраняются; downgrade schema7→6 не предоставлен. Для прежнего продукта нужна
новая копия basis и pre-migration backup, не новое ПО поверх altered DB.

## Непроверенные границы

Registry — trusted host configuration; arbitrary same-user Python не sandboxed.
Одна Process/workspace, in-place version migration отсутствует. W16–W20 остаются
по PLAN. Семь capabilities/полный M1 и независимая установка не заявляются.
Owner acceptance и binding fresh physical G5 pending. Следующий маршрут — HOME
в solmax на исходный CALL; эта инструкция не создаёт successor/T3.

END_OF_FILE: docs/m1-packs/REPRODUCE.md

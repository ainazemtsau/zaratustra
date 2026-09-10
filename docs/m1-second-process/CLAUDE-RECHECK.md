# Свежий Claude Code — узкая повторная G5 после G5-S01

Владелец поручил реализацию автору, проверки Claude Code. Исправление уже
закоммичено. Проведи проверку сам, без запроса владельцу собирать команды.
Это новый handoff; прежний CLAUDE-CHECK.md относится к старому candidate.

Source fix: b4a2aa88caea717663e7a5afdc064eb3e15bc922.
Original source5348690b9d9aa97dc4419ae884885e916d3ba02f;
old handoff9b7f3676b85a8c34fc9fe0e4e35289b5041d2939.
Авторская worktree C:/projects/zaratustra/_scratch/m1-second-process-20260910,
branch codex/m1-second-process-20260910; общий Git repo C:/projects/zaratustra.
Binding original G5 commit f4e3a26d85507f76429fc01e53c4dfdc1c4b18c5:
C:/projects/zaratustra/_scratch/g5-m1-second-process-20260910/docs/g5/m1-second-process-20260910/G5-REPORT.md.
Original reviewer session3d42376d-5619-4a77-9397-f3cd7c1e22bc, отдельна от автора
Codex task01a08a2a-1109-7211-8aa0-17cc639cf1d7.

Начни в свежей физической reviewer-сессии. Прочитай AGENTS.md, tools/AGENTS.md,
validation.config (PROBA36), STOP/STEER, CALL.md/PLAN.md/FIX-G5-S01.md рядом,
RESULT.md и исходный G5 report с raw. Создай NEW reviewer worktree, например
C:/projects/zaratustra/_scratch/g5-m1-second-process-recheck-20260910,
branch codex/g5-m1-second-process-recheck-20260910, от handoff commit из сообщения
владельца. При занятом имени выбери новый суффикс: не очищай и не переключай чужое.
Если дан только этот файл, HEAD author branch допустим лишь как прямой потомок
b4a2aa88 с изменениями только RESULT.md и docs/m1-second-process/; иначе сообщи drift.

## Проверить ровно оставшееся

1. Изучи diff9b7f367 → b4a2aa88: три строки вместо одной, явная проверка None
   в единственном tools/probe_second_install.py. Нет игнорирования типов,
   ослабления проверки расположения, изменения tests/PLAN/контракта/правил/host.
2. Выполни целиком обязательный native gate на новом pin, не отдельный mypy:

```powershell
$ErrorActionPreference = 'Stop'
$env:PYTHONUTF8 = '1'
$env:UV_CACHE_DIR = Join-Path (Get-Location) '_scratch/environment/uv-cache'
uv sync --locked
if ($LASTEXITCODE -ne 0) { throw 'Setup failed' }
New-Item -ItemType Directory -Path '_scratch/t5-recheck-01' -ErrorAction Stop
$env:PYTEST_ADDOPTS = '--basetemp=_scratch/t5-recheck-01/pytest'
uv run --locked python -m tools.check --deliver 2>&1 | Tee-Object '_scratch/t5-recheck-01/native.txt'
if ($LASTEXITCODE -ne 0) { throw 'Deliver failed; retain raw and return finding' }
```

   Managed Python3.13.7; версии из lock. Новый basetemp, старые evidence не чистить.
   Native должен целиком завершиться exit0: formatting/lint/types,11boundaries,
   tests, build и report structure.235tests — прежний результат, не подставлять
   заранее вместо фактического нового вывода. Максимум3повтора одного failed gate.
3. Сверь committed tree src/zaratustra на5348690b, b4a2aa88 и новом handoff:
   все равны2610df3b5e130eaf96ecb5566f08d564bfc42d43. Проверь также отсутствие
   изменений tests/fixtures, shared host, обоих runner и dependencies; исключение
   только описанная guard-правка installation probe. Обе гарантии P§30/§40 сохраняются.
4. Полную поведенческую G5 переиспользуй из f4e3a26 после сверки этой узкой дельты.
   Полные pair/install сценарии заново не обязательны; если увидишь новый риск,
   проведи лишь нужную дополнительную проверку и сохрани её raw. Старые
   CANDIDATE.json/ZIP относятся к5348690b, не к исправленному файлу.

Не редактируй продукт, авторские tests или контракт. Разрешены свои probes и
retained evidence/docs в reviewer-ветке. При FAIL верни точный вывод автору,
не исправляй вместо него. Не читать/искать Work8, original attachment, archive/**.
Не работать с реальными данными, не запускать T6/T7, не делать product push/merge
и не менять Direction live/**. Установка владельца недоступна этой проверке.

## Возврат

Сохрани и локально закоммить
`docs/g5/m1-second-process-recheck-20260910/G5-ADDENDUM.md` и full raw/evidence.
Назови exact source/handoff/reviewer commits и fresh session identity.
Два отдельных verdict: (а) full deliver, (б) unchanged product + narrow fix delta.
Укажи original G5 commit, что переиспользовано, что выполнено заново и что NOT RUN.
Хеши retained evidence считай от committed blobs, поскольку Tee-Object может
писать CRLF, а Git хранит LF. Не перезаписывай исходный FAIL report.
После PASS G5-S01 может быть признан закрытым этим addendum; owner acceptance T5,
Direction close, T6 и M1 этим не объявляются. Ответ владельцу коротко: результат,
ошибки если есть, полный путь к отчёту и commit; при FAIL готовый возврат автору.

END_OF_FILE: docs/m1-second-process/CLAUDE-RECHECK.md

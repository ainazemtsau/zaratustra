# T5 — G5-S01 исправлен, полный native gate ждёт повтора

## outcome

CALL c-solmax-zaratustra-m1-second-process-20260910-exec, PROBA36.
Source fix b4a2aa88caea717663e7a5afdc064eb3e15bc922: в development installation
probe __file__ сохраняется в локальную переменную и проверяется на None перед
Path. Остальные правила/проверки/host и установленный src/zaratustra не меняются.
Это кандидат исправления; зелёный полный gate и проверенное закрытие G5-S01 pending.

## evidence

Исходный source5348690b, handoff9b7f367. Fresh Claude G5
f4e3a26d85507f76429fc01e53c4dfdc1c4b18c5:
C:/projects/zaratustra/_scratch/g5-m1-second-process-20260910/docs/g5/m1-second-process-20260910/G5-REPORT.md.
По этому отчёту: deliver FAIL на mypy2.3.1, отдельно235tests/11contracts/build,
оба сценария,9bytechecks/13ownprobes PASS. Здесь сверены report, native raw,
minimal repro и итог pytest. Эти результаты относятся к старому exact candidate.
Review-дельта содержит только docs/g5, исходники авторского candidate не менялись.

Исправление: git diff9b7f367..b4a2aa88 содержит один Python-файл, +3/-1.
src/zaratustra в old5348690b и newb4a2aa88 имеет один tree id
2610df3b5e130eaf96ecb5566f08d564bfc42d43. Git identity не заменяет full native.
Решение/граница: docs/m1-second-process/FIX-G5-S01.md; новый готовый handoff
проверяющему: docs/m1-second-process/CLAUDE-RECHECK.md.
Автор fix не запускал native/mypy/pytest/scenarios; только source/evidence reading,
Git diff/tree inspection и обычный commit hygiene. Полный --deliver назначен Claude.
Исходные PLAN/baseline/CANDIDATE.json и ZIP сохранены с прежними pins без перезаписи.

## assumptions

Распределение владельца «Реализация здесь, проверки в Claude Code» сохраняется.
Явная None-проверка сужает тип и отвергает модуль без файла, не обходит guard.
При существующем файле сохраняется прежняя проверка расположения обеих fixtures.
Исходная поведенческая G5 может быть использована повторно после проверки узкой
дельты; addendum подтверждает full native и неизменность установленного продукта.

## cuts

Новых cuts нет; полный native обязателен, selective mypy не заменяет его.
Неблокирующие ограничения review сохранены: одинаковые changed-байты имеют
одинаковый digest; долгие цепи NOT RUN; G5-S02 про старую смену provenance не
требует новой правки. W17/W18/W20 обсуждаются с исходной G5 и новым addendum.
P§30/P§40 не ослаблены. Нет T6/T7/M1 close, real data или product push/merge.

## cost

Одно локальное исправление типизации в dev-инструменте; dependencies, schema
и package version не менялись. Токены/денежная стоимость не измерялись.

## manual-acceptance

T5 pending. Старый candidate не прошёл полный gate; новый ещё не проверен.
Приёмка T4 не переносится на T5. Direction root остаётся открытым, M0 partial.

## next

solmax

Свежий Claude Code: full --deliver и узкий G5 addendum по CLAUDE-RECHECK.md.
FAIL → автору raw/воспроизведение; PASS → HOME с original report и addendum.

END_OF_FILE: RESULT.md

# G5-S01 — явная проверка __file__ перед Path

Source fix: b4a2aa88caea717663e7a5afdc064eb3e15bc922.
Parent/handoff: 9b7f3676b85a8c34fc9fe0e4e35289b5041d2939.
Original source: 5348690b9d9aa97dc4419ae884885e916d3ba02f.
Исходный PLAN/baseline и CANDIDATE.json/ZIP сохраняются как evidence именно
старого source5348690b; они не объявляются manifest исправленной версии.

## Основание и принятая правка

Свежая G5 Claude Code session3d42376d-5619-4a77-9397-f3cd7c1e22bc:
review commit f4e3a26d85507f76429fc01e53c4dfdc1c4b18c5,
C:/projects/zaratustra/_scratch/g5-m1-second-process-20260910/docs/g5/m1-second-process-20260910/G5-REPORT.md.
Весь review diff от9b7f367 ограничен docs/g5/m1-second-process-20260910/.
Сверены сам отчёт, native-deliver-FAIL.txt, minimal repro и итог pytest.
Дефект: переменная цикла — ModuleType, её __file__ имеет тип str|None;
Path требует str/PathLike и не принимает None. Mypy2.3.1 отвергает исходную строку.

Правка ровно одного Python-файла tools/probe_second_install.py:
__file__ сначала сохраняется в fixture_file; assert fixture_file is not None
отвергает модуль без файла; затем прежняя проверка Path(...).resolve().is_relative_to
проверяет расположение каждой fixture. Нет cast/ignore/str(None) и удаления
проверки. При корректном модуле проверяется прежний путь; при None — явный отказ.
Другие Path/__file__ в этом файле прочитаны: у прямых модулей нет этой потери
типа, обход sys.modules фильтрует отсутствие пути отдельно; дополнительных правок нет.

## Доказательство границы, не PASS нового gate

Git diff source5348690b → fixb4a2aa88 по src/tests/tools/config/deps содержит
только tools/probe_second_install.py (+3/-1); tests, правила и shared host неизменны.
Дерево src/zaratustra в обоих commit:
2610df3b5e130eaf96ecb5566f08d564bfc42d43.
Это byte identity; самостоятельного утверждения семантического PASS не добавляет.

Исходная G5: обязательный deliver FAIL, отдельно235tests/11contracts/build/оба
сценария,9bytechecks/13ownprobes PASS по отчёту на исходном candidate.
Для fix автор не запускал mypy/pytest/native/scenarios: владелец сохраняет
«Реализация здесь, проверки в Claude Code». Выполнены только чтение/evidence,
Git diff/tree inspection и обычный commit hygiene. Новая версия ждёт полного
--deliver и отдельной узкой G5; G5-S01 не объявляется проверенно закрытым.

Неблокирующие ограничения исходного review сохраняются: digest связывает байты,
а одинаковые changed-байты не различают раунды; долгие цепи NOT RUN; G5-S02
описывает смену текстов provenance при прежнем выделении host. Это не новые
дефекты данного исправления; старые raw/fingerprints не переписываются.

Следующее задание — CLAUDE-RECHECK.md. При PASS исходная поведенческая G5 и новый
узкий addendum вместе идут HOME. T5/owner acceptance/M1 здесь не закрываются.

END_OF_FILE: docs/m1-second-process/FIX-G5-S01.md

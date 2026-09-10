# Повтор проверки границы «примеры только в тестах»

Source: 5b145b8bdfb9239939ca118ebe70542ffbb13b68, product 0.10.1.
Создать отдельную development worktree от этого source или его report-потомка.
Прочитать текущие STOP/STEER, AGENTS.md и validation.config. Использовать managed
Python 3.13.7 и uv sync --locked. Выбрать новые имена scratch-папок:

```powershell
$env:PYTEST_ADDOPTS = '--basetemp=_scratch/native-repeat-01'
uv run --locked python -m tools.check --deliver
uv run --locked python docs/m1-test-only/evidence/verify_install.py.txt _scratch/install-repeat-01
```

Ожидается: 220 tests, 9 import contracts, native Deliver PASS. Verification script
сверяет wheel с Git, отсутствие fictional_lot/process_probe и dev-пакетов в нём,
создаёт отдельную установку из wheel с runtime dependencies из lock и запускает
Python -I из пустой папки. При init и migration7 новая база имеет 0 records/revision0.
Только после проверки отсутствия примеров script добавляет development checkout
для внешней test fixture; все zaratustra modules остаются из установленного wheel.
Ожидаемый исход сценария: release/revision19, три ожидаемых отказа.

Фиктивное состояние создаётся лишь в выбранной NEW _scratch, ничего не удаляется.
Проверяется новая локальная установка; существующая установка владельца недоступна.
Сохранены wheel, исходные команды/script, raw, inventory и архив повторного сценария.
Состояние/UUID/время/path-bound confirmations при повторе будут новыми.

Первый native01: 216 PASS/1 FAIL — gate fixture копировала только src. Исправлена
подготовка этой проверки: копируются также tests/tools, добавлены отрицательные
импорты test fixture/tool. Focused3PASS; полный native02: 219PASS. Core не менялся.

Fresh G5 затем выявила пустые namespace directories после старых __pycache__:
никаких Python/pyc правил в wheel уже не было, но find_spec видел два пустых
имени. Регрессионная проверка воспроизводит остатки обоих старых каталогов и
реально собирает sdist/wheel: до исправления FAIL, после PASS. В build-backend
явно исключены сами старые src-пути. [Документация uv source-exclude](https://docs.astral.sh/uv/reference/settings/#build-backend_source-exclude)
описывает применение этого исключения и к sdist, и к wheel; здесь поведение
подтверждено закреплённым uv_build0.8.22. Итоговый native03: 220PASS/60.61s.
Финальная повторная установка: install-02.txt и evidence/final-install/.
Корневые evidence/verification.json и scenario.zip относятся к первому install01
на aca494; сохранены отдельно, не заменены финальной проверкой на 5b145b8.

Историческая baseline b1e0853 и G5 над 46718e4 сохранены как были. Этот перенос —
отдельная поправка до второго процесса; при будущем сравнении учитывать её явно.
Известное прежнее G5-F01 (CRLF/LF в manifest CALL) относится к старому evidence,
не к новому wheel. Старый manifest применяется только к его candidate, включая
прежний RESULT.md, а не к текущему report-потомку.

END_OF_FILE: docs/m1-test-only/REPRODUCE.md

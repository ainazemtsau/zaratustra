# Память и Sleep — пакет C

Sleep открывается как обычная работа с конечным лимитом. Он восстанавливает
положение, выбирает ограниченную историю, поддерживает память, сам выбирает
вопросы, проверяет основания и сохраняет поправки либо предложения. Следующая
работа получает текущую память и Method; её реальный результат доступен следующему
Sleep. Конец порции не означает, что вся среда изучена.

Безопасный показ механики на новых вымышленных данных, без платной модели:

~~~powershell
Set-Location 'C:\projects\zaratustra\.worktrees\restart-first-release'
$demoRoot = Join-Path '_scratch' ('owner-c-' + [guid]::NewGuid().ToString('N'))
.venv/Scripts/python.exe -m pytest tests/restart/test_sleep.py::test_sleep_adaptation_trace -q --basetemp $demoRoot
~~~

Driver и настоящий Pi проходят одну историю: Sleep меняет память/Method, следующая
Work использует новые версии, её отрицательный исход возвращается в Sleep, Method
получает новую версию с откатом в той же области. Прежние версии сохранены; owner
acceptance не появляется. Нужны Pi 1.0.4/Node и разрешённый localhost. Сценарные
тексты показывают перенос и управление, а не смысловую пользу модели.

Публичный вход: `Sleep(client).start(work_id=..., scope=..., call_limit=...)` и
`run(work_id, profile_ref, executor)`. Повтор start достраивает оборванный запуск;
run сначала использует удержанный terminal. Неизвестная отправка требует сверки.
Ошибка формата известного ответа сохраняет bytes; явный
`Coordinator.refresh_basis` допускает новую Attempt в прежнем остатке ресурса.

Команда `zaratustra-next --data-root <новый root> sleep` требует `--profile-file`,
`--work-id` и `--call-limit`. Профиль содержит pi_cli, endpoint, model,
credential_env и при необходимости api/max_tokens/context_window/timeout.
Значение ключа не кладётся в профиль, Method, context или evidence. Автоматического
перехода на платную модель или чужой OAuth нет. API Luna здесь вернула «нет
кредитов»; технический Codex Luna стенд — отдельная проверка, не установленный
адаптер продукта. `--refresh-basis` явно разрешает новую Attempt после известного
непригодного ответа, сохраняя старый и расход.

Статус проверок и ограничения — PACKAGE-C-RETURN.md. Кандидат ожидает независимой
проверки и слов владельца.

END_OF_FILE: PACKAGE-C-RUNTIME.md

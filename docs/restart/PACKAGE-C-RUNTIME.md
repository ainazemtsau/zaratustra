# Память и Sleep — пакет C

Sleep открывается как обычная работа с конечным лимитом. Он восстанавливает
положение, выбирает ограниченную историю, поддерживает память, сам выбирает
вопросы, проверяет основания и сохраняет поправки либо предложения. Следующая
работа получает текущую память и Method; её реальный результат доступен следующему
Sleep. Конец порции не означает, что вся среда изучена.

Безопасный показ механики на новых вымышленных данных, без платной модели:

~~~powershell
Set-Location 'C:\projects\zaratustra\.worktrees\restart-first-release'
$demoRoot = Join-Path (Get-Location).Path ('_scratch/owner-c-' + [guid]::NewGuid().ToString('N'))
$savedEvidence = $env:ZARA_RESTART_EVIDENCE
try {
    $env:ZARA_RESTART_EVIDENCE = Join-Path $demoRoot 'evidence'
    .venv/Scripts/python.exe -m pytest tests/restart/test_sleep.py::test_sleep_adaptation_trace -q --basetemp $demoRoot
} finally {
    $env:ZARA_RESTART_EVIDENCE = $savedEvidence
}
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

Повторный запуск с тем же work-id требует того же закреплённого профиля. Изменение
модели, endpoint, API или ресурсных параметров даёт отказ до отправки; параметры
не подменяются незаметно. Пауза владельца сохраняется до явного управления.

Исходник проверки — `3fbbf3e30cbf907ad3ea2d40686f02914c060dbf`. Четыре wheel/sdist
в `evidence/package-c/install-3fbbf3e-external/physical-builds` собраны в OS temp
вне всех Git checkout и отдельно установлены в чистой среде. Проверка Git в обоих
каталогах вернула not-a-repository. `install-3fbbf3e-external` содержит Driver/Pi traces,
точные зависимости и проверку
самостоятельного Core. Это disposable установка на новых вымышленных данных.

Живые запуски Luna сохранены отдельно. В одной цепочке Sleep изменил память,
получил отрицательный исход следующей работы и пересмотрел Method. Другая
подтвердила доставку новой Method, но один Sleep ответил на исторический запрос
вместо полного анализа. Поэтому completed в Work ещё не означает полезный
выполненный Sleep. Код проверяет происхождение, версии, права и расход; смысл
анализа оценивается отдельно. Тестовый Codex CLI считает конечные invocations;
точное число внутренних provider sends неизвестно.

Независимый проверяющий дал READY_SOURCE_WITH_RECORDED_LIMITS и отдельно получил
ограниченный положительный живой результат на своей рубрике. Неудачные ответы
автора остаются в evidence; устойчивость полезного Sleep этим не доказана.

Полный native gate прошёл: 1636 PASS, exit 0; scoped — 238 PASS и 46 контрольных
поломок. Статус и ограничения — PACKAGE-C-RETURN.md. Остаются независимая сверка
точного кандидата и слова владельца. Пакет D и перенос
рабочих данных этим показом не разрешаются.

END_OF_FILE: PACKAGE-C-RUNTIME.md

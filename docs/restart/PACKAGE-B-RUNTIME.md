# Что показал пакет B

На новом временном экземпляре сохранена одна работа. Её приостановили до отправки, затем возобновили. Первая новая попытка создала Activity ровно один раз и сохранила адресный вопрос. Новый процесс дважды открыл удержанный terminal: ни отправка, ни tool effect не повторились. Свободная поправка сохранилась, но сама вопрос не закрыла. Точный ответ снял именно текущий вопрос; следующая попытка получила и поправку, и ответ, а также прежнюю tool receipt. Работа завершилась с двумя final, cursor=22 и сохранённым reserve=4. Owner acceptance осталась отдельной и пустой.

Та же трасса прошла через настоящий Pi со сценарным localhost provider и независимый Driver. Отдельно показаны четыре initial ready/paused случая до самой первой Attempt: новая память или Method сохраняются через явный refresh, исходный ввод не теряется, продолжение той же Work возможно. Неизвестный внешний исход требует доказанной сверки; повторный send не подменяет её. Исчерпанный резерв не сбрасывается при reopen/resume.

Это проверка сохранения и управления исполнением. Сценарная речь provider не доказывает пользу реальной модели; полный Sleep и следующие пакеты сюда не входят. B ожидает отдельного owner verdict после независимой технической проверки.

Один воспроизводимый пример из рабочей копии, с новой disposable root на каждый запуск:

~~~powershell
Set-Location 'C:\projects\zaratustra\.worktrees\restart-first-release'
$demoRoot = Join-Path '_scratch' ('owner-b-' + [guid]::NewGuid().ToString('N'))
.venv/Scripts/python.exe -m pytest tests/restart/test_continuation.py::test_pause_reopen_retained_question_and_correction -q --basetemp $demoRoot
~~~

Два параметра проверяют Driver и Pi. Нужны обычный Pi 1.0.4/Node и разрешённый loopback; живые или платные модели не вызываются. Raw physical observations и exact installed-wheel trace: `evidence/package-b/corrected/`, итоговые pins и команды — `evidence/package-b/PROVENANCE.json`.

END_OF_FILE: PACKAGE-B-RUNTIME.md

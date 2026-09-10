# T4 — конечная проверка вымышленной партии

CALL c-solmax-zaratustra-m1-first-process-20260910-exec, PROBA, pin/stamp36.
Basis 4e892153200d6fa0b1ef3add0bfeceae06b23331; accepted T3 candidate
73ee71a3282291592040083df64adc9c6567eeda. Basis — прямой docs-only review-потомок.
Execution C:/projects/zaratustra/_scratch/m1-first-process-20260910,
branch codex/m1-first-process-20260910. Source clean, path/branch свободны на старте,
STOP/STEER отсутствуют. Source не переключается и не используется для записей.

## W18 — пара и наблюдаемые правила до реализации

| Измерение | T4: fictional lot release | T5: fictional signal rounds, только PLAN |
|---|---|---|
| Цель | Один конечный выпуск или отклонение партии KITE | Повторяемая проверка условного сигнала без расписания |
| Правило | Все именованные проверки должны пройти; затем отдельная disposition с SHA256 принятой проверки | Результат observe=steady открывает новый observe; changed открывает compare, compare открывает observe |
| Work types | inspect → decide → closed continuation, которую host явно отменяет | observe ↔ compare; число раундов не фиксировано |
| Наблюдаемое различие | Одной положительной отметки недостаточно; неверное основание решения отвергается; выпуск не автоматический | Одного события changed достаточно для смены типа следующей Work; нет conjunction gate/решения о выпуске |
| Конец сценария | Два сохранённых Results, cancelled пустая continuation, никаких доступных Works | Сохранённые результаты нескольких раундов и следующая ready Work |
| Данные | Только вымышленные item/marks/решение | Только вымышленные signal observations; никаких health/schedule/real data |

Реализуется только левая колонка. Это проверочные процессы, не пользовательские
шаблоны. T1 Batch/Cycle и T2/T3 fixtures сохраняются как прежние проверки;
ни один из них не объявляется полным вторым Process.

Точный T4 input: партия KITE, checks casing и label. Оба bool поля каждого check
(observed, recorded) должны быть true, имена checks должны совпасть с требуемыми
и быть уникальны. Первый вход с label.recorded=false даёт ожидаемый отказ.
После исправления exact bytes принимаются через Handoff и propose_result.
Следующая Work несёт требование decide и SHA256 этой inspection; её контекст
получает actual grounds из Core. Disposition содержит batch, release|discard,
inspection_sha256. Чужой digest/партия/неверная стадия отвергаются без mutation.
Оба решения завершают конечный процесс; успешный основной показ выбирает release.
Пакет не превращает текст решения в owner authority: fictional host имеет RUN CALL
и отдельно подтверждает каждый точный request. Это не приёмка владельцем T4.

Core submit_result всегда создаёт next Work. Сохраняем этот общий контракт:
последний Result создаёт явно обозначенную closed continuation с release/discard,
а host вызывает штатную cancel_work. Эта Work не выдаётся за выполненную Work
или третий Result. Пакет отвергает её продолжение; read показывает отсутствие
доступной работы после отмены. Нового terminal API и предметной ветки Core нет.

Семь ответов: scoped статус стадий, внимание при decide, открытый выбор disposition,
доступные inspect/decide, заблокированная closed/unknown Work, все видимые Results
как важные для этой конечной партии, требования выбранной Work + exact разрешённые
context_references. Ответ не делает утверждений о скрытой части Process.
Context отдельно подтверждается; условия/содержание и authority не смешиваются.

## W17 — placement и две границы сравнения

Выбрано существующее placement: один Process в отдельно выбранной workspace,
оба под одной установкой продукта и одним явным immutable runtime PackRegistry.
Будущий host получает явный список двух workspace; это конфигурация запуска,
не новый state/registry файл, discovery, предметный router или пара баз Core.
Каждая workspace хранит собственное authoritative состояние. T6 читает обе через
одинаковый read_capabilities с отдельными exact authorizations; каждое значение
показывает свой workspace/process/revision. Между workspace нет общей транзакции
или обещания единого revision (принятый W16). Общий обзор остаётся T6, здесь его нет.

Это технический выбор размещения, не подмена доказательства папками: T5 обязан
зарегистрировать оба полных пакета в одном host, выполнить оба сценария, доказать
различие правил и отсутствие взаимного изменения/доступа. T7 судит соответствие
W01–W03 целиком; количество папок/файлов не служит поведенческим PASS.

Граница A: accepted T3 basis → T4 source. Новая fictional module, runner, tests,
import boundaries и package version; Core/общий process_packs сохраняются побайтно.
Общая подготовка T2/T3 уже описана их PLAN. Если обнаружится необходимость общей
подготовки здесь, её надо явно назвать и закончить до границы B; redesign → HOME.
Граница B: финальный committed T4 source + retained wheel/manifest/state → T5.
T5 не вправе менять Core: P§30 «без изменения основной семантики Core» и P§40
«без изменения Core» обе сохраняются, без тихого переноса baseline после изменений.
Сравнивать полные Git blobs src/zaratustra/core и process_packs и запускать старый
и новый сценарии на одной версии. Проверка hashes — evidence идентичности, не
самодельный scanner семантики. Изменения правил/host/dependencies перечислять
по полному diff, включая переезды; отсутствие предметных веток судит fresh review.

## Сохранность и проверка

До edits: native tools.check; штатный tools.probe_capabilities в новой
_scratch/t4-before-edits с exact restore и дальнейшим Result через Core.
Сохраняются исходный wheel, Git source bytes, full raw и trial с before-result
snapshot/manifest. PLAN и baseline коммитятся до реализации.
Все новые fictional состояния и pytest basetemp — новые папки внутри ignored
_scratch именно execution worktree, пути с '/' в PYTEST_ADDOPTS. Не чистить чужое.

Runner сохраняет bootstrap/registration, exact inputs/requests/confirmations/receipts,
семь responses и selected context, Results/state/history. До изменений сценария
делает retain_trial; restore_snapshot только в новую папку, сверяет bytes/layout,
снова открывает контекст и повторяет тот же Result с новым path-bound caller.
Нет прямых DB/state Markdown edits или потери неудачных attempts ради PASS.

Тесты только для невидимого по показу: отказ правил без записи, точная привязка
оснований и сохранённых ссылок, scope/permissions/missing pack, отсутствие authority
у proposal, сохранность результата/контекста/replay/rollback. Наблюдаемые значения
показаны в READOUT, не заменяются тестом вкуса. Native tools.check --deliver обязателен.

## Диспозиции и сверка полномочий

W15: accepted T2 lifecycle/version/binding сохраняется без изменения.
W16: accepted T3 семь ответов/scope/revision сохраняются без изменения.
W17: выбран placement и baseline B до второго; Proof C остаётся T5/T7.
W18: выбрана пара выше, реализуется первый; второй остаётся T5.
W19: общий renderer остаётся PLAN/T6; JSON evidence не объявляется обзором.
W20: exact T4 evidence + восстановимая baseline; сравнение обоих/обзор T5–T7.
Исходные rewrites W15–W20 сохранены в CALL; scope cuts не добавлены.

Сверка: Direction plan 2026-09-05 §§8/30/40/43, shape 2026-09-09 T4/T5,
converge W01–W03/C01–C06 и fresh readiness review, accepted T3 close 2026-09-10,
knowledge/zaratustra-plan-conforming-approval-2026-09-07.md и independent-use
2026-09-10. Verdict: conforms under owner-ack:solmax-plan-conforming-20260907;
новая реплика владельца о PLAN не выдумана. Один ограниченный T4, без redesign,
новых внешних прав/расходов/реальных данных. При нарушении shape kill_by → HOME.
Repo contract делегацию для этого CALL не назначает; leg выполняется single-agent.
Product REPORT возвращает RESULT.md, next: solmax. Owner acceptance T4 и binding
fresh physical G5 pending. M0 partial, T5/T6/T7 и M1 не закрываются; live/** не меняется.

END_OF_FILE: docs/m1-first-process/PLAN.md

# Пакет B: полное продолжение — технический кандидат

База A: `accb09563bf46d25020a14c91cbc58b8d6dfa57b`. Владелец отдельно принял A как технический этап и разрешил B: «Окей, пакет A принимаю как технический этап. Запускай исполнителя на Sol 6.1 для пакета B, потом независимую проверку. Существенные отклонения согласуй со мной, остальное делай сам».

Scope — только §10 B принятой FIRST-RELEASE-PLAN revision 2. Frozen plan SHA256 `3e279c312d20f137e2076ecd7240f6b2c039923b9ee9bfa55e9662c5df98e0cb`; frozen review SHA256 `e7493dc10a06ce34b7f4e06efb6db55509565b46099ee51d1d6987b2aa268dcb`. Эти файлы, A return/manifests/raw evidence и PROBA36 сохранены. C/D, live usefulness и платные модели не входят.

## Реализация

Два устанавливаемых пакета и два адаптера сохранены. Изменён только существующий C9 в независимом ядре:

- Pause/cancel повышают generation, fencing остаётся; устаревшие prepare/dispatch/observe intents удаляются атомарно. Input intent, сообщения, terminal, tool receipts и расход сохраняются.
- Resume проверяет текущие must_be_current входы/Method; при продолжении существующей Attempt также profile. Новый admission невозможен при исчерпанном сохранённом calls reserve. Продолжение существующего running/terminal действия не расходует новый вызов и не требует свободного лимита для нового send.
- Observe intent после доказанной сверки адресует Attempt, а не Work. Повторный dispatch прежней Attempt отвергается.
- Существующий explicit refresh теперь работает также после безопасного pause: owner/уполномоченный клиент явно перечитывает refs и формирует новое намерение. Проверяются права, текущая Work revision, тип Method, ресурс и отсутствие unresolved/running внешнего действия. Без claim либо после доказанного terminal/not_received прежняя Attempt superseded, generation повышается, cursor не движется, новая Attempt получает сохранённые сообщения/receipts. Waiting/cancelled/completed refresh запрещён. Это исправление недостающего маршрута уже существующих C9/Coordinator.refresh_basis, без нового backend или неявного смыслового rebase.

При pause уже отправленная Attempt теряет право публиковать current. Reconcile running поэтому не возобновляет fenced публикацию; требуется доказанный terminal/not_received, затем новый безопасный admission. Сохранённый late terminal остаётся evidence. Для blocked без pause known-running/terminal возобновляет наблюдение той же Attempt и C8 без send.

### Коррекция независимого B-F1

Первый source `f3265f5439a196282e1edfcec455b1a6d3909ce9` получил независимый NOT READY: refresh требовал существующую Attempt. Настоящая initial ready Work после safe pause и correction до первой подготовки навсегда оставалась paused. Прежний тест ready имел ранее подготовленную Attempt и этот случай не покрывал. Независимый byte-identical reproducer SHA256 `1901bce3ea4e787b7f0c46fd978719d0260d0d010ffbed43cbda111b0bdda568` дал RED exit1 на этом source, затем GREEN exit0 после узкого исправления. Исходные report/scripts проверяющего не менялись; собственные RED/GREEN и raw observations сохранены в `evidence/package-b/`.

Refresh теперь не требует Attempt, если её никогда не было: проверяет те же права/Work CAS/status/current refs/Method kind/resource, сохраняет ready и prepare intent. Supersede и удаление attempt-specific intents выполняются только для существующей Attempt. Никакие fences внешних действий не снимаются. Четыре дополнительные проверки ready/paused × memory/Method удерживают input/cursor/reserve, допускают свежую Attempt и один реальный Driver effect. Шестой targeted control возвращает старый mandatory-Attempt guard и должен упасть на предметном assertion достижимости продолжения. Начатый native gate f3265f5 остановлен как INCOMPLETE/SUPERSEDED; не считается PASS и не подменяет новые gates исправленного pin.

## Конечная матрица поддержанных случаев

| Переход / окно | Обязательное наблюдение | Доказательство |
|---|---|---|
| Late input до C6 | Нулевой receiver effect; prepared superseded; fresh generation включает весь новый диапазон | A claim/refresh tests, G7 controls |
| Late input после C6 / до C8 | Старый cutoff, новая message pending, следующий input range без пропуска | Сохранённая A fixed trace, native Pi и Driver |
| Ready/prepared/claimed/waiting/blocked → pause/cancel | Generation +1, сохранённый reserve; dispatch/prepare/observe отсутствуют; late callback только evidence | B `test_control_fences_every_supported_stage`, 10 случаев |
| Pause до send → resume → fresh Attempt | Старое поколение fenced; original input сохранён; новый действительный вопрос и результат | B оба адаптера, fresh recovery процессы |
| Paused claimed/unknown → resume/refresh без proof | outcome_unknown, без повторного send и ready | B paused proof / crash cases |
| Paused + known-running | Старый executor не оживает; resume по-прежнему запрещён | B paused-running test + targeted mutation |
| Paused + proven-terminal | Fresh generation допустима; прежняя Attempt остаётся fenced/evidence, reserve сохранён | B paused-terminal proof |
| Unknown → proven-not_received → resume | Ready; новая Attempt сохраняет диапазон и старый консервативный reserve | B reconciliation case и fresh crash-before-send |
| Unknown → proven-running → resume | Running той же Attempt, observe intent по её ID, ноль resend | B reconciliation case + wrong-address mutation |
| Unknown → proven-terminal → resume → C8 | Retained terminal применяется после reopen, один final и прежний effect count | B reconciliation case / fresh crash-after-receiver |
| Crash после claim до send / после receiver до C7 | Fresh process не считает отсутствие send доказательством безопасности; затем только доказанная сверка разрешает продолжение | A crash windows + B full reconciliation routes, physical receiver log |
| Retained terminal до C8 / повтор recovery | Fresh interpreter дважды получает одну receipt; sends не растут; один final | A crash cases + B Pi/Driver reopen |
| Tool receipt сохранена, crash до terminal | Fresh lookup exact receipt, одна subject revision; после reconciliation следующий manifest содержит прежний ledger | B `test_tool_receipt_survives_crash_before_terminal` + A receipt retry |
| Correction после pause, stale current input | Resume atomic stale_basis; explicit refresh читает revision 2, cursor прежний, fresh generation | B correction + stale-basis mutation |
| Initial ready / paused до первой Attempt, correction memory/Method | Без claim/action/reserve refresh фиксирует новые refs; original input сохранён; fresh Attempt и один effect достижимы | Четыре B-F1 neighbor cases, byte-identical RED→GREEN, mandatory-Attempt mutation |
| Correction после dispatch | Новая raw message остаётся pending; precise answer снимает лишь свой wait; следующий manifest содержит обе message | B оба адаптера + A fixed trace |
| Reopen текущего wait / wrong/free/old reply / replay/race | Только exact current wait/Attempt/generation освобождается; старая receipt не снимает новый wait | A F2 regression/independent rereview и B fresh reopen exact answer |
| Cancelled/completed/waiting → refresh | Atomic refusal без оживления или обхода адресного вопроса | B три boundary cases |
| Refresh с non-Method | Atomic invalid_request, paused Work сохранена | B Method-kind case |
| Revoke до resume / current bases при продолжении | Denied/stale_basis; ни прав, ни нового эффекта | B revoke/current tests, сохранённые A claim/tool/C8 checks |
| Exhausted reserve после reopen/reconciliation | Resume/refresh не делают ready и не сбрасывают reserve | B exhausted case + targeted mutation; A C6 limit |
| Результат без owner acceptance | Completed/final отдельно; acceptance пустая; инструмент не может принять | B physical tables и сохранённые A authority tests |

G7–G11 расширены этими конкретными случаями, а не заявлением о всех возможных внешних системах. Recovery epoch остаётся проверенным envelope/fixture пределом A; production restore не добавлен. Unknown reconciliation — существующая доверенная host boundary с exact action identity и receiver evidence, не общий сторонний reconciler. Calls учитываются консервативным reserve; неизвестный расход не обнуляется. Нет произвольного partial prefix, one-shot approvals, artifact restore или полного Sleep.

## Проверка и воспроизведение

Новые проверки находятся в `tests/restart/test_continuation.py`: 30 behavioral cases; шесть targeted controls — `test_continuation_controls.py`. Они физически читают таблицы отдельно от production readers, считают receiver actions и используют новые subprocess для crash/reopen. Negative controls требуют валидного source, reached marker и behavioral assertion; syntax/import failure не засчитывается. Все 124 исходные A checks и 22 A controls сохраняются.

~~~powershell
.venv/Scripts/python.exe -m pytest tests/restart -q --tb=short --basetemp _scratch/new-b-check
uv run --locked python -m tools.check --deliver
~~~

Для полного legacy-root gate только его прежний явный `ZARATUSTRA_SQLITE_DLL`; независимое ядро и outside-checkout wheel proof используют native SQLite без bootstrap. Native Pi 1.0.4 и Node 22.19.0; только сценарный localhost provider, без personal auth/extensions/tools. `ZARA_RESTART_EVIDENCE` и `ZARA_RESTART_NEGATIVES` задаются новому `evidence/package-b/current`; `ZARA_RESTART_INSTALL_ROOT` — новому disposable каталогу `restart-package-b` вне checkout. Никакое A evidence не перезаписывается.

Исправленный source: `ac608192e620f2aa18e9c1d97debd1afac1adc89`. На нём свежий полный A+B scoped: **160 PASS/290.12s**, включая прежние A124/22 и новые B30/6; все **28/28 reached behavioral controls** подтверждены raw diffs/assertions. Focused B36 PASS/33.69s. Полный required native: **1558 PASS/1629.53s**, exit0, format/lint/types,37 import contracts,hygiene/report и все шесть build artifacts PASS. Full gate заново из-за delivery-only edits не запускался.

Обе новые outside-checkout wheel-only среды содержат одинаковые core/app wheels; 13 production `.py/.ts` members совпадают с source pin и installed bytes. Native SQLite3.50.4 в чистой установке; legacy DLL требуется только полному root gate. B runtime probe дополнительно подтвердил все четыре no-Attempt случая и pause/reopen/question/correction/receipt/reserve. Физические шесть artifacts удержаны в `evidence/package-b/builds/`, а не только названы hashes. Тридцать независимых физических наблюдений B, raw process/receiver logs и все исходные/корректирующие proofs сохранены.

Точные команды/exits и source/build/dependency/proof manifests: `evidence/package-b/PROVENANCE.json`, raw полный log `native-check.log`, финальные raw proofs `corrected/`. Сохранённые старые `current/`, `scoped-prefreeze/`, `freeze-observations/`, `superseded-f3265f5/` относятся к прежним runs и не подменяют финальное evidence. Независимая перепроверка закрыла B-F1 и дала SOURCE READY на ac60819; финальный evidence-only candidate ещё проходит отдельную reconciliation. Self-check не является binding review или принятием владельцем.

manual-acceptance: pending B. next: solmax — отдельная fresh physical review, затем owner verdict. Без merge/push/publication.

END_OF_FILE: PACKAGE-B-RETURN.md

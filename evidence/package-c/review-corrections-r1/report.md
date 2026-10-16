# Независимая physical-проверка C — NOT READY

16 октября 2026. Проверенный продуктовый исходник: `a2a446975526ce046e2d43f5ea85403c69af0096`, база принятого B: `05b5d0a8d24bfdc1ade4c7450d64979a398077b7`. Рабочая копия исключительно `C:/projects/zaratustra/.worktrees/restart-first-release`. Это возврат обнаруженных блокеров, не завершённая положительная проверка кандидата и не принятие владельцем.

Авторитет: вся revision 2 FIRST-RELEASE-PLAN.md, особенно §§3–7, 9–11; FIRST-RELEASE-REVIEW.md; текущий допуск C. SHA-256 плана `3e279c312d20f137e2076ecd7240f6b2c039923b9ee9bfa55e9662c5df98e0cb`, review `e7493dc10a06ce34b7f4e06efb6db55509565b46099ee51d1d6987b2aa268dcb` совпали. Прочитаны применимые AGENTS, validation.config (PROBA v36), проверено отсутствие STOP/STEER. Product source/tests/docs/config не менялись проверяющим. Собственные воспроизведения используют только public Core/app API и вымышленные данные.

## Findings

### C-R1 — P1: public Core допускает применение Method вне его области

Контракт: §3 — память/Method имеют область и явный статус применения; §7 шаг 6 — новая версия/область; G13 — неверная версия/полномочия fail. Проверка только в `Coordinator.open_work` (`coordinator.py:26–28`) не обеспечивает общий контракт обоих клиентов.

Собственный сценарий создаёт активный Method `lab-method` со scope=`lab`. Principal `review-executor` имеет `write:method:lab` и обычные operation rights, без делегирования `other`. Через public `client.call('open_work', ...)` создаётся Work scope=`other` с exact ref этого Method, затем обычные prepare/claim/dispatch/C8. Receiver фактически получает `context.work.scope='other'` и `context.method.scope='lab'`; результат сохраняется как completed. Не только readiness, а весь эффект достигнут.

Ожидается отказ до отправки либо явное авторизованное изменение области Method. `_work` в `api.py:509` проверяет kind/application, но не совместимость scope. Core admission и refresh должны сохранять эту границу независимо от app entry.

Физическое доказательство: `scope-core.json`, включая `received[].context` и итоговый snapshot. Независимый assertion `check_findings.py::test_public_core_enforces_method_application_scope` падает после реальной доставки (`assertions.log`).

### C-R2 — P1: refresh превращает proposal Method в исполняемый

Контракт: §3/§7 различают предложение и применённую версию; результат разрешённого изменения не может сам наделять Method статусом применения. В текущем C `_work` специально отвергает неактивный Method, но другой публичный переход обходит эту проверку.

Сценарий: создаётся Method `proposed`, scope=`lab`, application=`proposal`. Work открывается с обычным активным Method. Public `control_work(action='refresh', method_ref={id:'proposed',revision:1,role:'exact'})` принимается; prepare/dispatch/C8 также принимаются. Receiver фактически получает Method с `application='proposal'`; Work завершается. Исходное предложение остаётся proposal, отдельного разрешения применения нет.

Причина: ветка refresh (`api.py:1108`, проверка Method около 1136) проверяет только kind; `_exact` отвергает неактивность лишь для role=`must_be_current`, поэтому exact обходит барьер. Нельзя полагаться на добровольный выбор role адаптером. Проверить также withdrawn/tombstone и последующие prepare/claim/recovery — воспроизведённый вариант именно proposal.

Доказательство: `inactive-refresh.json`, `check_findings.py::test_refresh_cannot_execute_proposal_method`, `assertions.log`. Поведенческий failure достигнут, без mutation/build ошибки.

### C-R3 — P2: исчерпанный незавершённый Sleep сохраняется ready

Прямое требование §5: исчерпание ресурса при незавершённой работе означает paused с остатком либо blocked при неизвестном расходе/исходе. §7 требует честную причину остановки и продолжение.

Новая Sleep Work: call_limit=1, порция=1, controlled executor resource_upper=1. Первый конечный ответ просит state=`ready` с дальнейшим разбором. После C8 Work имеет reserved=1 и status=`ready`. Повтор public Sleep.run возвращает resource_exhausted/calls до нового внешнего вызова; долговечное состояние остаётся ready, intent подготовки остаётся, progress.stop_reason=`not_started`. Прогресс сохраняет remaining_refs, но не отражает наступившую остановку. Есть и промежуточная запись следующей порции до отказа refresh.

Превышения бюджета нет: receiver вызван ровно один раз. Finding касается ложного долговечного состояния/продолжения, а не опасного дополнительного send. Отказ не должен оставить исчерпанную незавершённую работу готовой к исполнению.

Доказательство: `exhausted.json` с first/next_error/deliveries/progress/snapshot, `check_findings.py::test_resource_exhaustion_persists_stopped_continuation`, `assertions.log`. В `api.py` C8 около 1080 создаёт prepare intent для ready независимо от остатка; refresh около 1123 только отказывает. `Sleep.run`/continue_portion не сохраняют остановку при этом отказе.

## Остальные наблюдения и действительные проверки

`probe.py` — собственный исходный воспроизводимый сценарий. `check_findings.py` воспроизводит каждый случай заново на отдельном Core и проверяет ожидаемый контракт. Итог **3 failed** — три адресных поведенческих assertion; raw receiver contexts/snapshots сохраняются и в первом запуске, и в `assertion-runtime/`. SHA исходных probes закреплены в verification.json; при исправлении повторять именно эти bytes.

Наблюдение `new-memory.json` **не объявляется дефектом**. Память создана после open_work до prepare; её нет в pinned inputs, но точные bytes текущей памяти присутствуют в delivered catalog. Это не доказательство input omission. Нужно отдельно определить требование обязательного admission pin для новой памяти и момент выбора; по имеющимся наблюдениям невыполнение доставки не установлено.

Вспомогательно прогнаны авторские tests/restart/test_sleep.py без двух adaptation_trace: **24 passed, 2 deselected**, фактические stdout/exit/argv в supporting-scoped.log и supporting-scoped-exit.json. Они покрывают стартовые crash-окна, retained terminal, историю/границу, prepared/unknown delivery, unknown reservation/reopen, запреты дельт, свободный текст, stale Method, resource cap и known invalid terminal. Это дополнительные checks, не независимый oracle и не полный gate. Сами независимые expected assertions не импортируют авторские tests/helpers и production admission/recovery helpers.

К моменту вспомогательного scoped-run HEAD стал `d4d2e73a1337beb14bd8d4770669e9aa37fb2b2d`. Фактически проверенный diff a2a4469..HEAD затрагивает только test-only tools/probe_restart_sleep_semantic.py (6 строк); packages и tests/restart идентичны a2a4469. Собственные probes не импортируют этот tool. environment.json сохраняет настоящий HEAD, package byte hashes, Python 3.13.7/SQLite 3.50.4 и diff. Поэтому первоначальные findings относятся к a2a4469; supporting scoped исполняет те же package/test bytes на указанном позднем HEAD. Это не reconciliation будущего исправленного исходника.

Скопированы фактические первые native exit/log (`native-first-*`): запуск остановлен, returncode=4294967295, 74.23 s, pytest остановился на первой части с F. PASS не заявлен; полный legacy gate самостоятельно не повторялся. Причину и новый запуск ведёт builder; его результат ещё не проверен здесь.

## Criterion → evidence / остаток проверки

| Обязательство исходного допуска | Состояние и свидетельство |
|---|---|
| §7.1 восстановить Work/Method/права/ресурс/outcomes | Public код прочитан; supporting scoped recovery/unknown зелёный; R2/R3 блокируют полную гарантию |
| §7.2 bounded enumeration/high-watermark/selection, отдельная exploration coverage | Структура и supporting scoped cutoff проверены; собственная содержательная exploration и полный независимый trace ещё не выполнены |
| §7.3 обычная/успешная/неудачная работа, реальные разрешённые поправки | Source/method inspected; semantic criterion открыт, scripted text его не доказывает |
| §7.4 самостоятельные вопросы вне готовых связей | Присутствует в generic Method; независимая live-оценка ещё не выполнена |
| §7.5 exact основания, альтернативы, контрпримеры, отрицательные попытки | Формальная доставка/остаток частично поддержана scoped; смысловая оценка открыта |
| §7.6 permitted corrections/proposals/versioned Method, scope/history | **FAIL R1/R2**; точная реальная доставка недопустимого Method и completed outcome сохранены |
| §7.7 следующая Work получает актуальные изменения, actual outcome feedback, пересмотр без переписывания истории | **BLOCKED R1/R2**; адаптерные traces/negative outcomes/rollback и live полный цикл ожидают независимой проверки исправленного источника |
| §7.8 truthful remainder/stop/continuation | **FAIL R3**; ready после фактического resource_exhausted; остальные формальные поля не доказывают понимание |
| Нет второго SleepRun/current/engine; код проверяет структуру/права, не смысл | По исходнику Sleep использует ordinary Work/Attempt/data и public Core; supporting free-text test passed. Это архитектурное наблюдение, не полный behavioral verdict |
| G12–G13 механика, обе adapter traces, crash/recovery/unknown/resource | Три independent failures; supporting 24 tests; собственные две полные adapter traces ещё не выполнены |
| A/B regression | Полный независимый regression не заявлен; первый native interrupted; требуется exact-source final raw native |
| Достигнутые behavioral negative controls | Авторские negatives-03 существуют; весь raw/faultdiff не проверен здесь и PASS не присваивается |
| clean installed builds; source/candidate/build/manifests/lock/raw | Final candidate/build ожидаются; физическая сверка wheels/installed bytes/lock и full native не выполнена |
| Независимая live Luna semantic оценка на новом материале | Не запускалась на заведомо блокируемом source; по уточнению ведущего откладывается до исправлений. Содержательная рубрика/полученные bytes/usage/invocations/reopen остаются обязательными. Author run03 rejected terminal не заменяет этот критерий |
| Runtime показать, честные ограничения, owner acceptance отдельно | Авторский runtime документ прочитан; положительный пригодный runtime ещё не заявляется; owner acceptance отсутствует |

Ни один исходный критерий C не снят. D/G14 wide usability, публикация/merge/push, личные данные и старые установки не проверялись и не затрагивались. Авторский semantic helper не объявляется production Codex adapter. Будущий live должен учитывать Codex invocations отдельно от неизвестного числа physical provider sends; неизвестный usage не ноль, paid fallback не разрешён.

## Возврат

Verdict: **NOT READY / NEEDS CHANGES** по исходнику a2a4469. Исправления — sole product writer; проверяющий не исправляет продукт. После corrected source повторить исходные три probes, выполнить оставшуюся независимую проверку C и отдельную finalcandidate reconciliation. Никакого source READY/final READY/owner acceptance сейчас нет.

Все собственные scripts/logs/JSON/runtime SQLite outputs перечислены в inventory.json с SHA-256 и размером (сам inventory исключён). Инвентарь физически пересчитан перед возвратом; mutable credentials в evidence не публикуются, используются только хэши credentials внутри вымышленных локальных Core. next: solmax через ведущего, без записи Solmax проверяющим.

# Независимая перепроверка пакета A: F1/F2

**Промежуточный code verdict: F1/F2 CLOSED, новых blockers в проверенном correction scope нет. Финальная готовность пакета: PENDING RECONCILIATION.** Новые полный native raw log/provenance и evidence-only final candidate ещё не получены. Этот отчёт не является финальным READY и не заявляет owner acceptance.

Физический независимый чат: `01a142fb-ed51-78e2-83f3-e1e6822af7f2`. Я не автор production или test corrections; использовал собственные probes и read-only inspection. Старый report/verification/proof в `_scratch/binding-review-20261016/` не изменён и остаётся NOT READY для старого candidate e6277cf/source3870ac4. Solmax state, tracked production/tests/evidence, прежняя грязная рабочая копия и установки не изменялись мной. Новые файлы только в этом review scratch; никаких новых функций/B–D/live моделей/личных данных/publication/merge.

## Exact basis и source freeze

- Рабочая копия: `C:/projects/zaratustra/.worktrees/restart-first-release`.
- Initial correction pin: `099621ba494e5042cb2cfb81b50c13aa7479fa2f`, parent `e6277cfdeb540366ead81d61d2045485e452446a`.
- Final source/test pin: **`3d4bcbc9acf3a6374643f8c9b72a056e188354b8`**.
- Production packages на 3d4bcbc побайтно совпадают с 099621b. Diff состоит ровно из exact wait-body expectation в `tests/restart/support.py`, SOURCE-MANIFEST и correction note.
- Спецификация revision2 неизменна: SHA256 **`3e279c312d20f137e2076ecd7240f6b2c039923b9ee9bfa55e9662c5df98e0cb`**. FIRST-RELEASE-REVIEW также не менялась.
- `pin-final-source.json`: 41 отслеживаемый source/test/config/spec файл чист относительно 3d4bcbc; production diff от099621b пуст. Dirty delivery reports и untracked f1f2 evidence ожидаемы и не являются source drift.

Прочитаны correction note, applicable AGENTS и pin diffs. STOP/STEER в рабочем корне отсутствовали. Scope, исходный CALL/done_when, PROBA36, независимость и все ограничения первой проверки сохраняются. Новый owner-direct допуск разрешает исправление и эту перепроверку, не acceptance.

## F1 — CLOSED

Инвариант: декларация каждого узла конечной схемы валидна независимо от наличия/nullable/пустоты значения; C3 и C8 либо сохраняют весь bundle, либо ничего.

В production появился отдельный `validate_schema`, который обходит object.fields/list.items и проверяет type, flags, имена, enum, допустимость bounds и их согласованность до обработки value. Общий `validate_value` вызывает его до короткого пути None и до обхода элементов. Это та же C3/C8 admission boundary, без предметных правил.

Собственные исходные `counterexamples.py` и `probes.py` скопированы байт-в-байт. SHA256: counterexamples `94e09c20e70df71127744318d53f4d11476ea2abe214eebe0e6ddcd3f8797a1a`; probes `ef4ff6029304f880da8345787437cecdc19950de3cd447318b9716a91bb672d6`. Исходный F1 assertion теперь проходит и на099621b, и на3d4bcbc.

Собственный `invariant_sweep.py` провёл **42 negative public admissions**: 21 декларация через каждый C3/C8. Unknown/non-string descendant, absent optional descendants, nullable object/list, malformed required/nullable, missing items, duplicate fields/enum, empty/typed-invalid enum, bounds wrong type/order и запрещённые structural members отклонены `invalid_request`. В наборе сначала стоит допустимое изменение, затем invalid entry; физический SQL snapshot всех 15 доменных таблиц до/после совпадает. C8 использует настоящий claim/retained terminal и проверяет также отсутствие partial final/cursor/wait/intent/receipt.

**16 positive admissions** подтвердили valid optional/empty/nullable/filled/integer/decimal/enum/text values в C3/C8. Untyped ordinary prose по-прежнему сохраняется без оценки истинности/полезности. Это не тест tuning magnitudes или owner-visible ответа.

## F2 — CLOSED

Инвариант: ответ освобождает только актуальный wait точной Work/Attempt/generation. Старый ответ не снимает новое ожидание; сохранённая receipt остаётся идемпотентной.

C8 атомарно добавляет trusted attempt_id/generation в body wait; shape пользовательского wait не разрешает эти поля. C2 под тем же writer transaction проверяет current waiting Work, latest finished Attempt, сохранённый attempt_id и совпадение generation до изменения wait/Work/message/intent. Не привязанные старые rows fail closed; migration прежних user roots не заявляется и не входит в этот new-root A.

Исходный F2 assertion теперь проходит на обоих pins. Собственные дополнительные случаи:

- Q1 → pause/resume → A2/Q2: старый Q1 reply даёт `stale_basis`, весь bundle неизменен; прямой C5/A3 до ответа Q2 также отвергнут.
- Точный Q2 reply работает, его exact command replay не меняет bundle; после него A3 допускается.
- Pause и cancel не позволяют старому ответу создать message/prepare intent или оживить Work.
- Ранее committed Q1 reply receipt можно повторить после появления Q2; Q2 остаётся blocking waiting.
- Два конкурентных точных Q1 replies через отдельные clients: ровно один commit, другой `stale_basis`, одна новая message и wait revision1→2.

Это **5 собственных соседних F2 случаев**, дополнительно к исходным контрпримерам. `supplementary.py` сохранил unknown→known-running→resume→terminal без второго action, cancel/late output, old epoch-envelope fixture и nested C8/revoke. Прежние lifecycle/current-basis/nested rights regressions также входят в полный scoped gate.

## Verification history без смешения pins

1. Byte-identical counterexamples на099621b: 2 PASS, exit0; повтор на3d4bcbc: 2 PASS, exit0. Логи `original-counterexamples.log`, `counterexamples-3d4bcbc.log`.
2. Byte-identical observational `probes.py`: exit1 после правильных F1/F2 denials на старом безусловном ожидании A3 admission. Это диагностический script, который описывал дефект; его последний happy-path assumption несовместим с исправлением. Сам assertion reproducer выше GREEN. `original-probes.log` удержан без редактирования.
3. Первый собственный invariant sweep: F1 58 cases и F2 pause/cancel/historical receipt прошли; один F2 assertion ошибочно учитывал read_snapshot receipt от Coordinator.prepare как partial C5 mutation. Сохранил `invariant-sweep-first.log`/`invariant-results-first.json`, исправил только свой harness на прямой C5 и повторил затронутый F2: PASS. `invariant-f2-confirmed.log`; отдельно `concurrent-replies.log`: PASS. Это не product finding и не ослабление atomic rejection: raw C5 не оставляет effects.
4. На099621b отдельно воспроизведён gate blocker `test_fixed_trace[driver]`, exit1: старый oracle в support.py:295 не учитывал новые trusted wait fields. `initial-driver.log`.
5. Exploratory full suite, начатая до test-helper correction: **121 PASS / 3 FAIL / 247,01s / exit1**. Три failures — parent process, уже загрузивший старый exact wait expectation: parity, trace driver, trace Pi. Installed driver скопировал уже обновлённый helper и прошёл. Это run через момент изменения oracle, он **не** считается pinned acceptance evidence. Лог `full-scoped-suite.log`; результаты/22 fault proofs в `unrestricted/`.
6. На финальном3d4bcbc выполнен отдельный полный scoped run: `run_suite.py --run=source-3d4bcbc`, с новыми собственными basetemp/cache/evidence/wheels/env. **124 PASS / 222,01s / exit0**, включая actual Pi/driver parity, exact updated wait oracle, чистый installed-wheel runtime, прежние8review regressions и22controls. Результат в `scoped-3d4bcbc.log` и `source-3d4bcbc/suite-exit.json`; `pin-scoped-end.json` подтвердил неизменность source/test/config/spec bytes на3d4bcbc.

Оба controls F1/F2 разобраны по failing assertions: F1 — DID NOT RAISE на malformed declaration admission, F2 — фактическая ready Work при unanswered Q2. Compile валиден, injection достигнута. Прежние20 controls сохранены; **финальный pinned run воспроизвёл22/22 reached behavioral kills**, без import/syntax errors. Baseline124tests прошёл, поэтому исходный stale-oracle failure не объясняет эти kills. `fault-audit-source-3d4bcbc.json` сохраняет test nodes/diffs/assertions, а не только helper PASS flags; exploratory proofs удержаны отдельно.

## Исходная матрица A / G1–G11

Полностью наследуется исходная матрица независимой проверки из `C:/projects/zaratustra/.worktrees/restart-first-release/_scratch/binding-review-20261016/report.md`, разделы «Покрытие исходных обязанностей A» и «G1–G11», с **явными changed rows ниже**. Наследование относится к неизменившимся source boundaries/ограничениям, не переносит старые source fingerprints или1493 PASS на новый pin. Новый полный scoped gate повторяет всю A suite.

| Исходная строка | Новая code disposition | Основание |
|---|---|---|
| C2 / exact active question | PASS проверенных cases | F2 original + соседние public probes + current addressed reply / replay / race |
| C3 / finite forms | PASS проверенных cases | F1 complete-declaration sweep, C3 atomic negative/positive и прежние rights/CAS |
| C8 shared schema / wait lifecycle | PASS проверенных cases | Common C3/C8 validator; full rollback; exact binding в той же outcome transaction |
| Control/generation | PASS bounded A, epoch предел прежний | Старый question не снимает новый wait; pause/cancel/replay сохранены. Epoch проверен только старым envelope/fixture, не production restore |
| G7 | PASS bounded generation/late-input scope; epoch evidence limit прежний | Старый F2 seam закрыт, late input cutoff/late output fencing не менялись и повторены suite |
| G11 | PASS проверенной адресной области | Точный active wait; старый/wrong/free reply не освобождает его; acceptance по-прежнему отдельно |
| §6 / exact prior wait receiver evidence | Повторяется на новом oracle | Exact JSON comparison сохраняет id/question и дополнительно требует A1/generation1; assertion не заменён loose subset/snapshot |
| G1–G6, G8–G10; прежние8 review regressions | Без нового source изменения вне common validation / wait boundary | Повторяются новым полным scoped gate; результат хранится отдельно от exploration |

Оговорки исходной проверки сохраняются: clean runtime guard до imports; новый собственный wheel env находится внутри разрешённого scratch, не outside-checkout. Удержанная прежняя внешняя установка была проверена по old source bytes, **не** является новой corrected external installation. Одноразовые approvals, pagination, token/money limits, arbitrary partial prefixes, общий third-party reconciler, production restore/artifacts, full Sleep/live usefulness не объявляются реализованными. Это согласованные пределы A, не перенос дефектов F1/F2 в B–D.

Fixed trace по-прежнему переиспользует предварительно сохранённую conversation Work; combined Activity+initial_work отдельно проверяется atomic test. Не выдаю это за наблюдённое создание новой первой Work одним native C3 в §6 шаге4. Прежняя оценка допустимого механического reuse для A сохранена.

## Что ещё нужно для финальной reconciliation

Проверить переданный evidence-only candidate: HEAD/diff от3d4bcbc не меняет source/tests/config/frozen specification; новый SOURCE/BUILD/GATE provenance и raw native terminal PASS относятся к3d4bcbc и новым artifacts; claimed counts/exits сопоставлены с raw bytes. Затем проверить fingerprints новых raw traces/22 negative proofs/builds. Старые общий1493 gate и provenance с source3870ac4 не считаются новым gate. Во время написания этого checkpoint новый required native выполняется исполнителем; я не запускаю его параллельный duplicate.

outcome: CODE_CORRECTION_CHECKED, PACKAGE_READINESS_PENDING_RECONCILIATION.

evidence: собственные immutable copies, logs, SQL snapshots, pin audits, scoped runs и fault proofs в этом каталоге; verification.json перечисляет фактически удерживаемые proof files.

assumptions: trusted host reconciliation boundary и остальные пределы A — как в исходной независимой проверке.

cuts: full native не дублирован; новый outside-checkout install не выполнялся; B–D не навязаны.

cost: bounded public API sweep, исходные counterexamples, exploratory и новый pinned scoped gate; без live/paid model calls.

manual-acceptance: pending, не заявлена.

next: solmax — передать новый native/provenance/final candidate для окончательной reconciliation; этот checkpoint не закрывает Direction state/G5.

END_OF_FILE: report.md

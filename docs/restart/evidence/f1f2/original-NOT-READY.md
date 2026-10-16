# Независимая итоговая техническая проверка пакета A

**Verdict: NOT READY.** Найдены два воспроизводимых дефекта контракта на неизменённом candidate. Собственный повтор штатной suite дал **95 PASS / 110,10 s**, все **20 seeded faults killed**, но два новых независимых assertions падают. Зелёная suite не закрывает эти контрпримеры.

Дата: 2026-10-16. Физический чат проверяющего: `01a142fb-ed51-78e2-83f3-e1e6822af7f2`, прочитан из `CODEX_THREAD_ID`. Я не автор реализации; это отдельный физический чат без истории ведущего/исполнителя, с их утверждениями только как входами проверки. Другие агенты не привлекались. Производственные файлы, tests, specs, отчёты репозитория и Solmax не изменялись; commit/push/merge/publication отсутствуют. Новый материал находится только под `_scratch/binding-review-20261016/`.

## Exact basis

- Рабочая копия: `C:/projects/zaratustra/.worktrees/restart-first-release`.
- Candidate / HEAD: `e6277cfdeb540366ead81d61d2045485e452446a`; начальный и конечный tracked status чистый.
- Tested source: `3870ac4ac1f6af1aa818c70c83e999a0f68646b1`.
- Base: `9d903d709783601c4878b707b9618031753a6854`.
- Единственная спецификация: `docs/restart/FIRST-RELEASE-PLAN.md`, revision 2, SHA256 `3e279c312d20f137e2076ecd7240f6b2c039923b9ee9bfa55e9662c5df98e0cb`.
- Frozen review SHA256: `e7493dc10a06ce34b7f4e06efb6db55509565b46099ee51d1d6987b2aa268dcb`.

Прочитаны применимые AGENTS.md, OWNER-LAUNCH, исходный CALL/done_when, KERNEL §G5 и play work. STOP/STEER в рабочем корне отсутствовали. Архивы не читались. Owner-direct разрешение допускает эту проверку до оценки владельца, но **owner acceptance остаётся pending**. PROBA36; никакого перехода на v37 или opt-in.

Сверка `audit_evidence.py`: все 37 source entries совпали между manifest, исходным commit, candidate Git blobs и рабочими bytes. Совпали 4 frozen-файла, 32 raw evidence fingerprints, 6 dist-артефактов и 8 reference-only источников reuse manifest. Diff source→candidate содержит delivery/evidence, без изменения проверяемого package source. Подробности: `evidence-audit.json`.

## Findings

### F1 [P2] Схема пустого контейнера допускает неизвестные вложенные типы

**Source:** `packages/core/src/zaratustra_core/formats.py:117–121`; второй путь — строки 107–116. C3/C8 используют этот validator через `api.py:308–309`.

**Минимальное воспроизведение через public API:** создать обычную data-запись схемы с body `{"type":"list","items":{"type":"unknown"}}`; затем C3 создать entry с `body=[]` и exact schema_ref на неё. Требование §3 прямо отвергает неизвестные типы объявленного формата. Ожидается `invalid_request` без entry/head/receipt эффекта. Фактически C3 возвращает committed refs `entry@1`, а физическая таблица records содержит entry с этой schema_ref.

Отдельно воспроизведён тот же класс для отсутствующего optional поля: schema `{"type":"object","fields":[{"name":"x","type":"list","items":{"type":"bogus"}}]}`, value `{}` тоже принят. Проверяется только непосредственный тип отсутствующего поля, но не его вложенная декларация.

**Причина:** рекурсивная проверка items выполняется только для реально присутствующих элементов. Пустой список не вызывает её ни разу. Валидация декларации зависит от наполненности конкретного значения.

**Последствия:** ядро публикует данные с невалидным заявленным форматом; invalid schema становится допустимой для пустого значения, но отвергается после наполнения. Это обязательство уже реализованного C3 в A, не полный Sleep или будущая поставка D. Не требуется оценивать истинность/полезность текста модели.

**Proof:** `counterexamples.py::test_unknown_type_in_empty_list_is_rejected`, `counterexamples.log` (CoreError not raised); `probe-results.json` / `probes-confirmed.log` содержат receipt и независимое SQL-чтение принятой записи. Оба примера используют только fictional roots. Рекомендация: независимо и полностью валидировать декларацию схемы, затем значение, включая отсутствующие/nullable/пустые ветви.

### F2 [P2] Ответ предыдущему вопросу снимает ожидание нового вопроса той же Work

**Source:** `packages/core/src/zaratustra_core/api.py:472–491`, особенно безусловная привязка готовности Work к любому waiting wait этой Work в строках 486–491. Pause/resume повышает generation без retirement/привязки вопросов; новая запись wait также не фиксирует Attempt/generation (`api.py:763–769`).

**Минимальные шаги public API:**

1. A1 generation 1 получает retained terminal; C8 фиксирует Q1@1, Work waiting.
2. Поддержанными control_work выполнить pause, затем resume. Подготовить и claim A2 generation 2.
3. Удержать terminal A2; C8 фиксирует Q2@1, Work waiting.
4. C2 отправить адресный человеческий ответ **Q1@1**, не Q2.

**Expected:** либо Q1 уже недействителен и ответ отвергается `stale_basis`, либо он сохраняется как ответ старому вопросу, сохраняя Q2 как блокирующее ожидание. Ответ Q1 не является ответом Q2.

**Actual:** C2 committed. Q1 становится answered@2; Q2 остаётся waiting@1; Work revision 7→8 меняет waiting→ready. Следующий `Coordinator.prepare('w','a3',...)` успешно допускается, хотя Q2 не отвечен. Это подтверждено отдельным SQL-чтением, не только public snapshot.

**Последствия:** ожидание текущей генерации обходится ответом прежнему вопросу; ядро разрешает дальнейшее исполнение без адресного ответа на актуальное ожидание. Это стык уже поддержанных A controls/fencing и адресного G11/C2, а не требование реализовать все вопросы B. Даже если оставить Q1 открытым намеренно, он не должен освобождать Q2. Изменять только revision-check Q1 недостаточно: в примере Q1@1 действительно существует и не отвечен.

**Proof:** `counterexamples.py::test_answer_to_previous_generation_cannot_unblock_current_question`, `counterexamples.log` (`ready != waiting`); расширенный `probes.py`, `probe-results.json` подтверждают допуск A3. Рекомендация: точно связывать active wait с generation/Attempt либо явно проверять оставшиеся актуальные блокирующие waits при переходе Work.

Оба контрпримера выполняются из текущей рабочей копии:

```powershell
.venv/Scripts/python.exe _scratch/binding-review-20261016/counterexamples.py
```

На candidate exit=1, **2 assertion failures**, без ошибок harness/import/build. Общие setup/read функции находятся в собственном `probes.py`, который не импортирует repository test helpers или production admission/context/recovery oracle.

## Покрытие исходных обязанностей A

PASS ниже ограничен описанным проверенным объёмом A, не означает принятия первой поставки целиком.

| Обязанность | Итог | Source / фактическая проверка / наблюдение |
|---|---|---|
| Два независимых installable packages; один Core | PASS | core api/types/shapes/formats не импортируют app/legacy; pyprojects разделены. Свежая сборка обоих wheels; isolated installed driver проходит cursor=22. Core-only guard до imports блокирует legacy, process/network/config. SOURCE/BUILD hashes совпали |
| C0 identity, wire/v1, CAS, receipts, errors | PASS в A | `types.py`, `api.py:209–260`; strict shape/vector tests, current principal/revoke/foreign receipts, expected_heads. Canonical object order, exact strings/list order; ошибкам сопоставлен diagnostic_id. Own preclaim/foreign executor/current-basis probes дают typed denied/stale_basis |
| C1 contract/snapshot/exact/lookup/readiness | PASS в A | `api.py:403–448`, `assess`; ограниченный полный snapshot, отказ вместо silent truncation; exact historical read; preview исполняет тот же путь и rollback. Snapshot pagination отсутствует и явно объявлена |
| C2 message + intent + receipt, exact question | **FAIL** | Atomic ingress/crash/replay проходят. Origin из credential, wrong revision/free reply проходят. F2 показывает пропущенную active-question/generation связь |
| C3 typed changes/history/unique/CAS/audit/initial_work/tool | **FAIL** | Atomic initial_work и его права, claimed executor, pinned current bases, denied generic delta проходят. F1 нарушает принятый finite-format контракт в общем validator; он используется и C8 |
| C4 Work + prepare intent, exact Method/inputs/resource | PASS в A | `_work`; kind Method, exact refs, call_limit, durable intent; missing material/unsupported units отвергаются до внешнего запуска |
| C5 continuous inputs/pinned material/one active slot | PASS | `prepare_attempt`; independent SQL/cutoff assertions, missing M19, manifest hash, work revision, exclusive work/conversation indexes. Receiver получает original/correction/Method/memory/profile/catalog/goal/prior result/wait/tool ledger |
| C6 claim/action/reserve before send; no blind resend | PASS в A | `claim_dispatch`, coordinator dispatch и bridge send_lock; unknown reserve остаётся, claim replay не выдаёт resend. Physical provider cap test и receiver effect count проходят |
| C7 retained raw/unknown/reconciliation/late evidence | PASS в A с пределом | `observe_attempt`, Pi raw message_end retention. Fresh-process recovery и own known-running→resume→terminal: один action/reserve. Reconciliation доверяет отдельному host-origin наблюдателю; общего verifier произвольной внешней системы здесь нет |
| C8 atomic final/cursor/changes/wait/continuation | PARTIAL | Crash после cursor/final и после commit, competing C8, slot uniqueness, late M21 pending проходят. Shared schema validation имеет F1; active-question lifecycle после C8/C9 имеет F2 |
| Current rights, provenance, separate acceptance | PASS проверенных admissions | Собственные nested initial_work/C8, revoke, tool executor/lifecycle/current bases; suite forbidden C3/C8 atomic и fake human tests. Acceptance отдельно, empty acceptance в обеих трассах. Нет свидетельства принятия владельцем |
| Pause/cancel/generation/epoch | PARTIAL | Suite pause/old C8 fencing и own cancel/late terminal проходят. Wrong/old epoch envelope отвергнут. Epoch advance — только fixture meta increment, не implemented restore/credential lifecycle. F2 затрагивает waits разных generations |
| §6 fixed trace actual Pi + independent driver | PASS механики, с уточнением шага 4 | Оба пути реально выполнены мной, совпали domain IDs/versions/heads/work/attempts/waits/tool ledger и stale/forbidden callback refusals. M20 cutoff20, M21 pending, answer cutoff22; повтор retained processing без inference. Разговорная Work предварительно создана C4; C3 создаёт Activity без нового initial_work. Combined Activity+initial_work проверен отдельным atomic тестом, не этим native callback |
| Diagnostics / clean install / manifests | PASS bounded A | Typed safe diagnostic IDs; model-free CLI init/diagnostics. Fresh wheel-only env с закрытым runtime доступом. Outside-checkout historical install отдельно проверен по удержанному proof и установленным source bytes; не выдаётся за мой новый outside install |

## G1–G11

| Gate | Verdict | Независимо полученное доказательство и граница |
|---|---|---|
| G1 | PASS с оговоркой места нового env | Новая wheel-only сборка/установка/guarded полный driver; hashes wheels равны принятому BUILD manifest. Новый env под разрешённым scratch внутри checkout; external install proof исполнителя проверен отдельно |
| G2 | PASS | Actual Pi1.0.4 native callback и независимый driver; domain-table parity и реальные native callback stale/denied; seed G2 пойман на отсутствии Core tool effect |
| G3 | PASS identity/CAS | Concurrent writers/CAS, unique current key, exact history после reopen и strict identities; seed stale write пойман. Общая C3 shape correctness отдельно FAIL F1 |
| G4 | PASS | Fresh-process ingress crash до/после commit; отдельный SQL oracle; lost intent/early commit mutants падают по состоянию |
| G5 | PASS | Receiver bytes/refs обязательного контекста, drop-input mutant, own current memory/Method/profile guards; stale basis блокирует новый tool admission |
| G6 | PASS | Atomic bundle/crash/racing C8/M19 gap/late pending; split commit/lost continuation/gap mutants пойманы |
| G7 | PARTIAL | Pinned cutoff и old output cancellation/pause fencing проходят; old-envelope epoch probe проходит с указанным пределом. Active wait generation seam F2 не выдержан |
| G8 | PASS bounded synthetic | Claim-before-send/after receiver crash не пересылается; tool receipt replay; own unknown→known-running→resume; no-blind-resend seed даёт действительно два receiver effects и ловится счётчиком |
| G9 | PASS проверенной поверхности | Revoke/foreign receipt/strict trusted origin/forbidden delta/nested rights. Forbidden набор не оставляет частичную запись; три соответствующих mutant assertions достигнуты |
| G10 | PASS | Raw terminal до C8, свежие recovery процессы без inference, duplicate callbacks, stable tool receipt ledger; drop raw/receipt seeds пойманы |
| G11 | **FAIL** | Базовый W7@1/wrong revision/free reply/separate acceptance проходят; новый контрпример F2 допускает выполнение при новом unanswered wait |

20/20 seeds валидно компилируются, injection достигнута, exit=1 обусловлен соответствующим behavioral assertion, не SyntaxError/ImportError. Их stdout/diff/test node находятся в `unrestricted/suite-negatives/*.json`. Я прочитал failing assertions, а не только helper flags. Этот набор не является полнотой контракта: F1/F2 отсутствуют в его oracle. Для G1 assertion — срабатывание запрещённого import guard; для G2 — отсутствие физической Core correlation/effect после реального native callback; G8 фиксирует duplicate receiver effect.

## Фактические собственные запуски

1. `run_suite.py`: первый полный прогон **88 PASS, 7 failures / 102,42 s / exit1**. Причины среды: sandbox sockets WinError10013 и DNS для нового dependency env. Pi/G2 seed не засчитан в этом прогоне, injection не достигнута. Лог `suite.log`; это не product FAIL и не скрытый PASS.
2. `run_suite.py --unrestricted`: полный повтор после разрешённой эскалации, **95 PASS / 110,10 s / exit0**. Pi localhost, свежие installed wheels и все 20 mutants фактически выполнены. `unrestricted-suite.log`, `unrestricted/suite-exit.json`, `unrestricted/suite-subprocesses.json`.
3. Собственные `probes.py`: exit0, шесть lifecycle/current-basis denials, nested C3 rights denial; два семейства accepted-invalid shapes и старый вопрос с A3 admission сохранены как expected/actual observations. Повтор подтверждён, логи `probes.log`, `probes-confirmed.log`.
4. `counterexamples.py`: exit1, два контрактных assertion failures. Это ожидаемый выход независимого опровержения, не сбой воспроизводителя.
5. `supplementary.py`: exit0, own unknown/known-running/resume/terminal, cancel/late C8 denial, stale epoch envelope и nested C8/revoke. `supplementary.json`/`.log`.
6. `audit_evidence.py`: exit0, fingerprint/installed source audit. Первая версия reader использовала Windows default encoding при чтении одного JSON; исправлена на UTF-8. Это ошибка моего audit harness, не finding продукта.

Suite runner перенаправлял только subprocess UV_CACHE_DIR в новый собственный cache и evidence destinations; tests/source не изменялись, assertions не ослаблялись. Явно очищены legacy DLL/PYTEST_ADDOPTS/install-root environment overrides. Новый install-root намеренно не объявлен outside_checkout: без расширения разрешённой области записей создание там не выполнялось. Guard самого чистого runtime сохранён полностью.

## Проверенные чужие evidence и пределы

Полный native gate **1493 PASS / 1317,12 s** — свидетельство исполнителя. Я проверил raw log с terminal PASS, provenance/fingerprints и соответствие source/build; **сам этот полный gate не повторял**. Мои scoped runs и counterexamples указаны выше отдельно. Старый source4136136 и superseded native log не засчитываются в финальный PASS.

Удержанная outside-checkout установка существует; все 13 установленных `.py/.ts` source files core/app совпадают с candidate. Проверены exact wheel hashes и guard-before-import recipe. Собственная новая установка дала те же wheel hashes и полный installed driver, но находится внутри scratch. Нельзя подменять одно утверждение другим.

Unsupported в describe/возврате: one-shot confirmation; pagination; денежный/token лимит; arbitrary partial-prefix terminal bundle; произвольный внешний reconciler; artifact/backup/restore; live profile и полный Sleep. Для A допустимы: явные отказы неподдержанного вместо эффекта, ограниченный полный snapshot вместо неполной страницы, whole pinned prefix с pending late inputs и консервативный calls reserve. G12–G15, полный Sleep/live usefulness, migration/maintenance и реальный paid provider остаются вне этой проверки. Нет live model calls, личных данных, daemon, публикации или изменения прежней установки. Эти ограничения не объясняют и не оправдывают F1/F2.

Уточнение §6 шага 4: фактическая трасса переиспользует уже сохранённую conversation Work; не доказывает создание новой первой Work одним native C3 с Activity. Сам atomic путь C3+initial_work реализован и проверен отдельно. В области механической вертикали A это допустимое переиспользование сохранённой Work; его нельзя описывать как наблюдённое выполнение literal combined шага через Pi. Я не вывожу из него доказательство будущего автоматического выбора Activity/первой предметной Work или live usefulness.

Три прежних pre-pass семейства перепроверены: suite восемь regression tests прошла; собственные public probes подтвердили preclaim/finished/foreign executor/current-basis guards и nested rights atomicity. Исправления в рассмотренном объёме подтверждены; вывод не основан на прежнем READY.

## Возврат

- outcome: **NOT READY**, два открытых P2 findings; owner acceptance pending.
- evidence: собственные suite/counterexamples/raw proofs, `verification.json`, `evidence-audit.json`; exact source/spec выше.
- assumptions: trusted local host observations считаются доверенной внешней границей; scope A только по принятой редакции 2.
- cuts: полный1493 gate не повторён; новый outside-checkout install не выполнен; B–D не навязаны.
- cost: два scoped suite runs, собственные bounded probes и read-only audit; без live model/денежных вызовов.
- manual-acceptance: **не получена, не заявлена**.
- next: **solmax** — удержать report/proof bytes, передать F1/F2 исполнителю; после исправления проверить exact новый source затронутыми gates. Эта scratch-поставка сама не закрывает Direction task/G5 и не изменяет Solmax state.

END_OF_FILE: live/solmax/work/restart-2026-10-16/returns/package-a-binding-review/REVIEW.md

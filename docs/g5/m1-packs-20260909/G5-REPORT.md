# Fresh physical G5 — M1/T2

## outcome

**PASS в пределах T2. Дефектов по трём done_when исходного CALL не найдено.**
Это binding fresh physical review, выполненная отдельной задачей
`01a0869b-59b5-7b62-9e19-e2f8056f4341`, а не авторский self-check или подагент.
Owner acceptance T2 **pending**. REPORT HOME на
`c-solmax-zaratustra-m1-packs-20260909-exec`; `next: solmax`.
Direction CALL/T2/M1 не закрываются. M0 partial; T3 не запускалась.

| Проверенная идентичность | Значение |
|---|---|
| Candidate | `25a35b449570caf500cf09fca560b2bb64313169` |
| Implementation/source | `f728ad6a8645ba04532e1cd74a34ea57c31c4dd8` |
| PLAN и retained baseline до BUILD | `8dfaa5c50faa6c50bd6e67d357ee7bcef3dbf200` |
| Принятая T1 review basis | `f67959e7c1a412c202ebb0d6e67938ec4355042f` |
| Review worktree | `C:/my_global_workflow/fa61/zaratustra` |
| Review branch | `codex/g5-m1-packs-20260909` |
| Source task, поручившая G5 | `01a0865e-b759-7bf3-9d21-e86819e52156` |
| Product / contract / mode | Zaratustra 0.8.0 / engineering_contract36 / PROBA |

Новая app-managed копия первоначально была чистой на detached setup commit
`512c7a1657aee9295a1e2e826eb3abc698d05fd8`. До переключения прочитаны candidate
AGENTS.md/validation.config через Git. STOP/STEER отсутствовали здесь и в
`C:/projects/zaratustra/_scratch/m1-packs-20260909`. После разрешённого escalation
создана свободная review-ветка на exact candidate. Все проверки продукта выполнялись
на этом HEAD; последующий коммит содержит только данный review-каталог.
Идентичность и ограничения записаны в [isolation.json](isolation.json).
Точный SHA review-коммита передаётся в финальном handoff; это коммит, содержащий
данный отчёт и receipt, а не изменение candidate.

## evidence

### Verdict по исходным done_when

| done_when | Verdict | Проверяемая улика |
|---|---|---|
| 1. На PLAN-модели pack/type/instance проверены registration, version compatibility и сохранённая связь Work с пакетом | **PASS** | Независимые `independent-checks.json`: строгие manifest values, все три несовпадения type/contract/state, unsupported registered versions, duplicate constructor, adapter/manifest collision, idempotent registration и coexistence. Реальный bind требует schema7 и exact authority; Process и Work меняются вместе, остальные поля сохраняются. Bound context читает обе ссылки. `supplemental-checks.json` подтверждает новые независимые workspace/Process/Work UUID и два перехода с новой версией. |
| 2. Missing/incompatible и смена версии имеют определённое проверенное поведение для unfinished Work без тихой смены прав/state | **PASS** | Missing и v2-only дают `missing_pack`; несовпадающие type/contract/state дают `incompatible_pack`, rule не вызывается. In-place rebind отказывает. Для каждого отказа независимо сравнены SHA-256 **всех файлов и полный layout**, включая DB/projection; изменений нет. Возврат exact old registration позволяет Result, следующая Work сохраняет binding и получает только `work_metadata`. Изменение прав, revision, query, path или подтверждённого next Work отвергается. |
| 3. Сохранены commit и воспроизводимые проверки общей Mutation/revision/history границы; поведение подтверждено выполнением | **PASS** | Полный native check: **173 passed**, ruff/mypy, 6 import contracts, wheel/sdist build. Независимые fault injections выполнены после двух record updates + event/receipt и после полной записи Result/next/event/receipt: DB и layout откатились. Original pre-bind/pre-result backups восстановлены в новые папки; exact requests успешно повторены. Original schema6 с уже записанным Result мигрирован в7 без переписывания прежних rows/events/receipts/Result. Old retained wheel 0.7.0 реально продолжил восстановленную legacy Work. |

### Что пытался опровергнуть

Проверки написаны в этой физической задаче, вне прежних tests/tools; исходный
`tools.probe_packs` не использовался как самостоятельное основание PASS.
Основной сценарий создаёт свой Process с неизвестными Core `review.unseen`
и `review.unseen-type`, версией `3.1.4` и обычными bytes, не T1 batch JSON.
Отдельное правило возвращает свою NextWork через публичный package runner.
Выбор версии `9.0.0` отдельно проверен на новых UUID; два продолжения сохраняют
binding и читают inherited grounds. Это узкие lifecycle fixtures, не два полных
процесса T4/T5 и не Proof C.

Проверены следующие попытки нарушения:

- Изменить любое из пяти полей manifest после подтверждения bind; подменить
  adapter или manifest на той же координате; использовать unsupported contract/state.
- Получить latest при отсутствии старой версии, перепривязать старую/следующую Work,
  повторить bind новым operation_id, повторить устаревший request или столкнуть intent.
- Вызвать rule без caller, с изменённым query/Process scope, после revoke/cancel
  или изменения revision; отправить сохранённое предложение после этих изменений.
- Изменить next Work после подтверждения, применить разрешение к restored path,
  подменить выбранные next IDs, расширить authority_scope из adapter output,
  столкнуть новые IDs с сохранёнными records.
- Получить Artifact scope одним bind, возобновить terminal Work, лишить владельца
  разрешённых history/repair/revoke при отсутствии registry.
- Оставить частичный bind или Result после позднего сбоя общей транзакции.
  Внутри точки сбоя выполнены только SELECT для фиксации уже сделанных продуктом
  записей; direct SQL/state edits для успеха не применялись.
- Потерять прежний Result/acceptance/history при schema6→7 и последующем bind
  незавершённой next Work. Проверка использует original retained backup, созданный
  до BUILD, а не только новое состояние текущей реализации.

`independent.py` завершил 72 локальные проверки; `supplemental.py` — ещё 12.
Это счётчики сценариев для навигации, не введённая квота или OPORA gate.
Последняя строка основного сценария с именем «explicit new instance» относится
к **восстановленной unbound копии с прежними UUID**; реальная новая instance
с другими UUID отдельно доказана в supplemental. Название в raw оставлено как было.

### Raw, восстановление и provenance

| Артефакт | Назначение |
|---|---|
| [raw/check-deliver-01.txt](raw/check-deliver-01.txt) | Полный успешный `uv run --locked python -m tools.check --deliver`; pytest 36.89s, 173 tests; basetemp внутри новой review `_scratch`. |
| [raw/uv-sync-02.txt](raw/uv-sync-02.txt) | Успешный обязательный `uv sync --locked`. Первый sandbox refusal сохранён в `raw/uv-sync-01.txt`. |
| [independent-checks.json](independent-checks.json), [independent.zip](independent.zip) | Собственные requests, confirmations, receipts, before/after records/history/context, backups, все отказы и hash/layout сравнения. |
| [supplemental-checks.json](supplemental-checks.json), [supplemental.zip](supplemental.zip) | Некорректный adapter output, новая отдельная instance, два перехода, characterization trusted-host boundary. |
| [provenance-checks.json](provenance-checks.json), [provenance.zip](provenance.zip) | 32 проверки provenance/rollback, оригинальные восстановленные данные и отдельный old-wheel process output. |
| [candidate-protected-bytes.json](candidate-protected-bytes.json) | SHA-256 и size exact Git blobs protected surfaces, сверенные с читаемыми source bytes. Это только provenance. |
| [source-core-pack.diff](source-core-pack.diff) | PLAN→source изменения Core/pack для ручной оценки общей, а не предметной подготовки. |
| [REPRODUCE.md](REPRODUCE.md), `*.py.txt` | Исполненные независимые scripts и инструкция воспроизведения на новом exact candidate checkout. |
| `*-manifest.json`, [manifest.json](manifest.json) | ZIP CRC, каждый распакованный file SHA-256, полный directory inventory; общий manifest review-файлов. |

Цепочка basis→PLAN→source→candidate проверена через Git ancestry.
Candidate/source diff содержит только RESULT и `docs/m1-packs/**`; code/tests/tools/
dependencies/authority совпадают. Sources в review checkout равны exact committed
bytes. Released migrations1–6, прежние local/process_probe и validation.config
не изменены относительно basis. Авторский source-verification перепроверен из Git.
Все original evidence files сверены с manifest, Git blobs и filesystem bytes.
Оба original trial ZIP прошли CRC, отсутствие duplicate members, hashes/layout;
проверены также используемые вложенные backups.

Python files обоих retained wheels и новой native сборки побайтно совпали с
соответствующим basis/source/candidate; проверены wheel RECORD hashes/sizes и CRC.
Сохранённый raw baseline-probe совпал с summary внутри pre-BUILD archive, включая
CRLF. Baseline-check совпал с версией PLAN после явного сравнения line endings;
его candidate raw bytes отдельно совпали с финальным manifest. Нормализация не
использовалась для утверждения о raw-byte identity.

Original lifecycle backups воспроизвели bind revision3→4 и Result7→8 с прежними
fingerprints и новым path-bound подтверждением. Original legacy batch backup
содержал 9 событий и 1 Result; schema7 сохранила все прежние domain rows, а bind
next Work добавил ровно одну общую mutation до revision11.
Retained wheel 0.7.0 загружен **первым из своего wheel** в отдельном `python -I`:
его `core.__file__` и version сохранены; исходный pre-submit request выполнен
с revision9→10 и прежним fingerprint. Зависимости предоставляла locked venv.
Это реальный old-code rollback, но не доказательство внешней установки.

### Ручная оценка границы и обязательств

Прочитаны целиком новые lifecycle/runner, новые pack tests, изменения Core;
проверены общий evolve/mutate/history путь, request validation, context guard и
module instructions. В изменениях Core нет выбора fictional rule, названий pack
или выбора latest. Новое неизвестное Core правило действительно прошло через
тот же Mutation/Result путь. Scanning/hashes не используются вместо этой проверки
поведения; native import contracts подтверждают только граф зависимостей.

Выбранная граница **достаточна для заявленного trusted-host T2**: registry проверяет
установленную точную identity и contract1/state1; Core сохраняет generic reference,
проверяет полномочия/целостность и одноразовость binding. Manifest не удостоверяет
байты adapter code. Независимый supplemental прямо подтвердил предел: с отдельным
точным подтверждением публичный Core может сохранить валидную generic reference
со state_version2, однако package runner откажет `incompatible_pack` и не вызовет rule.
Это объявленное распределение ответственности, не обещанный Core-side installation
gate. Аналогично отдельное точное owner-confirmed общее действие не требует
установленного pack. Пакетное предложение само прав не выдаёт.

| Обязательство | Диспозиция |
|---|---|
| C01 | Общая identity/type/version, Process/Work binding и внешний rule подтверждены в T2. Полный M1 contract не заявлен. |
| C02 | Пакет не выдаёт authority; current rights/revision, точный request, duplicate/collision и общий receipt/history реально проверены. |
| C06 | Result/acceptance/Artifact grounds и binding продолжаются через общий Core; rollback и legacy preservation подтверждены. |
| W15 | Модель/registration/compatibility/lifecycle отвечены PLAN и проверены в T2; полные предметные правила остаются T4/T5. |
| W16 | OPEN → PLAN/T3: семь capabilities, empty/denied/unavailable, scope/revisions, metadata/counts/consistency сохранены. |
| W17 | OPEN → PLAN/T3–T5: окончательный baseline до второго, сосуществование, полная независимость. T2 — общая подготовка, не Proof C. |
| W18 | OPEN → PLAN/T4/T5: два полных существенно разных fictional процесса. Review fixtures это обязательство не закрывают. |
| W19 | OPEN → PLAN/T6: общий обзор в допустимой поверхности; нового frontend здесь нет. |
| W20 | T2 exact evidence/rollback сохранено; полные сценарии и сравнение второго OPEN → PLAN/T4–T7. |

Исходный Direction plan§8 сохраняет семь возможностей. Обе отдельные гарантии
P§30 «без изменения основной семантики Core» и P§40 «без изменения Core» не
ослаблены: текущие изменения относятся к общей подготовке, а доказательство
подключения второго ещё впереди. PLAN сохраняет оставшиеся rewrites/answerers;
T2 не переименована в финальную независимость или завершённую M1.
Применение delegation knowledge не выдаёт новых слов приёмки владельца.

## assumptions

Trusted local Python/host и текущая W21 модель приняты из CALL/PLAN/AGENTS.
Arbitrary hostile same-user Python не sandboxed; подписи кода, внешняя установка,
in-place version migration и совместное размещение нескольких Process не доказаны.
Fault injection проверяет откат транзакции при исключении в указанной точке,
не отключение питания, filesystem damage или все interleavings ОС.
Полный native suite использован как регрессионное evidence, не owner acceptance.

## cuts

Новых сокращений T2 CALL нет. Не выполнялись T3–T7, Work8/original attachment,
реальные процессы, публикация, CI/CD, внешние сервисы или платные действия.
Direction OS, source worktree, прежние tests/tools/RESULT/evidence и validation.config
не изменялись. Все новые fictional workspace/scripts работают только в ignored
`_scratch/g5-m1-packs-20260909/` review-копии; tracked результат — только этот каталог.

## cost

Один полный native check, 84 независимых runtime/validation checks и 32 проверки
provenance/rollback; без новых зависимостей и подагентов. Все три независимых
script runs прошли с первого запуска. Git switch и первоначальный uv sync
потребовали разрешённого выхода за workspace sandbox для штатных Git/runtime/cache
путей; обязательные tools доступны, STOP из-за отсутствующего инструмента нет.
Стоимость API/денег не измерялась; внешних платных вызовов не было.

## manual-acceptance

**PENDING.** Полученное поручение «запусти G5» разрешает эту проверку и новые
изолированные fictional данные. Оно не принимает T2. Историческое «принимаю»
относится к T1; T1 не открывалась заново. Отчёт не заменяет слова владельца.

## next

solmax — Product G5 REPORT HOME на исходный engineering CALL. Передать PASS
и exact review commit владельцу/Direction для их следующего решения.
Этот отчёт не закрывает T2/M1, не создаёт successor и не запускает T3.

END_OF_FILE: docs/g5/m1-packs-20260909/G5-REPORT.md

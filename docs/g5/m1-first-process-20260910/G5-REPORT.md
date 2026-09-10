# Binding fresh physical G5 — M1 / T4

## outcome

**PASS по всем трём done_when T4. Одно неблокирующее замечание P3 к упаковке
evidence; поведенческих дефектов в проверенном объёме не обнаружено.** Это verdict
отдельной физической refutation, не авторский pre-pass, не owner acceptance и не
закрытие Direction T4/M1. `next: solmax`.

Проверка 2026-09-10. Авторская задача: `01a08a2a-1109-7211-8aa0-17cc639cf1d7`.
Review task: `01a08a4d-cc87-7be2-929a-1b28d577bc63`, подтверждённая
`CODEX_THREAD_ID`. Авторская история не загружалась; предмет получен из exact
candidate и названных источников. Разрешение запуска G5 — переданные владельцем
слова «запусти g5» после Product REPORT. Действующий Direction AGENTS требует
физической отдельности, не определённого model/provider. Helpers не запускались.

## evidence

### Точный предмет и изоляция

| Роль | Commit |
|---|---|
| Accepted T3 basis | `4e892153200d6fa0b1ef3add0bfeceae06b23331` |
| PLAN/baseline, до BUILD | `ae7a809a4055f31b5da1a9920b508f3e6f13d474` |
| Source / baseline B перед вторым | `b1e0853f9b405e2910f2085dae6fd7f6100ba009` |
| Проверенный candidate | `46718e4da82810e57ba7126c8ec3ef0fc4f57268` |

Review worktree: `C:/my_global_workflow/ebf7/zaratustra`; ветка
`codex/g5-m1-first-process-20260910`. Начальный detached HEAD приложения
`512c7a1657aee9295a1e2e826eb3abc698d05fd8` не проверялся как candidate. На preflight
копия чиста, STOP/STEER отсутствовали, имя ветки свободно. Candidate AGENTS.md и
validation.config прочитаны через Git до переключения. Создана новая ветка от
точного candidate. PROBA / pin36 / stamp36; re-sync и OPORA отсутствуют.

Отдельный Git index: `C:/projects/zaratustra/.git/worktrees/zaratustra2`.
Object database общий, рабочие файлы, index, venv, scratch и confirmations отдельные.
Это Git worktree, не копия пользовательской установки. Авторский checkout
`C:/projects/zaratustra/_scratch/m1-first-process-20260910` только читался:
HEAD остался candidate, status clean. Его CRLF CALL прочитан для разбора finding.

Новая `.venv`, cache `_scratch/g5-environment/uv-cache`, managed CPython 3.13.7.
Actual pytest basetemp:
`C:/my_global_workflow/ebf7/zaratustra/_scratch/g5-native-deliver-01`.
Существование, реальные test directories, containment и git-ignore проверены
в `evidence/retained-checks.json`. Использовано
`PYTEST_ADDOPTS=--basetemp=_scratch/g5-native-deliver-01` с `/`.
Все собственные fictional workspace находятся внутри review `_scratch`.

### Попытки опровергнуть done_when

| Критерий | Попытка опровержения и наблюдение | Verdict |
|---|---|---|
| 1. Первый Process из заранее выбранной существенно разной пары, правила вне Core, T2/T3 | Проверены ancestry и PLAN bytes: выбор finite lot / recurring signal уже в PLAN, fictional_lot отсутствует на PLAN commit. Прочитаны pack, host, публичный runner/read contract, relevant Core guards и tests. Правила двух отметок и digest находятся в `src/zaratustra/fictional_lot/pack.py:89`; T2 принимает только immutable Work и verified bytes, T3 — scoped metadata. Полные path/mode/blob деревья Core и process_packs равны T3 basis, PLAN, source и candidate. Затем правила атакованы через настоящий Core: неполная inspection, отсутствующая/несовместимая registration, unknown и closed stage отвергнуты без изменения footprint. | **PASS** |
| 2. Проверяемый сохранённый результат, bounded Work grounds и Mutation API, exact inputs/outputs/version | Новый source replay дал release, Results на11/18, cancel на19. Собственный host дал discard с иначе сериализованной inspection. Digest от тех же JSON значений в других bytes отвергнут. Проверены отдельные полномочия metadata/context/mutation, сохранение неудачных наблюдений в обоих Results, inherited refs без чужого Result header в selected metadata, stale/revoked/path-bound refusals, семь ответов и read-only footprints. Авторские snapshots восстановлены через restore_snapshot, Context bytes и fingerprints совпали при apply_mutation из retained wheel. | **PASS** |
| 3. Воспроизводимая baseline B и способ сравнения W17/W20; нет заявления полноты M1 | Архивы source/baseline/state и wheel независимо сверены по CRC, SHA256, directory inventory и Git blobs. Все40 package files wheel совпадают с source; wheel исполнил полный release. B фиксирован до второго, обе формулировки P§30/P§40 сохранены. PLAN требует повтор обоих разных сценариев в одном host/registry и полный diff при T5; T6/T7 остаются открыты. CALL hash mismatch разобран отдельно ниже: source/state baseline от него не зависит. | **PASS** |

Hash equality используется только как доказательство неизменности bytes, не как
самодельный source scanner поведения. Поведенческое основание — native tests,
исполнение public APIs, точные requests/receipts/context/history и попытки отказов.

### Собственные исполнения и сохранённые попытки

| Запуск | Результат / raw |
|---|---|
| `uv sync --locked`, attempt01 | Sandbox не дал прочитать managed Python directory; exit2. `evidence/uv-sync-01.txt`. |
| `uv sync --locked`, attempt02, reviewed escalation | PASS, 24 locked packages; `evidence/uv-sync-02.txt`. Новых зависимостей не вводилось. |
| `uv run --locked python -m tools.check --deliver` | **PASS**, exit0, **217 tests / 67.31s**, 8 contracts, build/hygiene/types/report presence PASS. `evidence/native-deliver-01.txt`. Это собственный обязательный native run. |
| `tools.probe_first_process --output _scratch/g5-source-01` | PASS release; `evidence/source-scenario-01.txt`, `source-scenario.zip`. Author helper provenance сохранена как часть exact reproduction; это не приёмка. |
| `verify_candidate.py.txt` | 426 byte checks; два первоначальных различия сохранены в `candidate-byte-checks.json`: реальный CALL line-ending finding и слишком широкий scope сравнения source.diff в собственном audit. |
| `refute.py.txt _scratch/g5-refutation-01` | Остановился на собственном неверном ожидании `invalid_work` для cancelled context. Реальный Core корректно вернул `permission_denied`. Source script и полный stopped trial сохранены: `refute-attempt-01.py.txt`, `refutation-01.txt`, `refutation-01.zip`. |
| `refute.py.txt _scratch/g5-refutation-02` | PASS, **64 named checks**, включая вспомогательные проверки, не64 уникальных сценария. `refutation-02.txt`, `refutation-02.zip`, `refutation-checks.json`. Исправлены только ожидания собственного script: cancelled→permission_denied; stale mutation→conflict по существующему контракту. |
| `retained_replay.py.txt` | PASS, **21 named checks**: исходные snapshots, loaded wheel paths, replay, точная причина CALL mismatch, scoped source.diff и actual basetemp. `retained-replay-01.txt`, `retained-checks.json`, `retained.zip`. |

Первый `git switch -c ... candidate` встретил sandbox denial `index.lock`; штатный
reviewed escalation создал только запрошенную review-ветку. Required tools не
подменялись. Неудачные попытки сохранены, лимит трёх не превышен. Никакого
исправления product source/tests/authority/evidence здесь не производилось.

### Проверка поведения и оснований

В source replay inspection SHA256
`e9713526f4c6a5be58f911d6bba578bcbe4384fad7f077bdc9d843e11c1e0312`,
disposition `baa2a2877997bf1a3567eb17c279053873c4b5f35d7656a73089e28a593a10cb`.
Results: `a53cb7f3-9c73-45fd-865e-fcdb9ff15e4e` на11 и
`1124aa90-79dd-44fb-a1c4-feb0c07a4c7e` на18; final revision19.

Собственный host использует отдельный actor `independent-G5-reviewer` и G5
source_ref, публикует bytes через `apply_mutation`, передаёт Handoff через public
`handoff_request` и запрашивает T2 `propose_result`. Для каждого изменения сохранены
request, exact confirmation, content, receipt и before/after footprints. Bootstrap
идёт штатно через init/migrate/create_initial_records. Прямых DB/state Markdown
edits нет.

Новая inspection имеет SHA256
`4c1119dfc48d9e2fe712e0bc7b1e63389930279129ffc0fc4b0409f1e964904d`;
discard disposition — `4e7324a0ead1005489f1cc620b3b9790fb42b4932cbba6aae7e8e17f071edf75`.
Неполная inspection и неправильная disposition остаются принятыми наблюдениями
в history/Result closure. Отказ правила сам не пишет состояние и не стирает их.
Digest связывает решение с конкретными inspection bytes, но не выдаёт authority.

Конечность сценария подтверждается двумя done Works и одной cancelled Work без
completion_id. До cancel внешний reader считает closed continuation blocked;
после cancel доступны0 Works и0 решений, Results2. На отдельной восстановленной
копии ready closed Work ей дано собственное наблюдение: package всё равно
возвращает `lot_closed`. Это вспомогательная refutation, не изменение пустого
terminal continuation основного сценария. Core не получил новый terminal API.

Selected-only metadata не раскрывает header первого Result, однако отдельный
точно подтверждённый ContextQuery получает разрешённые inherited references,
включая обе inspection observations. ProcessQuery caller отвергается как caller
ContextQuery и MutationRequest. Вызов mutation без caller также отвергнут.
Stale, revoked и чужой path дают envelopes без данных/counts; empty scope не
раскрывает идентификатор скрытой Work. Все ответы сохраняют свой revision.

Авторские inspection/disposition snapshots восстановлены из `scenario.zip` в
новые review пути. Nested archive hashes, bytes/layout, exact context и replay
проверены самостоятельно. Replayed revisions11/18; fingerprints соответственно
`547234cd4e9204d8a3a36659c1c157b8b84466d807928c4a1d4e0caf194b9e93` и
`b86e800519eeafc0ca77f6ca5a7337bd675cfc84914068eb31810096b2bbaf6a`.
Старые path-bound confirmations не использованы для mutation в новом пути;
новые G5 confirmations сохранены. Исторические timestamp/DB hashes после нового
исполнения не объявляются побайтно равными; сравниваются предусмотренные контрактом
request fingerprint, revision, context bytes и сохранённые grounds.

### Actionable finding G5-F01 — P3, неблокирующий

**`docs/m1-first-process/evidence/manifest.json:13` содержит hash CRLF CALL, которого
нет в committed candidate после LF-нормализации.** Строка14 также содержит размер
11565 вместо11464. На свежем checkout буквальная проверка outer manifest не проходит
для `CALL.md`: expected SHA256
`5c0b4674c59b67c9e80e8e6f7ee6a89101d4cd3ef61863b0edc672b2ee8ff054`, actual
`52c6a45de5b86b4710fd1df0155b0393b389bf33761758478463fe549d07ab4f`.

Доказательство: `candidate-byte-summary.json`, первые проверки
`retained-checks.json`. В read-only авторском checkout CALL действительно содержит
ожидаемые CRLF bytes; преобразование committed LF→CRLF даёт в точности ожидаемые
SHA256/size. Авторизация и текст не различаются. Остальные outer entries, RESULT,
архивы, source manifests и wheel проверены без такого исключения.

Рекомендуемое исправление в отдельной разрешённой follow-up ноге: сохранять
manifest из committed Git blobs либо нормализовать текст до digest и проверить
его после fresh checkout. Прежнюю квитанцию и это наблюдение сохранить. Здесь
candidate manifest не исправлен. Finding не опровергает done_when: exact
source/inputs/outputs/state/baseline воспроизводимы; затронут один authority text
artifact с доказанно одинаковым содержанием. Буквального PASS всей outer manifest
эта G5 не заявляет.

Второе первоначальное различие byte-audit не является finding продукта:
`source.diff` создан retained generator с явным scope src/tools/tests/AGENTS/
pyproject/lock/inputs. Этот exact scoped diff совпал. Самостоятельные полные
`basis-to-source.diff` и `source-to-candidate.diff` сохранены для проверки всех
добавленных документов/archives; PLAN проверен отдельно из Git.

### W15–W20, placement и смысл второго процесса

| ID | Диспозиция этой G5 |
|---|---|
| W15 | Accepted T2 сохранён: exact immutable binding, missing/incompatible refusal, continuation с тем же binding, proposal без authority. |
| W16 | Accepted T3 сохранён: семь scoped ответов, explicit empty/denied/unavailable, отдельный selected context, inherited grounds, revision и read-only behavior. Native повторяет также ранее существующие T3 проверки согласованности. |
| W17 | T4 не меняет Core/process_packs bytes относительно accepted T3. Baseline B фиксирован. Одна workspace на Process, одна установка/registry/контракт, отдельный revision для каждого ответа. Собственная проба двух экземпляров lot подтверждает path/state isolation, но не доказательство двух разных процессов. P§30 «без изменения основной семантики Core» и P§40 «без изменения Core» сохранены. Proof C остаётся T5/T7. |
| W18 | До BUILD выбрана существенно разная пара: finite conjunction gate + явное evidence-bound решение против recurring observe/compare с переключением по одному changed событию и открытой следующей Work. Различие затрагивает правило, форму переходов и конечность, не только названия. Первый реализован; второй только PLAN, его фактическая достаточность ещё проверяется в T5/T7. |
| W19 | Общий renderer остаётся T6. JSON evidence одного Process не выдано за обзор двух. |
| W20 | Exact T4 source/wheel/input/state/receipts/rollback воспроизведены. Способ сравнения B→T5 есть. Полное сравнение двух процессов и обзор остаются T5–T7. CALL manifest finding сохранён отдельно. |

Placement согласуется с принятой единицей T3 — один ProcessQuery/одна workspace.
Будущий host обязан использовать один registry с обоими полными пакетами, явный
список workspace и отдельные authorizations. Между workspace не обещана общая
транзакция. Раздельные DB не объявлены двумя продуктами, а количество файлов не
объявлено архитектурным доказательством. Гарантии нельзя переопределить переносом
baseline после появления второй реализации.

## assumptions

Trusted local Python/host и существующая W21 модель. Разрешение на review относится
только к новым fictional workspace этой копии. Пользовательская установка и данные
не доступны разработчику. Источники Direction читались только по указанным CALL
путям: актуальные AGENTS, NOW/CHARTER/cards, shape/converge, P§§8/30/40/43,
accepted T3 close и границы independent use. Это не новая owner acceptance.

## cuts

Новых scope cuts нет. Не проверяется hostile same-user Python sandbox,
power-loss/exhaustive concurrency или независимая пользовательская установка.
Wheel запущен через zipimport с locked dependencies, что явно видно по module
paths. Настоящий второй Process/T5, renderer/T6, итоговый T7/Proof C и полнота M1
не реализованы и не объявлены выполненными. M0 остаётся partial. Work8, его
инструкции/inputs, original attachment и archive/** не читались/не искались/
не повторялись. live/** не изменялся. Merge/push/remote publication отсутствуют.

## cost

Одна отдельная G5 задача; один native Deliver, один source replay, два собственных
refutation attempts, один retained-wheel/restore run, byte audit и его разбор.
Использованы имеющиеся managed runtime/dependencies, новых внешних прав/платных
сервисов нет. Денежная стоимость и tokens не измерены. Ошибочные ожидания reviewer
и sandbox attempts сохранены отдельно от product findings.

## manual-acceptance

**pending.** Слова «запусти g5» разрешают проверку, не приёмку T4. Эта G5 не закрывает
Direction task/node. README/RESULT candidate, где G5 pending, остаются исторически
неизменными; актуальный reviewer verdict находится только в этом review пакете.

## next

solmax

HOME получает отдельный локальный review commit с PASS трёх done_when и G5-F01.
Owner acceptance T4 остаётся pending. Эта задача не выдаёт и не запускает T5 CALL.

END_OF_FILE: docs/g5/m1-first-process-20260910/G5-REPORT.md

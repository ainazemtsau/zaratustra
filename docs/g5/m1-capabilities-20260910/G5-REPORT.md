# Fresh physical G5 — M1/T3

**Verdict: PASS по всем трём исходным done_when T3.** Найденных дефектов продукта нет.
Это независимая попытка опровержения точной версии, а не приёмка владельцем и не
закрытие Direction T3/M1. Owner acceptance T3 остаётся **pending**, M0 — partial.
Возврат HOME на `c-solmax-zaratustra-m1-capabilities-20260909-exec`; **next: solmax**.

## Предмет и физическая независимость

- Review task: `01a089d2-1faa-78f2-a543-47a480b1744b`.
- Авторская/source task: `01a086ca-b1ad-7692-a503-4f4b3bcfa8f9`.
- Новый app-managed checkout: `C:/my_global_workflow/ba2e/zaratustra`.
- Начальный detached HEAD: `512c7a1657aee9295a1e2e826eb3abc698d05fd8`, status чист.
  Этот HEAD не был объектом review. После чтения candidate AGENTS/validation через
  `git show` создана свободная ветка `codex/g5-m1-capabilities-20260910`.
- Reviewed candidate: **`73ee71a3282291592040083df64adc9c6567eeda`**.
- Implementation/source: `d0cb354807ab16b1d917d500a4e3d1d46f59ad3e`.
- PLAN/baseline: `9eb43fabc029931148355007f156123156fcb90b`.
- Принятая T2 basis: `a5efbb15c7c39e52072f4fb1593a294ebe109a80`.
- Product 0.9.0 / schema 7 / engineering contract 36 / PROBA.

Ревьюер не участвовал в реализации или подготовке авторского evidence. Подагенты
не запускались. Физическая identity получена из `CODEX_THREAD_ID`; checkout,
ветка и source проверены Git. [isolation.json](isolation.json) фиксирует изоляцию,
команду native и точное значение PYTEST_ADDOPTS. Source
`C:/projects/zaratustra/_scratch/m1-capabilities-20260909` не переключалась и не
менялась; начальный и конечный HEAD равны candidate, status чист.

STOP/STEER здесь и в source отсутствовали. Git index.lock и uv cache сначала
отказали в sandbox; штатные escalation были одобрены средой. Для read-only Git
source использован разовый `-c safe.directory=...`; global config не менялся.

## Три исходных done_when

| Строка CALL | Verdict | Независимая попытка опровержения и разрешимое evidence |
|---|---|---|
| 1. Current status, attention, open decisions, available/blocked Works, recent important Results, context requirements через единый контракт | **PASS** | Собственный Reader получает настоящий Core ProcessMetadata из retained wheel и возвращает все семь значений. Ready → metadata choice → ready → настоящий Result/next меняют ответы на соответствующей revision. Available сравнивается с полным authoritative Work; attention/decision/blocked согласованы; header Result сверяется с совершённой операцией. `independent-04.zip!reads/{ready,blocked-current,continued}/`, `events/`, `open-work-oracle.json`; именованные проверки в [independent-04-checks.json](independent-04-checks.json). |
| 2. PLAN empty/denied/unavailable, revisions/scope, metadata/counts, authoritative consistency, отсутствие чужого контекста | **PASS** | Empty scope без hidden Work ID; строгие counts возвращённых списков; exact type/query/path authority; missing/version/incompatible/reader/unsupported; invalid selections; stale revisions; terminal и revoked rights; отдельный ContextQuery; inherited grants и отказ на реальную forward foreign reference; пропавшие/изменённые bytes; final revalidation после успешного и падающего adapter; отдельный managed writer OS process. `independent-04.zip!reads/`, `concurrency/`, `fault-workspace/`; полная матрица ниже. |
| 3. Exact version/checks сохранены; ответы derived, без второго state и готовых M2+ | **PASS** | 21 авторский evidence-file прошёл exact SHA256/size; source/candidate product одинаков; Python inventory retained wheel и fresh build одинаковы, 37 protected files совпали с basis; baseline wheel/trial сохранены до source. Настоящие Core read/Result/repair на законно восстановленных копиях. Native deliver PASS. Без изменений DB/layout на обычных reads/refusals. [protected-bytes.json](protected-bytes.json), [audit-01-checks.json](audit-01-checks.json), [audit-dispositions.json](audit-dispositions.json), raw native и manifests. Отличия переводов строк старых raw честно выделены ниже. |

Исходные строки сверены с Product CALL и HOME
`live/solmax/cards/t-zara-m1-capabilities.md`. Авторские tests/readout — input
evidence, они не использовались как самостоятельный verdict. Независимый runner
не вызывает `tools.probe_capabilities` и не импортирует его FixtureReader/tests.
Он использует public Core/pack APIs; из прежних tools переиспользованы только
restore/retain и fictional lifecycle rule для реального Result. Никаких SQL или
state Markdown edits ради PASS нет.

## Проверки и сильные контрпримеры

**Native:** `uv sync --locked` PASS после одного sandbox refusal;
`uv run --locked python -m tools.check --deliver` **PASS**, 204 теста за 51.82 s,
ruff format/check, mypy (59 source files), 6 import contracts, wheel/sdist build,
hygiene и report structure. [raw/check-deliver-02.txt](raw/check-deliver-02.txt).
До native установлен `PYTEST_ADDOPTS` с новым
`_scratch/g5-m1-capabilities-20260910/pytest-deliver-02` именно этой worktree;
существующая папка отвергалась до вызова pytest. Использован относительный путь
на `/`; фактическое размещение проверено после завершения. После этого native
source/tests/validation/RESULT не менялись. Первый native имел ошибку изоляции,
описанную ниже, и не является итоговым доказательством выполнения run contract.

**Independent:** [raw/independent-04.txt](raw/independent-04.txt),
[summary](independent-04-summary.json): **240/240 именованных проверок PASS**.
Число включает вспомогательные проверки семи полей, counts и footprint; это не
240 различных сценариев. Исполнение Core шло непосредственно из сохранённого
`zaratustra-0.9.0-py3-none-any.whl` с locked dependencies; путь модуля и SHA256
зафиксированы в [runtime.json](runtime.json). Это не независимая установка wheel
в отдельную среду: используется zipimport retained wheel в подготовленном venv.

| Граница | Контрпример / полученный результат | Путь внутри independent-04.zip |
|---|---|---|
| Scope/metadata/counts | Пустая область; hidden completed Work и её Result; revoked hidden member против явного включения; отозванный anchor даже при empty scope. Hidden ID не попадает в metadata; один revoked visible member отвергает весь ответ без envelope/data/counts. | `reads/empty-scope`, `next-only-metadata`, `revoked-mixed-scope`, `hidden-revoked`, `revoked-anchor` |
| Authority | Caller на ContextQuery не разрешает ProcessQuery; metadata caller не разрешает context; изменённый budget разрушает digest. Wrong process/workspace/unknown visible ID не вызывает reader. Wrong workspace отклоняется уже при prepare_authorization. | `reads/context-auth-as-metadata`, `metadata-auth-as-context`, `changed-query`, `wrong-*`, `unknown-member` |
| Revisions | Старая query после реального изменения requirements даёт conflict; текущая отражает блокировку. Семь ответов имеют одну revision. | `reads/stale`, `blocked-current`, `continued` |
| Package lifecycle | Missing exact version, v99-only, incompatible state, no reader и unsupported различаются с supported empty. Reader exception не раскрывает private error text. | `reads/missing`, `other-version`, `incompatible`, `missing-reader`, `unsupported`, `reader-exception` |
| Selections | Foreign notice/Result; overlap, missing active Work, duplicate available/notice; terminal в available; подменённый hash inherited requirement. Возвращается invalid_read_response, без partial values. | Одноимённые `reads/` |
| Selected context | Full output равен отдельному public open_work. Другая выбранная Work даёт scope; terminal допускает metadata, context denied. Requirements/query mismatch даёт requirements_changed. | `reads/ready`, `terminal-metadata`, `wrong-selected-context`, `requirements-mismatch` |
| Inherited против foreign | Next-only metadata скрывает источник, но отдельно разрешённый context содержит точное законное inherited основание. Grant сохраняется после revoke источника. Реальный опубликованный artifact следующей Work не может стать требованием прошлой Work. | `reads/next-only-inherited`, `explicit-inherited-ref`, `revoked-source-inherited-context`, `real-foreign-requirement`, `events/` |
| Budget и недоступные bytes | Успешный ответ на точной длине; длина минус 1 и budget=1 отказывают целиком. Missing и same-size changed content оставляют requirements с unavailable context. | `reads/exact-budget0`, `exact-budget-1`, `budget-one`, `missing-bytes`, `changed-bytes` |
| Final revalidation | Callback после initial collection переименовывает обязательный blob. Весь response становится dependency_changed; то же при последующем exception reader. Никакого content_base64/partial metadata response. | `reads/late-byte-loss`, `late-loss-and-reader-error` |
| Managed concurrency | Reader запускает второй OS process, тот отмечает вход перед apply_mutation(revoke_work) и остаётся заблокированным внутри read callback. Reader получает coherent revision7/context; writer затем коммитит revision8; новое чтение denied. | `concurrency/`, `reads/concurrent-reader`, `revoked-current` |
| Derived/read-only | До/после обычного чтения или отказа сравниваются SHA256 всех файлов и полный directory layout, плюс сохраняются authoritative state/history. Intentional byte faults и concurrent mutation помечены отдельно. | `reads/*/footprints.json`, `state-before.json`, `history-before.json` |

Fault injection — контролируемый trusted callback с замыканием на выбранный blob
в новой fictional папке. Core не передавал reader путь или права. Это проверка
реального late revalidation, а не демонстрация hostile Python sandbox, OS crash,
power loss или всех возможных гонок. Corruption исправлена через отдельный exact
`restore_artifact` Core request с receipt. Для rename fault возвращён тот же
сохранённый blob; DB/state Markdown не редактировались. Два OS-процесса здесь —
reader/writer **одного Process**, не два полных M1 Process.

## Persisted evidence и диспозиция исходных failures

[audit-01.zip](audit-01.zip) и [raw/evidence-audit-01.txt](raw/evidence-audit-01.txt)
содержат 17 первичных byte/evidence проверок: 14 PASS, 3 несовпадения исходных
предположений ревьюера. Они не переписаны. [audit-dispositions.json](audit-dispositions.json)
закрывает все три на проверяемых bytes:

1. Source→candidate действительно docs-only; первоначальный whitelist моего
   audit забыл `README.md` и архив `docs/results/m1-packs-20260909.md`.
   Архивный T2 RESULT точно равен source RESULT; executable/rules/tests/authority
   и lock candidate/source одинаковы.
2. `baseline-check.txt` и `baseline-packs.txt` не byte-identical PLAN→candidate:
   LF заменён CRLF; содержание побайтно одинаково после удаления только CR из
   CRLF. Исходные **обе** версии и hashes сохранены в `evidence/plan-*` и
   `evidence/candidate-*`. Не заявляется неизменность этих двух raw между commits.
   Baseline wheel и trial ZIP byte-identical PLAN→candidate, история PLAN сохранена.

Дополнительно audit проверил линейную связь basis→PLAN→source→candidate, wheel
RECORD/digests, отсутствие новых dependencies, exact source.diff, author runtime,
соответствие десяти persisted ответов сохранённым query/state и восстановление
авторского final snapshot в новую папку через restore_snapshot. Final snapshot
сохранил exact bytes/layout. Все пять наших attempts заархивированы вместе с
restored evidence; manifests учитывают каждый файл и directory inventory.

**Авторский execution issue:** native-01 был прерван из-за отсутствия явного
scratch basetemp. Raw обрывается после 70% pytest, не содержит итогового PASS.
Точный default temp path автором не записан; полную изоляцию того запуска G5
не устанавливает. Native02/Deliver автором заявлены с explicit fresh scratch
basetemp; их raw завершаются PASS, но сами raw tools.check не печатают environment.
Новый G5 native подтверждает поведение на exact candidate с отдельно записанной
basetemp. Исторический issue не исправлен задним числом и не скрыт.

**Наши attempts:** independent-01 ошибочно ожидал одинаковый manifest schema,
independent-02 не обработал ожидаемый ранний invalid_work для foreign workspace,
independent-03 забыл отдельный authorize_artifact перед публикацией next Work.
Core корректно отказал `permission_denied`. Три retries после initial attempt;
independent-04 завершился. Каждый прежний raw/script/частичная fixture сохранены
под своим номером. Повторения не меняли candidate и не подменяли Core механизм.

**Наш native-01: ошибка изоляции.** Я задал абсолютный Windows-путь без защиты
обратных слешей. Pytest разобрал PYTEST_ADDOPTS через shlex и потерял `\`, создав
папку `my_global_workflowba2ezaratustra_scratchg5-m1-capabilities-20260910pytest-deliver-01`
в корне собственной review worktree, вне ignored `_scratch`. 204 tests/native
завершились успешно, но инструкция размещения не была выполнена. Это обнаружено
при final Git status до коммита. Папка целиком, без удаления, перемещена в новую
`_scratch/g5-m1-capabilities-20260910/pytest-deliver-01-misparsed-retained`; перед
Move-Item проверены оба абсолютных пути внутри review workspace. Сохранены
raw, первоначальный isolation record, [native-isolation.json](native-isolation.json)
и [manifest 2569 файлов](native01-retained-files.json). Итоговый native-02 повторён
с новым относительным POSIX basetemp: actual folder внутри ignored `_scratch`
проверена, 204 tests/весь deliver PASS. Source/чужие папки не затрагивались.
Первый finalizer также остановился на моём неверном имени API inspect_workspace;
script/raw сохранены, для публичного чтения использован существующий read_workspace.

## Сохранённые ограничения W15–W20

- W15: принятая T2 exact lifecycle сохранена; новые чтения не дают permission,
  отсутствующий пакет не подменяется latest, Result/next сохраняют exact binding.
  Историческое T2 pending не открывает принятую и закрытую HOME T2 заново.
- W16: T3 контракт и перечисленные PLAN cases получили независимый PASS выше;
  owner acceptance всё ещё pending.
- W17: это общая additive read-подготовка. Обе гарантии сохраняются дословно:
  P§30 «без изменения основной семантики Core» и P§40 «без изменения Core».
  Финальный placement, baseline перед вторым Process и Proof C не доказаны T3,
  остаются T4/T5. Изменение Core сейчас не выдается за уже пройденный Proof C.
- W18: полная существенно разная fictional пара и её scenarios остаются T4/T5.
- W19: общий renderer остаётся T6; этот Python API не предъявлен как готовый обзор.
- W20: exact T3 evidence сохранено; сравнение обоих полных сценариев и общая
  проверка остаются T4–T7.

Сверены HOME P§§8/30/40, shape T3, C03/C04/C05 и поздняя квитанция приёмки T2.
Нет нового owner concept, OPORA gates, CI/CD, уведомлений, M2+ prerequisite,
платных/внешних прав. Work8/original attachment не читались и не повторялись,
Direction archive/** не читался. Live/** и кандидатные source/tests/spec/rules/
validation.config/RESULT.md не менялись.

## Возврат

Outcome: G5 PASS; findings: none; blocked: none. Assumptions: trusted local Python,
один Process/workspace, исторические ответы требуют нового чтения. Cuts: новых нет.
Cost: одна physical review task, без подагентов/новых расходов; два native PASS
по тестам, из них только второй удовлетворяет scratch isolation;
четыре independent attempts и отдельный evidence audit. Полные token/cost не измерены.
Manual acceptance: **pending**. Следующий владелец результата — Solmax; successor
CALL/T4 не создавался. Review commit — docs-only commit, содержащий этот отчёт и
receipt; точный SHA передан в финальном handback. **next: solmax**.

END_OF_FILE: docs/g5/m1-capabilities-20260910/G5-REPORT.md

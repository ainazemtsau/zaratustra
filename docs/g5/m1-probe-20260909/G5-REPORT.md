# Fresh binding G5 — M1 / T1 probe

Технический verdict: **PASS в границах T1**. Попытки опровергнуть узкое K1
не выявили дефекта: два разных правила исполняются вне неизменённого Core
через реальные open_work, Mutation, Result и Work. Это раннее свидетельство
исполнимости контраста, а не доказательство полного контракта M1.

Product candidate: `f917565e141804508c11954c5de51566e82c48ca`.
Source implementation: `fc32c8dcf79d88e2799e061638ad7b51ff94a98c`.
Общая подготовка + batch: `eeb5da071aa610b41ddf353f84db6a1da0fae076`.
Basis: `a6e6a2e5be90eed111504712c7443b8a907576c1`;
его прямой родитель: `05047e38acc7386484223a5feacc510b015b2a85`.

Проверяющий — новая физическая Codex task
`01a08622-47fd-7d82-974e-15ef8e1f2263`, не подагент и не авторский чат.
Запуск по переданному прямому запросу владельца «запусти g5»;
dispatch task `01a08602-60e0-7ff2-ab16-92fd333aa4a4`.
Review worktree: `C:/my_global_workflow/943d/zaratustra`.
Review branch: `codex/g5-m1-probe-20260909`.
До проверки чистая новая detached-копия была переключена с setup `512c7a1`
на exact candidate. Ни setup, ни чужая execution-копия не использовались
как проверяемый продукт. STOP/STEER отсутствовали при всех запусках.

Authority: исходный engineering CALL
`C:/my_global_workflow_worktrees/solmax/live/solmax/work/calls/c-solmax-zaratustra-m1-probe-admission-20260909-exec.md`,
product AGENTS, validation.config и docs/m1-probe/PLAN.md. Pin 36, PROBA.
Для границы G5 прочитаны Direction AGENTS, KERNEL и play work; T1/shape,
P §§8/30/40 и knowledge о делегации сверены read-only. Их exact hashes:
`raw/authority-sha256.json`. Это product review реализованной пробы;
converge-verify спецификации здесь не проводилась.

## Разложение исходных done_when и verdict

| CALL | Самостоятельный критерий проверки | Verdict и evidence |
|---|---|---|
| 1 | Два fictional правила имеют наблюдаемое различие на правильном M0; до зависимого прогона определены T1-ответы W15/W17/W18 и exact evidence W20, остальное сохранено open. | **PASS.** PLAN уже содержится в first-source commit eeb5da0 и неизменён до candidate. Его решения предшествуют retained runtime на clean eeb5da0 и fc32c8d. W15 — explicit Python rule + Work binding/phase; W17 — неизменный Core и отдельный baseline второго; W18 — conjunction против persisted alternating phase; W20 — commits, exact inputs/state и pre-submit backup. Семантическое различие воспроизведено независимо; `raw/behavior-checks.json`, `raw/audit-checks.json`. |
| 2 | На настоящих общих механизмах проверить правильный источник observation, фазу, proposal/authority/revision, один эффект и точное продолжение; сопоставить execution с source и diff. | **PASS.** 41 независимая группа проверок, включая три восстановления; 34 отрицательные попытки оставили DB bytes, records и history без изменения. Собственные inputs/requests/confirmations/receipts/contexts/states сохранены в `behavior-evidence.zip`. Core, CLI/local, прежние Core tests, lock и authority-файлы идентичны базе. При добавлении cycle runner и batch также идентичны. Оба сохранённых diff воспроизведены byte-for-byte. |
| 3 | Ограниченный честный verdict, обязательный полный native check, проверяемые exact manifests и законное восстановление без потери evidence; owner acceptance не выдумана. | **PASS для технического handback; owner acceptance PENDING.** На candidate `uv sync --locked` и полный `tools.check --deliver` PASS: 148 tests / 33.21s, build, hygiene, types, четыре import contracts, report structure. 19 manifest hashes совпали, 222 файла двух архивов и их layout проверены. Три original pre-submit backup независимо восстановлены и исполнены через Core. T1/M1/M0 этим review не закрываются. |

Строка 3 допускает честный pending по самому CALL. Поэтому технический PASS
не означает завершённую приёмку или завершение продукта в PROBA.

## Почему контраст достаточен только для узкого K1

Batch вычисляет conjunction двух независимых отметок. Cycle читает текущую
фазу из сохранённой Work, требует соответствующую отметку и сохраняет другую
фазу в next Work. На одном input observed=true, recorded=false batch отказал,
а cycle observe продолжился. На record-фазе этот же input отказал; отдельный
accepted observed=false, recorded=true разрешил переход обратно. Успешный
batch тоже реально сохранил Result/next Work.

Таким образом, различаются условие разрешения и переход состояния. Решение
правила влияет на реальное сохранение и последующий context. Одинаковый M0
путь обслужил оба правила; причинная граница добавления второго сохранена
отдельным commit без изменения runner/batch/Core. Для T1 это достаточный
минимальный falsifiable контраст. Он не доказывает «радикально другой Process»
и совместный общий контракт всей M1; требования P§30 «без изменения основной
семантики Core» и P§40 «без изменения Core» сохранены дословно.

Правила здесь являются доверенным Python-кодом. У них нет переданного path
или authorization handle, runner возвращает proposal; права выдаёт отдельный
trusted adapter по данному разрешению на fictional пробы. Изоляция враждебного
Python pack не заявляется. Source/diff анализ подтверждает только размещение
и bytes; поведенческое основание verdict — реальные вызовы Core.

## Независимые попытки опровержения

Harness `independent_probe.py.txt` написан в этой проверке. Он не импортирует
авторские Trial, confirm, proposed, run_case или restore_snapshot и не запускает
tools.probe_m1. Fictional state создаётся через init/migrate/bootstrap и только
публичный apply_mutation; используется штатный retain_trial для собственного
backup. Моки, SQL/DML и правка state Markdown не использовались.

- Проверены отсутствие authority, authority другой workspace, чужой Process,
  ограниченный context, неизвестный binding и неправильный rule для Work.
- Между proposal и submit законной Mutation изменена сохранённая фаза.
  Старые proposal/query отказали по conflict; fresh query прочитал новую фазу.
  Отзыв прав после подтверждения запретил submit и context.
- Подменена цель next Work после точного подтверждения. Submit отказал.
  Предложение без подтверждения тоже отказало; само propose не изменяло DB.
- Несколько own acceptances и разные active versions показали, что используется
  последняя принятая observation, а не последняя публикация. Сохраняются все
  own acceptance ids. Унаследованное основание не выдано за own observation
  новой Work; строковое `"true"` отклонено строгой схемой.
- Для трёх успехов проверены exact result reference и source revision,
  сохранённый request/receipt, source done/completion_id, ровно одна новая
  Work и Artifact, +1 state revision, ready/authority новой Work, все поля
  next Work, SHA исходного artifact и полный SavedResult в следующем context.
- Повтор exact request, повтор с current revision и новый operation id на
  completed Work отказали, не создав второй эффект. Committed Result читается
  через отдельный read_result. Это существующая terminal replay семантика M0.

Собственные success revisions: cycle observe 8→9, cycle record 15→16,
batch 17→18. Отличие от авторских revisions обусловлено дополнительными
законными adversarial операциями. Оно не скрыто под исходным evidence.

## Exact evidence и восстановление

`audit_evidence.py.txt` независимо сверил Git ancestry/objects и 58 protected
source hashes; candidate и implementation идентичны по src/tools/tests/
dependencies/config, а parent M0 и basis отличаются только docs/evidence.
PLAN, runner и batch идентичны между first-source и candidate.

19 записей handoff-manifest совпали с Git objects и checkout bytes без
нормализации. From-M0 diff: 38 945 bytes; second-connection diff: 8 541 bytes;
оба byte-for-byte равны свежему git diff для названных source commits.
First-batch ZIP: 64 файла / 18 каталогов; two-rule ZIP: 158 / 46.
Проверены CRC, SHA каждого файла, полный layout и все вложенные backup manifests.
Runtime и summaries совпали с versions/output. Оба архива извлечены в новые
scratch-папки: реальные read_records/read_history совпали с final JSON.
31 mutation request/authority/receipt сопоставлен с actual history, publication
input bytes — с hash/size запроса и сохранённым Artifact.

В отдельные новые папки восстановлены `two-rule-contrast.zip` members:

| Исходный stage | Restore result revision | Точный fingerprint |
|---|---:|---|
| batch/step-1 | 10 | 845c74ba11031ec45d1dca6dfa591520ddb33a418c5c716ced0437689cbf06a5 |
| cycle/step-0 | 7 | 96f6233f62ee7ba2b9219972436dac140df9b15fdcb1c983488d63672d687f12 |
| cycle/step-2 | 14 | b1d6b647235d3158f3d41e222dcf413004163136fce8f96bf8f376ad4c70f326 |

До submit сверены exact layout/file hashes, read_records/read_history и
byte-identical open_work output с новой authority на новый path. Rule заново
построил exact исходный proposal с сохранёнными ids. Он исполнен обычным
submit_result; совпали fingerprint/revision и следующая фаза, SavedResult
снова доступен в next context. Новые confirmation timestamps/path и created_at
нового исполнения являются новыми фактами; полное равенство after-DB bytes
исходному запуску не заявляется. Исходные ZIP и restored evidence сохранены.

## Оставшиеся границы

W15 остаток: registry, pack/type/instance, missing/incompatible pack и смена
версии начатой Work. W17 остаток: полный M1 baseline, совместное размещение,
весь внешний контракт. W18 остаток: полные сценарии двух существенно разных
M1 Processes. W20 остаток: exact evidence полных сценариев/overview.
W16 (семь capabilities, scope/revisions, empty/denied/unavailable,
metadata/counts/consistency) и W19 (общий обзор) остаются open целиком.
Их answerer PLAN и исходные rewrites сохранены в неизменённом product PLAN.

Отдельные workspace не выданы за сосуществование двух Processes. M0 partial
и предел original attachment сохранены. Work8 не повторялась, запрещённые
root input-файлы и archive/** не читались. Source, production tests, PLAN,
validation.config, исходное evidence, Work3/Work7/author worktree и Direction
OS не редактировались. Новых сервисов, публикации, уведомлений и successor
CALL нет. Обнаруженных product findings нет; все проверенные критерии PASS.
Это проверка на Windows/Python 3.13.7; полный M1 и иные платформы не проверены.

## Команды, стоимость и воспроизведение

Точные команды/exit/raw locators: `receipt.json`; инструкция — `REPRODUCE.md`.
`raw/native-deliver.txt` — полный repo-native run на чистом candidate.
`raw/independent-01.txt` — независимый поведенческий run, с первого раза PASS.
`raw/audit-01.txt` — первая успешная byte/state сверка; `raw/audit-02.txt` —
успешная дополнительная сверка input-to-Artifact и nested manifests.

Access к Git index и uv cache/managed runtime сначала был ограничен sandbox.
Предусмотренная escalation разрешила switch, locked runtime и проверки;
другой продукт/runtime не подставлялся. Прямой вызов venv Python в sandbox
тоже не стартовал; повторён через разрешённый uv. Это infra отказы до
исполнения, не product failures. Неуспешные сообщения сохранены в raw.
Harness не потребовал исправления по runtime failure. Новых зависимостей нет;
денежные/API затраты не измерялись. Полный тестовый suite занял 33.21s.

Отдельный helper упаковки один раз остановился на неверном ожидании формы
`git status`: Git свернул новую папку до `?? docs/g5/`. Guard исправлен на
`--untracked-files=all` с проверкой каждого пути. Raw сохранён как
`raw/package-review-first.txt`; source и behavioral checks не менялись.

Owner acceptance: **pending**. Слов владельца о принятии exact candidate
не добавлено. Binding fresh G5 проведена; технический PASS возвращается
**HOME: solmax** для сверки и отдельной фактической приёмки. Этот product
review не закрывает Direction CALL, T1, M1 или M0 и не выдаёт допуск T2.

END_OF_FILE: docs/g5/m1-probe-20260909/G5-REPORT.md

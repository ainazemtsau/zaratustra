# Product handback — M1 / T1 process-rule probe

CALL: c-solmax-zaratustra-m1-probe-admission-20260909-exec.
engineering_contract: 36; mode: PROBA; next: solmax.

## outcome

Узкая проба process-rules-outside-core-on-real-m0 исполнена. На одинаковом входе
observed=true, recorded=false batch отказывает без изменения DB, cycle в фазе
observe сохраняет Result и следующую Work в фазе record. В этой фазе прежний
вход блокируется; recorded=true позволяет перейти обратно в observe. Batch
с обеими отметками также успешно продолжает работу.

Ограниченный verdict: K1 не опровергнут для этого контраста на двух отдельных
fictional workspace. Предметная ветка Core и перепроектирование основания
не понадобились. Полная M1, совместное размещение процессов и все семь
capabilities этим не доказаны. PROBA owner acceptance остаётся pending.
T1/M1 не объявлены Direction done; T2 не запущена; M0 остаётся partial.

## evidence

- Basis M0: a6e6a2e5be90eed111504712c7443b8a907576c1; его родитель — принятый
  candidate 05047e38acc7386484223a5feacc510b015b2a85.
- Общая подготовка + первое правило: eeb5da071aa610b41ddf353f84db6a1da0fae076.
- Подключение второго: fc32c8dcf79d88e2799e061638ad7b51ff94a98c.
  Оба фактических прогона — на чистом соответствующем commit, runtime сохранён.
- [Exact versions / Git objects](docs/m1-probe/evidence/versions.json),
  [diff второго](docs/m1-probe/evidence/second-connection.diff),
  [полный diff от M0](docs/m1-probe/evidence/from-m0.diff).
  Core, CLI/local, исходные Core tests, uv.lock, validation.config и AGENTS
  имеют те же Git objects во всех трёх версиях; shared runner и batch неизменны
  при подключении cycle. Это проверка bytes; поведение подтверждено прогонами.
- [Наблюдаемые результаты](docs/m1-probe/evidence/contrast-summary.json).
  Exact inputs, context, requests, authority, receipts, histories, before/after
  state и backup находятся в [полном пакете](docs/m1-probe/evidence/two-rule-contrast.zip)
  и [первом прогоне](docs/m1-probe/evidence/first-batch.zip).
  Их manifests: docs/m1-probe/evidence/two-rule-contrast-manifest.json и
  docs/m1-probe/evidence/first-batch-manifest.json. Все hashes/layout сверены
  штатным tools.retain_trial, данные и исходные рабочие папки сохранены.
- Три успешных перехода полного прогона: batch revision 9→10, cycle 6→7 и
  13→14. Каждый повторён из exact pre-submit backup в НОВОЙ папке с тем же
  запросом, новыми полномочиями на точный путь и тем же fingerprint результата.
  Восстановление не изменяло DB/Markdown вручную и не стирало исходный опыт.
- Проверка новых файлов: 8 tests PASS, build/hygiene/types и 4 import contracts
  PASS; docs/m1-probe/evidence/check-second-focused.txt. Это focused evidence.
  Итоговый полный `uv run --locked python -m tools.check --deliver`: PASS,
  148 tests / 35.86s, native build/hygiene/types, 4 import contracts и report
  structure; полный вывод docs/m1-probe/evidence/check-deliver.txt.
  Источник тот же fc32c8d; последующие изменения — только отчёт/evidence.
- Новые тесты обоих правил используют реальный Core: отсутствие/подмена
  подтверждения, stale context, чужой Process, неизвестный binding, изменение
  revision между proposal и submit, повтор completed Work и сохранность при
  отказе. Recovery читает saved Result; повтор done Work штатно запрещён M0.
  Подагенты/новая binding G5 не запускались. Это execution evidence и self-check.

## assumptions

Технический PLAN и W15–W20: [docs/m1-probe/PLAN.md](docs/m1-probe/PLAN.md).
Для T1 используется один существующий Process на отдельную workspace, schema6,
явно выбранное доверенным адаптером правило и его probe-v1 binding/phase в
executor_requirements. Это ещё не pack registry/version compatibility M1.
Локальный adapter действует только на новые fictional папки по исходному RUN;
он отдельно выдаёт точные подтверждения чтения/записи. Текст входа, имя правила
и accepted fictional observation не означают owner acceptance продукта.

План сверен с Direction P §§8/30/40, shape T1/K1 и CALL. Конкретная пара входит
в делегированный HOW; новой owner concept/гарантии/прав не добавлено. Обе
формулировки W17 сохранены. До плана отвергнута идея terminal Result без next:
M0 такого завершения не предоставляет; его поддержка здесь не заявляется.

## cuts

Не расширены: T2–T7, полный Process Pack contract, registry/versions/migrations,
missing/incompatible pack, все семь ответов включая empty/denied/unavailable,
scope/revisions/metadata/counts/consistency и общий обзор. Остатки W15/W17/W18/W20,
W16/W19 целиком — open с answerer PLAN и исходными rewrites в PLAN.md.
Новые product templates, реальные процессы, frontend/transport/autonomy,
CI/CD/Actions/notifications, внешние права/расходы отсутствуют. Work8 и original
attachment не читались/не повторялись. Legacy Unicode issue не исправлялась.
Это границы исходного T1 CALL; новых сокращений его трёх done_when нет.

## cost

Один локальный контраст, два source commits. Новых runtime dependencies и
платных сервисов нет. Четыре предварительных validation запуска: первая
ошибка mypy — недостающая аннотация списка в новом тесте; затем 142 tests PASS
и один неверный тест повторной подачи done Work. Ожидание исправлено по
существующему Work7 test_terminal_replay_new_id_and_current_discovery_rights;
Core/старые тесты не менялись. Следующие focused runs: 3 и 8 PASS.
Raw неуспешные и успешные выводы сохранены в evidence; ошибок продукта
этими двумя исправлениями не заявлено. Пробы: один первый batch и один полный
контраст; все завершились без runtime retry, плюс backup replay каждого успеха.
Затраты API/денежная стоимость не измерялись; нового бюджета не назначено.

## manual-acceptance

Pending — фактических слов владельца о точной реализации ещё нет.
Открыть [короткое предъявление](docs/m1-probe/READOUT.md) и сравнить строки:
batch на неполном входе блокируется, cycle на том же входе меняет фазу; затем
cycle требует отметку новой фазы. В каждой успешной строке есть сохранённый
Result/next Work и проверенное восстановление backup.

Повтор из того же скрипта проверки, в этой рабочей копии, выбрав НОВОЕ имя:
`uv run --locked python -m tools.probe_m1 --output _scratch/owner-probe-01`.
Программа не перезаписывает существующую папку. Архивы распаковывать только в
новую папку; исторические absolute paths — provenance, не команды к запуску.
Тестовые local-chat confirmations не выданы за личную проверку владельца.

## next

solmax — REPORT HOME на исходный CALL для сверки exact evidence, получения
owner acceptance и необходимой отдельной свежей binding G5. Этот product
REPORT сам не закрывает Direction CALL/T1/M1 и не создаёт successor.
Execution worktree: C:/projects/zaratustra/_scratch/m1-probe-20260909.
Branch: codex/m1-probe-20260909. Work7/Work3 и live/** не изменялись.

END_OF_FILE: RESULT.md

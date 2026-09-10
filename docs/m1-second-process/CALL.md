CALL c-solmax-zaratustra-m1-second-process-20260910-exec
to: executor
kind: engineering
direction: solmax
node: g-zara-m1-modularity
task: t-zara-m1-second-process
surface: cli
repo: C:/projects/zaratustra/_scratch/m1-test-only-processes-20260910
engineering_contract: 36
mode: PROBA
basis: 2df9b286b3b54ac3fabd07db0e7d9b343bc17850
execution_worktree: C:/projects/zaratustra/_scratch/m1-second-process-20260910
execution_branch: codex/m1-second-process-20260910

goal: |
  Второй существенно другой проверочный Process работает через тот же внешний
  контракт; сохранены сравнение ядра и результаты обоих процессов.
context: |
  Direction root C:/my_global_workflow_worktrees/solmax, пути от live/solmax/:
  NOW.md; CHARTER.md; cards/g-zara-m1-modularity.md; cards/bet-g-zara-m1-modularity.md;
  cards/t-zara-m1-second-process.md; cards/closed/t-zara-m1-first-process.md;
  work/zaratustra-m1-first-process-close-2026-09-10.md;
  work/zaratustra-m1-first-process-owner-acceptance-2026-09-10.md;
  work/evidence/zaratustra-m1-first-process-close-20260910/byte-verification.json;
  knowledge/zaratustra-fictional-examples-test-only-2026-09-10.md;
  knowledge/zaratustra-independent-use-and-practical-development-2026-09-10.md;
  knowledge/zaratustra-plan-conforming-approval-2026-09-07.md;
  work/zaratustra-m1-shape-2026-09-09.md;
  work/zaratustra-architecture-plan-2026-09-05.md §§8/30/40/43;
  work/converge-g-zara-m1-modularity.md W01–W03/C01–C06;
  work/zaratustra-m1-converge-verify-2026-09-09.md.
  Product: AGENTS.md, validation.config, STOP/STEER, ближайшие module AGENTS;
  RESULT.md; docs/m1-first-process/PLAN.md, inputs.json, REPRODUCE.md;
  docs/m1-test-only/PLAN.md, OWNER-DECISION.md, REPRODUCE.md;
  docs/m1-packs/PLAN.md; docs/m1-capabilities/PLAN.md.
  T4 PLAN выбрал finite lot и recurring signal rounds; реализован пока только lot.
  Historical baseline b1e0853f9b405e2910f2085dae6fd7f6100ba009, поправка упаковки
  до второго5b145b8bdfb9239939ca118ebe70542ffbb13b68, report basis2df9b28.
  Fresh G5 original9c9c978 и relocation af1005b; оба сохранены HOME.
boundaries: |
  Только T5; первый процесс сохранить. W15/W16 остаются принятой основой;
  W17/W18/W20 определяют явное сравнение ДО/ПОСЛЕ второго. Сохранить обе гарантии
  P§30 «без изменения основной семантики Core» и P§40 «без изменения Core»;
  не заменять их счётчиком файлов или разрешением предметного исключения.
  Baseline до второго не переопределяется после изменения. Технический HOW — product PLAN.
  Оба fictional примера только в development tests, вне installed product и user data;
  наблюдения сигнала исключительно выдуманные, без реальных расписаний/автономности.
  Владелец: «Реализация здесь, проверки в Claude Code». Автор здесь готовит source,
  проверочные сценарии и exact-commit handoff; новые тестовые/native/behavioral прогоны
  исполняются владельцем в отдельном Claude Code. До них статус честно unverified;
  непроведённые проверки не считаются PASS и весь root не закрывается.
  Нужная binding fresh G5 также отдельна от автора; ей не требуется иной провайдер,
  Claude Code здесь выбран владельцем как место исполнения.
  Чистая отдельная worktree от basis, только NEW fictional workspace в её ignored
  _scratch. На запуске проверить path/branch/pin/stamp/STOP/STEER; занятые папки не
  очищать. Сохранить source/evidence/rollback, все управляемые записи через Core API.
  Не читать/не искать/не повторять Work8/original attachment и archive/**.
  Пользовательская установка/репозиторий/данные недоступны разработчику.
  Перепроектирование основания, предметное исключение, обход authority/state,
  ослабление гарантии или выход за appetite возвращаются HOME по shape kill_by.
  Нет T6 renderer, T7/M1 close, M2+, реальных процессов, нового frontend/transport,
  CI/CD/Actions/уведомлений, remote/push/merge продукта, новых расходов/внешних прав.
  PROBA pin/stamp36. Приёмка T4 не является приёмкой T5. M0 partial.
done_when: |
  1. Второй процесс проходит наблюдаемо иной сценарий по правилам выбранной пары,
     а первый сохраняет проверенное поведение через тот же внешний контракт.
  2. Сохранены baseline, точный diff и результаты обоих сценариев; попытка найти
     скрытую предметную ветку/смену основной семантики не подменяется счётчиком
     файлов. Обе формулировки §§30/40 сохранены.
  3. Evidence позволяет сопоставить различие процессов, изменения и state точных
     версий; неподтверждённая гарантия остаётся открытой и возвращается в review.
return: |
  Product RESULT.md: outcome/evidence/assumptions/cuts/cost/manual-acceptance/next: solmax.
  До Claude checks — конкретный committed candidate и готовое сообщение владельцу
  для запуска проверок, без заявления REPORT PASS. После проверок — exact raw,
  source/diff/inputs/outputs/state/rollback, W15–W20 dispositions, binding review
  и понятный показ владельцу. Только HOME закрывает Direction; T6 не запускать.
budget: одно ограниченное приращение T5; оценочно ≤ половины фокусного дня как правило нарезки, не дедлайн; не помещается — конкретная причина HOME

END_OF_FILE: docs/m1-second-process/CALL.md

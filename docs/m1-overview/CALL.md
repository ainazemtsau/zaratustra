CALL c-solmax-zaratustra-m1-overview-20260910-exec
to: executor
kind: engineering
direction: solmax
node: g-zara-m1-modularity
task: t-zara-m1-overview
surface: cli
repo: C:/projects/zaratustra/_scratch/m1-second-process-20260910
engineering_contract: 36
mode: PROBA
basis: c4b8aea4db38fea4c39a473c47d0d8b82d8552a0
execution_worktree: C:/projects/zaratustra/_scratch/m1-overview-20260910
execution_branch: codex/m1-overview-20260910

goal: |
  Один общий обзор показывает оба процесса через одинаковый внешний контракт.
context: |
  Direction root C:/my_global_workflow_worktrees/solmax, пути от live/solmax/:
  NOW.md; CHARTER.md; cards/g-zara-m1-modularity.md; cards/bet-g-zara-m1-modularity.md;
  cards/t-zara-m1-overview.md; cards/closed/t-zara-m1-second-process.md;
  work/zaratustra-m1-second-process-close-2026-09-10.md;
  work/zaratustra-m1-second-process-owner-acceptance-2026-09-10.md;
  work/evidence/zaratustra-m1-second-process-close-20260910/;
  work/zaratustra-m1-shape-2026-09-09.md;
  work/zaratustra-architecture-plan-2026-09-05.md §§8/30/40/43;
  work/converge-g-zara-m1-modularity.md W19/W20 и C03–C05;
  knowledge/zaratustra-plan-conforming-approval-2026-09-07.md;
  knowledge/zaratustra-independent-use-and-practical-development-2026-09-10.md;
  knowledge/zaratustra-fictional-examples-test-only-2026-09-10.md.
  Product: AGENTS.md, module AGENTS, validation.config, STOP/STEER; RESULT.md;
  docs/m1-capabilities/PLAN.md; docs/m1-first-process/PLAN.md;
  docs/m1-second-process/PLAN.md, REPRODUCE.md, FIX-G5-S01.md;
  tools/probe_second_process.py и внешние fixtures. Root RESULT.md на basis
  предшествует повторной G5; актуальная приёмка T5 — HOME receipt выше.
  Binding G5 f4e3a26d85507f76429fc01e53c4dfdc1c4b18c5 и
  fa4e0796710b8ddcf07a9aada32b2351f7b8ecf7, полный native: 235 PASS / 11 contracts.
boundaries: |
  Только T6/W19 и нужное W20 evidence. Вид/command layout выбирает product PLAN
  в существующей допустимой поверхности; без нового frontend/assistant/transport.
  Оба процесса получать через публичный T3 read_capabilities, без чтения их
  внутренних инструкций/прямого обхода state. Сохранять scope, права, отдельно
  подтверждённый selected context, пустые/denied/unavailable/stale ответы.
  Две явно выбранные workspace и один registry; каждая строка имеет собственные
  workspace/process/revision. Единую межбазовую транзакцию/revision не обещать.
  Обзор производный, сам не даёт полномочий и не меняет authoritative state.
  Fictional примеры только development tests, вне установленного продукта и
  данных владельца; overview не должен автоматически создавать примеры.
  Чистая отдельная worktree от exact basis; path/branch выбрать свободные;
  новые fictional state/temp только ignored _scratch, старые не очищать.
  Прочитать STOP/STEER и pin/stamp 36. Новый PLAN до реализации сверить с shape;
  сохранить прежние Core/pack гарантии и scoped семантику W16, не ослаблять их.
  Прежнее пожелание владельца о месте проверок сохраняется: реализация здесь,
  проверки в Claude Code. Подготовить exact candidate и готовый текст проверки;
  до результатов не заявлять PASS. Binding G5 — отдельная физическая сессия.
  Пользовательская установка/репозиторий/данные недоступны разработчику.
  Не читать/искать/повторять Work8, original attachment, archive/**.
  Нет T7/M1 close, M2+, реальных процессов/расписаний/автономности, product
  remote/push/merge, новых расходов/внешних прав, CI/CD/Actions/уведомлений.
  Если нужен redesign/предметное исключение/ослабление guarantee — HOME по kill_by.
  Этот CALL ready, запуска ещё нет. Приёмка T5 не является приёмкой обзора.
done_when: |
  1. В существующей допустимой поверхности общий потребитель получает оба процесса
     через контракт T3; ему не нужны предметные инструкции для обходного чтения состояния.
  2. Представление согласовано с разрешённым state и правилами W16, включая пустые/
     недоступные ответы; выбранная Work сохраняет изоляцию контекста.
  3. Сохранён воспроизводимый вывод exact version для обоих процессов; он предъявляется
     владельцу в рамках PROBA, новые frontend/assistant не вводятся.
return: |
  Product RESULT.md: outcome/evidence/assumptions/cuts/cost/manual-acceptance/next: solmax.
  До проверок — committed candidate и готовый Claude handoff со статусом unverified.
  После — exact source/inputs/output/state/revisions, полный raw native и binding
  fresh G5, понятный показ общего обзора. Не объявлять owner acceptance или
  Direction close самостоятельно. Только HOME продолжает к T7.
budget: один минимальный общий обзор; оценочно не более половины фокусного дня как правило нарезки, не дедлайн; не помещается — конкретная причина HOME

END_OF_FILE: docs/m1-overview/CALL.md

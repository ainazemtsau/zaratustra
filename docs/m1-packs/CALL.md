CALL c-solmax-zaratustra-m1-packs-20260909-exec
to: executor
kind: engineering
direction: solmax
node: g-zara-m1-modularity
task: t-zara-m1-packs
surface: cli
repo: C:/my_global_workflow/943d/zaratustra
engineering_contract: 36
mode: PROBA
basis: f67959e7c1a412c202ebb0d6e67938ec4355042f
execution_worktree: C:/projects/zaratustra/_scratch/m1-packs-20260909
execution_branch: codex/m1-packs-20260909

goal: |
  Внешний пакет связывается с Process и незавершённой Work без обхода общих
  state/authority механизмов. Только T2: привязка и жизненный цикл пакета.
context: |
  Direction root C:/my_global_workflow_worktrees/solmax, следующие пути от live/solmax/:
  NOW.md; CHARTER.md; cards/g-zara-m1-modularity.md; cards/bet-g-zara-m1-modularity.md;
  cards/t-zara-m1-packs.md; cards/closed/t-zara-m1-probe.md;
  work/zaratustra-m1-probe-close-2026-09-09.md;
  work/zaratustra-m1-probe-owner-acceptance-2026-09-09.md;
  work/evidence/zaratustra-m1-probe-close-20260909/byte-verification.json;
  work/zaratustra-m1-shape-2026-09-09.md;
  work/zaratustra-m1-shape-owner-approval-2026-09-09.md;
  work/zaratustra-architecture-plan-2026-09-05.md §§8,30,40;
  work/converge-g-zara-m1-modularity.md — W01–W03, C01/C02/C06, M0;
  work/zaratustra-m1-converge-verify-2026-09-09.md;
  work/zaratustra-m0-review-2026-09-09.md — M0 partial;
  knowledge/zaratustra-plan-conforming-approval-2026-09-07.md;
  knowledge/zaratustra-local-no-automation-2026-09-07.md.
  В продукте: AGENTS.md, validation.config, ближайшие module AGENTS и STOP/STEER
  при наличии; RESULT.md; docs/m1-probe/PLAN.md; docs/m1-probe/READOUT.md;
  docs/g5/m1-probe-20260909/G5-REPORT.md, receipt.json, REPRODUCE.md.
  T1 candidate f917565e141804508c11954c5de51566e82c48ca принят словом «принимаю» после binding fresh G5.
  Basis — его прямой docs-only review-потомок; src/tests/tools/dependencies и
  authority идентичны. Старые pending в Product/G5 — исторические; точная более
  поздняя приёмка сохранена HOME. Техническая архитектура принадлежит PLAN.
boundaries: |
  Только T2, не универсальный scheduler/interpreter и не скрытая цепочка полной M1.
  Сначала PLAN отвечает W15 до dependent state/миграций: pack/type/instance,
  регистрация, state/contract versions, missing/incompatible и начатая Work при
  смене версии. Общие гарантии C01/C02/C06/M0, Mutation/revision/history обязательны.
  Конкретный ответ выбирает продуктовая работа по HOW; Direction его не выдумывает.
  Все оставшиеся W15–W20 сохранены ниже. T1 дала только частичные ответы для пробы;
  они не закрывают полную M1. Общий контракт сохраняет семь возможностей,
  scope/revisions, empty/denied/unavailable и metadata/counts/consistency.
  Обе гарантии W17 сохранены: P§30 «без изменения основной семантики Core»
  и P§40 «без изменения Core». Сохранить baseline и различение общей подготовки
  от подключения второго; executor не ослабляет ни одну гарантию.
  Источник — чистый basis в repo. Записи разрешены только в новом execution_worktree
  от basis и новых явно выбранных fictional workspace внутри его ignored _scratch/.
  На запуске перепроверить source/pin/stamp/STOP/STEER и свободные path/branch;
  при столкновении выбрать иную свободную изоляцию и записать её точные данные.
  Не очищать чужие папки. Work3, Work7, probe и G5 review остаются источниками.
  Корневые WORK8-CHATGPT-INSTRUCTIONS.md и work8-chatgpt-input.json не читать
  и не менять; Work8/original attachment не искать и не повторять. M0 partial.
  До изменения сохранить проверенную версию и восстанавливаемое тестовое состояние.
  Проверки работают через настоящий Core; восстановление — законным продуктовым
  механизмом. Прямые DB/state Markdown edits и потеря evidence ради PASS запрещены.
  Перепроектирование основания, предметное исключение Core, обход authority/state,
  изменение owner concept/гарантии или превышение appetite возвращаются HOME
  по shape kill_by, без зависимого расширения. Ожидаемый тестовый отказ не дефект.
  Нет реальных процессов, M2+, нового frontend, transport, автономности,
  CI/CD, Actions, уведомлений, новых внешних/денежных прав или расходов.
  Отсутствие product remote не требует публикации; действующий pin/stamp=36,
  режим PROBA. Принятая T1 и делегация conforming HOW не являются приёмкой T2.
  Поведенческий done требует отдельной свежей physical G5; подагент даёт только
  предварительную помощь. Итоговая T7 остаётся отдельной проверкой всей M1.
  REPORT возвращается HOME, не закрывает Direction T2/M1 и не выдаёт CALL/T3.
done_when: |
  1. На выбранной продуктовым PLAN модели pack/type/instance проверены регистрация,
     совместимость версий и сохранённая связь Work с пакетом.
  2. Missing/incompatible pack и смена его версии имеют определённое и проверенное
     поведение для незавершённой Work без тихого переопределения прав или состояния.
  3. Сохранены commit и воспроизводимые проверки общей Mutation/revision/history
     границы; утверждения о поведении закрываются по evidence, а не по наличию интерфейса.
return: |
  Product RESULT.md по repo contract: outcome/evidence/assumptions/cuts/cost/
  manual-acceptance/next: solmax. REPORT либо точный ESCALATE HOME на этот CALL,
  exact commits/inputs/outputs/state/diff, native check, evidence/rollback и W15–W20
  dispositions. Фактические слова владельца о предъявленной T2 либо честный pending;
  pending не объявлять завершением PROBA. Не менять live/** и не запускать T3.
budget: одно ограниченное приращение T2, оценочно ≤ половины фокусного дня как правило нарезки, не дедлайн; если не помещается — конкретный blocker HOME для пересмотра нарезки

PLAN agenda — полные вопросы и цена неверного ответа из shape; частичные T1
решения в docs/m1-probe/PLAN.md не заменяют оставшиеся обязательства:

| ID | Не выбранный ответ / зависимости | Answerer и цена неверного ответа |
|---|---|---|
| W15 | pack/type/instance, registration, state/contract versions, исполнение предметных правил; поведение сохранённых ссылок при отсутствующем или несовместимом pack и судьба начатой Work при смене его версии. | open; answerer PLAN; → PLAN; rewrites: registry, manifests, привязки Work/context, adapters, сохранённые ссылки и migrations; ≤1 дня не доказано. |
| W16 | Значение семи ответов, пустота/отказ/недоступность, scope и revisions; совместимость разрешённого общего обзора с изоляцией выбранной Work, видимость metadata/counts и единица согласованности ответов; изменение прав, недоступный контекст и устаревшее представление. Depends on W15. | open; answerer PLAN; → PLAN; rewrites: публичный контракт, read guards, mapping, context/projections и потребители; ≤1 дня не доказано. |
| W17 | Граница Core/pack и baseline добавления второго, отсутствие скрытых предметных веток; обе формулировки P§30/P§40 сохранены. Depends on W15/W16 и W18. | open; answerer PLAN; → PLAN; rewrites: границы модулей, refactor, замороженный diff/evidence и повтор сценариев; ≤1 дня не доказано. Изменение гарантии возвращается OWNER. |
| W18 | Конкретная fictional пара и наблюдаемое различие процессных правил; работающие сценарии обоих без продуктовых шаблонов. | open; answerer PLAN; → PLAN; rewrites: fixtures/сценарии/ожидания, обычно обратимо до связанной реализации; после предметного кода оценить заново. Новый owner concept/acceptance возвращается OWNER. |
| W19 | Представление одного общего обзора в существующей допустимой поверхности; смысл ответов остаётся W16. | open; answerer PLAN; → PLAN; rewrites: renderer/adapters и проверки вывода; обычно ≤1 дня до фиксации внешнего контракта. Новый frontend/assistant не вводится. |
| W20 | Exact commits/versions/inputs/outputs обоих сценариев и сопоставление с состоянием и diff. Depends on W17/W18/W19. | open; answerer PLAN; → PLAN; rewrites: evidence capture/manifest, контрольные состояния и повтор сценариев; до прогона обычно ≤1 дня, потерянную provenance после прогона восстановить не гарантировано. |

END_OF_FILE: live/solmax/work/calls/c-solmax-zaratustra-m1-packs-20260909-exec.md

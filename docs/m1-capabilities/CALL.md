CALL c-solmax-zaratustra-m1-capabilities-20260909-exec
to: executor
kind: engineering
direction: solmax
node: g-zara-m1-modularity
task: t-zara-m1-capabilities
surface: cli
repo: C:/my_global_workflow/fa61/zaratustra
engineering_contract: 36
mode: PROBA
basis: a5efbb15c7c39e52072f4fb1593a294ebe109a80
execution_worktree: C:/projects/zaratustra/_scratch/m1-capabilities-20260909
execution_branch: codex/m1-capabilities-20260909

goal: |
  Разрешённый потребитель получает семь согласованных ответов Process через один
  внешний контракт. Только T3: общий read/context contract.
context: |
  Direction root C:/my_global_workflow_worktrees/solmax, пути от live/solmax/:
  NOW.md; CHARTER.md; cards/g-zara-m1-modularity.md; cards/bet-g-zara-m1-modularity.md;
  cards/t-zara-m1-capabilities.md; cards/closed/t-zara-m1-packs.md;
  work/zaratustra-m1-packs-close-2026-09-09.md;
  work/zaratustra-m1-packs-owner-acceptance-2026-09-09.md;
  work/evidence/zaratustra-m1-packs-close-20260909/byte-verification.json;
  work/zaratustra-m1-shape-2026-09-09.md;
  work/zaratustra-m1-shape-owner-approval-2026-09-09.md;
  work/zaratustra-architecture-plan-2026-09-05.md §§8,30,40;
  work/converge-g-zara-m1-modularity.md — W01–W03, C01–C06, M0;
  work/zaratustra-m1-converge-verify-2026-09-09.md;
  work/zaratustra-m0-review-2026-09-09.md — M0 partial;
  knowledge/zaratustra-plan-conforming-approval-2026-09-07.md;
  knowledge/zaratustra-local-no-automation-2026-09-07.md.
  В продукте: AGENTS.md, validation.config, ближайшие module AGENTS и STOP/STEER
  при наличии; RESULT.md; docs/m1-packs/PLAN.md, READOUT.md, REPRODUCE.md;
  docs/g5/m1-packs-20260909/G5-REPORT.md, receipt.json, REPRODUCE.md.
  T2 candidate 25a35b449570caf500cf09fca560b2bb64313169 принят словом «да» после binding fresh G5.
  Basis — прямой docs-only review-потомок; source/tests/tools/dependencies/authority
  идентичны. Pending в старых Product/G5 — исторические, поздняя приёмка в HOME.
  T1 была узкой пробой; T2 — lifecycle. Полные сценарии и общий обзор впереди.
boundaries: |
  Только T3: один общий read/context contract; renderer и полные сценарии — T4–T6.
  W16 и все смыслы семи ответов принадлежат PLAN до реализации: пустота, отказ,
  недоступность, scope/revisions, metadata/counts, единица согласованности,
  изменившиеся права, недоступный контекст, устаревшее представление. W15 T2
  сохраняется как точная проверенная привязка; capabilities не предоставляют прав.
  Общие C03/C04/C05 и state/Mutation/history гарантии сохраняются; ответы derived.
  W17 сохраняет обе гарантии: P§30 «без изменения основной семантики Core»
  и P§40 «без изменения Core». Baseline различает общую подготовку и подключение
  второго процесса; ни одна гарантия не ослабляется. Остаток W15–W20 — ниже.
  Источник — чистый basis. Записи только в новом execution_worktree от basis и
  новых явно выбранных fictional workspace внутри его ignored _scratch/.
  На запуске перепроверить source/pin/stamp/STOP/STEER и свободные path/branch;
  при столкновении выбрать другую свободную изоляцию и сохранить точные данные.
  Не очищать чужие папки. Work3, Work7, probe, packs и G5 остаются источниками.
  WORK8-CHATGPT-INSTRUCTIONS.md и work8-chatgpt-input.json не читать/не менять;
  Work8/original attachment не искать и не повторять. M0 partial.
  До изменений сохранить проверенную версию и восстанавливаемое тестовое состояние.
  Проверки через настоящий Core, восстановление законным продуктовым механизмом;
  прямые DB/state Markdown edits и потеря evidence ради PASS запрещены.
  Перепроектирование основания, предметное исключение Core, обход authority/state,
  изменение owner concept/гарантии или превышение appetite возвращаются HOME
  по shape kill_by. Ожидаемый тестовый отказ сам по себе не дефект.
  Нет реальных процессов, M2+, нового frontend, transport, автономности,
  CI/CD, Actions, уведомлений, новых внешних/денежных прав или расходов.
  Product remote не требуется. PROBA pin/stamp 36. Приёмка T2 и conforming HOW
  не являются приёмкой T3. Поведенческий done требует отдельной fresh physical G5;
  подагент даёт только предварительную помощь. T7 проверяет всю M1 отдельно.
  REPORT возвращается HOME, не закрывает Direction T3/M1 и не выдаёт CALL/T4.
done_when: |
  1. Реализованы current status, items needing attention, open decisions, available
     works, blocked works, recent important results, context requirements for a
     chosen Work через единый контракт.
  2. На определённых PLAN случаях проверены пустота, отказ и недоступность,
     revisions/scope, видимость metadata/counts и согласованность ответов с
     authoritative state; выбранная Work не получает чужой контекст.
  3. Сохранены exact version и результаты проверок; ответы не создают второй
     источник состояния и не требуют готовых M2+ компонентов.
return: |
  Product RESULT.md по repo contract: outcome/evidence/assumptions/cuts/cost/
  manual-acceptance/next: solmax. REPORT либо точный ESCALATE HOME на этот CALL;
  exact commits/inputs/outputs/state/diff, native check, evidence/rollback,
  W15–W20 dispositions. Фактические слова владельца о предъявленной T3 либо
  честный pending; pending не объявлять завершением PROBA. Не менять live/**
  и не запускать T4.
budget: одно ограниченное приращение T3, оценочно ≤ половины фокусного дня как правило нарезки, не дедлайн; если не помещается — конкретный blocker HOME для пересмотра нарезки

PLAN agenda: исходные вопросы/rewrites из shape сохранены ниже. Их первоначальный
open не отменяет узкие ответы T2: docs/m1-packs/PLAN.md и G5 receipt w15_w20.
Текущая диспозиция: W15 lifecycle отвечен T2, полные правила T4/T5; W16 OPEN
PLAN/T3; W17 OPEN PLAN/T3–T5; W18 OPEN PLAN/T4/T5; W19 OPEN PLAN/T6;
W20 evidence T2 сохранено, оба полных сценария и итоговое сравнение OPEN T4–T7.

| ID | Не выбранный ответ / зависимости | Answerer и цена неверного ответа |
|---|---|---|
| W15 | pack/type/instance, registration, state/contract versions, исполнение предметных правил; поведение сохранённых ссылок при отсутствующем или несовместимом pack и судьба начатой Work при смене его версии. | open; answerer PLAN; → PLAN; rewrites: registry, manifests, привязки Work/context, adapters, сохранённые ссылки и migrations; ≤1 дня не доказано. |
| W16 | Значение семи ответов, пустота/отказ/недоступность, scope и revisions; совместимость разрешённого общего обзора с изоляцией выбранной Work, видимость metadata/counts и единица согласованности ответов; изменение прав, недоступный контекст и устаревшее представление. Depends on W15. | open; answerer PLAN; → PLAN; rewrites: публичный контракт, read guards, mapping, context/projections и потребители; ≤1 дня не доказано. |
| W17 | Граница Core/pack и baseline добавления второго, отсутствие скрытых предметных веток; обе формулировки P§30/P§40 сохранены. Depends on W15/W16 и W18. | open; answerer PLAN; → PLAN; rewrites: границы модулей, refactor, замороженный diff/evidence и повтор сценариев; ≤1 дня не доказано. Изменение гарантии возвращается OWNER. |
| W18 | Конкретная fictional пара и наблюдаемое различие процессных правил; работающие сценарии обоих без продуктовых шаблонов. | open; answerer PLAN; → PLAN; rewrites: fixtures/сценарии/ожидания, обычно обратимо до связанной реализации; после предметного кода оценить заново. Новый owner concept/acceptance возвращается OWNER. |
| W19 | Представление одного общего обзора в существующей допустимой поверхности; смысл ответов остаётся W16. | open; answerer PLAN; → PLAN; rewrites: renderer/adapters и проверки вывода; обычно ≤1 дня до фиксации внешнего контракта. Новый frontend/assistant не вводится. |
| W20 | Exact commits/versions/inputs/outputs обоих сценариев и сопоставление с состоянием и diff. Depends on W17/W18/W19. | open; answerer PLAN; → PLAN; rewrites: evidence capture/manifest, контрольные состояния и повтор сценариев; до прогона обычно ≤1 дня, потерянную provenance после прогона восстановить не гарантировано. |

END_OF_FILE: live/solmax/work/calls/c-solmax-zaratustra-m1-capabilities-20260909-exec.md

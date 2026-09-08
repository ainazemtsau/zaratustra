CALL c-solmax-zaratustra-m0-context-20260908-work6
to: executor
kind: engineering
direction: solmax
node: g-zara-m0-continuity
task: t-zara-m0-context
repo: C:/projects/zaratustra
engineering_contract: 36
mode: PROBA
surface: cli
goal: |
  Открытие Work выдаёт актуальные разрешённые основания и manifest реально
  собранного контекста.
context: |
  Work 6 — Work context, принятый план §§7,10,41; T5 после закрытой T4/Work 5.
  Direction root: C:/my_global_workflow_worktrees/solmax. От него:
  live/solmax/NOW.md, live/solmax/CHARTER.md;
  live/solmax/cards/t-zara-m0-context.md,
  live/solmax/cards/closed/t-zara-m0-handoff.md,
  live/solmax/cards/bet-g-zara-m0-continuity.md;
  свежий payload: uv run --locked python osctl.py context --for t-zara-m0-context.
  Закрытие Work 5:
  live/solmax/work/zaratustra-m0-work5-close-2026-09-08.md;
  live/solmax/history/2026-09-08-s-solmax-zaratustra-work5-close-20260908-a1.md;
  live/solmax/work/evidence/zaratustra-m0-work5-close-20260908/manifest.md.
  В том же evidence-каталоге: G5-REPORT.md (первоначальный FAIL/F1),
  G5-F1-RECHECK.md (binding aggregate PASS/PASS/PASS),
  g5-f1-recheck-manifest.json, g5-f1-recheck-evidence.zip, product-handback.zip,
  byte-verification.json, retained-trial-v2.zip и retained-trial-v2-manifest.json.
  G5-F1-RECHECK.md SHA-256:
  de6c9cdcb0ddcfcb0ce79ca2d3b55a972b5eca016372efcf9a1dcbf538e4074c.
  G5 ZIP SHA-256:
  afeab5227162e4d99b1bf485ed131afc103bd0072483b61d02c519cc9cc97d03.
  Manifest объясняет nested prior/source/raw locators; весь bundle в prompt
  загружать не требуется, конкретный claim проверяется по названному raw.
  Проверенная Product-база:
  589861c4657f19763b0af4ab965bd84646eecb70, version 0.5.0;
  её parent df79b2fc385bd2db5747968bc09422a580d98559 проверен отдельной G5.
  589861c меняет только RESULT.md, docs/work5/HOME.md и F1-REPAIR.md,
  записывая полученный PASS; runtime, packer/test, PLAN/INSTALL и backup неизменны.
  Actual accepted checkout C:/projects/zaratustra/_scratch/work5-handoff,
  branch codex/work5-handoff. Основной repo C:/projects/zaratustra, remote отсутствует.
  Для Work 6 использовать новый isolated checkout этого repo от указанной базы;
  записать actual path/branch/HEAD. Старый main и reviewer extraction не база.
  Прежнюю checked Work 5 копию/branch/evidence сохранить.
  Product-local на этой базе: AGENTS.md, validation.config (36/PROBA), RESULT.md;
  docs/work5/PLAN.md, HOME.md, F1-REPAIR.md, INSTALL.md и evidence/;
  docs/work4/PLAN.md, docs/work3/OWNER-DECISION-20260908.md и PLAN.md,
  docs/work2/RECORDS.md, docs/work1/FOUNDATION.md,
  docs/setup/OWNER-DECISION-20260907.md.
  План Direction: live/solmax/work/zaratustra-architecture-plan-2026-09-05.md,
  §§3–7,10,25,28–29,41–43; SHA-256
  4f90d19fc742ab616301b6b4121880f76c75faaeb1f606c8190a84853d8b3e0e.
  Design evidence для Product PLAN:
  live/solmax/work/converge-g-zara-m0-continuity-arch.md, W22/W23/W27;
  live/solmax/work/converge-g-zara-m0-continuity.md, CONTRACTS C02/C04–C07/E1–E12.
  Knowledge: live/solmax/knowledge/zaratustra-plan-conforming-approval-2026-09-07.md
  и zaratustra-local-no-automation-2026-09-07.md в том же knowledge/.
  Стек Python 3.13/uv/sqlite3/Pydantic v2/pytest/ruff/SHA-256.
  Work 5 сохраняет accepted Handoff с exact result/basis version/hash, provenance,
  source_revision, delivery/confirmation и receipt; read_handoffs/projection —
  owner-local inspection, пока не Work context. Schema 5 explicit, default migrate 4.
boundaries: |
  Только Work 6/T5: open_work, актуальный ограниченный context/manifest и isolation
  одной Work. Технический HOW/формат/снимок/budget units решает Product PLAN
  до зависимой реализации по W22/W24, с учётом current read authority W21.
  Envelope определяет разрешённое чтение, namespaces, revisions и budget.
  Ссылка на объект/Artifact не выдаёт право на его содержимое. Pasted Next Call,
  старый manifest/projection/receipt не делают сведения актуальными; недоступные
  или подменённые bytes нельзя выдавать за проверенные. Обязательные основания,
  authority и acceptance не усекать тихо при overflow и budget не расширять молча.
  Manifest должен описывать actual output, а не только планируемый набор.
  PLAN определяет зависимые revisions решения/прав/Process membership, условия
  invalidation и остановки/пересборки, включая изменение основания во время сборки.
  Все управляемые изменения через единый Mutation API с literal §5:
  input → current Work/authority → revision → duplicate → artifact refs
  → DB mutation/event/receipt → projections. Context не получает обход записи.
  Сохранять W19 acceptance/replay/stale semantics и W20 file/DB/orphan/exact repair/
  rebuild/late availability. Released migrations не переписывать; если необходима
  новая, только explicit migration на новой выбранной fictional копии.
  W21 exact owner decision уже принят: local console либо actual trusted local-chat
  permission; файл/model text сам себе authority не выдаёт, действующие права
  проверяются. Повторной проверки личности при уже полученном permission не нужно;
  accounts/login/hostile same-user isolation не добавлять.
  Проверенный trial: C:/Users/Anton/AppData/Local/Temp/zaratustra-work5-96nw94ii.
  Новые испытания только на явно выбранных новых копиях его main workspace
  одного fictional Process либо восстановлении v2 через docs/work5/INSTALL.md.
  Current backup SHA-256:
  fdb39d39441f9e739e2d6ec17391ad7500a8d86284a79b186df073088487bb51;
  wheel 0.5.0: cc11753b83bbfddf670c255c46a8dc414d8c5216e78e77e8f686977243461894;
  main DB revision 11/schema 5:
  9069fd067bfd792da663d2281508e0cb12bcd3ebd6e9fed991ffb9830a3d2c24.
  v2 сохраняет 26 файлов/15 каталогов. Old retained-trial.zip — F1 diagnostics,
  не restore-база; fault-workspace намеренно содержит missing result и не база.
  Прежние DB/wheels/receipts 0.1–0.5, Product commits и все исходные G5 сохраняются.
  Минимальный foreign-context отрицательный fixture допускается по W25, второй
  полноценный Process/real personal data/permanent personal workspace не допускаются.
  Не писать в live Direction OS, старые repos и archive; не чинить DB/state Markdown
  напрямую. Work 7 submit_result/next Work и Work 8 actual clean-chat five facts/
  full owner demonstration здесь не начинать и не объявлять PASS.
  M0 остаётся active; наличие context manifest не доказывает понимание чатом.
  M1+, MCP/automatic transport/GitHub inbox, memory engine/retrieval/router/frontend/
  autonomy, внешняя установка/upgrade/full migration, CI/CD/Actions/notifications,
  Product remote/publication, расходы и новые внешние/необратимые права не допущены.
  Оба no-automation owner-ack сохраняются. Соответствующий принятому плану HOW
  не требует повторной подписи; реальное расхождение или owner-owned выбор — HOME.
done_when: |
  1. После Work 5 open_work сверяет актуальное состояние: выполненная или неактуальная
     Work не запускается вновь; пакет связан с действующими основаниями/revisions
     по решению PLAN W22.
  2. Manifest перечисляет реально переданный набор источников в пределах scope
     и budget; чужой контекст, в том числе через недопустимую ссылку, не попадает
     в Work. Минимальные fictional fixtures определены W25.
  3. Сохранены проверки свежести/зависимостей, scope и нехватки budget без тихой
     потери обязательных оснований; наличие manifest не объявляется доказательством
     понимания отдельным чатом.
return: |
  HOME solmax: полный Product RESULT по трём done_when, actual commits/diff,
  version/install/workspace/wheel hashes, exact context output и manifest/revisions/
  hashes/измеренный budget, raw native и installed checks; assumptions/cuts/cost/
  manual-acceptance/next: solmax. Показать реальные scope/freshness/dependency/budget
  refusals и неизменность принятой базы; сохранить восстанавливаемую копию нового
  trial с files И directories, исходные locators и hashes.
  Воспроизводимый walkthrough: команды, ожидаемое наблюдение и что сохранить.
  Native build/hygiene/types/boundaries/hidden-state проверки — по repo authority;
  actual engineering checks отдельно от owner runtime words и будущего Work 8.
  W19–W27 вернуть поимённо: что решено, ответчик остатка, момент решения, rewrites.
  Product не закрывает Direction T5/CALL/M0 и не выдаёт successor Direction CALL.
  Поведенческое закрытие T5 требует binding fresh physical G5 exact version;
  прежняя Work 5 G5 подтверждает только совпавшие claims/inputs.
  Полный конкретный blocker вернуть HOME; sizing/scope/acceptance не сокращать молча.
budget: одно минимальное приращение Work 6 внутри T5; калибровка до половины фокусного рабочего дня, PLAN проверяет размер; без нового срока/расхода

## PLAN agenda — W19–W27

| ID | Ответчик и момент решения / сохранённый остаток | rewrites |
|---|---|---|
| W19 | Product PLAN: Work 5 identity/effect/replay/stale/collision/receipt подтверждены G5; до зависимых Work 6 read решений сохранить смысл. Result/next unit решается PLAN до Work 7. | importer/receipts/linkage/failures/migrations; дешёвая переделка не доказана |
| W20 | Product PLAN до Work 6 content reads: сохранить exact versions/hash/late availability, file/DB/orphan/repair/rebuild и проверенный restore v2; continuation/recovery до Work 7. | durable references/recovery/evidence/migrations |
| W21 | Product PLAN до Work 6 чтения: current scope/trusted caller/context channel и недопустимые транзитивные refs; использовать exact owner words Work 3 без повторного решения W21. Result consumer до Work 7. | adapters/permissions/consumer boundaries; решение не runtime PASS |
| W22 | Product PLAN до Work 6: authoritative snapshot либо полная revalidation, dependency revisions/invalidation, namespace/scope, budget units/overflow, manifest actual output. Разрешённый объект не открывает чужое содержимое. | snapshot/context contract/tests/возможные migrations; freshness/scope/budget не вырезаются |
| W23 | Product PLAN до Work 6: сохранить точные bytes/hash фактического output и связь с manifest; определить протокол дальнейшей передачи. Реальная отдельная чистая сессия и ответ по пяти фактам — Work 8. | delivery/demo и повтор Work 8; недоказуемая чистота в Work 8 — blocker |
| W24 | Product PLAN до реализации Work 6: минимальные schema/CLI/serialization/budget accounting/transaction-BUSY/layout; при необходимости explicit migration, не правка released bytes. | локальные mechanics/tests/migrations; семантика возвращается W19–W22 |
| W25 | Product PLAN до Work 6 fixtures: один fictional graph, stale/terminal/changed authority/dependency/missing bytes/budget overflow/foreign context через недопустимую ссылку; actual demo до Work 8. | fixtures/tests/demo; без второго полного/реального Process |
| W26 | Product PLAN перед стартом Work 6: проверить actual base/ref/new checkout/install layout; permanent folder/hosting/independent external install-upgrade требуют отдельного допуска. | package/layout/docs; новые внешние права отсутствуют |
| W27 | Product PLAN до нового Work 6 public consumer: только нужный M0 context seam; E1–E12 остаются в CONTRACTS, E4/E5/E7/E12 без выдуманных direct M0 APIs. Следующие consumers решают HOW при собственном допуске. | публичные Core/data/consumer migrations; M1+ не prerequisite, дешёвая замена не доказана |

END_OF_FILE: live/solmax/work/calls/c-solmax-zaratustra-m0-context-20260908-work6.md

CALL c-solmax-zaratustra-m0-result-20260908-work7
to: executor
kind: engineering
direction: solmax
node: g-zara-m0-continuity
task: t-zara-m0-result
repo: C:/projects/zaratustra
engineering_contract: 36
mode: PROBA
surface: cli
goal: |
  Записанный результат с квитанцией однозначно связывается с дальнейшей Work
  и восстанавливается после нового запуска.
context: |
  Work 7 — Result, принятый план §§5,7,28,41; T6 после закрытой T5/Work 6.
  Это полный ready CALL для будущего запуска. Создание этого CALL не является
  launch receipt; реализация Work 7 и Work 8 в выдавшей Direction-сессии не начата.
  HOME: solmax. Direction root текущего выпуска C:/my_global_workflow/207a/solmax;
  durable authority — свежий Git main репозитория C:/my_global_workflow.
  Из актуального Direction checkout прочитать:
  live/solmax/NOW.md, CHARTER.md; cards/t-zara-m0-result.md,
  cards/closed/t-zara-m0-context.md, cards/bet-g-zara-m0-continuity.md;
  uv run --locked python osctl.py context --direction solmax --for t-zara-m0-result.
  Все сокращённые пути здесь относительно live/solmax/.
  work/zaratustra-architecture-plan-2026-09-05.md §§3–7,10,25,28–29,41–43;
  source SHA-256 4f90d19fc742ab616301b6b4121880f76c75faaeb1f606c8190a84853d8b3e0e.
  Текущий checkout может иметь только CRLF/LF отличие; source bytes и сверка
  названы в work/evidence/zaratustra-m0-work6-close-20260908/byte-verification.json.
  work/converge-g-zara-m0-continuity-arch.md W19–W27 и
  work/converge-g-zara-m0-continuity.md CONTRACTS C01–C08/E1–E12 — design evidence
  для Product PLAN, не самостоятельный binding HOW.
  knowledge/zaratustra-plan-conforming-approval-2026-09-07.md и
  knowledge/zaratustra-local-no-automation-2026-09-07.md.
  Закрытие Work 6: work/zaratustra-m0-work6-close-2026-09-08.md;
  history/2026-09-08-s-solmax-zaratustra-work6-close-20260908-a1.md.
  Durable evidence: work/evidence/zaratustra-m0-work6-close-20260908/manifest.md,
  G5-REPORT.md, g5-work6-evidence.zip, g5-work6-manifest.json,
  product-handback.zip, byte-verification.json и verify.py в том же каталоге.
  Binding G5 — отдельная физическая задача 01a080fc-5523-7a92-b8e6-6f33909a1811;
  PASS/PASS/PASS exact candidate, без blocking findings.
  Report SHA-256 a7714cb01c73c0b0c328e4f3a5b91ad9d6100707d237d0a4e9e46502f483815c;
  G5 ZIP 41bd2218158c38bda8455905f5695dce716e0105f0c85ae55a8d3baa5aa70144;
  manifest 2217f22434c7f688b066c905664789584f770c0cac940b1f87c760dd14c31317.
  ZIP содержит 354 files/285 directories, raw, scripts, restored trial и
  candidate-source.zip (полный Git tree 271 blobs; SHA-256
  916a70c04a6f34627fee44e0a17da90ea8927e879ad5bfb0faea5b31c46f1ddb).
  Product-handback.zip содержит canonical Git RESULT, AGENTS/validation.config,
  exact W21/setup words и весь docs/work6/, включая retained-trial.zip.
  Полный bundle не нужно загружать в prompt: manifest даёт точные raw locators.
  Проверенная accepted Product-база: 2fa3111666139eef3ae699319444809fce563ead,
  version 0.6.0. Parent implementation e5576df5550d54de47c1d29d666d60c0194412f3;
  final candidate меняет относительно него только docs/evidence/RESULT.
  Actual accepted checkout C:/projects/zaratustra/_scratch/work6-context,
  branch codex/work6-context; основной repo C:/projects/zaratustra, remote отсутствует.
  Будущая реализация использует НОВЫЙ isolated Product checkout от exact accepted
  base; записать actual path/branch/HEAD. Прежние Work 5/6 checkout/refs сохраняются.
  Product-local authority на базе: AGENTS.md, validation.config (36/PROBA), RESULT.md;
  docs/work6/CALL.md, PLAN.md, HOME.md, INSTALL.md и evidence/;
  docs/work5/PLAN.md, INSTALL.md, F1-REPAIR.md; docs/work4/PLAN.md;
  docs/work3/PLAN.md и OWNER-DECISION-20260908.md; docs/work2/RECORDS.md;
  docs/work1/FOUNDATION.md; docs/setup/OWNER-DECISION-20260907.md.
  Product HOME.md исторически говорит «G5 ещё не выполнена»: он написан ДО
  отдельного G5; актуальный close receipt находится HOME в указанных Direction files.
  Стек Python 3.13/uv/sqlite3/Pydantic v2/pytest/ruff/SHA-256.
  Work 6 open_work — только read: не запускает executor, не меняет Work status,
  DB/event/receipt/projection. Ready open повторяется как свежий read. Cancelled/
  revoked/stale отказывают; done/submit_result/next semantics ещё не реализованы.
  Schema 5; default explicit migrate target по-прежнему 4. Work 6 migration не вводила.
boundaries: |
  Только Work 7/T6: одна Result → next Work связь с историей и восстановлением.
  Product PLAN до зависимой реализации определяет completion/next semantics,
  единицу принятого эффекта, replay/collision/unknown outcome и recovery W19/W20.
  Не предполагать по Work 6, что done status, inherited acceptance следующей Work
  либо атомарность её создания уже существуют. Способ linkage, публичные inputs,
  переходы статусов и права Result consumer обосновать в PLAN, сохранив WHAT.
  Owner-content/цель/критерии/разрешения следующей Work не решать за владельца:
  использовать точное допущенное fictional содержание; реальный недостающий выбор HOME.
  Все managed изменения через единый Mutation API с literal §5:
  input → current Work/authority → expected revision → duplicate → artifact refs
  → DB mutation/event/receipt → projections. Сохранить W19 Work5 acceptance identity,
  stale/replay/collision/receipt; не переставлять duplicate перед current authority/
  revision. Не обходить unknown outcome новым operation id или reopen terminal Work.
  Сохранить W20 versioned bytes → hash → registration/active transaction, orphan,
  file/DB boundary, exact retry/repair/quarantine, deterministic rebuild и late loss.
  Сбой projection после commit не означает rollback принятого результата/continuation.
  Проверить result/linkage/receipt после restart и при утрате ответа отдельно.
  Work 6 envelope/current rights/scope, conservative global current revision,
  validated snapshot/journal/membership/acceptances/descriptors и полная final
  byte revalidation сохраняются. Freshness — на final validation, не lease до
  будущего исполнения. Любая managed mutation инвалидирует старый запрос; physical
  loss может не менять DB revision. Новое membership поведение не придумывать из probe.
  Разрешённая ссылка не открывает чужой контент. Text/URI/Next Call/projection/receipt
  не дают ни authority, ни доказательства current bytes. Full provenance closure
  и все committed acceptances текущей Work сохраняются, без latest-wins. Как их
  исторические основания связаны с новым Work consumer, решает PLAN W19/W22;
  требуемое понимание пяти фактов не заменять одним manifest.
  Full canonical wire budget включает envelope, sources, manifest и LF; content
  bytes сохраняются с hash. Не усекать mandatory authority/acceptance/grounds и
  не расширять max_bytes молча; human effort budget отдельно и не конвертируется.
  W21 exact owner decision: actual local console confirmation точной операции либо
  фактическое permission доверенного local-chat adapter; file/model text/approved
  flag сами себя не авторизуют. Current scope/rights/revision проверяются. Уже
  полученное permission не требует повторной проверки личности. Accounts/login/
  новой identity и защиты от hostile same-OS-user не добавлять.
  Испытания только на явно выбранной НОВОЙ копии Work6 main workspace одного
  fictional Process или его восстановлении через docs/work6/INSTALL.md.
  Accepted trial C:/Users/Anton/AppData/Local/Temp/zaratustra-work6-_0caf231;
  retained-trial.zip SHA-256
  1657d3a559ba1275ea010b5d83ff0cb818ba26fa74ab195cc86f8218ac57d539,
  75 files/72 directories; ZIP сохраняет пустые storage dirs. Main DB schema5/rev11
  SHA-256 9069fd067bfd792da663d2281508e0cb12bcd3ebd6e9fed991ffb9830a3d2c24;
  wheel 0.6.0 876f623afe6a96f937e3584ea54470e5510002ef67f2b55480b99f1f6b41c816.
  Context 12320/65536 bytes, 7 sources; SHA-256
  438bf8af803b20763c9e904097c7f5f250e2b06f34928720535d7e903604df85.
  Выбор DB/schema/upgrade explicit. Released migrations не переписывать; если PLAN
  докажет необходимость новой, новая explicit migration только на новой выбранной
  fictional копии с сохранённой old-schema/old-migrate совместимостью по контракту.
  Work5 accepted checkout C:/projects/zaratustra/_scratch/work5-handoff, HEAD
  589861c4657f19763b0af4ab965bd84646eecb70, trial
  C:/Users/Anton/AppData/Local/Temp/zaratustra-work5-96nw94ii сохраняются неизменными.
  Его retained-trial-v2.zip fdb39d39441f9e739e2d6ec17391ad7500a8d86284a79b186df073088487bb51
  остаётся accepted Work5 restore base; старый retained-trial.zip — F1 diagnostic.
  Negative copies любого Work — diagnostics, никогда main working base.
  Все прежние DB/wheels/receipts/refs/G5 сохранить; новые backup сохраняют files И dirs.
  Один минимальный foreign-context sentinel допустим; второй полный Process,
  personal data/permanent workspace, прямое исправление DB/state Markdown запрещены.
  Не писать live Direction OS, archive или старые repos. Не запускать следующую
  Work автоматически; Work8 actual clean-chat/owner demonstration не часть Work7.
  M0 остаётся active до T7 и review. M1+, MCP/automatic transport/GitHub inbox,
  memory/retrieval/router/frontend/autonomy, external install/upgrade/full migration,
  Product remote/publication, расходы и новые внешние/необратимые права не допущены.
  CI/CD/GitHub Actions/notifications и настройка уведомлений исключены по обоим:
  owner-ack:solmax-zaratustra-local-setup-no-automation-20260907;
  owner-ack:solmax-zaratustra-work1-no-automation-20260907.
  Conforming HOW подтверждён owner-ack:solmax-plan-conforming-20260907 после сверки;
  повторная подпись не нужна. Plan divergence/реальный owner-owned выбор — HOME.
  Недоступный required tool, sizing/scope/acceptance blocker вернуть конкретно;
  пределы не сокращать молча. Repo AGENTS определяет native commands и STOP/STEER.
done_when: |
  1. После Work 6 submit_result сохраняет принятый результат, mutation, receipt и ссылку на следующую Work; связь восстанавливается из authoritative состояния.
  2. PLAN W19/W20 определяет единицу эффекта результата и продолжения; проверки повтора, сбоя и неизвестного исхода не допускают второго эффекта либо потерянного принятого продолжения.
  3. Пакет следующей Work содержит восстановимые решение, основание, действовавшую revision, результат и следующий шаг. Evidence фиксирует точный commit и вход/выход; понимание чистым чатом проверяет T7.
return: |
  HOME solmax: полный Product RESULT по каждому из трёх done_when с EXISTENCE
  built artifacts, actual commits/diff, PLAN W19–W27, version/schema/install layout,
  exact accepted input, result/mutation/receipt/next Work link и restart evidence.
  Exact query/context output/manifest/revisions/hashes/full byte budget; raw native
  --deliver и installed runtime failure/replay/unknown outcome/recovery/current
  authority/scope/budget checks; retained new main trial files AND directories,
  restore check и before/after preservation accepted Work5/Work6 refs/trials/evidence.
  Runnable walkthrough: команды, ожидаемые наблюдения, что сохранить. Отдельно
  assumptions/cuts/cost/manual-acceptance/next: solmax; actual checks не owner words.
  W19–W27 поимённо: решение, answerer остатка, момент решения, rewrites.
  Product handback не закрывает Direction T6/CALL/M0 и не выдаёт Direction successor.
  T6 behavioral close требует binding fresh physical G5 точного candidate по всем
  трём критериям. Work6 G5 reusable лишь для совпавших claims/inputs; новая Result/
  next семантика ею не проверена. После HOME отдельный Direction допуск Work8;
  пять фактов настоящего чистого чата и показ владельцу ещё не выполнены.
budget: одно минимальное приращение Work 7 внутри T6; калибровка до половины фокусного рабочего дня, PLAN проверяет размер; без нового срока/расхода

## PLAN agenda — W19–W27

| ID | Answerer / decision point / сохранённый остаток | rewrites |
|---|---|---|
| W19 | Product PLAN ДО submit_result: result/completion/next effect unit, identity/collision/stale/terminal/revoked, lost reply и discovery committed outcome. Work5 replay и read-only Work6 сохраняются. Owner-content выбор — HOME. | importer/receipts/linkage/failure tests/migrations; дешёвая переделка не доказана |
| W20 | Product PLAN ДО Result/continuation записи: file-before-DB, result/link durability, failures до/после commit, unknown outcome/recovery/rebuild и restart; exact repair/late loss/restore сохраняются. | durable references/recovery/evidence/migrations |
| W21 | Product PLAN ДО Result consumer: exact caller/request/content/path binding, current scope/rights, receipt/continuation-read authorization; Work3 exact owner words действуют. Реальный канал должен получить permission. | adapters/permissions/consumer boundaries; trust decision не runtime PASS |
| W22 | Product PLAN ДО next context: связь исторических решений/оснований с новой Work, effective/current revisions, global invalidation, full snapshot+byte revalidation и reference closure; все acceptance текущей Work, без latest-wins; full canonical budget. | snapshot/context contract/tests/возможные migrations; freshness/scope/budget не вырезаются |
| W23 | Product PLAN ДО передачи next package: exact delivered bytes/hash и сохраняемый input/output. Product PLAN/владелец в T7/Work8: реальный отдельный чистый чат и ответ по пяти фактам. | delivery/demo/повтор Work8; недоказуемая чистота — blocker там |
| W24 | Product PLAN ДО реализации: минимальные schema/CLI/serialization/operation identity, DB selection, transaction/BUSY/layout и explicit migration при необходимости; released/default migrate поведение сохранить. | локальные mechanics/tests/migrations; semantic change возвращается W19–W22 |
| W25 | Product PLAN ДО fixtures: новые копии одного fictional main graph, failures/replay/unknown continuation/current authority/stale/missing bytes/budget/foreign refs; actual owner demo — Work8. | fixtures/tests/demo; без второго полного или реального Process |
| W26 | Product PLAN ДО старта: новый isolated checkout от exact accepted base и отдельный installed trial; Work5/6 refs/trials/evidence сохранить. Владелец до permanent location/hosting/independent external install-upgrade. | package/layout/docs; новых внешних прав нет |
| W27 | Product PLAN ДО нового public Result/next consumer: только необходимые M0 seams. E1–E12 остаются в CONTRACTS, E4/E5/E7/E12 без выдуманных direct M0 APIs; будущий consumer решает HOW при своём допуске. | public Core/data/consumer migrations; M1+ не prerequisite, дешёвая замена не доказана |

END_OF_FILE: live/solmax/work/calls/c-solmax-zaratustra-m0-result-20260908-work7.md

CALL c-solmax-zaratustra-m0-artifacts-20260908-work4
to: executor
kind: engineering
direction: solmax
node: g-zara-m0-continuity
task: t-zara-m0-artifacts
repo: C:/projects/zaratustra
engineering_contract: 36
mode: PROBA
surface: cli
goal: |
  Принятое состояние Zaratustra ссылается на проверяемую версию содержимого,
  а производные представления восстанавливаются после сбоя.
context: |
  Work 4 — Artifacts + projections, план §41; T3 после завершённой T2.
  Direction root: C:/my_global_workflow_worktrees/solmax. От него:
  live/solmax/NOW.md, live/solmax/CHARTER.md,
  live/solmax/cards/t-zara-m0-artifacts.md,
  live/solmax/cards/closed/t-zara-m0-mutation.md,
  live/solmax/cards/bet-g-zara-m0-continuity.md,
  live/solmax/work/zaratustra-m0-work3-g5-2026-09-08.md,
  live/solmax/history/2026-09-08-s-solmax-zaratustra-work3-g5-20260908-a1.md,
  live/solmax/work/zaratustra-m0-work4-admission-2026-09-08.md.
  Binding G5 Work 3: Direction commit 397f9ec8c8cde744cfb07a727cd7f403354e208d,
  три done_when PASS для product implementation c4c795815169e3a38352b09d94cdeba15134f2b1,
  full report/evidence 5dce7fd665439968e46ee0725004be3bb5563eb7,
  report locator/basis HEAD 11b4b95d0f696c63e3ae4d56cb8fb4b748cd933d, version 0.3.0.
  При допуске actual Product — C:/projects/zaratustra,
  branch codex/work3-mutation-plan, remote отсутствует. Новый isolated checkout
  того же repo допустим; сверить actual path/branch/HEAD и сохранить их в report.
  Продолжение исходит из указанного проверенного HEAD, не из старого main.
  Product-local: AGENTS.md, validation.config (36/PROBA), полный RESULT.md,
  docs/work3/PLAN.md, OWNER-DECISION-20260908.md, INSTALL.md, evidence/;
  docs/work2/RECORDS.md, docs/work1/FOUNDATION.md, docs/setup/OWNER-DECISION-20260907.md.
  Принятый план live/solmax/work/zaratustra-architecture-plan-2026-09-05.md,
  §§3–7,26–29,41; SHA-256 4f90d19fc742ab616301b6b4121880f76c75faaeb1f606c8190a84853d8b3e0e.
  Design evidence: live/solmax/work/converge-g-zara-m0-continuity-arch.md и
  converge-g-zara-m0-continuity-verification-input-20260907.md в том же work/.
  Knowledge: live/solmax/knowledge/zaratustra-plan-conforming-approval-2026-09-07.md,
  zaratustra-local-no-automation-2026-09-07.md в том же knowledge/.
  Стек: Python 3.13, uv, sqlite3, Pydantic v2, pytest, ruff, SHA-256.
  Work 3 даёт единый DB Mutation API и exact local authorization, schema 3,
  atomic mutation/event/receipt, literal replay ordering и current rights.
  Его allowlist только Work metadata/status/rights; непустые content references
  отклоняются, affected projections пусты. Это не реализация Work 4.
  До зависимых решений PLAN отвечает на W20/W22/W24/W27 и затрагиваемые W19/W21.
  Продукт выбирает технический HOW; архитектурные варианты не являются authority.
boundaries: |
  Только Work 4/T3: один жизненный цикл содержимого и производных представлений.
  Принятые §4.2/4.4/5 сохраняются: новый immutable/versioned файл → SHA-256 →
  регистрация в DB → transactional active revision; projections read-only,
  содержат generated_from_revision/generated_at и пересоздаются из authoritative
  состояния. Git не transaction mechanism и не второй live store.
  Один общий Mutation API; current Work/authority, literal revision-before-duplicate,
  проверка referenced artifacts, mutation/event/receipt и affected projections
  сохраняются при расширении для допущенного lifecycle. PLAN определяет наблюдаемую
  границу file/DB publication, orphan/recovery/rebuild и late availability, а также
  необходимые revisions/ссылки до зависимой реализации, без скрытого обхода §5.
  Необходимый новый narrow artifact scope и actual authorization связываются
  с текущей Work и точной операцией; payload/model text не выдают права.
  W21 принимает local console / реально доверенный local-chat adapter без аккаунтов,
  login или same-OS-user isolation; это не blanket permission и не runtime PASS.
  Терминальная Work не переоткрывается; bootstrap/migration не будущий grant/updater.
  Сохранить все принятые DB/wheels 0.1.0/0.2.0/0.3.0 и receipts. Работать на новых
  копиях. Точные locators/backup/manifests:
  live/solmax/work/evidence/zaratustra-m0-work2-20260908/retained-trials.md,
  live/solmax/work/evidence/zaratustra-m0-work3-g5-20260908/identity-preservation.md,
  retained-trials-manifest.md и retained-trials.zip в том же G5 evidence/.
  Native original 0.3 trial: C:/Users/Anton/AppData/Local/Temp/zaratustra-work3-gnt5ksg0;
  fresh G5: C:/Users/Anton/AppData/Local/Temp/solmax-work3-g5-20260908-bz2pciak.
  Released schema changes только explicit migrations; принятые migration bytes
  не переписывать. Ручная DB/state Markdown правка для успеха/восстановления запрещена.
  Только fictional data и один исходный Process graph; без второго полного Process,
  реального Process, постоянного personal workspace, Direction OS writes,
  старых repos и archive reads. Новые файлы — только в явно выбранных новых копиях.
  Handoff file/stdin — Work 5; context — Work 6; submit_result/next — Work 7;
  clean-chat proof/full owner demo — Work 8. Не реализовывать и не объявлять их PASS.
  M1+, MCP, memory system, independent external install/upgrade и полный переезд
  не допущены. CI/CD/Actions/notifications/setup/test push, product remote/account/
  publication, расходы и external/irreversible effects исключены до отдельного слова.
  Оба owner-ack no-automation сохраняются; PROBA v36, OPORA не выбрана.
  Соответствующие плану технические решения не требуют повторной подписи.
  Содержательное расхождение или нерешённый owner-owned выбор возвращается HOME.
done_when: |
  1. После Work 3 versioned/immutable artifacts имеют проверяемый SHA-256 и
     согласованную регистрацию/active revision по принятому порядку §4;
     PLAN W20 определяет наблюдаемую границу публикации и восстановления.
  2. Read-only projections показывают происхождение и пересоздаются из сохранённого
     authoritative состояния; их сбой не становится вторым изменением либо второй истиной.
  3. Сохранённые проверки публикации/commit/rebuild и чтения недоступного либо
     изменённого содержимого подтверждают согласованность в заявленной границе,
     без ручной правки DB/state Markdown. Точная установленная версия, artifacts и
     raw evidence сохранены; native build/hygiene/types/boundaries/hidden-state checks проходят.
return: |
  HOME solmax: полный Product RESULT по трём done_when — actual commits/diff,
  version, wheel/hash/install/workspace locators и raw native/installed evidence,
  assumptions/cuts/cost/manual-acceptance/next: solmax; W19–W27 dispositions
  поимённо с оставшимся answerer/моментом решения/rewrites.
  Простой воспроизводимый walkthrough для владельца: что запустить, что увидеть,
  какие выходы сохранить; actual check отдельно от owner words и будущего Work 8 demo.
  Product не закрывает Direction CALL/T3/M0, не выдаёт следующий Direction CALL
  и не начинает Work 5. Close route T3 — binding fresh physical G5 точной версии.
  Старый G5 поддерживает только совпавшие Work 3 claims/inputs, не новую файловую
  гарантию. Неполнота/необходимый выход за scope/authority/sizing blocker возвращается
  полным конкретным RESULT; критерии и W19–W27 не исчезают.
budget: одно минимальное приращение Work 4 в существующей T3; калибровка до половины фокусного рабочего дня, без нового срока/расхода; PLAN проверяет размер до исполнения

## PLAN agenda — W19–W27

| ID | Принято в Work 3 / оставшийся ответчик и момент | rewrites: |
|---|---|---|
| W19 | Literal order, stale original conflict, refreshed duplicate receipt, collision, terminal/current rights проверены. PLAN до Work 4 решает расширение на artifact lifecycle без смены семантики; Result/next effect до Works 5/7. | importer, receipts, linkage, failure tests/migrations; cheap reversal не доказан. |
| W20 | DB atomicity и simulated lost reply проверены. PLAN до Work 4: file publication/DB commit, orphan/recovery/rebuild, late content availability; Result continuation до Work 7. | durable references, recovery/evidence/migrations; DB PASS не file durability. |
| W21 | Owner local trust boundary, exact request/path и current/revoked scope проверены. PLAN до новых artifact operations Work 4 определяет необходимый scope/binding; actual importer/context до Works 5/6/7. | adapters/import/permissions; W21 не runtime acceptance. |
| W22 | Single transaction/snapshot и global revision всех допущенных Work mutations проверены. PLAN до Work 4: artifact/dependent revisions/references; scope/freshness/budget/delivered manifest до Work 6. | snapshot/context contracts/tests; обязанности не cut. |
| W23 | Clean-chat proof отсутствует. PLAN протокол до Works 6/8, exact delivered input и отдельный реальный ответ по пяти фактам в Work 8. | delivery/demo; недоказуемая чистота — blocker. |
| W24 | v3 migration, typed requests, UUID, canonical JSON/SHA-256, UTC, separate revision/transaction/BUSY проверены. PLAN до Work 4: нужные file/schema/layout/recovery/cleanup механики. | mechanics/tests/migrations; семантика возвращается W19–W22. |
| W25 | Копии одного fictional graph и foreign id/path checks; это не context isolation. PLAN fixtures до зависимых file checks Work 4 и Works 5/6/8, без второго полного Process. | fixtures/tests/demo. |
| W26 | Actual local refs/no remote, отдельная 0.3 install и сохранённые 0.1/0.2/0.3 подтверждены. PLAN перепроверяет меняющиеся факты; permanent folder/hosting/external install-upgrade — future admissions. | package/layout/docs; пересмотреть при внешних потребителях. |
| W27 | Core/data/receipt seam сохраняет E1/E2/E3/E6/E8/E9/E10/E11. PLAN до публичных artifact/projection решений Work 4; полные consumer contracts при их допуске. E4/E5/E7/E12 без выдуманного direct M0 API; M1+ не prerequisite. | Core/data/consumer migrations; cheap replacement не доказана. |

END_OF_FILE: live/solmax/work/calls/c-solmax-zaratustra-m0-artifacts-20260908-work4.md

# M1 / T2 — точная привязка внешнего пакета

CALL: c-solmax-zaratustra-m1-packs-20260909-exec; contract 36; PROBA.
Basis: f67959e7c1a412c202ebb0d6e67938ec4355042f, docs-only потомок принятого T1.
Execution: C:/projects/zaratustra/_scratch/m1-packs-20260909,
branch codex/m1-packs-20260909. Source чист, pin/stamp 36, STOP/STEER отсутствуют.

## W15 — решение до изменения state

Pack — явно зарегистрированный trusted Python adapter с неизменяемым manifest:
pack_id, pack_version, process_type, contract_version, state_version. Один pack
предоставляет один type; Process.id — экземпляр этого type. Registry — immutable
локальный набор явных registrations, заново собираемый trusted host при запуске.
Это установка кода, не operational state и не выдача прав. Нет discovery/import
по данным Work, автоматического выбора latest или внешней установки.
Повтор той же registration идемпотентен; замена того же pack_id/version другим
manifest/adapter — collision. Разные версии могут сосуществовать.

В Core появляется только общий immutable PackReference, optional exact binding
в Process и Work, и одна операция bind_pack в существующем apply_mutation.
Она атомарно привязывает ранее unbound Process и ready Work, не меняет scope,
goal, requirements, artifacts или историю. Повтор exact operation_id возвращает
сохранённый receipt по прежним правилам; иной binding отвергается. Начатая Work
и её next Work сохраняют exact binding. Старые завершённые Work не переписываются.
Process binding одноразовый: смена сохранённой версии/схемы не предоставлена T2.

Версии сравниваются точно; contract1/state1 — единственная исполняемая пара T2.
Missing exact pack/version => missing_pack, совпавшая координата с другим type/
contract/state либо неподдержанные contract/state => incompatible_pack. Отказ
не вызывает rule и не меняет DB/history/authority. v2 рядом с v1 не заменяет v1;
удаление v1 блокирует пакетное продолжение старой Work; возвращение exact v1
восстанавливает его. Новый независимый fictional Process может явно выбрать v2.
Миграция начатой Work не подразумевается совместимостью semver: попытка смены
отвергается; будущая миграция нуждается в отдельном плане и точной Mutation.

Pack rule получает только immutable Work и bytes её проверенного принятого
результата. Он предлагает NextWork; trusted host отдельно подтверждает exact
Result request. Чтение сначала проходит open_work/current rights/scope/revision.
Core остаётся доступен для разрешённого просмотра истории, revoke/repair и
точно подтверждённых общих операций без установленного пакета: пакет не становится
источником authority и не лишает владельца административного восстановления.
Trusted Python code сохраняет W21 модель; registry не sandbox для враждебного
кода того же OS-пользователя. Manifest identity не выдается за аттестацию кода.

Schema7 — явная semantic migration JSON records/events, без новых domain tables.
Она записывает версию формата, сохраняет все прежние records/events/receipts bytes
и revision. Released migrations1–6 и default migrate4 не меняются. Legacy unbound
JSON сериализуется как раньше, без новых null-полей. Read/init не мигрируют.
CLI допускает только явный существующий migrate --to 7; bind — Core API T2.

Рассмотрены автоматический latest/rebind и хранение binding в свободном тексте
requirements: первое меняло бы смысл начатой Work, второе не даёт общего immutable
инварианта. Выбрана точная ссылка с явным отказом; небольшой общий additive
переход на существующих JSON records/Mutation/history, не redesign foundation.

## Проверка и rollback до BUILD

Baseline tools.check: 148 PASS, полный raw _scratch/m1-packs-evidence/baseline-check.txt.
До edits штатный tools.probe_m1 создал _scratch/t2-baseline-probe; три успешных
перехода восстановлены из exact pre-submit backups. Исходные папки не меняются.
План коммитится до зависимых schema/code; baseline wheel и эти backups сохраняются.

Новые проверки используют настоящий Core: регистрация, совместимость, atomic
Process/Work binding, exact authorization, revoked/terminal rights, stale revision,
replay/collision, полный journal reconstruction, inherited next binding, rollback
ошибки транзакции, legacy6→7 без переписывания, missing/v2-only/restore-v1.
Фиксируются exact commits/inputs/requests/receipts/context/state/DB hashes и diff.
Перед привязкой и успешным Result — retain_trial; restore в новую папку,
сверка bytes/layout и повтор через API. Ни SQL, ни state Markdown edits.
Полный tools.check --deliver; тесты проверяют невидимые state/authority свойства.
Owner-readable READOUT показывает жизненный цикл; owner acceptance pending.

## W15–W20 и оставшиеся обязательства

- W15: T2 решает модель/регистрацию/версии/связь/отказы выше. Предметные правила
  T4/T5 остаются PLAN; полный семь-capability контракт не поставляется T2.
- W16: OPEN → PLAN/T3, все семь ответов, scope/revisions, empty/denied/unavailable,
  metadata/counts/consistency, смена прав/недоступный context. rewrites: публичный
  контракт, read guards, mapping/context/projections/потребители; ≤1 дня не доказано.
- W17: T2 — общая подготовка до первого полного M1 Process. Обе гарантии P§30
  «без изменения основной семантики Core» и P§40 «без изменения Core» сохраняются.
  OPEN → PLAN/T3–T5: окончательный baseline до второго, совместное размещение и
  полный контракт. rewrites: границы/refactor/frozen diff/evidence/повтор сценариев;
  ≤1 дня не доказано. Изменение гарантии → OWNER. T2 не доказывает Proof C.
- W18: T2 повторно использует fictional batch bytes для lifecycle; OPEN → PLAN/T4/T5
  полные два разных процесса. rewrites: fixtures/сценарии/ожидания, обычно обратимо
  до предметного кода; после оценить заново. Новый concept/acceptance → OWNER.
- W19: OPEN → PLAN/T6: один общий обзор, без frontend/assistant; смысл W16.
  rewrites: renderer/adapters/вывод, обычно ≤1 дня до внешнего контракта.
- W20: T2 exact lifecycle evidence/rollback выше. OPEN → PLAN/T4–T7: полные оба
  сценария, сравнение второго и обзор. rewrites: capture/manifest/states/replay;
  до прогона обычно ≤1 дня, потерянная provenance потом не гарантирована.

Существующее ограничение одного Process/workspace сохраняется в T2; решение
сосуществования принадлежит оставшемуся W17, не вырезается из M1. В Core нет
названий fictional правил, их условий или выбора версии за владельца.

## Делегация и граница отчёта

Сверка: Direction plan 2026-09-05 §§8/30/40, shape T2/C01/C02/C06, принятый T1
и knowledge/zaratustra-plan-conforming-approval-2026-09-07.md. Verdict:
conforms within T2 under owner delegation; отдельная реплика approval не придумана.
Новая owner concept/смягчение guarantees/redesign/authority defect → HOME stop.
M0 partial. Семь возможностей и T3–T7 остаются открыты. REPORT HOME:
RESULT.md, next: solmax; не Direction close, не CALL/T3. Binding fresh physical
G5 и реальные слова владельца о T2 ещё pending; helpers не заменяют G5.

END_OF_FILE: docs/m1-packs/PLAN.md

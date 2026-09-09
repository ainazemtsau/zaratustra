# M1 / T2 — точная версия пакета сохраняется вместе с Process и Work

## outcome

REPORT HOME на c-solmax-zaratustra-m1-packs-20260909-exec, engineering_contract36,
PROBA. Техническая реализация T2 подготовлена и проверена; завершение PROBA,
Direction T2 и всей M1 не заявляется: owner acceptance и fresh physical G5 pending.

Zaratustra0.8.0 добавляет immutable external registration и PackReference,
явный schema7 и bind_pack через единственный apply_mutation. Привязка Process/Work
атомарна и одноразова; next Work наследует exact binding. Missing/incompatible
отказывают без изменений; новая установленная версия не заменяет старую.
Общее управление authority/history/repair остаётся в Core, а предметный rule — снаружи.

## evidence

Точные версии:
- basis: f67959e7c1a412c202ebb0d6e67938ec4355042f;
- PLAN + verified baseline до source edits: 8dfaa5c50faa6c50bd6e67d357ee7bcef3dbf200;
- implementation/source: f728ad6a8645ba04532e1cd74a34ea57c31c4dd8;
- этот финальный REPORT сохраняется отдельным docs/evidence commit поверх source;
  source/tests/tools/lock/authority после source commit не менялись.

Worktree C:/projects/zaratustra/_scratch/m1-packs-20260909;
branch codex/m1-packs-20260909. Source review worktree остался на basis.
Исходный worktree был чист; path/branch свободны; pin/stamp36 и отсутствие
STOP/STEER перепроверены перед созданием и перед каждым запуском.

| done_when исходного CALL | Полученное evidence | Граница вывода |
|---|---|---|
| 1. PLAN-модель pack/type/instance, registration, compatibility, сохранённая связь | docs/m1-packs/PLAN.md записан первым; Registry проверяет identity/collision, exact contract1/state1. bind_pack записывает Process и Work в одном event/receipt, revision3→4, без изменения scope. Context и отдельный Python restart читают exact binding. | Технические проверки T2 PASS; не полная семь-capability M1. |
| 2. Missing/incompatible и версия незавершённой Work | lifecycle missing/v2-only/incompatible-contract/incompatible-state/in-place-change: пять отказов, DB bytes/history неизменны. Возврат v1 позволяет Result7→8 и next Work с v1. Другой новый Process явно связывается и продолжается с v2. | In-place миграция не предоставлена: явный отказ, не скрытый upgrade. |
| 3. Commit, runnable Mutation/revision/history evidence | native tools.check --deliver на clean source: 173 tests PASS, 44.58s pytest, build/hygiene/types, шесть import contracts. 25 новых тестов проверяют exact authority, stale, replay/collision, journal, наследование, отказ после revoke/terminal, transaction rollback и legacy6→7 bytes, включая старый Result. | Это авторская инженерная проверка; binding G5 всё ещё нужна. |

Основные сохранённые артефакты в docs/m1-packs/:
- READOUT.md — короткий показ; REPRODUCE.md — команды и rollback;
- evidence/check-deliver.txt — полный native output;
- evidence/lifecycle.zip и lifecycle-manifest.json — exact inputs, requests,
  confirmations, receipts, state/history/context, rollback backups, восстановленные
  состояния и runtime.json (source f728ad6, source diff пустой);
- evidence/summary.json — итог того же сценария;
- evidence/restart-read.json и restart_read.py.txt — отдельный interpreter,
  retained schema7/revision8, ready Work, exact v1 и новое scoped context без записи;
- evidence/source-verification.json, source.diff — Git blobs/hashes и граница diff;
- evidence/zaratustra-0.8.0-py3-none-any.whl — проверенная сборка; Python files внутри
  wheel сверены с проверенными исходниками;
- evidence/manifest.json — SHA256/размер каждого evidence файла, кроме самого manifest.

Released migrations1–6, прежние Core tests, T1 process_probe, local adapter и
validation.config побайтно/по Git неизменны относительно basis. Это проверка
provenance, не source-scanner доказательство поведения. Реальное поведение
проверяют Core tests и lifecycle. Новая schema7 — semantic JSON-format migration:
добавляет запись schema_migrations, не переписывает старые domain rows/history.
Default migrate4, init/read без миграции и текущие scoped rights сохранены.

Rollback: baseline0.7.0 wheel и исходные fictional backups сохранены до edits.
В T2 восстановлены pre-migration, pre-bind и pre-result в НОВЫЕ папки;
полный layout/hashes совпали. Core перечитал legacy state; bind и submit повторены
с exact request и новым разрешением на восстановленный путь. Исходные folders и
все evidence сохранены, прямых SQL/state Markdown edits нет. Schema downgrade
не предлагается: возврат старого продукта использует старый backup в новой папке.

## assumptions

- Pack содержит один process_type; Process.id — instance. Exact manifest включает
  pack_id, pack_version, process_type, contract_version и state_version.
- Registry — явная immutable trusted-host конфигурация установленного Python кода;
  её восстановление при старте не создаёт Operational authority. Manifest identity
  не аттестует код, и trusted same-user Python не sandboxed (сохранённая W21 модель).
- Core хранит generic reference и проверяет state/authority/integrity; совместимость
  установки проверяет внешний registry. Core не импортирует pack и не ищет latest.
  Только отдельно подтверждённый request изменяет state; packet/file не даёт прав.
- Process/начатая Work не перепривязываются. Версии могут сосуществовать; для старой
  Work нужен exact старый pack. Отсутствие pack не отменяет owner-local историю,
  revoke и разрешённый Artifact repair. Для state migration нужен отдельный PLAN.
- T2 сохраняет существующий один Process/workspace. Разрешение совместного размещения
  остаётся W17 в полном M1, не объявляется решённым или вырезанным.

## cuts

Новых cuts исходного T2 CALL нет. Полная диспозиция с rewrites — PLAN W15–W20:
W15 lifecycle решён в пределах T2; W16 OPEN → PLAN/T3 (все семь capabilities,
scope/revisions, empty/denied/unavailable, metadata/counts/consistency); W17 OPEN
→ PLAN/T3–T5 (окончательный baseline и сосуществование); W18 OPEN → PLAN/T4/T5
(два полных fictional процесса); W19 OPEN → PLAN/T6 (общий обзор); W20 OPEN
→ PLAN/T4–T7 (полные сценарии и доказательство второго). T2 W20 evidence сохранено.

Обе гарантии P§30 «без изменения основной семантики Core» и P§40 «без изменения
Core» сохранены. Изменения Core здесь — общая подготовка T2 до подключения полного
второго Process; они не предъявляются как доказательство W17/Proof C. Предметных
веток в Core нет; выбранная фикстура повторно использует принятый T1 batch rule.

M0 partial; Work8/original attachment не читались и не повторялись. Реальные
процессы, M2+, новый frontend/transport/scheduler, автономность, CI/CD/Actions,
уведомления, внешние/денежные права, расходы и публикация отсутствуют.

## cost

Одна ограниченная T2 source-реализация и два отчётных этапа (PLAN/baseline и handback).
Новых runtime/dev dependencies нет; lock меняет только zaratustra0.7.0→0.8.0.
Baseline native: 148 tests PASS, pytest31.13s. Предварительные native запуски:
один unused import в новом тесте, затем две type-аннотации; после исправления
24 focused tests PASS (6.94s). Ещё один legacy-chain тест добавлен перед полным
native запуском; полный 173 PASS с первого запуска. Все raw выводы сохранены.
Final lifecycle и отдельное чтение после restart прошли с первого запуска.

Managed sandbox не читал установленный uv Python и запрещал Git refs; действия
прошли разрешённое escalation. Требуемые uv/native tools доступны; обхода тестов
или источника нет. Денежная стоимость/API tokens не измерялись; дедлайн не назначен.

## manual-acceptance

PENDING. Владелец сказал «RUN c-solmax-zaratustra-m1-packs-20260909-exec» — запуск
реализации и новых fictional проверок. Это не принятие результата T2. Технический
PLAN соответствует принятому плану по сохранённой делегации; новых слов approval
не придумано. Старое «принимаю» относится только к T1.

Предмет будущей приёмки — docs/m1-packs/READOUT.md: точная версия переживает
смену установки, отказы не портят state, возврат old pack восстанавливает продолжение.
Fresh binding physical G5 pending, не light close; separate Python process и
авторские тесты не физическая G5. Подагенты не запускались.

## next

solmax — REPORT HOME на исходный CALL для отдельной свежей G5 exact candidate
и фактической приёмки владельцем, затем Direction сверяет закрытие.
Этот Product REPORT не закрывает Direction CALL/T2/M1, не выдаёт successor
и не запускает T3. live/** и чужие product worktrees не изменены.

END_OF_FILE: RESULT.md

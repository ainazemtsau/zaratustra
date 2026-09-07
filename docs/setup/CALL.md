CALL c-solmax-zaratustra-m0-bootstrap-20260907-setup
to: executor
kind: engineering
direction: solmax
node: g-zara-m0-continuity
task: t-zara-m0-foundation
repo: C:/projects/zaratustra
engineering_contract: 36
mode: PROBA
surface: cli
goal: |
  Новый локальный репозиторий Zaratustra подготовлен для первой продуктовой
  работы: применимый инженерный контракт и проверяемая среда разработки
  установлены, результаты настройки воспроизводимы.
context: |
  Это первый setup-only root, до Work 1. Каталог C:/projects/zaratustra
  ещё не создан: Test-Path=False 2026-09-07 после подтверждения владельца.
  Владелец ответил «да» на «Подтверждаешь C:\projects\zaratustra?»;
  точное исходное форматирование вопроса и факты: live/solmax/work/zaratustra-m0-bootstrap-admission-2026-09-07.md,
  owner-ack:solmax-zaratustra-repo-path-20260907.
  Допуск предусматривает создание/инициализацию нового локального repo по этому
  пути. Старые C:/projects/zaratusta и C:/projects/zaratusta-product не являются
  выбранным продуктом или источником уже выполненного setup.

  Корень доступных read-only источников Direction OS:
  C:/my_global_workflow_worktrees/solmax, basis 638a12a815880e6f9c01cbeff155b74f92b26001.
  Относительные пути этого CALL разрешаются от него.
  os/engineering/PROJECT_SETUP.md; os/engineering/CONTOUR.md (режим v36);
  os/engineering/CONTRACT_VERSION (при выдаче current: 36);
  os/engineering/VALIDATION.md; os/engineering/TOOLING.md;
  os/engineering/profiles/README.md; os/engineering/profiles/python.md.
  live/solmax/CHARTER.md; live/solmax/NOW.md;
  live/solmax/cards/t-zara-m0-foundation.md;
  live/solmax/work/zaratustra-m0-shape-2026-09-07.md;
  live/solmax/work/zaratustra-m0-shape-owner-approval-2026-09-07.md;
  live/solmax/work/zaratustra-architecture-plan-2026-09-05.md §§26–29,41,
  SHA-256 4f90d19fc742ab616301b6b4121880f76c75faaeb1f606c8190a84853d8b3e0e;
  live/solmax/work/converge-g-zara-m0-continuity-verification-input-20260907.md,
  SHA-256 e428e19a9342dd12541462dfff953de969a64609257cd2c8c79f6145bae3cdfe;
  live/solmax/work/converge-g-zara-m0-continuity-arch.md — варианты/evidence
  для PLAN, не binding ADR и не выбранные решения.
  live/solmax/knowledge/zaratustra-plan-conforming-approval-2026-09-07.md;
  live/solmax/knowledge/light-close-throughput-measured.md.

  Стек уже принят: Python 3.13, uv, sqlite3, Pydantic v2, pytest, ruff, SHA-256.
  Наблюдались Windows/PowerShell, uv 0.8.22, системный и managed Python 3.13.7.
  Проверка новой среды/зависимостей предстоит setup; иной runtime не выбран.
  Отдельная пользовательская workspace выбирается при фактической установке.
  Python-профиль существует, повторное интервью о принятом стеке не требуется.
  Его package=false/PYTHONPATH не заменяют требование устанавливаемого продукта;
  совместимое packaging/layout остаётся W26 → PLAN/setup, HOW здесь не задан.

boundaries: |
  Только PROJECT_SETUP для неинициализированного repo. Допуск не является
  Re-sync и не включает Work 1–8 как дополнительные features. Создание SQLite
  state, migration v1 и workspace init относятся к следующей Work 1; затем
  Work 2–8 строго последовательно. Структурный scaffold настройки не означает
  исполнения этих продуктовых Works.
  PROBA — default v36; OPORA требует отдельного точного слова владельца.
  Применимость PROJECT_SETUP/профиля определяется вместе с CONTOUR v36.
  Согласие на путь и M0 не является согласием на OPORA или новым HOW.
  Не менять accepted WHAT, стек, порядок §5, appetite, WIP, приоритет, сроки.
  Все W19–W27 ниже остаются open → PLAN; W26 подтверждён только в части
  имени/локального пути. Ответ нужен до зависимого решения; остальные строки
  сохраняются для следующих Works и не расширяют setup.
  Duplicate-first не утверждён и не подменяет буквальный §5.
  M0 сохраняет W01–W06 ниже, реальный показ после Work 8 и остановку перед M1.
  Один fictional Process; отрицательный fixture чужого контекста не является
  вторым полноценным Process. M1+, MCP, real Process, полный переезд и
  внешний independent-install proof остаются вне M0.
  Пользовательские данные отделены от product repo; живой Direction OS остаётся
  рабочей системой. Исполнитель не пишет в Direction OS или старые repos.
  Архивы без owner_ack_archive_read не читаются.
  Новых внешних прав, публикации, удалённого repo/account и расходов этот CALL
  не выдаёт. Если обязательное действие нуждается в них — конкретный вопрос
  владельцу/ESCALATE, без выдуманного PASS или самовольного cut.
  Необходимое расхождение с принятым планом и неразрешённый owner-owned выбор
  предъявляются владельцу; подтверждать соответствующее плану можно только
  в пределах записанной делегации и с точным предметом сверки.

done_when: |
  1. В C:/projects/zaratustra существует новый локальный Git repo с проверенной
     применимой настройкой PROJECT_SETUP для Python и PROBA v36; точный commit,
     installed contract stamp и disposition каждого применимого пункта
     подтверждены артефактами/выводом проверок, пропуски названы явно.
  2. Заявленные команды подготовки/проверки среды воспроизводимы на доступной
     Windows; сохранён raw output применимых проверок, а решения/ограничения
     установки учитывают отдельную пользовательскую workspace и будущую Work 1.
  3. Product RESULT содержит точный diff/commits, checks, assumptions, cuts,
     cost, manual-acceptance и next: solmax; сохранена передача W19–W27,
     Work 1–8 не объявлены выполненными, T1 и M0 не закрыты этим report.

return: |
  HOME в solmax: product RESULT с evidence по каждому из трёх done_when,
  фактическим repo/path/commit/stamp, применимостью checklist PROJECT_SETUP,
  командами и raw check outputs, точными словами для owner decisions,
  реально проверенными runtime/install фактами либо полным blocker.
  Review/check receipts не выдумывать; mode-specific n/a обосновать источником.
  Требуемое изменение Python-профиля, если обнаружится при реальном setup,
  вернуть как предложенную точную дельту в RESULT; в workflow repo не писать.
  Product REPORT — evidence input для следующей Direction work-сессии,
  не authority закрыть call/T1. Direction сверит его и выдаст следующий
  локальный допуск; engineering executor сам не выдаёт Direction CALL.
  Будущее закрытие T1 следует её close_route: binding fresh G5 либо light
  только при фактической применимости правила work. Сам setup не закрывает T1.

budget: один setup-only root в admission T1; без продуктовых features и новых сроков/расходов

# PLAN agenda — сохранённые открытые строки

Источник таблицы: cards/bet-g-zara-m0-continuity.md, plan_agenda.
Все строки open; W26 дополнен отдельным owner receipt выше, а не закрыт.

| ID | Передача и момент решения | Цена переделки / основание |
|---|---|---|
| W19 | → PLAN; replay/revision/terminal/collision/receipt-read и единица эффекта Result/next Work; до зависимой реализации T1/T2, затем T4/T6. | rewrites: importer, receipts, failure tests, next-Work linkage и возможные migrations; ≤1 дня не доказано. §5 и исходная W19. |
| W20 | → PLAN; artifact bytes/publication/commit/recovery/rebuild; до зависимых решений T1–T3/T6. | rewrites: durable references, recovery и evidence, возможные migrations; дешёвый stub не доказан. §§4–5/28 и W20. |
| W21 | → PLAN; trusted caller/current authority/bootstrap/receipt-read/scope; bootstrap до первой Work, затем T2/T4/T5/T6. | rewrites: trust boundary, import paths и permissions tests всех mutations; ≤1 дня не доказано. §6.1 и W21. |
| W22 | → PLAN; snapshot/dependent revisions/scoped references/budget/manifest; до зависимого состояния T1/T3 и поведения T5/T6. | rewrites: snapshot/context contract и проверки; freshness/scope/budget не вырезаются как формат. §§7/10 и W22. |
| W23 | → PLAN; реальный отдельный чистый чат, точный delivered input и сохранённый ответ; протокол до T5/T7, actual evidence в T7. | rewrites: протокол показа и повтор Work 8; прежняя предварительная оценка ≤1 дня при доступной поверхности. Недоказуемая чистота — blocker. W23. |
| W24 | → PLAN; локальные formats/schema/CLI, transaction mode/BUSY, identity, timestamp, layout/cleanup; в соответствующей Work до реализации. | rewrites: ограниченный прототип и его проверки, прежняя оценка ≤1 дня до внешних зависимостей; смена семантики возвращается W19–W22. W24. |
| W25 | → PLAN; минимальные fictional fixtures и отрицательный чужой context без второго полного Process; до T4/T5/T7. | rewrites: тестовые данные и повтор проверки; прежняя оценка ≤1 дня. Реальный Process не выбирается. W25. |
| W26 | → PLAN/bootstrap; доступные product repo/name/location/install layout; T1 начинается с проверки фактов. | rewrites: scaffold/metadata/docs до публикации, прежняя оценка ≤1 дня; после внешних зависимостей пересмотреть. Внешние права не добавлены. W26. |
| W27 | → PLAN; только необходимые M0 seams E1–E12, без входящих M1+ prerequisites; до зависимого публичного решения каждой Work. | rewrites: публичный Core contract/данные и возможные migrations потребителей; дешёвая замена не доказана. W27 и §CONTRACTS E1–E12. |

# Exact M0 acceptance — контекст последующих Works

Источник: done_when действующей ставки; соответствует W01–W06 проверенного
входа. Это не дополнительные done_when setup-only root.

1. В выбранной пустой папке создаются workspace, один вымышленный Process и Work. Состояние сохраняется между запусками.
2. Владелец проходит цепочку: обсуждение в ChatGPT → принятый результат через Handoff → импорт в Codex → записанный результат с квитанцией → следующая Work. Импорт поддерживает file/stdin.
3. Отдельный чистый чат получает только актуальный пакет контекста и правильно называет решение, его основание, действовавшую revision, полученный результат и следующий шаг.
4. Проверки подтверждают: повтор Handoff даёт один эффект; устаревшая revision вызывает conflict; сбой сохраняет согласованность; операция без прав отклоняется; чужой контекст не попадает в Work.
5. Журнал позволяет восстановить, кто, на каком основании и что изменил. Производные представления пересоздаются из сохранённого состояния; сценарий проходит без ручной правки DB/state Markdown, предметных исключений в Core и доверия устаревшему контексту.
6. После Work 8 владельцу предъявлен работающий сценарий, выполнение остановлено перед M1.

END_OF_FILE: live/solmax/work/calls/c-solmax-zaratustra-m0-bootstrap-20260907-setup.md

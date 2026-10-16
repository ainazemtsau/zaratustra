# Пакет A: технический возврат

Source: `3d4bcbc9acf3a6374643f8c9b72a056e188354b8`, база `9d903d709783601c4878b707b9618031753a6854`. Это кандидат пакета A принятой редакции 2; первая поставка целиком и полезность модели ещё не приняты.

## Коррекция F1/F2 после независимого NOT READY

Независимая проверка прежнего e6277cf/source3870ac4 получила NOT READY: F1 допускал невалидные вложенные декларации при пустом/отсутствующем/nullable значении; F2 позволял старому ответу снять новое ожидание. Исходный отчёт сохранён без изменений.

На final source неизменённые контрпримеры перешли из **2 RED в2 GREEN**. Исправленный пакет A: **124 PASS/242.03s**, все **22 отрицательных контроля пойманы**. Exact oracle требует настоящую привязку вопроса к A1/generation1. Полный native gate: **1522 PASS/1518.47s**. Инварианты, проверка соседних случаев и RED/GREEN evidence — `F1-F2-CORRECTION.md`, `evidence/f1f2/FOCUSED-PROVENANCE.json`.

Независимый повтор закрыл F1/F2 на уровне кода: собственные124 PASS/222.01s,22/22 controls,42 negative+16 positive C3/C8 admissions и соседние F2/race проверки. **Финальная reconciliation нового evidence-only candidate ещё ожидается**. Принятие владельцем не заявлено.

## Что показано

Одинаковая фиксированная трасса проходит через независимый driver и настоящий Pi 1.0.4. Provider сценарный, localhost; его заранее заданная речь не доказывает полезность реальной модели.

1. Сохраняются M1–M20, включая точную просьбу: «Есть десять минут, потренируем разговор в отеле. Начни без плана и карточек». A1 закрепляет полный диапазон до M20, Method, обязательную память, profile и каталог текущих ключей.
2. Actual Pi вызывает native `zara_change`. Activity и корреляция `(A1, create-activity)` → command/receipt фиксируются до native terminal. Driver проходит тот же subject-write контракт. Work для этого bounded conversation turn заранее создан через C4; атомарный C3 Activity+initial_work проверяется отдельно, без создания лишней Work в happy trace.
3. Terminal удерживается исходной UTF-8 `message_end` строкой Pi. Пока A1 завершает свою границу, поступает M21: «Теперь только пять минут». C8 сохраняет W7, final и cursor=20; M21 остаётся pending.
4. Клиент открывается заново; сохранённый terminal применяется без нового send. Отдельные fresh-process проверки воспроизводят crash/replay, а callback не повторяет subject effect.
5. Адресный ответ закрывает именно W7@1. A2 получает M21 и ответ, а также исходную просьбу, вопрос/предыдущий final, Work goal, current catalog и tool receipt ledger. Итог — cursor=22, один final на Attempt, пустая таблица acceptance.

`evidence/f1f2/current/client-parity.json` сравнивает одинаковые доменные IDs/версии/Work/Attempt/wait/heads/tool ledger обеих трасс. `evidence/f1f2/current/client-parity-stale.json` и `evidence/f1f2/current/client-parity-forbidden.json` сравнивают реальные отказы native callback и driver: stale_basis и denied.

## Контракт в A

| Область | Реализация и предел |
|---|---|
| C0 | Strict Pydantic envelope/payload, wire/v1 vectors, сохранённые exact user bytes, текущий trusted principal, committed receipt/idempotency, exact heads/CAS, типизированные ошибки и diagnostic ID. `confirmation_ref` явно отвергается как unsupported; one-shot confirmation не объявлена работающей |
| C1 | describe, bounded snapshot, exact read, receipt lookup; `Client.preview(Request)` исполняет тот же admission/SQL путь с rollback. Snapshot — полная ограниченная страница локального пространства, до 1000 строк/таблицу; pagination=false |
| C2 | Message+sequence+processing intent+receipt атомарно; stable event ID и exact active reply_to wait/revision/Attempt/generation, origin из credential |
| C3 | Typed subject revisions/unique keys, value-independent recursive schema declaration, strict optional neutral schema_ref, CAS/history/audit/receipt; initial_work требует open_work; tool admission требует live claimed Attempt, того же executor и текущих pinned bases |
| C4–C5 | Work+prepare intent; точные Method/inputs/profile, исходный cursor и непрерывный manifest/cutoff; один активный turn/Attempt; bounded context 1000 rows/1 MiB с предыдущей exact conversation basis и каталогом |
| C6 | Claim/action identity и верхняя граница calls до dispatch; Pi forwarding bridge атомарно ограничивает физические sends. Повтор claim не даёт права resend. Учёт консервативный: резерв не возвращается автоматически по неполным данным |
| C7 | Matching executor, event dedupe, исходный terminal, unknown и доверенное host reconciliation evidence, поздний fenced output только evidence. Общего live third-party reconciler нет |
| C8 | Result/final slot, typed changes, cursor CAS до pinned cutoff, wait/continuation и receipt в одной транзакции. Generic delta не меняет права/acceptance/origin/receipts/execution states. A использует whole pinned prefix; произвольный partial terminal bundle не поддержан |
| Права/control | Trusted owner grant/revoke и отдельное exact acceptance; host/model не может имитировать human. Pause/resume/refresh не оживляет старый tool executor. Ведущий отдельно воспроизвёл cancel+late output, known-running reconciliation и fixture-only epoch fencing (root-gate-seams-report.json). Полная расширенная матрица B и one-shot approvals остаются отдельной работой |

## Проверки A

| Gate | Итог на fixed A scope | Проверяемое опровержение |
|---|---|---|
| G1 | PASS | Core wheel без app/legacy; полный installed driver вне checkout, audit запрещает sockets/processes/посторонние files/config; import guard до обоих imports; запрет legacy dependency ловится seed |
| G2 | PASS | Real Pi native callback и driver; exact domain-table parity, actual stale/forbidden callback refusals; seed fake callback effect ловится |
| G3 | PASS | Два writers/CAS, unique current key, строгие identity types, exact historical bytes после reopen; stale-write seed |
| G4 | PASS | Fresh-process crash до receipt/после commit, независимое SQL чтение; ранний ingress commit и потерянный input intent ловятся |
| G5 | PASS | Actual receiver получает original/correction/Method/memory/profile/prior wait/result/goal/catalog; current bases проверяются при claim, tool effect и C8. Drop-input seed и stale public repros |
| G6 | PASS | Fresh crashes после cursor/после final и после commit, late pending, конкурирующие C8, пропуск M19 при cutoff20 отвергается; split-outcome/lost-intent/gap seeds |
| G7 | PASS в A | Поздний M21 не consumed A1; pause/epoch/late callback не публикуют current. Broken generation guard ловится попыткой actual old C8 publication |
| G8 | PASS в A | Same-ID receipts/conflict, claim до send/после receiver crash без blind resend, known-terminal reconciliation/resume. Broken replay даёт два наблюдённых effects вместо одного и падает именно на счётчике |
| G9 | PASS в A | Revoke, чужая receipt, forbidden C3/C8 delta, strict identity/origin и nested rights; атомарный отказ без частичного subject write |
| G10 | PASS в A | Retained raw terminal, fresh-process replay без inference, C3 tool receipt до C7 и ledger в следующем input; raw/ledger defects ловятся |
| G11 | PASS адресного вопроса | W7@1, wrong/stale/free reply не закрывает его; success не создаёт acceptance |
| G12–G15 | UNRUN в A | Полный Sleep/adaptation, live usefulness и artifact maintenance принадлежат C–D; не считаются выполненными этим кандидатом |

Исправленный пакет A: **124 PASS/242.03s**, все **22 seeded faults killed**, survived=0, invalid=0. Source/test bytes закреплены на3d4bcbc; original independent counterexamples: 2 RED старого pin → 2 GREEN нового. Адресный F2 fault падает на actual ready Work при unanswered Q2; F1 fault — на ошибочно допущенных malformed declarations через C3/C8.

Полный required repository-native gate на3d4bcbc: **PASS, 1522 passed in1518.47s**, exit0, terminal PASS. Format/lint/types,37 import contracts,hygiene/report и шесть root/core/app build artifacts прошли. Новый raw log — `evidence/f1f2/native-check.log`, provenance — `evidence/GATE-PROVENANCE.json`, build hashes — `BUILD-MANIFEST.json`. Новые traces/parity/22 controls/wheel proof — `evidence/f1f2/current/`. Первоначальный native099621b сохранён как INCOMPLETE/SUPERSEDED: exact wait oracle был исправлен перед новым freeze. Исторические95/1493 PASS source3870ac4 и original20 controls сохранены; их manifests — `evidence/f1f2/previous-manifests/`.

## Воспроизведение

Из этой рабочей копии после `uv sync --locked`:

~~~powershell
uv run --locked python -m pytest tests/restart --basetemp _scratch/restart-a-recheck -q
uv build --package zaratustra-core --wheel
uv build --package zaratustra-next --wheel
~~~

Pi checks требуют обычного установленного Pi и разрешённого loopback. Для clean-install proof `ZARA_RESTART_INSTALL_ROOT` указывает новый disposable каталог вне checkout. Для legacy полного native gate явно задаётся только его прежний SQLite 3.53.3 DLL с SHA256 `79FD9EC89DBA3F8BD64529A2CA8E9DDE6AE6EDC486C55A1D3F1CE77975A8375C`; новый core и clean proof используют native SQLite 3.50.4 без legacy bootstrap.

~~~powershell
uv run --locked python -m tools.check --deliver
~~~

Python 3.13.7; Pydantic 2.13.5; Node v22.19.0; Pi 1.0.4; wire/v1. Пакеты `zaratustra-core` и `zaratustra-next` 0.1.0. Новая команда требует явный `--data-root`; init/diagnostics не вызывают модель. Build hashes и фактический новый install-root — `evidence/f1f2/current/wheel-install.json`, source hashes — `SOURCE-MANIFEST.json`, перенос/reference-only зависимости — `REUSE-MANIFEST.json`.

Scope заканчивается A. Нет real-model/API calls, paid fallback, личных данных, daemon, изменения старой установки, merge/main или публикации. PROBA36 сохранён; v37 prototype publication pipeline здесь отсутствует, Solmax opt-in=false. Ни технические gates, ни запуск владельцем не означают его принятия результата.

END_OF_FILE: PACKAGE-A-RETURN.md

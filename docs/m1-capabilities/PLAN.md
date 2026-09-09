# T3 — семь ответов из одного разрешённого состояния

CALL c-solmax-zaratustra-m1-capabilities-20260909-exec; PROBA / pin36.
Basis a5efbb15c7c39e52072f4fb1593a294ebe109a80. Execution branch
codex/m1-capabilities-20260909, новая одноимённая копия под product _scratch.
Source чист, STOP/STEER отсутствуют, pin/stamp36 совпали. Право запуска: RUN CALL.

## W16: техническое решение до реализации

Один read_capabilities возвращает семь именованных ответов и общий envelope.
PackRegistration получает необязательный read adapter: прежний lifecycle
сохраняется; отсутствие адаптера явно unavailable, никогда мнимые пустые ответы.
Adapter получает immutable разрешённые Process/Work и заголовки Results; без
workspace path, DB, authority, содержимого чужих артефактов и owner-local history.
Он выбирает производные ответы; Core проверяет state, права, ссылки и согласованность.

Core ProcessQuery — отдельный exact metadata запрос, а не расширение ContextQuery:
workspace/process, anchor Work, expected_revision, явный набор visible_work_ids,
optional selected_work_id, max_bytes. Разрешение — существующий trusted local
канал и digest типа/пути/всего запроса. Anchor и каждая указанная Work должны иметь
текущие metadata rights; terminal Work допускает только metadata, не исполнение.
Пустой набор законен. Права на одну Work не расширяются до всех Works Process.
Один чужой/отозванный член отвергает весь запрос; нельзя угадывать скрытые counts.

| Ответ | Значение |
|---|---|
| current_status | Краткое pack-derived состояние только раскрытой области; не утверждение о скрытых Works. |
| items_needing_attention | Производные уведомления со stable pack-local id, ссылкой на раскрытую Work и её revision. |
| open_decisions | Нерешённые вопросы, выводимые adapter из текущих metadata; не новое хранилище решений и не уже принятые Handoff. Пусто только если adapter явно вернул пустой набор. |
| available_works | Выбранные adapter готовые Works с текущими правами; обещание пригодности по правилам pack, не разрешение выполнить mutation. |
| blocked_works | Остальные незавершённые раскрытые Works с причиной. При поддержке обоих списков они дают точное непересекающееся разбиение; terminal Works в них нет. |
| recent_important_results | Выбранные adapter заголовки сохранённых Results раскрытых Works, по убыванию revision. Importance — правило pack, не Core. Без содержимого, grounds и чужой next Work. |
| context_requirements | Требования выбранной Work: executor requirements + pack notes + exact ArtifactReference. Они не выдают прав. Без выбранной Work — unavailable/not_requested. |

Каждый ответ: ok/empty/denied/unavailable. empty — поддержанный пустой список;
denied — нет действующего разрешения; unavailable — нет точного pack/адаптера,
ответ не поддержан, stale revision, недоступно основание или превышен byte budget.
У denied/unavailable нет value/count; ошибка не содержит DB detail или скрытых ids.
Counts считаются только по реально возвращённым спискам. Envelope явно перечисляет
scope и единый state_revision (это разрешённый глобальный revision, не count);
binding точный по W15. Сохранённый ответ — исторический, после изменений перечитать.

Контекст материализуется только при отдельном ContextQuery + точном caller на
selected Work, тот же process/revision. Её references должны совпасть с требованиями
pack. Используется существующий open_work compiler/полная проверка closure,
без нового чтения по текстовым ссылкам. Requirements остаются видны при unavailable
содержимом; вложенное context состояние отличает not_requested/denied/unavailable/ok.
Предварительный запрос требований позволяет подготовить exact ContextQuery.

Одна единица согласованности — один ProcessQuery в одной workspace. Core читает
metadata/history и optional context под существующим writer lock; повторно сверяет
весь input после callback до возврата. Pack не получает mutable state. Контракт
не обещает общей транзакции между workspace. Общий обзор T6 обязан учитывать это;
выбор размещения нескольких Process остаётся W17/T4–T5, не закрыт этим решением.

## Проверки, сохранность и предел

До edits: штатный tools.check PASS, 173 tests; tools.probe_packs создал новую
_scratch/t3-baseline-packs и проверил восстановление legacy/bind/result. Wheel0.8.0
и полный trial сохраняются в evidence вместе с исходным raw, SHA256/layout.
До BUILD коммитятся этот PLAN, CALL и retained baseline.

Новые tests проверяют ненаблюдаемые свойства через Core: exact metadata scope,
смену прав, stale query, pack/adapter absence, reference membership, coherent
partition, hidden metadata/counts, selected context и foreign reference, отказ
при недоступных bytes, блокировку concurrent managed writer, budget и отсутствие
записей при чтении/отказе. Native tools.check --deliver остаётся обязательным.
Runnable tools.probe_capabilities сохраняет exact query/authority/answers,
state/history, mutations и backups; restore_snapshot — только в новую папку.
Прямые SQL/state edits и потеря evidence ради PASS запрещены.

W15: T2 exact binding/versions/lifecycle сохраняется. Read adapter — явная часть
той же trusted registration, без latest/rebind/code attestation.
W16: выбранное решение выше реализуется и проверяется в T3.
W17: общая additive read-подготовка до двух полных Process; обе гарантии P§30
«без изменения основной семантики Core» и P§40 «без изменения Core» сохранены.
Baseline перед вторым и multi-Process placement OPEN T4/T5, Proof C не заявляется.
W18: только fictional contract fixtures T3; полная пара/правила OPEN T4/T5.
W19: renderer общего обзора OPEN T6, API JSON не новый frontend/transport.
W20: exact T3 evidence/rollback; полные сценарии и итоговое сравнение OPEN T4–T7.
Исходные rewrites W15–W20 сохранены в CALL; новых cuts нет.

Сверка принятого плана §§8/30/40, shape T3 и C03/C04/C05: conforms under
owner-ack:solmax-plan-conforming-20260907. Источник точных слов и предел делегации:
Direction knowledge/zaratustra-plan-conforming-approval-2026-09-07.md.
Нового owner concept/прав/бюджета/гарантии нет. Foundation redesign или изменение
этого основания возвращается HOME; это не разрешение менять acceptance.
M0 partial; T4 не запускается. REPORT возвращает RESULT.md, next: solmax.
Owner acceptance T3 и binding fresh physical G5 pending, не заменяются тестами.

END_OF_FILE: docs/m1-capabilities/PLAN.md

# Actual synthetic conversations and process restarts

These are actual model prompts and responses, not scripted mutations. Each row is a
new Node/Pi in-memory session with empty transcript and a different cwd; the same
declared synthetic home carries the durable records between relevant rows. RPC is
the explicitly trusted test controller, not the owner. Source files are synthetic.
Medium thinking; openai-codex/gpt-6.1-sol. No reasoning blocks are published.

Attempts 01–03: d3dc6c3; 04–05: fe8271d; completed qualification 06–19: fixed
55fac403fd4aba2f6e6ccb81d4e569ec5c0fde33; 20: corrected 334c572, budget-aborted.
See [qualification boundary](C-VALIDATION.md). All amounts below are Pi estimates.

| Attempt                                                                           | PID    | Provider requests | USD        | Tool errors |
| --------------------------------------------------------------------------------- | ------ | ----------------- | ---------- | ----------- |
| [01-upgrade](c-evidence/live/01-upgrade/events.jsonl)                             | 109180 | 9                 | 0.10651880 | 0           |
| [02-plan](c-evidence/live/02-plan/events.jsonl)                                   | 104628 | 9                 | 0.14410880 | 2           |
| [03-partial-handoff](c-evidence/live/03-partial-handoff/events.jsonl)             | 98188  | 8                 | 0.14406360 | 0           |
| [04-frozen-plan](c-evidence/live/04-frozen-plan/events.jsonl)                     | 104216 | 13                | 0.24536360 | 0           |
| [05-partial-reply](c-evidence/live/05-partial-reply/events.jsonl)                 | 106916 | 7                 | 0.11586960 | 0           |
| [06-qualified-plan](c-evidence/live/06-qualified-plan/events.jsonl)               | 125276 | 11                | 0.22172040 | 0           |
| [07-qualified-partial](c-evidence/live/07-qualified-partial/events.jsonl)         | 98836  | 4                 | 0.06870280 | 0           |
| [08-pause-goal](c-evidence/live/08-pause-goal/events.jsonl)                       | 92956  | 5                 | 0.10432240 | 1           |
| [09-late-paused](c-evidence/live/09-late-paused/events.jsonl)                     | 43144  | 5                 | 0.11471720 | 0           |
| [10-explicit-resume](c-evidence/live/10-explicit-resume/events.jsonl)             | 33340  | 6                 | 0.16514200 | 2           |
| [11-cancel-late](c-evidence/live/11-cancel-late/events.jsonl)                     | 111468 | 5                 | 0.11004240 | 0           |
| [12-complete](c-evidence/live/12-complete/events.jsonl)                           | 125516 | 9                 | 0.20486120 | 0           |
| [13-reopen](c-evidence/live/13-reopen/events.jsonl)                               | 72656  | 4                 | 0.07123680 | 0           |
| [14-retain-books](c-evidence/live/14-retain-books/events.jsonl)                   | 35784  | 6                 | 0.06984200 | 0           |
| [15-read-books](c-evidence/live/15-read-books/events.jsonl)                       | 70532  | 6                 | 0.07977600 | 0           |
| [16-ambiguous-prepare](c-evidence/live/16-ambiguous-prepare/events.jsonl)         | 41364  | 9                 | 0.13532880 | 0           |
| [17-ambiguous-return](c-evidence/live/17-ambiguous-return/events.jsonl)           | 59420  | 3                 | 0.03984520 | 0           |
| [18-clarified-return](c-evidence/live/18-clarified-return/events.jsonl)           | 22792  | 7                 | 0.13039560 | 1           |
| [19-reconcile-preparation](c-evidence/live/19-reconcile-preparation/events.jsonl) | 125120 | 12                | 0.25930960 | 0           |
| [20-image-only](c-evidence/live/20-image-only/events.jsonl)                       | 60944  | 2                 | 0.02352160 | 0           |

The first exhibition story creates two children; one finishes while another waits.
Attempt 07 is a later process receiving only the partial reply, with no old transcript.
08–11 change the goal, pause, receive late content, explicitly resume and cancel.
12 completes a new Work from evidence and mandatory children; 13 reopens the same ID.
14 retains books in a real upgraded predecessor home; after deleting source copies,
15 answers from managed reads. EPUB chapter 2 starts at global code point 12615;
Markdown answer is past 10000. The answer is absent from prompt/snapshot/card and first
appears in real zara_read outputs, as checked by verification-final.json.
16–19 expose and resolve ambiguity/preparation drift through normal conversation.

## 01-upgrade

Public candidate `d3dc6c38b02ba6e91c1037bdf1ed074b9be3c3b3`; PID 109180; empty starting transcript.

**Controller request (Russian, actual):**

> Продолжим старую работу с материалом. Что сохранено и чего ещё не хватает? Ничего пока не меняй. Ответь по-русски.

**Actual assistant response:**

> Сохранено:
>
> - Исходный запрос: «Создай работу; часть материалов пришлю позже».
> - Полученная часть материала — оригинальный Markdown-файл; его сохранённый текст доступен.
> - Работа с целью прочитать оставшийся материал и подготовить обоснованный разбор.
>
> **Чего не хватает:** остальной части материала. Работа находится в состоянии ожидания; завершение и итоговый разбор не зафиксированы.
>
> Ничего не менял. Сохранность проверил, но весь материал сейчас не перечитывал.

[Actual events](c-evidence/live/01-upgrade/events.jsonl), [database/usage readback](c-evidence/live/01-upgrade/summary.json).

## 02-plan

Public candidate `d3dc6c38b02ba6e91c1037bdf1ed074b9be3c3b3`; PID 104628; empty starting transcript.

**Controller request (Russian, actual):**

> Начнём небольшой проект «Лесная выставка». Итог — короткая заметка из обзора экспонатов и приглашения. Сделай обзор отдельной обязательной подзадачей: материал пришлю двумя частями. Независимая подзадача — приглашение в два предложения: выставка в субботу в 15:00, вход свободный. Подготовь и сохрани приглашение уже сейчас, пока обзор ждёт материал. Итоговую заметку пока не закрывай; продолжим после получения обеих частей. Общаемся по-русски.

**Actual assistant response:**

> Проект «Лесная выставка» создан. Обзор — отдельная обязательная подзадача, ожидающая две части материала. Итоговая заметка остаётся незавершённой.
>
> **Приглашение подготовлено и сохранено:**
>
> Приглашаем вас на «Лесную выставку» в субботу в 15:00. Вход свободный!
>
> Присылайте первую часть материала.

**Actual rejected tools before subsequent repair:**

- `INVALID_TRANSITION`: Waiting Work needs an addressed pending wait.
- `INVALID_TRANSITION`: Transition must change Work state.

[Actual events](c-evidence/live/02-plan/events.jsonl), [database/usage readback](c-evidence/live/02-plan/summary.json).

## 03-partial-handoff

Public candidate `d3dc6c38b02ba6e91c1037bdf1ed074b9be3c3b3`; PID 98188; empty starting transcript.

**Controller request (Russian, actual):**

> Пришла первая часть для «Лесной выставки»: «На стенде представлены три учебных образца: сосновая шишка, берёзовый лист и кусочек коры. Их собрали с земли, живые растения не повреждали». Вторая часть ещё не готова. Сохрани этот фрагмент, не считай весь материал полученным. Подготовь сообщение для ручного переноса в другой чат: попроси проверить ясность описания этих трёх образцов и отдельно предложить заголовок. Сам ничего не отправляй. Ответ может прийти частями; пока продолжай хранить ожидание второй части материала.

**Actual assistant response:**

> Первый фрагмент сохранён. Вторая часть остаётся в ожидании; весь материал не считаю полученным. Ничего не отправлял.
>
> **Сообщение для ручного переноса:**
>
> > Проверь, пожалуйста, ясность первой части материала для «Лесной выставки»:
> >
> > «На стенде представлены три учебных образца: сосновая шишка, берёзовый лист и кусочек коры. Их собрали с земли, живые растения не повреждали».
> >
> > 1. Понятно ли описание всех трёх образцов? Если нужны правки, предложи их без добавления новых фактов.
> > 2. Отдельно предложи заголовок для этого фрагмента.
> >
> > Вторая часть ещё не готова — не составляй полный материал и не додумывай продолжение. Можно ответить частями: отдельно по ясности и отдельно по заголовку.
>
> Ответы будем учитывать отдельно, сохраняя ожидание второй части.
>
> Ссылка для сопоставления ответа: `handoff-ac549ce1-1a76-47b2-bf05-f30912ef7aad`.

[Actual events](c-evidence/live/03-partial-handoff/events.jsonl), [database/usage readback](c-evidence/live/03-partial-handoff/summary.json).

## 04-frozen-plan

Public candidate `fe8271d41228dc67cdcd12fc1e9d8a04ac36c40b`; PID 104216; empty starting transcript.

**Controller request (Russian, actual):**

> Создай проект «Лесная выставка»: итоговая заметка должна объединить обзор экспонатов и короткое приглашение. Обзор сделай отдельной обязательной подзадачей: материал поступает двумя частями. Первая часть уже есть: «На стенде представлены сосновая шишка, берёзовый лист и кусочек коры. Их собрали с земли, живые растения не повреждали». Вторую часть пришлю позже. Независимая подзадача — приглашение из двух предложений: выставка в субботу в 15:00, вход свободный. Его подготовь и сохрани сейчас, пока обзор ждёт продолжение. Ещё подготовь минимальное сообщение для ручного переноса в другой чат: проверить ясность первой части и отдельно предложить заголовок. Сам ничего не отправляй. Всю итоговую работу пока не закрывай. Общаемся по-русски.

**Actual assistant response:**

> Проект «Лесная выставка» создан и оставлен открытым. Первая часть сохранена; обязательная подзадача обзора ждёт вторую часть.
>
> **Приглашение подготовлено и сохранено:**
>
> > Приглашаем на «Лесную выставку» в субботу в 15:00. Вход свободный.
>
> **Сообщение для ручного переноса:**
>
> > Проверь ясность первой части текста: «На стенде представлены сосновая шишка, берёзовый лист и кусочек коры. Их собрали с земли, живые растения не повреждали». Ответь двумя пунктами: 1) оценка ясности; 2) отдельно — предлагаемый заголовок. Второй части пока нет, ничего не додумывай.
>
> Ссылка для сопоставления ответа: `handoff-d5a06bc2-5d96-4435-a6c8-9a0fb28596fe`.
>
> Ничего в другой чат не отправлял.

[Actual events](c-evidence/live/04-frozen-plan/events.jsonl), [database/usage readback](c-evidence/live/04-frozen-plan/summary.json).

## 05-partial-reply

Public candidate `fe8271d41228dc67cdcd12fc1e9d8a04ac36c40b`; PID 106916; empty starting transcript.

**Controller request (Russian, actual):**

> Из другого чата пришла только первая часть ответа по «Лесной выставке»: «Описание трёх образцов понятно. Лучше оставить короткую фразу, что образцы собраны с земли, чтобы не возникало впечатления, что растения повредили». Заголовок там ещё не предложили. Сохрани полезное замечание как внешний ответ, но не считай всё задание тому чату выполненным. Вторую часть исходного материала я также пока не прислал. Что теперь готово и что ещё ждём?

**Actual assistant response:**

> Сохранил замечание как **частичный внешний ответ**: описание трёх образцов понятно; короткую фразу «собраны с земли» следует оставить, чтобы не создавалось впечатления повреждения растений.
>
> **Уже готово:**
>
> - сохранена первая часть материала;
> - сохранено замечание из другого чата;
> - подготовлено и сохранено приглашение из двух предложений.
>
> **Ещё ждём:**
>
> - предложенный заголовок из другого чата — его задание не закрыто;
> - вторую часть исходного материала от вас.
>
> Полный обзор и итоговая заметка пока не готовы; общее задание остаётся открытым.

[Actual events](c-evidence/live/05-partial-reply/events.jsonl), [database/usage readback](c-evidence/live/05-partial-reply/summary.json).

## 06-qualified-plan

Public candidate `55fac403fd4aba2f6e6ccb81d4e569ec5c0fde33`; PID 125276; empty starting transcript.

**Controller request (Russian, actual):**

> Создай проект «Лесная выставка»: итоговая заметка должна объединить обзор экспонатов и короткое приглашение. Обзор сделай отдельной обязательной подзадачей: материал поступает двумя частями. Первая часть уже есть: «На стенде представлены сосновая шишка, берёзовый лист и кусочек коры. Их собрали с земли, живые растения не повреждали». Вторую часть пришлю позже. Независимая подзадача — приглашение из двух предложений: выставка в субботу в 15:00, вход свободный. Его подготовь и сохрани сейчас, пока обзор ждёт продолжение. Ещё подготовь минимальное сообщение для ручного переноса в другой чат: проверить ясность первой части и отдельно предложить заголовок. Сам ничего не отправляй. Всю итоговую работу пока не закрывай. Общаемся по-русски.

**Actual assistant response:**

> Проект «Лесная выставка» создан и сохранён. Обзор — отдельная обязательная подзадача: первая часть сохранена, ждём вторую. Итоговая работа остаётся открытой.
>
> **Приглашение подготовлено и сохранено:**
>
> > Приглашаем на выставку «Лесная выставка» в субботу в 15:00. Вход свободный.
>
> **Сообщение для ручного переноса:**
>
> > Проверь ясность первой части для проекта «Лесная выставка»: «На стенде представлены сосновая шишка, берёзовый лист и кусочек коры. Их собрали с земли, живые растения не повреждали». Ответь отдельно: 1) оценка ясности; 2) предложенный заголовок. Вторую часть не придумывай.
>
> Ссылка для сопоставления ответа: `handoff-69714c87-2af5-44fc-b640-b84709b2f938`.
>
> Ничего в другой чат не отправлял.

[Actual events](c-evidence/live/06-qualified-plan/events.jsonl), [database/usage readback](c-evidence/live/06-qualified-plan/summary.json).

## 07-qualified-partial

Public candidate `55fac403fd4aba2f6e6ccb81d4e569ec5c0fde33`; PID 98836; empty starting transcript.

**Controller request (Russian, actual):**

> Из другого чата пришла только первая часть ответа по «Лесной выставке»: «Описание трёх образцов понятно. Лучше оставить короткую фразу, что образцы собраны с земли, чтобы не возникало впечатления, что растения повредили». Заголовок там ещё не предложили. Сохрани полезное замечание как внешний ответ, но не считай всё задание тому чату выполненным. Вторую часть исходного материала я также пока не прислал. Что теперь готово и что ещё ждём?

**Actual assistant response:**

> Сохранил замечание как **частичный внешний ответ**, не как выполнение всего задания другому чату.
>
> **Готово:**
>
> - Проверка ясности: описание трёх образцов понятно.
> - Сохранена рекомендация оставить фразу «образцы собраны с земли», чтобы не создавать впечатления повреждения растений.
> - Отдельное приглашение из двух предложений уже готово и сохранено.
>
> **Ещё ждём:**
>
> - Предложенный заголовок от другого чата.
> - Вторую часть исходного материала от вас.
>
> Обзор и итоговая заметка пока не завершены; общее задание остаётся открытым.

[Actual events](c-evidence/live/07-qualified-partial/events.jsonl), [database/usage readback](c-evidence/live/07-qualified-partial/summary.json).

## 08-pause-goal

Public candidate `55fac403fd4aba2f6e6ccb81d4e569ec5c0fde33`; PID 92956; empty starting transcript.

**Controller request (Russian, actual):**

> Приостановим весь проект «Лесная выставка». Конечная цель меняется: теперь нужна только нейтральная учебная карточка об образцах, без приглашения на событие. Уже готовое приглашение сохрани как историю. Фактические состояния подзадач не переписывай из-за паузы: обзор пока ждёт продолжение. Ничего по проекту автоматически не продолжай.

**Actual assistant response:**

> Сохранено: весь проект «Лесная выставка» приостановлен.
>
> - Новая цель — только нейтральная учебная карточка об образцах, без приглашения.
> - Готовое приглашение сохранено как история.
> - Состояния подзадач не изменены: обзор по-прежнему ждёт продолжение.
>
> Без вашей явной команды ничего по проекту не продолжу.

**Actual rejected tools before subsequent repair:**

- `INVALID_TRANSITION`: Use a new Work for a new goal or explicitly reopen before revising a terminal plan.

[Actual events](c-evidence/live/08-pause-goal/events.jsonl), [database/usage readback](c-evidence/live/08-pause-goal/summary.json).

## 09-late-paused

Public candidate `55fac403fd4aba2f6e6ccb81d4e569ec5c0fde33`; PID 43144; empty starting transcript.

**Controller request (Russian, actual):**

> Пришёл запоздалый ответ из того чата по старому заданию: «Предлагаю заголовок: Лесные находки без вреда природе. В приглашении можно сохранить время 15:00». Сохрани полезное содержание, сравни его с новой учебной целью. Пауза остаётся в силе: ничего не возобновляй и не возвращай старую цель с приглашением.

**Actual assistant response:**

> Сохранил ответ как запоздалый.
>
> - «Лесные находки без вреда природе» — подходящий вариант заголовка для новой учебной карточки, пока не окончательный.
> - Упоминание 15:00 относится к старому приглашению и в карточку не включается.
>
> Пауза сохранена: ничего не возобновлял, старую цель не возвращал.

[Actual events](c-evidence/live/09-late-paused/events.jsonl), [database/usage readback](c-evidence/live/09-late-paused/summary.json).

## 10-explicit-resume

Public candidate `55fac403fd4aba2f6e6ccb81d4e569ec5c0fde33`; PID 33340; empty starting transcript.

**Controller request (Russian, actual):**

> Теперь явно возобнови родительский проект «Лесная выставка» с новой целью учебной карточки, без приглашения. Проверь текущие условия. Обзор не считай готовым: вторую часть материала я ещё не прислал. Объясни ближайший доступный шаг.

**Actual assistant response:**

> Родительский проект «Лесная выставка» возобновлён; изменение сохранено. Цель — нейтральная учебная карточка об образцах, **без приглашения**.
>
> Проверены текущие условия:
>
> - обзор не завершён: вторая часть материала отсутствует;
> - первая часть и замечания сохранены;
> - прежнее приглашение остаётся только в истории, повторно делать его не нужно.
>
> **Ближайший шаг — прислать вторую часть материала.** После этого можно завершить обзор и на его основе подготовить карточку, сохранив указание о сборе без вреда природе. Повторно возобновлять проект не потребуется.

**Actual rejected tools before subsequent repair:**

- `INVALID_TRANSITION`: Waiting Work needs an addressed pending wait.
- `INVALID_TRANSITION`: An independent step is available; the whole Work cannot be waiting.

[Actual events](c-evidence/live/10-explicit-resume/events.jsonl), [database/usage readback](c-evidence/live/10-explicit-resume/summary.json).

## 11-cancel-late

Public candidate `55fac403fd4aba2f6e6ccb81d4e569ec5c0fde33`; PID 111468; empty starting transcript.

**Controller request (Russian, actual):**

> Отмени прежний проект «Лесная выставка» целиком: карточку больше не готовим, второй части материала не будет. Сохрани причину и объясни последствия для незавершённого обзора. Ещё пришёл дополнительный запоздалый комментарий из того же чата: «Для будущего учебного текста полезно подчеркнуть различие наблюдения и вывода». Сохрани полезную мысль как внешний материал, но отменённый план не восстанавливай.

**Actual assistant response:**

> Проект «Лесная выставка» отменён целиком. Причина сохранена: карточку больше не готовим, второй части материала не будет.
>
> Незавершённый обзор отменён, а не отмечен выполненным; ожидание второй части снято. Ранее сохранённые материалы остаются в истории.
>
> Запоздалый комментарий о различии наблюдения и вывода сохранён как внешний материал для возможного будущего текста. Отменённый план не восстановлен.

[Actual events](c-evidence/live/11-cancel-late/events.jsonl), [database/usage readback](c-evidence/live/11-cancel-late/summary.json).

## 12-complete

Public candidate `55fac403fd4aba2f6e6ccb81d4e569ec5c0fde33`; PID 125516; empty starting transcript.

**Controller request (Russian, actual):**

> Создай новую независимую работу «Правило наблюдения»; отменённую выставку не восстанавливай. Нужен небольшой текст из трёх предложений для учебной памятки. Основа: наблюдение описывает непосредственно замеченное; вывод предлагает объяснение; если подтверждений недостаточно, объяснение остаётся предположением. Критерии: ровно три предложения, оба понятия различены, ограничение про недостаточные подтверждения сохранено. Подготовь и сохрани текст. Если все критерии фактически выполнены, обоснованно заверши эту новую работу. Оформи различение понятий и проверку ограничения как две отдельные обязательные подзадачи. Родительскую работу заверши только когда готовы обе подзадачи и итоговый текст.

**Actual assistant response:**

> **Правило наблюдения**
>
> Наблюдение описывает то, что непосредственно замечено. Вывод предлагает объяснение наблюдаемого. Если подтверждений недостаточно, это объяснение остаётся предположением.
>
> Текст сохранён. Обе обязательные подзадачи завершены отдельно; затем завершена родительская работа: все три критерия выполнены. Отменённая выставка не восстановлена.

[Actual events](c-evidence/live/12-complete/events.jsonl), [database/usage readback](c-evidence/live/12-complete/summary.json).

## 13-reopen

Public candidate `55fac403fd4aba2f6e6ccb81d4e569ec5c0fde33`; PID 72656; empty starting transcript.

**Controller request (Russian, actual):**

> Вернём именно завершённую работу «Правило наблюдения» в работу, чтобы я позже уточнил формулировку. Старое завершение и прежний текст должны остаться в истории. Пока новую версию не пиши и повторно работу не закрывай. Покажи прежний сохранённый вариант и текущий статус.

**Actual assistant response:**

> «Правило наблюдения» возвращено в работу. **Текущий статус: активна**, ожидает вашего уточнения формулировки.
>
> Прежний сохранённый вариант:
>
> > Наблюдение описывает то, что непосредственно замечено. Вывод предлагает объяснение наблюдаемого. Если подтверждений недостаточно, это объяснение остаётся предположением.
>
> Старое завершение и прежний текст сохранены в истории. Новую версию не писал, повторно работу не закрывал.

[Actual events](c-evidence/live/13-reopen/events.jsonl), [database/usage readback](c-evidence/live/13-reopen/summary.json).

## 14-retain-books

Public candidate `55fac403fd4aba2f6e6ccb81d4e569ec5c0fde33`; PID 35784; empty starting transcript.

**Controller request (Russian, actual):**

> Сохрани две синтетические книги в библиотеке: PDF по пути <C_EVIDENCE_ROOT>\live-inputs\field-notebook.pdf и EPUB по пути <C_EVIDENCE_ROOT>\live-inputs\field-manual.epub. Это самостоятельные материалы: существующую ожидающую работу не меняй и новую задачу ради хранения не создавай. Пока содержание книг не читай и не пересказывай; я задам вопрос позднее. Также сохрани Markdown-заметку из последнего набора по пути <C_EVIDENCE_ROOT>\live-inputs\field-notes.md с теми же условиями: отдельный материал, без новой работы и без чтения содержания сейчас.

**Actual assistant response:**

> Сохранены три отдельных материала: `field-notebook.pdf`, `field-manual.epub` и `field-notes.md`.
>
> Оригиналы и автоматически извлечённые тексты доступны для будущих вопросов. Содержание не читал и не пересказывал. Существующую ожидающую работу не менял, новых задач не создавал.

[Actual events](c-evidence/live/14-retain-books/events.jsonl), [database/usage readback](c-evidence/live/14-retain-books/summary.json).

## 15-read-books

Public candidate `55fac403fd4aba2f6e6ccb81d4e569ec5c0fde33`; PID 70532; empty starting transcript.

**Controller request (Russian, actual):**

> По сохранённым книгам ответь по-русски: куда по PDF нужно оставить призму, а где по EPUB хранится маяк и какая там проверочная фраза? Исходных файлов больше нет; используй сохранённые материалы. Укажи страницы и главу, откуда взяты ответы. Ещё скажи, какое указание записано в самом хвосте Markdown-заметки из последнего сохранённого набора.

**Actual assistant response:**

> По сохранённым текстам:
>
> - **PDF `field-notebook.pdf`, стр. 2:** призму нужно оставить **в шкафу цвета индиго, в ящике L-42**. На **стр. 3** указан проверочный код: **QUARTZ-6815**.
> - **EPUB `field-manual.epub`, глава 2** (`OPS/two.xhtml`): маяк хранится **в медном алькове, в нише M-73**. Проверочная фраза: **LICHEN-2948**.
> - **Самый хвост Markdown `field-notes.md`:** «Tail: archive drawer R-17» — **архивный ящик R-17**.
>
> Использованы сохранённые извлечённые тексты, исходные файлы не требовались.

[Actual events](c-evidence/live/15-read-books/events.jsonl), [database/usage readback](c-evidence/live/15-read-books/summary.json).

## 16-ambiguous-prepare

Public candidate `55fac403fd4aba2f6e6ccb81d4e569ec5c0fde33`; PID 41364; empty starting transcript.

**Controller request (Russian, actual):**

> Есть две отдельные работы: карточка «Север» и карточка «Юг». Для каждой нужна внешняя проверка одной и той же заготовки: «Записывай наблюдение отдельно от объяснения». Сохрани две отдельные работы и подготовь по отдельному сообщению для ручного переноса в другие чаты. Проверяющий должен сказать, понятна ли формулировка, и предложить правку. Пока только подготовь запросы, сам ничего не отправляй.

**Actual assistant response:**

> Сохранены две отдельные работы и два запроса. Ничего не отправлено.
>
> ### «Север»
>
> > Карточка «Север». Проверь формулировку: «Записывай наблюдение отдельно от объяснения».
> >
> > 1. Понятна ли она? Кратко объясни, как ты её понимаешь и есть ли неоднозначность.
> > 2. Предложи отредактированный вариант.
> >    В ответе сохрани пометку «Север».
>
> Ссылка запроса: `handoff-4a176448-9375-4bb3-8b22-f4e0cdb24ab6`
>
> ### «Юг»
>
> > Карточка «Юг». Проверь формулировку: «Записывай наблюдение отдельно от объяснения».
> >
> > 1. Понятна ли она? Кратко объясни, как ты её понимаешь и есть ли неоднозначность.
> > 2. Предложи отредактированный вариант.
> >    В ответе сохрани пометку «Юг».
>
> Ссылка запроса: `handoff-71d4646a-26aa-4976-b8ef-fb9db0e87510`
>
> Ответы можно принести сюда с пометкой соответствующей карточки.

[Actual events](c-evidence/live/16-ambiguous-prepare/events.jsonl), [database/usage readback](c-evidence/live/16-ambiguous-prepare/summary.json).

## 17-ambiguous-return

Public candidate `55fac403fd4aba2f6e6ccb81d4e569ec5c0fde33`; PID 59420; empty starting transcript.

**Controller request (Russian, actual):**

> Вернулся ответ из другого чата: «Формулировка понятна, правки не нужны». Сохрани его к нужной работе.

**Actual assistant response:**

> Этот ответ относится к карточке «Север» или «Юг»? Для обеих подготовлен одинаковый запрос, а в ответе нет пометки. Пока не привязываю его, чтобы не сохранить к неверной работе.

[Actual events](c-evidence/live/17-ambiguous-return/events.jsonl), [database/usage readback](c-evidence/live/17-ambiguous-return/summary.json).

## 18-clarified-return

Public candidate `55fac403fd4aba2f6e6ccb81d4e569ec5c0fde33`; PID 22792; empty starting transcript.

**Controller request (Russian, actual):**

> Этот ответ относился к карточке «Север». Повторю его для точности: «Формулировка понятна, правки не нужны». Это уточнение уже присланного ответа, а не новая независимая проверка. Сохрани его для «Севера»; работу по «Югу» оставь ждать своего отдельного ответа.

**Actual assistant response:**

> Сохранил для «Севера»: «Формулировка понятна, правки не нужны» — как уточнение прежнего ответа, не новую независимую проверку. «Юг» по-прежнему ждёт своего отдельного ответа.

**Actual rejected tools before subsequent repair:**

- `INVALID_TRANSITION`: An independent step is available; the whole Work cannot be waiting.

[Actual events](c-evidence/live/18-clarified-return/events.jsonl), [database/usage readback](c-evidence/live/18-clarified-return/summary.json).

## 19-reconcile-preparation

Public candidate `55fac403fd4aba2f6e6ccb81d4e569ec5c0fde33`; PID 125120; empty starting transcript.

**Controller request (Russian, actual):**

> Оба сообщения для «Севера» и «Юга» уже подготовлены и сохранены. Сверь план с этими сохранёнными сообщениями: подготовка для обеих карточек закончена. Приведи состояние плана в соответствие с фактом, не создавая повторных запросов и ничего не отправляя. Полного внешнего разбора для «Севера» ещё нет, для «Юга» ответа совсем нет. Обе работы должны ждать соответствующего продолжения, а не начинать подготовку заново.

**Actual assistant response:**

> План сверён и сохранён:
>
> - Подготовка для обеих карточек завершена.
> - «Север» ждёт недостающей части разбора; частичный ответ сохранён.
> - «Юг» ждёт отдельного ответа, которого пока нет.
>
> Повторных запросов не создавал, ничего не отправлял.

[Actual events](c-evidence/live/19-reconcile-preparation/events.jsonl), [database/usage readback](c-evidence/live/19-reconcile-preparation/summary.json).

## 20-image-only

Public candidate `334c572691df179cbf37d9a6582e69effc8a4aed`; PID 60944; empty starting transcript.

**Controller request (Russian, actual):**

> Сохрани для дальнейшего чтения EPUB по пути <C_EVIDENCE_ROOT>\image-only-fixture\image-only.epub. Проверь, доступен ли в нём текст. Если читать нечего, честно скажи об этом. Новую работу пока не создавай.

**Actual assistant response:**

No response. Two requests used on skill/navigation; the third payload was blocked
before sending at request 140. No import or record mutation. UNVERIFIED.

[Actual events](c-evidence/live/20-image-only/events.jsonl), [database/usage readback](c-evidence/live/20-image-only/summary.json).

END_OF_FILE: docs/C-CONVERSATIONS.md

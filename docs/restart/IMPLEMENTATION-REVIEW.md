# Проверка реализации пакета A

Это инженерный pre-pass по закреплённому source, не binding Direction G5 и не принятие владельцем.

## Первый кандидат: 4136136133376a41606364aaf24abf3f86381e6b — NOT READY

Свежий read-only проверяющий воспроизвёл три Important семейства через публичный API в отдельных fictional roots:

1. Коррелированные tool writes допускались до claim и после finished Attempt; не проверялся исполнитель claim.
2. C3 tool effect не повторял проверку закреплённых must_be_current входов/Method/profile; поздний отказ C8 оставлял уже применённую устаревшую правку.
3. `apply_changes.initial_work` обходил отдельное право `open_work`; nested C8 changes обходили `apply_changes`.

Первый общий native-прогон намеренно остановлен как superseded/incomplete на этом отклонённом source. Его лог — `evidence/native-check-4136136-superseded.log`; это не PASS и не предметный FAIL финального кандидата.

## Исправленный source: 3870ac4ac1f6af1aa818c70c83e999a0f68646b1 — READY в области pre-pass

Исполнитель добавил общий текущий admission коррелированных tools, проверку claim/executor/статуса, общий pinned-basis evaluator для C3/C6/C8 и отдельную проверку каждого вложенного права. Старые успешно сохранённые receipts по-прежнему возвращаются до нового admission; новый callback не получает права старой Attempt.

Свежий проверяющий независимо повторил public API воспроизведения: preclaim, finished, чужой executor, memory/Method/profile stale bases, атомарные nested-rights отказы и стабильный exact receipt replay. Восемь focused tests прошли с явным basetemp. Fictional reproduction root: `_scratch/fresh-review/corrected-c7cc41f5-0786-423f-933a-f6a448897fea`. Новых блокирующих findings в рассмотренной области не выявлено. Pi и полный gate проверяющий самостоятельно не перезапускал.

Ведущий дополнительно проверил G1 guard до обоих product imports и copied outside-checkout fixture; G2 сравнение доменных таблиц и реальных callback refusal; G8 killed variant с двумя наблюдёнными эффектами вместо одного; все 37 source hashes из SOURCE-MANIFEST совпадают с Git blobs и working bytes, mismatches=0.

Scope этой проверки ограничен названными гарантиями. Полные фактические gates и build hashes записываются отдельно в `evidence/GATE-PROVENANCE.json` и `PACKAGE-A-RETURN.md`. Решение владельца о реализации отсутствует.

Ведущий независимо выполнил ещё три адресных шва на source3870ac4: cancel+late C7/C8 fencing; known-running reconciliation→resume→terminal без второго receiver effect; внешний fixture-only epoch advance, отвергающий старые envelope/C7/C8. Это не production restore API и не binding G5. Исходные байты воспроизводителя и отчёта удержаны в `evidence/root-gate-seams.py.txt` и `evidence/root-gate-seams-report.json` без редактирования.

Воспроизведение retained root seams из этой рабочей копии:

~~~powershell
.venv/Scripts/python.exe -c "from pathlib import Path; exec(compile(Path('docs/restart/evidence/root-gate-seams.py.txt').read_text(encoding='utf-8'), 'root-gate-seams', 'exec'))"
~~~

## Binding independent review: e6277cf/source3870ac4 — NOT READY

Separate physical chat 01a142fb-ed51-78e2-83f3-e1e6822af7f2 independently ran the A suite and original controls, then found F1/F2 using its own public API reproductions: declaration validation skipped absent/empty/nullable descendants, and an answer to an old-generation wait released a new unanswered wait. Its original report is retained byte-for-byte in evidence/f1f2/original-NOT-READY.md (SHA256 6f66ca4dca61181c24e9db7d82ad3cf9a4087b356a719bb2569388937e31b086). That verdict is not overwritten by this correction.

Owner authorized only this A correction and repeat independent review. Production fix source099621b adds full declaration admission and current Attempt/generation wait binding. Its first native run exposed a stale exact wait oracle and was stopped INCOMPLETE/SUPERSEDED. Final source3d4bcbc changes that oracle to require every exact binding field; production api/formats are unchanged from099621b. Full A124 PASS/242.03s and original counterexamples2 GREEN precede the final full native gate. Independent physical re-review on final3d4bcbc closed F1/F2 at code level without new blockers: its own124 PASS/222.01s,22/22 controls,42 negative and16 positive C3/C8 admissions, five adjacent F2 cases plus original assertions and concurrent replies. Its checkpoint report/verification are retained raw as evidence/f1f2/re-review-code-checkpoint.md/.json. Final readiness remains PENDING RECONCILIATION until the new native/raw manifests/evidence-only candidate are checked; no final READY or owner acceptance is inferred.

Final required native gate on3d4bcbc:1522 PASS/1518.47s, exit0; format/lint/types/37boundaries/hygiene/report and root/core/app builds PASS. All38 source Git/worktree hashes and new wheel proof match. These are executor measurements; independent final reconciliation of the evidence-only candidate remains pending. No owner acceptance is claimed.

END_OF_FILE: IMPLEMENTATION-REVIEW.md

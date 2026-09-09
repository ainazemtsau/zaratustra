# G5 engineering REPORT HOME

## outcome

Fresh binding G5: PASS для exact candidate
f917565e141804508c11954c5de51566e82c48ca, только M1/T1.
Дефектов, опровергающих узкое K1, не найдено. Все три done_when исходного
engineering CALL технически подтверждены; приёмка в PROBA не завершена.

## evidence

[G5-REPORT.md](G5-REPORT.md), [receipt.json](receipt.json),
[REPRODUCE.md](REPRODUCE.md), raw/native-deliver.txt и evidence archives.
148 tests / 33.21s, все native gates PASS; 41 независимая группа,
включая 34 отказа без записи и три exact original-backup restores.
19 handoff hashes, оба source diff и 222 retained files сверены;
31 actual mutation сопоставлена с request/authority/receipt.
Fresh physical task: 01a08622-47fd-7d82-974e-15ef8e1f2263.

## assumptions

PROBA v36; доверенный локальный adapter действует по данному разрешению
только в новых fictional scratch workspace. Правила — доверенный Python.
Source implementation fc32c8dcf79d88e2799e061638ad7b51ff94a98c идентична
candidate по src/tools/tests/dependencies/config.

## cuts

Новых cuts нет. Full M1, сосуществование Processes, семь capabilities,
overview и весь остаток W15–W20 остаются open. M0 partial и Work8 boundary
сохранены. Product source и Direction OS не менялись.

## cost

Один полный native run; один независимый behavioral run; две успешные
проверки evidence (вторая добавила input/Artifact и nested ZIP связи).
Sandbox access отказы разрешены escalation; product/behavioral failures нет.
Один guard упаковки исправлен для полного списка untracked путей; raw сохранён.
Новых dependencies/сервисов нет; API/денежная стоимость не измерялась.

## manual-acceptance

Pending. «Запусти g5» — разрешение проверки, не принятие продукта.
Technical binding G5 PASS не означает owner acceptance и Direction done.

## next

solmax — HOME-сверка exact review outputs и фактическая owner acceptance.
T1/M1/M0 не закрываются, successor CALL не создаётся.

END_OF_FILE: docs/g5/m1-probe-20260909/RESULT.md

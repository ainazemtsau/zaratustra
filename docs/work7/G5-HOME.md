# Work 7 после G5 — handback в solmax

Полный Product RESULT: ../../RESULT.md.
Product candidate: 05047e38acc7386484223a5feacc510b015b2a85.
Source candidate: 5866a48c5f9d0f492ad55723120366ffe8f08921.
Fresh physical G5 task: 01a0837c-d088-7eb3-bd31-973ac5d9654e.
Review commit: cf239d7fe0a99fec533fa3977f419d5146962306, прямой потомок candidate;
изменения только docs/g5/work7-20260909/.

## Три критерия исходного CALL

| Критерий | Binding G5 |
|---|---|
| Сохранение Result, mutation, receipt и единственной связи с next Work; authoritative recovery | PASS |
| Единица эффекта W19/W20; повтор, сбой и неизвестный исход без второго эффекта или потери continuation | PASS |
| Восстановимые решение, основание, effective revision, результат и следующий шаг; exact input/output | PASS для Work7; actual clean-chat demonstration принадлежит T7 |

Блокирующих findings нет. Native --deliver: 140 tests, 29.29s, все gates PASS.
Независимая G5: 58 semantic groups и четыре исправленных повтора ошибок своего
harness. Шесть actual console confirmations были действиями проверяющего на
разрешённой fictional копии, не owner runtime acceptance. Исходный пакет 20873
bytes воспроизведён точно; собственный G5 run дал 20882 bytes с новыми id/provenance.

## Полный сохранённый пакет

[Report/raw bundle](evidence/g5-return-20260909/review-bundle.zip) содержит
G5-REPORT.md, RESULT.md, REPRODUCE.md, scripts/raw/input/output, manifest и
runtime-bundle.zip. Для рабочих внутренних ссылок распаковать в новый каталог.
Оригинальный отчёт: C:/my_global_workflow/9111/zaratustra/docs/g5/work7-20260909/G5-REPORT.md.

| Артефакт | SHA-256 |
|---|---|
| G5-REPORT.md внутри bundle | 8cf557c315d1e41324420279cc116305c177cffa66d00ddebdab7689a0600f1c |
| review-manifest.json | a96872b7c0789cfb8e038851be58e58f458f612fac90127106352eb09add45ef |
| review-bundle.zip | 2271667af5240efcab251166462444307cefcdd3b9b982324677cdbf5e150510 |
| runtime-bundle.zip внутри bundle | 167e432e738ffedb6cc61d1d3e1e19e42aa6d883da07e26649714e823f07c571 |

При приёме сверены committed bytes report/manifest/bundle, все 279
файлов и 5 каталогов review manifest, все 556
файлов и 675 каталогов вложенного runtime archive.
Receipt: evidence/g5-return-20260909/receipt.json. Это проверка сохранности
оснований; behavioral verdict вынесен в отдельной G5. Product source/tests/tools/
dependencies после проверенного source candidate не изменены. Текущий handback
commit меняет только отчёт и G5 receipt/evidence. Исходный полный Product RESULT
остаётся доступен по immutable candidate commit.

## Остаток и дальнейшее действие HOME

N1: известный P2 в старом zara records read при ASCII stdout и Unicode данных.
Локус candidate src/zaratustra/cli/__init__.py:238,260; repro в bundle/scripts/
known_locale.py и raw/known-legacy-records-ascii.*. Новый Result-read и carrier
следующей Work проверены; N1 не опровергает три критерия. Сохранить ранее названный
HOME:work7-locale-output-audit из OUTPUT-REPAIR.md. Исправление и новый CALL здесь
не создавались.

next: solmax. Полный Product RESULT и binding G5 готовы как основания для
Direction work/RESULT закрытия T6. Этот Product handback не является Direction
RESULT.state_changes и сам не закрывает T6/CALL/M0. Work8 actual clean-chat
understanding/показ владельцу ещё не выполнены; последующий допуск принадлежит
Direction. Повтор G5 из-за изменения только этих документов не требуется.

END_OF_FILE: docs/work7/G5-HOME.md

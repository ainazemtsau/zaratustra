# W21 — owner decision, 2026-09-08

Source: owner's direct message in the continuing Work 3 product session.
This decision resolves the trust-boundary question returned at
6c9da9eb8213de9f5612179adc829b5192c400a7 / 085e402e17d9d68e579622941c4fb9ada53e531a.

## Exact owner words

«Да, для M0 принимаю предложенную границу доверия: отдельное интерактивное подтверждение точной операции в локальной консоли допустимо. Защита от других процессов того же пользователя ОС и доказательство личности человека не требуются.

Программа локальная, для одного человека, без аккаунтов и входа. За безопасность компьютера отвечает пользователь.

При этом текст файла или ответ модели не считается моим разрешением. Сохраняются проверка границ поручения, актуальных прав и revision. Если моё разрешение уже получено через предусмотренный планом доверенный локальный чат, повторное подтверждение только ради проверки личности не нужно.

Это ответ по W21, а не приёмка Work 3. Сохранить W19–W27. T2/M0 не закрывать, owner runtime PASS не заявлять, Work 4–8 не начинать.»

## Application

Use a local console adapter that displays the exact operation and selected current
Work, then creates a separate in-process authorization bound to that request/path.
No account/login or same-OS-user isolation is required. The trusted library caller
seam also accepts authorization already obtained by a trusted local chat adapter,
without a second identity confirmation. There is no serialized CLI bypass flag or
payload-to-authority conversion. A future chat/Handoff adapter must actually obtain
the owner's permission; a model's assertion cannot substitute for it.

Core still checks current Work status, operation allowlist, rights and revision.
The development request authorizes executor testing on fictional copies; automated
console input in that trial is labeled executor evidence, never owner runtime PASS.
This decision resolves the boundary only. Work 3 done_when still require evidence.

END_OF_FILE: docs/work3/OWNER-DECISION-20260908.md

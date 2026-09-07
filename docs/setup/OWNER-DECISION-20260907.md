# Owner decision — local setup without CI/CD or push notifications

date: 2026-09-07
owner-ack:solmax-zaratustra-local-setup-no-automation-20260907
context: setup report at d91aeee5f4af832b056913fb24cb9584544f65cc

## Question presented
«Принимаем локальную настройку, отложив CI и push-уведомления до отдельного подключения сервисов?»

## Exact owner response
«Так, давай слушай, вообще это отложим. И вот этот push, какие-то вот эти обвязки, то есть да, мы делаем public репозиторий, но сейчас нам это вообще не надо, не хочу, чтобы мы отвлекались вообще. То есть не надо это вообще настраивать. Ну, GitHub нужно будет настроить, вот эти push-уведомления, CI, CD, actions и так далее, не надо настраивать. Пока я отдельно об этом не скажу, можно вырезать это требование.»

## Operative scope
Accept the prepared local setup with the following explicit owner-approved cuts:
CI, CD, GitHub Actions, push notifications and their external setup/test push are
not requirements and must not be configured until the owner separately requests them.
Their absence does not block setup, delivery or the next admitted product Work.
Do not reopen this question merely because a generic checklist mentions them.

A public GitHub repository remains intended future work. This response does not
cancel GitHub, does not prove it configured and does not require creating it now.
Local build, hygiene, tests and package-install evidence remain unchanged.
This is scope acceptance, not an owner-performed runtime test or an M0 demo.
Only the Direction writer may consume the setup CALL and admit Work 1.
No Direction state change is made by this product session.

This decision supersedes the pending external-decision wording in the earlier
LOCAL-RECEIPT.md and the generic PROJECT_SETUP checklist items #2 (CI portion)
and #29 (test push) for this product until new owner words.
All original raw runtime evidence and the issued CALL remain historical evidence.

END_OF_FILE: docs/setup/OWNER-DECISION-20260907.md

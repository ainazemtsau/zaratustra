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


Setup observation: W26 now has local repo/package evidence only. All rows remain open; no product authority/storage/transaction choice was made.
END_OF_FILE: docs/setup/OPEN-AGENDA.md

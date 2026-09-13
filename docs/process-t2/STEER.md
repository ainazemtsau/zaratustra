# HOME technical pre-pass — T2, 2026-09-13

Parent engineering feedback while T2 is under implementation. This is not a new
owner decision, scope change, owner acceptance or binding fresh review. Current
CALL stays authoritative. Evaluate these within T2 and continue autonomously.

1. Observed through the public API: constructing a valid `CreationDraft`, taking
   its `model_dump_json().encode()` and passing it to `save_creation_draft` raises
   `invalid_draft`. Strict Python `model_validate(json.loads(...))` receives JSON
   lists where the frozen model expects tuples. The saved journal/request/proposal
   parsers appear to share the same issue. Preserve strict validation and duplicate
   key rejection, but the product's own serialized model must round-trip. Add an
   exact regression through the real public entry.

2. Inspect and independently reproduce this neighboring failure before fixing it:
   `prepare_process_activation` calls `init_workspace`/`migrate_workspace(..., 7)`
   before proving that an existing target is the retained creation graph. On a
   wrong pre-existing initialized schema-2 workspace, the call ultimately refuses
   `workspace_collision`, but the unrelated target has already been migrated to 7.
   A refusing wrong-target preparation must not mutate/migrate/adopt it. Add a
   behavioral regression using only public product setup/reads, and keep legitimate
   partial activation recovery exact. Do not hand-edit managed state/DB.

3. After disposition is recorded in the product PLAN, move this note intact to
   `docs/process-t2/STEER.md`; do not delete it. Then continue the CALL without
   asking for `continue`.

Keep the T1 prior-snapshot digest invariant, Core authority/binding/migrations and
manual research != approval distinctions unchanged. Fresh HOME G5 remains separate.

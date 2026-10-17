# API-key descriptor compatibility seam

**Confirmed regression in the initial draft; observed narrow correction passes the bounded own checks.** This is an uncommitted snapshot above ac58, not final frozen source acceptance.

Trigger: an API-key profile created by83af has no `native_resource_mode` key. Adding the dataclass field with defaultNone makes raw `asdict(profile)` contain `native_resource_mode:null`. The original CLI chat and Sleep descriptor producers used raw asdict. Their existing pin checks compare the exact descriptor digest; thus identical old config would fail `stale_basis/profile.configuration` before existing Work handling. Unchanged provider wire does not prove this compatibility.

Precise boundary: CLI descriptor construction for chat and Sleep, plus `conversation.pin_profile` and Sleep CLI's exact profile comparison. The pin check is correct; the new producer changed identity bytes. It would fence ordinary reopen/refresh and repeated Sleep for a previously pinned API-key Work, even though the new field is irrelevant for that auth mode. There is no need for general migration or relaxed Core identity checks.

By the time this review captured the source, the worker had already changed both producers to `LiveProfile.configuration()`, which removes **only** `native_resource_mode` whenNone. Native calls-only retains its explicit nonempty mode. Own source snapshot/manifest records the actual inspected bytes. No product source or tests were edited by the reviewer.

Own runtime proof used the actual installed83af package to create two disposable public-API fixtures: existing paused chat Work and paused Sleep Work with the old exact profile record. Old CLI and the captured corrected CLI both return the same appropriate Work-level refusal (`resource_exhausted/work.paused` or `stale_basis/sleep.paused`), not profile.configuration. The corrected descriptor equals the full old descriptor and its digest. Direct admission of raw asdict with the added null reproduces the configuration refusal. A real model-name change remains refused. `read_exact` confirms profile body/revision unchanged; heads, Work, attempts, actions and observations stay unchanged; attempts/actions0. Native calls-only mode remains present in configuration. No network, model or real credential access occurred.

Limits: these fixtures prove unchanged descriptor/pin handling and repeat admission to the same paused-state behavior, not a successful model execution or completed Sleep analysis. Final frozen source/build must contain this same correction and its reached regression control; final API-key wire checks remain separately required.

The first checker wrongly expected `records` in public read_snapshot and stopped with KeyError after the chat comparisons. Original checker/logs and `harness-note.json` are preserved; corrected checker uses public read_exact and passes both cases. This harness failure is not reported as a product defect or hidden retry.

Evidence: `result.json`, `snapshot-manifest.json`, `seed_old.py`, corrected/first checker and both old/current CLI stdout/stderr. A bounded fix is sufficient: preserve pre-change API-key descriptor serialization while including the new mode when actually selected. Do not rewrite saved profile records or weaken exact profile equality.

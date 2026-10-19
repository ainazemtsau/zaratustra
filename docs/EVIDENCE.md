# First-block evidence

The three authorized first-block outcomes have executed evidence. Full R1 is still
incomplete; independent fresh review and actual-owner usefulness remain pending.

Public runtime candidate 1:
`92b1d8d7953a56f1a41e90856770d4b7128391bd`.
Public runtime candidate 2:
`8c9340d4a6717cf4c22ab1a8592378115a5d17aa`.
Route: `ainazemtsau/zaratustra`, branch `codex/zaratustra-v1`, public visibility
checked through authenticated GitHub metadata. The final handoff commit adds only
documentation/evidence/command clarification to candidate 2; runtime resources,
manifest, lockfile and tests remain identical. Its exact identity is supplied in
the executor's final reply and read back from the installed Git checkout.

Installed package identity: Pi-managed
`git:github.com/ainazemtsau/zaratustra@<exact-commit>`; `package.json` version
`0.1.0-dev.1`. Git commit is the candidate version identity. Cache was outside the
development checkout, with only Zod installed physically; host Pi/TypeBox peers
were supplied by Pi. No custom installer/build step or npm release was used.

Actual qualification host: Windows 11 Pro x64, build `10.0.26200`; Node
`v22.19.0`, npm `11.6.2`, Pi `@earendil-works/pi-coding-agent@1.3.0`, SQLite
`3.50.4`, WAL, schema 1, SQLite integrity `ok`. Live recipient:
`openai-codex / gpt-6.1-sol`, thinking level medium. Initial selection came from
the owner's Pi settings; native SDK authPath handled authentication. No credentials
were inspected/copied/printed/committed and package config stayed isolated.

## Required outcome observations

| Outcome                                | Observed evidence                                                                                                                                                                                                                                                                                                                                                                                                                                       |
| -------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Public installed create/save/continue  | Attempts 3–4 on candidate 1 and 13–14 on candidate 2. Actual model chose skills/tools and committed four English/original records, four revisions, a Change and receipt. Exact original Russian input hash matches retained Evidence. A separate process/cwd had no previous messages and continued in Russian from Core.                                                                                                                               |
| Real retained material                 | Attempt 5 retained Markdown, committed Evidence, read `zara_read.range`, explained the actual source and kept the full-book wait. Attempt 12 after reinstall read the immutable copy with the original input path absent. Attempt 15 repeated TXT retention/read on candidate 2.                                                                                                                                                                        |
| Atomicity and honest errors            | Full native command: 10/10 tests. Installed candidate-2 Core: 9/9 disk tests. Faults after prepare, after records, before commit and after commit; all domain state/receipt or none. Same-ID replay and changed-payload conflict; stale revisions and bad linked types reject atomically. Corrupt/missing/read-only stores and SQLite disk-full fault do not reset or claim persistence. Live attempt 10 had no database and honestly reported no save. |
| Lost response without request ID       | Attempt 8 discarded the real committed reply and aborted. Attempt 9, then candidate-2 attempt 16, began with an empty session and an ordinary request without IDs/names/transcript; model browsed operations, read receipt and targets, and created no replacement.                                                                                                                                                                                     |
| Similar/ambiguous inputs               | Mechanical equal-text independent intentions create distinct records. Attempt 7 created a second independent Work while preserving the first. Attempt 11 asked which of two actual works the person meant and made no commit.                                                                                                                                                                                                                           |
| Current snapshot and host preservation | Attempt 6 requests show snapshot sequence `3,3,4`; the request after guarded correction contains new state/revision. One bootstrap occurrence, host system sections and earlier messages remain. All observed settled sessions have zero permanent snapshot messages. Mechanical test preserves system/user/tool/foreign custom messages by object identity.                                                                                            |
| Native package lifecycle               | `pi update --extensions` kept the pin. Native extension/skill filters and `pi remove` made all six zara tools and both skills absent. Disable/remove/same-ref reinstall and explicit candidate-1→2 upgrade preserved byte hashes of manifest/database/material. Reinstall restored resources and attempt 12 rediscovered state.                                                                                                                         |

Evidence files live in [evidence/](evidence/README.md): scenario inputs, actual tool
events, model outputs, request snapshots, disk rows, receipts, failures, mechanical
logs, resource observations and workspace hashes. [ATTEMPTS.md](ATTEMPTS.md)
retains development failures and the corrected reporting error. Independent
reviewers should open these artifacts rather than infer success from fluent prose.

## Validation and limits

`npm run check` ran formatting, ESLint, TypeScript, dependency-cruiser, compile and
10 native tests. A seeded Core→extension import failed the dependency boundary and
was removed. Missing RESULT failed the report gate; final required fields pass.
Installed Core used isolated `tsx@4.20.6` tooling with sources/tests from the Pi Git
cache, not the developer tree. No independent review has occurred.

Before live tests the finite budget was recorded: 18 prompt attempts, 80 provider
requests, 1,500,000 input tokens including cache reads/writes, 90,000 output tokens,
$20 reported estimated cost; per scenario 180 seconds. Through attempt 16:
16 prompt attempts (one failed before model access), 65 requests, 413,249 input,
7,590 output, 137,600 cache-read tokens, estimated $0.640958. Every attempt is
retained. The last documentation-commit smoke check has its own local receipt and
is included in the final reply's usage. Product use has no such imposed test limits.

Known limits: one trusted personal writer, no OS isolation; UTF-8 TXT/Markdown up
to 1 MiB, 8,000-code-point read ranges, bounded catalog/snapshot; safe orphan files
may remain after interrupted import. Power-loss durability, a generally new-schema
upgrade, other OS/runtime profiles and full R1 are unqualified. Tests of logical
interruption and SQLite max_page_count are not hardware power-loss or physical
disk-exhaustion certification. No arbitrary-command duplicate prevention.

The first missing R1 outcome is complete nested/terminal Work and dependencies.
All outstanding R1 areas and per-row dispositions are in [R1-STATUS.md](R1-STATUS.md)
and [DEVELOPMENT.md](DEVELOPMENT.md). PDF/EPUB, other four kinds, search/corrections,
Methods/Runs, Signals/Evaluations, effects/exact approvals, backup/quarantine restore,
archive/deletion, complete access/provider-switch coverage remain outstanding.
Codex is next integration; Sleep is R2. Owner plan approval does not accept this result.

## Fresh reviewer

Freeze the delivered public commit, install it in a newly isolated Pi config/home,
choose an independent natural-language case and inspect actual records/receipts
after a new-process continuation. Refute source fidelity, English/original separation,
snapshot freshness, atomicity/replay and no-ID recovery, failure honesty, package
lifecycle preservation and scope/public hygiene. Rerun native checks. The reviewer
chooses their request/rubric independently; neither this executor nor a helper has
supplied a binding review. Owner acceptance follows actual inspection/use.

END_OF_FILE: docs/EVIDENCE.md

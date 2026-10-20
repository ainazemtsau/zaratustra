# Outcome C attempt ledger

Accepted baseline 27a74fd. This ledger covers this assignment only; historical B/P2 and
independent-review budgets remain separate and unchanged. All actual totals and later attempts are retained below.
Live caps fixed at 24 conversation attempts, 140 provider requests, USD 15 Pi estimate.

Mechanical/development attempts retained under the separate original evidence root:

- Required source/schema/spec/profile reads completed; both specification hashes match.
- Initial combined long read outputs were truncated; required sections were reread in bounded chunks.
- A read of eslint.config.mjs failed because this repository uses eslint.config.js; corrected.
- New runtime parsers installed successfully. Attempted @types/yauzl@3.2.0 failed ETARGET;
  no such package was added. The yauzl caller is JS, so no type package is needed.
- Python reportlab/pypdf availability check failed; a separate fixture-only pypdf@6.1.3
  tools directory was installed. Runtime/product dependencies do not include it.
- Initial 18 first-block/P2 tests all passed after implementation.
- First new Work test run: 4/6 passed. One fixture omitted next_action on explicit reopen;
  transition_work now accepts an explicit next_action. One real final-state reply check
  incorrectly read the old Work revision; fixed to inspect the final transaction state.
  A union-ref assertion needed a TypeScript narrowing. All failures are retained.
- First combined C run: 12/12 passed; ESLint found one unused test type import, removed.
- First full format/check found three Prettier non-idempotent first-pass layouts;
  a focused second formatting pass resolved them. The subsequent full check passed 30/30.
- Added larger book/output/ZIP-limit fixtures and tightened final-batch late-reply,
  dependency/wait and lifecycle checks. Focused material/work checks passed.
- One patch application had stale skill context and made no edits; reapplied to current text.
- One Python documentation write used the Windows default codec and failed on Russian words;
  RESULT was immediately rewritten with explicit UTF-8 before checks/publication.
- Native SDK P2 probe passed twice (second adds positive PDF/EPUB and denied formats):
  zero provider requests, denied source reads and UUIDs; exact retained tail and emoji.
- Actual normally installed 27a74fd seeded 4 records, 5 revisions, 2 Changes and 2 receipts
  plus an immutable Markdown original. Separate old-reader install retained for rejection.
- Candidate deliver passed 31/31 tests, including generated results/handoff claim fault
  boundaries. No test failure is relabelled an independent review or owner verdict.
- npm audit: runtime zero; full 9 high nodes from the retained single braces advisory.
  No existing locked dependency version changed. Expected audit nonzero is not a PASS.

Every live attempt and installation identity is retained. No budget
reset and no prepared mutation is called model behavior.

Initial public validation candidates: e683a4809fa762ee27e8e08d400f0a231fd0c229,
then d3dc6c38b02ba6e91c1037bdf1ed074b9be3c3b3 (observer-only row-prototype fix).
The initial upgrade verifier compared null-prototype DatabaseSync rows with parsed JSON
objects and failed despite equal stored columns; corrected serialization comparison passed.
The original failure and both verifier logs remain. Clean installs disclosed six native
peer metadata removals in installed package-lock, with every other tracked byte matching.
A launch command used a cwd before creating it and was rejected before a live attempt;
setup was then split into creation and launch.

Early live pre-validation on d3dc6c3: 3 attempts, 26 requests, Pi USD 0.3946912.
All settled: old installed data continuation; nested plan/independent saved invitation;
first partial material and manual handoff. No scripted mutation or owner verdict.
Inspection of the return path found missing ancestor-version bindings for handoffs and
claims. Added ancestor snapshots/guards and final-batch pause/late-response negatives;
8/8 focused Work tests passed. These early runs remain counted, not final-candidate proof.
Affected stories subsequently ran on fixed public 55fac403, as recorded below.

## Subsequent implementation, qualification and reboot continuation

- Found a real graph-node key collision for step IDs `parent` and `complete`; fixed
  with JSON tuple keys, regression passed. Candidate 55fac403 then frozen for main stories.
- Check/deliver grew from 30 to 31, 32 and 33 meaningful tests; final code check/deliver
  passed 33/33. All first-block/P2 regressions retained. Installed tests passed 32/32
  on 55fac. On corrected 334c572 the initial installed command selected 24 tests;
  the separate omitted P2 file then passed 8/8. No fabricated combined test run.
- Native Pi installs outside checkout checked clean package configuration and actual
  27a74fd→55fac and 27a74fd→334c572 upgrades. Seed: 4 records, 5 revisions, 2 Changes,
  2 intents/receipts plus exact material. Every original row, ID/hash and receipt replay
  preserved; old 27a74fd writer refuses schema 2. Backups retained in isolated homes.
- Actual model attempts 04–19, all errors/costs/prompts/responses are in
  [C-CONVERSATIONS](C-CONVERSATIONS.md) and verification-final.json. Six validator
  rejections: 02 twice, 08 once, 10 twice, 18 once. They are actual tool failures,
  not hidden passes. Corrected commits follow new intent IDs. No timeout occurred.
- A followup readback assertion expected South to be waiting after 18, but both Works
  were active with pending waits and still-open preparation steps. This was observed
  model planning drift. Ordinary request 19 reconciled saved handoffs with the plan;
  both now wait, North partial, South unanswered, no new external reply. Detailed
  before/after rows are retained in clarification-verification.json.
- Additional negative probe found image-only EPUB wrongly marked readable with only
  line separators. RED original retained. Corrected worker marks blank/image-only
  chapters unavailable, whole book scanned if all blank, mixed book partial.
  One added fixture extends an existing classification test. Corrected installed GREEN
  passed; 13 other installed-worker PDF/EPUB fixture outputs are byte-identical.
- Computer rebooted after deliver-image-fix completed. Fresh status retained only four
  intended fix files on authorized branch; published 334c572. No state/budget reset.
- After reboot, two evidence probes used relative paths where Worker/Jiti require
  absolute paths; both failed before comparison, and absolute-path retries passed.
- One native P2 run omitted the supported authPath environment after reboot and failed
  before native model-switch authorization. Retry supplied the path to Pi without
  reading/copying credentials; positive TXT/PDF/EPUB and all denied-source checks passed.
  Native async revoke on corrected package passed, zero provider requests.
- Attempt 20 on corrected public package used the remaining two requests on skill/read
  and map. Next payload was logged but blocked before provider dispatch. No import,
  response or mutation; unverified. Budget stopped at first cap: 20 attempts, 140
  requests, USD 2.5546883999999985 Pi estimate. No subsequent model request authorized.
- Extending the verifier for this aborted case initially indexed absent response and
  failed KeyError; nullable response handling passed. Raw failed log retained.
- Evidence export 01 rejected a captured JSON followed by SQLite stderr; export 02
  then rejected sanitizer source code containing its own forbidden-pattern literal;
  export 03 rejected the same literal quoted in the previous failure log. Export 04
  validated JSON payloads separately from tool/log source text and passed 316 files.
  All failed exports remain outside checkout. Checked export 05 adds final check/deliver,
  old-writer rejection and pre-delivery preservation snapshot; only validated derivatives
  are published. Final check and deliver both passed 33/33.
- Git staging exposed CRLF normalization of text derivatives. Export 06 canonicalizes
  derivative LF before hashing; staged Git blobs are checked against every manifest
  digest. Raw originals and failed exports remain unchanged. Only final checked export
  derivatives enter the public commit.
- A documentation apply_patch attempted delete/add of the same path and was rejected
  without edits; rewritten as ordinary UTF-8 writes. This is executor diary, not a test.

Raw command outputs are hashed synthetic derivatives under c-evidence; raw originals
remain outside checkout. Earlier P2/review originals and normative specification were
not rewritten. Mechanical actions never count as model behavior or owner verdict.

END_OF_FILE: docs/C-ATTEMPTS.md

# Outcome C attempt ledger

Accepted baseline 27a74fd. This ledger covers this assignment only; historical B/P2 and
independent-review budgets remain separate and unchanged. No live attempt/request yet.
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

Every live attempt and installation identity will be appended after execution. No budget
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
Affected stories will run on the next fixed public candidate.

END_OF_FILE: docs/C-ATTEMPTS.md

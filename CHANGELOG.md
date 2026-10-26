# Changelog

## 0.6.0-dev.2 — compact interactive approvals

- Pi 1.4 interactive confirmation shows a short action/target/consequence summary, not full record data or complete file bodies.
- Press Latin `D` while the native confirmation is open to review full human-readable details in bounded pages without relying on terminal/modal scrolling. Return to the SAME proposal for the final native Yes/No. Escape/cancel from details rejects the proposal.
- Destructive/administrative changes, non-create record mutations and omitted scope/long consequences require detail review before the final confirmation. Oversized content remains in the immutable proposal, never replaced by the summary.
- Terminal control/bidi controls are shown as escaped data. The normal path still uses one native confirmation; detail navigation never approves or executes anything.
- RPC/SDK clients retain the existing full native-dialog presentation; compact paging is currently interactive-TUI only.
- No schema, dependencies, storage authority or deployment behavior change. No personal workspace is automatically updated.
- Added focused summary/navigation/refusal/failure/Unicode cases. Updated the existing epoch-invalidation test to check the current exact fencing error code rather than a stale message regex; production epoch checks are unchanged.

Verification: nine focused confirmation cases pass, including a headless render of the actual Pi 1.4 selector at 60×24; selected exact-approval invalidation and native-dialog concurrency cases pass. Types, changed-file ESLint/Prettier, dependency boundaries, build and diff whitespace checks pass. Initial mixed verification timed out at 120 seconds and exposed a page-count fixture error and stale epoch-error expectation; these failed attempts are not relabelled as passing runs.

Limits: focused mechanical checks only; failed initial attempts retained in development history. No paid model scenarios, full historical qualification, independent live visual acceptance or real-user usefulness claim. The owner must still verify readability and `D` navigation after explicitly updating their installed package.

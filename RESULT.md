outcome: Fixed the two independently confirmed P2 defects in the first block; local regressions passed. This development candidate still requires its installed checks and fresh-process live retrieval before handback. No independent PASS or owner acceptance is claimed.

evidence: Baseline 91ab52cfcfd53bfa7041b052468e2432d432b311 reproduced both defects with native Pi SDK and zero provider requests. Import preflight now rejects before source content reads/UUID allocations; code-point ranges address both imported and retained observed Evidence. Local npm run check passed 18/18 tests. New immutable outputs are separate from original builder/reviewer evidence. Installed/public/live observations will be added after this candidate is published.

assumptions: Trusted personal one-writer deployment; Windows 11 x64, Node 22.19.0 and Pi 1.3.0. Existing consciously selected openai-codex/gpt-6.1-sol, medium thinking and native Pi authentication only. Original specification and public derivative hashes were reverified unchanged. No scope or authority change.

cuts: Full R1 outstanding as recorded in docs/R1-STATUS.md. No Codex adapter, Sleep, PDF/EPUB, general provider-switch policy or OS isolation added. Development advisories remain under applicability review; no dependency updates are included in these P2 fixes.

cost: No live attempts or provider requests used before this candidate. Upcoming patch checks share a single ledger capped at 6 conversational attempts, 30 provider requests and USD 5 Pi estimate; previous first-block costs remain historical and separate.

manual-acceptance: Pending installed verification, separate fresh review and actual owner verdict. docs/REPRODUCE.md now requires an explicit chosen full public commit instead of an old implicit pin.

next: solmax

END_OF_FILE: RESULT.md

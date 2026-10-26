# Release workflow

Agreed maintenance workflow, 26 October 2026. Pi 1.4 only. Ordinary releases use numeric versions without an automatic dev suffix. A release tag does not assert full R1 qualification or real-user usefulness.

1. Start a separate branch for a bounded issue. Preserve original reports, hypotheses, failed attempts, actual checks and later confirmation separately. Parallel implementers own disjoint branches/modules; one integrator owns the final release.
2. Read current AGENTS.md and relevant contracts/skills. General fixes belong in this public source checkout, never permanently in an installed package. Public fixtures and notes must be minimal and anonymized; no personal workspace, Health, credentials or private Activity exports.
3. Run proportionate focused tests, types, lint, format and build. Do not automatically run the full historical matrix, scale qualification or paid model conversations. Preserve failures and explain scope/limitations. Changes to approval, access or recovery require focused negative regressions.
4. Review the exact diff and intended file set. Bump package.json and the lockfile together. Use ordinary numeric releases: 0.6.0 is the current baseline, 0.6.1/0.6.2 are fixes and 0.7.0 adds capabilities. Use rc only for explicitly designated release candidates; pending real-use verification alone does not require dev. Preserve old published prerelease tags. Before 1.0, communicate incompatible changes and migration requirements explicitly; the number alone is not a guarantee of full stability. Record changes, verification and limitations in CHANGELOG.md.
5. Integrate checked changes into main without force pushes or overwriting another writer. Recheck main/remote state first. Publish the exact commit and matching version tag; add concise GitHub release notes when available. Never move an existing release tag to different bytes. Report a failed/uncertain publication rather than claiming completion.
6. Installation in a personal workspace is a SEPARATE explicit owner-authorized action, pinned to the exact public commit. Source publication is not deployment. Preserve memory and Git policy. Before a schema/control change assess compatibility and verified backup needs; follow CONCURRENCY.md upgrade instructions. Rolling old code back over a newer schema may be unsafe.
7. Report: changed behavior; checks actually performed; public commit/tag; installed-package update status; ordinary-use checks still needed. Keep the issue open for real-use confirmation; synthetic checks or editing instructions/code do not establish usefulness.

Personal context persistence and its private Git commit/push remain separate from public product release. Do not automatically stage live memory files, change ignore rules, copy only an active SQLite main file or promise cross-device merging/working-system restoration.

## Approval UI maintenance

The immutable exact proposal, native yes/no answer and existing dependency/epoch checks remain authoritative. Interactive Pi confirmation may use a compact presentation, but complete details must remain reviewable before approval. No summary, details-navigation key or model-generated explanation can itself grant permission.

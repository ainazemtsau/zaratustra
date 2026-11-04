# Zaratustra development

This is the public TypeScript product repository. Read README.md for current
runtime behavior and docs/OPENSPEC.md for the development workflow.

## Working agreements

- Use the project-local OpenSpec CLI through `npm run openspec -- <command>`.
- Read `openspec/config.yaml` and the relevant capability specs and active change.
- Keep root guidance short. Read module AGENTS.md when working in its module.
- Investigate questions through exploration. Prepare behavior changes as OpenSpec
  proposals, delta specs, design and tasks, then obtain the owner's approval of
  that scope before implementation. Existing explicit approval covers its scope.
- Keep current behavior, approved changes and open decisions distinguishable.
  Sync completed delta specs only when implementation and checks support them.
- Use a `codex/` branch and bounded tasks. A coordinator owns shared interfaces,
  integration and release. Preserve concurrent edits and assign worker ownership.
- Keep private workspace and Health data out of public files and fixtures.
  Development uses isolated synthetic workspaces. Updating personal data needs
  an explicitly authorized migration with a verified backup and comparison.
- Preserve IDs, revisions, selected source bytes, documents, access boundaries
  and UNKNOWN effects. Run Core behind its portable storage boundary.
- The qualified runtime is Windows x64, Node 24.22.1 and Pi 1.4.0. Canonical corpus
  format is 1, projection schema is 10 and control format is 3.
- Run focused mechanical tests and relevant types, lint, dependency boundaries
  and build. Use at most ten processes. Paid model calls, long conversations and
  full historical qualification require a concrete authorized need.
- Give the owner concise Russian explanations. Keep canonical OpenSpec artifacts
  in English. Report actual checks, limitations and pending work.

Start a successor chat by reading docs/workspace-structure-handoff.md. It records
an upcoming architecture discussion. Product implementation requires the agreed
OpenSpec change and owner approval.

END_OF_FILE: AGENTS.md

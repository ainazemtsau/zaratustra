# Stage 6 pass 3, part 3.9 — open technical review

Independent Codex review of exact commit
`74485ca8f6b2b8c8d895ebfa800b3994ef737ebf` confirmed P1. Review is OPEN.
The full Windows `tools.check --deliver` PASS (662 tests, types, Ruff, 21
contracts, sdist, wheel) is the implementation session's result; the reviewer
did not repeat that full gate.

Public Core reproducer and report:
`C:\Users\Anton\AppData\Local\Temp\zaratustra-stage6-3.9-review-74485ca-1790326772351\review_nested_artifact.py`
and `READONLY-REVIEW.md` beside it. In P→N→G, unique Artifact X is only an
input of G. After G/Y and N are accepted, P is accepted with a basis quoting
X. Deleting X and completing deletions clears N's basis but leaves P's basis,
replay and receipt; the marker remains after restart in closed SQLite and a
new backup, despite `pending_jobs=0` and `live_store_sanitized=true`.

`_outcome_dependencies` includes descendant Work IDs but only collects
Artifact dependencies of immediate children. Correction must follow saved
structural addresses through descendants and historical plan revisions, also
checking closure/revalidation bases, nested plans and confirmations, and
sequential deletion after restart. Independent replacement evidence must stay.
No correction is claimed here. Part 3.10 and acceptance remain unstarted;
`database is locked` remains a separate open observation.

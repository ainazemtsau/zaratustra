# Attempts — retain failures

1. Environment discovery tried the historical `@mariozechner` package location;
   it did not exist. The actual installed package is `@earendil-works/pi-coding-agent`
   1.3.0. This was a read-only discovery error, not a product test.
2. First native run: formatting/lint/boundary passed; types failed because commit
   and envelope results were typed too broadly. Disk tests: 5/7 passed; two failed
   with `no such column: updated_at` in snapshot sorting. No candidate published.
3. First patch attempt matched pre-format text and was rejected without applying.
   Corrected against current formatted files. Snapshot sort now reads the JSON field;
   Receipt and generic envelopes preserve actual result types. Structural operations
   filtering was also moved before pagination, using exact JSON atom equality.
4. Next check stopped at three test-only unsafe casts after the stronger result
   type. A scripted edit then failed on Windows' default cp1252 when reading the
   Russian fixture; check retained the same errors. Explicit UTF-8 fixed the edit.
5. Native `npm run check` passed: format, ESLint, types, dependency boundaries,
   build, 7/7 real-disk tests (`mechanical-04.txt` in isolated local output).
   npm installation warned about a transitive deprecated node-domexception and
   the selected ESLint release's support status. No installation failure.

6. Candidate 1 was published at `92b1d8d7953a56f1a41e90856770d4b7128391bd` and
   installed through native Pi into an isolated config/cache. Only Zod was physically
   installed as a runtime dependency; Pi and TypeBox came from the host mapping.
7. Live attempt 1 stopped before a provider request: ReadOnlyAuthStorage is declared
   internally but not exported by the public SDK root. The runner now uses documented
   ModelRuntime `authPath`, leaving credential reads/refresh to native Pi. No credential
   was manually inspected, copied, printed or committed.
8. Live attempt 2 made three actual model requests but the runner had omitted
   `session.bindExtensions({})`; session_start had not opened Core. The model read the
   skill, received an actual STORE_UNAVAILABLE tool error and truthfully said no area
   was saved. The runner was corrected using the pinned SDK example. No product source
   change was needed for this harness defect.
9. Live attempts 3–11 passed their assigned cases: create, fresh continuation,
   retained material import/range read, correction/current snapshot, distinct similar
   goal, intentional lost reply, no-ID recovery, unavailable store, ambiguous request.
   Attempt 8 is deliberately interrupted after the real commit; no successful commit
   response or final assistant answer reached that session. Attempt 9 found its receipt
   and targets with no new commit. Attempt 10 is an expected failure-path test.
10. Native reconcile kept the exact pin. Native resource filters disabled extension
    and skills; remove and same-ref reinstall preserved byte hashes of all three home
    files (manifest, database, retained material). Resource discovery had no tools or
    skills while disabled/removed and restored them after reinstall.
11. Executor self-inspection found two preserving hardening gaps before the next
    candidate: invalid UTF-8 was reported too generically, and a trusted home alias
    should be resolved before creating files. UTF-8 now has a specific validation error;
    existing ancestors are resolved before rejecting package/cache homes. Native checks
    pass, including invalid UTF-8 and SQLite max_page_count disk-full fault.
12. Git warned about automatic line-ending conversion. A draft note in candidate 2
    incorrectly described an observed HTML digest mismatch. Exact Git-blob readback
    disproved that: both candidate 1 and candidate 2 have the declared derivative
    SHA256 `4940e16e39174df941da98889c43b713c48287d4aeda8754fd57660d462a77cb`.
    `.gitattributes` is a preserving guard, not repair of a demonstrated byte defect.
    This note corrects that reporting error explicitly.
13. Budget accounting initially tracked uncached input separately. Before attempt 9
    it was recomputed from all retained message usage including cache reads/writes;
    subsequent input accounting includes them. The original ledger is retained. No cap
    was approached and no usage was discarded.

14. After same-ref reinstall, attempt 12 read retained source ranges even though the
    original input path no longer existed, and continued from the corrected wait.
15. Candidate 2 (`8c9340d4a6717cf4c22ab1a8592378115a5d17aa`) passed the full native
    command (10/10 tests), published fast-forward, installed via Pi, and its installed
    Core passed 9/9 disk tests using isolated tsx tooling. An explicit candidate-1 to
    candidate-2 upgrade preserved the existing workspace/material hashes. Both are
    authorized development candidates with schema 1, not a general migration proof.

16. Attempts 13–16 on installed candidate 2 passed create, another-cwd fresh
    continuation, retained TXT import/range read, and no-ID lost-response recovery.
17. First public-evidence export stopped when a native resource console file with
    a `.json` suffix also contained SQLite's stderr warning. No evidence was lost;
    the exporter now preserves such captures as console text and labels derivatives.
    Original files remain unchanged, with both original/public hashes in the manifest.
18. Seeded boundary, missing-report and underfilled-report negative checks failed
    as intended. These are expected validation outcomes, not passing product requests.

19. A report-file patch using delete+add of the same path was rejected by the
    patch tool; it changed no source/report bytes. Updating the existing fixture
    in one operation produced the final report. This was tooling, not a product run.

20. Handoff candidate `2a91733a1215cee74c57a733e8ef527d17d3c1da` installed and
    live attempt 17 continued correctly (runtime inputs matched candidate 2).
    Installed artifact verification then found 153 public evidence digest mismatches:
    Git had normalized CRLF in derived evidence after its manifest was computed.
    This was an actual packaging defect, distinct from the disproved HTML suspicion
    in item 12. `docs/evidence/** -text` now preserves evidence bytes through Git.
    Source, model results and original local artifacts were unchanged. The replacement
    handoff is checked from staged Git blobs and the installed public checkout.

Later final-candidate checks and identities are recorded in EVIDENCE.md. Saved raw live attempts and native logs remain under the isolated output root;
public evidence is a labelled path-redacted derivative. The earliest setup/type/SQL
failures are recorded in this execution transcript and the observations above, not
misrepresented as later raw file captures.

END_OF_FILE: docs/ATTEMPTS.md

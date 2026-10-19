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
12. Git's initial automatic text conversion normalized the public HTML's CRLF bytes,
    making the declared derivative digest inaccurate in candidate 1. `.gitattributes`
    now preserves the HTML as bytes and fixes source/docs checkout line endings to LF.
    The next candidate restores the declared derivative digest without normative edits.
13. Budget accounting initially tracked uncached input separately. Before attempt 9
    it was recomputed from all retained message usage including cache reads/writes;
    subsequent input accounting includes them. The original ledger is retained. No cap
    was approached and no usage was discarded.

Later final-candidate checks and identities are recorded in EVIDENCE.md. All local
raw attempts remain under the isolated output root; public evidence is a labelled
path-redacted derivative.

END_OF_FILE: docs/ATTEMPTS.md

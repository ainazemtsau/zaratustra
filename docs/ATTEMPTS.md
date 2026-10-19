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

Further candidate/install/live attempts are appended below, including failures.

END_OF_FILE: docs/ATTEMPTS.md

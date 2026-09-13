# Process creation T2 correction technical handback

## outcome

Version 0.14.1 at implementation commit
`71d76ace9ec443c633ce2019e9dc5676c4cbbdcd` repairs the fresh-review F1 defect.
Retained preview SHA-256, readable UTF-8 display, authorization and fresh
revalidation now bind one exact byte representation. The report evidence commit is
`REPORT_COMMIT_PENDING`. Existing journal/request/source canonical serialization,
saved source digests, Core identity/authority/immutable bindings and released
migrations remain unchanged. This is technical correction delivery, not T2 close.

## evidence

- Independent pre-fix reproduction: ASCII retained/shown hashes matched and
  authorized; combined Unicode retained/shown hashes differed and refused
  `permission_denied`. The new regression now authorizes, executes six Core
  operations and common-entry opens the exact first Work for both cases.
- Exact pre-fix 0.14.0 Unicode request fixture SHA-256
  `5f993c2957b78eaedc9d9d70d6a5bb881ef21a6957f5bab4a07dec9f16245272`
  parses and re-saves byte-for-byte under 0.14.1.
- Focused T2 suite: 15 passed. Existing wrong/stale/tampered/no-authorization,
  missing/terminal-rights, replay/reconciliation and wrong-target protections remain
  covered and their implementation paths were not changed.
- Native `tools.check`: exit 0; 114 format, Ruff, mypy 99, contracts 16/16,
  345 tests in 110.72 seconds, wheel/sdist. Log:
  `_scratch/process-t2-correction-gates-01/full-check.log`.
- Exact commit `71d76ac...` wheel proof: 0.14.1 wheel SHA-256
  `7e0b08bc68ec2c074feee309b9c1682f15616a866c50889941d641a5d1d38a56`;
  both original external fixtures activate/open; dev packages absent before explicit
  exposure; every product origin is wheel `site-packages`. Correction-specific `-I`
  empty-cwd proof also activates/opens ASCII and combined Unicode cases with six
  receipts and equal retained/shown hashes. Evidence:
  `_scratch/process-t2-correction-installed-01/verification.json` and
  `_scratch/process-t2-correction-installed-unicode-02/verification.json`.
- Report-aware `tools.check --deliver`: exit 0; the same 114/99/16 surface,
  345 tests in 105.23 seconds, wheel/sdist and report structure. Log:
  `_scratch/process-t2-correction-gates-02/deliver.log`. Detailed reproduction,
  criteria disposition and limits are in `docs/process-t2/FIX-READOUT.md`; the
  original `docs/process-t2/READOUT.md` and failed reviewer evidence are preserved.

## assumptions

Pending drafts retain content, not a stored activation-preview digest; recomputing
their prepared preview therefore needs no migration. Synthetic local-chat is valid
technical seam evidence only. Actual human research, confirmation and owner
acceptance remain separate.

## cuts

No T3 safe evolution/replacement/rebinding/migration work and no T4 full physical
installed-reader/lifecycle work was started. No provider, browser, account, real
research/data, personal workspace, paid service, Direction state, CI/integration,
new external right or main push was used.

## cost

One preview-hash representation correction, one two-case activation/open regression,
one immutable pre-fix request fixture, patch version metadata, correction plan/readout
and isolated native/wheel evidence; no new runtime dependency or expense.

## manual-acceptance

pending. Executor checks are not binding G5, owner acceptance or permission to close
T2/start T3/T4. HOME must open another fresh physical reviewer after handback.

## next

solmax

END_OF_FILE: RESULT.md

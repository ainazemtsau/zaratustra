# Process creation T2 correction readout

The bounded F1 correction is implemented in commit
`71d76ace9ec443c633ce2019e9dc5676c4cbbdcd`; the report evidence commit is
`REPORT_COMMIT_PENDING`. It is based on failed candidate
`c9a8d6ee68371f6f68e6971a8d51677125d70f06`. The original `PLAN.md` and
`READOUT.md`, both steering notes, and all fresh-review workspaces/evidence remain
unchanged. Version 0.14.1 distinguishes the corrected artifact.

## Reproduction and correction

A new isolated pre-fix reproduction under `_scratch/process-t2-correction` exercised
public product operations with an ASCII control and one case containing Unicode in
designation, need/research and proposal. ASCII retained/shown preview SHA-256 values
were both `bf22df735fac90cae55c95bac2378f09ca705a47ceec78b12ba78636ad55eaf1`
and authorization succeeded. The Unicode retained value
`5cb3874a75a82ca733610fb472263fc7cd56f0c0417cd3f471f37e4de839c31a`
differed from shown UTF-8 value
`84ff808f778da7093c16fe9f149026f3d276f39eb62e262f007249dce6cb7d6f`;
authorization refused `permission_denied: Changed activation preview`.

The correction changes only `_prepared` preview digest construction from
`sha256(_wire(preview))` to `sha256(_readable_wire(preview))`. The same readable
UTF-8 bytes are now retained, displayed, checked by authorization and compared during
fresh revalidation. `_wire` remains unchanged for journals, research requests,
proposal/definition sources and their existing digests. No migration, Unicode
restriction, special case or hash-check removal was introduced.

The tracked `pre_fix_unicode_request.json` is exact canonical request bytes saved by
0.14.0 before the correction. Its SHA-256 is
`5f993c2957b78eaedc9d9d70d6a5bb881ef21a6957f5bab4a07dec9f16245272`;
0.14.1 parses it and saves identical bytes. This substantiates saved-source wire and
digest compatibility. Pending creation journals need no migration because the
preview digest is derived from their retained content at each preparation.

## Behavioral and installed evidence

The correction-focused regression has an ASCII control and a combined Unicode case.
Both compare the shown bytes to the retained digest, authorize through synthetic
`local-chat`, execute all six exact Core mutations, reach `activated`, and open the
same first Work through common entry. The complete focused T2 command passed 15 tests:

```text
uv run --locked python -m pytest tests/zaratustra/process_creation/test_creation.py tests/tools/test_probe_process_t2.py -q
```

That suite also retains no-authorization and stale-preview refusals, request/return
tamper and proposal/source collision refusals, unsupported capability reporting,
partial-prefix recovery, same-receipt replay, truthful terminal current rights and
wrong initialized target non-mutation. The product correction does not change any of
those validation, authority, reconciliation or Core code paths.

The required native `uv run --locked python -m tools.check` exited 0: 114 files were
formatted, Ruff passed, strict mypy passed over 99 source files, all 16 import
contracts were kept, 345 tests passed in 110.72 seconds, and the 0.14.1 wheel/sdist
built. Full log: `_scratch/process-t2-correction-gates-01/full-check.log`.

The committed-wheel probe exited 0 for exact implementation commit `71d76ac...`.
`_scratch/process-t2-correction-installed-01/verification.json` records version
0.14.1, wheel SHA-256
`7e0b08bc68ec2c074feee309b9c1682f15616a866c50889941d641a5d1d38a56`,
absence of tests/tools before explicit external-fixture exposure, and all product
modules under the isolated wheel `site-packages`. Both original small/project
fictional inputs activated and opened their first Works.

A separate external harness then ran with that wheel's Python, `-I`, from its empty
cwd, without checkout fixtures. Its ASCII and combined Unicode cases both retained
the exact shown preview digest, activated with six receipts and opened the exact first
Work. The Unicode digest was
`6d3c5e1b0076d0c415200b9979cfec3f48c9cfb5697efaf9ebdc853f37e77aa4`.
All loaded `zaratustra.*` origins are recorded under wheel `site-packages` in
`_scratch/process-t2-correction-installed-unicode-02/verification.json`. The first
attempt's product operations succeeded but CP1252 console rendering failed after
evidence save; that `-01` workspace is preserved, and the `-02` retry changed only
console JSON escaping. All research and confirmations were synthetic technical
evidence, never an actual human handoff or approval.

The report-aware `uv run --locked python -m tools.check --deliver` exited 0 with
the same 114/99/16 surface, 345 tests in 105.23 seconds, the 0.14.1 wheel/sdist and
`report structure`. Full log:
`_scratch/process-t2-correction-gates-02/deliver.log`.

## Original criteria disposition and limits

1. Draft/clarification/manual provider-neutral research remains technically MET from
   the original implementation and fresh review; F1 did not change it.
2. The executor now has native and exact installed-wheel evidence that the full shown
   ASCII/Unicode proposal bytes authorize activation and an openable first Work.
   This repairs the fresh-review blocker, but only a new HOME physical review can
   issue the binding close.
3. Durable continuation, truthful status/current rights, recovery/replay and installed
   evidence remain covered, and corrected installed evidence is now present. Fresh
   close and owner acceptance remain pending, so T2 is not claimed closed here.

No T3 safe definition/process evolution, replacement, rebinding or migration policy
was added. T4 still owns full fresh physical installed-reader synthesis and later
lifecycle proof. There was no provider/browser/account use, real research, real user
data, personal workspace, paid service, Direction mutation, CI change or push. HOME
must open another fresh physical reviewer after handback.

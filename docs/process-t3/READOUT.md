# Process creation T3 readout

T3 is implemented on verified T2 basis `3929b2242a000674d8e408b1f6518c5698b70661`.
The bounded implementation is commit `3c9db45f1518da617de7c72fb388c01eb69d4495`,
version 0.15.0. This is a technical candidate handback, not owner acceptance,
binding HOME G5, T4 synthesis, or a whole-product/domain release claim.

## Exact future-edition effect

`zaratustra.process_packs` now admits one explicit immutable `DefinitionTransition`
inside an exact runtime registration. It binds the original and proposed full
definitions, exact prior snapshot SHA-256, and exact current Work id. Admission
requires the same definition id, title, sources and capabilities, exactly the next
edition, byte-equivalent completed/current nodes, and the same current Work selection
when old results replay under the new edition. Changed started nodes, sources,
identity, skipped editions and changed history refuse.

The active Work continues under its original definition. Its accepted result stays
the original canonical snapshot bytes. Only when that Work's separately authorized
Core `submit_result` commits does the rule project preserved history into the approved
edition and specify the next Work. That Work inherits the exact existing Process/Work
`PackReference`; its requirements pin the new definition and projected basis digests.
There is no Core operation/schema/migration change, rebind, mutable latest lookup,
rewritten Artifact or alternate state graph.

## Reviewed, saved and recoverable stages

The installed `zaratustra.process_change` coordinator resolves the catalog row only
as a Process/initial-Work anchor, then follows verified committed Result links to the
actual tail Work. Timestamps and T2's pinned first-Work designation never select a
continuation.

An authorized current Core context supplies the exact effective basis. The readable
UTF-8 preview includes full old/new definitions, exact path/value diffs, the current
Work and unchanged-current statement, old/new projected next Work, revision, Pack
reference, snapshot/digests, and the explicit fact that review/approval has no Core
effect. Stages are truthful:

- `review_pending`: the understandable preview/edition are saved for another chat,
  but no decision or Core effect exists;
- `rejected`: an exact preview-bound rejection is retained; Core is unchanged;
- `pending`: exact preview-bound approval is retained as intent only;
- `planned`: authorized current Result context produced one saved exact Core Result
  request with fixed operation/Work/Artifact identities;
- `applied`: that exact operation and receipt exist in verified Core history.

The saved-review query/resume API rebuilds the same preview in a later trusted chat.
The continuation query grants nothing. Apply requires separate authorization bound to
the complete Core Result request. Lost-reply/restart recovery returns the same receipt
only with that exact request right and creates no second effect. A new reviewed change
is allowed after the prior effect; a genuinely pending one blocks competitors.

Effective bases after a transition are reconstructed from the unchanged inherited
accepted snapshot plus the exact transition whose Result receipt is in Core history.
The reconstruction must hash to the Work's pinned basis requirement. Thus later
review requires no previous-Artifact rewrite. HOME's note is retained intact at
`docs/process-t3/STEER.md`; its regression covers a mutated continuation, two completed
change effects, reconstructed edition-2/3 bases, and a third saved review.

## Preservation, authority and refusal evidence

Tests cover both fictional inputs and same-invariant siblings: approve/reject, saved
review resume, missing/wrong context rights, missing mutation rights, stale preview/
request, wrong definition id, skipped edition, changed current node, replay, current
lineage mutation and repeated later changes. The coordinator never imports the trusted
adapter or fixtures. Its journal is non-authoritative; all managed effects use public
Core operations.

Final native log `_scratch/process-t3-gates-02/full-check.log`: 120 formatted files,
Ruff, strict mypy over 104 sources, 17/17 import contracts, 360 tests in 137.90 seconds,
and both 0.15.0 artifacts. The basis-to-candidate diff is empty for Core and the two
original fixtures. Retained SHA-256 values:

- small fixture: `1ba23582df8a8ed4fd215cc8988d68f106a2fcfbc3379a5dc9d2f19719f45ce8`;
- project fixture: `c9762ddf484aa534d3d34e9bfe254338522b1f63ed8004ec4c630776c3e33a4d`;
- Core migrations: `e02eabf89c1e5692587cd945f686b45bffc54971f79339d13923c9a2c13f66b4`;
- migration v7: `0d68fedc52de5439fbe619a8fed45bb9c4e005ce8234d6b8e91c3496d53c7130`.

## Exact installed-wheel lifecycle

`_scratch/process-t3-installed-01/verification.json` records implementation commit
`3c9db45f1518da617de7c72fb388c01eb69d4495` and wheel SHA-256
`2e05915bd42060753a4a9b51a95cb5a58c0c8a75623ad53c8abb6ff88566e3c3`.
The isolated Python 3.13.7 `-I` harness first proved tests/tools absent, then explicitly
exposed both external fixtures. Every loaded product origin is under wheel
`site-packages`, recorded in `product-module-paths.json` there.

Small preview SHA-256 is `c395f5ce7909872bcd1ceda55ad432a665e325772e65b51b8760957a9ed8f327`.
Definition `2aa4357f...4d51` became `fe47a7a7...66e0`; starting snapshot
`c6ed4d81...7299` and accepted edition-1 Result `9e1c3956...50bf` survived.
Revision 9→10 used operation `c32f40b6-fc48-4f63-abc3-a67d7aac4c38`, event
`d4386cfb-6018-4324-8bd8-eb05d1736672`; the new Work is the edition-2 review.
Authorized replay stayed revision 10.

Project preview SHA-256 is `ab7eeea53881b2bf6d2096298cb40d52870000affdcbce350564f8a7f9af5da1`.
Definition `38fdcc9e...dde0` became `f0b1bb1f...52e1`; starting snapshot
`74a0e57b...db06` and edition-1 Result `a50c11db...fab7` survived. Revision 9→10
used operation `c497e03b-5db1-4f5c-87bf-e3eceacaa7dc`, event
`91e2f239-15bd-45c7-9a3b-7415386f8aef`; the new Work has the edition-2
research-review meaning. Authorized replay stayed revision 10.

Both summaries, exact before/after definitions, Pack bytes, snapshots, requests,
receipts and full ZIP/file manifests are under
`_scratch/process-t3-installed-01/{small,project}`. Rejection/approval changed no Core
database bytes. Pre-effect manifests contain both initial and edition-1 Result
artifacts; post-effect manifests retain identical hashes and add only Result/next-Work
state plus projection. Pack-byte hashes remain `9d074c14...2d68` (small) and
`67bfc48e...a6870` (project).

The required report-aware `uv run --locked python -m tools.check --deliver` also
exited 0: the same 120/104/17 surface, 360 tests in 123.55 seconds, both artifacts,
and `report structure` passed. Full log:
`_scratch/process-t3-gates-03/deliver.log`. This required delivery pass is not a
second independent binding review.

## Honest limits

Fixtures and derived modifications are technical development data, not personal
workflow choices. Test/probe local-chat confirmations are simulated trusted calls,
not real owner manual acceptance. No human research, provider/browser/account call,
paid service, personal installation, old/private Direction source, other checkout,
real data, SQL/state edit, Core/migration change, CI/integration, GUI, push or main
update occurred. T4 owns the complete installed-path/new-reader synthesis and later
Direction review. HOME still owes a fresh binding refutation of this exact candidate.

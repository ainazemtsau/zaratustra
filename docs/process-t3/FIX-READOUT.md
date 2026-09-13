# Process creation T3 correction R1 readout

Correction R1 starts from failed candidate
`2189f3c2ca5c484048200db8e0ded3d42100a3bb`. The bounded 0.15.1 implementation
is commit `61cef42275577927a71d92d8aa6e4a628131013a`. This is a technical handback,
not owner acceptance, binding HOME G5, T3 closure or authorization to launch T4.
The evidence-bearing report commit is
`6fa183869702945c7d6f5208a65e6da032aad032`.

## Corrected invariant

`edition_transition` now rejects an edition increment whose node definitions are
unchanged as `no_change`. It also projects completion of the exact bound current
occurrence and rejects `no_future_work` when the proposed definition would leave no
selectable next Work. These checks happen before a review journal can be saved and
are repeated by the existing runtime transition check before Core can construct a
Result request. The current/completed nodes, accepted data, source snapshot,
immutable Process/Work Pack reference and exact confirmation path are unchanged.

The rule does not require the immediately next Work's meaning to differ. A product-
API regression changes only the later third project node: review/approval/apply
succeeds, the immediate second Work retains its old goal and receives the approved
definition digest, and a subsequent attempt at that ordinarily mutated Work to
remove its sole future node refuses without changing records or the applied stage.

The journal reader recognizes both invalid preview shapes produced by 0.15.0 as
`saved_change_unsupported`; it does not delete, edit, reinterpret or apply them.
Read-only analysis of the retained reviewer workspaces records every file hash before
and after as identical in
`_scratch/process-t3-r1-saved-invalid/analysis.json`. The old edition-only workspace
already contains the failed candidate's authoritative Core event and remains an
unsupported continuation basis; this correction does not undo it. The old no-future
approval remains retained but unusable. No recovery or migration policy was added.

## Fresh behavior and preservation

The focused product surface passes 40 tests. Coverage includes both reviewer cases,
edition-only small/project siblings, initial and later-current no-future siblings,
runtime revalidation of retained invalid transitions, the legitimate later-future
change, both prior valid semantic paths, rejection, stale/wrong/missing rights,
mutable lineage, multiple editions, exact Unicode actor/source confirmation, restart
and receipt replay.

The required full native gate at implementation commit passed: 120 formatted files,
Ruff, strict mypy over 104 sources, 17/17 import contracts, 371 tests in 122.80s,
and 0.15.1 wheel/sdist. Log
`_scratch/process-t3-r1-gates/full-check.log`, SHA-256
`63d29faeeff3310b2ec3d68a64435da9ba70bf3706dae34e0fef00d908e9112e`.
Core and the original external process-creation fixture bytes have an empty diff from
the failed starting candidate.

## Corrected installed-wheel proof

`_scratch/process-t3-r1-installed-01/verification.json` binds source commit
`61cef42275577927a71d92d8aa6e4a628131013a` to wheel
`zaratustra-0.15.1-py3-none-any.whl`, SHA-256
`34b8a3889ceb741fbc5f7576558751c7b85a1f678aad41731b3c61a2b76bb7f5`.
Python 3.13.7 `-I` first proved `tests` and `tools` absent, then explicitly exposed
the existing development fixtures. All 29 loaded `zaratustra.*` modules resolve
under that venv's `Lib/site-packages/zaratustra`; exact origins are in
`product-module-paths.json` (SHA-256
`742db1248dd35d8199e8517f9aee852092047d5f93d5fdafa96cd439a66832bb`).

The installed correction summary (SHA-256
`a212ce69b5009763a27b7943c28c99f0344d89b67edd4ef55b2901ebd7aaf4a5`)
records `no_change` for edition-only small and project proposals, and
`no_future_work` for the project proposal that drops untouched future nodes. Each
has identical before/after Core database and records, with no review or approval
saved.

Both valid installed lifecycles also remain exact. Small preview
`a5de4051...62f8` preserves initial snapshot `4c719f3e...3e29`, accepted Result
`ea7c1431...de7a` and Pack bytes `55812033...75b2`; operation
`92191cf9-9083-4e9c-92da-3fe74acb2a39` advances revision 9 to 10 and replay stays
10. Project preview `b2da96ee...ccf1` preserves initial snapshot
`c7656b8d...e795`, accepted Result `27549848...9a7f` and Pack bytes
`cc3e2930...ec47`; operation `0cec491b-3b57-4662-894f-28911ef8ec1e` advances
revision 9 to 10 and replay stays 10. Full before/effect/after ZIP manifests,
definitions, requests and receipts are retained below that installed-proof path.
The synthetic Unicode confirmations are exact technical evidence, not owner words.

Installed log `_scratch/process-t3-r1-gates/installed-wheel.log`, SHA-256
`1123eb11e0e511a9969b14d09c46ea1e3c5de05bcd7ac3cd3c353a63e428798a`.
The distinct required `uv run --locked python -m tools.check --deliver` also exits
0: the same 120/104/17 surface, 371 tests in 136.90s, both 0.15.1 artifacts and
`report structure` pass. Log `_scratch/process-t3-r1-gates/deliver.log`, SHA-256
`a76ecde1de2aabec00565d55caf672acd36e5c848450a6144e7685f883eb6239`.

## Preserved failure and limits

The first fresh FAIL remains byte-exact: `REPORT.md` SHA-256
`0d27b9c1f446b41d7f5da1321f13346af6b9a7261c70e0042a135ae97fc3af38`,
`refutations.json` `3ab4fa9018880c67f60d3eb7d63396e118177de8bb713b7fe9462f6d1056b5a2`,
and `refute_installed.py` `ee71c9d007d45b398636b31914fed6a5fd7e508ab5fca8e8445bd6cf3d1cd544`.
The read-only legacy analysis is SHA-256
`e4c2d7ccd3be6edd4ee09673246ebd5981722d09bfe38b01fe2415eb378bf1e3`.

No Core terminal lifecycle, migration, mutable latest/rebinding, current/completed
node edit, fixture edit, managed-state rewrite, arbitrary cleanup or recovery policy
was added. No personal installation, actual data, other checkout, Direction OS,
provider/browser/account/service, paid service, CI, push, main update or T4 launch
occurred. Manual acceptance and fresh physical binding review remain pending;
next is `solmax`.

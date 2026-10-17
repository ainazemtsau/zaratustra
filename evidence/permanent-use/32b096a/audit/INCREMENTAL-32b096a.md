# Incremental codec publication audit 32b096a — privacy/source/package PASS

Exact committed range `bc95ceb412210e5bb8355e60cdff537088fdf25a..32b096a474f36fb55a6296110261e6a67d6981a4`: one commit, six new blobs, 86,568 bytes. Full committed bytes and source/document diff inspected. Scope is the native source-data codec/presentation extension, documentation and fictional SDK/presentation tests. No mutable checkout product source was read for alignment; successor work remains outside this audit.

No concrete credential/private-personal-data blocker found. Changed committed/package text and five freeze/map metadata files scanned: no private-key/API-key/GitHub/AWS/JWT or personal-data path/email matches. The sole generic credential-field match is the explicit fictional-localhost-only test key. No user Activity, auth file, owner credential, Core DB or private capture in the exact immutable package inventory. Source decoding implementation/test literals are code, not uploaded live data.

Immutable `delivery/zaratustra-pi-0.2.0-32b096a/`:
- Exactly nine files; every source-manifest hash/source_commit matches. ZIP contains exactly nine members, all byte-identical to durable files.
- ZIP exactly 100,775 bytes, SHA256 `011eb1314d90e052aaf1fc83dfe676be195aeca70efadf67a508368fa9f2a566`.
- Independently computed tree SHA256 `1790eb131d3c1d2635ca2e2dbee350f094be246eb842f489dc70346f9059fdde` matches supplied TREE metadata (relative path UTF-8 + NUL + raw bytes, locale-compatible ASCII order).
- Extension SHA256 `5c35a58862d5248142f9ac9fd4dda350011373f0f0b7ab13802ef1b5618d8658`; extension and README match pinned Git content after CR newline normalization.
- Exactly extension.ts/README.md differ from bc95. Both wheels and bootstrap unchanged byte-for-byte: Core `3993806a9c92bd8450db328641ac95bbdd53549cd7388ff4b6a762cb5c1b2372`, app `55a9150a4e285992b4004089bc077849f6a313b41b6b8d688a2011d410effb67`. Prior code-only privacy inspection carries forward; unchanged contents not rescanned.

Frozen source reconciliation independently verified against COMMITTED Git objects and immutable package bytes:
- All 59 source paths, committed blob OIDs/SHA256/sizes, frozen hashes and map entries align. Exactly 44 raw-identical, 15 CRLF-only, zero other differences.
- Fourteen CRLF-only frozen hashes/sizes were independently reconstructed from the exact committed LF blobs. One mixed-newline bootstrap was checked against its already-frozen immutable package bytes and CR-normalized committed blob. No current working source hashes used.
- All nine frozen package hashes match. ARCHIVE source/hash/size, TREE digest and COMPONENT seven-unchanged/two-changed lists independently match observations. All 103 package/freeze/map/hash checks pass; final immutable metadata/package readback stable.

Metadata SHA256:
- FREEZE.json: `37446dcf4ee7739db07138041fb4ea04fe022d65ac67c562ad2b8583c2e98798`.
- SOURCE-BYTE-PROVENANCE.json: `80cdcffe61a7f125443c10f91a7daba15dc8d125f0fe35dc7f7f573f29a72731`.
- ARCHIVE.json: `caa49fb357130f7fd5c516544018e12c60e6adec89b4d7c7002ef8da37697bc8`.
- COMPONENT-ALIGNMENT.json: `e9d682f460af6a27676aaf6061b258e3f11714ad133657e48856e762b1e097b4`.
- TREE.json: `fa4a0abfe938b79325c684fe5b73dfd2b96c7829fcac5d192391628b9711a001`.

Boundary: PASS supports public source/package preservation only. Product readiness remains NOT_READY; no technical/live/gate/owner-acceptance or main/release verdict. New curated docs/evidence are excluded and need their own delta audit. No mutable checkout source alignment, actual auth/DB/raw trace/all-scratch/archive reads, model calls, source/index edits, commit or push. Wrote only this audit scratch directory. Heuristic scans cannot prove absence of every possible opaque secret.

Reproduction: incremental-32b.py, freeze-32b.py. Exact per-file/source-map metadata: incremental-32b096a.json.

# Actual-live sanitized subset v2 — privacy PASS

Exact manifest: `_scratch/root-native-live-proof-envelopefix/public-evidence-v2/subset-manifest.json`, SHA256 `4d0e98a9faadcbde8e450ecb51ceee96cc34d46ee0fb4f84b817d3bf0f1b2a36` (2,079 bytes). Final manifest readback stable.

| Selected file | Bytes | SHA256 |
|---|---:|---|
| 158617f-descriptor.json | 1,770 | 4b1c8aa11917d3fbe6c8554b1462b641c33512d8e6ff402d53583aed0bfc8346 |
| 158617f-selected-records.jsonl | 14,288 | 33294c1208bf3b6635dda3ff95122ccfa6d9a379c06e35d037f0f2704443b060 |
| 32db2ac-descriptor.json | 1,891 | 604eeeb5f2824f7a7cf463a4551e00ccb179c6145446c104ccc242d6b90b4e6c |
| 32db2ac-selected-records.jsonl | 33,701 | bf9c76d989b0bd0a298768fbc0c549f97f0b532251f1a3f490b7678689174fe2 |
| provenance-selfcheck.json | 11,038 | 42549a0ce77f07f33b3540d636a5f0806b5961d5536f8f85f1574c6fa9a4a812 |

All five selected files total 62,688 bytes, matching every manifest hash/size. Exact directory inventory is the manifest plus these five files: no unlisted sidecar, missing file or extra raw capture.

No concrete credential/private-personal-data blocker found. Scanned all selected raw/nested JSON content; zero private-key/API-key/GitHub/AWS/JWT/generic credential-field/personal-data path/email matches. No encoded payload, database, owner credential, authentication content or giant raw trace included. All 43 records retain explicit projectionOnly=true and original-line-SHA/byte-count/sourcePointer qualifications; sourceRaw/sourceSummary remain marked published=false and owner acceptance pending.

Independent v1-to-v2 sanitized-file comparison confirms:
- V1 manifest and two selected JSONL files remain byte-identical to their previous audited hashes.
- Same 43 original-record identities, types, source line SHA/byte counts and projection qualifications; no new source pointers.
- Exactly six source pointers removed, together with exactly six corresponding null selected fields; no other selected-value changes. The removed fields are progressRevisionFingerprints, sameScopeResultFingerprints and absent errorMessage occurrences.
- Published selfcheck metadata covers exactly the same 43 file/line identities and 124 declared pointer counts; its SHA256 matches requested value. Added descriptors identify the correction and previous descriptor hashes. All 103 hash/inventory/delta/label checks pass.

Source semantic boundary: this audit did not open any giant original trace, source summary, ledger, database or auth file. The selfcheck claims that pointers resolve and original raw/line hashes match are author assertions here; root/reviewer independently verify them against source. Privacy PASS and internally consistent projection labels do not independently prove source semantic validity or product readiness.

Read only the v2 manifest-selected files and previously audited v1 selected baseline files/manifest to compare preservation. No new model calls, source/index edits or push; wrote only this audit scratch directory. Prior v1 report preserved. Later altered/curated copies require exact-hash/delta checks. Heuristic scans cannot prove absence of every possible opaque secret.

Reproduction: sanitized-live-subset-v2.py, sanitized-v2-delta.py. Exact file/delta metadata: sanitized-live-subset-v2.json.

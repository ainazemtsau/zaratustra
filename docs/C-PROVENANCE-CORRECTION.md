# Explicit correction of the exporter self-log provenance

Independent PARTIAL at 0d188eee found one mismatch in c-evidence/manifest.json:
export-06-console.txt declared an empty raw source (SHA256 e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855),
while the currently retained raw log contains 56 bytes. All 327 published derivative
hashes were independently confirmed. This does not rewrite those historical observations.

Preserved byte-for-byte from published 0d188eee:

- [Original manifest](c-evidence/history/manifest-0d188eee.json), SHA256
  faaf1bd4aace62e33a79e8f84dafa863917a7b4d76592c5d7793b17ed0774aac.
- Original published [empty derivative](c-evidence/export-06-console.txt), also copied
  to [history](c-evidence/history/export-06-console-0d188eee.txt).

**No separate empty raw snapshot was retained.** The empty published derivative exists;
it is not proof of an available immutable raw file of that version. The original
export command redirected stdout to export-06-console.txt while the exporter globbed
all root text files before printing completion. The current raw source is the completed
log; it has not been edited to match the old claim.

The corrected entry is explicitly versioned as a correction. Available raw snapshot:
56 bytes, SHA256 f47b203181d86fd3b0bb16fd238cc61d5d25c64d040937154321fe0f3ae5b00e.
A new frozen byte-for-byte raw copy is retained in the separate fix evidence directory.
Its [new derivative](c-evidence/corrections/export-06-console-completed.txt) has canonical
LF, 55 bytes, SHA256 45278501683385d62e9affeb0049853128bd6536ae7e1c047c98ed2e05447308.
The [current manifest](c-evidence/manifest.json) links this source/version and derivative,
retains the full original declared entry in provenance_corrections, and names the
unavailable historical raw snapshot. The original entry is not relabelled as corrected.

Future exports use scripts/export-evidence.mjs with an explicit sealed input list,
expected length/hash, new destination and current stdout path. Inputs are verified
before/after processing. No glob is used; ongoing stdout is refused even if sealed
while empty. Behavioral tests exercise a completed positive log, own-stdout rejection,
changed-source rejection, and derivative digests. No old raw log or closed budget is
modified. This is developer evidence tooling, not a product export/backup feature.

END_OF_FILE: docs/C-PROVENANCE-CORRECTION.md

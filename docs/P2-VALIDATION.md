# Two P2 corrections: implementation and observed validation

This is a bounded correction of the first installed Pi block after independent
review returned PARTIAL. It does not change the approved architecture, claim an
independent PASS, accept the result for the owner, or complete R1.

Baseline: `91ab52cfcfd53bfa7041b052468e2432d432b311`.
Published and normally installed execution candidate:
`7a1e409f64f0a85b3c9340286c6445f41a862fb4`, branch `codex/zaratustra-v1`.
The subsequent handoff contains documentation/evidence only; its exact remote and
installed SHA is returned in the executor handback. Reproduction always requires
the operator's explicitly chosen full SHA, never a branch/default historical pin.

## Corrected behavior

| Finding                                     | Before correction                                                                                             | Installed corrected candidate                                                                                                                                                   |
| ------------------------------------------- | ------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Denied import after native session.setModel | PERMISSION_DENIED after one watched source-content read, one staging UUID allocation, and a new material file | Core authorizeImport preflight returns PERMISSION_DENIED before source reads or UUID allocation; staging/material inventories and all domain tables unchanged; no source handle |
| Long observed original (8519 code points)   | Normal read truncated with continuation flag; range returned VALIDATION_ERROR                                 | Addressable retained_excerpt range returns the exact tail; full sequential reconstruction and original hash/history checks pass                                                 |
| Unicode boundary                            | Ordinary read split a non-BMP owl at UTF-16 index 8000                                                        | Ordinary truncation and ranges use Unicode code points; 7999 BMP characters plus a whole owl fit the first page; exactly 8000 non-BMP code points do not falsely truncate       |

Core owns authority. The adapter adds only the explicit preflight call before
importFile; the policy is not copied and no unrelated tool is called to authorize
an import. Source read and UUID spies use actual Node builtins with ESM exports
synchronized, a successful allowed-import positive control, and a real native Pi
SDK session.setModel. The alternate model is selected but never prompted. Every
mechanical probe records zero provider requests. Permitted BOM/CRLF/emoji bytes
are retained exactly, committed and read back through the actual extension tool.

The existing read API selects the requested record revision before choosing its
blob or retained excerpt. Core applies the same bounded code-point slicing and
continuation contract to both. Normal truncated output reports range_unit,
total_characters, has_more and next_start along with the existing flags. The input
bound and 8000-code-point output bound remain. No input shrink, unbounded output,
Evidence edit API, schema migration or custom parser was introduced. Revision tests
use an explicit synthetic two-version storage fixture, not an advertised edit tool.

## Neighboring adapter sites

The adapter was inspected in full. Input capture enters Core.capture, whose first
operation authorizes processing before byte measurement, hashing or handle
allocation. zara_read enters Core before reading retained material; catalog,
operation and snapshot reads likewise authorize before returning managed records.
zara_commit enters Core authorization before durable mutation. Doctor opens no
source material. Static bootstrap reading at module load is product instruction
loading; session startup reads workspace/lock/schema identity and integrity, not an
imported source. No second implemented personal-material pre-read site was found.
No broader provider-switch policy or OS isolation is claimed. The current design
still conservatively blocks on an observed model change and trusts one writer.

## Mechanical and installed checks

- Pre-fix SDK/Core reproduction retained both defects on the exact reviewed base.
- Range regression RED: 3 pass / 5 fail before the range fix; GREEN: 8/8 after it.
- Checkout npm run check: format, lint, types, dependency boundaries, build and
  18/18 tests passed. Candidate npm run deliver also passed.
- Native Pi 1.3.0 install from the real public exact SHA outside checkout passed;
  one product extension and both small skills were loaded. Platform: Windows 11
  x64 / Node 22.19.0; built-in node:sqlite disk storage, no fake model responses.
- Installed SDK corrected negatives passed; installed Core/P2 tests passed 17/17.
  They check authorization, actual retained/imported ranges, sequential originals,
  hash/history immutability, current/exact historical revision and invalid bounds.
- Normal Pi npm install changes installed package-lock.json by removing exactly
  nine peer:true metadata flags. All versions, integrity and other lock data match.
  Installed HEAD is the public SHA, but that lockfile is dirty. Source, manifest,
  instructions, skills, scripts and tests exactly match candidate-input-hashes.json.
  This exception is disclosed rather than claiming a byte-clean installed tree.
- Remote refs before/after candidate publication prove only the authorized branch
  advanced by normal push. Final refs/readback are retained separately after handoff.

The old builder/reviewer matrices were preserved; unrelated fault/lifecycle/model
scenarios were not rerun without a reason. Original specification and public copy
remain byte-identical to their declared SHA256 values in DEVELOPMENT.md.

## Actual live observations

Recipient `openai-codex/gpt-6.1-sol`, thinking medium, supported native Pi authPath;
credentials were never inspected, copied, printed or published. The shared finite
budget was recorded before the first request. Every attempt starts a new process
and in-memory session; startup messages were empty.

1. Create/save: model reads skills, inspects catalog, chooses zara_commit. Four
   connected records, four revisions, one Change and one receipt commit. Original
   Russian input is exact; Activity, waiting Work and preference are English.
   Work says no book was received/read. Save prose follows actual commit completion.
2. Continue: model discovers the waiting work from disk, asks for the book in Russian.
   This attempt changed SDK cwd but retained the launch process directory; it remains
   recorded and counted, with no strict OS-cwd claim based on it alone.
3. Continue again: OS process and SDK cwd both changed to cwd-b, empty transcript.
   The model again explains the actual wait without needing IDs/state reconstruction.
4. Tail: a declared synthetic controller first retains an 8604-code-point observed
   log through installed Core.capture/commit. It does not fake a model create path.
   The unique answer starts at code point 8529 and is absent from the new question,
   every snapshot, material cards and ordinary truncated read. In a fresh process
   from cwd-tail, the actual model chooses zara_map, materials browse, then zara_read
   ranges `{start:0,length:8000}` and `{start:8000,length:8000}`. The second result
   contains the original instruction. The original/hash are unchanged afterward.

Observed continuation (attempt 3):
“Сейчас нужен текст книги или первый фрагмент: пока ничего не получено и не прочитано.”

Observed tail response (attempt 4):
“По сохранённому журналу контрольный образец нужно оставить в янтарном шкафу, на четвёртой полке.”

Totals: 4/6 conversational attempts, 15/30 provider requests, 94558 input tokens
including 35200 cache-read, 1336 output tokens; Pi estimate USD 0.135596 / 5. No
live attempt failed or was discarded. The extra cwd attempt is included. Subscription
billing and executor cost are unknown. These are development-test limits only.

## Evidence, failures and remaining limits

[p2-evidence/manifest.json](p2-evidence/manifest.json) identifies original local and
public derivative digests. Raw originals remain in a new isolated root disclosed
in the handback; old builder/reviewer evidence was never edited. Public files are
sanitized synthetic technical observations. Path redaction and the omission of
provider thinking/signatures are explicit derivations, not fabricated quotations.
Actual tool arguments/results, request snapshots, receipts and final text remain.
The baseline driver is preserved separately from the maintained corrected probe.

[P2-ATTEMPTS.md](P2-ATTEMPTS.md) records expected RED/negative outcomes, the additional
cwd attempt, command/helper failures and two failed evidence-export attempts. The
first export stopped on the installed lock metadata exception; the second caught
escaped private paths before publication. Their partial outputs remain local. The
third export passes path/JSON/digest validation. No credentials were export inputs.
[P2-DEPENDENCIES.md](P2-DEPENDENCIES.md) records the still-open high braces advisory
in dev tooling; no general security PASS or dependency update is claimed.

[REPRODUCE.md](REPRODUCE.md) gives exact-SHA install, regression and live commands.
A separate fresh reviewer should refute read ordering using its positive control,
Unicode/revision/history guarantees, installed identity (including the lock metadata
exception), fresh-process continuation, actual tail range calls and answer absence
from earlier representations. Choose an independent case and inspect public hygiene.
That review has not run for this correction. Owner acceptance is pending.

Full R1 obligations remain in the complete specification and R1-STATUS.md: nested
Work/dependencies/partial waits, other kinds, richer retrieval/corrections, managed
effects/approvals, backup/restore/epoch/archive/deletion, full provider/access and
scale qualification, PDF/EPUB. Codex integration and separate R2 Sleep are unbuilt.
Known first-block limits (one trusted writer, 1 MiB UTF-8 material, possible orphan
blobs, no OS isolation/power-loss or arbitrary-shell deduplication guarantee) remain.

END_OF_FILE: docs/P2-VALIDATION.md

# Approved outcome C: full Work and materials

The current owner assignment explicitly replaces the old first-block-only scope with
specification §25.8 outcome C, approved with “ок”: implementation, checks and ordinary
pushes solely to `codex/zaratustra-v1`. No subagents/chats. Independent review is separate.
The accepted base is `27a74fdb9e7bd826f07a9c9f1e2e3775d54f5c1f`: independent first-block
PASS followed by the owner's separate “да”, as recorded in this assignment. This accepts
that first block only, not full R1 or T31. The previous [RESULT](FIRST-BLOCK-RESULT.md),
[decisions](FIRST-BLOCK-DEVELOPMENT.md), P2 documents and evidence remain historical.

The complete [specification](specification-v1.1.html) is unchanged. Verified original
SHA256 `7d3bd88d71dd954949ad33caae38859f9e06c460b8537ed3259780d11668fac4`;
public derivative `4940e16e39174df941da98889c43b713c48287d4aeda8754fd57660d462a77cb`.
The derivative only redacts the original-1.0 local path. No old product branch is a basis.

## Retained profile

Windows 11 x64, Node 22.19.0, npm 11.6.2, Pi 1.3.0; TypeScript, node:sqlite/WAL, short
transactions, portable Core without Pi SDK types, one extension and two small English
skills. Pi/model own semantics, planning, language and context selection. User interaction
is conversation only. Personal trusted installation, one writer; no automatic routing.
The existing conservative provider-switch denial remains. No credentials are read/copied.

## Necessary mechanisms and considered alternatives

| Addition                                  | Guarantee and simpler alternative considered                                                                                                                                                                                               | Boundary/removal                                                                                                                                                                                                            |
| ----------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Work schemas and whole final-graph checks | SQLite JSON and prompts do not reject cycles, invalid dependency/parent links or missing formal grounds. Zod validates shapes; small domain code validates the graph, lifecycle and required children. Model judges semantic fit.          | Guarded Core transactions; no custom planner/DSL. Preserved revisions keep former completion/cancellation.                                                                                                                  |
| Execution claims                          | Writer lease prevents a second process writer, but cannot bind a model's action to Work revision, step, session, runtime, epoch, ancestor revisions and operation token across thinking time. Native SQLite serializes claim changes.      | Only local step/result recording, Work completion and handoff preparation. 15-minute expiry never proves non-execution; unresolved claims require release/reconciliation. No external execution guarantee.                  |
| Immutable handoff row and reply Evidence  | Plain chat cannot retain the exact prepared Work/ancestor plan versions across restart or compare a late reply. Reuse Core IDs, refs, Changes and receipts; no messaging service.                                                          | Preparation is not send/execution. Replies retain original/current plan comparison, transport separate from external authorship. Content/hash equality does not merge events.                                               |
| Original plus text Evidence               | A binary blob is not addressable extracted text. Separate immutable blobs/Evidence link exact source digest, parser version, limitations and section offsets. Existing range API is reused.                                                | Original bytes unchanged. No OCR, DOCX or general HTML import. Unsupported input can remain opaque.                                                                                                                         |
| Bounded parser worker                     | Synchronous PDF/ZIP parsing can block Pi and a malicious book can expand excessively. Reuse Node workers/resourceLimits and pinned parser libraries, rather than a new service or hand-written document parsers.                           | Data only; no source path in worker, no fetch, PDF eval/WASM/system-font loading disabled, ZIP never extracted to filesystem. Abort on runtime/provider change; reauthorize after await before material/handle publication. |
| Schema-1→2 migration                      | Old code must reject changed semantics, and a failed upgrade must retain the old data. Keeping schema 1 would permit old writers. Reuse SQLite VACUUM INTO for a consistent pre-migration database, then one DDL/meta/receipt transaction. | Exclusive writer, verify refs/material hashes first; old records/revisions/Changes/receipts untouched. Narrow interrupted-manifest repair requires the exact migration receipt. No general backup/restore product yet.      |

## Parsers, dependencies and limits

Runtime additions: `pdfjs-dist@6.4.299` (Apache-2.0), `yauzl@3.4.0` (MIT),
`htmlparser2@12.0.0` (MIT). PDF.js reads data buffers only; yauzl uses lazy entries and
validated lengths, with Node CRC32 verification; htmlparser2 extracts EPUB container,
package reading order and XHTML text without entity resolution/execution. Standalone
HTML is opaque. Existing `zod@4.1.12` remains MIT. Pi/TypeBox are host peers.
PDF.js optional canvas packages are transitively installed by npm; rendering is unused.
The package lock pins the actual resolved dependencies. Audit evidence is reported in
[C-VALIDATION](C-VALIDATION.md); the old braces advisory remains a separate open issue.

Limits: TXT/Markdown 1 MiB original, PDF/EPUB 64 MiB original; 2000 pages/chapters,
10000 ZIP entries, 16 MiB per expanded ZIP entry, 128 MiB total expansion, 8,000,000
Unicode code points of extracted text, 45 seconds per worker, 256 MiB worker old heap.
The heap limit is not an OS memory sandbox. Truncated text is partial with unavailable
sections; encrypted/damaged/scanned-or-blank/unsupported/limit outcomes are explicit.
Blank PDF pages cannot be distinguished reliably from scanned pages without OCR.
EPUB UTF-8 and BOM-marked UTF-16 XML are decoded; missing/unsupported sections remain
visible. Text order is the parser's reading order; complex layouts, images, equations and
interactive content are not promised faithful. Original files remain inspectable bytes.

Global and section-relative ranges are half-open Unicode code-point intervals, never
UTF-16 code units or byte offsets. With locator, continuation uses section-relative
next_start; global_start/global_next_start also identify the derivative positions.
No time scheduler: waits preserve due_at with offset and required IANA timezone.

## State and scope

Schema 2 adds claims, handoffs and migration receipts, leaving existing domain rows intact.
Backup files stay under the separate home and are not automatically deleted. Missing/corrupt
stores never create replacement empty databases. Failed imports can leave orphan staging/
immutable blobs; garbage collection and full user backup/quarantine restore remain stage E.
Fsync/readback are not a hardware power-loss guarantee. Managed policy is not OS isolation
from same-account shell/extensions or adversarial outside filesystem writers.

Outcome D shared memory/Concept/Entity/FTS is the first unimplemented outcome. Methods,
Runs/Evaluations/Signals, universal approvals/effects, general backup/restore/archive,
Codex and Sleep remain later. Full R1 matrix is retained in R1-STATUS.md.

END_OF_FILE: docs/DEVELOPMENT.md

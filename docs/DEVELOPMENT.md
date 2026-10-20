# Approved outcome E1: Methods and experience

The owner assigned E1 implementation, verification and public delivery from accepted D
`1b742a6e774eaa14826c036977ae2a42ff1ca46a`, solely to `codex/zaratustra-v1`.
His “принимаю” approves the E1 scope, not its future result. D was independently
scope-qualified PASS and separately accepted. The independent large D review was mechanical;
its own live scenarios were small. Those limits remain. One executor; no agents/other chats.
Direction OS is untouched. Full E, R1 and actual-owner trial T31 remain open.

Before changes the complete unchanged specification and D handoff were read. Original
SHA256 `7d3bd88d71dd954949ad33caae38859f9e06c460b8537ed3259780d11668fac4`;
public derivative `4940e16e39174df941da98889c43b713c48287d4aeda8754fd57660d462a77cb`.
Previous current documents are preserved byte-for-byte in D-RESULT-1b742a6.md,
D-DEVELOPMENT-1b742a6.md and D-R1-STATUS-1b742a6.md. Historical evidence stays frozen.

E1 implements specification §§4.7–4.8, 5.2–5.3 and 11: canonical textual Methods,
exact selected dependency closures, meaningful Runs, separate addressed Evaluations and
Signals/reviews. Schema 4 reuses Core/StoragePort, guarded short transactions, version
history, receipts, Changes, FTS and managed scopes. Model/Pi own applicability, composition,
execution and interpretation. No Method runtime, workflow language or second model.
See [E1-DESIGN](E1-DESIGN.md) for each mechanism and its finite limits. Actual M/L
qualification is recorded in E1-VALIDATION.md, with reproduction in E1-REPRODUCE.md.

One new E1 ledger, never reset: 24 conversational attempts / 180 actual provider dispatch
attempts / USD 15 Pi estimate; stop at the first cap. It includes errors and incomplete
attempts. Selected `openai-codex/gpt-6.1-sol`, medium, native Pi auth/authPath only.
The synthetic RPC controller is programmatic, never Anton or T31. Mechanical SDK
interactive-source tests are separately labelled M, with zero provider requests.

Default scopes are workspace-only. A separate protected profile explicitly supplies
`restricted:read`/`restricted:write` before its history starts. Do not raise rights during
a failing history and claim the old profile passed. Owner feedback additionally needs
trusted setup `ZARATUSTRA_INTERACTIVE_INPUT_CONTRACT=first-untransformed`: the local Pi
owner channel with this hook preceding transforming handlers. Without that deployment
assertion the observed stage is retained but original input is unknown. Quotations,
external/agent reports and programmatic inputs cannot acquire owner origin through tool
arguments. This is a trusted personal deployment contract, not biometric identity or
protection from malicious same-process extensions. Exact action approvals remain E2.

## Retained profile

Windows 11 x64, Node 22.19.0, npm 11.6.2, Pi 1.3.0; TypeScript, node:sqlite/WAL, short
transactions, portable Core without Pi SDK types, one extension and two English
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
Image-only/blank EPUB chapters are unavailable; all-blank books use scanned and mixed
books partial. This classifier does not prove that an image came from scanning.
EPUB UTF-8 and BOM-marked UTF-16 XML are decoded; missing/unsupported sections remain
visible. Text order is the parser's reading order; complex layouts, images, equations and
interactive content are not promised faithful. Original files remain inspectable bytes.

Global and section-relative ranges are half-open Unicode code-point intervals, never
UTF-16 code units or byte offsets. With locator, continuation uses section-relative
next_start; global_start/global_next_start also identify the derivative positions.
No time scheduler: waits preserve due_at with offset and required IANA timezone.

## State and scope

The accepted schema-2 base added claims, handoffs and migration receipts. Accepted D
schema 3 added shared-memory indexes. Schema 4 retains canonical rows exactly and adds
supporting experience rows/versions and address views. A verified pre-schema-4 SQLite
copy precedes the atomic migration; the old D writer refuses schema 4.
Backup files stay under the separate home and are not automatically deleted. Missing/corrupt
stores never create replacement empty databases. Failed imports can leave orphan staging/
immutable blobs; garbage collection and full user backup/quarantine restore remain stage E.
Fsync/readback are not a hardware power-loss guarantee. Managed policy is not OS isolation
from same-account shell/extensions or adversarial outside filesystem writers.

E1 is the current authorized implementation. E2 is the next bounded outcome: exact
preview-bound confirmations and controlled actions/unknown-result recovery, including
managed textual SKILL.md export and drift checks. E3 retains user backup, quarantine
restore, retention/archive/delete and the restore epoch barrier. Real identity merges
and bulk reorganization await E2 authority. Codex and R2 Sleep/scheduler remain separate.
Full R1 matrix is retained in R1-STATUS.md; E1 does not close it.

END_OF_FILE: docs/DEVELOPMENT.md

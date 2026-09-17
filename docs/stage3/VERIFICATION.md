# Stage 3 verification — September 17, 2026

Baseline: a3e1c970bee97ef73c49084c1b940665d4bed4db. Local candidate: 0.21.0.
Product checks, personal hookup and owner acceptance are separate claims.

## Native checks

Final `uv run --locked python -m tools.check --deliver`: PASS. 485 tests passed
in 223.33 seconds; formatting, lint, strict types, 26 import contracts, source/wheel
build, hygiene and report structure passed. Log: evidence/native-gate.txt.
All 89 installed package files match the final source and wheel byte-for-byte;
see evidence/installed-bytes.json. Final document hygiene/report checks also passed.
The focused web suite has 12 tests covering free-form originals, paged capture,
replay, partial progress, crash recovery, exact attachments, concurrent edits,
scope, stale selected context, later approval sources, exports and registration.

GitHub tests use a controlled fake API: commit/tree/blob checks, pagination,
per-file failures and create-only publication/replay. These do not establish an
actual remote write or ChatGPT account-specific permission.

Earlier full gates passed before subsequent review/demo corrections. New code
changes justified the repeated gate. An initial environment-only Git ownership
failure was resolved with process-scoped safe.directory, without global config edits.

## Ordinary Pi walkthrough

Pi 0.85.1, openai-codex / gpt-5.6-terra, installed candidate wheel in a separate
runtime. tools.probe_stage3 created a new fictional Home with selected context
and one locally captured request: malformed JSON containing ordinary Russian prose.
No personal Home or data was used.

Each invocation started a fresh session. Prompts used ordinary names, no request
IDs or technical operations. The generated extension was selected explicitly with
--extension because the fixture lives in ignored _scratch. This is not fresh
autoload verification.

1. Process the already received request without fetching GitHub or developing.
   Pi stored a backlog proposal, asked for the missing report and kept the request
   open. Two stale-context attempts were refused; Pi reread and recovered.
2. In a new chat, supply the named report and finish the understood instructions.
   Pi used web.attach, updated progress and completed the request. One omitted
   review reason caused a refused call and corrected retry.
3. A further fresh chat opened original, context, proposal and report. It reported
   zero unfinished requests and no current development work.

Independent public-API evidence: evidence/pi-verification.json. One request,
zero pending, completed; original hash unchanged; supplied/saved report SHA-256
both `700601db4251fd978a4867af3d7601870a887b916519e54a786815b4c88dcd41`.
evidence/pi-first.jsonl, pi-second.jsonl and pi-third.jsonl retain tool calls,
results and visible replies, excluding internal reasoning.

## Failed trial and correction

Before web.attach, Pi reconstructed the report text while saving. Its final reply
claimed success, but independent comparison found different bytes. The original
trace and comparison remain in evidence/pi-before-attachment-fix.jsonl and
evidence/pi-before-attachment-fix-verification.json. That trial is not passing evidence.

The dedicated file operation now reads exact bytes, pins revision 1 and recovers
interrupted binding. Review cannot substitute or clear received sources. Tests cover
CRLF/binary bytes, retries after completion, changed-file refusal, and concurrent
revision before binding. A new fictional Home passed the corrected Pi scenario and
independent byte comparison. An earlier extension-less invocation was an invalid
harness attempt: the agent could not call the product.

## Review, limitations and next boundary

One bounded in-session read-only evaluator reviewed setup and changed paths;
concrete findings were corrected with regressions. This is not fresh Direction G5
or owner acceptance. The legacy catalog concurrency observation remains OPEN and
UNFIXED: ../stage2b/OPEN-OBSERVATIONS.md and its retained original trace.

Semantic completeness, authorship and actual owner authority remain agent judgments;
code checks bytes, schemas, scope, references, versions and known delivery accounting.
The corrected tool retries are a usability/token-cost limitation. No endless full
run retries were launched for them.

The personal installation was not changed. Real ChatGPT → private GitHub → Pi
transfer remains a separate visible hookup check. No routing, paid service,
publication or Stage4 was started.

END_OF_FILE: docs/stage3/VERIFICATION.md

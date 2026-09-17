# 0.21.1 — ready instructions at first setup

## Defect and cause

The owner asked Pi to set up a ChatGPT Project and provide the Project instructions.
Pi instead required publication of an empty prepared packet. Version 0.21.0 had a
shipped template but exposed its rendering only inside web.publish. That operation
also returned file metadata rather than the ready text. The earlier Pi demonstration
started with a captured incoming request; it did not test initial setup. Its passing
result did not justify claiming that the first setup interaction had been verified.

## Correction

web.instructions reads the existing process/channel, fills the shipped template
and returns the complete instructions_text, connection requirement and check prompt.
It needs no prepared packet and performs no journal writes or GitHub calls. An
optional selected packet can be referenced. The template's source-file trailer is
excluded from the user-facing text. web.publish uses the same renderer and retains
its former outputs, adding instructions_text.

The shipped Pi guidance routes an ordinary setup request through this read operation,
uses configured/default branch values and presents the whole copyable text before
the next user step. No internal command incantation or empty packet is required.
Real reading and writing permissions in ChatGPT still require a separate account check.

## Verification scope

Common-command regression tests check rendering without a packet, with all GitHub
calls and journal writes prohibited, exact selected channel/branch, no changes to
Process revision and parity between preview text and published bytes.

The first actual fresh Pi setup attempt asked an unnecessary question about the
default branch. Guidance was corrected; its trace is retained separately. The
repeated setup starts with a new fictional Process and no configured channel,
prepared material or request. The user prompt contains only the process/repository
names and asks for ready Project instructions and one next step. No instruction
operation or technical workaround is named in the prompt.

## Results

The corrected fresh Pi invocation returned the entire filled template and one next
step: paste it into the ChatGPT Project. The public-API state contains only the
configured channel, with no packet/request. The trace has no web.prepare or
web.publish call. One stale-context tool attempt was refused and recovered; this
does not justify claiming zero tool friction. Evidence is retained under
evidence/0.21.1/: pi-first-setup.jsonl, setup-verification.json and the earlier
pi-before-default-guidance.jsonl.

Native delivery gate: PASS, 486 tests in 245.95 seconds, formatting/lint, strict
types, 26 import contracts, build, hygiene and report structure. See
evidence/0.21.1/native-gate.txt. Package bytes were compared with the installed
runtime and wheel. A bounded in-session read-only review found no blockers; it is
not fresh Direction G5 or owner acceptance.

This check does not establish a real ChatGPT/GitHub transfer or fix the previously
open catalog concurrency observation. Personal upgrade is checked separately for
unchanged existing data and dependency versions.

END_OF_FILE: docs/stage3/FIRST-SETUP-FIX.md

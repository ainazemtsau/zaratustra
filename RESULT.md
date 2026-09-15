# Trusted local-agent Process activation entry

## outcome

The installed `zara-agent` entry now has a closed two-step activation path for one
saved supported proposal. `activation-preview` renders the owner-readable Process
design, complete Work graph, selected target, aliases and observed workspace identity
without calling the mutating activation preparation API. It prints a digest retained
by the trusted assistant. After the owner agrees in ordinary conversation,
`activation-confirm` recomputes that exact read-only intent and refuses any change
before reusing the existing prepare, local authorization and execution APIs.

An explicitly selected initialized empty workspace is now a valid first-use target.
Its workspace identity is retained through migration and Process creation. Schema 2+
targets must have revision zero and no records; occupied, malformed or mismatched
workspaces still refuse. A fresh preview can resume the exact retained activation plan
after interruption or return the same completed Process and first Work.

## evidence

Focused trusted-chat and process-creation behavior passed with 28 tests before the
final delivery run. The tests invoke the shipped module in fresh `python -I` processes
with stdin disabled. They verify a byte-stable read-only preview, missing/wrong/changed
confirmation refusal before bootstrap, successful confirm and fresh selected read,
stable Process and first Work on replay, preservation of an initialized schema 1
workspace id, continuation after a retained partial activation, and byte-stable refusal
after replacement of an early reserved workspace. Existing occupied-target refusal
remains covered and unchanged.

The final native `uv run --python C:\Python313\python.exe --locked python -m
tools.check --deliver` passed with a task-local uv cache and pytest base temp: 150 files
formatted, Ruff clean, strict mypy clean over 129 files, all 19 import contracts kept,
436 tests passed, and wheel/source distributions built. A reader-only same-thread
reviewer identified the old mutating-prepare preview risk, partial-activation recovery
edge and early reserved-workspace replacement risk before the final patch, then passed
the bounded recheck. The implementation keeps preview read-only and admits occupied
state only when `inspect_process_creation` validates the matching retained activation
plan. This is an in-session pre-pass, not a binding fresh Direction G5.

## assumptions

This is a trusted single-user local application. The trusted assistant supplies actor
and source-reference provenance from the current host and owner message. The digest is
freshness binding for the exact displayed intent, not identity proof and never an
owner question. A new preview is required after target state changes, including after
completion or interruption.

## cuts

No automatic research, Process change, material intake, generic authorization command,
owner-authored JSON, host form, router, custom UI, Pi extension, private Solmax content,
provider account, updater or arbitrary workspace discovery was added. This bounded
result does not prove a real fresh model conversation or close the wider kernel/T4
outcome.

## cost

One extension to the existing common-agent entry, a narrow initialized-empty admission
in the current process-creation API, focused behavioral coverage, and updates to the
shared connection instructions and README. Existing dependencies and authorities only.

## manual-acceptance

The owner authorized this small common Python-core correction and requires the exact
Process and location to be shown before one ordinary conversational creation decision.
Automated and installed-process checks establish mechanics; a real owner chat remains
separate acceptance evidence.

## next

solmax

END_OF_FILE: RESULT.md

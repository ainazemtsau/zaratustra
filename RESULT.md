# Trusted local-agent core entry fix

## outcome

The installed product now ships `zara-agent`, a host-independent ordinary local-agent
entry with two closed commands. `read` resolves one explicit catalog and designation,
prepares the fresh Core Process-state query, and binds that exact query/revision to the
current owner-request provenance without requiring an MCP form. `draft` passes ordinary
title, need, outcome, constraint and clarification prose to the existing creation API.
The same draft is recovered by `read` in a later process invocation.

The entry exposes no activation, Process-change, material-intake or generic mutation
route. Those effects continue through the existing displayed proposal and genuine owner
decision paths. Standard connection instructions now route routine reads and prose
drafts to `zara-agent`, while retaining the existing confirmed path for effects.

## evidence

Focused trusted-chat behavioral tests passed: 12 tests. They run the entry through
fresh `python -I -m zaratustra.trusted_chat.agent` processes and cover exact UTF-8
Russian draft save, fresh-process recovery, idempotent repeat, an activated fictional
Process read with stdin disabled, missing-selection refusal before catalog access, and
absence of activation/change commands. They also cover a directory catalog with no
side effect, refusal to shadow a cataloged Process by designation or alias, and an
explicit conflict when an old retained journal already collides with that Process.
Existing accepted/refused MCP read, activation, material and explicit Process-change
reject tests remain green in the same file.

The final `uv run --locked python -m tools.check --deliver` passed: formatting, Ruff,
strict mypy, all 19 import contracts, 432 tests and wheel/sdist build. The only warning
was pytest's inability to write its optional cache under the managed sandbox; tests and
build completed successfully. The focused trusted-chat native check also passed with
12 tests and the same format/lint/type/boundary/build gates.

Independent installed-product probes outside this checkout reproduced the original
active Process case after the implementation patch: exit 0, stage `current_work`, Core
revision 7 and the exact selected Work id, without an approval form. They also verified
exact Russian save/restart/read, byte-stable read and repeat, missing-selection refusal,
no activation command, no legacy Process shadowing and explicit pre-existing conflict.
That is independent process evidence, not a fresh-model-chat proof or acceptance of the
wider T4 outcome.

A reader-only same-thread reviewer pre-pass reproduced the blank-catalog and legacy
Process-shadowing risks, then rechecked the installed correction: both refuse without
side effects, the original active selection remains readable, and a pre-existing
collision reports `selection_conflict`. This is not the binding fresh Direction G5.

## assumptions

This is a trusted single-user local application. Calling the closed `read` entry from a
host that received the owner's request is sufficient authority for that routine exact
read. Actor and source reference are provenance supplied by the host from the current
session/message; they are not proof tokens or extra questions for the owner. Draft prose
in the explicit command is the content the owner asked the trusted assistant to retain.

## cuts

No Pi extension, Solmax integration, updater, provider account, token, private data,
router, custom UI or host-attestation mechanism was added. The generic MCP `run` API and
its activation/change/material decision behavior were not widened. This bounded result
does not prove both Codex and Claude user interfaces or close the original wider T4.

## cost

One small installed entry module, one console-script declaration, focused behavioral
coverage, and updates to the shipped connection instructions and README. Locked existing
dependencies only; no external account or paid service.

## manual-acceptance

The owner authorized completing the existing Python engine first. Product checks and the
independent installed active-read probe establish code/process behavior. A real fresh
model chat using the final installed commit remains separate acceptance evidence.

## next

solmax

END_OF_FILE: RESULT.md

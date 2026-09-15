# Public onboarding R2 T4 — trusted local chat adapter ESCALATE

## outcome

The installed implementation began at `aff0ec6`, with refusal/material evidence at
`5380577` and the final general trusted-agent API in this correction. Shipped Codex
and Claude connections now
export a local stdio MCP server. Its `run` tool invokes the existing CLI application
under one temporary in-process `ConfirmationBackend`, so generic Core operations and
the existing activation, Process-change and material-intake confirmation surfaces
all use the same trusted-host boundary. `run_trusted` is the transport-neutral
application API: a trusted local host supplies its live owner-decision callback,
actor and owner-instruction source reference. MCP elicitation is an optional adapter.
The console remains the normal fallback.

Actual accepted headless-host evidence is not established. Fresh Codex and Claude
headless hosts both discovered and called the installed tool, but their host modes
returned an elicitation decline without displaying an owner-operable form. Core
therefore refused each protected read and reported current Work as unknown.

## evidence

Focused trusted_chat/connections/local check: PASS in 13.3 seconds; formatting,
Ruff, strict mypy, 19 boundaries, 11 tests and package build. The later correction
check passed in 11.3 seconds with six trusted-chat tests. It covers accepted and
declined exact reads, activation, material intake, explicit Process-change reject,
and rejection on a non-decision form. It also proves one authorized `run_trusted`
read with the exact supplied local-chat source reference and refusal when the live
callback says the owner instruction does not cover the request. The corrected rejection raises
`permission_denied`, never `UnboundLocalError`.

Installed/native probe:
`uv run --locked python -m tools.probe_public_onboarding_r2_t4 --output
_scratch/t4-trusted-chat-native-20260915-0435 --codex
C:/Users/Anton/AppData/Local/OpenAI/Codex/bin/bffc5354119c8421/codex.exe
--claude C:/Users/Anton/.local/bin/claude.exe`
passed in 26.6 seconds. It built and installed the wheel, exercised both command
contracts, and completed two fresh no-turn discovery passes per native host.

Fresh actual-host evidence is retained under
`_scratch/t4-trusted-chat-actual-20260915`. Codex 0.154.0-alpha.6.2 session PID
136724 ran for 90.7844 seconds. It loaded the shipped skill, called
`zaratustra.run` for the draft readiness/resume and protected readiness/resume.
The draft calls passed. Both protected calls returned exactly
`permission_denied: Trusted local agent permission was not granted`; readiness kept
Workspace unverified and Current Work unknown.

Claude Code 2.1.261 session `9f41bb84-521f-4a0f-b7ef-0ebf003ea5d2` loaded the
exported `.mcp.json` explicitly with `--strict-mcp-config --mcp-config <path>`.
Its init event records `mcp__zaratustra__run` and server status `connected`. Draft
readiness/resume passed; protected readiness/resume returned the same exact refusal
and unknown-current truth. The transcript records 49.230 seconds. The earlier
Claude preflight omitted `--mcp-config` under strict mode and truthfully reported no
MCP servers; it is not claimed as discovery evidence.

Neither run supplied or synthesized an elicitation response. Both exact shipped
configs and all fictional data hashes were retained before and after the sessions.

## assumptions

A trusted host's live callback becomes owner authority only when that host actually
received the owner's instruction or decision. MCP elicitation is one possible source
for that callback; it is not required. A headless host's automatic decline is a safe
refusal, not permission. The temporary runtime contains only fictional data.

## cuts

No T5/T6 work, push, publication, release, private data, paid service, alternate
authorization, serialized token, model-as-permission behavior, router or remote MCP
service was added. Successful first protected read, fresh re-read/continuation and
actual-host activation/change/material/Result confirmations remain unproven because
neither shipped headless adapter supplied a live owner-instruction callback.

## cost

Two implementation commits and this report update. Existing local tools and existing
host subscriptions only; no dependency or account change.

## manual-acceptance

The transport-neutral product seam is implemented and locally proven. Codex `exec`
and Claude `--print --permission-prompts host` connect to the stdio tool but
automatically decline its optional `elicitation/create` request. Those specific
headless adapters need to call `run_trusted` from a host-owned instruction/decision
event, or expose another genuine host callback; passing model text, a serialized
approval flag or a reusable token is not an acceptable substitute.

## next

solmax

END_OF_FILE: RESULT.md

# Public onboarding R2 T4 — trusted local chat adapter REPORT

## outcome

Implemented the accepted trusted-local-agent adapter at commit `aff0ec6`. A shipped
Codex or Claude project now exports its skill plus a local stdio MCP configuration.
The adapter runs the existing CLI application under a temporary in-process
`ConfirmationBackend`: every existing generic Core authorization and specialized
activation, Process-change, and material-intake confirmation uses a fresh host MCP
elicitation response to construct the existing local authorization object. The normal
CLI path remains the console confirmation fallback.

The adapter neither serializes authorization nor treats model text, MCP arguments,
files, saved state, or a previous response as permission. A rejected Process-change
form produces the existing explicit reject decision; cancellation and all other
declines refuse the operation.

## evidence

At `aff0ec6`, `uv run --locked python -m tools.check --deliver` passed: formatting,
Ruff, strict mypy across 128 source files, all 19 import-boundary contracts, and the
full pytest suite passed. Focused adapter evidence also passed: 13 tests cover
connection identity, accepted exact read, declined exact read, activation through the
same backend, and the MCP reject form.

An isolated fresh Codex CLI session loaded the exported skill, discovered
`zaratustra.run`, and made the exact fictional selected-Process tool call. Codex CLI
returned an elicitation decline, so the product truthfully returned
`permission_denied`, unverified workspace, and unknown current Work. No authorization
was bypassed. The host's automatic CLI decline does not establish an accepted desktop
Codex or Claude form interaction.

## assumptions

The owner-approved local-chat trust boundary applies only when the host actually
collects the owner's response through MCP elicitation. The retained temporary test
workspace contains only fictional fixture data. No remote publication, paid service,
account change, or user workspace access occurred.

## cuts

No T5/T6 work, release, publication, alternate permission path, remote router,
serialized authorization, or product state migration was added. The current actual
host proof is one correct refusal rather than accepted Codex and Claude desktop-form
evidence.

## cost

One implementation commit and one report update were made. Existing local tooling
and subscriptions were used; no dependency was added.

## manual-acceptance

Pending. Home needs accepted fresh Codex and Claude host-form interactions against
the isolated fictional selection before claiming that those hosts deliver the owner
permission path in practice. The automated Codex CLI proof is retained only as a
discovery-and-safe-refusal observation.

## next

solmax

END_OF_FILE: RESULT.md

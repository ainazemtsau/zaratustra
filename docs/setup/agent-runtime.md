# Agent runtime
Project-only Codex config keeps workspace-write, on-request approvals and no
network by default; actual managed runtime permissions take precedence.
Evaluator and investigator use read-only roles without a model override.
A narrow investigator prompt limits work; no unsupported cost guarantee.
Hard nevers and required command set are in AGENTS.md.

STOP/STEER are owner-created local files, ignored by Git and honored by the
check runner and written instructions. They are not an OS-wide interrupt.
No shell hooks, secret-reading helper or external notification sender is installed.
Codex's existing task completion UI is available, but no external push channel
was selected/authorized; needs-input/finished push-hook and test push are NOT verified.
CI is also unprovisioned (CALL authorizes local repo only).

Custom role files apply to sessions started with this project. A smoke helper
spawned from the current Direction task uses the exact evaluator instructions
in its prompt; this is not proof of auto-discovery after a product-task restart.
Source: https://developers.openai.com/codex/subagents/
END_OF_FILE: docs/setup/agent-runtime.md

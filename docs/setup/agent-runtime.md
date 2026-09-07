# Agent runtime
Project-only Codex config keeps workspace-write, on-request approvals and no
network by default; actual managed runtime permissions take precedence.
Evaluator and investigator use read-only roles without a model override.
A narrow investigator prompt limits work; no unsupported cost guarantee.
Hard nevers and required command set are in AGENTS.md.

STOP/STEER are owner-created local files, ignored by Git and honored by the
check runner and written instructions. They are not an OS-wide interrupt.
No shell hooks, secret-reading helper or external notification sender is installed.
Codex's existing task completion UI is available. The owner excluded external
push notifications, CI/CD and GitHub Actions until a separate request
(OWNER-DECISION-20260907.md). They are unconfigured and are not setup/delivery
requirements; do not request permission to install them again without new owner intent.
Public GitHub hosting remains future work.

Custom role files apply to sessions started with this project. A smoke helper
spawned from the current Direction task uses the exact evaluator instructions
in its prompt; this is not proof of auto-discovery after a product-task restart.
Source: https://developers.openai.com/codex/subagents/
END_OF_FILE: docs/setup/agent-runtime.md

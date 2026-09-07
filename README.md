# Zaratustra

Local development scaffold for the accepted M0 plan. Product commands arrive
through Works 1–8; this version cannot initialize or mutate a workspace.

Requires uv and managed Python 3.13.7. From this repository:

| Step | Windows PowerShell / other shells |
|---|---|
| Prepare | `uv sync --locked` |
| Check and build | `uv run --locked python -m tools.check` |
| Focus a file | `uv run --locked python -m tools.check --files src/zaratustra/core/__init__.py` |
| Verify report and full check | `uv run --locked python -m tools.check --deliver` |
| Enable local commit guard | `git config core.hooksPath .githooks` |

The full check runs ruff formatting/lint, mypy, the complete dependency graph,
pytest and wheel/sdist build. A file selection still checks the complete graph;
it cannot replace full delivery evidence. Check logs: docs/setup/evidence/.

Development uses an editable package through uv. Packaging builds
`dist/zaratustra-0.0.0-py3-none-any.whl` with uv_build 0.8.22.
Setup tests its import in a separate temporary environment, outside the source tree.
This is an installation-mechanics probe, not the Work 1 product installation.

The product repository contains code; the user chooses a separate data workspace
when Work 1 is actually installed and exercised. No data folder is selected here.
No remote repository, CI account, publication, external notifier or cost is configured.
Windows was observed; macOS/Linux runtime support has not been verified.

Read docs/setup/SETUP.md for applicability and limitations, docs/setup/OPEN-AGENDA.md
before the next Work, and RESULT.md for the engineering handback to Solmax.
OpenSpec is initialized as native repo documents under openspec/; no Node CLI is required.

END_OF_FILE: README.md

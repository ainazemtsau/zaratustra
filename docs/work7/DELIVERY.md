# Work 7 delivery verification

Final source candidate: 5866a48c5f9d0f492ad55723120366ffe8f08921.
Accepted base: 2fa3111666139eef3ae699319444809fce563ead. Branch: codex/work7-result.
Evidence/docs delivery commit follows this candidate; the final HOME message
provides its exact id. No source, tests, tools or dependency changes follow the
source candidate.

Command: uv run --locked python -m tools.check --deliver.
Actual cwd: C:/projects/zaratustra/_scratch/work7-result.
Exit: 0; completed UTC: 2026-09-08T17:10:16.885507+00:00; total seconds: 31.101.
140 tests passed in 29.52s. Ruff formatting/lint, mypy (41 files), both import
boundaries, hygiene, wheel/sdist build and report structure all passed.
Raw evidence: evidence/native-deliver.json, .stdout and .stderr.
Native report gate checks structure, never truth or owner acceptance.

Rebuilt wheel SHA-256 equals the independently installed/restored wheel:
dada5424fdf899c7d78d62b97f7acbd9edece35bc2c322e65e877b3bb6db8b84.
Source diff is byte-identical to evidence/implementation.patch. Released migration
files1–5, validation.config, docs/work1–6 and prior tests are unchanged. Only the
new test_results.py appears in the test diff. Retained ZIP was reread: all 149
file hashes and 136 directory entries match its manifest.

Installed execution, actual console permissions, rollback/replay/lost-response,
byte repair, final Unicode-output repair and full restore evidence are described
in RESULT.md and INSTALL.md. Initial failed runs are preserved separately.
No broad test rerun is needed for the following evidence-only documentation edits.

Owner confirmed the fictional fixture only. Actual clean-chat understanding,
owner runtime acceptance and fresh physical G5 are absent. HOME: solmax.
This report does not close T6/CALL/M0 or authorize Work8.

END_OF_FILE: docs/work7/DELIVERY.md

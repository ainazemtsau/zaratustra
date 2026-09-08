# Work 6 setup evaluator smoke

Read-only in-session child: /root/setup_smoke, required by Product AGENTS §10.
Performed at initial Work 6 setup before implementation; not binding G5 or feature review.

Reported findings:
- Work 6 clean checkout, branch codex/work6-context, exact HEAD
  589861c4657f19763b0af4ab965bd84646eecb70.
- Work 5 clean checkout on the same accepted HEAD, branch codex/work5-handoff.
- STOP/STEER absent; Product AGENTS read; validation.config matches PROBA v36.
- .githooks configured, uv 0.8.22 available; documented commands match tools/check.py.
- Git global-ignore access warnings did not prevent inspection commands.
- No edits, mutations, feature review or full gates performed by this child.

Parent separately completed native/installed/restore checks. No provider identity gate.

END_OF_FILE: docs/work6/evidence/setup-smoke.md

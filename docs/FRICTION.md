# Friction
2026-09-07 — observed, fixed during setup: subprocess capture used Windows locale
decoding for UTF-8 linter output. Explicit encoding plus PYTHONIOENCODING for
the child makes the actual negative-case result readable; raw initial failure
remains in docs/setup/evidence/check-initial.txt.
2026-09-07 — profile adaptation: package=false cannot prove installation;
use one packaged root, remove PYTHONPATH from real checks, verify installed wheel.
Proposed exact upstream profile delta is in docs/setup/python-profile-proposal.patch.
One product observation, not a claim of repeated evidence across repos.
2026-09-07 — owner-resolved: generic PROJECT_SETUP CI/test-push requirements
distracted from the local product. Exact owner request in
docs/setup/OWNER-DECISION-20260907.md authorizes their removal for this product
until a separate request, including CD and Actions. Public GitHub remains future work.
The repo contract, validation.config and report now carry the same scope.
END_OF_FILE: docs/FRICTION.md

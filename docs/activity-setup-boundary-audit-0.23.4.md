# Activity setup boundary audit — candidate 0.23.4

## Scope and delivery state

Audit of public 0.23.3 at `b3197cd8d257a802a369c88c372f721de99cddba`,
with fixes on `codex/activity-setup-boundary-audit`. Candidate version 0.23.4
keeps schema 16. Personal spaces, Activity identities, exports, private Git,
subscription trials and installed personal launchers were not changed.
This is a local candidate, not a publication or an owner acceptance record.

## Confirmed findings and corrections

### Addressed stop could stop another setup

The bridge closed the window coordinator before validating the requested setup.
Pausing or cancelling B could therefore interrupt active A; even an absent target
closed A before returning an error. Core now commits the addressed operation
first. The coordinator checks the target under its lock and captures that target
and thread before stopping. Global window shutdown remains available separately.

Regression uses two real Core setups and the actual coordinator stop signal:
pause/cancel of another, missing, closed and active target. It verifies both
the signal and unchanged A revisions. This test does not alone prove termination
of a live child; existing stop tests and the installed interruption probe cover
that separate behavior.

### Saved wait continuation discarded necessary inputs

Restart after an answered closed wait replaced all Work inputs with the new
packet. The prior schema-14 test passed because it had no native dependency
Artifact in that list. Extending the same test to schema 16 reproduced
`stale_input` when the review tried to publish its result.

Continuation now replaces only the prior packet, preserving the other exact
Work inputs. The new packet also contains the actual saved question/answer pair,
which had previously remained absent from the copied packet. Tests on schemas
14/16 continue the same review Work and pass number through publication and
activation, checking exact dependency inputs and original answer text.

### Reopening an unknown request could hide its status

Pi attempted auto resume from the saved phase before checking derived execution.
A correct Core refusal could prevent watcher/widget setup. Startup now observes
Core's `can_resume`, and a raced refusal still leaves the saved status visible.

The bounded smoke caught a gap in this correction: known runnable phases also
need to permit continuation. That was corrected before delivery. Public Core
tests cover reopening preparation, review, correction and activation. The final
activation case goes through bridge resume and the actual coordinator thread,
finishing the saved review without a new model request or new stage Work.

### Superseded stage remained in the current native plan

Changing inputs through an owner answer could mark the unfinished stage retired
in setup while retaining its child in the current WorkPlan. No activation failure
was demonstrated for this case; it was an inconsistent current graph. Answer now
uses the same native cancellation/retirement as source attachment. The genuine
saved-wait continuation branch still keeps its existing Work. Previous plan
revisions, results and separate owner acceptance are preserved.

## Coverage changes

- Stopped draft, review and correction on schemas 15/16; source receipt replay,
  historical plan/result retention, and refusal of late completion.
- Changed inputs after completed draft, successful review, paused review and
  review question; old activation refused, fresh full packet reviewed.
- Actual owner answer retirement versus genuine saved-wait continuation.
- Late assign, send and output publication on a superseded unknown stage;
  no new effect and unchanged earlier unknown invocation/reserve.
- Two setup targets and rejected stop operations.
- Known runnable reopening, unknown reopening and a raced resume refusal.

These checks exercise typed operations and raw retained results. They do not
classify user intent by keywords. An interaction identifier alone cannot prove
that a model correctly understood a message such as a request for explanation.
Semantic understanding remains a model behavior, with actual original owner
messages required at the tool boundary.

## Executed evidence

One full native gate passed: 1019 tests, Ruff, mypy, hygiene, 32 import contracts
and build. Final changes made during that run were followed by affected checks;
the full count is not presented as a second frozen-snapshot gate.
The affected native gate passed 171 tests, types, Ruff, hygiene, 32 import
contracts and build. A final four-case reopening run also passed, including the
actual bridge/coordinator activation of an already saved reviewed result.
The final Bridge/delivery check passed all 52 Bridge tests, types, Ruff, hygiene,
32 import contracts, report structure and build after that last test extension.

The ordinary installed-wheel interruption probe ran outside checkout with Pi
1.0.4: 10 actual HTTP requests and 10 accounted sends, nine answered and one
unknown; one owner confirmation, two exact fresh packets, one full fresh review,
the same Activity identity and no owner Work acceptance. Product import paths
were verified inside the temporary wheel environment. Deliberate client shutdown
produced expected localhost connection resets, not successful prior responses.

The native UI-hook probe from that installed wheel passed unknown reopen without
resume, refusal with visible status, known-stage continuation, unchanged-error
guarding, no phantom owner message and compaction notice filtering. Zero provider
requests were made by this UI probe.

Two independent bounded code reviews and one bounded read-only evaluator smoke
identified the issues above. Final follow-up reported no new material defect
in the reviewed fixes. Their read-only conclusions are distinct from executed
native and installed Pi evidence; they are not Direction G5 or owner acceptance.

During test authoring, an assertion omitted the valid correcting phase and one
new test used an incorrect upgrade API name. Both were corrected. The subsequent
schema-16 `stale_input` was a product defect, not that test preparation error.

Wheel: `dist/zaratustra-0.23.4-py3-none-any.whl`.
SHA-256: `AF9978BB4853C11CD7277024862C83FC37E8ED543F3C296C274AC5C3EB22CCDE`.
The separately built, installed test wheel and native-gate wheel have identical
SHA-256 and all archive entries. No real-model or paid API calls were made.

## Limits and next action

This covers the named transitions and effects, not every future conversation or
model interpretation. Unknown prior outcomes remain unknown. The current personal
installation stays at its prior version until separately updated. Publication and
installation are separate from this audit; no personal Activity was recreated.

END_OF_FILE: activity-setup-boundary-audit-0.23.4.md

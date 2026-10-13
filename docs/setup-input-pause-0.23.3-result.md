# Activity setup 0.23.3 — pause and additional inputs

## Confirmed failures

The ordinary Pi sequence was additional originals → `setup_running` → pause →
the same `setup_running`. Core checked only that a stage lacked an output and
was not retired. Pause did not retire it, so even a confirmed executor stop
could not make the suggested action work. The second identical rejection
correctly triggered the existing repeat-error guard.

Pause is a saved control decision. It does not establish that an executor has
exited or that the provider response and usage are known. The previous tool
response displayed the control phase without that distinction. An additional
gap was that selected file references did not necessarily attach the complete
supplemental owner message.

## Correction contract

All changes use existing Core operations, revisions and receipts. Schema stays
16; no new queue or second execution graph is added.

- Additional Sources preserve the actual owner original and exact selected file
  bytes. Adding context does not answer or close a question.
- A known stopped unfinished stage can be retired when inputs change. Its Work,
  packets, output history and accounting remain addressable. Previous draft,
  review and manifest cannot authorize a changed input version.
- Paused uncertain stages can retain new originals without pretending that the
  response or stop is known. Ordinary resume cannot start another model send.
- For internal `setup_json` only, observed local process exit is recorded
  independently of an unknown provider outcome. Invocation uncertainty and its
  reserve remain; ordinary Work retains its previous stop policy.
- Explicit retry can prepare a different stage only after observed executor
  stop, new inputs and the existing owner confirmation. It never replays the
  interrupted Work. The prior uncertainty and cost remain in history.
- Status and Pi show execution state and allowed next action directly from
  Core. The repeat-error guard remains in place for unchanged failures.

## Verification record

The final affected native gate passed 149 tests, Ruff format/lint, mypy for the
nine selected files, hygiene, all 32 import contracts and wheel build. This is
a scoped correction gate after the earlier workflow full gate, not a claim
that the whole repository suite was rerun.

The new ordinary Pi probe uses a real localhost barrier to interrupt an
in-flight correction. It runs selected-file retention → attachment refusal →
pause → exact owner/file attachment → explicit owner confirmation → new complete
preparation → full review → activation. Previous draft/review fixtures are
prepared through public Core operations. Actual provider requests for the
interrupted and fresh stages are checked before their scripted replies.

Both checkout and final installed wheel passed this trace with Pi 1.0.4:
10 actual HTTP requests equal 10 ContextDelivery records; nine are answered,
one remains unknown with its reserved expense. The file and supplemental owner
text appear exactly in both fresh packets. There is one owner confirmation,
no repeated-error abort, no automatic Work acceptance and no Activity recreation.
The installed run used a new temporary fictional space outside checkout and
verified product imports from the uv tool's site-packages. Expected localhost
connection resets occur when the deliberately interrupted client is closed;
they are not treated as successful prior responses.

The actual Pi UI-hook probe passed stopping/unknown status, owner retry
confirmation and unchanged-error guarding with zero provider calls. One bounded
read-only evaluator smoke verified final wheel/source bytes and the stop/retry
contract and reported no concrete violation. It did not run the native tests
and is not owner acceptance or Direction G5.

Wheel: `zaratustra-0.23.3-py3-none-any.whl`.
SHA-256: `F27759B11D7E84612A828C1C8D93A5FAE51526B917B9B383371FAE654A30D9D5`.

Private maintenance passed on a restored backup and then the selected live
space. It preserved the existing Activity identity, old stage history, review
count, independent Development history and send identities/reserves/usage.
It retained the actual supplemental owner message and exact research original
through normal Core operations. No new real-model stage was started: the saved
next action requires the owner's explicit new-stage confirmation in Pi.
An operator-script metadata key error occurred during the restored rehearsal;
it was corrected before the successful rehearsal and before live changes.

## Limits

The synthetic provider proves the saved transitions, request bytes, receipts
and accounting for this path. It does not prove the model's understanding of
every possible user request. Unknown prior usage is not replaced with zero or
a guessed result. Personal identities, paths, originals and maintenance receipts
stay in the private archive. Exports and private Git publication are unchanged.
Owner authorization and later Work acceptance are reported separately.

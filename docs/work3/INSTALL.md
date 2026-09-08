# Work 3 — install and inspect version 0.3.0

Use the implementation commit and exact wheel/retained trial named in RESULT.md.
Existing uv, managed Python 3.13.7 and locked dependencies are sufficient. No
account/login, network service, new dependency or remote publication is required.
The engine installation and selected data workspace remain separate.

## Reproduce native and installed checks

From the product checkout:

```powershell
uv sync --locked
uv run --locked python -m tools.check
uv run --locked python -m tools.probe_install
uv run --locked python -m tools.probe_records --accepted-trial 'C:/Users/Anton/AppData/Local/Temp/solmax-work1-accept-20260907-a1/retained-trial'
uv run --locked python -m tools.probe_mutations --accepted-trial 'C:/Users/Anton/AppData/Local/Temp/zaratustra-work2-ltyq1qsb'
```

The final probe needs a real local terminal. For each displayed fictional request,
inspect workspace, current Work, operation, revision and digest, then type the exact
displayed approval text. Wrong confirmation or piped input is refused. The probe
prints and retains its separate environment, copied workspace, wheel, transcript
and receipt.json. It never migrates or edits the accepted original. Before using a
different accepted-trial locator, verify it against the retained-trials source.

The script deliberately repeats a committed request with its original revision,
tries stale input and repeats after revocation. Those invocations are expected to
refuse without another effect. They require confirmations to exercise the console
adapter. A trusted local-chat application with actual prior owner permission can
use the in-process Core authorization seam without a second identity confirmation.
No current CLI flag asserts that a file/model response is such permission.

The Work 2 probe now explicitly selects migration target 2, retaining its original
initial-record scenario. It runs the current wheel, not the preserved old wheel.
The Work 3 probe separately proves v2 -> v3 on a copy. init still creates schema 1;
the default explicit migrate targets 3. No read/init implicitly upgrades anything.

## Mutation request and owner-local reads

The installed CLI accepts a version 1 JSON value as a command argument. This is a
Core operation request, not a Handoff schema or file/stdin importer. Obtain exact
workspace_id, work_id and state_revision using records read. Generate a new UUID
once for a new intent; keep it when retrying an unknown outcome.

```text
zara records read <workspace>
zara mutate <workspace> <request-json>
zara receipt <workspace> <query-json>
zara history <workspace>
```

Mutation JSON fields: version=1, operation_id (UUID), workspace_id, work_id,
expected_revision (current global integer revision), operation, requirements
(array, only for set_work_requirements), artifact_references (must be empty in
Work 3), provenance (short explanation, not authority). Other fields are rejected.
Receipt query contains version, workspace_id, work_id, operation_id only.

Operations: authorize_work explicitly grants work_metadata and makes a draft ready;
set_work_requirements changes executor requirements of ready authorized Work;
cancel_work makes it terminal; revoke_work removes rights, including receipt-read.
All require exact authorization from the accepted channel. Bootstrap and migrations
never grant. Goal, criteria, boundaries, budget, membership and files are not editable
through this allowlist. Terminal Work cannot restart; its rights can still be revoked.

Original retry usually returns conflict because revision validation precedes
duplicate lookup. A newly confirmed retry at the current revision with the same
id/intent returns the stored receipt. Changed intent at that stage returns collision.
Revoked or ineligible Work refuses earlier. Receipt-read requires current rights;
terminal status alone does not prevent authorized historical reading.

records read and history are local owner inspection surfaces, governed by access
to this single-user workspace. They are not Work-scoped context APIs and do not
promise isolation against the local owner or another process of the same OS user.
The separate receipt API enforces the narrower current Work permissions.

## Evidence and recovery boundary

Native failure tests inject DB refusals during state/event/receipt/commit and
migration, simulate lost CLI reply after commit, concurrent requests and revoked
rights after preview. Installed console trial tests actual adapter/CLI persistence.
They are executor checks, not owner runtime acceptance or binding fresh G5.

SQLite handles rollback for the tested DB failures; never manually repair DB/state
Markdown or issue a fresh operation id to work around an unknown outcome. Read the
saved receipt/history instead. Failed trials remain available. There is no downgrade,
general DB repair, power-loss/disk-loss guarantee or artifact recovery tool. Copy an
unchanged retained sample into a new folder for a new trial; keep originals intact.

Work 3 has no content references or file projections to publish/rebuild. Work 4 must
add those duties before dependent operations. Handoff, context, Result/next Work,
clean-chat behavior and the full owner demonstration remain Works 5–8.
No CI/CD, Actions, notifications, publication or successor Direction CALL is implied.

END_OF_FILE: docs/work3/INSTALL.md

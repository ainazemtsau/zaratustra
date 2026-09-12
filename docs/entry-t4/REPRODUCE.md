# Reproduce recoverable installed material transfer

From this repository, choose a new ignored output directory:

```text
uv run --locked python -m tools.probe_entry_t4 --output _scratch/entry-t4-run
```

The probe builds version 0.11.0, installs its wheel with locked runtime dependencies
into a new Python 3.13.7 environment, and runs from an unrelated directory. The first
isolated process creates a new generic schema-7 workspace through public APIs, grants
ordinary Work/Artifact authority, publishes a generic basis, prepares and confirms an
exact external-material plan, then performs the standard publication and acceptance.

A second fresh isolated process opens only those retained generic inputs. Before
confirmation it reads the bounded coordinator inspection: intake id, preview hash and
the unverified claimed stage names. That surface contains neither receipt bodies nor
material and grants no authority. The new trusted session reviews the same exact plan,
uses authorized Core receipt lookup and verified content, and receives the original
publication, acceptance and saved-continuation receipts without another revision or
acceptance.

The output retains `summary.json`, `commands.json`, the installed wheel/runtime
environment, disposable workspace, exact external envelope, preview, original receipt
and recovered receipt. These are ignored local proof only. The summary's `recovery`
object must report both exact receipts recovered, saved continuation recovered, no
revision change and one acceptance.

The same interactive command can be repeated after interruption:

```text
zara entry intake CATALOG DESIGNATION EXTERNAL_JSON
```

Each new process obtains a new trusted confirmation of the exact immutable plan.
Progress files never preserve confirmation. A changed envelope under the same intake
identity, malformed/colliding progress, missing current read rights, an unrelated
revision before a remaining stage, or unavailable exact bytes is refused.

The coordinator serializes cooperating local retries for one intake identity. It does
not claim an all-or-nothing transaction across the two Core calls, hostile-writer or
network-filesystem safety, power-loss certification, provider interaction, automatic
research, Work completion, or full external-chat/product construction.

END_OF_FILE: docs/entry-t4/REPRODUCE.md

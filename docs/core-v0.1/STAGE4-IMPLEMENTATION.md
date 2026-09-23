# Core v0.1 Stage 4 — interactive Pi path

## Boundary

`zaratustra.pi_adapter` starts an ordinary upstream Pi process with an extension.
Pi owns the conversation, authentication, provider protocol and model cycle. A
localhost bridge owns one selected Core space and one trusted local actor. The
foundation remains the sole domain store. No independent RPC executor, DBOS
production dependency, scheduler or dispatcher is installed by this stage.

The host asks the console user to confirm the resolved new Core space, working
directory, local OS account and selected initial Activity/Work. It then binds
`LocalAuthority` to space id and execution epoch. The bridge has a random bearer
token, listens on `127.0.0.1`, and only accepts typed execution operations for
the selected Work. Text from a model cannot establish actor, grant or acceptance.

## User path

1. Create an empty Core space and synthetic or authorized Activity/Work using
   the public foundation operations. Provide the exact `--space`, `--workspace`,
   `--pi-cli` and `--pi-runtime` paths to
   `python -m zaratustra.pi_adapter`. Set a positive `--limit-units` and
   `--reserve-units`; select provider/model explicitly. Pi starts without tools
   unless the local operator chooses `--pi-tools`. Optional
   `--activity-id` and `--work-id` preselect one existing Work. The local runtime
   must contain ordinary upstream Pi and be writable for the temporary extension
   copy. The host removes that copy at exit.
2. In Pi, `/zara-work` chooses an Activity and Work, creates a persistent
   Attempt bound to its exact Work revision, input references, resource revision,
   session, epoch and generation. An active prior Attempt requires an explicit
   interruption after the old Pi process has stopped. `/zara-status` reads the
   current Core snapshot, including saved input/output bytes, basis, current
   Work rights, status and model ledger.
3. Before a prompt, the extension reads the exact current input Artifacts and
   injects a hidden context message. For each final observable HTTP body, including
   service calls and repeats, it creates a distinct invocation and records the
   body SHA-256 and byte length. It prepares, reserves and marks the invocation
   sent through atomic Core operations before calling `fetch`. A denied operation
   stops the HTTP request. Provider `stream` and `streamSimple` are wrapped; the
   Codex profile forces SSE because Pi's default Codex WebSocket path bypasses
   the observable `fetch` seam.
4. A completed answer with usage records actual units. Missing or failed
   outcomes remain `unknown` and hold the full reserve. A successful single
   textual Work output becomes a new Artifact and a separate Work output link;
   Work remains `proposed`. `/zara-accept` shows the exact current Work revision,
   outputs and requested basis, asks for an explicit UI confirmation, then uses
   a separate `work.accept` Grant and Core receipt to set `succeeded`.
5. A new session reads Core again. It sees the original Activity, Work, exact
   inputs/outputs, acceptance, resource and invocation history. Restore rotates
   the execution epoch and invalidates old authority; recovery interrupts active
   Attempts and leaves admitted/sent calls unknown. Work deletion removes its
   execution rows, receipts and content-derived fingerprints through the same
   maintenance path as its prior subject data.

The supported transport profiles are `codex-sse` and a configurable local
OpenAI-completions HTTP/SSE profile for tests or explicitly chosen providers.
Model, provider, working directory, resource limit, reserve and Pi tool
allowlist are launch choices. The first trial's model and call count are not
product defaults or an allowlist. An unobserved transport is refused.

## Evidence and limits

The localhost synthetic run used upstream Pi 0.87.0 in RPC mode solely as a
test driver of the same extension. Its `/zara-work` UI chose Activity/Work; it
observed one final HTTP body whose SHA-256 matched Core's pre-send invocation,
then an answered invocation, Artifact and Work output link with Work still
`proposed`. The separate `/zara-accept` basis and confirmation changed Work to
`succeeded`. A deliberately insufficient reserve produced a prepared record
and zero provider HTTP requests. Focused tests cover stale input, current
separate rights, unknown reserve after a new session, explicit result
acceptance, and deletion. Pi's authorization readiness check
does not prove a token remains valid at the provider; a rejected real trial
request must be counted and retained as unknown.

This stage automatically publishes only a single nonempty text output from a
completed turn. Multi-slot and non-text Work require a later explicit output
path. Token usage is provider-reported; an answered call can exceed its prior
reserve, and that overrun remains charged and blocks later admission. An
`unknown` call retains its full reserve until a separately justified
reconciliation. The adapter does not inspect opaque provider transports,
persist Pi's own session JSONL as Core evidence, or claim recovery of a
standalone RPC executor. Managed Core data are covered by Core maintenance;
external Pi session files and provider-side copies are outside Core-managed
deletion and must be handled under their separate retention controls.

## Manual acceptance

Use a fresh authorized space and working directory. Confirm the host's path and
actor prompt, choose a Work in `/zara-work`, and ask Pi to summarize an authorized
text Artifact. Run `/zara-status`: verify the exact input, an answered invocation,
saved output Artifact, its Work link and `proposed` status. Quit and reopen Pi
against the same Core space; verify the same output and resource ledger. Review
the text, invoke `/zara-accept`, enter a basis and confirm the exact revision.
Run `/zara-status` again: `succeeded` and the acceptance receipt must appear,
while the Activity remains `ongoing`. The owner decides acceptance from that
review; engineering checks alone do not accept the Work or this stage.

END_OF_FILE

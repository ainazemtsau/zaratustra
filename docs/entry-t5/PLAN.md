# Entry T5: shipped first-use and manual external-chat path

## Bounded product outcome

This increment joins accepted public operations without changing Core semantics. The
installed `zara entry start` command explicitly initializes one selected directory,
migrates it to schema 7, creates one generic unbound Process/Work/Artifact graph,
registers that Work under a human designation, and then asks for the existing exact
trusted confirmation for each ordinary mutation that makes the Work ready, grants
its Artifact scope, publishes the supplied initial UTF-8 material and accepts that
exact version as the initial Handoff result. Empty drafts remain drafts and cannot be
opened as ready context. A non-authoritative first-use plan below `inbox/first-use`
keeps operation identities and the original material digest stable across retries.

The setup JSON contains only user-facing names and generic text fields. Core creates
all record identities; the coordinator creates all operation/version identities and
the catalog adapter records them. The user chooses a catalog, designation, workspace,
setup data and initial material, but never assembles UUIDs, revisions or hashes.
Unbound Core metadata is used deliberately: this is not a Pack or method constructor.

## Exact setup and recovery boundary

The saved plan fixes the workspace/Process/Work/Artifact identities, setup fields,
initial bytes hash and size, and four complete Core requests before the first mutation.
On retry the coordinator validates the existing graph, catalog row, plan, full Core
history and registered bytes. It runs only the uncommitted suffix at the original
revisions. Loss or mismatch of a plan after state advancement is refused; an existing
nonmatching workspace, designation, mutation or Artifact is never overwritten or
adopted. Publication and acceptance remain separate Core commits, and any incomplete
result reports the completed receipts rather than claiming readiness.

The four state changes are the existing `authorize_work`, `authorize_artifact`,
`publish_artifact` and `accept_handoff` operations. The initial Handoff's result is the
new immutable version and its basis is empty because it is the first accepted material.
Publication alone is not preparation: success requires its accepted Handoff and a
currently ready Work with Artifact authority.

## Designation-based context and external exchange

`zara entry open CATALOG DESIGNATION --max-bytes N` resolves the selected path,
identities and current revision, confirms the exact generated `ContextQuery`, and
returns the existing bounded Core context. Therefore saved accepted material bytes,
not metadata headings, are the continuation basis. Draft, terminal, missing-acceptance,
damaged-content, stale and insufficient-budget cases retain Core's refusals.

`zara entry request CATALOG DESIGNATION OUTPUT --max-bytes N` performs that same
authorized context read and writes one new, non-overwriting provider-neutral request
package. The package captures the original revision, exact accepted references,
Artifact identity, immutable context bytes/hash and three generated intake operation
identities. Its `copyable_request` tells a human to copy the bounded context to a
chosen external chat and return only new UTF-8 material. Preparing or exporting this
request contacts no provider and changes no workspace fact.

`zara entry receive CATALOG DESIGNATION REQUEST RESPONSE` validates that package
against the selected catalog row, wraps the response bytes in the existing strict
external-material envelope, displays the unchanged Entry T4 publication/acceptance
preview for trusted confirmation, and executes the recoverable intake. The wrapper
uses the request's captured revision and references; it never refreshes them when the
response arrives. Wrong selection, inconsistent request/context fields, stale state
or a different response under the same intake identities refuses without rebasing.
The request file is an untrusted snapshot, not an authenticated or immutable file:
self-consistent replacement operation identities may prepare a distinct intake,
which still faces current Core checks and separate exact trusted confirmation.
Keep the original request file unchanged for retries. Returned text is data only
and cannot grant rights, confirm itself or complete the Work.

## Validation and explicit limits

Unit and CLI tests cover exact setup/retry, partial/draft truth, two designations,
ambiguous aliases and an unavailable neighbor, designation-based context with actual
saved bytes, non-overwriting request export, wrong/stale request target, altered
request/context, damaged bytes and recoverable intake. An installed-wheel probe in a
new ignored scratch directory creates two generic instances from an unrelated working
directory, opens both by designation, and completes one simulated manual return
through the public request/receive coordinator while retaining exact receipts and
bytes. The probe supplies generic local text; it does not contact or impersonate an
external provider.

This is not a subject method, Pack, interactive constructor, Result completion,
automatic research, real ChatGPT trial, provider/account/API integration, personal
workspace use, GUI, memory, model routing, hostile same-user isolation, CI/CD or a
claim of owner acceptance.

END_OF_FILE: docs/entry-t5/PLAN.md

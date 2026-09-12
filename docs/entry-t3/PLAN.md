# Entry T3: exact incoming material preview and acceptance

## Scope and public boundary

This increment adds one installed coordinator for receiving genuinely new external
UTF-8 material for one explicitly selected Work. A catalog designation resolves a
source, but the coordinator separately binds and validates the workspace, Process,
Work and Artifact identities. It neither discovers authority nor executes a Pack.

The external envelope is strict JSON version 1: its `version` is exactly the JSON
integer `1`, with no coercion. It names an intake, publication and
acceptance identity; the selected workspace/Process/Work/Artifact; the original
state revision; exact existing Artifact-version basis references; the complete
material; and bounded provenance fields. Duplicate keys, unknown fields (including
approval assertions), booleans in integer fields, invalid UTF-8 and oversized input
are refused. The envelope is limited to 393,216 bytes and the UTF-8 material to
262,144 bytes. These are limits of this text-intake wrapper, not universal Artifact
or future research-report limits. The generated metadata-only Handoff remains under
Core's separate 64 KiB Handoff limit.

The installed CLI surface is:

```text
zara entry intake CATALOG DESIGNATION SOURCE
```

`SOURCE` is a UTF-8 JSON file or `-` for stdin. No provider is contacted. A human
may separately copy a request to an external research provider and bring the result
back through this command; provider launch, model routing and paid/API activity are
outside this increment.

## Exact plan and trusted confirmation

Preparation reads one current schema-7 record graph and verifies:

- the explicit catalog selection and envelope name the same workspace, Process and
  Work, and the envelope names that Work's sole declared Artifact;
- the Work is ready with current `work_metadata_and_artifact` authority;
- the envelope's original revision is still current;
- every declared basis reference belongs to that Artifact, matches an immutable
  descriptor, and has currently verified bytes;
- Process and Work Pack references still agree through existing Core validation;
- the proposed material digest and size match the complete displayed material.

The preview contains the full escaped material, exact input/material hashes, current
active version, declared basis, target identities and rights, immutable Pack binding,
and both complete planned Core requests. The first request publishes/registers a new
immutable Artifact version. The second accepts a generated Handoff whose result is
that exact new version and whose basis is the exact envelope basis.

One trusted local confirmation binds the canonical complete preview and workspace
path. Files, envelope fields and caller-supplied booleans cannot create that token.
The trusted adapter derives the two ordinary Core authorizations only after this
confirmation. Execution re-prepares and compares the complete plan before any
effect, so changing material, target, basis or original revision invalidates the old
approval. The intended original revision is never refreshed. The acceptance request
names the expected revision after the one planned publication; it does not pretend
that this derived revision was the incoming source basis.

Rewrite cost: envelope validation, preview fields and confirmation wording are
isolated in `zaratustra.intake` and the trusted local adapter. Core operation and
identity models are unchanged.

## Effects and receipt

Successful execution calls the standard public `apply_mutation` twice:

1. `publish_artifact` saves new bytes under the publication operation/version id and
   atomically registers/activates its immutable descriptor with a Core receipt.
2. `accept_handoff` verifies that new content and every basis reference, saves the
   accepted material/provenance, and returns a separate Core receipt.

The wrapper receipt distinguishes four facts: the received envelope/material hashes,
the publication receipt, the acceptance receipt, and completion. Completion is
always `not_requested` in this increment; receiving a report does not complete Work.
The continuation fact is derived from the post-acceptance record and can only be the
same selected ready Work. No Result, next Work or inferred decision is fabricated.

If publication commits but acceptance fails, a typed incomplete error carries the
known publication receipt and reports acceptance as absent. A post-commit projection
failure is likewise reported with the Core receipt that proves the committed stage.
No rollback or all-or-nothing claim spans the two calls. Durable coordinator replay,
restart discovery and full cross-invocation fault recovery are deliberately left to
the next increment; the retained exact ids, hashes, planned requests and stage
receipts form its small compatible boundary.

## Validation and limits

Focused tests cover new-byte publication and acceptance, exact basis/content reads,
missing initial versions, target and source identity, stale revision, insufficient
rights, terminal Work, hidden approval fields, malformed and oversized envelopes,
changed payload/target/basis after preview, damaged basis bytes, distinct receipts,
no completion, and honest partial effects. The installed-wheel demo starts with a
new generic schema-7 workspace and an external envelope whose new material has no
registered version. It uses normal Core authorization to establish the ready
Artifact scope, then exercises preparation, trusted local-chat confirmation and both
standard effects from an unrelated directory.

The feature supports one local process and one selected Work per invocation. It is
not a general constructor, binary intake, transfer replay engine, Process method,
health/game workflow, Pack installer, GUI, memory, model router, provider integration,
startup assistant, actual ChatGPT transfer, or automatic Work completion.

END_OF_FILE: docs/entry-t3/PLAN.md

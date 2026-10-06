# Integration boundary and adaptive manual setup

## Scope

Implement a reusable integration boundary, not a closed list of services, discussion
subjects or user goals. Installed technical operations are typed and described;
service/account capabilities and the user's narrow/broad preferences are distinct.

First executable route: manual external chat with regular instructions, reusable
context from available repository reading, an optional file/text fallback,
questions relayed to the local agent and robust return retention. Existing Core
Source/Handoff/Analysis/Claim store originals, setup and reasoning. Acceptance stays
separate. No schema migration or parallel backend.

## Implementation contract

- `zaratustra.integrations` is above public Core and below Pi/release. Trusted code
  supplies adapter names and operations with parameter models and handlers.
- Catalog enumerates only installed operations. Versioned contracts validate internal
  calls before dispatch. Unknown adapter/operation/version and extra arguments fail.
- The manual adapter retains an actual generated instruction/context, not a fixed
  discussion prompt. Context includes exact selected sources and Core-added scope.
- Existing Handoffs with source evidence can receive linked returns without pretending
  their Source refs are other Activities. Actual foreign Activity/Work anchors and
  foreign scoped Source material remain refused.
- Raw external text is never validated as a Save Package schema. Formatting mistakes
  are retained. Uncertain association does not require a trip back to the external chat;
  an unassociated original can be retained first under the owner's selected scope.
- Core owns operation identity, receipts and immutable bytes. A changed document gets
  a new Handoff; replay preserves historical scope bases and reports staleness.
- Exact reads are windowed; metadata-only imports do not add an unseen Source as model
  evidence. Actual reads expose exact refs through the Bridge.
- The ordinary launcher loads the installed skill explicitly. Instance configuration
  is not copied into shared resources. Assigned RPC cannot configure integrations.
- A self-contained product overview ships with the wheel, without owner paths/IDs or
  a development journal. It describes its package version, not live remote/instance state.
- Preserve all earlier compact/resume fixes, old transfer/CLI interfaces and unrelated
  dirty-workspace changes. Publication is a separate explicitly authorized operation;
  service setup does not publish code or replace the live installation.

## Validation

Public-API synthetic tests: independent adapter schema/dispatch, permission denial,
replay/conflict, tailored setup with Source basis, rejected foreign scope, malformed
external text, Unicode/BOM/CRLF, bounded exact reading, unchanged acceptance, model-free
CLI and package resource discovery. Ordinary native Pi: full skill delivery, installed
catalog/contract/prepare/import/read, source-backed return and a fresh-process reopen.
Run the existing complete native gate and repeat the native trace against the installed
wheel in an isolated environment. No paid provider or real external account required.
Tests establish technical behavior, not prose quality or owner acceptance.

## Deferred, not represented as implemented

Automatic API/Trilium/GitHub connectors, MCP servers, browser agents, secret-store
integration, external-effect outbox/scheduler, automatic workflow activation and
bidirectional synchronisation. A saved proposal for these is not an active integration.
The common code boundary supports later adapters without hardcoding new user stories;
each actual external-effect implementation still needs its own authority and reliable
send/recovery contract. Real-account convenience needs a human manual roundtrip.

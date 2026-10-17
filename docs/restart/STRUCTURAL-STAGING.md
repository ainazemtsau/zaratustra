# Structural admission before native result staging

The native result tool accepts metadata for a later outcome. Its acknowledgement
does not mean that a Result, analysis or memory update has committed. The actual
plain Pi final remains the outcome text; Core retains final authority over its
current basis, rights, delivery evidence and atomic changes.

Core's public `validate_outcome_metadata(metadata)` reuses the typed outcome fields,
record references, expected-head types and tagged Sleep progress v1/v2 models.
It performs no database access, preview, terminal observation or state mutation.
Recognized progress tags retain their required fields and version distinction.
Other free bodies, analysis content, Memory and Method prose are not judged.

`Change.source_refs` contains record references with `id` and `revision`, plus an
optional role. History references with `sequence`, `index` and `sha256` belong in
the free analysis body's `sources`. The adapter never converts between families,
adds a value wrapper, invents record identifiers or upgrades a progress version.
`outcome_metadata_contract()` returns fresh canonical schemas and guidance; the
adapter exposes them to the model alongside Core context.

Before saving staged metadata, the host performs the pure structural check.
A deterministic failure from that call returns a precise structured rejection.
No rejected candidate becomes staged and no terminal is fabricated. If there was
an earlier staged candidate, the host clears it through the existing mapping CAS
and explicitly reports `previous_metadata_cleared`; a subsequent final cannot
silently commit the earlier candidate. Clearing failure remains a blocking error.
An invalid first candidate needs no mapping write. Historical bytes are retained;
clearing current staging is not a rollback of earlier domain effects.

Pi may reject tool arguments before invoking the host tool. The adapter recognizes
that pre-execution path from trusted lifecycle ordering, not error-message text:
there was neither a successful tool-call admission nor tool-execute entry for the
failed result call. It retains the original end observation with this provenance
and clears prior staging through CAS. The original SDK error remains the model's
tool response; the clearing acknowledgement belongs to the retained host
observation. Tool guidance explicitly requires corrected staging after that
error. Other tool failures do not acquire this provenance or a corrective status.

The model may issue a new corrected tool call. The host does not generate a retry
or additional inference itself. Authorization, stale basis, transport, persistence
and unknown-effect failures are not reclassified as argument errors. Structural
acceptance cannot guarantee later admission: final Core checks still run against
the actual terminal and current state. A legitimate progress change can depend on
pending delivery, so this check is not a full commit preview.

The actual ce07210 failed terminal remains historical evidence. Preventing future
invalid staging does not repair or replace that terminal, create a Result, resolve
old effects or confer semantic analysis credit. Overall readiness and owner
acceptance remain separate from this bounded correction.

END_OF_FILE: docs/restart/STRUCTURAL-STAGING.md

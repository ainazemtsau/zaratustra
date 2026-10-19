# Synthetic execution evidence — derived public copy

The original local test artifacts are retained unchanged in the isolated output
root named in the handback. This directory is a public derivative: machine paths
are replaced with `<TEST_ROOT>`, `<DEV_CHECKOUT>` or `<OWNER_PROFILE>`. Structured
and nested JSON was reserialized. Opaque provider reasoning/signatures are omitted
from public copies; original raw artifacts remain local. IDs, model outputs, observations, error status,
commit receipts and declared original-content hashes are preserved.

`manifest.json` records each original artifact's SHA256 and its public derivative
SHA256. A source content_hash inside a redacted record refers to the original
retained local bytes, not to a path-redacted rendering. Synthetic material files
under `materials/` are copied byte-for-byte and their digests match both sides.
Native console captures can include SQLite experimental warnings even when their
historical filename ends in `.json`; those captures remain readable console text.

Each scenario is a separate Node/Pi process and in-memory session. The test runner
uses the installed public package, global Pi 1.3.0 SDK and native authentication
via `ModelRuntime.authPath`; no developer Core/resources or copied credentials.
The observer records actual requests, tool events, current disk rows and settlement.
It supplies no model replies or prepared domain mutation. Attempt 8's observer
deliberately discards the response after a real commit and aborts that test session.

Attempts 1–2 are failed runner attempts; 8 is an expected interruption; 10 is an
expected unavailable-store case. All remain visible alongside successful attempts.
The initial runner's cached-input accounting was corrected by recomputing every
retained assistant usage before attempt 9; both ledgers remain. Estimated Pi cost
is not an invoice or subscription charge measurement.

Raw credentials, normal user configuration and personal memory are absent. These
are execution observations, not an independent review or owner acceptance.

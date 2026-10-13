# Workflow 0.23.2 — explicit upgrade ordering

## Confirmed failure and correction

The installed 0.23.1 `zaratustra upgrade` created its verified pre-upgrade backup,
then called ordinary space preparation. That preparation correctly refused an
old schema before opening Pi, but also refused the explicitly authorized upgrade
before its migrations ran. The existing Core stayed on schema 15.

Version 0.23.2 gives space preparation an explicit `upgrade_existing` flag,
defaulting to false. Only the confirmed maintenance command passes true, after
creating its verified backup. It uses the existing ordered migration chain;
ordinary Pi still refuses an old Core and never silently migrates it. No new
schema, runtime queue, export behaviour or Activity contract is introduced.

## Verification

The regression calls the actual `release.main` CLI entry with a selected
fictional configuration and trusted UPGRADE input. It does not mock preparation,
backup or Core migrations. It covers schemas 1, 2, 6, 14 and 15 to 16, verified
restorable pre-upgrade backups, declined confirmation without changes, and an
accepted Work with its Activity, exact inputs, output, revisions, Attempt,
invocation usage and owner acceptance preserved. Pi availability and the local
console actor are test fixtures; no provider or personal space is used.

The final affected native gate passed 15 tests, Ruff formatting/lint, mypy on
six selected files, hygiene, all 32 import contracts and a wheel build. This is
a scoped regression gate after the earlier workflow full gate, not a new full
suite claim. The bounded read-only evaluator smoke confirmed the final wheel's
version and matching patched modules and reported no concrete upgrade-order
defect. It did not rerun tests and is not owner acceptance.

The wheel was installed in the ordinary uv tool environment and invoked from
outside the checkout. The actual `zaratustra upgrade` confirmed UPGRADE,
created a verified backup and migrated a restored schema-15 Core to 16.
The selected live Core then migrated through the same installed command.
The private reset rehearsal and actual reset passed preservation checks for
the independent Activity and its Work revisions, inputs, Methods, results,
Attempts, acceptance and model-send identities/usage. Independent Sources and
the externally retained verified backup remained readable. Native deletion
maintenance purges managed interactive Pi sessions; their original history
was archived separately before deletion. Detailed private reset results remain
outside public docs. No new personal Activity or real-model send was started.

Wheel: `zaratustra-0.23.2-py3-none-any.whl`.
SHA-256: `6FABC1AB7843B482E6FC2048149A93555F236DF22CC0C05B0C0472DEA6920FFB`.

## Limits and owner authorization

This patch addresses the actual CLI migration failure. It does not repeat the
real-model Activity trial or claim quality for every future conversation. The
earlier trial's allowance violation remains documented in the 0.23.1 report.
No new real-model calls or paid API calls are authorized or made by this patch.

The owner authorized updating the selected personal installation and resetting
Health while preserving answers and Development. Private paths, identities,
answers and reset receipts are retained only in the private maintenance archive.
Exports and personal Git publication remain outside this work. Authorization
to deliver the correction is separate from acceptance of later owner Work.

## Public delivery

Published to `ainazemtsau/zaratustra/main` at
`e8b08bcc1973d9f3a6559845478c68ab6a837a5b`. Authenticated GitHub ref readback
and a subsequent Git fetch confirmed the exact commit and matching version,
patched modules and report. The following documentation receipt does not
change the installed wheel or its recorded SHA.

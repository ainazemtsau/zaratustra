# Process creation T3 correction R1 plan

Basis: correction CALL `c-solmax-zaratustra-process-t3-r1-20260913`, exact
candidate `2189f3c2ca5c484048200db8e0ded3d42100a3bb`, contract 36 PROBA. The
retained fresh physical report and its installed artifacts remain unchanged.

## Rule correction

Keep `edition_transition` as the single admission rule already repeated by the
runtime before Core proposal. Add two narrow invariants there: changing only the
mandatory edition number is `no_change`, and completing the bound current
occurrence under the proposed definition must select a next Work. The latter
refuses the unsupported no-future case before any review or approval is saved.
Changing a later untouched node remains valid even when the immediately next Work
has the same meaning.

Journal validation will recognize the two pre-correction invalid preview shapes and
refuse them as unsupported saved intent. It will not edit, discard, reinterpret or
apply those journals. Any Core effect already committed by the failed candidate
remains authoritative and is not repaired by this correction; further coordinator
use safely refuses pending/reconstruction paths that depend on invalid intent.

## Evidence

Add public-API regressions for edition-only and no-future refusals, later-lineage
siblings, a legitimate later-future semantic change, both existing valid change
paths, unchanged Core bytes/no saved approval on refusal, Unicode-bound exact
confirmation, restart and replay. Extend the isolated installed-wheel probe to
record the correction refusals while proving every product import is in that
wheel's `site-packages`.

Run focused checks only as change feedback, then one native full check, the corrected
installed-wheel proof from a new isolated directory, and one distinct `--deliver`
gate. Commit implementation first; then record exact candidate, wheel, logs,
limitations and pending manual acceptance in `FIX-READOUT.md` and root `RESULT.md`.


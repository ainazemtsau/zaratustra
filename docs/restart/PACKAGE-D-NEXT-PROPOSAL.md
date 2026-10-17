# Bounded proposal after F-D-08

Basis: source/build `83af4d4a529ca73d06d566db62a3586f2a432af9` remains a
retained negative checkpoint. The lead authorized the bounded JSON metadata fix
and offline verification as routine D work after recovery. The implementation
was completed in ac58f9437f5122a5e8ea5ba93384b14cbb2b4563, then final
source f80180a passed mandatory gates and independent source review
READY_FOR_CANDIDATE_RECONCILIATION. The separately bounded fourth overall G14
is PASS_LIMITED_SINGLE_TRACE. This historical proposal remains the decision basis;
owner acceptance of D is pending. No live capability probe is
included. The resource capability choice is documented separately in
PACKAGE-D-RESOURCE-PROFILE-PROPOSAL.md.

## Established blocker

The third and last authorized substantive G14 trial made four completed native
requests. Initial useful execution passed; correction failed before C8 because the
2189-character terminal contains an extra closing brace at offset 2067. The
provider reported completed/stop and 851 output tokens with 4096 requested;
that field was not verified as an enforced cap, and this
was not observed truncation. Reopen was not reached. The exact retained terminal,
negative history and reviewer assessment stay unchanged. Trial allowance is 3/3
exhausted. Neither account access nor a larger output cap addresses this finding.

## Proposed smallest change

For the existing native `pi-chatgpt` branch only, add this model metadata beside
the existing `maxTokens`, `contextWindow` and compatibility metadata in
`packages/app/src/zaratustra_app/executor_port.py`:

```json
"samplingParams": {"text": {"format": {"type": "json_object"}}}
```

Pi 1.3.0 documents free-form sampling parameters and model overrides. Its installed
model schema permits this object; `provider-composer.js:76` merges it into model
metadata. `pi-ai/dist/api/simple-options.js:12` resolves model/per-thinking/request
sampling parameters. `pi-ai/dist/api/openai-responses.js:304` resolves them and
`:306` assigns them to the actual request. Bundled CLI code has the same path.
Exact installed source hashes/excerpts are recorded in
`evidence/package-d/final-83af4d4/JSON-MODE-SDK-BASIS-20261017.json`.

The existing system instruction already explicitly requests terminal JSON.
Keep its response contract and useful prose, dynamic subject bodies, existing
zara_change tool and pinned Method. No new codec, final-result tool, schema
translation, brace repair, truncation, response rewrite, hidden retry or fallback
is proposed. Core still retains and validates exact C7/C8 bytes, refs, rights,
scope, expected heads and resource accounting. Both routing and useful execution
must receive the same selected native request format.

JSON mode targets syntax generation only. It does not establish field/schema
validity, reference validity, safe effects or useful meaning. It has documented
incomplete-output edge cases, so existing refusal/retention remains necessary.
Strict json_schema is not this change: arbitrary subject body fields and current
dynamic maps must not be silently closed or encoded into opaque JSON strings.

## Evidence before any further live trial

1. Add actual native Pi SDK offline captures using fictional auth/HTTP responses
   to the existing medium/high controlled transport tests. Assert exact final
   `text.format` for discovery and scoped execution, selected model/effort,
   tools, context, max tokens and finite cap. Compare complete request objects
   against the baseline, allowing only this intended format delta. Exercise the
   installed bundled CLI, not a locally reconstructed request builder.
2. Reach controls removing the format setting and changing json_object to text;
   each must fail on actual wire assertions. Preserve corresponding RED/GREEN.
3. Confirm malformed, fenced, empty, nonobject and missing-field known terminals
   remain retained/refused; reopening does not resend. Confirm tool effect before
   malformed terminal stays exactly once, and existing unknown/cancel/late-input,
   rights/CAS, shared budget and backup-reference controls remain green. Reuse
   unchanged completed evidence where applicable; run affected checks, then
   freeze new source/build and perform required gates and outside install proof.
4. Independent physical reviewer checks the new source/build and chooses a new
   unseen ordinary request and rubric after freeze. Prior failed trials remain
   failed; do not replay the old mathematical response as live proof.

## Capability and decision boundary

The [official Responses JSON mode guide](https://developers.openai.com/api/docs/guides/structured-outputs#json-mode)
documents `text.format.type=json_object`, requires an explicit JSON instruction,
and distinguishes valid JSON from schema compliance. The
[SiWC preview limitations](https://developers.openai.com/siwc/token-sharing-open-source/preview-limitations)
do not establish this selected account/model's JSON mode capability. That remains
unproven by offline SDK construction. Current general documentation also lists
max_output_tokens as unsupported for that preview route, whereas the retained
four requests completed with the current profile; this discrepancy is preserved,
not a reason for an unrelated silent transport change.

The lead authorized superseding incomplete 83af gates and moving the mandatory
complete gates to the actual corrected final source. Preserve every partial and
negative receipt. Bounded metadata implementation and offline proof are already
authorized; they do not require a second owner approval. The owner subsequently selected the explicit calls-only resource option; exact
words and guarantees are retained in PACKAGE-D-RESOURCE-PROFILE-PROPOSAL.md. No
repeated Luna access approval is implied.
Only after the resulting reviewed source/build and the resource choice exist,
the lead may admit one separately bounded new G14 under the existing owner grant.
The reviewer must declare total physical sends,
per-chain reservations, unsupported token/money maximum and stop rules before launch. Use the first
ordinary request to establish format capability within that same budget, without
a separate auth or inference preflight. Any unsupported-capability response stops
the trial with actual error/usage uncertainty; do not remove the setting or retry
under another model/account/endpoint. This document does not itself launch the
fourth substantive trial. Any such separately admitted trial must retain the
exhausted earlier 3/3 history; a new failure returns a concrete architectural
choice to the owner without an automatic fifth. Its author executes no live
requests.

END_OF_FILE: PACKAGE-D-NEXT-PROPOSAL.md

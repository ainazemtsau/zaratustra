# Resource capability choice for native Pi

Status: the owner explicitly selected the recommended calls-only option on
2026-10-17: «Да, ограничиваем число обращений — продолжай (рекомендуется)». The
question specified Pi/Luna subscription,8sends/chain and24total next G14, with no
guaranteed hard token/money maximum or automatic retry. This accepts the resource
choice only. Bounded implementation/verification completed on final source
f80180a with full gates and independent READY_FOR_CANDIDATE_RECONCILIATION.
One bounded fourth G14 is PASS_LIMITED_SINGLE_TRACE; owner acceptance of D remains
pending. No fifth or automatic retry is authorized.
The following proposal is retained as the concrete decision basis.

The selected Sign in with ChatGPT route documents max_output_tokens as unsupported.
The four retained 83af requests completed with 4096 present, but accepting a field
does not prove enforcement. Consequently that value cannot currently be claimed
as a hard server output-token bound. The independently enforced finite physical
inference-send count and inherited C6 Work reservation remain distinct guarantees.

## Supported mechanism, without stack change

Pi 1.3.0 accepts this selected-model metadata:

```json
"compat": {"supportsMidConvoEffort": false, "supportsMaxOutputTokens": false}
```

Installed models.schema.json:1011 permits the boolean. provider-composer.js merges
compat overrides without a global patch. pi-ai/api/openai-responses.js:75 reads it;
:264–265 emits max_output_tokens only when that capability is true. The setting
belongs to the model descriptor used for every request, including tool follow-up.
Later samplingParams can override named fields; the product-generated JSON-mode
sampling metadata contains only text.format and must never reintroduce the token
field. No payload rewriting proxy or extension heuristic is needed.

Actual installed ModelRuntime controlled captures passed for medium/high and both
initial and tool-return contexts. Twelve request bodies compare exactly: JSON mode
adds only text.format; the proposed calls-only setting additionally removes only
max_output_tokens. All fetches were intercepted with fictional responses; no
network request, inference or real credential access occurred. Evidence:
evidence/package-d/final-83af4d4/json-mode-sdk-offline/result.json. This proves SDK
request construction, not selected-account acceptance or token enforcement.

## Concrete contract choice

Recommended option: explicitly select a native calls-only profile. Its finite
resource unit is physical inference sends, shared across the existing Work chain;
each actual provider/tool-follow-up send consumes that cap. Unknown outcomes retain
their reservation. The profile declares no guaranteed output-token or monetary
ceiling. Pi may use a local context sizing value internally, but sends no unsupported
max_output_tokens field and never describes that sizing value as an enforced cap.
This preserves Pi/Luna, current Core commands, account and endpoint.

Alternative: require an enforced output-token bound. The present subscription
route cannot be declared supported for that demand; stop native dispatch before
credential/inference access. A different explicitly authorized route with verified
capability would require its own exact profile, access and evidence. No automatic
account, provider, API-key or billing fallback is part of either option.

## Minimal proposed implementation after selection

Add one explicit resource mode to the declared native profile; reject unknown or
inconsistent modes. Keep all existing finite call_limit admission and accounting.
Only an explicitly selected native calls-only mode sets supportsMaxOutputTokens:false.
A native hard-token-limit demand fails before dispatch. Existing API-key profiles
retain their requested max_output_tokens and lower-bound tests; no API-key behavior
is silently changed. Old profiles cannot silently be reinterpreted as calls-only.
Update installer/Start/profile instructions and diagnostics labels to state the
selected guarantee plainly. Keep JSON mode, exact raw C7/C8, refs, rights, CAS,
unknown-send stop, retention, restore and semantic review unchanged.

Before delivery: actual launcher captures must prove omission for discovery,
scoped execution and tool-return rounds; reached controls must restore the field
and bypass hard-limit refusal; assert inherited physical cap across all those
rounds, reopen and unknown. Prove old/inconsistent profiles refuse without a send,
and API-key field admission remains unchanged. Then freeze exact source/build,
run affected and mandatory gates, outside install proof and independent review.
Only the lead can admit any new finite live G14 after that evidence exists.

Official source:
[SiWC preview limitations](https://developers.openai.com/siwc/token-sharing-open-source/preview-limitations).

END_OF_FILE: PACKAGE-D-RESOURCE-PROFILE-PROPOSAL.md

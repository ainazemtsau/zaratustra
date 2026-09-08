# Result CLI output repair

invariant/class: result-discovery-json-survives-console-encoding

Installed additional restart evidence first failed in its diagnostic print under
Windows cp1252, after it had already recovered the saved Result and context.
The same risk was then reproduced in the NEW public result read command with
PYTHONIOENCODING=ascii and simulated prior-permission adapter. Raw locale-before:
exit1, empty stdout, UnicodeEncodeError. The new command emitted unescaped Russian
goal text through print. The fix serializes its JSON with ASCII escapes, preserving
all decoded values. locale-after on the same untouched DB: exit0, valid JSON.
The diagnostic standalone script separately writes its UTF-8 bytes explicitly.

fixed: the CLI change following implementation 90f35f6; exact commit in RESULT.
test: test_result_cli_discovery_survives_ascii_pipe_encoding (actual child process).

sweep:
- New result read: closed by installed RED/GREEN and native regression.
- New result submit: receipt has ids/revisions/digest/version/timestamp, no owner
  text; n/a to this Unicode-content failure. Actual console receipt retained.
- work open: closed by existing raw UTF-8 buffer write and exact installed stdout;
  its manifest and byte budget include actual delivered escaped content.
- projection-error receipt: existing json.dumps escapes content; n/a.
- Legacy records/history human-readable CLI branches at final print(output),
  outside this Result command delta: routed HOME:work7-locale-output-audit below.
  They are not used as the next Work context carrier and were not changed here.

HOME:work7-locale-output-audit — evaluate legacy owner-local JSON inspection
commands with non-ASCII saved fields under restrictive Windows stdout encoding.
This is a concrete class-sibling follow-up pointer, not a Direction CALL or a
claim that those commands are repaired. No live Direction state was written.

END_OF_FILE: docs/work7/OUTPUT-REPAIR.md

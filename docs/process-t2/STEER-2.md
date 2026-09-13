# Additional HOME technical feedback — T2

This is parent-session engineering feedback, not owner words, an approval, a new
scope or a binding review. The earlier JSON and wrong-target findings are resolved
in the current code; HOME independently repeated the foreign schema-2 target case
and observed workspace_collision with schema still 2 and the same workspace id.

One accepted T2 property still needs attention before handback: the current
ActivationPreview has proposal/source digests and low-level mutation requests, but
does not contain the actual ProcessDefinition or the first Work meaning. The console
prints only those bytes and then says "displayed process proposal". The steps,
dependencies, reasons, goal and acceptance are not in that displayed content.
An exact confirmation must let the person see the understandable actual proposal
being confirmed; hashes bind that content but cannot replace it. Include the actual
bounded proposal and first Work meaning in the shown, validated confirmation
surface, with readable UTF-8 for Russian text, and behaviorally verify that the
displayed content is the content authorized for activation. Keep the solution small;
no GUI or extra approval layer is requested.

Also demonstrate how the shipped path exposes the actual readable, copyable
research text: current `entry create request` reports only a canonical transport
file with escaped line breaks. An assistant/tool presentation of the exact text is
fine; don't require the owner to manually reconstruct JSON or claim a provider was
contacted. The transport and exact identity checks can remain. Choose the minimal
presentation seam, not a new framework or prescribed file format.

Before handback, also keep the installed-evidence label exact. The current
`tools.probe_process_t2` imports the editable checkout's public APIs and is valid
development evidence; that alone does not prove the built wheel's T2 path. The CALL
already requires installed/native evidence. Exercise both synthetic inputs using
the newly built wheel in an isolated test environment, with code import origins
recorded and no checkout/test-fixture imports in the installed runtime. Fixtures
may be supplied as external JSON/text inputs. Use existing installation-probe
mechanics, and label simulated local-chat confirmations honestly. T4 still owns
the full independent physical-reader synthesis; no personal installation or real
provider research is requested here.

This concern was added concurrently to an earlier note but is absent from the
retained docs/process-t2/STEER.md copy and remains in the actual source. Please
preserve this note intact as docs/process-t2/STEER-PRESENTATION.md after disposition;
continue T2 without asking for 'continue'. Fresh independent G5 follows handback.

END_OF_FILE: STEER.md



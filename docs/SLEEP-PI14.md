# Current Sleep host: Pi 1.4 only

The owner's 2026-10-22 amendment, «если что работаем только на pi 1.4», supersedes
the earlier Pi 1.3 baseline/separate Pi 1.4 compatibility arrangement. Current development
and qualification target actual Pi 1.4.0, Node 22.19.0, npm 11.6.2, Windows x64.
No further Pi 1.3 execution is authorized. Global Pi stays unchanged.

The scoped change pins the development SDK to exact 1.4.0. Its seven Pi packages move
to 1.4.0; Pi TUI requires marked-cjk-friendly 0.1.2 and npm marks its existing marked
peer accordingly. Unnecessary npm refreshes of existing AWS/Smithy entries were excluded.
All 22 production lock entries, their versions/integrities and four direct production
dependencies remain bytewise equal to d9b65518c157391f20586a36f32d87b438e3c51c.
Core, storage/schema, extension, skills, bootstrap and working instructions are unchanged.
The current synthetic live runner now defaults to and accepts only 1.4.0; historical
runner copies and evidence retain their original version labels.

The completed d9b handback is preserved in
[sleep-preview-RESULT-d9b6551.md](sleep-preview-RESULT-d9b6551.md). Original specification,
prior reports, failed attempts, ledgers and seals remain immutable. Prior Pi 1.3 results
are historical, rather than current-target L. Prior genuine Pi 1.4 results remain applicable
to identical runtime/working instructions/production dependencies, with exact original
source and host attribution. This metadata/qualification-host amendment makes no new L claim.

The published/installed toolchain candidate is `7c3861727befe7f18df855afb4c658abaa88d49e`.
`npm ci` and one `npm run deliver` passed against development Pi 1.4.0: 161 tests,
159 passed, two inherited Windows skips, zero failures. Deliver includes format, lint,
types, boundaries, build and disk tests; no second full check was run. File-symlink permission
and case-sensitive filename checks are the two skips. No compatibility correction was needed.
Fresh native package discovery/default startup passed as M with zero provider dispatches.
All 29 runtime/working-instruction files and all 21 compiled JavaScript artifacts match
the preceding qualified runtime. Actual development and global SDK/CLI versions are 1.4.0;
their code hashes match. Native production dependencies resolve inside the isolated package.
Current evidence is isolated at `C:/projects/zaratustra-v1-sleep-pi14-evidence-20261022`;
final documentation public/install identities are read back in `final-readback.json` there.
Normal native npm installation removes seven measured `peer: true` flags and reorders package
keys; lockfile bytes differ, while versions/integrities/dependency declarations are unchanged.
Public allowlisted evidence is in [sleep-pi14-evidence/](sleep-pi14-evidence/source.json).
The final handback supplies the final documentation SHA; the validated toolchain install is:

```powershell
Set-Location 'C:/projects/zaratustra-v1-sleep-pi14-evidence-20261022/install/cwd'
$env:PI_CODING_AGENT_DIR = 'C:/projects/zaratustra-v1-sleep-pi14-evidence-20261022/install/agent'
pi.cmd install --local --approve git:github.com/ainazemtsau/zaratustra@7c3861727befe7f18df855afb4c658abaa88d49e
```

Native `--approve` authorizes isolated local package configuration, not Sleep actions.
No production wrapper or configuration ceremony is introduced. Native authentication may
refresh normally; credential contents are not exposed, copied or manually altered.

| Qualification        | Attribution                                                                                                                                                                                  |
| -------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| New M                | Clean install, full deliver159pass/2skip/0fail, actual1.4 native resources/default startup, source/build/dependency equality passed                                                          |
| Reused L             | Actual Pi 1.4 only; preview low/high full-operation audits on runtime07510ec, earlier semantic/continuation/scoped stories retain their original pins in SLEEP-PREVIEW.md and linked reports |
| New L                | None required for unchanged production behavior; zero new model calls                                                                                                                        |
| Usage                | Linked prior 58 attempts/626 dispatches/USD24.3995008 Pi estimate; no reset or double count; billing/CLI cost unknown                                                                        |
| Remaining acceptance | Root's separate fresh physical independent review, full R1/T31 and owner usefulness remain separate                                                                                          |

Two audit helpers initially failed on assumptions (eight Pi packages rather than seven;
requiring native zod peer metadata to stay byte-identical). Corrected helpers passed; their
drafts, failures and other authoring/read setup errors remain in external task-events/logs.
These are M preparation errors, not native model attempts. The full development dependency
audit reports nine high advisories; the native production install reports zero. No unrelated
audit fix or blanket dependency upgrade was attempted.

All five known coordinator categories retain their prior mechanical dispositions: scope
recovery; mixed ownership; immutable binding/abort; repeated deferral grounds; inherited
sensitivity including progressed reviews, old pending intents and typed previews. No privacy
logic or acceptance criteria were changed by this host amendment. No independent PASS is
assigned by the implementation writer. `next: solmax`.

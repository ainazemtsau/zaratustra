# Current stdout file identity correction

Scope: the single developer-exporter LOW from independent rereview of exact
`4796fbf6c1702f5cc51b2314fa65809e1ae20bc3`. That rereview remains **PARTIAL**,
with its runtime/Work/material component PASS and completed model-created pair
attributed to that version. This correction assigns no independent PASS, owner
acceptance of C, full R1 completion or new product capability.

## Cause and bounded change

The exporter compared a realpath source with a resolved stdout spelling using
case-sensitive strings. On the qualified Windows filesystem, `C:` and `c:` name
the same file. Exact baseline RED accepts an empty snapshot of its redirected
stdout, publishes a zero-byte source/derivative and prints 32 bytes afterwards.

`node:fs.statSync(..., { bigint: true })` now compares the device/inode pair for
each existing real source and the declared current stdout file. `realpathSync`
resolves existing symlinks/junctions; stat identity also recognizes hard links.
BigInt avoids truncating file identifiers. No dependency or lowercase path map
is introduced. A differing spelling is irrelevant; distinct file identities are
not merged. The existing stdout-log argument must name the actual existing
redirected log. This is a trusted operator convention, not authentication of
arbitrary command-line claims or protection against hostile outside file swaps.

The guard runs before source reads and before publication creates its new output
directory. It retains the explicit error `Current exporter stdout cannot be an input`.
Only the exporter and its behavioral tests change executable inputs. Core, Pi
adapter, skills, parsers, storage/schema, dependencies and all other instructions
remain unchanged. No runtime resource imports this developer script.

Neighboring comparisons were inspected: `existsSync(output)` already asks the
filesystem whether the destination exists; containment uses realpath plus the
platform's `relative`; the Set rejects duplicate declared entry names, not file
identity. These do not decide whether a source is current stdout. No global
case-folding or general filesystem abstraction was added. Sealed source length
and digest checks, the second read before publication, sanitation, canonical LF,
JSON transforms and gzip are retained.

## Checks on real Windows

All subprocess cases actually redirect stdout to an open file, wait for exit,
then inspect the completed log, stderr, output directory and manifest. No source
text matching substitutes for execution. The separate Python probe tests aliases
on the source side; repository tests also test aliases in the stdout argument.

| Case                                                          | Observed result                                                                                                |
| ------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------- |
| Exact 4796fbf exporter, C:/c: stdout alias                    | RED reproduced: exit 0, output created, manifest 0 bytes versus finished stdout 32 bytes                       |
| Same stdout spelling                                          | GREEN: exit 1, explicit refusal, no output or manifest                                                         |
| Different drive letter case                                   | GREEN: same refusal and absence                                                                                |
| Different path case                                           | GREEN: same refusal and absence                                                                                |
| `/`, `.` and `scratch/..` spelling                            | GREEN: same refusal and absence                                                                                |
| NTFS hard link                                                | GREEN: same refusal and absence                                                                                |
| Directory junction                                            | GREEN: same refusal and absence; created without privilege changes                                             |
| Different completed file                                      | GREEN: exit 0; raw and derivative length/hash exact; CRLF to LF exact                                          |
| Source changes after sealing: length, then same-length digest | GREEN: exit 1 before output creation                                                                           |
| Source changes just after first read                          | GREEN: second validation rejects before output creation; test-only preload, no exporter hook                   |
| File symlink                                                  | UNAVAILABLE: Windows error 1314 / Node EPERM; no permissions changed                                           |
| Distinct case-only file names                                 | UNAVAILABLE in this case-insensitive directory; regression runs on a filesystem supporting such distinct names |

Checkout `npm run check` and `npm run deliver` both passed: 46 tests, 44 passed,
2 explicitly skipped, no failures; format, lint, types, dependency boundaries,
build and RESULT structure passed. `check-01.log` and `deliver-01.log` are finished
originals. The installed affected suite has 10 tests: 8 passed, the same 2 skipped.
All ten Python GREEN subprocess controls also passed using the installed exporter,
with cwd and all inputs/output outside the checkout. No parser change justified
repeating old model/material/upgrade histories; unchanged inputs and the full
checkout regression suite preserve their exact version attribution.

## Published installation and fixed evidence

Code candidate, publicly pushed and natively installed:
`6ca077ff7fd9b8a0fdcd862dc9ed406ca20c20ee`.
The final containing commit adds documentation and fixed synthetic evidence only;
its exact public and installed SHA are read back in local `FINAL-READBACK.json`
after native reinstallation, avoiding a self-referential SHA in committed text.
That final check verifies equality of every executable/configuration/test input
with this candidate and repeats the installed exporter controls.

Candidate [installed identity](c-evidence/stdout-alias-20261020/candidate-identity.json)
compares all **779 tracked files** with exact public Git bytes. Sole exception:
native Pi/npm removes six `peer:true` fields from package-lock.json, for
@typescript-eslint/parser, acorn, eslint, typescript, undici and zod. No versions,
resolved URLs or integrity changes. The installed tree is **not fully clean**.
The [unchanged-input proof](c-evidence/stdout-alias-20261020/runtime-equality.json)
checks 50 other committed implementation/configuration/fixture inputs against
4796fbf, including all Core/adapter/skills/parser/schema/dependency inputs.

The [new manifest](c-evidence/stdout-alias-20261020/manifest.json) has **117** entries,
all checked against available completed raw sources and derivatives, including
the [exact-base RED](c-evidence/stdout-alias-20261020/red-base/verification.json),
[checkout GREEN](c-evidence/stdout-alias-20261020/green-checkout/verification.json),
[installed GREEN](c-evidence/stdout-alias-20261020/green-installed/verification.json),
[commands/probe](c-evidence/stdout-alias-20261020/probe.py),
[check log](c-evidence/stdout-alias-20261020/check-01.log) and
[deliver log](c-evidence/stdout-alias-20261020/deliver-01.log).
Every producer exited before sealing. Current public-export stdout is not among
its own inputs. Derivatives use declared path substitutions and canonical LF;
originals remain in the separate evidence directory and are never overwritten.
The pre-existing broken RED manifest is retained as an artifact inside this new
export, not represented as a correct manifest of its completed RED stdout.

[Attempt accounting](c-evidence/stdout-alias-20261020/attempts.json) includes the
expected product RED and an early observer failure: the first equality verifier
assumed checkout lockfile LF, then found pre-existing CRLF. Only the verifier was
corrected to disclose this exception. An initial patch submission was rejected
before edits and resubmitted; no hidden product/test failure or model retry.

## Evidence and reproduction

New local originals only:
`C:/projects/zaratustra-v1-c-stdout-alias-evidence-20261020`.
Reviewer originals remain at
`C:/projects/zaratustra-v1-c-rereview-evidence-20261020`; they are read-only inputs.
The new probe saves exact baseline Git-blob identity, RED and GREEN stderr/logs,
exit codes and source/derivative checks. Its `cost.json` records **0 attempts,
0 provider requests, USD 0 Pi estimate**. No Pi model session or credential access.
All old ledgers stay closed.

```powershell
$r = 'C:/projects/zaratustra-v1-c-stdout-alias-evidence-20261020'
$repo = 'C:/projects/zaratustra-v1'
python "$r/probe.py" cases "$repo/scripts/export-evidence.mjs" fresh-checkout green
$env:ZARATUSTRA_TEST_ROOT = "$r/check-tests" # create this directory first
# In the checkout:
npm run check
npm run deliver
# After native installation in a separate config; $package is that installed repo:
python "$r/probe.py" cases "$package/scripts/export-evidence.mjs" fresh-installed green
```

Each probe label must be new. Run from outside checkout/package storage. Native
installation uses an exact public SHA, separate PI_CODING_AGENT_DIR and
ZARATUSTRA_HOME, as in [REPRODUCE](REPRODUCE.md). No login/model command is needed
for this mechanical qualification. Finished explicit input lists are sealed only
after their producers exit; exporter stdout stays outside that list.

The 327 historical corrected entries and 136 previous-fix entries were checked
against their available raw and derivative lengths/hashes: exact. Their manifests,
historical empty derivative and explanation of the missing old empty raw snapshot
are preserved. This new alias RED is separate evidence, never a relabeling of
the original historical self-log mismatch.

The [historical digest check](c-evidence/stdout-alias-20261020/historical-provenance.json)
and [728 protected-artifact check](c-evidence/stdout-alias-20261020/preservation.json)
preserve these facts, reviewer reports/reproduction and selected closed ledgers.
No reviewer directory was a target of writes. The historical return is preserved
verbatim in [C-RESULT-4796fbf](C-RESULT-4796fbf.md), with its original trailer.

Published runtime inputs equal the base Git blobs. A pre-existing checkout-only
exception is disclosed: package-lock.json has CRLF (170512 bytes), while its
unchanged committed LF blob has 165767 bytes. It was not rewritten; Git reports
no dependency delta. Installed-tree drift is checked separately, not assumed clean.
No broader filesystem/platform, concurrent hostile mutation or symlink result is
claimed. The open dev-stack braces advisory remains separate. Outcome D remains
the first unimplemented result; no D/E work was done.

END_OF_FILE: docs/C-STDOUT-ALIAS.md

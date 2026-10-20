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

Checkout `npm run check`: 46 tests, 44 passed, 2 explicitly skipped, no failures;
format, lint, types, dependency boundaries and build passed. Mandatory deliver and
native installed qualification are recorded with final delivery below.

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

Published runtime inputs equal the base Git blobs. A pre-existing checkout-only
exception is disclosed: package-lock.json has CRLF (170512 bytes), while its
unchanged committed LF blob has 165767 bytes. It was not rewritten; Git reports
no dependency delta. Installed-tree drift is checked separately, not assumed clean.
No broader filesystem/platform, concurrent hostile mutation or symlink result is
claimed. The open dev-stack braces advisory remains separate. Outcome D remains
the first unimplemented result; no D/E work was done.

END_OF_FILE: docs/C-STDOUT-ALIAS.md

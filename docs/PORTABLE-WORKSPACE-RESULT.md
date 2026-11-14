# Portable workspace implementation evidence

The owner approved `portable-workspace` on 2026-11-04. This implementation was
verified on Windows x64, Node 24.22.1 and Pi 1.4.0 in isolated synthetic
workspaces. The working tree is based on commit
`858224684971f5b5adb9feee3026ca7e131df1d1`.

The independently installed production package and the real Pi walkthrough both
identified product sources as
`sha256:200abbee6d46afb6b2b835452a2b4b69a4a5e4d9d3f6215b34c60ac26f10135e`.
The package version remains 0.7.7 for this development change. The build records
and checks its separate compiled-runtime inventory in `dist/build-manifest.json`.

| Focused checks                    | Passing evidence                                                                                                                                                                                                                 |
| --------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Workspace installation            | 19 cases covering initialization, owner preservation, repeat/update plans, exact conflicts, aliases, interrupted publication, native attachment uncertainty, alternate managed homes, torn technical journals and UTF-8/BOM/CRLF |
| Bundle files                      | 13 cases including link subcases, complete inventories, selected-version views, same-file identity/mode preservation, partial-write UNKNOWN and guarded compensation                                                             |
| Skill Core                        | 12 registry/access/recovery cases and two subsequent transitive-consumer cases, including long complete manifests, compact invocation references, original access grounds, archive reservation and separate/same-path adoption   |
| Pi integration                    | 10 cases using actual extension entry points and Core/files callbacks, including request-local Activity replacement, native previews, source paging, access denial, rollback and delegated Sleep publication                     |
| Sleep controller                  | 37 cases across `sleep-v2` and `sleep-skills`, including budget/phase preservation, exact permits, shared-skill review candidates and later benefit checks                                                                       |
| Generation and end-to-end rebuild | Eight cases across `workspace-generation` and `portable-workspace-integration`, covering explicit transition, original rows/sources/paths/UNKNOWN, dirty-before retention, corruption refusal and independent projection rebuild |
| Existing Method/effect behavior   | 14 selected cases across `experience` and `effects`. A denied-selector diagnostics leak was fixed and its original failed case passed unchanged on a targeted rerun                                                              |
| Existing corpus behavior          | Six selected cases covering retained revisions/raw material, clone identity/epoch, backup, interrupted restore and UNKNOWN. Two fresh-generation assertions were updated to the approved control 4/schema 11 and passed on rerun |
| Managed documents                 | Two existing cases covering external drift/adoption preserving identity and file-primary Sleep retaining previous document bytes                                                                                                 |

Counts include focused reruns after repairs. They describe the cases exercised
throughout implementation rather than one full historical qualification run.
Tests use `node --import tsx --test --test-concurrency=1`. Component files are
`tests/workspace-installation.test.ts`, `tests/skill-bundle-files.test.ts`,
`tests/skill-core.test.ts`, `tests/portable-pi.test.ts`, `tests/sleep-skills.test.ts`,
`tests/sleep-v2.test.ts`, `tests/workspace-generation.test.ts` and
`tests/portable-workspace-integration.test.ts`.

The preservation subset used test-name patterns in `experience.test.ts`,
`effects.test.ts`, `corpus.test.ts`, `documents.test.ts` and
`memory-v2-documents.test.ts`. Review covered installation, storage, access,
recovery and shared-consumer concurrency. The reported material findings were
repaired and rechecked by independent readers.

The actual predecessor writer was also loaded from the baseline commit's public
TypeScript sources in a separate synthetic source directory. Opening the new
managed workspace failed at its control-format validation. The complete corpus
inventory and active-control bytes remained identical before and after that
attempt.

The product tarball was built locally and installed offline into a fresh
temporary consumer directory with production dependencies, `--omit=dev`,
`--omit=optional` and `--ignore-scripts`. Installation added 16 packages. Pi and
typebox were physically absent. The installed `dist/cli/index.js` initialized a
workspace whose subsequent inspection returned `current`. The tarball includes
the compiled entry, build manifest, parser worker, source extension and portable
workspace resources.

The Codex-to-Pi walkthrough used `scripts/portable-workspace-smoke.mjs prepare`.
In this Codex session the installed root, system, owner, Activity and skill files
were read from the generated workspace. The ordinary document preserved both
synthetic dates, reported the two observations and their arithmetic mean of
22.5 minutes, and linked the original `notes.md`.

Running the script's `verify` phase then invoked the real Pi CLI to attach the
local product and loaded it through the real Pi SDK. Pi read the same
`activities/synthetic-health/AGENTS.md` and
`skills/personal/synthetic-health-summary/SKILL.md`. Its registered `zara_map`
returned schema 11. Source notes and the ordinary result survived attachment.
The SDK fixture supplied project trust explicitly, used a separate agent
directory and disabled network/model dispatch. Its model-call counter was zero.
The attach command uses Pi's command-scoped `--approve` for local configuration,
while later runtime project trust is a separate native decision.

Mechanical checks passed through the project scripts for formatting, types,
lint, dependency boundaries and build. The boundary check covered 71 modules
and 248 dependencies. `npm run openspec -- validate portable-workspace --strict`
also passed. Locked dependency versions were preserved.

Some Windows sandbox runs refused rename, hardlink or junction setup with
`EPERM`. Those synthetic file tests were rerun with automatically reviewed
escalation, or with temporary roots under ignored `_scratch/`, and passed.
File publication assumes the documented single-writer window for external
editors. Managed reservations serialize participating product operations.

Owner usefulness acceptance and real-workspace rollout remain explicit review
decisions. A real ZT transition requires its own authorization, verified full
backup, private Health/Web path comparison and cutover decision. Main OpenSpec
specifications can be synchronized after implementation review. The active
change retains its reviewable proposal, deltas, design and task history.

## Installed Pi startup follow-up

The initial archive qualification exercised the installed CLI, while the Pi
walkthrough used the source checkout. That combination missed an installed
extension startup failure: npm omitted the root `package-lock.json` which the
extension eagerly read for its build-input provenance.

The build now retains the exact lock bytes as `dist/dependency-lock.json`, covered
by the compiled inventory. Pi uses the source lock when present, preserving
checkout use without a build. An installed package uses the retained resource
only after validating its compiled manifest. The logical provenance key remains
`package-lock.json`; this records the build input, not an assertion that npm's
consumer-resolved dependency tree equals the development tree.

Four focused tests in `tests/package-extension.test.ts` passed: source loading
without `dist`, exact packaged bytes, absent/corrupt retained bytes, and stale or
missing compiled output. `node scripts/packaged-extension-smoke.mjs` then packed
and installed the actual archive offline with production dependencies, optional
peers absent, and loaded its source extension through Pi 1.4.0. The installed CLI
initialized the synthetic project; the native loader reported no extension
errors and registered `zara_map`. No model runtime, conversation, managed store
or network dispatch was created. The root source lock remained absent.

The final archive qualification identified product sources as
`sha256:bf1351a229f05b44f0c3fb76eb5168622110df47024756fedd31052f6cd1919d`.

Adjacent Pi regression checks also exposed an existing compensation mismatch:
Core previewed the complete operation/access scope, while the adapter verified
only three fields. `SkillRegistry.verifyCompensation` now verifies the same full
Core payload before native dispatch; final transactional consumption remains.
The focused native test passed with an approved wrong-operation preview causing
zero filesystem dispatches, followed by exact restoration under the correct
approval and a successful subsequent activation.

All ten adjacent cases in `tests/portable-pi.test.ts` passed across focused runs.
Windows sandbox `EPERM` failures were rerun with reviewed escalation. The hook
fixture requires its native temporary project outside the product tree; placing
`TEMP` beneath the product correctly triggers the containment refusal. These
environment failures are distinct from the repaired compensation failure.
Types, lint, dependency boundaries and build passed after the source repairs.

## Native skill discovery follow-up

The earlier import-only acceptance missed native resource diagnostics. Replaying
the actual installed archive reproduced four product warning groups: eight
pairwise collisions between `.pi` routes, `.agents` routes and package skills,
with no extension-load error. Task 5.4 was reopened. The prompt-time name filter
was removed because it ran after native discovery had already recorded warnings.

The installer now emits shared `.agents` routes and retires only recorded,
unchanged `.pi` copies through its guarded plan. Portable attachment disables
only its exact package's fallback skills. Original package skill declarations
remain available for standalone installations. Explicit owner filters and
autoload deltas are conflicts rather than implicit overrides. Attachment records
the exact native-before and filter-after bytes/identity; UNKNOWN completion never
reinstalls the package, and a confirmed receipt cannot replay a prior write after
an owner restores its before-state.

Workspace installation checks passed 27 cases across focused runs, including
retirement/owner conflicts, unrelated settings, interrupted normalization,
confirmed readonly replay and hoisted SDK selection. Nine adjacent Pi cases
passed together. Four dependency-provenance cases and four actual native skill
discovery cases passed. Independent review found the confirmed-replay defect
before rollout; the added regression now proves rejection without native or
file redispatch.

Actual archive acceptance passed on the qualified Pi 1.4.0 SDK and separately on
the installed Pi 1.5.0 SDK. Each clean fixture had zero extension errors/warnings,
skill, prompt and theme diagnostics. Four system routes, the scoped personal
route and unrelated project/user skills were preserved. Legacy discovery still
loaded four package skills; a deliberate owner collision remained visible.
These 1.5 observations cover startup/discovery, not full managed-runtime support.

The additional peer-present consumer installs real Pi 1.4.0 offline and calls
`attachPi` without a test installer callback. This caught the SDK's import-only
exports shape: CommonJS resolution cannot provide its entry, so executable
lookup now inspects conventional peer package areas and checks the exact native
name/version. The real default installation and subsequent clean discovery pass.
Model and network dispatch counters remain zero; the fixtures create no managed
store or conversation.

### Pi 1.5.2 managed adapter compatibility

On Windows x64 with Node 24.22.1, `npm run test:package -- --sdk-root <installed-pi-package> --managed`
passed against the owner's installed Pi 1.5.2 and the actual installed Zaratustra
npm archive. The probe recorded the exact executable passed to the native attach
subprocess and matched it to Pi 1.5.2's declared CLI. The fallback probe similarly
matched the hoisted Pi 1.4.0 peer with `PATH` empty. Both attachment probes reported
zero extension, skill, prompt and theme diagnostics and four product skill routes.

- The native Pi SDK confirmation callback approved an exact bundle registration and
  edit. A negative answer left the original bytes in place and blocked application.
  In TUI mode the same SDK persisted the exact review in the conversation branch
  before presenting the scripted native question and recording the refusal.
- A separately confirmed rollback restored the original bytes, including line endings,
  and the original content hash in a new bundle revision (revision 3).
- A real bounded Sleep child session exposed only its five allowed tools. It read one
  exact saved record, recorded analysis based on that revision and finished as
  `completed` / `no_change` after three generations. UI and model replies were scripted
  and no real provider was contacted. Physical TUI input and live model usefulness were
  outside this run.

The targeted suites covered 74 checks. The linked-path test required a separate
rerun because the sandbox denied creation of a hardlink. It passed when run with
permission to create the link in the synthetic fixture. Type checking, lint,
dependency boundaries, build and strict OpenSpec validation passed.

### Release 0.8.0

The release archive repeated the packaged Pi 1.5.2 managed scenarios and the
Pi 1.4.0 peer attachment check, with zero native startup diagnostics. All four
main capability specs were synchronized and passed strict validation.

The final observed product fingerprint is
`sha256:9e8a3d37bf7994b7240bcda548acc5c28731c8f72c273abef40cc986d97f15a4`.
`npm run test:package` is the focused repeatable gate, and full `check` includes
the same installed-archive acceptance. Source tests, OpenSpec validation and
native diagnostics describe different evidence; none alone establishes a clean
user workflow or owner acceptance.

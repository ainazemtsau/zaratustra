# Ordinary project Pi startup

The owner-authorized startup fix replaces mandatory environment/launcher setup for
new ordinary projects. It changes directory selection in the Pi adapter only.
Core, schema 6, existing explicit deployments and approval policy remain intact.
This assignment supersedes the earlier E3 directory setup recommendation, not the
full specification or its retained provenance/access guarantees. Full R1, F,
independent review and owner usefulness/T31 remain separate.

## Install and daily use

In the intended project root, install the selected public commit once:

```powershell
pi install --local git:github.com/ainazemtsau/zaratustra@<exact-public-commit>
pi
```

Review the package and use native Pi project trust. Choose/authenticate the model
in Pi normally. There is no Zaratustra launcher, additional AGENTS file, mandatory
status command, per-launch environment setup or requirement to disable extensions.
Daily use remains conversation. Close Pi and run `pi` in the same folder to reuse
existing memory without resuming a transcript.

| Default path relative to native Pi cwd | Purpose and lifetime                                                                                                     |
| -------------------------------------- | ------------------------------------------------------------------------------------------------------------------------ |
| `.local/memory`                        | DiskStorage identity, active epoch/control, SQLite, original materials and staging; persistent across sessions/processes |
| `.local/imports`                       | Permitted input directory; original files stay here while imports retain managed copies                                  |
| `.local/output`                        | Designated native write/edit output; existing exact preview, native confirmation and postcondition checks apply          |
| `.local/backups`                       | Designated bundle destination; full-read/write administrative policy still applies                                       |

The adapter uses native `ctx.cwd` and `ctx.isProjectTrusted()`. It does not search
for a Git root or take a memory path from model tool arguments. A different cwd,
including a subfolder, gets its own default memory. Always start in the intended
project root. A personal/global package also requires project trust before default
creation or opening. Project package declarations themselves remain trust-gated
by Pi. No migration or automatic relocation is performed.

`.local/.gitignore` is exclusively created with `*` before data roots. The root
ignore file is untouched. An existing bounded regular ignore file is preserved
only when it contains a whole-directory `*` or `/*` rule and no negations;
otherwise startup refuses without overwriting it. This protects untracked data,
not files already tracked by Git or deliberately force-added by the user.

## Compatibility and authority

An explicitly present `ZARATUSTRA_HOME` retains the legacy absolute-home profile:
optional `ZARATUSTRA_IMPORT_ROOTS` defaults to `[]`; output and backup roots remain
optional and retain their existing validation. The home is independent of cwd.
Existing deployments do not acquire `.local` roots. An empty/relative home fails;
backup/output/import overrides without a home fail instead of silently selecting
new memory. Set all legacy directory fields deliberately, or remove all of them
to select project defaults. Do not remove configuration expecting migration.

Default scopes are still `[]`. Workspace memory and supported imports work;
full backup/export requires explicitly preconfigured `restricted:read`; restore,
full body deletion and cleanup retain their full-read/write requirements. Native
confirmations remain mandatory for protected actions. RPC `hasUI` alone grants no
owner authority; a real TUI or explicitly registered synthetic controller remains
required by `dialogAuthority`. The fix never sets a test controller or input contract.

Native input hooks can receive earlier extension transformations. Default sources
remain `observed_stage_only`, `original_keystrokes:false`, owner-ineligible, with
exact observed text retained. They support ordinary Evidence and grounded Knowledge;
they cannot certify `user_feedback`. Explicit first-untransformed deployment
contracts retain their existing meaning. Other extension inputs/messages are retained.

All default roots are checked before creation. Links/junctions, device aliases,
package/Pi-cache overlap and nesting within existing memory/control ancestors are
refused. These are local managed-surface checks, not OS isolation against same-user
tools or malicious extensions. One trusted writer and no outside output writer
remain the supported profile. Existing known corrupt or missing databases are
refused by DiskStorage, never reset. Removing all storage/control metadata manually
is outside the recovery protocol and cannot be detected as an intact known store.

## Focused reproducibility

Use Node 22.19.0, npm 11.6.2 and native Pi 1.3.0 on Windows x64. No dependency
update, installer, auth system, model service, workflow engine or Core/schema change
is needed. The actual official local declarations were checked for `cwd`, `mode`,
`isProjectTrusted()` and public `getAgentDir()`; native loader docs were checked
for project package/trust behavior.

```powershell
npx tsx --test tests/startup.test.ts
npm run deliver
```

The new suite launches fresh Node processes using official `DefaultResourceLoader`
and `createAgentSession`, with normal package declarations in `.pi/settings.json`.
It does not use `noExtensions` or an additional extension path workaround. Synthetic
personal peer extensions test transformed input and preserved context. Calls enter
real registered tools; no provider/model prompt is dispatched. The synthetic TUI
mode injection verifies confirmation mechanics and is not owner testimony.

For installed proof, run `scripts/startup-native.mjs` with the absolute official
SDK entry, installed package root, action (`init`, `read`, `health`, `inspect`,
`untrusted` or `backup`) and new report path. Run it from the synthetic project
with normal project package discovery. `init` expects a synthetic `fixture.md`
in the permitted imports directory; it commits observed Evidence, Activity and
Knowledge, retains an import and verifies a confirmed native output. `read` is a
separate process with no old transcript. `backup` needs preconfigured full-read
scope and does not widen ordinary defaults. Exact native commands, public/installed
identities and retained results are recorded with the final readback.

Evidence lives only in the newly created
`C:/projects/zaratustra-v1-startup-evidence-20261021` and new isolated synthetic
fixtures. Prior committed evidence is preserved by Git identity; no historical
artifact recopy/reseal is required. The initial two focused runs retain fixture/API
errors, including the `.mjs` peer discovery assumption and missing search match
mode, rather than overwriting successful-looking evidence.

No live model proof is needed for directory selection: zero provider dispatches,
zero model attempts, USD 0 Pi estimate for this assignment. This does not establish
semantic model reliability, independent PASS, owner acceptance or T31.

next: solmax

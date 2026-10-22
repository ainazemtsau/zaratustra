# Reproduce the isolated Sleep qualification

Use a new visibly synthetic root outside checkout and package storage. Preserve existing
roots, ledgers, failed attempts and source bundles. All data in these fixtures is synthetic;
never use ZT, real Health or other personal workspaces. The source contract is SLEEP-CONTRACT.md.
Root chooses an independent fresh request/rubric after the implementation handback.

Install the pinned host in isolated test tools with ordinary npm, without changing global Pi:

```powershell
npm install --prefix C:/projects/zaratustra-sleep-synthetic/test-tools --no-audit --no-fund --save-exact @earendil-works/pi-coding-agent@1.3.0 typebox@1.3.27
```

Create the new cwd and agent directory before launching commands there. Use that isolated
agent directory with the native Pi 1.3.0 CLI, and the exact published development SHA:

```powershell
$env:PI_CODING_AGENT_DIR = 'C:/projects/zaratustra-sleep-synthetic/agent'
Set-Location C:/projects/zaratustra-sleep-synthetic/cwd
node C:/projects/zaratustra-sleep-synthetic/test-tools/node_modules/@earendil-works/pi-coding-agent/dist/bundle/cli.js install --local --approve git:github.com/ainazemtsau/zaratustra@afb3b5158aaf43bf8eb37821d90dd1b3ed2fc969
```

`--approve` is native project trust for the explicitly reviewed synthetic package, not a new
Zaratustra daily interface or an authorization for memory/effects. Wait for installation to
finish. Check the resolved Git HEAD and run the installed scripts/resources.mjs with
ZARA_PI_SDK pointing to the isolated host's dist/index.js. Verify exactly one product extension,
three skills and zara_sleep_batch before any model call. Never use an unverified global Pi.
Production startup remains ordinary trusted project Pi with its existing .local defaults.

For operator qualification, use the existing native authPath through ModelRuntime normally;
never print/read/copy credential contents. ZARA_AUTH_PATH may name that existing native store
for these test runners. Keep settings/models/session/output files isolated. The SDK and public
package are installed outside the developer checkout; no developer node_modules are used.

The published scripts/sleep-fixture.mjs prepares visibly synthetic prior cases through the
installed public Core. Its modes seed, next, feedback and scoped are mechanical preparation,
not model execution. It accepts installed-package path and a new root under the named evidence
namespace; choose a fresh subdirectory or a new root whose name includes
`zaratustra-v1-sleep-evidence-20261022`, and read the source before running it. No scripted model replies, classifier or second
Pi protocol is used. scripts/sleep-upgrade.mjs reuses the existing filled-upgrade fixture for
seed on exact predecessor 171415b, verify on schema 7 and old-reject through the prior writer.
The existing e3-filled-spine.mjs runner provides exact closed-synthetic backup/restore readback.

Each real scenario uses installed scripts/sleep-live.mjs with an external JSON configuration:
agentDir, cwd, home, output, outputRoot, backupRoot, scopes, prompt and usagePath. All state/output
paths must be synthetic and outside package storage. Supply a NEW uncapped usage ledger with
provider openai-codex, model gpt-6.1-sol, thinking medium, uncapped:true and cumulative counters;
continue that same ledger for all errors/retries, never reset it. There are no total limits.
The script uses normal resource discovery, native SDK session/event settlement and an empty
in-memory transcript each process. It fails before dispatch on the wrong Pi or missing resources.

Required stories: finite global review of prior cases; grounded small correction; intentionally
lost successful checkpoint reply via dropSleepCheckpoint:true, then fresh-process continuation;
ordinary suitable work without a Method reminder, exact selected version and separate observed/
reported/model assessments; late reported negative feedback and compatible revision preserving
negative history; Activity-only shared-change native refusal and addressed deferral, then a fresh
explicit request/exact native confirmation; no-new-ground review with no invented improvement or
automatic next cycle. dialogReplies are explicitly synthetic native-controller callbacks, not
owner testimony. Do not inject hidden source facts/answers into prompts, snapshots or routing cards.

Inspect actual canonical rows, historical versions, supporting assessments, dispositions, Changes,
receipts, source metadata and native events. A zero process exit, fluent answer or prepared fixture
is insufficient. Preserve all raw attempts externally; publish only an allowlist of synthetic
readback/identity/usage summaries, selected receipts and source equality. Final runtime/instruction/
test bytes must equal the live-qualified public snapshot even when later documentation adds commits;
read back the final public and native-installed SHAs and disclose normal peer-flag lock differences.

The exact final documentation commit/native-installed commit and after-install readback are
recorded after publication in the delivered external `final-public-installed.json` and final
handback. The immutable live-qualified runtime pin above remains reproducible.

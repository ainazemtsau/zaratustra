# Reproduce E2 qualification

Use the versions/profile and boundaries in [E2-VALIDATION](E2-VALIDATION.md).
Final live code ref:d6a3187163c385c3c45f5fb89f7279dfbf636ced. Original0d6c9a2 failed independent H1 and remains historical;85e44c1 is the intermediate correction. Final handback
ref is recorded by the terminal local FINAL-READBACK.json. Only the public
codex/zaratustra-v1 route is authorized; no force/main/tags/releases.

1. Read AGENTS, full immutable specification, DEVELOPMENT and E1/E2 handbacks.
   Check accepted exact E1 gate before any product mutation. Verify both normative
   hashes recorded in DEVELOPMENT. Check fresh HEAD/status/remote and coordination.
2. Checkout qualification: npm ci, npm run deliver. Existing Windows skips are not
   waived successes. Use a new ZARATUSTRA_TEST_ROOT for disk tests.
3. Native isolated install: set PI_CODING_AGENT_DIR to a new declared external agent
   root, then pi install git:github.com/ainazemtsau/zaratustra@<exact-public-sha>.
   pi list and scripts/c-identity.mjs <installed-package> <new-output.json> establish
   actual installed files and native lock metadata. Do not call a failed clone installed.
4. Use the supported native Pi SDK and ModelRuntime authPath; never copy/read auth
   contents. ZARA_PI_SDK names the native host dist/index.js. ZARA_AUTH_PATH names
   its supported existing auth file only. Do not change the actual selected recipient
   for a demonstration or send a test request to an untrusted provider.
5. From an external cwd execute installed scripts/e2-ingress.mjs <pkg> <new-out>
   and scripts/e2-native.mjs <pkg> <new-out>. Both are mechanical, zero-network SDK
   controls. Public createEditTool/createWriteTool supply native semantics. The sealed
   e2-recipient-choice-02.mjs derivative adds the positive recipient-return control;
   source and derivation are recorded. Its first wrong-oracle run remains visible.
6. Filled migration: native-install exact E1 0b45c085 into a separate agent root.
   Run installed scripts/e2-upgrade.mjs seed <E1pkg> <new-home> <proof-dir> once.
   Then candidate script verify <E2pkg> <same-home> <same-proof> and old-reject
   <E1pkg> <same-home> <same-proof>. Never reseed the upgrade target or replace its
   database. E2 effects tests additionally inject backup/transaction/manifest faults.
7. Installed test modules are executed from an external cwd by external pinned
   tsx4.20.6. Copy/hash-check only test fixtures/c and exporter into that cwd because
   existing tests intentionally resolve those assets against cwd. For effects/extension,
   external tsconfig paths map Pi host peer to its native installed dist/index.js;
   do not npm-install development peers into the native product. See sealed logs and
   installed-fixture-copy.json. All src/test imports still point to actual public package.
8. Real L uses existing installed scripts/live.mjs <ordinary-scenario.json>. Declare
   separate scopes[], or restricted:read/write synthetic profiles, output/import roots,
   isolated agent/home/cwd/output and one non-reset budget before starting. The
   historical E2 ledger is closed and must not be reset/replayed as a new budget.
   Any additional qualification needs its own authorization/accounting or continuation
   of the same ledger within caps. Fixed model openai-codex/gpt-6.1-sol, medium.
   Scenarios-resumed preserve agent-root recovery and authority clarification; scenarios-batch/final-code preserve affected post-review repeats; the
   original scenarios and failed attempt01 are retained. No mutation JSON is supplied.
9. Faults: dropNativeResult exits86 after native bytes before product result receipt;
   next ordinary prompt contains no old ID/transcript and asks to inspect, never retry.
   changeFileBeforeDispatch modifies only the declared synthetic target after dialog,
   before dispatch, to test stale binding and a second decision. This is controlled
   fault injection, not concurrent outside writers in the qualified dispatch path.
10. Export/drift: after L06 completes, retain its full original bytes; insert only the
    lamp-colour sentence recorded in skill-drift/injection.json. L07 imports a new
    canonical version after decision; L08 separately regenerates. verify-live-03.py checks the first10 attempts; verify-batch-live.py and verify-final-live.py check corrected connected batches, final v3 bytes/history, all18 calls/dispatches and non-reset costs.
11. Seal a fixed finished synthetic source list with byte lengths and SHA256. Run
    scripts/export-evidence.mjs <sealed-list> <new-output> <current-stdout-log>.
    Never seal live exporter stdout, credential/config files, databases or private raw.
    Verify every derivative/source digest and scan paths/secrets before public commit.
12. Before final freeze/publication read E2-COORDINATION. Run deliver. Publish once,
    native-install exact final public SHA in new roots, compare the union of every
    runtime/instruction/test input to the live candidate and every installed tracked
    file to its public object. Only documentation/evidence can differ without affected
    L rerun. Keep terminal FINAL-READBACK outside Git; do not edit root-owned final gate.

The native public package, dialog helpers and runner are the protocol. These scripts
are developer qualification fixtures, not a new product UI/control service or owner
impersonation. Prior E1/reviewer/raw directories and budgets stay untouched.

END_OF_FILE: docs/E2-REPRODUCE.md

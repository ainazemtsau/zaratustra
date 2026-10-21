// Qualification fixture only: copy an explicitly CLOSED synthetic predecessor,
// then exercise the product's real SQLite bundle/restore. Not a user backup path.
import assert from "node:assert/strict";
import { createRequire } from "node:module";
import { pathToFileURL } from "node:url";
import { resolve, join, relative, isAbsolute } from "node:path";
import {
  existsSync,
  mkdirSync,
  cpSync,
  writeFileSync,
  readFileSync,
} from "node:fs";
const [pkgArg, sourceArg, outArg] = process.argv.slice(2),
  pkg = resolve(pkgArg),
  source = resolve(sourceArg),
  out = resolve(outArg);
assert.ok(!existsSync(out));
assert.ok(!existsSync(join(source, "writer.lock")));
assert.ok(
  !existsSync(join(source, "zara.sqlite-wal")),
  "Predecessor must be closed; this fixture never copies an open DB",
);
mkdirSync(out, { recursive: true });
const home = join(out, "closed-predecessor-copy"),
  rel = relative(out, home);
assert.ok(rel && !rel.startsWith("..") && !isAbsolute(rel));
cpSync(source, home, { recursive: true, errorOnExist: true });
const { createJiti } = createRequire(pathToFileURL(process.env.ZARA_PI_SDK))(
    "jiti",
  ),
  jiti = createJiti(import.meta.url),
  { Core, canonical } = await jiti.import(join(pkg, "src/core/index.ts")),
  { DiskStorage, Administration, activeLocation } = await jiti.import(
    join(pkg, "src/storage/index.ts"),
  );
const tables = [
    "records",
    "revisions",
    "changes",
    "intents",
    "receipts",
    "claims",
    "handoffs",
    "relations",
    "relation_history",
    "experience_rows",
    "experience_versions",
  ],
  disk = new DiskStorage(home),
  rows = (d) =>
    Object.fromEntries(
      tables.map((t) => [t, d.all(`SELECT * FROM ${t} ORDER BY rowid`)]),
    ),
  before = rows(disk);
const context = {
    workspace_id: disk.workspace.workspace_id,
    epoch: disk.workspace.epoch,
    principal: "trusted-personal",
    session_id: "filled-spine",
    runtime_id: "filled-spine",
    can_write: true,
    processing_allowed: true,
    scopes: ["restricted:read", "restricted:write"],
  },
  admin = new Administration(home, join(out, "backups"), context);
const backup = await admin.backup(disk),
  verified = admin.verify(backup.backup),
  preview = admin.restorePreview(
    backup.backup,
    "Restore full synthetic predecessor including support/history/materials",
    "Keep current",
  ),
  shown = admin.approvals.present(preview.preview.request_id);
admin.approvals.answer(shown.token, true, {
  source_ref: "synthetic-filled-decision",
  transport: "native-dialog",
  channel_identity: "registered-fixture",
  stage: "pi-confirm-return",
});
admin.restore(preview.preview.request_id, disk);
const restored = new DiskStorage(home),
  core = new Core(restored, {
    ...context,
    epoch: restored.workspace.epoch,
    runtime_id: "fresh-filled-spine",
  });
try {
  assert.equal(canonical(rows(restored)), canonical(before));
  assert.notEqual(restored.workspace.epoch, context.epoch);
  assert.ok(core.snapshot().recovery_required.length);
  writeFileSync(
    join(out, "verification.json"),
    JSON.stringify(
      {
        schema: restored.workspace.schema_version,
        source_closed: true,
        active_database: join(activeLocation(home), "zara.sqlite"),
        backup,
        manifest: verified.manifest,
        canonical_support_history_receipts_claims_handoffs_exact: true,
        old_epoch: context.epoch,
        new_epoch: restored.workspace.epoch,
        table_counts: Object.fromEntries(
          Object.entries(before).map(([t, r]) => [t, r.length]),
        ),
        recovery: core.snapshot().recovery_required,
      },
      null,
      2,
    ),
  );
} finally {
  restored.close();
}
assert.ok(readFileSync(join(out, "verification.json")).length);
console.log(
  JSON.stringify({ filled_spine: true, exact_tables: tables.length }),
);

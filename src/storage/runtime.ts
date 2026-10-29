import { backup, DatabaseSync } from "node:sqlite";
import { CoreError } from "../core/index.ts";

let verified = false;
/** Probe only an in-memory database, before opening or creating any personal store. */
export function verifyRuntime() {
  if (verified) return;
  const node = process.versions.node.split(".").map(Number);
  if (node[0] !== 24 || node[1] < 22 || (node[1] === 22 && node[2] < 1))
    throw new CoreError(
      "RUNTIME_UNSUPPORTED",
      "Concurrent Zaratustra requires Node 24.22.1 or newer in the 24.x LTS line; qualified runtime: Node 24.22.1, Pi 1.4.0. Update Node once, then start ordinary Pi again. Personal storage has not been opened.",
    );
  const db = new DatabaseSync(":memory:");
  try {
    const sqlite = String(
      (
        db.prepare("SELECT sqlite_version() AS version").get() as {
          version: string;
        }
      ).version,
    );
    const parts = sqlite.split(".").map(Number);
    if (
      parts[0] < 3 ||
      (parts[0] === 3 && parts[1] < 53) ||
      typeof backup !== "function"
    )
      throw new Error("SQLite 3.53+ with backup API is required");
    db.exec(
      "CREATE VIRTUAL TABLE runtime_fts USING fts5(body); CREATE TABLE runtime_text(value TEXT, bytes BLOB)",
    );
    const original = "Zaratustra \u0000 \u{1f9ea} русский";
    const bytes = Buffer.from(original);
    db.prepare("INSERT INTO runtime_text VALUES (?,?)").run(original, bytes);
    const row = db
      .prepare(
        "SELECT value,bytes,json_extract('{\"ok\":true}','$.ok') AS ok FROM runtime_text",
      )
      .get() as { value: string; bytes: Uint8Array; ok: number };
    if (
      row.value !== original ||
      !Buffer.from(row.bytes).equals(bytes) ||
      row.ok !== 1
    )
      throw new Error("SQLite text/blob/JSON roundtrip failed");
    verified = true;
  } catch (error) {
    throw new CoreError(
      "RUNTIME_UNSUPPORTED",
      "SQLite runtime probe failed before personal storage access: " +
        (error as Error).message,
    );
  } finally {
    db.close();
  }
}

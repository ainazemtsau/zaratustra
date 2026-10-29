import type { DatabaseSync } from "node:sqlite";
import {
  MemorySchemaSQL,
  ExperienceSchemaSQL,
  ApprovalSchemaSQL,
  LifecycleSchemaSQL,
  SleepSchemaSQL,
} from "../core/index.ts";
import { BaseIndexesSQL } from "./indexes.ts";
import { ConcurrencySchemaSQL } from "./schema.ts";
import { CorpusMetadataSQL, SleepCycleSQL } from "./corpus.ts";
/** Trusted compiled schema only. Corpus data never supplies executable SQL. */
export function createProjectionSchema(
  db: DatabaseSync,
  workspace: { workspace_id: string; epoch: string; schema_version: number },
) {
  db.exec(`PRAGMA foreign_keys=OFF; BEGIN IMMEDIATE;
 CREATE TABLE meta(json TEXT NOT NULL);
 CREATE TABLE records(id TEXT PRIMARY KEY,kind TEXT NOT NULL,activity_id TEXT,json TEXT NOT NULL);
 ${BaseIndexesSQL.kind_activity}
 CREATE TABLE revisions(id TEXT NOT NULL,revision INTEGER NOT NULL,json TEXT NOT NULL,PRIMARY KEY(id,revision));
 CREATE TABLE changes(seq INTEGER PRIMARY KEY,json TEXT NOT NULL);
 CREATE TABLE intents(request_id TEXT PRIMARY KEY,hash TEXT NOT NULL,json TEXT NOT NULL);
 CREATE TABLE receipts(request_id TEXT PRIMARY KEY,hash TEXT NOT NULL,json TEXT NOT NULL,bindings TEXT NOT NULL);
 CREATE TABLE focus(session_id TEXT PRIMARY KEY,json TEXT NOT NULL);
 CREATE TABLE claims(token TEXT PRIMARY KEY,work_id TEXT NOT NULL,json TEXT NOT NULL);
 ${BaseIndexesSQL.claim_work}
 CREATE TABLE handoffs(id TEXT PRIMARY KEY,json TEXT NOT NULL);
 CREATE TABLE migrations(version INTEGER PRIMARY KEY,json TEXT NOT NULL);
 ${MemorySchemaSQL}
 ${ExperienceSchemaSQL}
 ${ApprovalSchemaSQL}
 ${LifecycleSchemaSQL}
 ${SleepSchemaSQL}
 ${ConcurrencySchemaSQL}
 ${CorpusMetadataSQL}
 ${SleepCycleSQL}
 CREATE TABLE corpus_dirty(collection TEXT NOT NULL,identity TEXT NOT NULL,PRIMARY KEY(collection,identity));
 CREATE TABLE corpus_projection(singleton INTEGER PRIMARY KEY CHECK(singleton=1),revision INTEGER NOT NULL);
 INSERT INTO corpus_projection VALUES(1,0);
 PRAGMA user_version=10;`);
  db.prepare("INSERT INTO meta VALUES(?)").run(JSON.stringify(workspace));
  db.exec("COMMIT");
}

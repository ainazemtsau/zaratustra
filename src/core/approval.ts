import { createHash, randomUUID } from "node:crypto";
import { canonical, requireThat } from "./contracts.ts";
import type { CallContext, JsonObject, StoragePort } from "./contracts.ts";

const hash = (v: unknown) =>
  createHash("sha256").update(canonical(v)).digest("hex");
export const ApprovalSchemaSQL = `CREATE INDEX intent_kind ON intents(json_extract(json,'$.kind'));`;
export const APPROVAL_POLICY = "E2-exact-v1";
export interface BoundPreview {
  payload_not_retained?: boolean;
  request_id: string;
  kind: "preview";
  status: string;
  payload: {
    workspace_id: string;
    epoch: string;
    principal: string;
    scopes: string[];
    policy_revision: string;
    session_id: string;
    runtime_id: string;
    action: string;
    exact: JsonObject;
    dependencies: { id: string; revision: number }[];
    consequence: string;
    alternatives: string;
    expires_at: string;
    revocation: string;
  };
  operation_digest: string;
  answer?: JsonObject;
  consumed_by?: string;
}

export interface PreviewStore {
  workspace: StoragePort["workspace"];
  assertActive?(epoch: string): void;
  readPreview(ref: string): BoundPreview | undefined;
  writePreview(preview: BoundPreview, create?: boolean): void;
}
/** Transient authority, durable immutable drafts. Only the trusted adapter completes a presentation. */
export class Approvals {
  private pending?: { ref: string; token: string; digest: string };
  private granted = new Map<string, string>();
  constructor(
    db: StoragePort | PreviewStore,
    private ctx: CallContext,
    private accessible: (value: unknown) => boolean,
    private revision: (id: string) => number,
  ) {
    this.db =
      "readPreview" in db
        ? db
        : {
            workspace: db.workspace,
            assertActive: (epoch) => db.assertActive?.(epoch),
            readPreview: (ref) => {
              const row = db.get<{ json: string }>(
                "SELECT json FROM intents WHERE request_id=?",
                ref,
              );
              return row ? JSON.parse(row.json) : undefined;
            },
            writePreview: (p, create) => {
              if (create)
                db.run(
                  "INSERT INTO intents VALUES(?,?,?)",
                  p.request_id,
                  p.operation_digest,
                  JSON.stringify(p),
                );
              else
                db.run(
                  "UPDATE intents SET json=? WHERE request_id=?",
                  JSON.stringify(p),
                  p.request_id,
                );
            },
          };
  }
  private db: PreviewStore;
  invalidate() {
    this.pending = undefined;
    this.granted.clear();
  }
  draft(
    action: string,
    exact: JsonObject,
    dependencies: { id: string; revision: number }[],
    consequence: string,
    alternatives: string,
    seconds = 900,
  ) {
    exact = JSON.parse(JSON.stringify(exact)) as JsonObject;
    requireThat(
      Number.isInteger(seconds) &&
        seconds >= 1 &&
        seconds <= 1800 &&
        consequence.length > 0 &&
        consequence.length <= 4000 &&
        alternatives.length > 0 &&
        alternatives.length <= 4000 &&
        Buffer.byteLength(canonical(exact)) <= 256000,
      "VALIDATION_ERROR",
      "Preview must be finite, explained and expire within 30 minutes.",
    );
    requireThat(
      this.accessible(exact),
      "REFERENCE_NOT_FOUND",
      "Preview premises unavailable.",
    );
    const payload: BoundPreview["payload"] = {
      workspace_id: this.ctx.workspace_id,
      epoch: this.ctx.epoch,
      principal: this.ctx.approval_principal ?? this.ctx.principal,
      scopes: [...(this.ctx.scopes ?? [])].sort(),
      policy_revision: this.ctx.policy_revision ?? APPROVAL_POLICY,
      session_id: this.ctx.session_id,
      runtime_id: this.ctx.runtime_id,
      action,
      exact,
      dependencies,
      consequence,
      alternatives,
      expires_at: new Date(Date.now() + seconds * 1000).toISOString(),
      revocation:
        "Runtime reload, session replacement, refusal/cancel, explicit revocation, changed authority/policy/epoch or a material dependency invalidates permission.",
    };
    const preview: BoundPreview = {
      request_id: "preview-" + randomUUID(),
      kind: "preview",
      status: "draft",
      payload,
      operation_digest: hash(payload),
    };
    this.db.writePreview(preview, true);
    return structuredClone(preview);
  }
  read(ref: string) {
    const p = this.db.readPreview(ref);
    requireThat(
      p?.kind === "preview" && this.accessible(p),
      "REFERENCE_NOT_FOUND",
      "Preview unavailable.",
    );
    requireThat(
      !p.payload_not_retained,
      "CONTENT_NOT_RETAINED",
      "The original preview payload is not retained and cannot grant permission.",
    );
    requireThat(
      p.operation_digest === hash(p.payload),
      "APPROVAL_STALE",
      "Preview digest changed.",
    );
    return p;
  }
  private valid(p: BoundPreview) {
    this.db.assertActive?.(this.ctx.epoch);
    const b = p.payload;
    requireThat(
      b.workspace_id === this.ctx.workspace_id &&
        b.epoch === this.ctx.epoch &&
        b.epoch === this.db.workspace.epoch &&
        b.principal === (this.ctx.approval_principal ?? this.ctx.principal) &&
        b.session_id === this.ctx.session_id &&
        b.runtime_id === this.ctx.runtime_id &&
        b.policy_revision === (this.ctx.policy_revision ?? APPROVAL_POLICY) &&
        canonical(b.scopes) ===
          canonical([...(this.ctx.scopes ?? [])].sort()) &&
        Date.parse(b.expires_at) > Date.now() &&
        !["revoked", "declined", "consumed"].includes(p.status),
      "APPROVAL_STALE",
      "Preview authority, runtime, policy, epoch, expiry or revocation changed; present a new proposal.",
    );
    for (const d of b.dependencies)
      requireThat(
        this.revision(d.id) === d.revision,
        "APPROVAL_STALE",
        "A material preview premise changed; present a new proposal.",
      );
  }
  present(ref: string) {
    const p = this.read(ref);
    this.valid(p);
    requireThat(
      !this.pending,
      "APPROVAL_PENDING",
      "Resolve the existing native dialog before presenting another proposal.",
    );
    const token = "presentation-" + randomUUID();
    this.pending = { ref, token, digest: p.operation_digest };
    return { token, preview: structuredClone(p) };
  }
  answer(
    token: string,
    affirmative: boolean,
    source: {
      source_ref: string;
      transport: "native-dialog";
      channel_identity: string;
      stage: "pi-confirm-return";
    },
  ) {
    const pending = this.pending;
    requireThat(
      pending?.token === token &&
        source.transport === "native-dialog" &&
        source.stage === "pi-confirm-return",
      "APPROVAL_REQUIRED",
      "No matching trusted dialog presentation.",
    );
    this.pending = undefined;
    const p = this.read(pending.ref);
    this.valid(p);
    requireThat(
      p.operation_digest === pending.digest,
      "APPROVAL_STALE",
      "Presented payload changed.",
    );
    p.status = affirmative ? "approved-transient" : "declined";
    p.answer = {
      ...source,
      affirmative,
      observed_at: new Date().toISOString(),
      presentation_digest: pending.digest,
      authority:
        source.channel_identity === "trusted-local-desktop-owner"
          ? "trusted-desktop-dialog"
          : "registered-synthetic-controller-not-owner",
    };
    this.save(p);
    if (affirmative) this.granted.set(p.request_id, p.operation_digest);
    return structuredClone(p);
  }
  revoke(ref: string) {
    const p = this.read(ref);
    p.status = "revoked";
    this.granted.delete(ref);
    if (this.pending?.ref === ref) this.pending = undefined;
    this.save(p);
    return p;
  }
  verify(ref: string | undefined, action: string, exact: JsonObject) {
    requireThat(
      ref,
      "APPROVAL_REQUIRED",
      "This action requires an exact preview and native confirmation.",
    );
    const p = this.read(ref);
    this.valid(p);
    requireThat(
      this.granted.get(ref) === p.operation_digest &&
        p.status === "approved-transient" &&
        p.payload.action === action &&
        canonical(p.payload.exact) === canonical(exact),
      "APPROVAL_STALE",
      "No current approval for these exact values/targets/recipient/conditions.",
    );
    return p;
  }
  /** Same short transaction as domain commit or native dispatch intent. */
  consume(
    ref: string | undefined,
    action: string,
    exact: JsonObject,
    requestId: string,
  ) {
    const p = this.verify(ref, action, exact);
    p.status = "consumed";
    p.consumed_by = requestId;
    this.save(p);
    // Keep the transient grant until commit: a rollback restores the durable status.
    return p.request_id;
  }
  private save(p: BoundPreview) {
    this.db.writePreview(p);
  }
}

import type { ExtensionContext } from "@earendil-works/pi-coding-agent";
import { createWriteTool } from "@earendil-works/pi-coding-agent";
import { randomUUID } from "node:crypto";
import { posix } from "node:path";
import { z } from "zod";
import {
  Core,
  DocumentPath,
  documentText,
  managedDocument,
  requireThat,
  FileEffectSchema,
} from "../core/index.ts";
import type { RecordRow } from "../core/index.ts";
import { DiskStorage, DocumentFiles } from "../storage/index.ts";
import { simulateNative } from "./managed.ts";

type Register = (
  name: string,
  description: string,
  schema: z.ZodType,
  action: (p: Record<string, unknown>, ctx: ExtensionContext) => unknown,
) => void;
const Exact = z.strictObject({
  id: z.string().min(1),
  revision: z.number().int().positive(),
});
type State = {
  core: () => Core;
  disk: () => DiskStorage;
  clearReady: (id: string) => void;
  begin?: () => () => void;
};

/** Coordination only: native Pi owns text writes; Core owns versions and receipts. */
export function registerDocuments(register: Register, state: State) {
  const files = (ctx: ExtensionContext) => {
    requireThat(
      ctx.isProjectTrusted(),
      "PERMISSION_DENIED",
      "Trust the project before accessing its activities documents.",
    );
    return new DocumentFiles(ctx.cwd);
  };
  const read = (c: Core, id: string) => c.read(id).data as RecordRow;
  const finish = (
    c: Core,
    disk: DiskStorage,
    f: DocumentFiles,
    e: ReturnType<Core["inspectFile"]>,
  ) => {
    requireThat(
      e.epoch === c.context.epoch,
      "APPROVAL_STALE",
      "Historical document operations cannot mutate files after restore. Inspect historical receipts read-only and reconcile current files.",
    );
    requireThat(
      !e.document_superseded_by,
      "APPROVAL_STALE",
      "This uncertain attempt was explicitly superseded by a later confirmed document operation; inspect that operation instead.",
    );
    const d = e.payload.document!;
    requireThat(
      e.payload.target === f.path(d.path),
      "PERMISSION_DENIED",
      "Operation belongs to a different project document root.",
    );
    let receipt = c.documentRegistration(e.request_id);
    if (!receipt) {
      const observed = f.inspect(d.path);
      requireThat(
        observed.hash === e.payload.final_hash,
        "UNKNOWN_EFFECT",
        "Current file does not match the approved version. Preserve and inspect; no automatic write replay.",
      );
      c.observeFile(e.request_id, {
        hash: observed.hash,
        byte_length: observed.byte_length,
      });
      const material = disk.importFile(observed.target, [f.root]);
      receipt = c.finalizeDocument(e.request_id, material);
    }
    const r = receipt as { created: Record<string, string> };
    const current = read(c, r.created.document),
      metadata = managedDocument(current);
    // An old replay must never remove a newer file that reused this path.
    if (metadata.operation_id === e.request_id) {
      if (d.previous_path && d.previous_path !== d.path)
        f.cleanup(d.previous_path, d.key, d.previous_hash!);
      if (d.state === "removed") f.cleanup(d.path, d.key, e.payload.final_hash);
    }
    return {
      ok: true,
      committed: true,
      receipt,
      document_ref: { id: current.id, revision: current.revision },
      state: metadata.state,
      note: "Retained history is separate from removal of the working file. Native postconditions do not prove exclusive writer authorship.",
    };
  };
  register(
    "zara_document_preview",
    "Prepare an exact managed Markdown document change below <project>/activities. One stable ID comment; content lives in the file, registry/history/links in Core. For updates supply the current exact ref. write supports create/edit/move/restore; archive preserves content; remove deletes only the working file and retains history, refusing live dependents. A format_ref pins retained Evidence containing a JSON Schema 2020-12 json block; data documents use one json block. Confirm via zara_confirm, then zara_document_apply. No model calls, auto Git or new editor.",
    z.strictObject({
      request_id: z.string().min(1).max(100),
      ref: Exact.optional(),
      path: DocumentPath.optional(),
      action: z.enum(["write", "archive", "remove"]).default("write"),
      title: z.string().min(1).max(4000).optional(),
      document_type: z.string().min(1).max(100).optional(),
      content: z.string().max(64000).optional(),
      activity_ref: Exact.nullable().optional(),
      format_ref: Exact.nullable().optional(),
      links: z.array(Exact).max(30).optional(),
      visibility: z.enum(["workspace", "restricted"]).optional(),
      source_language: z.string().min(1).max(100).default("en"),
      work_ref: Exact.nullable().optional(),
      step_id: z.string().nullable().optional(),
      adopt_changes: z.boolean().default(false),
      retry_of: z.string().optional(),
      retry_risk: z.string().min(1).max(4000).optional(),
      consequence: z.string().min(1).max(4000),
      alternatives: z.string().min(1).max(4000),
    }),
    async (raw, ctx) => {
      const c = state.core();
      c.authorizeImport();
      const p = raw as {
        request_id: string;
        ref?: z.infer<typeof Exact>;
        path?: string;
        action: "write" | "archive" | "remove";
        title?: string;
        document_type?: string;
        content?: string;
        activity_ref?: z.infer<typeof Exact> | null;
        format_ref?: z.infer<typeof Exact> | null;
        links?: z.infer<typeof Exact>[];
        visibility?: "workspace" | "restricted";
        source_language: string;
        work_ref?: z.infer<typeof Exact> | null;
        step_id?: string | null;
        adopt_changes: boolean;
        retry_of?: string;
        retry_risk?: string;
        consequence: string;
        alternatives: string;
      };
      const current = p.ref ? read(c, p.ref.id) : null,
        old = current ? managedDocument(current) : null;
      requireThat(
        !current || current.revision === p.ref!.revision,
        "REVISION_CONFLICT",
        "Read the current document registry before changing it.",
      );
      requireThat(
        current ||
          (p.path &&
            p.title &&
            p.document_type &&
            p.content !== undefined &&
            p.action === "write"),
        "VALIDATION_ERROR",
        "New documents require path, title, type and content.",
      );
      requireThat(
        (p.visibility ?? current?.visibility) !== "restricted" ||
          (c.context.scopes?.includes("restricted:read") &&
            c.context.scopes?.includes("restricted:write")),
        "PERMISSION_DENIED",
        "Protected document writes need trusted read/write scopes before file access.",
      );
      requireThat(
        !old ||
          old.state !== "removed" ||
          p.action !== "write" ||
          p.content !== undefined,
        "CONTENT_NOT_RETAINED",
        "Restoring a removed working file requires explicit retained-version content.",
      );
      const prior = p.retry_of ? c.inspectFile(p.retry_of) : null;
      const f = files(ctx),
        path = p.path ?? old!.path,
        key = old?.key ?? prior?.payload.document?.key ?? randomUUID();
      const previous = old ? read(c, old.head_ref.id) : null;
      const previousHash = previous?.data.content_hash as string | null;
      const existing = old ? f.inspect(old.path) : null;
      if (old && old.state !== "removed")
        requireThat(
          p.adopt_changes ||
            existing!.hash === previousHash ||
            (!existing!.bytes && p.content !== undefined),
          "DOCUMENT_DRIFT",
          "File differs from its registered version; inspect and explicitly adopt reviewed changes.",
        );
      requireThat(
        !old || path === old.path || f.inspect(path).bytes === null,
        "REVISION_CONFLICT",
        "Move destination already exists.",
      );
      const historical = previous?.data.blob_ref
        ? state.disk().readMaterial(String(previous.data.blob_ref))
        : "";
      const content =
        p.action === "remove"
          ? `<!-- zaratustra-document: ${key} -->\n`
          : documentText(
              key,
              p.content ?? existing?.bytes?.toString("utf8") ?? historical,
            );
      requireThat(
        p.action === "write" || p.content === undefined,
        "VALIDATION_ERROR",
        "Lifecycle actions preserve registered content; use a separate write for content edits.",
      );
      if (p.adopt_changes)
        requireThat(
          p.action === "write" &&
            path === old?.path &&
            existing?.bytes &&
            content === documentText(key, existing.bytes.toString("utf8")),
          "VALIDATION_ERROR",
          "Adoption must preserve the observed external bytes; make subsequent edits separately.",
        );
      const target = f.prepareParent(path),
        boundary = f.boundary();
      const prepared = await simulateNative(boundary, ctx.cwd, {
        tool: "write",
        arguments: { path: target, content },
      });
      c.authorizeImport();
      return c.prepareFile(
        {
          ...prepared,
          request_id: p.request_id,
          tool: "write",
          work_ref: p.work_ref ?? null,
          step_id: p.step_id ?? null,
          independent_basis: p.work_ref
            ? null
            : "Manage a requested durable Activity document",
          method_export: null,
          retry_of: p.retry_of ?? null,
          retry_risk: p.retry_risk ?? null,
          document: {
            ref: p.ref ?? null,
            key,
            path,
            document_type: p.document_type ?? old!.document_type,
            state:
              p.action === "remove"
                ? "removed"
                : p.action === "archive"
                  ? "archived"
                  : "active",
            activity_ref:
              p.activity_ref === undefined
                ? current?.origin_activity_id
                  ? {
                      id: current.origin_activity_id.id,
                      revision: read(c, current.origin_activity_id.id).revision,
                    }
                  : null
                : p.activity_ref,
            format_ref:
              p.format_ref === undefined
                ? (old?.format_ref ?? null)
                : p.format_ref,
            links: p.links ?? old?.links ?? [],
            title: p.title ?? current!.title,
            visibility: p.visibility ?? current?.visibility ?? "workspace",
            source_language: p.source_language,
            previous_path: old?.path ?? null,
            previous_hash: previousHash ?? null,
          },
        },
        p.consequence,
        p.alternatives,
      );
    },
  );
  register(
    "zara_document_apply",
    "Apply an exactly confirmed document preview using Pi's native write engine, observe bytes, then atomically register document/source/Change/receipt. After a lost reply use request_id to inspect/finalize without repeating the write. Move/remove cleanup is guarded by exact identity/hash; old replay cannot delete a newer version. No Git operations.",
    z
      .strictObject({
        preview_ref: z.string().optional(),
        request_id: z.string().optional(),
      })
      .refine(
        (p) => !!p.preview_ref !== !!p.request_id,
        "Supply preview_ref OR an existing request_id.",
      ),
    async (p, ctx) => {
      const end = state.begin?.() ?? (() => {});
      try {
        const c = state.core();
        c.authorizeImport();
        const disk = state.disk(),
          f = files(ctx);
        if (p.request_id)
          return finish(
            c,
            state.disk(),
            f,
            c.inspectFile(p.request_id as string),
          );
        const preview = c.approvals.read(p.preview_ref as string);
        requireThat(
          preview.payload.action === "managed_file",
          "VALIDATION_ERROR",
          "Expected a managed document preview.",
        );
        const effect = FileEffectSchema.parse(preview.payload.exact);
        requireThat(
          effect.document && effect.target === f.path(effect.document.path),
          "PERMISSION_DENIED",
          "Expected this project's managed document.",
        );
        const prior = c.fileReplay(
          effect.request_id,
          effect.tool,
          effect.arguments,
        );
        if (prior)
          return finish(c, state.disk(), f, c.inspectFile(effect.request_id));
        f.boundary().check(effect, ctx.cwd);
        const d = effect.document;
        if (d.previous_path && d.previous_hash && d.state !== "removed") {
          const previous = f.inspect(d.previous_path);
          requireThat(
            previous.hash === d.previous_hash ||
              (d.previous_path === d.path &&
                previous.hash === effect.before_hash),
            "REVISION_CONFLICT",
            "Previous file changed after preview.",
          );
        }
        const callId = "document-native-" + effect.request_id;
        c.dispatchFile(effect, p.preview_ref as string, callId);
        state.clearReady(effect.request_id);
        let isError = false;
        try {
          await createWriteTool(ctx.cwd).execute(
            callId,
            effect.arguments as { path: string; content: string },
          );
        } catch {
          isError = true;
        }
        requireThat(
          state.core() === c && state.disk() === disk,
          "STORE_UNAVAILABLE",
          "Document runtime was replaced; inspect the pending operation without replay.",
        );
        const actual = f.inspect(d.path);
        c.observeFile(
          effect.request_id,
          {
            hash: actual.hash,
            byte_length: actual.byte_length,
            boundary: "boundary" in actual ? actual.boundary : null,
          },
          { id: callId, runtime_id: c.context.runtime_id, is_error: isError },
        );
        return finish(c, disk, f, c.inspectFile(effect.request_id));
      } finally {
        end();
      }
    },
  );
  register(
    "zara_document_inspect",
    "Read a permitted document registry and compare its working file without adopting changes. Returns current/archived/removed/missing/drift. Historical sources use zara_read on head_ref; ordinary reads do not silently overwrite registry or file.",
    z.strictObject({ id: z.string() }),
    (p, ctx) => {
      const c = state.core(),
        r = read(c, p.id as string),
        d = managedDocument(r),
        source = read(c, d.head_ref.id);
      const current = files(ctx).inspect(d.path);
      return {
        ok: true,
        document: r,
        head_ref: d.head_ref,
        observed_hash: current.hash,
        state:
          d.state === "removed" && !current.bytes
            ? "removed"
            : !current.bytes
              ? "missing"
              : current.hash !== source.data.content_hash
                ? "drift"
                : d.state,
        instruction:
          "Read exact retained head_ref for registered content. Review external changes before adopting; modification time does not establish authority.",
      };
    },
  );
  register(
    "zara_documents_publication",
    "Check an explicit bounded set of current or exact historical document refs before GitHub publication. Return a version/hash manifest and Markdown index text; this does NOT write files or commit/push. Missing exact linked versions must be included. Historical exports use _history/<key>/revision-N.md and must be materialized from their retained head_ref, never latest content. Refuse incomplete, drifted or pending registrations as publication-ready.",
    z.strictObject({
      refs: z.array(Exact).min(1).max(30),
      index_path: DocumentPath,
    }),
    (p, ctx) => {
      const c = state.core(),
        f = files(ctx),
        refs = p.refs as z.infer<typeof Exact>[];
      requireThat(
        new Set(refs.map((r) => r.id + "@" + r.revision)).size === refs.length,
        "VALIDATION_ERROR",
        "Publication refs must be unique.",
      );
      const items = refs.map((ref) => {
        const r = c.read(ref.id, ref.revision).data as RecordRow,
          d = managedDocument(r);
        const latest = read(c, ref.id),
          historical = latest.revision !== r.revision;
        requireThat(
          d.state !== "removed",
          "CONTENT_NOT_RETAINED",
          "Removed working documents are not current publication entries; explicitly select retained history.",
        );
        const source = read(c, d.head_ref.id),
          path = historical
            ? `_history/${d.key}/revision-${r.revision}.md`
            : d.path;
        const observed = f.inspect(path);
        return {
          ref,
          key: d.key,
          title: r.title,
          path,
          historical,
          state: d.state,
          head_ref: d.head_ref,
          sha256: source.data.content_hash,
          matches: observed.hash === source.data.content_hash,
          links: d.links,
        };
      });
      const missing = items
        .flatMap((i) => i.links)
        .filter(
          (ref) =>
            !refs.some(
              (selected) =>
                selected.id === ref.id && selected.revision === ref.revision,
            ),
        );
      const pending = c.pendingDocuments(items.map((i) => i.key));
      const indexPath = p.index_path as string;
      return {
        ok: true,
        ready:
          items.every((i) => i.matches) &&
          missing.length === 0 &&
          pending.length === 0,
        written: false,
        format: "zaratustra.documents.publication.v1",
        workspace_id: c.context.workspace_id,
        snapshot_seq: c.sequence(),
        documents: items,
        missing_linked_refs: missing,
        pending_operations: pending,
        index_markdown:
          "# Activity documents\n\nPublished documents are a fixed snapshot, not live SQLite access. Start with the applicable current plan. Preserve the source version when returning observations.\n\n" +
          items
            .map(
              (i) =>
                `- [${i.title.replace(/[\r\n\[\]]/g, " ")}](<${posix.relative(posix.dirname(indexPath), i.path)}>) — ${i.historical ? "historical" : i.state}, revision ${i.ref.revision}`,
            )
            .join("\n") +
          "\n",
        next: "Materialize missing historical copies from exact head_ref; never substitute latest. Write/recheck the index with ordinary file controls, make a verified memory backup, then use normal Git after checking the intended file set. No automatic push or permission expansion.",
      };
    },
  );
}

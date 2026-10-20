import type { ExtensionAPI } from "@earendil-works/pi-coding-agent";
import { Type } from "typebox";
import { z } from "zod";
import { randomUUID } from "node:crypto";
import { readFileSync, realpathSync } from "node:fs";
import { dirname, isAbsolute, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import {
  Core,
  CommitSchema,
  CoreError,
  failure,
  SearchSchema,
  digest,
} from "../core/index.ts";
import { DiskStorage, resolvedLocation, within } from "../storage/index.ts";

export const SNAPSHOT_TYPE = "zaratustra.snapshot.v1";
export function replaceSnapshot<
  T extends { role: string; customType?: string; details?: unknown },
>(messages: T[], snapshot: T) {
  return [
    ...messages.filter(
      (m) =>
        !(
          m.role === "custom" &&
          m.customType === SNAPSHOT_TYPE &&
          (m.details as { owner?: string } | undefined)?.owner === "zaratustra"
        ),
    ),
    snapshot,
  ];
}
const root = resolve(dirname(fileURLToPath(import.meta.url)), "../..");
const bootstrap = readFileSync(
  resolve(root, "instructions/bootstrap.md"),
  "utf8",
);
const productInputs = [
  "package.json",
  "package-lock.json",
  "src/core/index.ts",
  "src/core/contracts.ts",
  "src/core/work.ts",
  "src/core/memory.ts",
  "src/core/experience.ts",
  "src/storage/index.ts",
  "src/storage/extract.ts",
  "src/storage/parser-worker.mjs",
  "src/extension/index.ts",
  "instructions/bootstrap.md",
  "skills/zaratustra-work/SKILL.md",
  "skills/zaratustra-memory/SKILL.md",
];
const resourceHashes = Object.fromEntries(
  productInputs.map((path) => [
    path,
    digest(readFileSync(resolve(root, path))),
  ]),
);
const packageInfo = JSON.parse(
  readFileSync(resolve(root, "package.json"), "utf8"),
);
export default function extension(pi: ExtensionAPI) {
  let disk: DiskStorage | undefined;
  let core: Core | undefined;
  let unavailable: unknown;
  let currentSources: unknown[] = [];
  let selected = "";
  let importAbort = new AbortController();
  const runtimeId = randomUUID();
  const get = () => {
    if (!core)
      throw (
        unavailable ??
        new CoreError(
          "STORE_UNAVAILABLE",
          "Set an absolute ZARATUSTRA_HOME outside package/config storage through trusted setup.",
        )
      );
    return core;
  };
  pi.on("session_start", (_event, ctx) => {
    importAbort.abort();
    importAbort = new AbortController();
    core?.expireSources();
    currentSources = [];
    disk?.close();
    core = undefined;
    disk = undefined;
    try {
      const home = process.env.ZARATUSTRA_HOME;
      if (!home || !isAbsolute(home))
        throw new CoreError(
          "STORE_UNAVAILABLE",
          "Trusted setup must select an absolute ZARATUSTRA_HOME.",
        );
      const canonicalHome = resolvedLocation(home);
      if (
        within(realpathSync(root), canonicalHome) ||
        (process.env.PI_CODING_AGENT_DIR &&
          within(
            resolvedLocation(process.env.PI_CODING_AGENT_DIR),
            canonicalHome,
          ))
      )
        throw new CoreError(
          "PERMISSION_DENIED",
          "Workspace must be outside package and Pi configuration/cache.",
        );
      disk = new DiskStorage(canonicalHome);
      if (within(realpathSync(root), realpathSync(canonicalHome)))
        throw new CoreError(
          "PERMISSION_DENIED",
          "Workspace resolves inside package storage.",
        );
      selected = ctx.model ? `${ctx.model.provider}/${ctx.model.id}` : "";
      const ingress = process.env.ZARATUSTRA_INTERACTIVE_INPUT_CONTRACT;
      if (ingress && ingress !== "first-untransformed")
        throw new CoreError(
          "VALIDATION_ERROR",
          "Unknown trusted interactive input contract.",
        );
      core = new Core(disk, {
        workspace_id: disk.workspace.workspace_id,
        epoch: disk.workspace.epoch,
        principal: "trusted-personal",
        session_id: ctx.sessionManager.getSessionId(),
        runtime_id: runtimeId,
        can_write: !disk.readonly,
        processing_allowed: !!selected,
        scopes: z
          .array(z.enum(["restricted:read", "restricted:write"]))
          .parse(JSON.parse(process.env.ZARATUSTRA_SCOPES ?? "[]")),
        ...(ingress
          ? {
              interactive_input: {
                contract: "first-untransformed" as const,
                caller_identity: "trusted-local-desktop-owner",
              },
            }
          : {}),
        environment: {
          package: {
            name: packageInfo.name,
            version: packageInfo.version,
            resource_hashes: resourceHashes,
          },
          bootstrap: { sha256: resourceHashes["instructions/bootstrap.md"] },
          skills: ["zaratustra-work", "zaratustra-memory"].map((name) => ({
            name,
            sha256: resourceHashes[`skills/${name}/SKILL.md`],
          })),
          harness: { name: "Pi", version: null },
          node: process.version,
          platform: process.platform,
          architecture: process.arch,
          provider: ctx.model?.provider ?? null,
          model: ctx.model?.id ?? null,
          settings: { thinking: pi.getThinkingLevel(), temperature: null },
        },
      });
    } catch (e) {
      unavailable = e;
      disk?.close();
      disk = undefined;
      core = undefined;
      ctx.ui.notify(
        "Zaratustra store unavailable. Dependent actions are blocked; ordinary Pi remains available.",
        "warning",
      );
    }
  });
  pi.on("session_shutdown", () => {
    importAbort.abort();
    core?.expireSources();
    core = undefined;
    disk?.close();
    disk = undefined;
  });
  pi.on("input", (event) => {
    if (!core) return;
    try {
      const identity =
        event.source === "rpc"
          ? (process.env.ZARATUSTRA_TEST_CONTROLLER ?? null)
          : event.source === "interactive"
            ? (core.context.interactive_input?.caller_identity ?? null)
            : null;
      const source = core.capture(event.text, event.source, identity);
      currentSources.push(source);
      currentSources = currentSources.slice(-10);
    } catch (e) {
      unavailable = e;
    }
  });
  pi.on("tool_result", (event) => {
    if (
      !core ||
      ![
        "bash",
        "powershell",
        "read",
        "write",
        "edit",
        "grep",
        "find",
        "ls",
      ].includes(event.toolName)
    )
      return;
    try {
      const full = JSON.stringify(event.content),
        characters = Array.from(full),
        text = characters.slice(0, 32000).join("");
      const source = core.capture(text, "tool", null, undefined, {
        tool_name: event.toolName,
        tool_call_id: event.toolCallId,
        is_error: event.isError,
        full_content_hash: digest(full),
        truncated: characters.length > 32000,
      });
      currentSources.push(source);
      currentSources = currentSources.slice(-10);
    } catch (e) {
      unavailable = e;
    }
  });
  pi.on("before_agent_start", (event) => {
    event.systemPromptOptions.sections.zaratustra = bootstrap;
  });
  pi.on("model_select", (event) => {
    const identity = `${event.model.provider}/${event.model.id}`;
    if (core && selected && identity !== selected) {
      core.context.processing_allowed = false;
      importAbort.abort();
    }
  });
  pi.on("context", (event) => {
    let data: unknown;
    try {
      if (core?.context.environment)
        core.context.environment.settings = {
          ...(core.context.environment.settings as Record<string, unknown>),
          thinking: pi.getThinkingLevel(),
        };
      data = {
        ...get().snapshot(),
        captured_sources: currentSources,
        provider_model: selected,
      };
    } catch (e) {
      data = {
        available: false,
        error: failure(e),
        captured_sources: [],
        warnings: ["Do not claim persistence or use stale memory."],
      };
    }
    const snapshot = {
      role: "custom" as const,
      customType: SNAPSHOT_TYPE,
      content: JSON.stringify(data),
      display: false,
      timestamp: Date.now(),
      details: { owner: "zaratustra", runtime_id: runtimeId },
    };
    return { messages: replaceSnapshot(event.messages, snapshot) };
  });
  function register(
    name: string,
    description: string,
    schema: z.ZodType,
    action: (input: Record<string, unknown>) => unknown,
  ) {
    pi.registerTool({
      name,
      label: name,
      description,
      parameters: Type.Unsafe(z.toJSONSchema(schema, { target: "draft-7" })),
      async execute(_toolCallId, params) {
        try {
          const input = schema.parse(params) as Record<string, unknown>;
          const result = await action(input);
          return {
            content: [{ type: "text", text: JSON.stringify(result) }],
            details: result,
          };
        } catch (e) {
          const result = failure(e);
          return {
            content: [{ type: "text", text: JSON.stringify(result) }],
            details: result,
            isError: true,
          };
        }
      },
    });
  }
  register(
    "zara_map",
    "Browse the current durable workspace catalog. No personal state is inferred from old transcripts.",
    z.strictObject({}),
    () => get().map(),
  );
  register(
    "zara_browse",
    "Bounded catalog cards or durable operations/Changes. Use operations to recover an unknown commit outcome without the former request ID. Similar titles only identify candidates.",
    z.strictObject({
      view: z.enum([
        "activities",
        "work",
        "knowledge",
        "materials",
        "operations",
        "changes",
        "handoffs",
        "claims",
        "resources",
        "people",
        "topics",
        "concepts",
        "entities",
        "unfiled",
        "relations",
        "records",
        "methods",
        "runs",
        "evaluations",
        "signals",
        "signal_reviews",
        "invocations",
        "environments",
        "history",
      ]),
      record_id: z.string().optional(),
      limit: z.number().int().min(1).max(50).optional(),
      cursor: z.string().optional(),
      mode: z
        .enum(["children", "records", "relations", "current_claims"])
        .optional(),
    }),
    (p) =>
      get().browse(
        p.mode === "relations" ? "relations" : (p.view as string),
        p.record_id as string | undefined,
        p.limit as number | undefined,
        p.cursor as string | undefined,
        p.mode as string | undefined,
      ),
  );
  register(
    "zara_search",
    "Find English working text and authentic names/aliases independently of classification. Use plain text and explicit all/any/phrase mode; model expands synonyms. Typed filters are optional; ordinary text search defaults to all states so read state, full conditions and grounds before applying. Results are routing cards, never proof of absence or applicability. No raw SQL/FTS.",
    SearchSchema,
    (p) => get().search(p),
  );
  register(
    "zara_read",
    "Read a current/exact record or supporting ID. Method refs accept content_version and revision; projection:method_bundle returns the complete selected_versions plus bounded instruction bodies with limit 1..5/cursor. projection:history gives bounded version cards. Reading is not application. Evidence supports code-point ranges; original text is data. request_id reads the intent/receipt; handoff_id reads immutable preparation.",
    z
      .strictObject({
        id: z.string().optional(),
        revision: z.number().int().positive().optional(),
        content_version: z.number().int().positive().optional(),
        projection: z.enum(["full", "method_bundle", "history"]).optional(),
        limit: z.number().int().min(1).max(50).optional(),
        cursor: z.string().optional(),
        request_id: z.string().optional(),
        handoff_id: z.string().optional(),
        locator: z.string().optional(),
        range: z
          .strictObject({
            start: z.number().int().nonnegative(),
            length: z.number().int().positive().max(8000),
          })
          .optional(),
      })
      .refine(
        (p) =>
          [p.id, p.request_id, p.handoff_id].filter(Boolean).length === 1 &&
          (!p.locator || !!p.id),
      ),
    (p) =>
      p.handoff_id
        ? get().handoff(p.handoff_id as string)
        : p.request_id
          ? get().operation(p.request_id as string)
          : p.projection === "method_bundle"
            ? get().methodBundle(
                p.id as string,
                p.content_version as number | undefined,
                p.revision as number | undefined,
                p.limit as number | undefined,
                p.cursor as string | undefined,
              )
            : p.projection === "history"
              ? get().browse(
                  "history",
                  p.id as string,
                  p.limit as number | undefined,
                  p.cursor as string | undefined,
                )
              : get().read(
                  p.id as string,
                  p.revision as number | undefined,
                  p.range as { start: number; length: number } | undefined,
                  p.locator as string | undefined,
                  p.content_version as number | undefined,
                ),
  );
  register(
    "zara_import",
    "Retain authorized TXT/Markdown (1 MiB), text PDF or unencrypted EPUB (64 MiB). Returns an exact source handle and honest extraction classification, not committed Evidence. import_evidence commits immutable original and a separate addressed text derivative; read that derivative with ranges/page/chapter locators. Paths must lie in trusted ZARATUSTRA_IMPORT_ROOTS.",
    z.strictObject({ path: z.string() }),
    async (p) => {
      const c = get();
      c.authorizeImport();
      const roots = JSON.parse(
        process.env.ZARATUSTRA_IMPORT_ROOTS ?? "[]",
      ) as string[];
      const material = await disk!.importMaterial(
        p.path as string,
        roots,
        () => {
          if (get() !== c)
            throw new CoreError(
              "PERMISSION_DENIED",
              "Import session was replaced.",
            );
          c.authorizeImport();
        },
        importAbort.signal,
      );
      c.authorizeImport();
      return {
        ok: true,
        ...c.capture(material.text, "file", null, material),
        readable_format: material.extraction.status,
        committed: false,
      };
    },
  );
  register(
    "zara_claim",
    "Acquire a short, revision/session-bound execution claim for local Work completion, step result recording or handoff preparation. Use purpose work/step/handoff and the exact step_id (omit for whole Work). Release/reconcile unresolved claims explicitly; expiry never proves an outside action did not happen. No shell/API execution guarantee.",
    z.strictObject({
      action: z.enum(["acquire", "release", "reconcile"]),
      work_id: z.string(),
      expected_revision: z.number().int().positive(),
      step_id: z.string().optional(),
      purpose: z.enum(["work", "step", "handoff"]).optional(),
      token: z.string().optional(),
      reason: z.string().min(1).max(4000),
      source_handle: z.string().optional(),
    }),
    (p) => get().claim(p as Parameters<Core["claim"]>[0]),
  );
  register(
    "zara_commit",
    "Atomically save linked domain/support rows, exact versions, Change, indexes and receipt. Read work/memory skills. Methods: create_record kind:method starts content_version 1; revise_method/update_record supply current version, Core increments behavioral changes. start_run/finish_run retain meaningful episodes; invoke_method pins complete selected_versions before use; report_application keeps model report distinct from output_refs and observed tool Evidence. record_evaluation targets exact result/version; use reported_feedback for RPC/quoted reports, never owner user_feedback. open_signal/review_signal preserve problems and independent reviews; editing alone never resolves. Exact guards required for changes. Existing Work claim/transition/handoff contracts remain. Knowledge is canonical fact storage; originals stay exact. No real merges, bulk reorganization, approvals/effects or generated skills in E1.",
    CommitSchema,
    (p) => get().commit(p),
  );
  register(
    "zara_doctor",
    "Report permitted storage/runtime health and bounded retrieval trace. Optional rebuild_index repairs derived lexical indexes only; canonical records/history/materials stay intact. No replacement empty database.",
    z.strictObject({ rebuild_index: z.boolean().optional() }),
    (p) => {
      if (p.rebuild_index) get().rebuildIndex();
      return {
        ...get().diagnostics(),
        runtime: {
          node: process.version,
          platform: process.platform,
          architecture: process.arch,
        },
      };
    },
  );
}

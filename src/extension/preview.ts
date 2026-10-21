import { canonical, mergedAliases } from "../core/index.ts";
import type { JsonObject, RecordRow } from "../core/index.ts";
/** Native dialog formatter. Model supplies the explanation in the conversation language. */
export function renderApproval(b: {
  consequence: string;
  alternatives: string;
  action: string;
  exact: JsonObject;
  expires_at: string;
}) {
  const e = b.exact,
    before = (e.before ?? []) as RecordRow[],
    ops = (e.ops ?? []) as JsonObject[];
  const byId = new Map(before.map((r) => [r.id, r]));
  const created = new Map(
    ops
      .filter((o) => o.client_ref)
      .map((o) => [o.client_ref, String(o.title ?? "New record")]),
  );
  const label = (key: string) =>
    key.replaceAll("_", " ").replace(/\bids?\b/g, "records");
  const value = (v: unknown): string => {
    if (v === null || v === undefined) return "none";
    if (Array.isArray(v)) return v.length ? v.map(value).join("; ") : "none";
    if (typeof v === "object") {
      const o = v as JsonObject;
      if (typeof o.id === "string")
        return `“${byId.get(o.id)?.title ?? "Retained referenced record"}”${o.content_version ? `, content version ${o.content_version}` : ""}${o.revision ? `, revision ${o.revision}` : ""}`;
      if (o.client_ref) return `“${created.get(o.client_ref) ?? "New record"}”`;
      return Object.entries(o)
        .filter(
          ([k]) =>
            ![
              "source_handle",
              "decision_source_handle",
              "claim_tokens",
              "client_ref",
              "request_id",
            ].includes(k),
        )
        .map(([k, x]) => `${label(k)}: ${value(x)}`)
        .join("\n");
    }
    return String(v);
  };
  const changes = (old: JsonObject, next: JsonObject) =>
    Object.entries(next)
      .filter(([k, v]) => canonical(old[k] ?? null) !== canonical(v ?? null))
      .map(([k, v]) => `${label(k)}: ${value(old[k])} → ${value(v)}`)
      .join("\n");
  const describe = (op: JsonObject) => {
    const row = byId.get((op.ref as { id: string } | undefined)?.id ?? "");
    if (op.op === "merge_identity" || op.op === "merge_activity") {
      const from = byId.get((op.from_ref as { id: string }).id)!,
        to = byId.get((op.to_ref as { id: string }).id)!;
      return `Merge ${from.kind} “${from.title}” into “${to.title}”.\nSource identity: ${value(from.data)}\nDestination identity: ${value(to.data)}\nDestination aliases will include: ${value(mergedAliases(from, to))}.\n${op.moved_work_refs ? `Move only these Work records: ${value(op.moved_work_refs)}.\n` : ""}Destination visibility: ${from.visibility === "restricted" || to.visibility === "restricted" || ((e.effective_access as { id: string; restricted: boolean }[]) ?? []).some((a) => [from.id, to.id].includes(a.id) && a.restricted) ? "restricted" : "workspace"}. Source keeps a current redirect; historical identities and references stay exact.`;
    }
    if (op.op === "reorganize_catalog")
      return (op.changes as JsonObject[])
        .map((c) => {
          const r = byId.get((c.ref as { id: string }).id)!;
          return `Reorganize “${r.title}”:\n${c.title ? `Title: ${r.title} → ${c.title}\n` : ""}${c.broader_ids ? `Broader sections: ${value(r.data.broader_ids)} → ${value(c.broader_ids)}\n` : ""}${c.concept_ids ? `Memberships: ${value(r.concept_ids)} → ${value(c.concept_ids)}` : ""}`;
        })
        .join("\n\n");
    if (op.op === "update_record" || op.op === "revise_method")
      return `Update ${row?.kind ?? "record"} “${row?.title ?? "Selected record"}”:\n${op.title ? `Title: ${row?.title} → ${op.title}\n` : ""}${op.body !== undefined ? `Body: ${value(row?.body)} → ${value(op.body)}\n` : ""}${changes(row?.data ?? {}, op.data as JsonObject)}${op.concept_ids ? `\nMemberships: ${value(row?.concept_ids)} → ${value(op.concept_ids)}` : ""}`;
    if (op.op === "create_record")
      return `Create ${op.kind} “${op.title}”:\n${value(op.data)}${op.body ? `\n${op.body}` : ""}`;
    if (op.op === "transition_work")
      return `Work “${row?.title}”: ${row?.data.status} → ${op.status}.\n${op.reason}${op.consequences ? `\nConsequences: ${op.consequences}` : ""}`;
    if (op.op === "import_evidence")
      return `Retain original source as Evidence “${op.title}” with captured provenance. Source text remains untrusted data.`;
    return `${label(String(op.op))}:\n${value(op)}`;
  };
  // Presentation-only projection of explicitly ordered finite fields. No validation,
  // authority or execution occurs here; the domain independently stages/validates.
  const descriptions = ops.map((op) => {
    const text = describe(op);
    if (op.op === "update_record") {
      const r = byId.get((op.ref as { id: string }).id)!;
      byId.set(r.id, {
        ...r,
        title: (op.title as string | undefined) ?? r.title,
        body: op.body === undefined ? r.body : (op.body as string | null),
        data: op.data as JsonObject,
        concept_ids: (op.concept_ids ??
          r.concept_ids) as RecordRow["concept_ids"],
      });
    } else if (op.op === "reorganize_catalog") {
      for (const c of op.changes as JsonObject[]) {
        const r = byId.get((c.ref as { id: string }).id)!;
        byId.set(r.id, {
          ...r,
          title: (c.title as string | undefined) ?? r.title,
          concept_ids: (c.concept_ids ??
            r.concept_ids) as RecordRow["concept_ids"],
          data: {
            ...r.data,
            ...(c.broader_ids ? { broader_ids: c.broader_ids } : {}),
          },
        });
      }
    } else if (op.op === "merge_identity" || op.op === "merge_activity") {
      const from = byId.get((op.from_ref as { id: string }).id)!,
        to = byId.get((op.to_ref as { id: string }).id)!;
      byId.set(to.id, {
        ...to,
        visibility:
          from.visibility === "restricted" ||
          to.visibility === "restricted" ||
          (
            (e.effective_access as { id: string; restricted: boolean }[]) ?? []
          ).some((a) => [from.id, to.id].includes(a.id) && a.restricted)
            ? "restricted"
            : "workspace",
        data: { ...to.data, aliases: mergedAliases(from, to) },
      });
      byId.set(from.id, {
        ...from,
        data: { ...from.data, status: "merged", redirect_to: { id: to.id } },
      });
    }
    return text;
  });
  const exact =
    b.action === "restore"
      ? `Restore backup: ${e.backup}\nCaptured sequence: ${e.captured_seq}.\nVerified destination: ${e.destination}\nCoverage: ${e.coverage}\nLoss/switch consequences: ${e.loss}\nOriginal generation remains retained; restored authority does not revive.`
      : b.action === "cleanup"
        ? `Remove only these unreferenced files:\n${(e.candidates as JsonObject[]).map((c) => `${c.path}: ${c.length} bytes`).join("\n")}\nCoverage: ${e.coverage}`
        : b.action === "release_backup_pin"
          ? `Release the held live pin for independent backup ${(e.pin as JsonObject).bundle}. The verified backup bundle remains. Other live/history/import pins remain effective.`
          : b.action === "storage"
            ? `Storage action: ${e.action}.\n${(e.targets as JsonObject[]).map((t) => `“${t.title}” (${t.kind}), revision ${t.revision}; retained versions: ${(t.versions as JsonObject[]).map((v) => v.revision).join(", ")}`).join("\n")}\nCoverage/loss: ${e.coverage}`
            : b.action === "reconcile"
              ? `Reconcile this named Work/action: ${e.work_title ?? "Selected restored Work"}. Step: ${e.step_id ?? "Work action"}.\nDisposition: ${e.disposition}. ${e.explanation}\nObserved target: ${(e.inspection as JsonObject).target}; ${(e.inspection as JsonObject).byte_length} bytes. Matching current bytes never prove who wrote them. No file is repeated by this decision.`
              : b.action === "managed_file"
                ? `File: ${e.target}\nAction: ${e.before_hash === null ? "Create new file (expected absent)" : "Replace/edit the exact observed existing file"}. Existing size: ${e.before_length} bytes.\nComplete resulting ${e.method_export ? "Method content (the file also carries internal source/version/hash metadata)" : "text"}:\n${e.method_snapshot ? value(e.method_snapshot) : e.final_text}\n${e.work_ref ? `Work: ${(e.work_snapshot as JsonObject)?.title ?? "Selected Work"}. Goal: ${(e.work_snapshot as JsonObject)?.objective}. ${(e.work_snapshot as JsonObject)?.step_intent ? `Step: ${(e.work_snapshot as JsonObject).step_intent}` : ""}` : `Independent action: ${e.independent_basis}`}\n${e.retry_of ? `Risky repeat: ${e.retry_risk}. The prior uncertain attempt stays linked internally.` : ""}`
                : descriptions.join("\n\n") +
                  ((
                    e.assigned_method_versions as
                      | { id: string; content_version: number }[]
                      | undefined
                  )
                    ?.map(
                      (v) =>
                        `\nMethod “${byId.get(v.id)?.title}” resulting content version: ${v.content_version}`,
                    )
                    .join("") ?? "");
  return `${b.consequence}\n\nAlternatives: ${b.alternatives}\n\n${exact}\n\nExpires: ${b.expires_at}. Changed material conditions require a new decision. Decline/cancel leaves this proposal unperformed.`;
}

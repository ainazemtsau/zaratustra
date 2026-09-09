"""Propose through the exact saved pack using one real authorized Core context."""

from __future__ import annotations

import base64
import json
from pathlib import Path
from uuid import UUID

from zaratustra.core import (
    AcceptedHandoff,
    ContextQuery,
    LocalAuthorization,
    MutationRequest,
    NextWork,
    Process,
    ResultSubmission,
    Work,
    open_work,
)

from .lifecycle import PackError, PackRegistry


def propose_result(
    path: Path,
    query: ContextQuery,
    caller: LocalAuthorization | None,
    registry: PackRegistry,
    *,
    operation_id: UUID,
    next_work_id: UUID,
    next_artifact_id: UUID,
) -> MutationRequest:
    package = json.loads(open_work(path, query, caller).output)
    sources = {row["locator"]: row["data"] for row in package["context"]["sources"]}
    work = Work.model_validate(sources[f"work:{query.work_id}"])
    process = Process.model_validate(sources[f"process:{query.process_id}"])
    reference = work.pack_binding
    if reference is None or reference != process.pack_binding:
        raise PackError("unbound_pack", "Work needs its saved Process pack binding")
    registration = registry.resolve(reference)
    acceptances = [
        AcceptedHandoff.model_validate(value)
        for key, value in sources.items()
        if key.startswith("acceptance:")
    ]
    own = [row for row in acceptances if row.handoff.related_work == work.id]
    if not own:
        raise PackError("missing_observation", "Work needs its own accepted result")
    result = own[-1].handoff.result
    source = sources[f"artifact-version:{result.version_id}"]
    accepted_bytes = base64.b64decode(source["content_base64"], validate=True)
    continuation = registration.rule.next_work(work, accepted_bytes, next_work_id, next_artifact_id)
    continuation = NextWork.model_validate(continuation.model_dump())
    if (continuation.work_id, continuation.artifact_id) != (next_work_id, next_artifact_id):
        raise PackError("invalid_proposal", "Pack changed the selected continuation identities")
    return MutationRequest(
        version=4,
        operation="submit_result",
        operation_id=operation_id,
        workspace_id=query.workspace_id,
        work_id=query.work_id,
        expected_revision=query.expected_revision,
        provenance=f"Exact pack proposal: {reference.model_dump_json()}; no authority granted",
        references=(result,),
        submission=ResultSubmission(
            source_revision=query.expected_revision,
            result=result,
            acceptance_ids=tuple(row.handoff.handoff_id for row in own),
            next_work=continuation,
        ),
    )

"""Read authorized Core context and propose a Result; never grant rights or write."""

from __future__ import annotations

import base64
import json
from pathlib import Path
from typing import Protocol
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from zaratustra.core import (
    AcceptedHandoff,
    ContextQuery,
    LocalAuthorization,
    MutationRequest,
    NextWork,
    ResultSubmission,
    Work,
    open_work,
)


class Observation(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", strict=True)
    observed: bool
    recorded: bool


class RuleBlocked(ValueError):
    """The selected rule refuses this observation or Work binding."""


class Rule(Protocol):
    def next_work(
        self, work: Work, observation: Observation, work_id: UUID, artifact_id: UUID
    ) -> NextWork: ...


def propose_result(
    path: Path,
    query: ContextQuery,
    caller: LocalAuthorization | None,
    rule: Rule,
    *,
    operation_id: UUID,
    next_work_id: UUID,
    next_artifact_id: UUID,
) -> MutationRequest:
    """Use latest own acceptance for the rule; retain all own acceptance identities.

    The caller separately confirms the returned EXACT proposal before Core submit.
    No path, authorization handle or arbitrary context is passed into a rule.
    """
    package = json.loads(open_work(path, query, caller).output)
    sources = {row["locator"]: row["data"] for row in package["context"]["sources"]}
    work = Work.model_validate(sources[f"work:{query.work_id}"])
    acceptances = [
        AcceptedHandoff.model_validate(value)
        for key, value in sources.items()
        if key.startswith("acceptance:")
    ]
    own = [row for row in acceptances if row.handoff.related_work == work.id]
    if not own:
        raise RuleBlocked("This Work needs its own accepted observation")
    result = own[-1].handoff.result
    source = sources[f"artifact-version:{result.version_id}"]
    observation = Observation.model_validate_json(base64.b64decode(source["content_base64"]))
    continuation = rule.next_work(work, observation, next_work_id, next_artifact_id)
    return MutationRequest(
        version=4,
        operation_id=operation_id,
        workspace_id=query.workspace_id,
        work_id=query.work_id,
        expected_revision=query.expected_revision,
        operation="submit_result",
        provenance="M1 T1 fictional rule proposal; authority supplied separately",
        references=(result,),
        submission=ResultSubmission(
            source_revision=query.expected_revision,
            result=result,
            acceptance_ids=tuple(row.handoff.handoff_id for row in own),
            next_work=continuation,
        ),
    )

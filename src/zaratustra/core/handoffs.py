"""Bounded portable values and read results; all mutations remain in mutations.py."""

from __future__ import annotations

import hashlib
import json
from typing import Any

from .protocol import (
    Confirmation,
    Handoff,
    HandoffDelivery,
    MutationReceipt,
    MutationRequest,
)
from .records import RecordModel
from .workspace import WorkspaceError

MAX_HANDOFF_BYTES = 65536


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"Duplicate JSON key: {key}")
        result[key] = value
    return result


def handoff_request(
    content: bytes, *, source_ref: str, expected_revision: int | None = None
) -> MutationRequest:
    """Parse data without obtaining permission, reading state or changing intent."""
    if len(content) > MAX_HANDOFF_BYTES:
        raise WorkspaceError("Handoff exceeds the 64 KiB input limit")
    try:
        handoff = Handoff.model_validate(
            json.loads(content.decode("utf-8-sig"), object_pairs_hook=_unique_object)
        )
    except (ValueError, RecursionError) as error:
        raise WorkspaceError(f"Invalid Handoff: {error}") from error
    return MutationRequest(
        version=3,
        operation_id=handoff.handoff_id,
        workspace_id=handoff.workspace_id,
        work_id=handoff.related_work,
        expected_revision=(
            handoff.source_revision if expected_revision is None else expected_revision
        ),
        operation="accept_handoff",
        provenance=handoff.provenance,
        references=(handoff.result, *handoff.basis),
        handoff=handoff,
        delivery=HandoffDelivery(
            source_ref=source_ref, input_sha256=hashlib.sha256(content).hexdigest()
        ),
    )


class AcceptedHandoff(RecordModel):
    handoff: Handoff
    delivery: HandoffDelivery
    confirmation: Confirmation
    receipt: MutationReceipt

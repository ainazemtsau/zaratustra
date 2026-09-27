"""Bounded, read-only structural inspection of a Core space."""

from __future__ import annotations

import json
from pathlib import Path
from uuid import UUID

from pydantic import Field

from .models import ContractModel
from .operations import FoundationError, LocalAuthority, _authorize, _local_space
from .storage import space_connection


class PulseFinding(ContractModel):
    code: str
    address: str
    detail: str
    repair: str


class PulseReport(ContractModel):
    space_id: UUID
    from_revision: int = Field(ge=0)
    through_revision: int = Field(ge=0)
    current_revision: int = Field(ge=0)
    has_more: bool
    checked_records: tuple[UUID, ...]
    findings: tuple[PulseFinding, ...]
    observations: tuple[PulseFinding, ...]


def pulse_space(
    path: Path,
    authority: LocalAuthority,
    *,
    checkpoint: int = 0,
    previous_addresses: tuple[UUID, ...] = (),
    previous_operations: tuple[UUID, ...] = (),
    limit: int = 200,
) -> PulseReport:
    """Inspect changed records, their direct references, and prior open addresses.

    The report is a checkpoint value for the caller. Nothing is marked repaired,
    accepted or externally succeeded by this read.
    """

    if checkpoint < 0 or limit < 1 or limit > 500:
        raise FoundationError("invalid_request", "Pulse needs a bounded revision window")
    findings: list[PulseFinding] = []
    observations: list[PulseFinding] = []
    with space_connection(path) as (connection, info):
        _local_space(authority, info)
        if info.recovery_state != "active":
            raise FoundationError("permission_denied", "Use recovery inspection in quarantine")
        _authorize(
            connection,
            actor=authority.actor,
            action="space.inspect",
            epoch=info.execution_epoch,
        )
        if checkpoint > info.state_revision:
            raise FoundationError("stale_revision", "Pulse checkpoint is ahead of the space")
        operations = connection.execute(
            "SELECT operation_id,state_revision FROM operations WHERE state_revision>? "
            "ORDER BY state_revision LIMIT ?",
            (checkpoint, limit + 1),
        ).fetchall()
        has_more = len(operations) > limit
        selected = operations[:limit]
        through = int(selected[-1][1]) if has_more else info.state_revision
        addresses = {str(item) for item in previous_addresses}
        for operation_id, _ in [*selected, *((str(item), 0) for item in previous_operations)]:
            audit = connection.execute(
                "SELECT target_refs_json FROM operation_audit WHERE operation_id=?",
                (operation_id,),
            ).fetchone()
            if audit is None:
                findings.append(
                    PulseFinding(
                        code="missing_audit",
                        address=f"operation:{operation_id}",
                        detail="Committed operation has no authorization audit",
                        repair="Inspect the receipt and a verified backup",
                    )
                )
                continue
            for ref in json.loads(audit[0]):
                addresses.add(str(ref["record_id"]))
        queue = list(addresses)
        visited: set[str] = set()
        while queue and len(visited) < 500:
            address = queue.pop()
            if address in visited:
                continue
            visited.add(address)
            dependencies: set[str] = set()
            if info.schema_version >= 2:
                subject = connection.execute(
                    "SELECT kind,parent_id,current_revision FROM subject_records WHERE record_id=?",
                    (address,),
                ).fetchone()
                if subject is not None:
                    if subject[1]:
                        dependencies.add(str(subject[1]))
                    if subject[0] == "work":
                        body = connection.execute(
                            "SELECT payload FROM subject_content WHERE record_id=? AND revision=?",
                            (address, subject[2]),
                        ).fetchone()
                        if body is not None:
                            state = json.loads(bytes(body[0]))
                            for ref in [*state.get("inputs", []), *state.get("linked_outputs", [])]:
                                artifact = ref.get("artifact", ref)
                                dependencies.add(str(artifact["artifact_id"]))
                if info.schema_version >= 5:
                    for (child,) in connection.execute(
                        "SELECT child_id FROM work_plan_children WHERE parent_id=? LIMIT 100",
                        (address,),
                    ):
                        dependencies.add(str(child))
            if info.schema_version >= 10:
                for (target,) in connection.execute(
                    "SELECT e.target_id FROM knowledge_edges e "
                    "JOIN knowledge_records r ON r.record_id=e.record_id "
                    "AND r.current_revision=e.revision WHERE e.record_id=? LIMIT 100",
                    (address,),
                ):
                    dependencies.add(str(target))
            for dependency in dependencies - addresses:
                addresses.add(dependency)
                queue.append(dependency)
        if queue:
            observations.append(
                PulseFinding(
                    code="dependency_limit",
                    address=f"space:{info.space_id}",
                    detail="Dependency closure exceeds this bounded Pulse pass",
                    repair="Run another addressed inspection for the remaining dependencies",
                )
            )
        head_tables = [("records", "record_revisions")]
        if info.schema_version >= 2:
            head_tables.append(("subject_records", "subject_revisions"))
        if info.schema_version >= 10:
            head_tables.append(("knowledge_records", "knowledge_revisions"))
        if info.schema_version >= 11:
            head_tables.append(("development_records", "development_revisions"))
        for address in sorted(addresses):
            for table, revisions in head_tables:
                row = connection.execute(
                    f"SELECT current_revision,status FROM {table} WHERE record_id=?",
                    (address,),
                ).fetchone()
                if row is None:
                    continue
                head = connection.execute(
                    f"SELECT 1 FROM {revisions} WHERE record_id=? AND revision=?",
                    (address, row[0]),
                ).fetchone()
                if head is None:
                    findings.append(
                        PulseFinding(
                            code="missing_head",
                            address=f"{table}:{address}@{row[0]}",
                            detail="Current record revision is absent",
                            repair="Stop writes and inspect a verified backup",
                        )
                    )
                break
        quick = connection.execute("PRAGMA quick_check(1)").fetchone()
        if quick is None or quick[0] != "ok":
            findings.append(
                PulseFinding(
                    code="sqlite_integrity",
                    address=f"space:{info.space_id}",
                    detail=str(quick[0] if quick else "no result"),
                    repair="Stop writes and inspect a verified backup",
                )
            )
        foreign = connection.execute("PRAGMA foreign_key_check").fetchone()
        if foreign is not None:
            findings.append(
                PulseFinding(
                    code="foreign_key",
                    address=f"{foreign[0]}:{foreign[1]}",
                    detail="SQLite reference is missing",
                    repair="Stop writes and inspect a verified backup",
                )
            )
        for table in (
            "deletion_jobs",
            *(("subject_deletion_jobs",) if info.schema_version >= 2 else ()),
            *(("method_deletion_jobs",) if info.schema_version >= 5 else ()),
            *(("knowledge_deletion_jobs",) if info.schema_version >= 10 else ()),
            *(("development_deletion_jobs",) if info.schema_version >= 11 else ()),
        ):
            pending = connection.execute(
                f"SELECT count(*) FROM {table} WHERE status='pending'"
            ).fetchone()[0]
            if pending:
                observations.append(
                    PulseFinding(
                        code="pending_maintenance",
                        address=f"space:{info.space_id}/{table}",
                        detail=f"{pending} pending deletion jobs",
                        repair="Run the authorized maintenance deletion operation",
                    )
                )
        if info.schema_version >= 4:
            for table, id_column, statuses, label in (
                (
                    "execution_invocations",
                    "invocation_id",
                    "'sent','unknown'",
                    "external_outcome_unknown",
                ),
                ("execution_assignments", "attempt_id", "'waiting','unknown'", "attempt_waiting"),
                ("execution_outbox", "outbox_id", "'pending'", "pending_outbox"),
            ):
                for item_id, work_id, status in connection.execute(
                    f"SELECT {id_column},work_id,status FROM {table} "
                    f"WHERE status IN ({statuses}) LIMIT 20"
                ):
                    observations.append(
                        PulseFinding(
                            code=label,
                            address=f"work:{work_id}/{item_id}",
                            detail=f"Saved state is {status}; external outcome is not inferred",
                            repair="Inspect the Attempt and reconcile through normal operations",
                        )
                    )
        return PulseReport(
            space_id=info.space_id,
            from_revision=checkpoint,
            through_revision=through,
            current_revision=info.state_revision,
            has_more=has_more,
            checked_records=tuple(UUID(item) for item in sorted(addresses)),
            findings=tuple(findings),
            observations=tuple(observations),
        )

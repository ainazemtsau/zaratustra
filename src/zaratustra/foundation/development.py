"""Saved Sleep analysis and addressed change decisions over ordinary Core operations."""

from __future__ import annotations

import hashlib
import json
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Literal, cast
from uuid import UUID, uuid4

from pydantic import TypeAdapter, ValidationError

from .models import (
    ActivityChange,
    ActivityRevisionChange,
    ActivityState,
    AdmitInvocationRequest,
    ApplyCandidateRequest,
    BindingChange,
    ChangeApplication,
    ChangeCandidateState,
    ChangeDecisionState,
    CompositeChange,
    ConfirmProgramInstallRequest,
    ContextState,
    CreateBindingVersionRequest,
    CreateDevelopmentRequest,
    CreateMethodVersionRequest,
    DeleteDevelopmentRequest,
    DevelopmentRevision,
    KnowledgeRef,
    MethodChange,
    MethodRef,
    ProgramChange,
    RecordChangeOutcomeRequest,
    ReorganizeActivitiesRequest,
    RestoreCandidateRequest,
    ReviseDevelopmentRequest,
    SetBindingStateRequest,
    SleepState,
    SpaceInfo,
    StopCandidateRequest,
    ValidationResultState,
    WorkActivityMove,
    WorkState,
)
from .operations import (
    LocalAuthority,
    _apply_subject_change,
    _authorize,
    _decision_body,
    _local_space,
    _subject_current,
    _subject_state,
    _write_subject,
)
from .storage import (
    CHANGE_PACKAGE_SCHEMA_NAME,
    CHANGE_PACKAGE_SCHEMA_SHA256,
    CHANGE_PACKAGE_SCHEMA_STATEMENTS,
    DEVELOPMENT_SCHEMA_NAME,
    DEVELOPMENT_SCHEMA_SHA256,
    DEVELOPMENT_SCHEMA_STATEMENTS,
    FoundationError,
    canonical_json,
    read_space,
    space_connection,
    utc_now,
)

DEVELOPMENT_ADAPTER: TypeAdapter[SleepState | ChangeCandidateState] = TypeAdapter(
    SleepState | ChangeCandidateState
)
PackagePart = MethodChange | BindingChange | ProgramChange | ActivityChange
CHANGE_PART_ADAPTER: TypeAdapter[PackagePart] = TypeAdapter(PackagePart)
DevelopmentChange = (
    CreateDevelopmentRequest
    | ReviseDevelopmentRequest
    | DeleteDevelopmentRequest
    | ApplyCandidateRequest
    | ConfirmProgramInstallRequest
    | StopCandidateRequest
    | RestoreCandidateRequest
    | RecordChangeOutcomeRequest
)


def upgrade_development_space(path: Path, authority: LocalAuthority) -> SpaceInfo:
    """Explicit additive schema 10 to 11 upgrade."""

    with space_connection(path, writable=True) as (connection, info):
        _local_space(authority, info)
        if info.recovery_state != "active" or info.schema_version < 10:
            raise FoundationError(
                "unsupported_schema", "Development upgrade needs active schema 10"
            )
        _authorize(
            connection,
            actor=authority.actor,
            action="maintenance.backup",
            epoch=info.execution_epoch,
        )
        if info.schema_version == 10:
            for statement in DEVELOPMENT_SCHEMA_STATEMENTS:
                connection.execute(statement)
            now = utc_now().isoformat()
            connection.execute(
                "INSERT INTO schema_migrations(version,name,sha256,applied_at) VALUES (11,?,?,?)",
                (DEVELOPMENT_SCHEMA_NAME, DEVELOPMENT_SCHEMA_SHA256, now),
            )
            connection.execute("PRAGMA user_version = 11")
            connection.execute(
                "UPDATE spaces SET state_revision=state_revision+1 WHERE singleton=1"
            )
            connection.execute(
                "INSERT INTO maintenance_events(event_id,kind,occurred_at,detail_json) "
                "VALUES (?,'schema_upgrade',?,?)",
                (str(uuid4()), now, canonical_json({"from": 10, "to": 11})),
            )
    return read_space(path)


def upgrade_change_package_space(path: Path, authority: LocalAuthority) -> SpaceInfo:
    """Explicit additive schema 11 to 12 upgrade for exact change packages."""

    with space_connection(path, writable=True) as (connection, info):
        _local_space(authority, info)
        if info.recovery_state != "active" or info.schema_version < 11:
            raise FoundationError("unsupported_schema", "Change upgrade needs active schema 11")
        _authorize(
            connection,
            actor=authority.actor,
            action="maintenance.backup",
            epoch=info.execution_epoch,
        )
        if info.schema_version == 11:
            for statement in CHANGE_PACKAGE_SCHEMA_STATEMENTS:
                connection.execute(statement)
            now = utc_now().isoformat()
            connection.execute(
                "INSERT INTO schema_migrations(version,name,sha256,applied_at) VALUES (12,?,?,?)",
                (CHANGE_PACKAGE_SCHEMA_NAME, CHANGE_PACKAGE_SCHEMA_SHA256, now),
            )
            connection.execute("PRAGMA user_version = 12")
            connection.execute(
                "UPDATE spaces SET state_revision=state_revision+1 WHERE singleton=1"
            )
            connection.execute(
                "INSERT INTO maintenance_events(event_id,kind,occurred_at,detail_json) "
                "VALUES (?,'schema_upgrade',?,?)",
                (str(uuid4()), now, canonical_json({"from": 11, "to": 12})),
            )
    return read_space(path)


def _current(
    connection: sqlite3.Connection, record_id: UUID
) -> tuple[int, SleepState | ChangeCandidateState]:
    row = connection.execute(
        "SELECT r.current_revision,v.payload FROM development_records r "
        "JOIN development_revisions v ON v.record_id=r.record_id "
        "AND v.revision=r.current_revision WHERE r.record_id=? AND r.status='active'",
        (str(record_id),),
    ).fetchone()
    if row is None or row[1] is None:
        raise FoundationError(
            "content_unavailable", f"Development record {record_id} is unavailable"
        )
    try:
        return int(row[0]), DEVELOPMENT_ADAPTER.validate_json(bytes(row[1]))
    except ValidationError as error:
        raise FoundationError("corrupt_space", f"Invalid development record: {error}") from error


def _at_revision(
    connection: sqlite3.Connection, record_id: UUID, revision: int
) -> SleepState | ChangeCandidateState:
    row = connection.execute(
        "SELECT payload FROM development_revisions WHERE record_id=? AND revision=?",
        (str(record_id), revision),
    ).fetchone()
    if row is None or row[0] is None:
        raise FoundationError("content_unavailable", "Pinned development revision is unavailable")
    return DEVELOPMENT_ADAPTER.validate_json(bytes(row[0]))


def _references(state: SleepState | ChangeCandidateState) -> list[tuple[str, KnowledgeRef]]:
    if isinstance(state, SleepState):
        refs = [("selected", item.source) for item in state.selected]
        refs += [("delivered", item.source) for item in state.deliveries]
        refs += [("manifest", item.manifest) for item in state.deliveries]
        refs += [("analysis", item) for item in state.analyses]
        refs += [("effect", item.result) for item in state.effects]
        return refs + [("remainder", item.source) for item in state.remainder if item.source]
    refs = [("evidence", item) for item in state.evidence]
    refs += [("counter_evidence", item) for item in state.counter_evidence]
    if state.validation_plan:
        refs += [
            ("criterion", ref)
            for criterion in state.validation_plan.criteria
            for ref in criterion.basis
        ]
    for result in state.results:
        refs += [("validation", ref) for ref in result.evidence]
        if result.manifest:
            refs.append(("validation_manifest", result.manifest))
    return refs


def _check_refs(
    connection: sqlite3.Connection, state: SleepState | ChangeCandidateState, actor: str, epoch: int
) -> None:
    from .knowledge import _require_ref

    for _, ref in _references(state):
        _require_ref(connection, ref, actor, epoch)


def _check_sleep(connection: sqlite3.Connection, state: SleepState, actor: str, epoch: int) -> None:
    from .composition import _method

    row = connection.execute(
        "SELECT r.current_revision,r.status,c.payload FROM subject_records r "
        "JOIN subject_content c ON c.record_id=r.record_id AND c.revision=r.current_revision "
        "WHERE r.record_id=? AND r.kind='work'",
        (str(state.work_id),),
    ).fetchone()
    if row is None or row[1] != "proposed":
        raise FoundationError("work_closed", "Sleep needs an open ordinary Work")
    work = WorkState.model_validate_json(bytes(row[2]))
    if work.method != state.method:
        raise FoundationError("method_mismatch", "Sleep Work must pin its exact Method")
    _method(connection, state.method)
    committed, held = _sleep_usage(connection, state.work_id)
    if (state.spent_units, state.reserved_units) != (committed, held):
        raise FoundationError(
            "resource_mismatch", "Sleep resource must reflect actual Work invocation usage"
        )
    _authorize(
        connection,
        actor=actor,
        action="work.write",
        epoch=epoch,
        resource_type="work",
        resource_id=state.work_id,
    )
    if state.scope_activity_ids:
        for activity_id in state.scope_activity_ids:
            _authorize(
                connection,
                actor=actor,
                action="record.read",
                epoch=epoch,
                resource_type="activity",
                resource_id=activity_id,
            )
    selected = {(item.source.record_id, item.source.revision) for item in state.selected}
    for item in state.selected:
        row = connection.execute(
            "SELECT r.kind,r.created_state_revision,v.payload FROM knowledge_records r "
            "JOIN knowledge_revisions v ON v.record_id=r.record_id AND v.revision=? "
            "WHERE r.record_id=? AND r.status='active'",
            (item.source.revision, str(item.source.record_id)),
        ).fetchone()
        if row is None or row[0] != "source" or int(row[1]) > state.intake_cutoff_revision:
            raise FoundationError(
                "invalid_sleep_source", "Selected source exceeds the intake boundary"
            )
        from .models import SourceState

        source = SourceState.model_validate_json(bytes(row[2]))
        in_scope = (
            source.scope_activity_id in state.scope_activity_ids
            if source.scope_activity_id
            else state.include_free_conversation
        )
        if not in_scope:
            raise FoundationError("out_of_scope", "Sleep source is outside its declared scope")
    for delivery in state.deliveries:
        if (delivery.source.record_id, delivery.source.revision) not in selected:
            raise FoundationError("invalid_sleep_delivery", "Delivery has no selected source")
        row = connection.execute(
            "SELECT stage,manifest_id,manifest_revision FROM knowledge_delivery "
            "WHERE invocation_id=?",
            (str(delivery.invocation_id),),
        ).fetchone()
        rank = {"prepared": 0, "sent": 1, "answered": 2, "unknown": 2}
        if (
            row is None
            or row[1:3] != (str(delivery.manifest.record_id), delivery.manifest.revision)
            or rank[row[0]] < rank[delivery.stage]
        ):
            raise FoundationError(
                "delivery_unverified", "Sleep delivery exceeds the observed stage"
            )
        manifest = connection.execute(
            "SELECT payload FROM knowledge_revisions WHERE record_id=? AND revision=?",
            (str(delivery.manifest.record_id), delivery.manifest.revision),
        ).fetchone()
        if manifest is None or manifest[0] is None:
            raise FoundationError("content_unavailable", "Sleep ContextManifest is unavailable")
        context = ContextState.model_validate_json(bytes(manifest[0]))
        if delivery.source not in (*context.mandatory, *context.optional):
            raise FoundationError("delivery_unverified", "Manifest did not include selected source")
    for effect in state.effects:
        row = connection.execute(
            "SELECT operation_id FROM knowledge_revisions WHERE record_id=? AND revision=? "
            "UNION ALL SELECT operation_id FROM subject_revisions WHERE record_id=? AND revision=? "
            "UNION ALL SELECT operation_id FROM record_revisions WHERE record_id=? AND revision=?",
            (str(effect.result.record_id), effect.result.revision) * 3,
        ).fetchone()
        if row is None or row[0] != str(effect.operation_id):
            raise FoundationError(
                "effect_unverified", "Sleep effect must name its committed revision"
            )
    if len({item.operation_id for item in state.effects}) != len(state.effects):
        raise FoundationError("duplicate_effect", "One effect is counted twice")
    for analysis in state.analyses:
        row = connection.execute(
            "SELECT r.kind FROM knowledge_records r JOIN knowledge_revisions v "
            "ON v.record_id=r.record_id AND v.revision=? WHERE r.record_id=?",
            (analysis.revision, str(analysis.record_id)),
        ).fetchone()
        if row is None or row[0] != "analysis":
            raise FoundationError("wrong_kind", "Sleep analysis needs an Analysis record")
    if (
        state.consolidation in ("complete", "no_material")
        and state.exploration in ("complete", "no_material")
        and state.remainder
        and any(item.kind == "selected" for item in state.remainder)
    ):
        raise FoundationError(
            "unfinished_sleep", "Selected unfinished analysis cannot be called complete"
        )


def _sleep_usage(connection: sqlite3.Connection, work_id: UUID) -> tuple[int, int]:
    row = connection.execute(
        "WITH RECURSIVE member(id) AS (SELECT ? UNION "
        "SELECT c.child_id FROM work_plan_children c JOIN member m ON c.parent_id=m.id "
        "UNION SELECT c.child_id FROM work_plan_members c JOIN member m ON c.parent_id=m.id) "
        "SELECT COALESCE(SUM(CASE WHEN i.status='answered' THEN i.usage_units ELSE 0 END),0), "
        "COALESCE(SUM(CASE WHEN i.status IN ('admitted','sent','unknown') "
        "THEN i.reserve_units ELSE 0 END),0) "
        "FROM execution_invocations i JOIN member m ON m.id=i.work_id",
        (str(work_id),),
    ).fetchone()
    return int(row[0]), int(row[1])


def read_sleep_usage(path: Path, work_id: UUID, authority: LocalAuthority) -> tuple[int, int]:
    with space_connection(path) as (connection, info):
        _local_space(authority, info)
        if info.schema_version < 11 or info.recovery_state != "active":
            raise FoundationError("unsupported_schema", "Sleep usage needs schema 11")
        _authorize(
            connection,
            actor=authority.actor,
            action="record.read",
            epoch=info.execution_epoch,
            resource_type="work",
            resource_id=work_id,
        )
        return _sleep_usage(connection, work_id)


def _root_work(connection: sqlite3.Connection, work_id: UUID) -> UUID:
    root = str(work_id)
    seen: set[str] = set()
    while root not in seen:
        seen.add(root)
        row = connection.execute(
            "SELECT parent_id FROM work_plan_children WHERE child_id=? UNION ALL "
            "SELECT parent_id FROM work_plan_members WHERE child_id=? LIMIT 1",
            (root, root),
        ).fetchone()
        if row is None:
            return UUID(root)
        root = row[0]
    raise FoundationError("corrupt_space", "Work ancestry contains a cycle")


def check_sleep_invocation_budget(
    connection: sqlite3.Connection, request: AdmitInvocationRequest
) -> None:
    """A Sleep limit covers parent and child Attempts inside the admitting transaction."""

    root = str(_root_work(connection, request.work_id))
    row = connection.execute(
        "SELECT v.payload FROM development_records r JOIN development_revisions v "
        "ON v.record_id=r.record_id AND v.revision=r.current_revision "
        "WHERE r.kind='sleep' AND r.status='active' "
        "AND json_extract(CAST(v.payload AS TEXT),'$.work_id')=? LIMIT 1",
        (root,),
    ).fetchone()
    if row is None:
        return
    state = SleepState.model_validate_json(bytes(row[0]))
    committed, held = _sleep_usage(connection, UUID(root))
    prepared = connection.execute(
        "SELECT reserve_units,status FROM execution_invocations WHERE invocation_id=? "
        "AND work_id=?",
        (str(request.invocation_id), str(request.work_id)),
    ).fetchone()
    if prepared is None or prepared[1] != "prepared":
        return
    if (
        state.resource_limit_units is not None
        and committed + held + int(prepared[0]) > state.resource_limit_units
    ):
        raise FoundationError("resource_exhausted", "Sleep's shared finite resource is spent")


def _check_candidate(
    connection: sqlite3.Connection, state: ChangeCandidateState, actor: str, epoch: int
) -> None:
    from .binding import _version
    from .composition import _method
    from .models import MethodRef

    target = state.target
    parts = target.parts if isinstance(target, CompositeChange) else (target,)
    for part in parts:
        if isinstance(part, MethodChange) and part.from_version is not None:
            assert part.from_checksum is not None
            _method(
                connection,
                MethodRef(
                    method_id=part.method_id,
                    version=part.from_version,
                    checksum=part.from_checksum,
                ),
            )
        if isinstance(part, BindingChange) and part.from_version is not None:
            assert part.from_checksum is not None
            prior = _version(connection, part.binding_id, part.from_version)
            if prior.checksum != part.from_checksum:
                raise FoundationError("stale_binding", "Candidate prior Binding checksum differs")
        if isinstance(part, ProgramChange):
            from .execution import _resource

            work_id, revision, resource = _resource(connection, part.resource_id)
            if revision != part.resource_revision or resource.status != "active":
                raise FoundationError("stale_resource", "Program resource changed or was revoked")
            work = connection.execute(
                "SELECT parent_id FROM subject_records WHERE record_id=? AND kind='work'",
                (str(work_id),),
            ).fetchone()
            if work is None or (
                not state.scope_global and UUID(work[0]) not in state.scope_activity_ids
            ):
                raise FoundationError("out_of_scope", "Program resource is outside candidate scope")
            _authorize(
                connection,
                actor=actor,
                action="resource.write",
                epoch=epoch,
                resource_type="work",
                resource_id=work_id,
            )
            for artifact, digest in (
                (part.build, part.build_sha256),
                (part.from_build, part.from_checksum),
            ):
                if artifact is None:
                    continue
                _authorize(
                    connection,
                    actor=actor,
                    action="record.read",
                    epoch=epoch,
                    resource_type="artifact",
                    resource_id=artifact.artifact_id,
                )
                row = connection.execute(
                    "SELECT sha256 FROM managed_content WHERE record_id=? AND revision=?",
                    (str(artifact.artifact_id), artifact.revision),
                ).fetchone()
                if row is None or row[0] != digest:
                    raise FoundationError(
                        "content_unavailable", "Exact program build is unavailable"
                    )
    for activity_id in state.scope_activity_ids:
        _authorize(
            connection,
            actor=actor,
            action="record.read",
            epoch=epoch,
            resource_type="activity",
            resource_id=activity_id,
        )
    for work_id in state.affected_work_ids:
        _authorize(
            connection,
            actor=actor,
            action="record.read",
            epoch=epoch,
            resource_type="work",
            resource_id=work_id,
        )


def _check_progress(prior: SleepState, state: SleepState) -> None:
    fixed = (
        "work_id",
        "method",
        "scope_activity_ids",
        "include_free_conversation",
        "intake_cutoff_revision",
        "resource_limit_units",
    )
    if any(getattr(prior, name) != getattr(state, name) for name in fixed):
        raise FoundationError(
            "invalid_transition", "Sleep scope, Method, cutoff and limit stay fixed"
        )
    if (state.enumeration_cursor_revision, str(state.enumeration_cursor_id or "")) < (
        prior.enumeration_cursor_revision,
        str(prior.enumeration_cursor_id or ""),
    ) or (state.exploration_cursor_revision, str(state.exploration_cursor_id or "")) < (
        prior.exploration_cursor_revision,
        str(prior.exploration_cursor_id or ""),
    ):
        raise FoundationError("invalid_transition", "Sleep cursors cannot move backwards")
    if state.spent_units < prior.spent_units:
        raise FoundationError("invalid_transition", "Sleep resource cannot be reset by a session")
    for name in ("selected", "deliveries", "analyses", "effects"):
        old = getattr(prior, name)
        new = getattr(state, name)
        if tuple(new[: len(old)]) != old:
            raise FoundationError("invalid_transition", f"Sleep {name} history is append only")
    for name in ("consolidation", "exploration"):
        if getattr(prior, name) in ("complete", "no_material") and getattr(prior, name) != getattr(
            state, name
        ):
            raise FoundationError(
                "invalid_transition", "Completed Sleep obligation cannot be erased"
            )


def _save_revision(
    connection: sqlite3.Connection,
    request: CreateDevelopmentRequest | ReviseDevelopmentRequest,
    state: SleepState | ChangeCandidateState,
    revision: int,
    now: str,
) -> None:
    payload = state.model_dump_json().encode("utf-8")
    digest = hashlib.sha256(payload).hexdigest().upper()
    if revision == 1:
        collision = connection.execute(
            "SELECT 1 FROM records WHERE record_id=? UNION ALL "
            "SELECT 1 FROM subject_records WHERE record_id=? UNION ALL "
            "SELECT 1 FROM knowledge_records WHERE record_id=? UNION ALL "
            "SELECT 1 FROM development_records WHERE record_id=? LIMIT 1",
            (str(request.record_id),) * 4,
        ).fetchone()
        if collision:
            raise FoundationError("record_exists", "Development address already exists")
        connection.execute(
            "INSERT INTO development_records(record_id,kind,current_revision,status,"
            "created_at,updated_at) "
            "VALUES (?,?,1,'active',?,?)",
            (str(request.record_id), state.kind, now, now),
        )
    else:
        connection.execute(
            "UPDATE development_records SET current_revision=?,updated_at=? WHERE record_id=?",
            (revision, now, str(request.record_id)),
        )
    connection.execute(
        "INSERT INTO development_revisions(record_id,revision,operation_id,actor,"
        "created_at,payload,sha256) "
        "VALUES (?,?,?,?,?,?,?)",
        (
            str(request.record_id),
            revision,
            str(request.operation_id),
            request.actor,
            now,
            payload,
            digest,
        ),
    )
    references = _references(state)
    for ordinal, (role, ref) in enumerate(references):
        connection.execute(
            "INSERT INTO development_edges(record_id,revision,ordinal,target_id,"
            "target_revision,role) "
            "VALUES (?,?,?,?,?,?)",
            (str(request.record_id), revision, ordinal, str(ref.record_id), ref.revision, role),
        )
    if isinstance(state, ChangeCandidateState):
        targets = (
            state.target.parts if isinstance(state.target, CompositeChange) else (state.target,)
        )
        ordinal = len(references)
        for target in targets:
            target_id = (
                target.method_id
                if isinstance(target, MethodChange)
                else target.binding_id
                if isinstance(target, BindingChange)
                else target.program_id
                if isinstance(target, ProgramChange)
                else target.change_id
            )
            for role, version in (
                ("target_previous", target.from_version),
                ("target_proposed", target.to_version),
            ):
                if version is not None:
                    connection.execute(
                        "INSERT INTO development_edges(record_id,revision,ordinal,target_id,"
                        "target_revision,role) VALUES (?,?,?,?,?,?)",
                        (str(request.record_id), revision, ordinal, str(target_id), version, role),
                    )
                    ordinal += 1
            if isinstance(target, ProgramChange):
                for role, build in (("build", target.build), ("previous_build", target.from_build)):
                    if build is not None:
                        connection.execute(
                            "INSERT INTO development_edges(record_id,revision,ordinal,target_id,"
                            "target_revision,role) VALUES (?,?,?,?,?,?)",
                            (
                                str(request.record_id),
                                revision,
                                ordinal,
                                str(build.artifact_id),
                                build.revision,
                                role,
                            ),
                        )
                        ordinal += 1


def _application(connection: sqlite3.Connection, application_id: UUID) -> ChangeApplication:
    row = connection.execute(
        "SELECT candidate_id,candidate_revision,decision_id,decision_revision,mode,target_kind,"
        "target_id,version,checksum,status,revision,created_at,changed_at "
        "FROM change_applications WHERE application_id=?",
        (str(application_id),),
    ).fetchone()
    if row is None and int(connection.execute("PRAGMA user_version").fetchone()[0]) >= 12:
        row = connection.execute(
            "SELECT candidate_id,candidate_revision,decision_id,decision_revision,mode,target_kind,"
            "target_id,version,checksum,status,revision,created_at,changed_at "
            "FROM change_packages WHERE application_id=?",
            (str(application_id),),
        ).fetchone()
    if row is None:
        raise FoundationError("not_found", "Change application is absent")
    return ChangeApplication(
        application_id=application_id,
        candidate_id=UUID(row[0]),
        candidate_revision=row[1],
        decision_id=UUID(row[2]),
        decision_revision=row[3],
        mode=row[4],
        target_kind=row[5],
        target_id=UUID(row[6]),
        version=row[7],
        checksum=row[8],
        status=row[9],
        revision=row[10],
        created_at=datetime.fromisoformat(row[11]),
        changed_at=datetime.fromisoformat(row[12]),
    )


def _package_event(
    connection: sqlite3.Connection,
    application_id: UUID,
    revision: int,
    operation_id: UUID,
    kind: str,
    detail: dict[str, object],
    now: str,
) -> None:
    connection.execute(
        "INSERT INTO change_package_events(application_id,revision,operation_id,kind,"
        "detail_json,created_at) VALUES (?,?,?,?,?,?)",
        (str(application_id), revision, str(operation_id), kind, canonical_json(detail), now),
    )


def _package_parts(connection: sqlite3.Connection, application_id: UUID) -> tuple[PackagePart, ...]:
    rows = connection.execute(
        "SELECT detail_json FROM change_package_parts WHERE application_id=? ORDER BY ordinal",
        (str(application_id),),
    ).fetchall()
    if not rows:
        raise FoundationError("corrupt_space", "Change package has no exact parts")
    return tuple(CHANGE_PART_ADAPTER.validate_json(row[0]) for row in rows)


def _program_path(connection: sqlite3.Connection, part: ProgramChange) -> Path:
    from .execution import _resource

    _, revision, resource = _resource(connection, part.resource_id)
    if revision != part.resource_revision or resource.status != "active":
        raise FoundationError("stale_resource", "Program resource changed or was revoked")
    root = resource.root.expanduser().resolve(strict=True)
    if not root.is_dir():
        raise FoundationError("resource_unavailable", "Program resource root is unavailable")
    candidate = root.joinpath(*part.relative_path.split("/"))
    if any(item.is_symlink() for item in (candidate, *candidate.parents) if item != root):
        raise FoundationError("resource_unavailable", "Program path contains a symbolic link")
    resolved = candidate.resolve()
    if not resolved.is_relative_to(root):
        raise FoundationError("out_of_scope", "Program path leaves its working resource")
    return resolved


def _check_program_observed(
    connection: sqlite3.Connection, part: ProgramChange, *, installed: bool
) -> None:
    path = _program_path(connection, part)
    expected = part.build_sha256 if installed else part.from_checksum
    if expected is None:
        if path.exists():
            raise FoundationError("program_mismatch", "Expected the previous program path absent")
        return
    if not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest().upper() != expected:
        raise FoundationError("program_mismatch", "Observed program bytes differ from exact build")


def program_target_path(path: Path, part: ProgramChange, authority: LocalAuthority) -> Path:
    """Resolve an admitted resource target for the installed local change tool."""

    from .execution import _resource

    with space_connection(path) as (connection, info):
        _local_space(authority, info)
        if info.schema_version < 12 or info.recovery_state != "active":
            raise FoundationError("upgrade_required", "Program target needs active schema 12")
        work_id, _, _ = _resource(connection, part.resource_id)
        _authorize(
            connection,
            actor=authority.actor,
            action="resource.write",
            epoch=info.execution_epoch,
            resource_type="work",
            resource_id=work_id,
        )
        return _program_path(connection, part)


def check_program_change_boundary(
    path: Path,
    request: ConfirmProgramInstallRequest | RestoreCandidateRequest,
    authority: LocalAuthority,
) -> tuple[ProgramChange, ...]:
    """Check current Core authority immediately before installed file effects."""

    with space_connection(path) as (connection, info):
        _local_space(authority, info)
        if request.space_id != info.space_id or request.actor != authority.actor:
            raise FoundationError("wrong_space", "Program action differs from local authority")
        if info.schema_version < 12 or info.recovery_state != "active":
            raise FoundationError("upgrade_required", "Program change needs active schema 12")
        _authorize(
            connection,
            actor=request.actor,
            action="method.write",
            epoch=info.execution_epoch,
        )
        app = _application(connection, request.application_id)
        if app.revision != request.expected_revision:
            raise FoundationError("stale_revision", "Change application changed")
        if app.target_kind not in ("program", "composite"):
            raise FoundationError("wrong_kind", "Change package has no program build")
        installing = isinstance(request, ConfirmProgramInstallRequest)
        if app.status not in (("prepared",) if installing else ("stopped", "partial")):
            raise FoundationError(
                "invalid_transition", "Program change is not ready for this action"
            )
        _authorize(
            connection,
            actor=request.actor,
            action="record.read",
            epoch=info.execution_epoch,
            resource_type="artifact",
            resource_id=app.candidate_id,
        )
        if installing:
            candidate_revision, candidate = _current(connection, app.candidate_id)
            if candidate_revision != app.candidate_revision or not isinstance(
                candidate, ChangeCandidateState
            ):
                raise FoundationError("stale_candidate", "Prepared candidate changed")
            admission = ApplyCandidateRequest(
                operation_id=request.operation_id,
                space_id=request.space_id,
                actor=request.actor,
                candidate_id=app.candidate_id,
                candidate_revision=app.candidate_revision,
                decision_id=app.decision_id,
                decision_revision=app.decision_revision,
                mode=app.mode,
            )
            _decision(connection, admission, candidate)
        else:
            candidate = _at_revision(connection, app.candidate_id, app.candidate_revision)
            if not isinstance(candidate, ChangeCandidateState):
                raise FoundationError("wrong_kind", "Application candidate is unavailable")
        _check_candidate(connection, candidate, request.actor, info.execution_epoch)
        parts = _package_parts(connection, app.application_id)
        expected_parts = (
            candidate.target.parts
            if isinstance(candidate.target, CompositeChange)
            else (candidate.target,)
        )
        if parts != expected_parts:
            raise FoundationError("corrupt_space", "Package parts differ from exact candidate")
        programs = tuple(part for part in parts if isinstance(part, ProgramChange))
        if not programs:
            raise FoundationError("wrong_kind", "Change package has no program build")
        if not installing:
            for part in programs:
                newer = connection.execute(
                    "SELECT 1 FROM change_package_parts t JOIN change_packages p "
                    "ON p.application_id=t.application_id WHERE t.target_kind='program' "
                    "AND t.target_id=? AND t.version>? AND p.status IN ('active','stopped') "
                    "LIMIT 1",
                    (str(part.program_id), part.to_version),
                ).fetchone()
                if newer:
                    raise FoundationError("stale_program", "Newer program must be addressed first")
        return programs


def _event(
    connection: sqlite3.Connection,
    application_id: UUID,
    revision: int,
    operation_id: UUID,
    kind: str,
    detail: dict[str, object],
    now: str,
) -> None:
    connection.execute(
        "INSERT INTO change_application_events(application_id,revision,operation_id,"
        "kind,detail_json,created_at) "
        "VALUES (?,?,?,?,?,?)",
        (str(application_id), revision, str(operation_id), kind, canonical_json(detail), now),
    )


def _decision(
    connection: sqlite3.Connection, request: ApplyCandidateRequest, candidate: ChangeCandidateState
) -> ChangeDecisionState:
    row = connection.execute(
        "SELECT r.current_revision,v.body_json FROM records r JOIN record_revisions v "
        "ON v.record_id=r.record_id AND v.revision=r.current_revision "
        "WHERE r.record_id=? AND r.kind='decision'",
        (str(request.decision_id),),
    ).fetchone()
    if row is None or int(row[0]) != request.decision_revision:
        raise FoundationError("stale_decision", "Change admission Decision changed")
    state = _decision_body(row[1])
    if (
        not isinstance(state, ChangeDecisionState)
        or state.status != "active"
        or state.candidate_id != request.candidate_id
        or state.candidate_revision != request.candidate_revision
        or state.mode != request.mode
    ):
        raise FoundationError(
            "admission_denied", "Current Decision does not admit this candidate and mode"
        )
    if not candidate.scope_global and state.scope_activity_id not in candidate.scope_activity_ids:
        raise FoundationError("out_of_scope", "Adoption scope exceeds the candidate scope")
    if candidate.validation_plan is None or candidate.status != "open":
        raise FoundationError("candidate_incomplete", "Candidate is not ready for application")
    results = {item.result_id: item for item in candidate.results}
    if not state.validation_result_ids or any(
        item not in results for item in state.validation_result_ids
    ):
        raise FoundationError(
            "validation_missing", "Decision must name real saved validation results"
        )
    observed = [results[item] for item in state.validation_result_ids]
    if any(item.outcome == "not_met" for item in observed):
        raise FoundationError("validation_failed", "A failed criterion cannot admit use")
    _check_program_prerequisites(candidate, observed)
    if request.mode == "regular":
        keys = {item.key for item in candidate.validation_plan.criteria}
        if {item.criterion for item in observed if item.outcome == "met"} != keys:
            raise FoundationError(
                "validation_missing", "Regular use needs met results for every criterion"
            )
    return state


def _check_program_prerequisites(
    candidate: ChangeCandidateState, observed: list[ValidationResultState]
) -> None:
    parts = (
        candidate.target.parts
        if isinstance(candidate.target, CompositeChange)
        else (candidate.target,)
    )
    required = {
        key
        for part in parts
        if isinstance(part, ProgramChange)
        for key in part.required_validation_keys
    }
    passed = {item.criterion for item in observed if item.outcome == "met" and item.evidence}
    if not required.issubset(passed):
        raise FoundationError(
            "validation_missing", "Program needs met, evidenced prerequisite checks"
        )


def validate_change_decision(
    connection: sqlite3.Connection,
    state: ChangeDecisionState,
    actor: str,
    epoch: int,
) -> None:
    _authorize(
        connection,
        actor=actor,
        action="record.read",
        epoch=epoch,
        resource_type="artifact",
        resource_id=state.candidate_id,
    )
    revision, candidate = _current(connection, state.candidate_id)
    if revision != state.candidate_revision or not isinstance(candidate, ChangeCandidateState):
        raise FoundationError("stale_candidate", "Decision needs the current candidate revision")
    if candidate.status != "open" or candidate.validation_plan is None:
        raise FoundationError("candidate_incomplete", "Decision needs an open candidate and plan")
    if not candidate.scope_global and state.scope_activity_id not in candidate.scope_activity_ids:
        raise FoundationError("out_of_scope", "Decision scope exceeds candidate scope")
    results = {item.result_id: item for item in candidate.results}
    if not state.validation_result_ids or any(
        item not in results for item in state.validation_result_ids
    ):
        raise FoundationError("validation_missing", "Decision must name saved results")
    observed = [results[item] for item in state.validation_result_ids]
    if any(item.outcome == "not_met" for item in observed):
        raise FoundationError("validation_failed", "Failed criterion cannot admit use")
    _check_program_prerequisites(candidate, observed)
    if state.mode == "regular":
        required = {item.key for item in candidate.validation_plan.criteria}
        if {item.criterion for item in observed if item.outcome == "met"} != required:
            raise FoundationError(
                "validation_missing", "Regular use needs met results for each criterion"
            )


def _active_target_modes(
    connection: sqlite3.Connection,
    target_kind: str,
    target_id: UUID,
    version: int,
    *,
    excluding: UUID | None = None,
) -> list[tuple[str, ChangeDecisionState]]:
    """Only current Decisions count toward a shared version's live scope."""

    rows = connection.execute(
        "SELECT application_id,mode,decision_id,decision_revision FROM change_applications "
        "WHERE target_kind=? AND target_id=? AND version=? AND status='active'",
        (target_kind, str(target_id), version),
    ).fetchall()
    if int(connection.execute("PRAGMA user_version").fetchone()[0]) >= 12:
        rows += connection.execute(
            "SELECT p.application_id,p.mode,p.decision_id,p.decision_revision "
            "FROM change_packages p JOIN change_package_parts t "
            "ON t.application_id=p.application_id WHERE t.target_kind=? AND t.target_id=? "
            "AND t.version=? AND p.status='active'",
            (target_kind, str(target_id), version),
        ).fetchall()
    result: list[tuple[str, ChangeDecisionState]] = []
    for application_id, mode, decision_id, decision_revision in rows:
        if excluding is not None and application_id == str(excluding):
            continue
        row = connection.execute(
            "SELECT r.current_revision,v.body_json FROM records r JOIN record_revisions v "
            "ON v.record_id=r.record_id AND v.revision=r.current_revision WHERE r.record_id=?",
            (decision_id,),
        ).fetchone()
        if row is None or row[0] != decision_revision:
            continue
        body = _decision_body(row[1])
        if isinstance(body, ChangeDecisionState) and body.status == "active":
            result.append((mode, body))
    return result


def _publish_package_part(
    connection: sqlite3.Connection,
    part: MethodChange | BindingChange,
    request: ApplyCandidateRequest | ConfirmProgramInstallRequest,
    *,
    mode: Literal["trial", "regular"],
    now: str,
    epoch: int,
    authority_source: str,
    grants: list[dict[str, object]],
    decisions: list[dict[str, object]],
) -> str:
    """Publish one exact internal part inside the package's Core transaction."""

    if isinstance(part, MethodChange):
        from .composition import apply_composition_change, method_checksum

        checksum = method_checksum(part.definition)
        row = connection.execute(
            "SELECT checksum,payload FROM method_versions WHERE method_id=? AND version=?",
            (str(part.method_id), part.to_version),
        ).fetchone()
        if row is None:
            apply_composition_change(
                connection,
                CreateMethodVersionRequest(
                    operation_id=request.operation_id,
                    space_id=request.space_id,
                    actor=request.actor,
                    method_id=part.method_id,
                    version=part.to_version,
                    definition=part.definition,
                ),
                now=now,
                epoch=epoch,
                grants=grants,
                decisions=decisions,
            )
        elif row[0] != checksum or row[1] is None:
            raise FoundationError("version_conflict", "Published Method differs from package")
        return checksum
    from .binding import _version, apply_binding_change, binding_checksum

    checksum = binding_checksum(part.definition)
    row = connection.execute(
        "SELECT checksum,payload FROM binding_versions WHERE binding_id=? AND version=?",
        (str(part.binding_id), part.to_version),
    ).fetchone()
    if row is None:
        apply_binding_change(
            connection,
            CreateBindingVersionRequest(
                operation_id=request.operation_id,
                space_id=request.space_id,
                actor=request.actor,
                binding_id=part.binding_id,
                version=part.to_version,
                definition=part.definition,
            ),
            now=now,
            epoch=epoch,
            authority_source=authority_source,
            grants=grants,
            decisions=decisions,
        )
    elif row[0] != checksum or row[1] is None:
        raise FoundationError("version_conflict", "Published Binding differs from package")
    version = _version(connection, part.binding_id, part.to_version)
    desired: Literal["trial", "enabled"] = "enabled" if mode == "regular" else "trial"
    if version.state != desired:
        apply_binding_change(
            connection,
            SetBindingStateRequest(
                operation_id=request.operation_id,
                space_id=request.space_id,
                actor=request.actor,
                binding_id=part.binding_id,
                version=part.to_version,
                expected_state_revision=version.state_revision,
                state=desired,
            ),
            now=now,
            epoch=epoch,
            authority_source=authority_source,
            grants=grants,
            decisions=decisions,
        )
    return checksum


def _package_apply(
    connection: sqlite3.Connection,
    request: ApplyCandidateRequest,
    state: ChangeCandidateState,
    revision: int,
    *,
    now: str,
    epoch: int,
    authority_source: str,
    authority: LocalAuthority,
    grants: list[dict[str, object]],
    decisions: list[dict[str, object]],
) -> tuple[dict[str, object], list[dict[str, object]]]:
    if int(connection.execute("PRAGMA user_version").fetchone()[0]) < 12:
        raise FoundationError("upgrade_required", "Program and composite changes need schema 12")
    decision = _decision(connection, request, state)
    _check_candidate(connection, state, request.actor, epoch)
    target = state.target
    assert isinstance(target, (ProgramChange, CompositeChange, ActivityChange))
    if isinstance(target, ActivityChange):
        created_ids = {item.activity_id for item in target.creations}
        affected = (
            {item.activity_id for item in target.revisions}
            | {item.from_activity_id for item in target.moves}
            | {item.to_activity_id for item in target.moves}
        ) - created_ids
        if not state.scope_global and not affected.issubset(state.scope_activity_ids):
            raise FoundationError("out_of_scope", "Activity change exceeds candidate scope")
        if not decision.scope_global and affected - {decision.scope_activity_id}:
            raise FoundationError("out_of_scope", "Activity change exceeds Decision scope")
    parts = target.parts if isinstance(target, CompositeChange) else (target,)
    if connection.execute(
        "SELECT 1 FROM change_packages WHERE candidate_id=? AND status IN ('prepared','active') "
        "LIMIT 1",
        (str(request.candidate_id),),
    ).fetchone():
        raise FoundationError("change_already_active", "Candidate already has a live package")
    if isinstance(target, ActivityChange):
        _authorize(
            connection,
            actor=request.actor,
            action="activity.write",
            epoch=epoch,
            resource_type="space",
        )
    else:
        _authorize(
            connection,
            actor=request.actor,
            action="method.use",
            epoch=epoch,
            resource_type="activity" if decision.scope_activity_id else "space",
            resource_id=decision.scope_activity_id,
        )
    part_rows: list[tuple[str, UUID, int, str, str]] = []
    has_program = False
    for part in parts:
        target_id = (
            part.method_id
            if isinstance(part, MethodChange)
            else part.binding_id
            if isinstance(part, BindingChange)
            else part.program_id
            if isinstance(part, ProgramChange)
            else part.change_id
        )
        existing = _active_target_modes(connection, part.kind, target_id, part.to_version)
        for _, other in existing:
            if (
                decision.scope_global
                or other.scope_global
                or decision.scope_activity_id == other.scope_activity_id
            ):
                raise FoundationError("change_already_active", "Target version is already active")
        if isinstance(part, ProgramChange):
            has_program = True
            prior = connection.execute(
                "SELECT t.version,t.checksum,p.status FROM change_package_parts t "
                "JOIN change_packages p ON p.application_id=t.application_id "
                "WHERE t.target_kind='program' AND t.target_id=? AND p.status IN "
                "('active','stopped','partial') "
                "ORDER BY t.version DESC LIMIT 1",
                (str(part.program_id),),
            ).fetchone()
            if part.from_version is None:
                if prior is not None:
                    raise FoundationError(
                        "stale_program", "Program already has an installed version"
                    )
            elif prior is None or (prior[0], prior[1]) != (
                part.from_version,
                part.from_checksum,
            ):
                raise FoundationError("stale_program", "Program predecessor differs")
            if prior is not None and prior[2] == "active":
                raise FoundationError("change_already_active", "Stop prior program use first")
            _check_program_observed(connection, part, installed=False)
            checksum = part.build_sha256
        elif isinstance(part, ActivityChange):
            checksum = hashlib.sha256(part.model_dump_json().encode("utf-8")).hexdigest().upper()
        elif isinstance(part, MethodChange):
            from .composition import method_checksum

            checksum = method_checksum(part.definition)
        else:
            from .binding import binding_checksum

            checksum = binding_checksum(part.definition)
        part_rows.append((part.kind, target_id, part.to_version, checksum, part.model_dump_json()))
    if isinstance(target, CompositeChange):
        target_id, version = target.package_id, target.to_version
    else:
        target_id, version = (
            (target.program_id, target.to_version)
            if isinstance(target, ProgramChange)
            else (target.change_id, target.to_version)
        )
    checksum = (
        hashlib.sha256(canonical_json(target.model_dump(mode="json")).encode("utf-8"))
        .hexdigest()
        .upper()
    )
    reorganization_targets: list[dict[str, object]] = []
    if not has_program:
        for part in parts:
            if isinstance(part, ActivityChange):
                _, reorganization_targets = _apply_subject_change(
                    connection,
                    ReorganizeActivitiesRequest(
                        operation_id=request.operation_id,
                        space_id=request.space_id,
                        actor=request.actor,
                        creations=part.creations,
                        revisions=part.revisions,
                        moves=part.moves,
                        rationale=part.rationale,
                        binding_disposition=part.binding_disposition,
                        decision_disposition=part.decision_disposition,
                        grant_disposition=part.grant_disposition,
                        event_boundary=part.event_boundary,
                    ),
                    now=now,
                    epoch=epoch,
                    authority=authority,
                    grants=grants,
                    decisions=decisions,
                )
                continue
            assert isinstance(part, (MethodChange, BindingChange))
            _publish_package_part(
                connection,
                part,
                request,
                mode=request.mode,
                now=now,
                epoch=epoch,
                authority_source=authority_source,
                grants=grants,
                decisions=decisions,
            )
    status = "prepared" if has_program else "active"
    connection.execute(
        "INSERT INTO change_packages(application_id,candidate_id,candidate_revision,decision_id,"
        "decision_revision,mode,target_kind,target_id,version,checksum,status,revision,"
        "created_at,changed_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,1,?,?)",
        (
            str(request.operation_id),
            str(request.candidate_id),
            revision,
            str(request.decision_id),
            request.decision_revision,
            request.mode,
            target.kind,
            str(target_id),
            version,
            checksum,
            status,
            now,
            now,
        ),
    )
    for ordinal, (kind, item_id, item_version, item_checksum, detail) in enumerate(part_rows):
        connection.execute(
            "INSERT INTO change_package_parts(application_id,ordinal,target_kind,target_id,"
            "version,checksum,detail_json) VALUES (?,?,?,?,?,?,?)",
            (
                str(request.operation_id),
                ordinal,
                kind,
                str(item_id),
                item_version,
                item_checksum,
                detail,
            ),
        )
    _package_event(
        connection,
        request.operation_id,
        1,
        request.operation_id,
        "prepare" if has_program else "apply",
        {"parts": [item[0] + ":" + str(item[1]) for item in part_rows], "mode": request.mode},
        now,
    )
    return {
        "application_id": str(request.operation_id),
        "status": status,
        "target_id": str(target_id),
        "version": version,
        "checksum": checksum,
        "parts": [item[0] + ":" + str(item[1]) for item in part_rows],
        "reorganization": reorganization_targets,
    }, [
        {"record_id": str(request.candidate_id), "revision": revision},
        {"record_id": str(request.decision_id), "revision": request.decision_revision},
        *[
            {"record_id": str(item_id), "revision": item_version}
            for _, item_id, item_version, _, _ in part_rows
        ],
        *reorganization_targets,
    ]


def _restore_activity_change(
    connection: sqlite3.Connection,
    part: ActivityChange,
    request: RestoreCandidateRequest,
    *,
    now: str,
    epoch: int,
    authority: LocalAuthority,
    grants: list[dict[str, object]],
    decisions: list[dict[str, object]],
) -> tuple[list[str], list[dict[str, object]]]:
    """Reverse exact current membership; leave changed successors for explicit review."""

    pending: list[str] = []
    for move in part.moves:
        revision, status, parent = _subject_current(connection, move.work_id, "work")
        if revision != move.expected_revision + 1 or parent != str(move.to_activity_id):
            pending.append(f"work:{move.work_id}:changed_after_application")
        elif status == "deleted":
            pending.append(f"work:{move.work_id}:deleted")
        elif connection.execute(
            "SELECT 1 FROM execution_attempts WHERE work_id=? AND status='active' LIMIT 1",
            (str(move.work_id),),
        ).fetchone():
            pending.append(f"work:{move.work_id}:attempt_active")
    for change in part.revisions:
        revision, _, _ = _subject_current(connection, change.activity_id, "activity")
        if revision != change.expected_revision + 1:
            pending.append(f"activity:{change.activity_id}:changed_after_application")
    for creation in part.creations:
        revision, _, _ = _subject_current(connection, creation.activity_id, "activity")
        if revision != 1:
            pending.append(f"activity:{creation.activity_id}:changed_after_application")
        moved = {
            str(item.work_id) for item in part.moves if item.to_activity_id == creation.activity_id
        }
        others = connection.execute(
            "SELECT record_id FROM subject_records WHERE kind='work' AND parent_id=? "
            "AND status!='deleted'",
            (str(creation.activity_id),),
        ).fetchall()
        if any(row[0] not in moved for row in others):
            pending.append(f"activity:{creation.activity_id}:new_work")
    if pending:
        return pending, []
    targets: list[dict[str, object]] = []
    reopened: set[UUID] = set()
    reverse_destinations = {move.from_activity_id for move in part.moves}
    for change in part.revisions:
        if change.activity_id not in reverse_destinations:
            continue
        prior = ActivityState.model_validate(
            _subject_state(connection, change.activity_id, change.expected_revision)
        )
        _, current_status, _ = _subject_current(connection, change.activity_id, "activity")
        if current_status == "ongoing":
            continue
        if prior.status != "ongoing":
            return [f"activity:{change.activity_id}:not_reopenable"], []
        _write_subject(
            connection,
            record_id=change.activity_id,
            kind="activity",
            parent_id=None,
            operation_id=request.operation_id,
            actor=request.actor,
            now=now,
            status=prior.status,
            state=prior,
            revision=change.expected_revision + 2,
        )
        targets.append(
            {"record_id": str(change.activity_id), "revision": change.expected_revision + 2}
        )
        reopened.add(change.activity_id)
    revisions = [
        ActivityRevisionChange(
            activity_id=change.activity_id,
            expected_revision=change.expected_revision + 1,
            state=ActivityState.model_validate(
                _subject_state(connection, change.activity_id, change.expected_revision)
            ),
        )
        for change in part.revisions
        if change.activity_id not in reopened
    ]
    revisions.extend(
        ActivityRevisionChange(
            activity_id=creation.activity_id,
            expected_revision=1,
            state=creation.state.model_copy(update={"status": "completed"}),
        )
        for creation in part.creations
    )
    _, restored_targets = _apply_subject_change(
        connection,
        ReorganizeActivitiesRequest(
            operation_id=request.operation_id,
            space_id=request.space_id,
            actor=request.actor,
            revisions=tuple(revisions),
            moves=tuple(
                WorkActivityMove(
                    work_id=move.work_id,
                    expected_revision=move.expected_revision + 1,
                    from_activity_id=move.to_activity_id,
                    to_activity_id=move.from_activity_id,
                )
                for move in part.moves
            ),
            rationale=request.reason,
            binding_disposition="Prior Binding scopes remain separate and unchanged",
            decision_disposition="Prior Decision scopes remain separate and unchanged",
            grant_disposition="Prior Grant scopes remain separate and unchanged",
            event_boundary=request.external_effects,
        ),
        now=now,
        epoch=epoch,
        authority=authority,
        grants=grants,
        decisions=decisions,
    )
    return [], targets + restored_targets


def _package_followup(
    connection: sqlite3.Connection,
    request: StopCandidateRequest | RestoreCandidateRequest | RecordChangeOutcomeRequest,
    app: ChangeApplication,
    *,
    now: str,
    epoch: int,
    authority_source: str,
    authority: LocalAuthority,
    grants: list[dict[str, object]],
    decisions: list[dict[str, object]],
) -> tuple[dict[str, object], list[dict[str, object]]]:
    parts = _package_parts(connection, app.application_id)
    detail: dict[str, object]
    followup_targets: list[dict[str, object]] = []
    if isinstance(request, StopCandidateRequest):
        if app.status not in ("prepared", "active"):
            raise FoundationError("invalid_transition", "Only prepared or active package can stop")
        for part in parts if app.status == "active" else ():
            if not isinstance(part, BindingChange):
                continue
            from .binding import _version, apply_binding_change

            version = _version(connection, part.binding_id, part.to_version)
            if version.checksum != part_rows_checksum(connection, app.application_id, part):
                raise FoundationError("stale_binding", "Package Binding changed")
            remaining = _active_target_modes(
                connection,
                "binding",
                part.binding_id,
                part.to_version,
                excluding=app.application_id,
            )
            desired: Literal["paused", "trial", "enabled"] = (
                "enabled"
                if any(mode == "regular" for mode, _ in remaining)
                else "trial"
                if remaining
                else "paused"
            )
            if version.state != desired and version.state != "retired":
                apply_binding_change(
                    connection,
                    SetBindingStateRequest(
                        operation_id=request.operation_id,
                        space_id=request.space_id,
                        actor=request.actor,
                        binding_id=part.binding_id,
                        version=part.to_version,
                        expected_state_revision=version.state_revision,
                        state=desired,
                    ),
                    now=now,
                    epoch=epoch,
                    authority_source=authority_source,
                    grants=grants,
                    decisions=decisions,
                )
        status, kind = "stopped", "stop"
        detail = {
            "reason": request.reason,
            "started_works": request.started_works,
            "external_effects": request.external_effects,
        }
    elif isinstance(request, RestoreCandidateRequest):
        if app.status not in ("stopped", "partial"):
            raise FoundationError("invalid_transition", "Stop package before restoration")
        activated = bool(
            connection.execute(
                "SELECT 1 FROM change_package_events WHERE application_id=? "
                "AND kind IN ('apply','confirm') LIMIT 1",
                (str(app.application_id),),
            ).fetchone()
        )
        pending: list[str] = []
        for part in reversed(parts):
            if isinstance(part, ProgramChange):
                newer = connection.execute(
                    "SELECT 1 FROM change_package_parts t JOIN change_packages p "
                    "ON p.application_id=t.application_id WHERE t.target_kind='program' "
                    "AND t.target_id=? AND t.version>? AND p.status IN ('active','stopped') "
                    "LIMIT 1",
                    (str(part.program_id), part.to_version),
                ).fetchone()
                if newer:
                    raise FoundationError("stale_program", "Newer program must be addressed first")
                _check_program_observed(connection, part, installed=False)
                if part.from_version is not None and not _active_target_modes(
                    connection, "program", part.program_id, part.from_version
                ):
                    pending.append(f"program:{part.program_id}:prior_needs_admission")
            elif not activated:
                continue
            elif isinstance(part, ActivityChange):
                _authorize(
                    connection,
                    actor=request.actor,
                    action="activity.write",
                    epoch=epoch,
                    resource_type="space",
                )
                activity_pending, activity_targets = _restore_activity_change(
                    connection,
                    part,
                    request,
                    now=now,
                    epoch=epoch,
                    authority=authority,
                    grants=grants,
                    decisions=decisions,
                )
                pending.extend(activity_pending)
                followup_targets.extend(activity_targets)
            elif isinstance(part, MethodChange):
                from .composition import _method

                row = connection.execute(
                    "SELECT version,checksum FROM method_versions WHERE method_id=? "
                    "ORDER BY version DESC LIMIT 1",
                    (str(part.method_id),),
                ).fetchone()
                if row is None or (row[0], row[1]) != (
                    part.to_version,
                    part_rows_checksum(connection, app.application_id, part),
                ):
                    raise FoundationError("stale_method", "Method changed after package")
                if part.from_version is not None:
                    assert part.from_checksum is not None
                    try:
                        _method(
                            connection,
                            MethodRef(
                                method_id=part.method_id,
                                version=part.from_version,
                                checksum=part.from_checksum,
                            ),
                        )
                    except FoundationError:
                        pending.append(f"method:{part.method_id}:prior_unavailable")
                    if not _active_target_modes(
                        connection, "method", part.method_id, part.from_version
                    ):
                        pending.append(f"method:{part.method_id}:prior_needs_admission")
            else:
                from .binding import _version, apply_binding_change

                row = connection.execute(
                    "SELECT max(version) FROM binding_versions WHERE binding_id=?",
                    (str(part.binding_id),),
                ).fetchone()
                if row is None or row[0] != part.to_version:
                    raise FoundationError("stale_binding", "Binding changed after package")
                if part.from_version is not None:
                    prior = _version(connection, part.binding_id, part.from_version)
                    if prior.checksum != part.from_checksum:
                        raise FoundationError("stale_binding", "Prior Binding differs")
                    apply_binding_change(
                        connection,
                        CreateBindingVersionRequest(
                            operation_id=request.operation_id,
                            space_id=request.space_id,
                            actor=request.actor,
                            binding_id=part.binding_id,
                            version=part.to_version + 1,
                            definition=prior.definition,
                        ),
                        now=now,
                        epoch=epoch,
                        authority_source=authority_source,
                        grants=grants,
                        decisions=decisions,
                    )
                    apply_binding_change(
                        connection,
                        SetBindingStateRequest(
                            operation_id=request.operation_id,
                            space_id=request.space_id,
                            actor=request.actor,
                            binding_id=part.binding_id,
                            version=part.to_version + 1,
                            expected_state_revision=1,
                            state="enabled",
                        ),
                        now=now,
                        epoch=epoch,
                        authority_source=authority_source,
                        grants=grants,
                        decisions=decisions,
                    )
        status, kind = ("partial" if pending else "restored"), "restore"
        detail = {
            "reason": request.reason,
            "data_restoration": request.data_restoration,
            "external_effects": request.external_effects,
            "pending": pending,
        }
    else:
        from .knowledge import _require_ref

        for ref in request.evidence:
            _require_ref(connection, ref, request.actor, epoch)
        status, kind = app.status, "outcome"
        detail = {
            "outcome": request.outcome,
            "observation": request.observation,
            "evidence": [item.model_dump(mode="json") for item in request.evidence],
        }
    connection.execute(
        "UPDATE change_packages SET status=?,revision=revision+1,changed_at=? "
        "WHERE application_id=?",
        (status, now, str(app.application_id)),
    )
    _package_event(
        connection, app.application_id, app.revision + 1, request.operation_id, kind, detail, now
    )
    if isinstance(request, RecordChangeOutcomeRequest):
        for ordinal, ref in enumerate(request.evidence):
            connection.execute(
                "INSERT INTO change_package_evidence(application_id,event_revision,ordinal,"
                "target_id,target_revision) VALUES (?,?,?,?,?)",
                (
                    str(app.application_id),
                    app.revision + 1,
                    ordinal,
                    str(ref.record_id),
                    ref.revision,
                ),
            )
    return {
        "application_id": str(app.application_id),
        "revision": app.revision + 1,
        "status": status,
        **detail,
    }, [
        {"record_id": str(app.candidate_id), "revision": app.candidate_revision},
        *followup_targets,
    ]


def part_rows_checksum(
    connection: sqlite3.Connection,
    application_id: UUID,
    part: MethodChange | BindingChange | ProgramChange,
) -> str:
    target_id = (
        part.method_id
        if isinstance(part, MethodChange)
        else part.binding_id
        if isinstance(part, BindingChange)
        else part.program_id
    )
    row = connection.execute(
        "SELECT checksum FROM change_package_parts WHERE application_id=? AND target_kind=? "
        "AND target_id=? AND version=?",
        (str(application_id), part.kind, str(target_id), part.to_version),
    ).fetchone()
    if row is None:
        raise FoundationError("corrupt_space", "Change package part is absent")
    return str(row[0])


def apply_development_change(
    connection: sqlite3.Connection,
    request: DevelopmentChange,
    *,
    now: str,
    epoch: int,
    authority_source: str,
    authority: LocalAuthority,
    grants: list[dict[str, object]],
    decisions: list[dict[str, object]],
) -> tuple[dict[str, object], list[dict[str, object]]]:
    """Mutate with the caller's existing operation, receipt and transaction."""

    if isinstance(request, (CreateDevelopmentRequest, ReviseDevelopmentRequest)):
        state = request.state
        _check_refs(connection, state, request.actor, epoch)
        if isinstance(state, SleepState):
            _check_sleep(connection, state, request.actor, epoch)
        else:
            _check_candidate(connection, state, request.actor, epoch)
        if isinstance(request, CreateDevelopmentRequest):
            revision = 1
            if isinstance(state, SleepState):
                existing = connection.execute(
                    "SELECT 1 FROM development_revisions "
                    "WHERE json_extract(CAST(payload AS TEXT),'$.work_id')=? LIMIT 1",
                    (str(state.work_id),),
                ).fetchone()
                if existing:
                    raise FoundationError("record_exists", "Sleep Work already has saved analysis")
                current_revision = connection.execute(
                    "SELECT state_revision FROM spaces WHERE singleton=1"
                ).fetchone()[0]
                if state.intake_cutoff_revision > int(current_revision):
                    raise FoundationError("stale_revision", "Sleep cutoff is from the future")
        else:
            previous_revision, previous = _current(connection, request.record_id)
            if previous_revision != request.expected_revision or type(previous) is not type(state):
                raise FoundationError("stale_revision", "Development record changed")
            if isinstance(state, SleepState):
                assert isinstance(previous, SleepState)
                _check_progress(previous, state)
            revision = previous_revision + 1
        _save_revision(connection, request, state, revision, now)
        return {"record_id": str(request.record_id), "revision": revision}, [
            {"record_id": str(request.record_id), "revision": revision}
        ]
    if isinstance(request, DeleteDevelopmentRequest):
        revision, _ = _current(connection, request.record_id)
        if revision != request.expected_revision:
            raise FoundationError("stale_revision", "Development record changed")
        if connection.execute(
            "SELECT 1 FROM change_applications WHERE candidate_id=? "
            "AND status IN ('active','partial') LIMIT 1",
            (str(request.record_id),),
        ).fetchone():
            raise FoundationError(
                "change_in_use", "Stop active applications before deleting candidate"
            )
        if (
            int(connection.execute("PRAGMA user_version").fetchone()[0]) >= 12
            and connection.execute(
                "SELECT 1 FROM change_packages WHERE candidate_id=? "
                "AND status IN ('prepared','active','partial') LIMIT 1",
                (str(request.record_id),),
            ).fetchone()
        ):
            raise FoundationError("change_in_use", "Resolve live package before deletion")
        _sanitize_development(connection, request.record_id, now, deleted=True)
        connection.execute(
            "UPDATE development_records SET current_revision=?,updated_at=? WHERE record_id=?",
            (revision + 1, now, str(request.record_id)),
        )
        connection.execute(
            "INSERT INTO development_revisions(record_id,revision,operation_id,actor,created_at) "
            "VALUES (?,?,?,?,?)",
            (str(request.record_id), revision + 1, str(request.operation_id), request.actor, now),
        )
        connection.execute(
            "INSERT INTO development_deletion_jobs(operation_id,record_id,status,created_at) "
            "VALUES (?,?,'pending',?)",
            (str(request.operation_id), str(request.record_id), now),
        )
        return {
            "record_id": str(request.record_id),
            "revision": revision + 1,
            "deletion": "pending",
        }, [{"record_id": str(request.record_id), "revision": revision + 1}]
    if isinstance(request, ApplyCandidateRequest):
        _authorize(
            connection,
            actor=request.actor,
            action="record.read",
            epoch=epoch,
            resource_type="artifact",
            resource_id=request.candidate_id,
        )
        revision, state = _current(connection, request.candidate_id)
        if revision != request.candidate_revision or not isinstance(state, ChangeCandidateState):
            raise FoundationError("stale_candidate", "Candidate proposal changed")
        if isinstance(state.target, (ProgramChange, CompositeChange, ActivityChange)):
            return _package_apply(
                connection,
                request,
                state,
                revision,
                now=now,
                epoch=epoch,
                authority_source=authority_source,
                authority=authority,
                grants=grants,
                decisions=decisions,
            )
        decision = _decision(connection, request, state)
        target = state.target
        target_id = target.method_id if isinstance(target, MethodChange) else target.binding_id
        existing_modes = _active_target_modes(connection, target.kind, target_id, target.to_version)
        for _, existing_decision in existing_modes:
            if (
                decision.scope_global
                or existing_decision.scope_global
                or decision.scope_activity_id == existing_decision.scope_activity_id
            ):
                raise FoundationError(
                    "change_already_active", "Target version already has adoption in this scope"
                )
        _authorize(
            connection,
            actor=request.actor,
            action="method.use",
            epoch=epoch,
            resource_type="activity" if decision.scope_activity_id else "space",
            resource_id=decision.scope_activity_id,
        )
        if isinstance(target, MethodChange):
            from .composition import apply_composition_change, method_checksum

            checksum = method_checksum(target.definition)
            row = connection.execute(
                "SELECT checksum,payload FROM method_versions WHERE method_id=? AND version=?",
                (str(target_id), target.to_version),
            ).fetchone()
            if row is None:
                method_request = CreateMethodVersionRequest(
                    operation_id=request.operation_id,
                    space_id=request.space_id,
                    actor=request.actor,
                    method_id=target.method_id,
                    version=target.to_version,
                    definition=target.definition,
                )
                apply_composition_change(
                    connection,
                    method_request,
                    now=now,
                    epoch=epoch,
                    grants=grants,
                    decisions=decisions,
                )
            elif row[0] != checksum or row[1] is None:
                raise FoundationError("version_conflict", "Published Method differs from candidate")
        else:
            from .binding import _version, apply_binding_change, binding_checksum

            checksum = binding_checksum(target.definition)
            row = connection.execute(
                "SELECT checksum,payload FROM binding_versions WHERE binding_id=? AND version=?",
                (str(target_id), target.to_version),
            ).fetchone()
            if row is None:
                binding_request = CreateBindingVersionRequest(
                    operation_id=request.operation_id,
                    space_id=request.space_id,
                    actor=request.actor,
                    binding_id=target.binding_id,
                    version=target.to_version,
                    definition=target.definition,
                )
                apply_binding_change(
                    connection,
                    binding_request,
                    now=now,
                    epoch=epoch,
                    authority_source=authority_source,
                    grants=grants,
                    decisions=decisions,
                )
            elif row[0] != checksum or row[1] is None:
                raise FoundationError(
                    "version_conflict", "Published Binding differs from candidate"
                )
            version = _version(connection, target.binding_id, target.to_version)
            desired: Literal["trial", "enabled"] = (
                "enabled"
                if request.mode == "regular" or any(mode == "regular" for mode, _ in existing_modes)
                else "trial"
            )
            if version.state != desired:
                sub_state = SetBindingStateRequest(
                    operation_id=request.operation_id,
                    space_id=request.space_id,
                    actor=request.actor,
                    binding_id=target.binding_id,
                    version=target.to_version,
                    expected_state_revision=version.state_revision,
                    state=desired,
                )
                apply_binding_change(
                    connection,
                    sub_state,
                    now=now,
                    epoch=epoch,
                    authority_source=authority_source,
                    grants=grants,
                    decisions=decisions,
                )
        connection.execute(
            "INSERT INTO change_applications(application_id,candidate_id,candidate_revision,"
            "decision_id,decision_revision,mode,target_kind,target_id,version,checksum,status,"
            "revision,created_at,changed_at) VALUES (?,?,?,?,?,?,?,?,?,?,'active',1,?,?)",
            (
                str(request.operation_id),
                str(request.candidate_id),
                request.candidate_revision,
                str(request.decision_id),
                request.decision_revision,
                request.mode,
                target.kind,
                str(target_id),
                target.to_version,
                checksum,
                now,
                now,
            ),
        )
        _event(
            connection,
            request.operation_id,
            1,
            request.operation_id,
            "apply",
            {
                "target_id": str(target_id),
                "version": target.to_version,
                "checksum": checksum,
                "decision": str(request.decision_id),
                "mode": request.mode,
            },
            now,
        )
        return {
            "application_id": str(request.operation_id),
            "target_id": str(target_id),
            "version": target.to_version,
            "checksum": checksum,
            "status": "active",
        }, [
            {"record_id": str(request.candidate_id), "revision": revision},
            {"record_id": str(request.decision_id), "revision": request.decision_revision},
            {"record_id": str(target_id), "revision": target.to_version},
        ]
    if isinstance(request, ConfirmProgramInstallRequest):
        app = _application(connection, request.application_id)
        if app.target_kind not in ("program", "composite") or app.status != "prepared":
            raise FoundationError("invalid_transition", "Only a prepared program can confirm")
        if app.revision != request.expected_revision:
            raise FoundationError("stale_revision", "Change application changed")
        current_revision, candidate = _current(connection, app.candidate_id)
        if current_revision != app.candidate_revision or not isinstance(
            candidate, ChangeCandidateState
        ):
            raise FoundationError("stale_candidate", "Prepared candidate changed")
        admission = ApplyCandidateRequest(
            operation_id=request.operation_id,
            space_id=request.space_id,
            actor=request.actor,
            candidate_id=app.candidate_id,
            candidate_revision=app.candidate_revision,
            decision_id=app.decision_id,
            decision_revision=app.decision_revision,
            mode=app.mode,
        )
        _decision(connection, admission, candidate)
        _check_candidate(connection, candidate, request.actor, epoch)
        parts = _package_parts(connection, app.application_id)
        for part in parts:
            if isinstance(part, ProgramChange):
                _check_program_observed(connection, part, installed=True)
            else:
                assert isinstance(part, (MethodChange, BindingChange))
                _publish_package_part(
                    connection,
                    part,
                    request,
                    mode=app.mode,
                    now=now,
                    epoch=epoch,
                    authority_source=authority_source,
                    grants=grants,
                    decisions=decisions,
                )
        connection.execute(
            "UPDATE change_packages SET status='active',revision=revision+1,changed_at=? "
            "WHERE application_id=?",
            (now, str(request.application_id)),
        )
        _package_event(
            connection,
            request.application_id,
            app.revision + 1,
            request.operation_id,
            "confirm",
            {
                "observed_programs": [
                    str(part.program_id) for part in parts if isinstance(part, ProgramChange)
                ]
            },
            now,
        )
        return {"application_id": str(request.application_id), "status": "active"}, [
            {"record_id": str(app.candidate_id), "revision": app.candidate_revision},
            {"record_id": str(app.decision_id), "revision": app.decision_revision},
        ]
    app = _application(connection, request.application_id)
    if app.revision != request.expected_revision:
        raise FoundationError("stale_revision", "Change application changed")
    if app.target_kind in ("program", "composite", "activity"):
        return _package_followup(
            connection,
            request,
            app,
            now=now,
            epoch=epoch,
            authority_source=authority_source,
            authority=authority,
            grants=grants,
            decisions=decisions,
        )
    if isinstance(request, StopCandidateRequest):
        if app.status != "active":
            raise FoundationError("invalid_transition", "Only active application can stop")
        if app.target_kind == "binding":
            from .binding import _version, apply_binding_change

            version = _version(connection, app.target_id, app.version)
            if version.checksum != app.checksum:
                raise FoundationError("stale_binding", "Applied Binding changed")
            remaining_modes = _active_target_modes(
                connection, "binding", app.target_id, app.version, excluding=app.application_id
            )
            desired_state: Literal["paused", "trial", "enabled"] = (
                "enabled"
                if any(mode == "regular" for mode, _ in remaining_modes)
                else "trial"
                if remaining_modes
                else "paused"
            )
            if version.state != desired_state and version.state != "retired":
                stop_request = SetBindingStateRequest(
                    operation_id=request.operation_id,
                    space_id=request.space_id,
                    actor=request.actor,
                    binding_id=app.target_id,
                    version=app.version,
                    expected_state_revision=version.state_revision,
                    state=desired_state,
                )
                apply_binding_change(
                    connection,
                    stop_request,
                    now=now,
                    epoch=epoch,
                    authority_source=authority_source,
                    grants=grants,
                    decisions=decisions,
                )
        if app.target_kind == "method":
            observed_works = [
                row[0]
                for row in connection.execute(
                    "SELECT work_id FROM change_application_works WHERE application_id=? "
                    "ORDER BY created_at,work_id",
                    (str(request.application_id),),
                ).fetchall()
            ]
        else:
            observed_works = [
                row[0]
                for row in connection.execute(
                    "SELECT DISTINCT f.consumer_work_id FROM change_application_firings a "
                    "JOIN binding_firings f ON f.operation_id=a.operation_id "
                    "AND f.binding_id=a.binding_id WHERE a.application_id=? "
                    "AND f.consumer_work_id IS NOT NULL ORDER BY f.consumer_work_id",
                    (str(request.application_id),),
                ).fetchall()
            ]
        detail: dict[str, object] = {
            "reason": request.reason,
            "started_works": request.started_works,
            "observed_work_ids": observed_works,
            "external_effects": request.external_effects,
        }
        status = "stopped"
        kind = "stop"
    elif isinstance(request, RestoreCandidateRequest):
        if app.status not in ("stopped", "partial"):
            raise FoundationError("invalid_transition", "Stop new use before restoration")
        candidate = _at_revision(connection, app.candidate_id, app.candidate_revision)
        if not isinstance(candidate, ChangeCandidateState):
            raise FoundationError("wrong_kind", "Application candidate is unavailable")
        legacy_target = candidate.target
        if not isinstance(legacy_target, (MethodChange, BindingChange)):
            raise FoundationError("wrong_kind", "Application target differs from its candidate")
        if app.target_kind == "method":
            from .composition import _method

            row = connection.execute(
                "SELECT version,checksum FROM method_versions WHERE method_id=? "
                "ORDER BY version DESC LIMIT 1",
                (str(app.target_id),),
            ).fetchone()
            if row is None or row[0] != app.version or row[1] != app.checksum:
                raise FoundationError(
                    "stale_method", "Method changed since application; reassess restoration"
                )
            restored = legacy_target.from_version
            restoration_pending: str | None = None
            if restored is not None:
                assert legacy_target.from_checksum is not None
                try:
                    _method(
                        connection,
                        MethodRef(
                            method_id=app.target_id,
                            version=restored,
                            checksum=legacy_target.from_checksum,
                        ),
                    )
                except FoundationError:
                    restoration_pending = "prior_method_unavailable"
                prior_rows = connection.execute(
                    "SELECT 1 FROM change_applications WHERE target_kind='method' "
                    "AND target_id=? AND version=? LIMIT 1",
                    (str(app.target_id), restored),
                ).fetchone()
                if prior_rows is not None:
                    decision_row = connection.execute(
                        "SELECT body_json FROM record_revisions WHERE record_id=? AND revision=?",
                        (str(app.decision_id), app.decision_revision),
                    ).fetchone()
                    current_decision = (
                        _decision_body(decision_row[0])
                        if decision_row is not None and decision_row[0] is not None
                        else None
                    )
                    prior_modes = _active_target_modes(
                        connection, "method", app.target_id, restored
                    )
                    if not any(
                        prior_decision.scope_global
                        or (
                            isinstance(current_decision, ChangeDecisionState)
                            and not current_decision.scope_global
                            and prior_decision.scope_activity_id
                            == current_decision.scope_activity_id
                        )
                        for _, prior_decision in prior_modes
                    ):
                        restoration_pending = "prior_method_needs_current_admission"
        else:
            from .binding import _version, apply_binding_change

            current = connection.execute(
                "SELECT max(version) FROM binding_versions WHERE binding_id=?",
                (str(app.target_id),),
            ).fetchone()[0]
            if current != app.version:
                raise FoundationError("stale_binding", "Binding changed since application")
            if legacy_target.from_version is None:
                restored = None
            else:
                prior = _version(connection, app.target_id, legacy_target.from_version)
                restore_request = CreateBindingVersionRequest(
                    operation_id=request.operation_id,
                    space_id=request.space_id,
                    actor=request.actor,
                    binding_id=app.target_id,
                    version=app.version + 1,
                    definition=prior.definition,
                )
                apply_binding_change(
                    connection,
                    restore_request,
                    now=now,
                    epoch=epoch,
                    authority_source=authority_source,
                    grants=grants,
                    decisions=decisions,
                )
                restore_state = SetBindingStateRequest(
                    operation_id=request.operation_id,
                    space_id=request.space_id,
                    actor=request.actor,
                    binding_id=app.target_id,
                    version=app.version + 1,
                    expected_state_revision=1,
                    state="enabled",
                )
                apply_binding_change(
                    connection,
                    restore_state,
                    now=now,
                    epoch=epoch,
                    authority_source=authority_source,
                    grants=grants,
                    decisions=decisions,
                )
                restored = app.version + 1
        detail = {
            "reason": request.reason,
            "data_restoration": request.data_restoration,
            "external_effects": request.external_effects,
            "restored_version": restored,
        }
        if app.target_kind == "method" and restoration_pending is not None:
            detail["pending"] = restoration_pending
        status = (
            "partial"
            if app.target_kind == "method" and restoration_pending is not None
            else "restored"
        )
        kind = "restore"
    else:
        assert isinstance(request, RecordChangeOutcomeRequest)
        from .knowledge import _require_ref

        for ref in request.evidence:
            _require_ref(connection, ref, request.actor, epoch)
        detail = {
            "outcome": request.outcome,
            "observation": request.observation,
            "evidence": [item.model_dump(mode="json") for item in request.evidence],
        }
        status = app.status
        kind = "outcome"
    connection.execute(
        "UPDATE change_applications SET status=?,revision=?,changed_at=? WHERE application_id=?",
        (status, app.revision + 1, now, str(request.application_id)),
    )
    _event(
        connection,
        request.application_id,
        app.revision + 1,
        request.operation_id,
        kind,
        detail,
        now,
    )
    if isinstance(request, RecordChangeOutcomeRequest):
        for ordinal, ref in enumerate(request.evidence):
            connection.execute(
                "INSERT INTO change_application_evidence("
                "application_id,event_revision,ordinal,target_id,target_revision) "
                "VALUES (?,?,?,?,?)",
                (
                    str(request.application_id),
                    app.revision + 1,
                    ordinal,
                    str(ref.record_id),
                    ref.revision,
                ),
            )
    return {
        "application_id": str(request.application_id),
        "revision": app.revision + 1,
        "status": status,
        **detail,
    }, [{"record_id": str(app.candidate_id), "revision": app.candidate_revision}]


def _sanitize_development(
    connection: sqlite3.Connection, record_id: UUID, now: str, *, deleted: bool
) -> None:
    ids = {str(record_id)}
    queue = [str(record_id)]
    while queue:
        current = queue.pop()
        for (child,) in connection.execute(
            "SELECT DISTINCT record_id FROM development_edges WHERE target_id=?", (current,)
        ).fetchall():
            if child not in ids:
                ids.add(child)
                queue.append(child)
    for item in ids:
        _sanitize_application_evidence(connection, UUID(item))
        for (operation_id,) in connection.execute(
            "SELECT operation_id FROM development_revisions WHERE record_id=?", (item,)
        ).fetchall():
            connection.execute("DELETE FROM receipts WHERE operation_id=?", (operation_id,))
            connection.execute(
                "UPDATE operations SET fingerprint='DELETED' WHERE operation_id=?", (operation_id,)
            )
        connection.execute(
            "UPDATE development_revisions SET payload=NULL,sha256=NULL WHERE record_id=?", (item,)
        )
        connection.execute(
            "UPDATE development_records SET status=?,updated_at=? WHERE record_id=?",
            ("deleted" if item == str(record_id) and deleted else "unavailable", now, item),
        )
        connection.execute(
            "UPDATE change_applications SET status='partial',changed_at=? "
            "WHERE candidate_id=? AND status IN ('active','stopped')",
            (now, item),
        )
        if int(connection.execute("PRAGMA user_version").fetchone()[0]) >= 12:
            connection.execute(
                "UPDATE change_packages SET status='partial',changed_at=? "
                "WHERE candidate_id=? AND status IN ('prepared','active','stopped')",
                (now, item),
            )
            for (application_id,) in connection.execute(
                "SELECT application_id FROM change_packages WHERE candidate_id=?", (item,)
            ).fetchall():
                for (operation_id,) in connection.execute(
                    "SELECT operation_id FROM change_package_events WHERE application_id=?",
                    (application_id,),
                ).fetchall():
                    connection.execute("DELETE FROM receipts WHERE operation_id=?", (operation_id,))
                    connection.execute(
                        "UPDATE operations SET fingerprint='DELETED' WHERE operation_id=?",
                        (operation_id,),
                    )
                connection.execute(
                    "UPDATE change_package_events SET detail_json='{}' WHERE application_id=?",
                    (application_id,),
                )
        for (application_id,) in connection.execute(
            "SELECT application_id FROM change_applications WHERE candidate_id=?", (item,)
        ).fetchall():
            for (operation_id,) in connection.execute(
                "SELECT operation_id FROM change_application_events WHERE application_id=?",
                (application_id,),
            ).fetchall():
                connection.execute("DELETE FROM receipts WHERE operation_id=?", (operation_id,))
                connection.execute(
                    "UPDATE operations SET fingerprint='DELETED' WHERE operation_id=?",
                    (operation_id,),
                )
            connection.execute(
                "UPDATE change_application_events SET detail_json='{}' WHERE application_id=?",
                (application_id,),
            )
    # Preserve snapshots from before all affected development payloads existed.
    # Knowledge deletion applies its own earlier source boundary as well.
    marks = ",".join("?" for _ in ids)
    earliest = connection.execute(
        "SELECT MIN(o.state_revision) FROM development_revisions r "
        "JOIN operations o ON o.operation_id=r.operation_id "
        f"WHERE r.record_id IN ({marks})",
        tuple(sorted(ids)),
    ).fetchone()[0]
    if earliest is not None:
        connection.execute(
            "UPDATE backup_inventory SET status='contaminated' "
            "WHERE status IN ('planned','failed','complete') AND state_revision >= ?",
            (earliest,),
        )


def _sanitize_application_evidence(connection: sqlite3.Connection, record_id: UUID) -> None:
    if int(connection.execute("PRAGMA user_version").fetchone()[0]) >= 12:
        for application_id, event_revision, operation_id in connection.execute(
            "SELECT DISTINCT e.application_id,e.event_revision,v.operation_id "
            "FROM change_package_evidence e JOIN change_package_events v "
            "ON v.application_id=e.application_id AND v.revision=e.event_revision "
            "WHERE e.target_id=?",
            (str(record_id),),
        ).fetchall():
            connection.execute(
                "UPDATE change_package_events SET detail_json='{}' "
                "WHERE application_id=? AND revision=?",
                (application_id, event_revision),
            )
            connection.execute("DELETE FROM receipts WHERE operation_id=?", (operation_id,))
            connection.execute(
                "UPDATE operations SET fingerprint='DELETED' WHERE operation_id=?",
                (operation_id,),
            )
    for application_id, event_revision, operation_id in connection.execute(
        "SELECT DISTINCT e.application_id,e.event_revision,v.operation_id "
        "FROM change_application_evidence e JOIN change_application_events v "
        "ON v.application_id=e.application_id AND v.revision=e.event_revision "
        "WHERE e.target_id=?",
        (str(record_id),),
    ).fetchall():
        connection.execute(
            "UPDATE change_application_events SET detail_json='{}' "
            "WHERE application_id=? AND revision=?",
            (application_id, event_revision),
        )
        connection.execute("DELETE FROM receipts WHERE operation_id=?", (operation_id,))
        connection.execute(
            "UPDATE operations SET fingerprint='DELETED' WHERE operation_id=?",
            (operation_id,),
        )


def sanitize_deleted_development_dependency(
    connection: sqlite3.Connection, record_id: UUID, now: str
) -> None:
    _sanitize_application_evidence(connection, record_id)
    for (child,) in connection.execute(
        "SELECT DISTINCT record_id FROM development_edges WHERE target_id=?", (str(record_id),)
    ).fetchall():
        _sanitize_development(connection, UUID(child), now, deleted=False)


def sanitize_deleted_change_target(
    connection: sqlite3.Connection, target_id: UUID, version: int, now: str
) -> None:
    for (child,) in connection.execute(
        "SELECT DISTINCT record_id FROM development_edges WHERE target_id=? "
        "AND target_revision=? AND role IN ('target_previous','target_proposed')",
        (str(target_id), version),
    ).fetchall():
        _sanitize_development(connection, UUID(child), now, deleted=False)


def read_development(
    path: Path, record_id: UUID, authority: LocalAuthority, revision: int | None = None
) -> DevelopmentRevision:
    with space_connection(path) as (connection, info):
        _local_space(authority, info)
        if info.schema_version < 11 or info.recovery_state != "active":
            raise FoundationError("unsupported_schema", "Development reads need schema 11")
        _authorize(
            connection,
            actor=authority.actor,
            action="record.read",
            epoch=info.execution_epoch,
            resource_type="artifact",
            resource_id=record_id,
        )
        row = connection.execute(
            "SELECT r.status,r.current_revision,v.revision,v.operation_id,v.actor,"
            "v.created_at,v.payload "
            "FROM development_records r JOIN development_revisions v ON v.record_id=r.record_id "
            "AND v.revision=COALESCE(?,r.current_revision) WHERE r.record_id=?",
            (revision, str(record_id)),
        ).fetchone()
        if row is None:
            raise FoundationError("not_found", "Development record or revision is absent")
        state = DEVELOPMENT_ADAPTER.validate_json(bytes(row[6])) if row[6] is not None else None
        return DevelopmentRevision(
            record_id=record_id,
            revision=row[2],
            operation_id=UUID(row[3]),
            actor=row[4],
            created_at=datetime.fromisoformat(row[5]),
            state=state,
            availability="available"
            if state is not None and row[0] == "active"
            else cast(
                Literal["unavailable", "deleted"],
                row[0] if row[0] != "active" else "unavailable",
            ),
        )


def read_change_application(
    path: Path, application_id: UUID, authority: LocalAuthority
) -> tuple[ChangeApplication, tuple[dict[str, object], ...]]:
    with space_connection(path) as (connection, info):
        _local_space(authority, info)
        if info.schema_version < 11 or info.recovery_state != "active":
            raise FoundationError("unsupported_schema", "Change reads need schema 11")
        app = _application(connection, application_id)
        _authorize(
            connection,
            actor=authority.actor,
            action="record.read",
            epoch=info.execution_epoch,
            resource_type="artifact",
            resource_id=app.candidate_id,
        )
        rows = connection.execute(
            "SELECT revision,operation_id,kind,detail_json,created_at "
            "FROM "
            + (
                "change_package_events"
                if app.target_kind in ("program", "composite")
                else "change_application_events"
            )
            + " WHERE application_id=? ORDER BY revision",
            (str(application_id),),
        ).fetchall()
        history = tuple(
            {
                "revision": row[0],
                "operation_id": row[1],
                "kind": row[2],
                "detail": json.loads(row[3]),
                "created_at": row[4],
            }
            for row in rows
        )
        return app, history


def list_change_applications(
    path: Path, authority: LocalAuthority, *, limit: int = 50
) -> tuple[ChangeApplication, ...]:
    if limit < 1 or limit > 100:
        raise FoundationError("invalid_request", "Application limit must be 1..100")
    with space_connection(path) as (connection, info):
        _local_space(authority, info)
        if info.schema_version < 11 or info.recovery_state != "active":
            raise FoundationError("unsupported_schema", "Change reads need schema 11")
        rows = connection.execute(
            "SELECT application_id,changed_at FROM change_applications "
            + (
                "UNION ALL SELECT application_id,changed_at FROM change_packages "
                if info.schema_version >= 12
                else ""
            )
            + "ORDER BY changed_at DESC"
        )
        visible: list[ChangeApplication] = []
        for row in rows:
            app = _application(connection, UUID(row[0]))
            try:
                _authorize(
                    connection,
                    actor=authority.actor,
                    action="record.read",
                    epoch=info.execution_epoch,
                    resource_type="artifact",
                    resource_id=app.candidate_id,
                )
            except FoundationError as error:
                if error.code in ("permission_denied", "decision_denied"):
                    continue
                raise
            visible.append(app)
            if len(visible) >= limit:
                break
        return tuple(visible)


def read_sleep_for_work(
    path: Path, work_id: UUID, authority: LocalAuthority
) -> DevelopmentRevision | None:
    with space_connection(path) as (connection, info):
        _local_space(authority, info)
        if info.schema_version < 11 or info.recovery_state != "active":
            return None
        _authorize(
            connection,
            actor=authority.actor,
            action="record.read",
            epoch=info.execution_epoch,
            resource_type="work",
            resource_id=work_id,
        )
        target_work_id = str(_root_work(connection, work_id))
        row = connection.execute(
            "SELECT r.record_id FROM development_records r JOIN development_revisions v "
            "ON v.record_id=r.record_id AND v.revision=r.current_revision "
            "WHERE r.kind='sleep' AND r.status='active' "
            "AND json_extract(CAST(v.payload AS TEXT),'$.work_id')=? LIMIT 1",
            (target_work_id,),
        ).fetchone()
    return read_development(path, UUID(row[0]), authority) if row else None


def list_development(
    path: Path, authority: LocalAuthority, *, kind: str | None = None, limit: int = 50
) -> tuple[DevelopmentRevision, ...]:
    if limit < 1 or limit > 100:
        raise FoundationError("invalid_request", "List limit must be 1..100")
    with space_connection(path) as (connection, info):
        _local_space(authority, info)
        if info.schema_version < 11 or info.recovery_state != "active":
            raise FoundationError("unsupported_schema", "Development reads need schema 11")
        rows = connection.execute(
            "SELECT r.record_id,r.status,v.revision,v.operation_id,v.actor,v.created_at,v.payload "
            "FROM development_records r JOIN development_revisions v ON v.record_id=r.record_id "
            "AND v.revision=r.current_revision WHERE (? IS NULL OR r.kind=?) "
            "ORDER BY r.updated_at DESC,r.record_id",
            (kind, kind),
        )
        visible: list[DevelopmentRevision] = []
        for row in rows:
            try:
                _authorize(
                    connection,
                    actor=authority.actor,
                    action="record.read",
                    epoch=info.execution_epoch,
                    resource_type="artifact",
                    resource_id=UUID(row[0]),
                )
            except FoundationError as error:
                if error.code in ("permission_denied", "decision_denied"):
                    continue
                raise
            visible.append(
                DevelopmentRevision(
                    record_id=UUID(row[0]),
                    revision=row[2],
                    operation_id=UUID(row[3]),
                    actor=row[4],
                    created_at=datetime.fromisoformat(row[5]),
                    state=DEVELOPMENT_ADAPTER.validate_json(bytes(row[6])) if row[6] else None,
                    availability="available" if row[6] and row[1] == "active" else row[1],
                )
            )
            if len(visible) >= limit:
                break
        return tuple(visible)


def list_sleep_sources(
    path: Path, sleep_id: UUID, authority: LocalAuthority, *, purpose: str, limit: int = 20
) -> dict[str, object]:
    """Stable bounded intake or rotating exploration, rechecking rights per page."""

    if purpose not in ("consolidation", "exploration") or limit < 1 or limit > 100:
        raise FoundationError("invalid_request", "Choose a bounded Sleep enumeration")
    with space_connection(path) as (connection, info):
        _local_space(authority, info)
        if info.schema_version < 11 or info.recovery_state != "active":
            raise FoundationError("unsupported_schema", "Sleep enumeration needs schema 11")
        _, state = _current(connection, sleep_id)
        _authorize(
            connection,
            actor=authority.actor,
            action="record.read",
            epoch=info.execution_epoch,
            resource_type="artifact",
            resource_id=sleep_id,
        )
        if not isinstance(state, SleepState):
            raise FoundationError("wrong_kind", "Address is not Sleep")
        cursor_revision = (
            state.enumeration_cursor_revision
            if purpose == "consolidation"
            else state.exploration_cursor_revision
        )
        cursor_id = (
            state.enumeration_cursor_id
            if purpose == "consolidation"
            else state.exploration_cursor_id
        )
        rows = connection.execute(
            "SELECT r.record_id,r.current_revision,r.created_state_revision,v.payload "
            "FROM knowledge_records r JOIN knowledge_revisions v ON v.record_id=r.record_id "
            "AND v.revision=r.current_revision WHERE r.kind='source' AND r.status='active' "
            "AND r.created_state_revision<=? AND "
            "(r.created_state_revision>? OR (r.created_state_revision=? AND r.record_id>?)) "
            "ORDER BY r.created_state_revision,r.record_id LIMIT ?",
            (
                state.intake_cutoff_revision,
                cursor_revision,
                cursor_revision,
                str(cursor_id or ""),
                limit * 5,
            ),
        ).fetchall()
        from .models import SourceState

        items: list[dict[str, object]] = []
        last_revision, last_id = cursor_revision, str(cursor_id or "")
        selected_ids = {str(item.source.record_id) for item in state.selected}
        consumed = 0
        for row in rows:
            consumed += 1
            last_revision, last_id = int(row[2]), row[0]
            source = SourceState.model_validate_json(bytes(row[3]))
            if source.scope_activity_id not in state.scope_activity_ids and not (
                source.scope_activity_id is None and state.include_free_conversation
            ):
                continue
            try:
                _authorize(
                    connection,
                    actor=authority.actor,
                    action="record.read",
                    epoch=info.execution_epoch,
                    resource_type="source",
                    resource_id=UUID(row[0]),
                )
            except FoundationError:
                continue
            if purpose == "exploration" and row[0] in selected_ids:
                continue
            if purpose == "exploration" and selected_ids:
                placeholders = ",".join("?" for _ in selected_ids)
                linked = connection.execute(
                    "SELECT 1 FROM knowledge_edges a JOIN knowledge_edges b "
                    "ON b.record_id=a.record_id AND b.revision=a.revision "
                    "JOIN knowledge_records r ON r.record_id=a.record_id "
                    "AND r.current_revision=a.revision AND r.kind='link' AND r.status='active' "
                    f"WHERE a.target_id IN ({placeholders}) AND b.target_id=? "
                    "AND a.role IN ('source','target') AND b.role IN ('source','target') "
                    "AND a.target_id!=b.target_id LIMIT 1",
                    (*sorted(selected_ids), row[0]),
                ).fetchone()
                if linked:
                    continue
            items.append(
                {
                    "record_id": row[0],
                    "revision": row[1],
                    "received_revision": row[2],
                    "channel": source.channel,
                    "scope_activity_id": str(source.scope_activity_id)
                    if source.scope_activity_id
                    else None,
                }
            )
            if len(items) >= limit:
                break
        return {
            "items": items,
            "next_cursor_revision": last_revision,
            "next_cursor_id": last_id or None,
            "cutoff_revision": state.intake_cutoff_revision,
            "exhausted": consumed == len(rows) and len(rows) < limit * 5,
        }


def check_new_method_use(
    connection: sqlite3.Connection, method_id: UUID, version: int, activity_id: UUID
) -> UUID | None:
    """A stopped application blocks new Work; existing pinned Work stays historical."""

    rows = connection.execute(
        "SELECT a.application_id,a.status,a.decision_id,a.decision_revision,a.mode "
        "FROM change_applications a "
        "WHERE a.target_kind='method' AND a.target_id=? AND a.version=?",
        (str(method_id), version),
    ).fetchall()
    if int(connection.execute("PRAGMA user_version").fetchone()[0]) >= 12:
        rows += connection.execute(
            "SELECT a.application_id,a.status,a.decision_id,a.decision_revision,a.mode "
            "FROM change_packages a JOIN change_package_parts p "
            "ON p.application_id=a.application_id WHERE p.target_kind='method' "
            "AND p.target_id=? AND p.version=?",
            (str(method_id), version),
        ).fetchall()
    if not rows:
        return None
    eligible: list[tuple[int, UUID]] = []
    for application_id, status, decision_id, decision_revision, mode in rows:
        row = connection.execute(
            "SELECT r.current_revision,v.body_json FROM records r JOIN record_revisions v "
            "ON v.record_id=r.record_id AND v.revision=r.current_revision WHERE r.record_id=?",
            (decision_id,),
        ).fetchone()
        if row is None:
            continue
        decision = _decision_body(row[1])
        if not isinstance(decision, ChangeDecisionState):
            continue
        if not (decision.scope_global or decision.scope_activity_id == activity_id):
            continue
        if status != "active" or row[0] != decision_revision or decision.status != "active":
            continue
        if mode == "trial":
            assert decision.trial_use_limit is not None
            table = (
                "change_package_works"
                if _package_exists(connection, UUID(application_id))
                else "change_application_works"
            )
            count = connection.execute(
                f"SELECT count(*) FROM {table} WHERE application_id=?",
                (application_id,),
            ).fetchone()[0]
            if count >= decision.trial_use_limit:
                continue
        eligible.append((0 if mode == "regular" else 1, UUID(application_id)))
    if not eligible:
        raise FoundationError("change_stopped", "New Work has no current bounded adoption")
    return min(eligible)[1]


def record_method_use(
    connection: sqlite3.Connection,
    application_id: UUID | None,
    work_id: UUID,
    now: str,
) -> None:
    if application_id is not None:
        table = (
            "change_package_works"
            if _package_exists(connection, application_id)
            else "change_application_works"
        )
        connection.execute(
            f"INSERT OR IGNORE INTO {table}(application_id,work_id,created_at) VALUES (?,?,?)",
            (str(application_id), str(work_id), now),
        )


def check_binding_trial_limit(
    connection: sqlite3.Connection, binding_id: UUID, version: int, activity_id: UUID
) -> UUID | None:
    rows = connection.execute(
        "SELECT a.application_id,a.status,a.decision_id,a.decision_revision,a.mode "
        "FROM change_applications a WHERE a.target_kind='binding' "
        "AND a.target_id=? AND a.version=?",
        (str(binding_id), version),
    ).fetchall()
    if int(connection.execute("PRAGMA user_version").fetchone()[0]) >= 12:
        rows += connection.execute(
            "SELECT a.application_id,a.status,a.decision_id,a.decision_revision,a.mode "
            "FROM change_packages a JOIN change_package_parts p "
            "ON p.application_id=a.application_id WHERE p.target_kind='binding' "
            "AND p.target_id=? AND p.version=?",
            (str(binding_id), version),
        ).fetchall()
    if not rows:
        return None
    eligible: list[tuple[int, UUID]] = []
    for application_id, status, decision_id, decision_revision, mode in rows:
        row = connection.execute(
            "SELECT r.current_revision,v.body_json FROM records r JOIN record_revisions v "
            "ON v.record_id=r.record_id AND v.revision=r.current_revision WHERE r.record_id=?",
            (decision_id,),
        ).fetchone()
        if row is None or status != "active" or row[0] != decision_revision:
            continue
        decision = _decision_body(row[1])
        if not isinstance(decision, ChangeDecisionState) or decision.status != "active":
            continue
        if not (decision.scope_global or decision.scope_activity_id == activity_id):
            continue
        if mode == "regular":
            eligible.append((0, UUID(application_id)))
            continue
        assert decision.trial_use_limit is not None
        table = (
            "change_package_firings"
            if _package_exists(connection, UUID(application_id))
            else "change_application_firings"
        )
        used = connection.execute(
            f"SELECT count(*) FROM {table} WHERE application_id=?",
            (application_id,),
        ).fetchone()[0]
        if used < decision.trial_use_limit:
            eligible.append((1, UUID(application_id)))
    if not eligible:
        raise FoundationError("change_stopped", "Binding has no current bounded adoption")
    return min(eligible)[1]


def record_binding_use(
    connection: sqlite3.Connection,
    application_id: UUID | None,
    operation_id: UUID,
    binding_id: UUID,
    now: str,
) -> None:
    if application_id is not None:
        table = (
            "change_package_firings"
            if _package_exists(connection, application_id)
            else "change_application_firings"
        )
        connection.execute(
            f"INSERT INTO {table}(application_id,operation_id,binding_id,created_at) "
            "VALUES (?,?,?,?)",
            (str(application_id), str(operation_id), str(binding_id), now),
        )


def _package_exists(connection: sqlite3.Connection, application_id: UUID) -> bool:
    return bool(
        int(connection.execute("PRAGMA user_version").fetchone()[0]) >= 12
        and connection.execute(
            "SELECT 1 FROM change_packages WHERE application_id=?",
            (str(application_id),),
        ).fetchone()
    )

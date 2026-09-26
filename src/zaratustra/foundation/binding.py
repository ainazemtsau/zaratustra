"""Versioned, address-only transfers between independent Activities."""

from __future__ import annotations

import hashlib
import json
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import cast
from uuid import UUID, uuid4, uuid5

from .composition import (
    _method,
    _plan,
    _validate_choice_leaves,
    _validate_plan,
    apply_composition_change,
)
from .models import (
    Action,
    ActivityState,
    ArtifactRef,
    BindingDefinition,
    BindingFiring,
    BindingInputRevision,
    BindingNewWork,
    BindingOffer,
    BindingOfferWork,
    BindingVersion,
    ChoiceState,
    CreateBindingVersionRequest,
    CreateCompositeWorkRequest,
    FireBindingRequest,
    MethodRef,
    MethodVersion,
    NamedInput,
    PlanChild,
    PlanNodeDecision,
    ResolveBindingOfferRequest,
    ReviseActivePlanRequest,
    SetBindingStateRequest,
    SpaceInfo,
    WorkPlan,
    WorkState,
)
from .operations import (
    LocalAuthority,
    _authorize,
    _authorize_artifact_ref,
    _decision_body,
    _hold_work_execution,
    _local_space,
    _subject_current,
    _subject_state,
    _write_subject,
)
from .storage import (
    BINDING_SCHEMA_NAME,
    BINDING_SCHEMA_SHA256,
    BINDING_SCHEMA_STATEMENTS,
    FoundationError,
    canonical_json,
    read_space,
    space_connection,
    utc_now,
)


def binding_checksum(definition: BindingDefinition) -> str:
    return (
        hashlib.sha256(canonical_json(definition.model_dump(mode="json")).encode())
        .hexdigest()
        .upper()
    )


def upgrade_binding_space(path: Path, authority: LocalAuthority) -> SpaceInfo:
    """Explicit additive schema 8 to 9 upgrade. Reads never upgrade."""

    with space_connection(path, writable=True) as (connection, info):
        _local_space(authority, info)
        if info.recovery_state != "active" or info.schema_version < 8:
            raise FoundationError("unsupported_schema", "Binding upgrade needs active schema 8")
        _authorize(
            connection,
            actor=authority.actor,
            action="maintenance.backup",
            epoch=info.execution_epoch,
        )
        if info.schema_version == 8:
            for statement in BINDING_SCHEMA_STATEMENTS:
                connection.execute(statement)
            now = utc_now().isoformat()
            connection.execute(
                "INSERT INTO schema_migrations(version, name, sha256, applied_at) "
                "VALUES (9, ?, ?, ?)",
                (BINDING_SCHEMA_NAME, BINDING_SCHEMA_SHA256, now),
            )
            connection.execute("PRAGMA user_version = 9")
            connection.execute(
                "UPDATE spaces SET state_revision = state_revision + 1 WHERE singleton = 1"
            )
            connection.execute(
                "INSERT INTO maintenance_events(event_id, kind, occurred_at, detail_json) "
                "VALUES (?, 'schema_upgrade', ?, ?)",
                (str(uuid4()), now, canonical_json({"from": 8, "to": 9})),
            )
    return read_space(path)


def _version(connection: sqlite3.Connection, binding_id: UUID, version: int) -> BindingVersion:
    row = connection.execute(
        "SELECT v.checksum, v.payload, v.first_event_state_revision, v.operation_id, v.created_at, "
        "s.revision, s.state FROM binding_versions v JOIN binding_states s "
        "ON s.binding_id = v.binding_id AND s.version = v.version AND s.revision = "
        "(SELECT max(revision) FROM binding_states WHERE binding_id = v.binding_id "
        "AND version = v.version) "
        "WHERE v.binding_id = ? AND v.version = ?",
        (str(binding_id), version),
    ).fetchone()
    if row is None:
        raise FoundationError("not_found", "Exact Binding version is absent")
    if row[1] is None:
        raise FoundationError("content_unavailable", "Binding definition was sanitized")
    definition = BindingDefinition.model_validate_json(bytes(row[1]))
    if binding_checksum(definition) != row[0]:
        raise FoundationError("corrupt_space", "Binding checksum differs from saved definition")
    return BindingVersion(
        binding_id=binding_id,
        version=version,
        checksum=row[0],
        definition=definition,
        state=row[6],
        state_revision=row[5],
        first_event_state_revision=row[2],
        operation_id=UUID(row[3]),
        created_at=datetime.fromisoformat(row[4]),
    )


def _current_version(connection: sqlite3.Connection, binding_id: UUID) -> int:
    row = connection.execute(
        "SELECT max(version) FROM binding_versions WHERE binding_id = ?", (str(binding_id),)
    ).fetchone()
    return int(row[0]) if row is not None and row[0] is not None else 0


def _right(
    connection: sqlite3.Connection,
    actor: str,
    action: str,
    epoch: int,
    resource_type: str,
    resource_id: UUID | None,
    grants: list[dict[str, object]],
    decisions: list[dict[str, object]],
) -> None:
    found, rules = _authorize(
        connection,
        actor=actor,
        action=cast(Action, action),
        epoch=epoch,
        resource_type=resource_type,
        resource_id=resource_id,
    )
    grants.extend(item for item in found if item not in grants)
    decisions.extend(item for item in rules if item not in decisions)


def _check_definition(
    connection: sqlite3.Connection,
    definition: BindingDefinition,
    actor: str,
    epoch: int,
    grants: list[dict[str, object]],
    decisions: list[dict[str, object]],
) -> None:
    revision, status, _ = _subject_current(connection, definition.source_activity_id, "activity")
    if status != "ongoing":
        raise FoundationError("activity_not_ongoing", "Binding producer Activity is unavailable")
    ActivityState.model_validate(
        _subject_state(connection, definition.source_activity_id, revision)
    )
    _right(
        connection,
        actor,
        "record.read",
        epoch,
        "activity",
        definition.source_activity_id,
        grants,
        decisions,
    )
    target = definition.target
    if isinstance(target, BindingNewWork):
        revision, status, _ = _subject_current(connection, target.activity_id, "activity")
        if status != "ongoing":
            raise FoundationError(
                "activity_not_ongoing", "Binding consumer Activity is unavailable"
            )
        ActivityState.model_validate(_subject_state(connection, target.activity_id, revision))
        _right(
            connection,
            actor,
            "work.write",
            epoch,
            "activity",
            target.activity_id,
            grants,
            decisions,
        )
        _right(
            connection,
            actor,
            "method.use",
            epoch,
            "activity",
            target.activity_id,
            grants,
            decisions,
        )
        method = _method(connection, target.method)
        if tuple(target.expected_outputs) != method.named_outputs:
            raise FoundationError("method_mismatch", "Binding consumer outputs differ from Method")
        declared_inputs = {item.slot: item.media_type for item in method.named_inputs}
        mapped_inputs = set(target.named_inputs) | {item.slot for item in target.fixed_inputs}
        if mapped_inputs != set(declared_inputs) or any(
            declared_inputs[slot] != definition.media_type for slot in target.named_inputs
        ):
            raise FoundationError("method_mismatch", "Binding input mapping differs from Method")
        for item in target.fixed_inputs:
            _authorize_artifact_ref(
                connection,
                item.artifact,
                actor=actor,
                epoch=epoch,
                grants=grants,
                decisions=decisions,
                media_type=declared_inputs[item.slot],
            )
        if len({child.role for child in target.children}) != len(target.children):
            raise FoundationError("invalid_binding", "Child roles must be unique")
        if target.activity_id == definition.source_activity_id:
            raise FoundationError("invalid_binding", "Producer and consumer Activities must differ")
        _, plan = _new_work_payload(
            target,
            ArtifactRef(artifact_id=UUID(int=0), revision=1),
            uuid5(definition.source_activity_id, "binding-template"),
        )
        _validate_plan(plan, method, target.activity_id, schema=9)
        _validate_choice_leaves(connection, plan)
    else:
        revision, status, parent = _subject_current(connection, target.work_id, "work")
        if status != "proposed":
            raise FoundationError("work_closed", "Offer target Work is not open")
        state = WorkState.model_validate(_subject_state(connection, target.work_id, revision))
        if state.method != "none":
            _right(
                connection,
                actor,
                "method.use",
                epoch,
                "activity",
                state.activity_id,
                grants,
                decisions,
            )
            plan = _plan(connection, target.work_id).plan
            if target.input_slot in {item.slot for item in plan.named_inputs}:
                raise FoundationError(
                    "method_mismatch", "Offer cannot replace a pinned Method input slot"
                )
        if parent != str(state.activity_id):
            raise FoundationError("corrupt_space", "Offer target Activity differs")
        if state.activity_id == definition.source_activity_id:
            raise FoundationError("invalid_binding", "Producer and consumer Activities must differ")
        _right(connection, actor, "work.write", epoch, "work", target.work_id, grants, decisions)
    if definition.condition is not None:
        _right(
            connection,
            actor,
            "record.read",
            epoch,
            "decision",
            definition.condition.choice.decision_id,
            grants,
            decisions,
        )
        _condition(connection, definition)


def _condition(connection: sqlite3.Connection, definition: BindingDefinition) -> None:
    if definition.condition is None:
        return
    condition = definition.condition
    ref = condition.choice
    row = connection.execute(
        "SELECT r.current_revision, v.body_json FROM records r JOIN record_revisions v "
        "ON v.record_id = r.record_id AND v.revision = r.current_revision "
        "WHERE r.record_id = ? AND r.kind = 'decision'",
        (str(ref.decision_id),),
    ).fetchone()
    if row is None or row[0] != ref.revision:
        raise FoundationError("stale_decision", "Binding condition names a noncurrent Decision")
    state = _decision_body(row[1])
    if (
        not isinstance(state, ChoiceState)
        or state.status != "active"
        or state.name != condition.name
        or state.value != condition.value
        or state.scope.kind != "activity"
        or state.scope.record_id != definition.source_activity_id
    ):
        raise FoundationError("condition_closed", "Binding source choice is not exact and active")


def _event(
    connection: sqlite3.Connection,
    definition: BindingDefinition,
    producer_work_id: UUID,
    accepted_revision: int,
) -> tuple[UUID, ArtifactRef, int]:
    revision, status, _ = _subject_current(connection, producer_work_id, "work")
    if revision != accepted_revision or status != "succeeded":
        raise FoundationError("stale_event", "Accepted producer Work revision is not current")
    state = WorkState.model_validate(_subject_state(connection, producer_work_id, revision))
    if state.activity_id != definition.source_activity_id or state.acceptance is None:
        raise FoundationError(
            "wrong_producer", "Work is not an accepted result of producer Activity"
        )
    declared = {item.slot: item.media_type for item in state.expected_outputs}
    outputs = {item.slot: item.artifact for item in state.linked_outputs}
    if (
        declared.get(definition.source_slot) != definition.media_type
        or definition.source_slot not in outputs
    ):
        raise FoundationError("wrong_output", "Accepted result lacks the exact Binding slot/type")
    source_op = state.acceptance.operation_id
    row = connection.execute(
        "SELECT state_revision FROM operations WHERE operation_id = ?", (str(source_op),)
    ).fetchone()
    if row is None:
        raise FoundationError("corrupt_space", "Accepted event has no operation")
    return source_op, outputs[definition.source_slot], int(row[0])


def _lineage(connection: sqlite3.Connection, producer_work_id: UUID) -> list[str]:
    row = connection.execute(
        "SELECT path_json FROM binding_lineages WHERE work_id = ?", (str(producer_work_id),)
    ).fetchone()
    return cast(list[str], json.loads(row[0])) if row else []


def _save_lineage(connection: sqlite3.Connection, work_id: UUID, path: list[str]) -> None:
    connection.execute(
        "INSERT INTO binding_lineages(work_id, path_json, depth) VALUES (?, ?, ?) "
        "ON CONFLICT(work_id) DO UPDATE SET path_json = excluded.path_json, depth = excluded.depth",
        (str(work_id), canonical_json(path), len(path)),
    )


def _new_work_payload(
    target: BindingNewWork,
    artifact: ArtifactRef,
    work_id: UUID,
) -> tuple[WorkState, WorkPlan]:
    inputs = tuple(dict.fromkeys([artifact, *(item.artifact for item in target.fixed_inputs)]))
    children = tuple(
        PlanChild(
            role=template.role,
            work_id=uuid5(work_id, f"child:{template.role}"),
            state=WorkState(
                activity_id=target.activity_id,
                goal=template.goal,
                inputs=(artifact,) if template.consume_source else (),
                constraints=template.constraints,
                expected_outputs=template.expected_outputs,
            ),
            readiness=template.readiness,
        )
        for template in target.children
    )
    state = WorkState(
        activity_id=target.activity_id,
        goal=target.goal,
        inputs=inputs,
        constraints=target.constraints,
        expected_outputs=target.expected_outputs,
        method=target.method,
    )
    plan = WorkPlan(
        named_inputs=(
            tuple(NamedInput(slot=slot, artifact=artifact) for slot in target.named_inputs)
            + target.fixed_inputs
        ),
        output_bindings=target.output_bindings,
        parent_outputs=target.parent_outputs,
        children=children,
        completion=target.completion,
        basis=inputs,
        rationale=target.rationale,
        source_ref=target.source_ref,
    )
    return state, plan


def _make_new_work(
    connection: sqlite3.Connection,
    request: FireBindingRequest,
    target: BindingNewWork,
    artifact: ArtifactRef,
    now: str,
    epoch: int,
    grants: list[dict[str, object]],
    decisions: list[dict[str, object]],
    source_op: UUID,
) -> tuple[UUID, list[dict[str, object]]]:
    work_id = uuid5(request.binding_id, f"{request.version}:{source_op}:work")
    state, plan = _new_work_payload(target, artifact, work_id)
    create = CreateCompositeWorkRequest(
        operation_id=request.operation_id,
        space_id=request.space_id,
        actor=request.actor,
        work_id=work_id,
        state=state,
        plan=plan,
    )
    _right(
        connection,
        request.actor,
        "work.write",
        epoch,
        "activity",
        target.activity_id,
        grants,
        decisions,
    )
    result, refs = apply_composition_change(
        connection,
        create,
        now=now,
        epoch=epoch,
        grants=grants,
        decisions=decisions,
    )
    if result.get("work_id") != str(work_id):
        raise FoundationError("corrupt_space", "Composite creation returned another Work")
    return work_id, refs


def _fire(
    connection: sqlite3.Connection,
    request: FireBindingRequest,
    *,
    now: str,
    epoch: int,
    grants: list[dict[str, object]],
    decisions: list[dict[str, object]],
) -> tuple[dict[str, object], list[dict[str, object]]]:
    version = _version(connection, request.binding_id, request.version)
    if request.version != _current_version(connection, request.binding_id) or version.state not in (
        "trial",
        "enabled",
    ):
        raise FoundationError("binding_inactive", "Only the current trial/enabled version may fire")
    definition = version.definition
    source_op, artifact, event_revision = _event(
        connection,
        definition,
        request.producer_work_id,
        request.accepted_work_revision,
    )
    if event_revision < version.first_event_state_revision and not request.backfill:
        raise FoundationError("event_before_version", "Past events need an explicit backfill run")
    delivered = connection.execute(
        "SELECT outcome, consumer_work_id, offer_id FROM binding_firings "
        "WHERE binding_id = ? AND version = ? AND source_operation_id = ? "
        "AND outcome IN ('created', 'offered', 'stopped')",
        (str(request.binding_id), request.version, str(source_op)),
    ).fetchone()
    if delivered is not None:
        return {
            "outcome": "repeated",
            "source_operation_id": str(source_op),
            "consumer_work_id": delivered[1],
            "offer_id": delivered[2],
        }, []
    _right(
        connection,
        request.actor,
        "record.read",
        epoch,
        "work",
        request.producer_work_id,
        grants,
        decisions,
    )
    _authorize_artifact_ref(
        connection,
        artifact,
        actor=request.actor,
        epoch=epoch,
        grants=grants,
        decisions=decisions,
        media_type=definition.media_type,
    )
    _check_definition(connection, definition, request.actor, epoch, grants, decisions)
    path = _lineage(connection, request.producer_work_id)
    reason = None
    outcome = "created" if isinstance(definition.target, BindingNewWork) else "offered"
    if str(request.binding_id) in path:
        reason, outcome = "binding_cycle", "stopped"
    elif len(path) + 1 > definition.max_depth:
        reason, outcome = "chain_limit", "stopped"
    consumer_work_id: UUID | None = None
    offer_id: UUID | None = None
    refs: list[dict[str, object]] = [
        {"record_id": str(request.producer_work_id), "revision": request.accepted_work_revision},
        {"record_id": str(artifact.artifact_id), "revision": artifact.revision},
    ]
    if outcome == "created":
        assert isinstance(definition.target, BindingNewWork)
        consumer_work_id, new_refs = _make_new_work(
            connection,
            request,
            definition.target,
            artifact,
            now,
            epoch,
            grants,
            decisions,
            source_op,
        )
        refs.extend(new_refs)
        _save_lineage(connection, consumer_work_id, path + [str(request.binding_id)])
    elif outcome == "offered":
        assert isinstance(definition.target, BindingOfferWork)
        revision, status, _ = _subject_current(connection, definition.target.work_id, "work")
        if status != "proposed":
            raise FoundationError("work_closed", "Consumer Work closed before offer")
        consumer_work_id = definition.target.work_id
        offer_id = uuid5(request.binding_id, f"{request.version}:{source_op}:offer")
        connection.execute(
            "INSERT INTO binding_offers(offer_id, binding_id, version, producer_work_id, "
            "accepted_work_revision, source_operation_id, artifact_id, artifact_revision, "
            "consumer_work_id, input_slot, status, consumer_work_revision) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'open', ?)",
            (
                str(offer_id),
                str(request.binding_id),
                request.version,
                str(request.producer_work_id),
                request.accepted_work_revision,
                str(source_op),
                str(artifact.artifact_id),
                artifact.revision,
                str(consumer_work_id),
                definition.target.input_slot,
                revision,
            ),
        )
        refs.append({"record_id": str(consumer_work_id), "revision": revision})
    connection.execute(
        "INSERT INTO binding_firings(operation_id, binding_id, version, producer_work_id, "
        "accepted_work_revision, source_operation_id, artifact_id, artifact_revision, "
        "outcome, reason, basis, consumer_work_id, offer_id, created_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            str(request.operation_id),
            str(request.binding_id),
            request.version,
            str(request.producer_work_id),
            request.accepted_work_revision,
            str(source_op),
            str(artifact.artifact_id),
            artifact.revision,
            outcome,
            reason,
            request.basis,
            str(consumer_work_id) if consumer_work_id else None,
            str(offer_id) if offer_id else None,
            now,
        ),
    )
    return {
        "outcome": outcome,
        "reason": reason,
        "source_operation_id": str(source_op),
        "consumer_work_id": str(consumer_work_id) if consumer_work_id else None,
        "offer_id": str(offer_id) if offer_id else None,
    }, refs


def _resolve(
    connection: sqlite3.Connection,
    request: ResolveBindingOfferRequest,
    *,
    now: str,
    epoch: int,
    authority_source: str,
    grants: list[dict[str, object]],
    decisions: list[dict[str, object]],
) -> tuple[dict[str, object], list[dict[str, object]]]:
    row = connection.execute(
        "SELECT binding_id, version, producer_work_id, source_operation_id, artifact_id, "
        "artifact_revision, consumer_work_id, input_slot, status, consumer_work_revision "
        "FROM binding_offers WHERE offer_id = ?",
        (str(request.offer_id),),
    ).fetchone()
    if row is None or row[8] != "open":
        raise FoundationError("offer_unavailable", "Binding offer is not open")
    consumer_id = UUID(row[6])
    revision, status, _ = _subject_current(connection, consumer_id, "work")
    if revision != request.expected_consumer_revision or status != "proposed":
        raise FoundationError("stale_work", "Consumer Work revision changed or closed")
    _right(connection, request.actor, "work.write", epoch, "work", consumer_id, grants, decisions)
    refs: list[dict[str, object]] = [{"record_id": str(consumer_id), "revision": revision}]
    if request.decision == "accept":
        state = WorkState.model_validate(_subject_state(connection, consumer_id, revision))
        artifact = ArtifactRef(artifact_id=UUID(row[4]), revision=row[5])
        _authorize_artifact_ref(
            connection,
            artifact,
            actor=request.actor,
            epoch=epoch,
            grants=grants,
            decisions=decisions,
        )
        path = _lineage(connection, UUID(row[2]))
        if str(row[0]) in path:
            raise FoundationError("binding_cycle", "Accepting offer would form a causal cycle")
        existing = _lineage(connection, consumer_id)
        combined = existing + [item for item in path + [str(row[0])] if item not in existing]
        definition = _version(connection, UUID(row[0]), row[1]).definition
        if len(combined) > definition.max_depth:
            raise FoundationError("chain_limit", "Offer would exceed Binding causal depth")
        current_inputs = list(state.inputs)
        prior = connection.execute(
            "SELECT artifact_id, artifact_revision FROM binding_input_revisions "
            "WHERE work_id = ? AND input_slot = ? ORDER BY revision DESC LIMIT 1",
            (str(consumer_id), row[7]),
        ).fetchone()
        if prior is not None:
            prior_artifact = ArtifactRef(artifact_id=UUID(prior[0]), revision=prior[1])
            original = WorkState.model_validate(_subject_state(connection, consumer_id, 1))
            others = connection.execute(
                "SELECT input_slot, artifact_id, artifact_revision FROM binding_input_revisions "
                "WHERE work_id = ? ORDER BY revision DESC",
                (str(consumer_id),),
            ).fetchall()
            seen = {row[7]}
            shared = False
            for other_slot, other_artifact, other_revision in others:
                if other_slot in seen:
                    continue
                seen.add(other_slot)
                if (other_artifact, other_revision) == (prior[0], prior[1]):
                    shared = True
            if (
                prior_artifact not in original.inputs
                and not shared
                and prior_artifact in current_inputs
            ):
                current_inputs.remove(prior_artifact)
        if artifact not in current_inputs:
            current_inputs.append(artifact)
        plan_revision: int | None = None
        if state.method != "none":
            from .active_plan import revise_active_plan

            current_plan = _plan(connection, consumer_id)
            if row[7] in {item.slot for item in current_plan.plan.named_inputs}:
                raise FoundationError(
                    "method_mismatch", "Offer cannot replace a pinned Method input slot"
                )
            basis = list(current_plan.plan.basis)
            if prior is not None and prior_artifact not in current_inputs:
                initial = _plan(connection, consumer_id, 1).plan
                if prior_artifact not in initial.basis and prior_artifact in basis:
                    basis.remove(prior_artifact)
            if artifact not in basis:
                basis.append(artifact)
            plan_request = ReviseActivePlanRequest(
                operation_id=request.operation_id,
                space_id=request.space_id,
                actor=request.actor,
                work_id=consumer_id,
                expected_plan_revision=current_plan.revision,
                expected_work_revision=revision,
                plan=current_plan.plan.model_copy(update={"basis": tuple(basis)}),
                nodes=tuple(
                    PlanNodeDecision(role=child.role, decision="keep", work_id=child.work_id)
                    for child in current_plan.plan.children
                ),
            )
            plan_result, plan_refs = revise_active_plan(
                connection,
                plan_request,
                now=now,
                epoch=epoch,
                authority_source=authority_source,
                grants=grants,
                decisions=decisions,
            )
            plan_revision = cast(int, plan_result["plan_revision"])
            refs.extend(plan_refs)
        else:
            _hold_work_execution(
                connection, consumer_id, request.operation_id, now, "binding_input"
            )
        _write_subject(
            connection,
            record_id=consumer_id,
            kind="work",
            parent_id=state.activity_id,
            operation_id=request.operation_id,
            actor=request.actor,
            now=now,
            status="proposed",
            state=state.model_copy(update={"inputs": tuple(current_inputs), "linked_outputs": ()}),
            revision=revision + 1,
        )
        connection.execute(
            "INSERT INTO binding_input_revisions(work_id, revision, offer_id, input_slot, "
            "artifact_id, artifact_revision, plan_revision, operation_id) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (
                str(consumer_id),
                revision + 1,
                str(request.offer_id),
                row[7],
                row[4],
                row[5],
                plan_revision,
                str(request.operation_id),
            ),
        )
        _save_lineage(connection, consumer_id, combined)
        refs.append({"record_id": str(consumer_id), "revision": revision + 1})
        refs.append({"record_id": row[4], "revision": row[5]})
    connection.execute(
        "UPDATE binding_offers SET status = ?, resolved_operation_id = ?, "
        "resolution_basis = ? WHERE offer_id = ?",
        (
            "accepted" if request.decision == "accept" else "refused",
            str(request.operation_id),
            request.basis,
            str(request.offer_id),
        ),
    )
    return {
        "offer_id": str(request.offer_id),
        "status": request.decision,
        "consumer_work_id": str(consumer_id),
        "consumer_work_revision": revision + (1 if request.decision == "accept" else 0),
        "plan_revision": plan_revision if request.decision == "accept" else None,
    }, refs


def apply_binding_change(
    connection: sqlite3.Connection,
    request: CreateBindingVersionRequest
    | SetBindingStateRequest
    | FireBindingRequest
    | ResolveBindingOfferRequest,
    *,
    now: str,
    epoch: int,
    authority_source: str,
    grants: list[dict[str, object]],
    decisions: list[dict[str, object]],
) -> tuple[dict[str, object], list[dict[str, object]]]:
    if isinstance(request, CreateBindingVersionRequest):
        previous = _current_version(connection, request.binding_id)
        if request.version != previous + 1:
            raise FoundationError("stale_binding", "Binding versions must be contiguous")
        _check_definition(connection, request.definition, request.actor, epoch, grants, decisions)
        if previous:
            prior = _version(connection, request.binding_id, previous)
            connection.execute(
                "INSERT INTO binding_states(binding_id, version, revision, state, "
                "operation_id, created_at) "
                "VALUES (?, ?, ?, 'retired', ?, ?)",
                (
                    str(request.binding_id),
                    previous,
                    prior.state_revision + 1,
                    str(request.operation_id),
                    now,
                ),
            )
        checksum = binding_checksum(request.definition)
        state_revision = int(
            connection.execute("SELECT state_revision FROM spaces WHERE singleton = 1").fetchone()[
                0
            ]
        )
        connection.execute(
            "INSERT INTO binding_versions(binding_id, version, checksum, payload, "
            "first_event_state_revision, operation_id, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                str(request.binding_id),
                request.version,
                checksum,
                request.definition.model_dump_json().encode(),
                state_revision + 1,
                str(request.operation_id),
                now,
            ),
        )
        connection.execute(
            "INSERT INTO binding_states(binding_id, version, revision, state, "
            "operation_id, created_at) "
            "VALUES (?, ?, 1, 'trial', ?, ?)",
            (str(request.binding_id), request.version, str(request.operation_id), now),
        )
        return {
            "binding_id": str(request.binding_id),
            "version": request.version,
            "checksum": checksum,
            "state": "trial",
        }, []
    if isinstance(request, SetBindingStateRequest):
        version = _version(connection, request.binding_id, request.version)
        if request.version != _current_version(connection, request.binding_id) or (
            version.state_revision != request.expected_state_revision
        ):
            raise FoundationError("stale_binding", "Binding state revision changed")
        if version.state == "retired" or (version.state == request.state):
            raise FoundationError("invalid_transition", "Binding state transition is unavailable")
        connection.execute(
            "INSERT INTO binding_states(binding_id, version, revision, state, "
            "operation_id, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (
                str(request.binding_id),
                request.version,
                version.state_revision + 1,
                request.state,
                str(request.operation_id),
                now,
            ),
        )
        return {
            "binding_id": str(request.binding_id),
            "version": request.version,
            "state": request.state,
            "state_revision": version.state_revision + 1,
        }, []
    if isinstance(request, FireBindingRequest):
        return _fire(connection, request, now=now, epoch=epoch, grants=grants, decisions=decisions)
    return _resolve(
        connection,
        request,
        now=now,
        epoch=epoch,
        authority_source=authority_source,
        grants=grants,
        decisions=decisions,
    )


def fire_on_acceptance(
    connection: sqlite3.Connection,
    *,
    operation_id: UUID,
    space_id: UUID,
    actor: str,
    work_id: UUID,
    accepted_revision: int,
    now: str,
    epoch: int,
    grants: list[dict[str, object]],
    decisions: list[dict[str, object]],
) -> tuple[list[dict[str, object]], list[dict[str, object]]]:
    """An accepted Work persists even when a transfer is blocked; each refusal is addressed."""

    rows = connection.execute(
        "SELECT v.binding_id, v.version FROM binding_versions v JOIN binding_states s "
        "ON s.binding_id = v.binding_id AND s.version = v.version AND s.revision = "
        "(SELECT max(revision) FROM binding_states WHERE binding_id = v.binding_id "
        "AND version = v.version) "
        "WHERE s.state = 'enabled' AND v.version = "
        "(SELECT max(version) FROM binding_versions WHERE binding_id = v.binding_id) "
        "ORDER BY v.binding_id"
    ).fetchall()
    results: list[dict[str, object]] = []
    targets: list[dict[str, object]] = []
    for raw_id, raw_version in rows:
        binding_id = UUID(raw_id)
        version = _version(connection, binding_id, raw_version)
        producer = WorkState.model_validate(_subject_state(connection, work_id, accepted_revision))
        if version.definition.source_activity_id != producer.activity_id or not any(
            item.slot == version.definition.source_slot
            and item.media_type == version.definition.media_type
            for item in producer.expected_outputs
        ):
            continue
        request = FireBindingRequest(
            operation_id=operation_id,
            space_id=space_id,
            actor=actor,
            binding_id=binding_id,
            version=raw_version,
            producer_work_id=work_id,
            accepted_work_revision=accepted_revision,
        )
        connection.execute("SAVEPOINT binding_fire")
        try:
            result, refs = _fire(
                connection,
                request,
                now=now,
                epoch=epoch,
                grants=grants,
                decisions=decisions,
            )
            connection.execute("RELEASE SAVEPOINT binding_fire")
            results.append({"binding_id": raw_id, "version": raw_version, **result})
            targets.extend(refs)
        except FoundationError as error:
            connection.execute("ROLLBACK TO SAVEPOINT binding_fire")
            connection.execute("RELEASE SAVEPOINT binding_fire")
            source_artifact = next(
                (
                    item.artifact
                    for item in producer.linked_outputs
                    if item.slot == version.definition.source_slot
                ),
                None,
            )
            connection.execute(
                "INSERT INTO binding_firings(operation_id, binding_id, version, producer_work_id, "
                "accepted_work_revision, source_operation_id, artifact_id, "
                "artifact_revision, outcome, reason, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'blocked', ?, ?)",
                (
                    str(operation_id),
                    raw_id,
                    raw_version,
                    str(work_id),
                    accepted_revision,
                    str(operation_id),
                    str(source_artifact.artifact_id) if source_artifact else None,
                    source_artifact.revision if source_artifact else None,
                    error.code,
                    now,
                ),
            )
            results.append(
                {
                    "binding_id": raw_id,
                    "version": raw_version,
                    "outcome": "blocked",
                    "reason": error.code,
                }
            )
    return results, targets


def read_binding_version(
    path: Path, binding_id: UUID, version: int, authority: LocalAuthority
) -> BindingVersion:
    with space_connection(path) as (connection, info):
        _local_space(authority, info)
        if info.schema_version < 9 or info.recovery_state != "active":
            raise FoundationError("unsupported_schema", "Binding reads need active schema 9")
        _authorize(
            connection, actor=authority.actor, action="record.read", epoch=info.execution_epoch
        )
        return _version(connection, binding_id, version)


def list_bindings(path: Path, authority: LocalAuthority) -> tuple[BindingVersion, ...]:
    with space_connection(path) as (connection, info):
        _local_space(authority, info)
        if info.schema_version < 9 or info.recovery_state != "active":
            raise FoundationError("unsupported_schema", "Binding reads need active schema 9")
        _authorize(
            connection, actor=authority.actor, action="record.read", epoch=info.execution_epoch
        )
        rows = connection.execute(
            "SELECT binding_id, version FROM binding_versions WHERE payload IS NOT NULL "
            "ORDER BY binding_id, version"
        ).fetchall()
        return tuple(_version(connection, UUID(row[0]), row[1]) for row in rows)


def list_binding_offers(path: Path, authority: LocalAuthority) -> tuple[BindingOffer, ...]:
    with space_connection(path) as (connection, info):
        _local_space(authority, info)
        if info.schema_version < 9 or info.recovery_state != "active":
            raise FoundationError("unsupported_schema", "Binding reads need active schema 9")
        _authorize(
            connection, actor=authority.actor, action="record.read", epoch=info.execution_epoch
        )
        ids = connection.execute("SELECT offer_id FROM binding_offers ORDER BY offer_id").fetchall()
    return tuple(read_binding_offer(path, UUID(row[0]), authority) for row in ids)


def list_binding_methods(path: Path, authority: LocalAuthority) -> tuple[MethodVersion, ...]:
    """Readable exact Methods available for an ordinary Pi Binding proposal."""

    with space_connection(path) as (connection, info):
        _local_space(authority, info)
        if info.schema_version < 5 or info.recovery_state != "active":
            return ()
        _authorize(
            connection, actor=authority.actor, action="record.read", epoch=info.execution_epoch
        )
        rows = connection.execute(
            "SELECT method_id, version, checksum, operation_id, created_at, actor "
            "FROM method_versions WHERE status = 'active' ORDER BY method_id, version"
        ).fetchall()
        return tuple(
            MethodVersion(
                reference=MethodRef(method_id=UUID(row[0]), version=row[1], checksum=row[2]),
                definition=_method(
                    connection, MethodRef(method_id=UUID(row[0]), version=row[1], checksum=row[2])
                ),
                operation_id=UUID(row[3]),
                created_at=datetime.fromisoformat(row[4]),
                actor=row[5],
            )
            for row in rows
        )


def require_method_released(connection: sqlite3.Connection, method: MethodRef) -> None:
    if int(connection.execute("PRAGMA user_version").fetchone()[0]) < 9:
        return
    rows = connection.execute(
        "SELECT v.payload FROM binding_versions v JOIN binding_states s ON "
        "s.binding_id = v.binding_id AND s.version = v.version AND s.revision = "
        "(SELECT max(revision) FROM binding_states WHERE binding_id = v.binding_id "
        "AND version = v.version) WHERE v.payload IS NOT NULL AND s.state != 'retired'"
    ).fetchall()
    for (payload,) in rows:
        target = BindingDefinition.model_validate_json(bytes(payload)).target
        if isinstance(target, BindingNewWork) and target.method == method:
            raise FoundationError("method_in_use", "Active Binding pins this Method version")


def sanitize_deleted_binding_subject(
    connection: sqlite3.Connection,
    *,
    subject_id: UUID,
    kind: str,
    operation_id: UUID,
    now: str,
) -> None:
    if int(connection.execute("PRAGMA user_version").fetchone()[0]) < 9:
        return
    if kind == "artifact":
        connection.execute(
            "UPDATE binding_offers SET status = 'unavailable' "
            "WHERE artifact_id = ? AND status = 'open'",
            (str(subject_id),),
        )
        connection.execute(
            "UPDATE binding_offers SET resolution_basis = NULL WHERE artifact_id = ?",
            (str(subject_id),),
        )
        connection.execute(
            "UPDATE binding_firings SET basis = NULL WHERE artifact_id = ?",
            (str(subject_id),),
        )
    elif kind == "work":
        connection.execute(
            "UPDATE binding_offers SET status = 'unavailable' WHERE status = 'open' "
            "AND (producer_work_id = ? OR consumer_work_id = ?)",
            (str(subject_id), str(subject_id)),
        )
        connection.execute(
            "UPDATE binding_offers SET resolution_basis = NULL "
            "WHERE producer_work_id = ? OR consumer_work_id = ?",
            (str(subject_id), str(subject_id)),
        )
        connection.execute(
            "UPDATE binding_firings SET basis = NULL "
            "WHERE producer_work_id = ? OR consumer_work_id = ?",
            (str(subject_id), str(subject_id)),
        )
    if kind == "work":
        connection.execute(
            "DELETE FROM binding_input_revisions WHERE work_id = ?", (str(subject_id),)
        )
        connection.execute("DELETE FROM binding_lineages WHERE work_id = ?", (str(subject_id),))
    rows = connection.execute(
        "SELECT binding_id, version, payload, operation_id FROM binding_versions "
        "WHERE payload IS NOT NULL"
    ).fetchall()
    for binding_id, version, payload, original_op in rows:
        definition = BindingDefinition.model_validate_json(bytes(payload))
        affected = (
            (
                kind == "activity"
                and (
                    definition.source_activity_id == subject_id
                    or isinstance(definition.target, BindingNewWork)
                    and definition.target.activity_id == subject_id
                )
            )
            or (
                kind == "work"
                and isinstance(definition.target, BindingOfferWork)
                and definition.target.work_id == subject_id
            )
            or (
                kind == "artifact"
                and isinstance(definition.target, BindingNewWork)
                and any(
                    item.artifact.artifact_id == subject_id
                    for item in definition.target.fixed_inputs
                )
            )
        )
        if not affected:
            continue
        latest = connection.execute(
            "SELECT max(revision) FROM binding_states WHERE binding_id = ? AND version = ?",
            (binding_id, version),
        ).fetchone()[0]
        connection.execute(
            "INSERT INTO binding_states(binding_id, version, revision, state, "
            "operation_id, created_at) "
            "VALUES (?, ?, ?, 'retired', ?, ?)",
            (binding_id, version, latest + 1, str(operation_id), now),
        )
        connection.execute(
            "UPDATE binding_versions SET payload = NULL WHERE binding_id = ? AND version = ?",
            (binding_id, version),
        )
        connection.execute(
            "UPDATE binding_firings SET basis = NULL WHERE binding_id = ? AND version = ?",
            (binding_id, version),
        )
        connection.execute(
            "UPDATE binding_offers SET resolution_basis = NULL, "
            "status = CASE WHEN status = 'open' THEN 'unavailable' ELSE status END "
            "WHERE binding_id = ? AND version = ?",
            (binding_id, version),
        )
        connection.execute("DELETE FROM receipts WHERE operation_id = ?", (original_op,))
        connection.execute(
            "UPDATE operations SET fingerprint = 'DELETED' WHERE operation_id = ?",
            (original_op,),
        )


def read_binding_firings(
    path: Path, binding_id: UUID, authority: LocalAuthority
) -> tuple[BindingFiring, ...]:
    with space_connection(path) as (connection, info):
        _local_space(authority, info)
        if info.schema_version < 9 or info.recovery_state != "active":
            raise FoundationError("unsupported_schema", "Binding reads need active schema 9")
        _authorize(
            connection, actor=authority.actor, action="record.read", epoch=info.execution_epoch
        )
        rows = connection.execute(
            "SELECT operation_id, version, producer_work_id, accepted_work_revision, "
            "source_operation_id, artifact_id, artifact_revision, "
            "outcome, reason, basis, consumer_work_id, offer_id, created_at "
            "FROM binding_firings "
            "WHERE binding_id = ? ORDER BY created_at, operation_id",
            (str(binding_id),),
        ).fetchall()
        return tuple(
            BindingFiring(
                binding_id=binding_id,
                version=row[1],
                producer_work_id=UUID(row[2]),
                accepted_work_revision=row[3],
                source_operation_id=UUID(row[4]),
                artifact=ArtifactRef(artifact_id=UUID(row[5]), revision=row[6]) if row[5] else None,
                outcome=row[7],
                reason=row[8],
                basis=row[9],
                consumer_work_id=UUID(row[10]) if row[10] else None,
                offer_id=UUID(row[11]) if row[11] else None,
                operation_id=UUID(row[0]),
                created_at=datetime.fromisoformat(row[12]),
            )
            for row in rows
        )


def read_binding_offer(path: Path, offer_id: UUID, authority: LocalAuthority) -> BindingOffer:
    with space_connection(path) as (connection, info):
        _local_space(authority, info)
        if info.schema_version < 9 or info.recovery_state != "active":
            raise FoundationError("unsupported_schema", "Binding reads need active schema 9")
        _authorize(
            connection, actor=authority.actor, action="record.read", epoch=info.execution_epoch
        )
        row = connection.execute(
            "SELECT binding_id, version, producer_work_id, accepted_work_revision, "
            "source_operation_id, "
            "artifact_id, artifact_revision, consumer_work_id, input_slot, status, "
            "consumer_work_revision, resolved_operation_id, resolution_basis "
            "FROM binding_offers WHERE offer_id = ?",
            (str(offer_id),),
        ).fetchone()
        if row is None:
            raise FoundationError("not_found", "Binding offer is absent")
        return BindingOffer(
            offer_id=offer_id,
            binding_id=UUID(row[0]),
            version=row[1],
            producer_work_id=UUID(row[2]),
            accepted_work_revision=row[3],
            source_operation_id=UUID(row[4]),
            artifact=ArtifactRef(artifact_id=UUID(row[5]), revision=row[6]),
            consumer_work_id=UUID(row[7]),
            input_slot=row[8],
            status=row[9],
            consumer_work_revision=row[10],
            resolved_operation_id=UUID(row[11]) if row[11] else None,
            resolution_basis=row[12],
        )


def read_binding_input_history(
    path: Path,
    work_id: UUID,
    authority: LocalAuthority,
) -> tuple[BindingInputRevision, ...]:
    with space_connection(path) as (connection, info):
        _local_space(authority, info)
        if info.schema_version < 9 or info.recovery_state != "active":
            raise FoundationError("unsupported_schema", "Binding reads need active schema 9")
        _authorize(
            connection,
            actor=authority.actor,
            action="record.read",
            epoch=info.execution_epoch,
            resource_type="work",
            resource_id=work_id,
        )
        rows = connection.execute(
            "SELECT revision, offer_id, input_slot, artifact_id, artifact_revision, "
            "plan_revision, operation_id "
            "FROM binding_input_revisions WHERE work_id = ? ORDER BY revision",
            (str(work_id),),
        ).fetchall()
        return tuple(
            BindingInputRevision(
                work_id=work_id,
                revision=row[0],
                offer_id=UUID(row[1]),
                input_slot=row[2],
                artifact=ArtifactRef(artifact_id=UUID(row[3]), revision=row[4]),
                plan_revision=row[5],
                operation_id=UUID(row[6]),
            )
            for row in rows
        )

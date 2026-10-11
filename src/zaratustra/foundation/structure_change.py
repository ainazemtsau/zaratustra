"""Exact reviewed structure activation through Candidate admission and receipts."""

from __future__ import annotations

import hashlib
import sqlite3
from typing import Any
from uuid import UUID, uuid5

from .models import (
    ActivityActivationManifest,
    ActivitySetupRequest,
    ActivitySetupReviewV2,
    ActivitySetupState,
    ApplyCandidateRequest,
    ChangeApplication,
    ChangeCandidateState,
    ChangeDecisionState,
    CreateDecisionRequest,
    CreateDevelopmentRequest,
    CreateKnowledgeRequest,
    KnowledgeRef,
    RecordChangeOutcomeRequest,
    RestoreCandidateRequest,
    ReviseKnowledgeRequest,
    StopCandidateRequest,
    StructureChange,
    ValidationCriterion,
    ValidationPlanState,
    ValidationResultState,
)
from .storage import FoundationError, canonical_json


def activate_setup_structure(
    connection: sqlite3.Connection,
    request: ActivitySetupRequest,
    state: ActivitySetupState,
    manifest: ActivityActivationManifest,
    review: Any,
    effect: Any,
    epoch: int,
) -> None:
    from .activity_setup import AREAS

    if (
        not isinstance(review, ActivitySetupReviewV2)
        or state.manifest is None
        or state.review is None
    ):
        raise FoundationError("setup_not_reviewed", "Structure needs an exact complete review")
    evidence = KnowledgeRef(record_id=state.review.artifact_id, revision=state.review.revision)
    candidate_id = uuid5(request.setup_id, "structure-candidate:" + str(state.manifest.artifact_id))
    results = tuple(
        ValidationResultState(
            result_id=uuid5(candidate_id, area),
            criterion=area,
            outcome="met",
            evidence=(evidence,),
            actual_input=str(state.manifest),
            environment="Full assigned Pi review of the compiled structure",
        )
        for area in AREAS
    )
    candidate = ChangeCandidateState(
        target=StructureChange(
            change_id=uuid5(candidate_id, "change"),
            activity_id=state.activity_id,
            expected_structure=state.previous_structure,
            manifest=state.manifest,
        ),
        proposal="Apply the exact fully reviewed Activity structure",
        evidence=state.sources + (evidence,),
        expected_outcome=manifest.structure.first_action,
        scope_activity_ids=(state.activity_id,),
        exclusions="No grants, code, publication or Work acceptance",
        impact="Formats, current structure and new Work in this Activity; old Work pins remain",
        unknowns="Review does not prove all future use",
        validation_plan=ValidationPlanState(
            baseline=str(state.manifest),
            environment="Core and ordinary Pi",
            criteria=tuple(
                ValidationCriterion(
                    key=area,
                    question=area,
                    pass_condition="No blocking obstacle",
                    basis=(evidence,),
                )
                for area in AREAS
            ),
            cases="Complete user requirements and compiled package",
            method="Full structure review",
            sufficiency="All seven areas with reasons and component references",
            limits="No mandatory trial",
            stop_and_restore="Stop new starts and restore prior structure without changing history",
            decision_condition="Exact current successful review",
            follow_up="Use and Sleep",
        ),
        results=results,
        restore_plan="Restore the preceding head; keep old and new revisions",
        irreversible_effects="None",
    )
    effect(CreateDevelopmentRequest, record_id=candidate_id, state=candidate)
    decision_id = uuid5(candidate_id, "adoption")
    effect(
        CreateDecisionRequest,
        decision_id=decision_id,
        state=ChangeDecisionState(
            statement="Apply under the saved local setup authorization and exact full review",
            candidate_id=candidate_id,
            candidate_revision=1,
            mode="regular",
            use="permitted",
            scope_activity_id=state.activity_id,
            validation_result_ids=tuple(item.result_id for item in results),
            review_condition="Review changed requirements or definitions",
        ),
    )
    effect(
        ApplyCandidateRequest,
        candidate_id=candidate_id,
        candidate_revision=1,
        decision_id=decision_id,
        decision_revision=1,
        mode="regular",
    )


def apply_structure_candidate(
    connection: sqlite3.Connection,
    request: ApplyCandidateRequest,
    candidate: ChangeCandidateState,
    *,
    now: str,
    epoch: int,
    authority: Any,
    grants: list[dict[str, object]],
    decisions: list[dict[str, object]],
) -> tuple[dict[str, Any], list[dict[str, object]]]:
    from .activity_setup import _artifact, _basis, _current
    from .data_store import APPLYING_STRUCTURE, head_ref
    from .development import _decision, _package_event
    from .models import ActivitySetupDraftV2
    from .operations import _apply_change, _authorize, _operation_action
    from .structure_setup import compile_structure, draft_from_bytes, validate_review_components

    target = candidate.target
    if (
        not isinstance(target, StructureChange)
        or int(connection.execute("PRAGMA user_version").fetchone()[0]) < 15
    ):
        raise FoundationError("upgrade_required", "Structure changes require schema 15")
    decision = _decision(connection, request, candidate)
    if (
        candidate.scope_global
        or candidate.scope_activity_ids != (target.activity_id,)
        or decision.scope_activity_id != target.activity_id
    ):
        raise FoundationError("out_of_scope", "Structure adoption admits one exact Activity")
    manifest = ActivityActivationManifest.model_validate_json(
        _artifact(connection, target.manifest, request.actor, epoch)
    )
    state = _current(connection, manifest.setup_id).state
    if state.phase != "activating" or state.manifest != target.manifest or state.review is None:
        raise FoundationError("stale_setup", "Only the current reviewed setup can be applied")
    report = ActivitySetupReviewV2.model_validate_json(
        _artifact(connection, state.review, request.actor, epoch)
    )
    if (
        report.manifest != target.manifest
        or report.draft != state.draft
        or report.input_version != state.input_version
        or report.unresolved
        or any(item.blocking for item in report.findings)
    ):
        raise FoundationError("stale_basis", "Structure has no successful exact review")
    validate_review_components(report, manifest)
    if (
        manifest.activity_id != target.activity_id
        or head_ref(connection, target.activity_id) != target.expected_structure
    ):
        raise FoundationError("stale_structure", "The expected current structure changed")
    for ref in state.sources:
        _basis(connection, ref, request.actor, epoch)
    draft = draft_from_bytes(_artifact(connection, manifest.draft, request.actor, epoch), 2)
    if (
        not isinstance(draft, ActivitySetupDraftV2)
        or compile_structure(
            connection, manifest.setup_id, state, draft, manifest.draft, request.actor, epoch
        )
        != manifest
    ):
        raise FoundationError("stale_basis", "Compiled structure definitions changed")
    targets: list[dict[str, object]] = []

    def write(identifier: UUID, body: Any, previous: int | None) -> None:
        fields: dict[str, Any] = {"expected_revision": previous} if previous else {}
        nested = (CreateKnowledgeRequest if previous is None else ReviseKnowledgeRequest)(
            operation_id=request.operation_id,
            space_id=request.space_id,
            actor=request.actor,
            record_id=identifier,
            state=body,
            **fields,
        )
        action, resource_type, resource_id = _operation_action(nested)
        g, d = _authorize(
            connection,
            actor=request.actor,
            action=action,
            epoch=epoch,
            resource_type=resource_type,
            resource_id=resource_id,
        )
        grants.extend(g)
        decisions.extend(d)
        _, refs = _apply_change(
            connection,
            nested,
            now=now,
            epoch=epoch,
            authority=authority,
            grants=grants,
            decisions=decisions,
        )
        targets.extend(refs)

    token = APPLYING_STRUCTURE.set(True)
    try:
        for component in manifest.formats:
            if component.create:
                write(component.ref.record_id, component.definition, component.expected_revision)
        write(
            manifest.structure_ref.record_id,
            manifest.structure,
            manifest.structure_expected_revision,
        )
    finally:
        APPLYING_STRUCTURE.reset(token)
    checksum = (
        hashlib.sha256(canonical_json(manifest.model_dump(mode="json")).encode())
        .hexdigest()
        .upper()
    )
    structure_sha = connection.execute(
        "SELECT sha256 FROM knowledge_revisions WHERE record_id=? AND revision=?",
        (str(manifest.structure_ref.record_id), manifest.structure_ref.revision),
    ).fetchone()[0]
    connection.execute(
        "INSERT INTO structure_heads (activity_id,record_id,revision,sha256,setup_id,status) "
        "VALUES (?,?,?,?,?,'active') ON CONFLICT(activity_id) DO UPDATE SET "
        "record_id=excluded.record_id,revision=excluded.revision,sha256=excluded.sha256,"
        "setup_id=excluded.setup_id,status='active'",
        (
            str(target.activity_id),
            str(manifest.structure_ref.record_id),
            manifest.structure_ref.revision,
            structure_sha,
            str(manifest.setup_id),
        ),
    )
    connection.execute(
        "INSERT INTO change_packages VALUES (?,?,?,?,?,?,?,?,?,?, 'active',1,?,?)",
        (
            str(request.operation_id),
            str(request.candidate_id),
            request.candidate_revision,
            str(request.decision_id),
            request.decision_revision,
            request.mode,
            "structure",
            str(target.change_id),
            1,
            checksum,
            now,
            now,
        ),
    )
    connection.execute(
        "INSERT INTO change_package_parts VALUES (?,0,'structure',?,?,?,?)",
        (str(request.operation_id), str(target.change_id), 1, checksum, target.model_dump_json()),
    )
    _package_event(
        connection,
        request.operation_id,
        1,
        request.operation_id,
        "apply",
        {"manifest": target.manifest.model_dump(mode="json")},
        now,
    )
    return {
        "application_id": str(request.operation_id),
        "status": "active",
        "structure": manifest.structure_ref.model_dump(mode="json"),
    }, targets


def followup_structure(
    connection: sqlite3.Connection,
    request: StopCandidateRequest | RestoreCandidateRequest | RecordChangeOutcomeRequest,
    app: ChangeApplication,
    *,
    now: str,
    epoch: int,
) -> tuple[dict[str, object], list[dict[str, object]]]:
    from .activity_setup import _artifact
    from .data_store import exact_state, head_ref
    from .development import _package_event

    row = connection.execute(
        "SELECT detail_json FROM change_package_parts WHERE application_id=? AND ordinal=0",
        (str(app.application_id),),
    ).fetchone()
    target = StructureChange.model_validate_json(row[0])
    manifest = ActivityActivationManifest.model_validate_json(
        _artifact(connection, target.manifest, request.actor, epoch, current=False)
    )
    if head_ref(connection, target.activity_id) != manifest.structure_ref:
        raise FoundationError("stale_structure", "A later structure cannot be silently replaced")
    detail: dict[str, object]
    if isinstance(request, StopCandidateRequest):
        if app.status != "active":
            raise FoundationError("invalid_transition", "Only active structure can stop")
        connection.execute(
            "UPDATE structure_heads SET status='stopped' WHERE activity_id=?",
            (str(target.activity_id),),
        )
        status, kind = "stopped", "stop"
        detail = {
            "reason": request.reason,
            "started_works": request.started_works,
            "external_effects": request.external_effects,
        }
    elif isinstance(request, RestoreCandidateRequest):
        if app.status != "stopped":
            raise FoundationError("invalid_transition", "Stop structure before restoring")
        if target.expected_structure is None:
            connection.execute(
                "DELETE FROM structure_heads WHERE activity_id=?", (str(target.activity_id),)
            )
        else:
            exact_state(connection, target.expected_structure, request.actor, epoch)
            sha = connection.execute(
                "SELECT sha256 FROM knowledge_revisions WHERE record_id=? AND revision=?",
                (str(target.expected_structure.record_id), target.expected_structure.revision),
            ).fetchone()[0]
            connection.execute(
                "UPDATE structure_heads SET record_id=?,revision=?,sha256=?,setup_id=?,"
                "status='active' WHERE activity_id=?",
                (
                    str(target.expected_structure.record_id),
                    target.expected_structure.revision,
                    sha,
                    str(manifest.previous_setup_id),
                    str(target.activity_id),
                ),
            )
        status, kind, detail = "restored", "restore", {"reason": request.reason}
    else:
        status, kind, detail = app.status, "outcome", request.model_dump(mode="json")
    connection.execute(
        "UPDATE change_packages SET status=?,revision=revision+1,changed_at=? "
        "WHERE application_id=?",
        (status, now, str(app.application_id)),
    )
    _package_event(
        connection, app.application_id, app.revision + 1, request.operation_id, kind, detail, now
    )
    return {"application_id": str(app.application_id), "status": status}, []


__all__ = ["activate_setup_structure"]

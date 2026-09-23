"""Frozen contracts for the independent Core v0.1 domain foundation."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Annotated, Literal
from uuid import UUID

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, JsonValue, model_validator

type Action = Literal[
    "artifact.write",
    "activity.write",
    "work.write",
    "work.accept",
    "decision.write",
    "grant.write",
    "record.read",
    "receipt.read",
    "space.inspect",
    "maintenance.backup",
    "maintenance.delete",
]
type RecordKind = Literal["artifact", "decision", "grant", "activity", "work"]

ALL_ACTIONS: tuple[Action, ...] = (
    "artifact.write",
    "activity.write",
    "work.write",
    "work.accept",
    "decision.write",
    "grant.write",
    "record.read",
    "receipt.read",
    "space.inspect",
    "maintenance.backup",
    "maintenance.delete",
)


class ContractModel(BaseModel):
    model_config = ConfigDict(
        frozen=True,
        extra="forbid",
        ser_json_bytes="base64",
        val_json_bytes="base64",
    )


class ProvenanceRef(ContractModel):
    relation: str = Field(min_length=1, max_length=80)
    record_id: UUID | None = None
    revision: int | None = Field(default=None, ge=1)
    external_ref: str | None = Field(default=None, min_length=1, max_length=2048)

    @model_validator(mode="after")
    def one_source(self) -> ProvenanceRef:
        internal = self.record_id is not None or self.revision is not None
        external = self.external_ref is not None
        if internal == external or (internal and (self.record_id is None or self.revision is None)):
            raise ValueError("Choose one exact internal revision or one external reference")
        return self


class DecisionState(ContractModel):
    statement: str = Field(min_length=1, max_length=4096)
    effect: Literal["require_grant", "deny"]
    actions: tuple[Action, ...] = Field(min_length=1)
    subjects: tuple[str, ...] = Field(default=("*",), min_length=1)
    status: Literal["active", "revoked"] = "active"


class GrantState(ContractModel):
    grantee: str = Field(min_length=1, max_length=200)
    actions: tuple[Action, ...] = Field(min_length=1)
    resource_type: Literal["space", "artifact", "activity", "work"] = "space"
    resource_id: UUID | None = None
    status: Literal["active", "revoked"] = "active"

    @model_validator(mode="after")
    def scope_is_exact(self) -> GrantState:
        if (self.resource_type == "space") == (self.resource_id is not None):
            raise ValueError("Scoped grants require one resource_id; space grants do not")
        return self


class ArtifactRef(ContractModel):
    artifact_id: UUID
    revision: int = Field(ge=1)


class ActivityState(ContractModel):
    title: str = Field(min_length=1, max_length=200)
    goal: str = Field(min_length=1, max_length=4096)
    status: Literal["ongoing", "paused", "completed"] = "ongoing"


class OutputContract(ContractModel):
    slot: str = Field(min_length=1, max_length=80, pattern=r"^[a-z][a-z0-9_-]*$")
    media_type: str = Field(min_length=1, max_length=200)


class LinkedOutput(ContractModel):
    slot: str = Field(min_length=1, max_length=80, pattern=r"^[a-z][a-z0-9_-]*$")
    artifact: ArtifactRef


class WorkAcceptance(ContractModel):
    operation_id: UUID
    basis: str = Field(min_length=1, max_length=4096)
    authority_source: str = Field(min_length=1, max_length=2048)
    accepted_at: AwareDatetime


class WorkState(ContractModel):
    activity_id: UUID
    goal: str = Field(min_length=1, max_length=4096)
    inputs: tuple[ArtifactRef, ...] = ()
    constraints: tuple[str, ...] = ()
    expected_outputs: tuple[OutputContract, ...] = Field(min_length=1)
    method: Literal["none"] = "none"
    status: Literal["proposed", "succeeded"] = "proposed"
    linked_outputs: tuple[LinkedOutput, ...] = ()
    acceptance: WorkAcceptance | None = None

    @model_validator(mode="after")
    def valid_slots(self) -> WorkState:
        expected = [item.slot for item in self.expected_outputs]
        linked = [item.slot for item in self.linked_outputs]
        if len(expected) != len(set(expected)) or len(linked) != len(set(linked)):
            raise ValueError("Output slots must be unique")
        if not set(linked).issubset(expected):
            raise ValueError("Linked output has no declared slot")
        if (self.status == "succeeded") != (self.acceptance is not None):
            raise ValueError("Succeeded Work requires acceptance and only succeeded Work has it")
        return self


class OperationRequest(ContractModel):
    protocol_version: Literal[1] = 1
    operation_id: UUID
    space_id: UUID
    actor: str = Field(min_length=1, max_length=200)


class BootstrapRequest(OperationRequest):
    kind: Literal["bootstrap"] = "bootstrap"
    decision_id: UUID
    grant_id: UUID


class RecoverRequest(OperationRequest):
    kind: Literal["recover"] = "recover"
    decision_id: UUID
    grant_id: UUID


class CreateArtifactRequest(OperationRequest):
    kind: Literal["create_artifact"] = "create_artifact"
    artifact_id: UUID
    media_type: str = Field(min_length=1, max_length=200)
    content: bytes = Field(max_length=8 * 1024 * 1024)
    provenance: tuple[ProvenanceRef, ...] = ()


class ReviseArtifactRequest(OperationRequest):
    kind: Literal["revise_artifact"] = "revise_artifact"
    artifact_id: UUID
    expected_revision: int = Field(ge=1)
    media_type: str = Field(min_length=1, max_length=200)
    content: bytes = Field(max_length=8 * 1024 * 1024)
    provenance: tuple[ProvenanceRef, ...] = ()


class DeleteArtifactRequest(OperationRequest):
    kind: Literal["delete_artifact"] = "delete_artifact"
    artifact_id: UUID
    expected_revision: int = Field(ge=1)


class CreateDecisionRequest(OperationRequest):
    kind: Literal["create_decision"] = "create_decision"
    decision_id: UUID
    state: DecisionState


class ReviseDecisionRequest(OperationRequest):
    kind: Literal["revise_decision"] = "revise_decision"
    decision_id: UUID
    expected_revision: int = Field(ge=1)
    state: DecisionState


class CreateGrantRequest(OperationRequest):
    kind: Literal["create_grant"] = "create_grant"
    grant_id: UUID
    state: GrantState


class RevokeGrantRequest(OperationRequest):
    kind: Literal["revoke_grant"] = "revoke_grant"
    grant_id: UUID
    expected_revision: int = Field(ge=1)


class CreateActivityRequest(OperationRequest):
    kind: Literal["create_activity"] = "create_activity"
    activity_id: UUID
    state: ActivityState


class ReviseActivityRequest(OperationRequest):
    kind: Literal["revise_activity"] = "revise_activity"
    activity_id: UUID
    expected_revision: int = Field(ge=1)
    state: ActivityState


class DeleteActivityRequest(OperationRequest):
    kind: Literal["delete_activity"] = "delete_activity"
    activity_id: UUID
    expected_revision: int = Field(ge=1)


class CreateWorkRequest(OperationRequest):
    kind: Literal["create_work"] = "create_work"
    work_id: UUID
    state: WorkState

    @model_validator(mode="after")
    def new_work_is_unaccepted(self) -> CreateWorkRequest:
        if self.state.status != "proposed" or self.state.linked_outputs:
            raise ValueError("New Work starts proposed with no linked output")
        return self


class LinkWorkOutputRequest(OperationRequest):
    kind: Literal["link_work_output"] = "link_work_output"
    work_id: UUID
    expected_revision: int = Field(ge=1)
    output: LinkedOutput


class AcceptWorkRequest(OperationRequest):
    kind: Literal["accept_work"] = "accept_work"
    work_id: UUID
    expected_revision: int = Field(ge=1)
    basis: str = Field(min_length=1, max_length=4096)


class DeleteWorkRequest(OperationRequest):
    kind: Literal["delete_work"] = "delete_work"
    work_id: UUID
    expected_revision: int = Field(ge=1)


DomainRequest = Annotated[
    BootstrapRequest
    | RecoverRequest
    | CreateArtifactRequest
    | ReviseArtifactRequest
    | DeleteArtifactRequest
    | CreateDecisionRequest
    | ReviseDecisionRequest
    | CreateGrantRequest
    | RevokeGrantRequest
    | CreateActivityRequest
    | ReviseActivityRequest
    | DeleteActivityRequest
    | CreateWorkRequest
    | LinkWorkOutputRequest
    | AcceptWorkRequest
    | DeleteWorkRequest,
    Field(discriminator="kind"),
]


class SpaceInfo(ContractModel):
    root: Path
    database: Path
    space_id: UUID
    created_at: AwareDatetime
    schema_version: Literal[1, 2]
    state_revision: int = Field(ge=0)
    execution_epoch: int = Field(ge=1)
    recovery_state: Literal["active", "quarantined"]
    sqlite_version: Literal["3.53.3"]


class OperationReceipt(ContractModel):
    operation_id: UUID
    fingerprint: str = Field(pattern=r"^[0-9A-F]{64}$")
    kind: str
    state_revision: int = Field(ge=1)
    committed_at: AwareDatetime
    result: dict[str, JsonValue]


class AuditReference(ContractModel):
    record_id: UUID
    revision: int = Field(ge=1)


class OperationAuditEntry(ContractModel):
    operation_id: UUID
    authority_source: str
    target_refs: tuple[AuditReference, ...]
    grant_refs: tuple[AuditReference, ...]
    decision_refs: tuple[AuditReference, ...]


class ArtifactRevision(ContractModel):
    artifact_id: UUID
    revision: int = Field(ge=1)
    operation_id: UUID
    created_at: AwareDatetime
    actor: str
    media_type: str | None
    content: bytes | None
    content_sha256: str | None
    status: Literal["active", "deleted"]
    provenance: tuple[ProvenanceRef, ...]


class ActivityRevision(ContractModel):
    activity_id: UUID
    revision: int = Field(ge=1)
    operation_id: UUID
    created_at: AwareDatetime
    actor: str
    state: ActivityState


class WorkRevision(ContractModel):
    work_id: UUID
    revision: int = Field(ge=1)
    operation_id: UUID
    created_at: AwareDatetime
    actor: str
    state: WorkState
    unavailable_refs: tuple[ArtifactRef, ...] = ()


class RecordSummary(ContractModel):
    record_id: UUID
    kind: RecordKind
    current_revision: int = Field(ge=1)
    status: str
    created_at: AwareDatetime
    updated_at: AwareDatetime


class SpaceInspection(ContractModel):
    space: SpaceInfo
    records: tuple[RecordSummary, ...]
    operation_count: int = Field(ge=0)
    audit_count: int = Field(ge=0)
    receipt_count: int = Field(ge=0)
    pending_deletions: int = Field(ge=0)
    completed_backups: int = Field(ge=0)
    contaminated_backups: int = Field(ge=0)


class BackupManifest(ContractModel):
    backup_id: UUID
    space_id: UUID
    schema_version: Literal[1, 2]
    state_revision: int = Field(ge=0)
    execution_epoch: int = Field(ge=1)
    created_at: AwareDatetime
    database_file: Literal["core.sqlite3"] = "core.sqlite3"
    database_sha256: str = Field(pattern=r"^[0-9A-F]{64}$")


class BackupInfo(ContractModel):
    manifest: BackupManifest
    package: Path


class DeletionStatus(ContractModel):
    pending_jobs: int = Field(ge=0)
    completed_jobs: int = Field(ge=0)
    purged_backups: int = Field(ge=0)
    live_store_sanitized: bool
    completed_at: datetime | None = None


__all__ = [
    "ALL_ACTIONS",
    "AcceptWorkRequest",
    "Action",
    "ActivityRevision",
    "ActivityState",
    "AuditReference",
    "ArtifactRevision",
    "ArtifactRef",
    "BackupInfo",
    "BackupManifest",
    "BootstrapRequest",
    "CreateActivityRequest",
    "CreateArtifactRequest",
    "CreateDecisionRequest",
    "CreateGrantRequest",
    "CreateWorkRequest",
    "DecisionState",
    "DeleteActivityRequest",
    "DeleteArtifactRequest",
    "DeleteWorkRequest",
    "DeletionStatus",
    "DomainRequest",
    "GrantState",
    "OperationReceipt",
    "OperationAuditEntry",
    "OutputContract",
    "LinkedOutput",
    "ProvenanceRef",
    "RecordSummary",
    "RecoverRequest",
    "ReviseActivityRequest",
    "ReviseArtifactRequest",
    "ReviseDecisionRequest",
    "RevokeGrantRequest",
    "SpaceInfo",
    "SpaceInspection",
    "WorkAcceptance",
    "WorkRevision",
    "WorkState",
    "LinkWorkOutputRequest",
]

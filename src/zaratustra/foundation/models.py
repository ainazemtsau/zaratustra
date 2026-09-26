"""Frozen contracts for the independent Core v0.1 domain foundation."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Annotated, Literal
from uuid import UUID

from pydantic import (
    AwareDatetime,
    BaseModel,
    ConfigDict,
    Discriminator,
    Field,
    JsonValue,
    Tag,
    model_validator,
)

type Action = Literal[
    "artifact.write",
    "activity.write",
    "work.write",
    "method.write",
    "method.use",
    "work.accept",
    "work.execute",
    "resource.write",
    "model.invoke",
    "decision.write",
    "grant.write",
    "record.read",
    "receipt.read",
    "space.inspect",
    "maintenance.backup",
    "maintenance.delete",
]
type RecordKind = Literal["artifact", "decision", "grant", "activity", "work", "method"]

ALL_ACTIONS: tuple[Action, ...] = (
    "artifact.write",
    "activity.write",
    "work.write",
    "method.write",
    "method.use",
    "work.accept",
    "work.execute",
    "resource.write",
    "model.invoke",
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


# A structural name or value; Core compares it exactly and never interprets prose.
Identifier = Annotated[str, Field(min_length=1, max_length=80, pattern=r"^[a-z][a-z0-9_-]*$")]


class DecisionScope(ContractModel):
    """The exact Work or Activity a choice covers; scopes overlap and form no tree."""

    kind: Literal["work", "activity"]
    record_id: UUID


class ChoiceState(ContractModel):
    """A named value with an explicit scope. It is never an access rule."""

    variant: Literal["choice"] = "choice"
    statement: str = Field(min_length=1, max_length=4096)
    name: Identifier
    value: Identifier
    scope: DecisionScope
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


class MethodRef(ContractModel):
    method_id: UUID
    version: int = Field(ge=1)
    checksum: str = Field(pattern=r"^[0-9A-F]{64}$")


class ObligationTarget(ContractModel):
    """Exactly one requirement: a composite parent Work and one obligation key."""

    work_id: UUID
    key: str = Field(min_length=1, max_length=80, pattern=r"^[a-z][a-z0-9_-]*$")


class ExceptionState(ContractModel):
    """A permitted deviation from exactly one requirement within explicit limits.

    ``target`` names the requirement, ``methods`` the exact Method versions within which
    the exception holds and ``statement`` the case and the reason. It is never an access
    rule and never a fulfilment: a waived obligation keeps this address and is shown
    apart from satisfied ones.
    """

    variant: Literal["exception"] = "exception"
    statement: str = Field(min_length=1, max_length=4096)
    target: ObligationTarget
    methods: tuple[MethodRef, ...] = Field(min_length=1)
    status: Literal["active", "revoked"] = "active"

    @model_validator(mode="after")
    def unique_limits(self) -> ExceptionState:
        versions = [(item.method_id, item.version) for item in self.methods]
        if len(versions) != len(set(versions)):
            raise ValueError("Exception limits name each Method version once")
        return self


def _decision_variant(value: object) -> str:
    variant = value.get("variant") if isinstance(value, dict) else getattr(value, "variant", None)
    return str(variant) if variant in ("choice", "exception") else "rule"


# An access rule keeps its earlier canonical form; only the other variants name themselves.
DecisionBody = Annotated[
    Annotated[DecisionState, Tag("rule")]
    | Annotated[ChoiceState, Tag("choice")]
    | Annotated[ExceptionState, Tag("exception")],
    Discriminator(_decision_variant),
]


class NamedInput(ContractModel):
    slot: str = Field(min_length=1, max_length=80, pattern=r"^[a-z][a-z0-9_-]*$")
    artifact: ArtifactRef


class CapabilityRequirement(ContractModel):
    name: str = Field(min_length=1, max_length=200)
    source_ref: str = Field(min_length=1, max_length=2048)


class ChoiceApplicability(ContractModel):
    """Which values of one named choice make an obligation active or inactive."""

    kind: Literal["choice"] = "choice"
    choice: Identifier
    active: tuple[Identifier, ...] = ()
    inactive: tuple[Identifier, ...] = ()

    @model_validator(mode="after")
    def exact_values(self) -> ChoiceApplicability:
        values = self.active + self.inactive
        if not values or len(values) != len(set(values)):
            raise ValueError("Applicability values must be unique and name at least one value")
        return self


class MethodObligation(ContractModel):
    key: str = Field(min_length=1, max_length=80, pattern=r"^[a-z][a-z0-9_-]*$")
    source: str = Field(min_length=1, max_length=2048)
    # Absent only for the schema 8 obligation proved in this composite Work.
    role: str | None = Field(
        default=None,
        min_length=1,
        max_length=80,
        pattern=r"^[a-z][a-z0-9_-]*$",
        exclude_if=lambda value: value is None,
    )
    slot: str = Field(min_length=1, max_length=80, pattern=r"^[a-z][a-z0-9_-]*$")
    media_type: str = Field(min_length=1, max_length=200)
    applicability: Literal["always"] | ChoiceApplicability = "always"


class MethodDefinition(ContractModel):
    instruction: str = Field(min_length=1, max_length=32768)
    applicability: Literal["always"] = "always"
    named_inputs: tuple[OutputContract, ...] = ()
    named_outputs: tuple[OutputContract, ...] = Field(min_length=1)
    obligations: tuple[MethodObligation, ...] = ()
    role_methods: tuple[tuple[str, MethodRef], ...] = ()
    required_capabilities: tuple[CapabilityRequirement, ...] = ()
    source_ref: str = Field(min_length=1, max_length=2048)

    @model_validator(mode="after")
    def unique_contract(self) -> MethodDefinition:
        for values in (
            [item.slot for item in self.named_inputs],
            [item.slot for item in self.named_outputs],
            [item.key for item in self.obligations],
            [role for role, _ in self.role_methods],
            [item.name for item in self.required_capabilities],
        ):
            if len(values) != len(set(values)):
                raise ValueError("Method contract keys must be unique")
        return self


class PlanCondition(ContractModel):
    kind: Literal[
        "accepted_output",
        "work_succeeded",
        "artifact_current",
        "decision_active",
        "decision_value",
        "all",
        "any",
    ]
    role: str | None = None
    slot: str | None = None
    media_type: str | None = None
    artifact: ArtifactRef | None = None
    decision_id: UUID | None = None
    decision_revision: int | None = Field(default=None, ge=1)
    members: tuple[PlanCondition, ...] = ()
    # Only a decision_value leaf names a choice; absent from earlier canonical plans.
    name: Identifier | None = Field(default=None, exclude_if=lambda value: value is None)
    value: Identifier | None = Field(default=None, exclude_if=lambda value: value is None)

    @model_validator(mode="after")
    def exact_shape(self) -> PlanCondition:
        fields = (
            self.role,
            self.slot,
            self.media_type,
            self.artifact,
            self.decision_id,
            self.decision_revision,
        )
        named = (self.name, self.value)
        if self.kind in ("all", "any"):
            if not self.members or any(value is not None for value in fields + named):
                raise ValueError("all/any require fixed members and no leaf fields")
        elif self.members:
            raise ValueError("Leaf condition cannot have members")
        elif self.kind != "decision_value" and any(value is not None for value in named):
            raise ValueError("Only decision_value names a choice and its value")
        elif self.kind == "decision_value" and (
            self.decision_id is None
            or self.decision_revision is None
            or self.name is None
            or self.value is None
            or any(value is not None for value in fields[:4])
        ):
            raise ValueError("decision_value needs exact Decision revision, choice name and value")
        elif self.kind == "accepted_output" and (
            not self.role
            or not self.slot
            or not self.media_type
            or any(value is not None for value in fields[3:])
        ):
            raise ValueError("accepted_output needs exact role, slot and type")
        elif self.kind == "work_succeeded" and (
            not self.role or any(value is not None for value in fields[1:])
        ):
            raise ValueError("work_succeeded needs only role")
        elif self.kind == "artifact_current" and (
            self.artifact is None or any(value is not None for value in fields[:3] + fields[4:])
        ):
            raise ValueError("artifact_current needs one exact Artifact")
        elif self.kind == "decision_active" and (
            self.decision_id is None
            or self.decision_revision is None
            or any(value is not None for value in fields[:4])
        ):
            raise ValueError("decision_active needs exact Decision revision")
        return self


class PlanOutputBinding(ContractModel):
    parent_slot: str = Field(min_length=1, max_length=80, pattern=r"^[a-z][a-z0-9_-]*$")
    role: str = Field(min_length=1, max_length=80, pattern=r"^[a-z][a-z0-9_-]*$")
    child_slot: str = Field(min_length=1, max_length=80, pattern=r"^[a-z][a-z0-9_-]*$")
    media_type: str = Field(min_length=1, max_length=200)


class ParentOutputSlot(ContractModel):
    """A plan declares its Work as producer; the publishing Attempt is evidence."""

    slot: str = Field(min_length=1, max_length=80, pattern=r"^[a-z][a-z0-9_-]*$")
    media_type: str = Field(min_length=1, max_length=200)


class PlanChild(ContractModel):
    role: str = Field(min_length=1, max_length=80, pattern=r"^[a-z][a-z0-9_-]*$")
    work_id: UUID
    state: WorkState
    readiness: PlanCondition | None = None


class WorkPlan(ContractModel):
    named_inputs: tuple[NamedInput, ...] = ()
    output_bindings: tuple[PlanOutputBinding, ...] = ()
    parent_outputs: tuple[ParentOutputSlot, ...] = Field(
        default=(), exclude_if=lambda value: not value
    )
    children: tuple[PlanChild, ...] = Field(min_length=1)
    completion: PlanCondition | None = None
    basis: tuple[ArtifactRef, ...] = ()
    rationale: str = Field(min_length=1, max_length=4096)
    source_ref: str = Field(min_length=1, max_length=2048)

    @model_validator(mode="after")
    def unique_children(self) -> WorkPlan:
        for values in (
            [item.slot for item in self.named_inputs],
            [item.parent_slot for item in self.output_bindings]
            + [item.slot for item in self.parent_outputs],
            [child.role for child in self.children],
            [child.work_id for child in self.children],
        ):
            if len(values) != len(set(values)):
                raise ValueError("Plan child roles and ids must be unique")
        return self


class MethodVersion(ContractModel):
    reference: MethodRef
    definition: MethodDefinition
    operation_id: UUID
    created_at: AwareDatetime
    actor: str


class PlanRevision(ContractModel):
    parent_work_id: UUID
    revision: int = Field(ge=1)
    plan: WorkPlan
    operation_id: UUID
    created_at: AwareDatetime
    actor: str


class DecisionRef(ContractModel):
    decision_id: UUID
    revision: int = Field(ge=1)


class PremiseChange(ContractModel):
    """One premise of an accepted child result: the held revision and the current one.

    ``current`` is ``None`` when the premise is no longer available; such a premise can
    never be rechecked, only left by an outcome or a plan revision.
    """

    kind: Literal["artifact", "decision"]
    record_id: UUID
    revision: int = Field(ge=1)
    current: int | None = Field(default=None, ge=1)

    @model_validator(mode="after")
    def names_a_change(self) -> PremiseChange:
        if self.current == self.revision:
            raise ValueError("A changed premise names another current revision")
        return self


class ParentResultEvidence(ContractModel):
    """The exact own Attempt and pin that published an obligation's result."""

    attempt_id: UUID
    plan_revision: int = Field(ge=1)
    method: MethodRef


class ObligationRevision(ContractModel):
    """One exact revision of a materialized obligation.

    Applicability and execution are separate fields. A conditional obligation starts
    ``unresolved``; an addressed choice (``choice``) resolves it ``active`` or
    ``inactive``, and execution starts ``open`` again with each resolution. An active
    obligation is executed ``satisfied`` with exact evidence or ``waived`` by an
    addressed exception (``exception``), never both. ``basis`` is the text of the
    operation that recorded this revision.
    """

    parent_work_id: UUID
    key: str
    revision: int = Field(ge=1)
    definition: MethodObligation
    applicability: Literal["active", "inactive", "unresolved"] = "active"
    status: Literal["open", "satisfied", "waived", "retired"]
    evidence: ArtifactRef | None = None
    parent_result: ParentResultEvidence | None = Field(
        default=None, exclude_if=lambda value: value is None
    )
    basis: str | None = None
    operation_id: UUID
    created_at: AwareDatetime
    # Absent from canonical JSON while empty, so earlier payloads stay byte-identical.
    choice: DecisionRef | None = Field(default=None, exclude_if=lambda value: value is None)
    exception: DecisionRef | None = Field(default=None, exclude_if=lambda value: value is None)
    # A plan revision reopened this execution: its evidence belongs to a Work that no longer
    # fills the role.
    reopened: Literal["node_replaced", "parent_attempt_replaced", "stale_plan"] | None = Field(
        default=None, exclude_if=lambda value: value is None
    )
    transitioned_to: str | None = Field(default=None, exclude_if=lambda value: value is None)
    retired_by: DecisionRef | None = Field(default=None, exclude_if=lambda value: value is None)
    carried_from_key: str | None = Field(default=None, exclude_if=lambda value: value is None)
    carried_from_revision: int | None = Field(
        default=None, ge=1, exclude_if=lambda value: value is None
    )

    @model_validator(mode="after")
    def applicability_matches_definition(self) -> ObligationRevision:
        if (self.carried_from_key is None) != (self.carried_from_revision is None):
            raise ValueError("A carried obligation names an exact source revision")
        if self.status == "retired":
            if (
                (self.transitioned_to is None) == (self.retired_by is None)
                or self.evidence is not None
                or self.parent_result is not None
                or self.basis is not None
                or self.exception is not None
                or self.reopened is not None
                or self.carried_from_key is not None
            ):
                raise ValueError("A retired obligation names its successor or exception only")
            return self
        if self.transitioned_to is not None or self.retired_by is not None:
            raise ValueError("Only a retired obligation names a transition")
        if self.definition.applicability == "always":
            if self.applicability != "active" or self.choice is not None:
                raise ValueError("An unconditional obligation is always active")
        elif (self.applicability == "unresolved") != (self.choice is None):
            raise ValueError("A conditional obligation is resolved only by an addressed choice")
        if self.applicability != "active" and (self.status != "open" or self.evidence is not None):
            raise ValueError("Only an active obligation is executed")
        if (self.status == "waived") != (self.exception is not None) or (
            self.status == "waived" and self.evidence is not None
        ):
            raise ValueError("Only a waived obligation names its exception, and no evidence")
        if self.reopened is not None and (self.status != "open" or self.basis is not None):
            raise ValueError("A reopened obligation is open and carries no basis")
        if self.parent_result is not None and (
            self.definition.role is not None or self.status != "satisfied" or self.evidence is None
        ):
            raise ValueError("Own Attempt evidence belongs only to a satisfied roleless need")
        if (
            self.definition.role is None
            and self.status == "satisfied"
            and self.parent_result is None
        ):
            raise ValueError("A roleless satisfied obligation needs its own Attempt evidence")
        return self


class WaivedObligation(ContractModel):
    """A requirement taken off by an exact exception; it is not a result."""

    key: str
    exception: DecisionRef


class ResultRevalidation(ContractModel):
    """Explicit recheck that an accepted child result holds under its changed premises.

    It permits integration of that exact result only while every named current revision
    stays current. ``basis`` is ``None`` after deletion of the child, one of its outputs
    or a named premise; the addresses stay and the record permits nothing any more.
    """

    parent_work_id: UUID
    role: str
    work_id: UUID
    revision: int = Field(ge=1)
    plan_revision: int = Field(ge=1)
    outputs: tuple[LinkedOutput, ...] = Field(min_length=1)
    premises: tuple[PremiseChange, ...] = Field(min_length=1)
    basis: str | None = Field(min_length=1, max_length=4096)
    operation_id: UUID
    created_at: AwareDatetime


class WorkAcceptance(ContractModel):
    """Separate acceptance of a Work's exact result.

    ``basis`` is ``None`` only in schema 7 and later, after deletion of something the
    basis structurally depends on; older schemas never store that representation. A read
    of schemas 2-6 withholds (``None``) a basis that an earlier deletion left in place
    until the explicit upgrade to 7 retires it; the stored bytes are not rewritten.
    ``waived`` names every requirement of a composite parent accepted under an exception.
    """

    operation_id: UUID
    basis: str | None = Field(min_length=1, max_length=4096)
    authority_source: str = Field(min_length=1, max_length=2048)
    accepted_at: AwareDatetime
    # Absent from canonical JSON while empty, so earlier acceptances stay byte-identical.
    waived: tuple[WaivedObligation, ...] = Field(default=(), exclude_if=lambda value: not value)


type ClosedOutcome = Literal["failed", "cancelled", "stale"]
CLOSED_OUTCOMES: tuple[ClosedOutcome, ...] = ("failed", "cancelled", "stale")


class WorkClosure(ContractModel):
    """Subject outcome of a Work that ended without acceptance; never a technical status.

    ``basis`` is ``None`` only after deletion of something the basis structurally depends
    on (see ``WorkAcceptance``); the outcome and addresses stay, the text does not.
    """

    outcome: ClosedOutcome
    operation_id: UUID
    basis: str | None = Field(min_length=1, max_length=4096)
    authority_source: str = Field(min_length=1, max_length=2048)
    closed_at: AwareDatetime
    premises: tuple[ArtifactRef, ...] = ()
    decision_premises: tuple[DecisionRef, ...] = ()

    @model_validator(mode="after")
    def premises_name_stale_only(self) -> WorkClosure:
        if (self.outcome == "stale") != bool(self.premises or self.decision_premises):
            raise ValueError("Only a stale outcome names its changed premises, and it must")
        return self


class WorkState(ContractModel):
    activity_id: UUID
    goal: str = Field(min_length=1, max_length=4096)
    inputs: tuple[ArtifactRef, ...] = ()
    constraints: tuple[str, ...] = ()
    expected_outputs: tuple[OutputContract, ...] = Field(min_length=1)
    method: Literal["none"] | MethodRef = "none"
    status: Literal["proposed", "succeeded", "failed", "cancelled", "stale"] = "proposed"
    linked_outputs: tuple[LinkedOutput, ...] = ()
    acceptance: WorkAcceptance | None = None
    # Absent from canonical JSON while empty, so earlier payloads and fingerprints hold.
    closure: WorkClosure | None = Field(default=None, exclude_if=lambda value: value is None)

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
        closed = self.status in CLOSED_OUTCOMES
        if closed != (self.closure is not None) or (
            self.closure is not None and self.closure.outcome != self.status
        ):
            raise ValueError("A closed outcome requires its own closure record")
        return self


class BindingChildTemplate(ContractModel):
    role: Identifier
    goal: str = Field(min_length=1, max_length=4096)
    expected_outputs: tuple[OutputContract, ...] = Field(min_length=1)
    constraints: tuple[str, ...] = ()
    readiness: PlanCondition | None = None
    consume_source: bool = False


class BindingNewWork(ContractModel):
    kind: Literal["new_work"] = "new_work"
    activity_id: UUID
    method: MethodRef
    goal: str = Field(min_length=1, max_length=4096)
    constraints: tuple[str, ...] = ()
    named_inputs: tuple[Identifier, ...] = Field(min_length=1)
    fixed_inputs: tuple[NamedInput, ...] = ()
    expected_outputs: tuple[OutputContract, ...] = Field(min_length=1)
    children: tuple[BindingChildTemplate, ...] = Field(min_length=1)
    output_bindings: tuple[PlanOutputBinding, ...] = ()
    parent_outputs: tuple[ParentOutputSlot, ...] = ()
    completion: PlanCondition | None = None
    rationale: str = Field(min_length=1, max_length=4096)
    source_ref: str = Field(min_length=1, max_length=2048)

    @model_validator(mode="after")
    def one_mapping_per_slot(self) -> BindingNewWork:
        slots = list(self.named_inputs) + [item.slot for item in self.fixed_inputs]
        if len(slots) != len(set(slots)):
            raise ValueError("Each consumer Method input has one Binding mapping")
        return self


class BindingOfferWork(ContractModel):
    kind: Literal["offer_work"] = "offer_work"
    work_id: UUID
    input_slot: Identifier


BindingTarget = Annotated[BindingNewWork | BindingOfferWork, Field(discriminator="kind")]


class BindingCondition(ContractModel):
    """An exact active Activity choice, never an inference from its statement."""

    choice: DecisionRef
    name: Identifier
    value: Identifier


class BindingDefinition(ContractModel):
    source_activity_id: UUID
    source_slot: Identifier
    media_type: str = Field(min_length=1, max_length=200)
    target: BindingTarget
    basis: str = Field(min_length=1, max_length=4096)
    condition: BindingCondition | None = None
    max_depth: int = Field(default=8, ge=1, le=32)


class BindingVersion(ContractModel):
    binding_id: UUID
    version: int = Field(ge=1)
    checksum: str = Field(pattern=r"^[0-9A-F]{64}$")
    definition: BindingDefinition
    state: Literal["trial", "enabled", "paused", "retired"]
    state_revision: int = Field(ge=1)
    first_event_state_revision: int = Field(ge=1)
    operation_id: UUID
    created_at: AwareDatetime


class BindingFiring(ContractModel):
    binding_id: UUID
    version: int = Field(ge=1)
    producer_work_id: UUID
    accepted_work_revision: int = Field(ge=1)
    source_operation_id: UUID
    artifact: ArtifactRef | None = None
    outcome: Literal["created", "offered", "blocked", "stopped"]
    reason: str | None = None
    basis: str | None = None
    consumer_work_id: UUID | None = None
    offer_id: UUID | None = None
    operation_id: UUID
    created_at: AwareDatetime


class BindingOffer(ContractModel):
    offer_id: UUID
    binding_id: UUID
    version: int = Field(ge=1)
    producer_work_id: UUID
    accepted_work_revision: int = Field(ge=1)
    source_operation_id: UUID
    artifact: ArtifactRef
    consumer_work_id: UUID
    input_slot: Identifier
    status: Literal["open", "accepted", "refused", "unavailable"]
    consumer_work_revision: int = Field(ge=1)
    resolved_operation_id: UUID | None = None
    resolution_basis: str | None = None


class BindingInputRevision(ContractModel):
    work_id: UUID
    revision: int = Field(ge=1)
    offer_id: UUID
    input_slot: Identifier
    artifact: ArtifactRef
    plan_revision: int | None = Field(default=None, ge=1)
    operation_id: UUID


PlanChild.model_rebuild()
WorkPlan.model_rebuild()


class OperationRequest(ContractModel):
    protocol_version: Literal[1] = 1
    operation_id: UUID
    space_id: UUID
    actor: str = Field(min_length=1, max_length=200)


class CreateBindingVersionRequest(OperationRequest):
    kind: Literal["create_binding_version"] = "create_binding_version"
    binding_id: UUID
    version: int = Field(ge=1)
    definition: BindingDefinition


class SetBindingStateRequest(OperationRequest):
    kind: Literal["set_binding_state"] = "set_binding_state"
    binding_id: UUID
    version: int = Field(ge=1)
    expected_state_revision: int = Field(ge=1)
    state: Literal["trial", "enabled", "paused", "retired"]


class FireBindingRequest(OperationRequest):
    kind: Literal["fire_binding"] = "fire_binding"
    binding_id: UUID
    version: int = Field(ge=1)
    producer_work_id: UUID
    accepted_work_revision: int = Field(ge=1)
    backfill: bool = False
    basis: str | None = Field(default=None, min_length=1, max_length=4096)

    @model_validator(mode="after")
    def backfill_needs_basis(self) -> FireBindingRequest:
        if self.backfill and self.basis is None:
            raise ValueError("Historical Binding events need an explicit backfill basis")
        return self


class ResolveBindingOfferRequest(OperationRequest):
    kind: Literal["resolve_binding_offer"] = "resolve_binding_offer"
    offer_id: UUID
    expected_consumer_revision: int = Field(ge=1)
    decision: Literal["accept", "refuse"]
    basis: str = Field(min_length=1, max_length=4096)


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
    state: DecisionBody


class ReviseDecisionRequest(OperationRequest):
    kind: Literal["revise_decision"] = "revise_decision"
    decision_id: UUID
    expected_revision: int = Field(ge=1)
    state: DecisionBody


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
        if (
            self.state.status != "proposed"
            or self.state.linked_outputs
            or self.state.method != "none"
        ):
            raise ValueError("New Work starts proposed with no linked output")
        return self


class CreateMethodVersionRequest(OperationRequest):
    kind: Literal["create_method_version"] = "create_method_version"
    method_id: UUID
    version: int = Field(ge=1)
    definition: MethodDefinition


class DeleteMethodVersionRequest(OperationRequest):
    kind: Literal["delete_method_version"] = "delete_method_version"
    method_id: UUID
    version: int = Field(ge=1)
    checksum: str = Field(pattern=r"^[0-9A-F]{64}$")


class CreateCompositeWorkRequest(OperationRequest):
    kind: Literal["create_composite_work"] = "create_composite_work"
    work_id: UUID
    state: WorkState
    plan: WorkPlan

    @model_validator(mode="after")
    def initial_state(self) -> CreateCompositeWorkRequest:
        if (
            self.state.method == "none"
            or self.state.status != "proposed"
            or self.state.linked_outputs
        ):
            raise ValueError("Composite Work needs a Method and starts unaccepted")
        return self


class ReviseWorkPlanRequest(OperationRequest):
    kind: Literal["revise_work_plan"] = "revise_work_plan"
    work_id: UUID
    expected_plan_revision: int = Field(ge=1)
    plan: WorkPlan


class IssueChildWorkRequest(OperationRequest):
    kind: Literal["issue_child_work"] = "issue_child_work"
    parent_work_id: UUID
    work_id: UUID
    expected_plan_revision: int = Field(ge=1)
    expected_work_revision: int = Field(ge=1)


class ConfirmObligationRequest(OperationRequest):
    kind: Literal["confirm_obligation"] = "confirm_obligation"
    work_id: UUID
    key: str = Field(min_length=1, max_length=80)
    expected_plan_revision: int = Field(ge=1)
    expected_obligation_revision: int = Field(ge=1)
    evidence: ArtifactRef
    basis: str = Field(min_length=1, max_length=4096)


class ResolveObligationApplicabilityRequest(OperationRequest):
    """Resolve one conditional obligation of a composite parent by an exact choice."""

    kind: Literal["resolve_obligation_applicability"] = "resolve_obligation_applicability"
    work_id: UUID
    key: str = Field(min_length=1, max_length=80)
    expected_plan_revision: int = Field(ge=1)
    expected_obligation_revision: int = Field(ge=1)
    choice: DecisionRef
    basis: str = Field(min_length=1, max_length=4096)


class WaiveObligationRequest(OperationRequest):
    """Take one active obligation of a composite parent off by an exact exception."""

    kind: Literal["waive_obligation"] = "waive_obligation"
    work_id: UUID
    key: str = Field(min_length=1, max_length=80)
    expected_plan_revision: int = Field(ge=1)
    expected_obligation_revision: int = Field(ge=1)
    exception: DecisionRef
    basis: str = Field(min_length=1, max_length=4096)


class RevalidateResultRequest(OperationRequest):
    """Recheck one accepted child result against exactly its changed premises.

    ``work_id`` is the child filling ``role`` of ``parent_work_id``; ``outputs`` are its
    exact linked outputs and each premise names its held and its current revision.
    """

    kind: Literal["revalidate_result"] = "revalidate_result"
    parent_work_id: UUID
    role: str = Field(min_length=1, max_length=80)
    work_id: UUID
    outputs: tuple[LinkedOutput, ...] = Field(min_length=1)
    expected_plan_revision: int = Field(ge=1)
    premises: tuple[PremiseChange, ...] = Field(min_length=1)
    basis: str = Field(min_length=1, max_length=4096)

    @model_validator(mode="after")
    def exact_pairs(self) -> RevalidateResultRequest:
        addresses = [(item.kind, item.record_id) for item in self.premises]
        slots = [item.slot for item in self.outputs]
        if len(addresses) != len(set(addresses)) or len(slots) != len(set(slots)):
            raise ValueError("Each premise and output is named once")
        if any(item.current is None for item in self.premises):
            raise ValueError("Each changed premise names its current revision")
        return self


type NodeDecisionKind = Literal["keep", "replace", "cancel", "stale", "release", "add"]


class NodeClosure(ContractModel):
    """Outcome of an unfinished node leaving the plan, as a ``CloseWorkRequest`` records it."""

    expected_revision: int = Field(ge=1)
    outcome: Literal["cancelled", "stale"]
    basis: str = Field(min_length=1, max_length=4096)
    premises: tuple[ArtifactRef, ...] = ()
    decision_premises: tuple[DecisionRef, ...] = ()

    @model_validator(mode="after")
    def premises_name_stale_only(self) -> NodeClosure:
        named = self.premises + self.decision_premises
        if (self.outcome == "stale") != bool(named):
            raise ValueError("Only a stale outcome names its changed premises, and it must")
        if len(set(self.premises)) != len(self.premises) or len(set(self.decision_premises)) != len(
            self.decision_premises
        ):
            raise ValueError("Changed premises must be unique")
        return self


class DescendantClosure(ContractModel):
    """Explicit closure of one unfinished node below a departing composite node."""

    parent_work_id: UUID
    expected_plan_revision: int = Field(ge=1)
    role: str = Field(min_length=1, max_length=80, pattern=r"^[a-z][a-z0-9_-]*$")
    work_id: UUID
    closure: NodeClosure


class PlanNodeDecision(ContractModel):
    """Explicit decision for one node of the current plan revision or one new node.

    ``work_id`` is the Work of the node in the current revision; for ``add`` it is the new
    Work. ``replace`` names the new Work filling the same role in ``replacement``. An
    unfinished node that leaves the plan (``cancel``, ``stale`` or ``replace``) gets its
    outcome from ``closure``; a finished one keeps its outcome and has none.
    """

    role: str = Field(min_length=1, max_length=80, pattern=r"^[a-z][a-z0-9_-]*$")
    decision: NodeDecisionKind
    work_id: UUID
    replacement: UUID | None = None
    closure: NodeClosure | None = None
    nested_plan: WorkPlan | None = Field(default=None, exclude_if=lambda value: value is None)
    descendants: tuple[DescendantClosure, ...] = Field(
        default=(), exclude_if=lambda value: not value
    )

    @model_validator(mode="after")
    def decision_shape(self) -> PlanNodeDecision:
        if (self.decision == "replace") != (self.replacement is not None):
            raise ValueError("Only replace names a replacement Work, and it must")
        if self.replacement == self.work_id:
            raise ValueError("A replacement is another Work")
        if self.decision in ("keep", "release", "add") and self.closure is not None:
            raise ValueError("Only a node that leaves the plan unfinished gets an outcome")
        if self.nested_plan is not None and self.decision not in ("add", "replace"):
            raise ValueError("Only a new node can provide its initial nested plan")
        if self.descendants and self.decision not in ("replace", "cancel", "stale"):
            raise ValueError("Only a departing node can close descendants")
        outcome = {"cancel": "cancelled", "stale": "stale"}.get(self.decision)
        if outcome is not None and (self.closure is None or self.closure.outcome != outcome):
            raise ValueError("cancel and stale name the matching outcome of the node")
        return self


class ObligationMapping(ContractModel):
    """Explicit disposition of one old Method requirement during a version change."""

    source_key: str = Field(min_length=1, max_length=80, pattern=r"^[a-z][a-z0-9_-]*$")
    action: Literal["carry", "retire"]
    target_key: str | None = Field(default=None, exclude_if=lambda value: value is None)
    exception: DecisionRef | None = Field(default=None, exclude_if=lambda value: value is None)


class MethodTransition(ContractModel):
    """Address-only record of the exact Method change for one plan revision."""

    parent_work_id: UUID
    plan_revision: int = Field(ge=2)
    from_method: MethodRef
    to_method: MethodRef
    mappings: tuple[ObligationMapping, ...]
    operation_id: UUID


class ReviseActivePlanRequest(OperationRequest):
    """Revise the plan of a started composite Work with an explicit decision per node.

    Every node of the current revision gets ``keep``, ``replace``, ``cancel``, ``stale`` or
    ``release``; every new node gets ``add``. ``ReviseWorkPlanRequest`` stays for revisions
    before any child is issued.
    """

    kind: Literal["revise_active_plan"] = "revise_active_plan"
    work_id: UUID
    expected_plan_revision: int = Field(ge=1)
    expected_work_revision: int = Field(ge=1)
    plan: WorkPlan
    nodes: tuple[PlanNodeDecision, ...] = Field(min_length=1)
    target_method: MethodRef | None = Field(default=None, exclude_if=lambda value: value is None)
    obligation_mapping: tuple[ObligationMapping, ...] = Field(
        default=(), exclude_if=lambda value: not value
    )

    @model_validator(mode="after")
    def one_decision_per_role(self) -> ReviseActivePlanRequest:
        roles = [item.role for item in self.nodes]
        works = [item.work_id for item in self.nodes] + [
            item.replacement for item in self.nodes if item.replacement is not None
        ]
        if len(roles) != len(set(roles)) or len(works) != len(set(works)):
            raise ValueError("Each role and each Work has one node decision")
        if self.target_method is None and self.obligation_mapping:
            raise ValueError("Obligation mapping needs an exact target Method")
        return self


class LinkWorkOutputRequest(OperationRequest):
    kind: Literal["link_work_output"] = "link_work_output"
    work_id: UUID
    expected_revision: int = Field(ge=1)
    output: LinkedOutput


class PublishAttemptOutputRequest(OperationRequest):
    kind: Literal["publish_attempt_output"] = "publish_attempt_output"
    attempt_id: UUID
    work_id: UUID
    session_id: UUID
    slot: str = Field(min_length=1, max_length=200)
    media_type: str = Field(min_length=1, max_length=200)
    content: bytes = Field(min_length=1, max_length=8 * 1024 * 1024)


class AcceptWorkRequest(OperationRequest):
    kind: Literal["accept_work"] = "accept_work"
    work_id: UUID
    expected_revision: int = Field(ge=1)
    basis: str = Field(min_length=1, max_length=4096)


class CloseWorkRequest(OperationRequest):
    """Record a Work outcome other than acceptance; ``stale`` names its changed premises."""

    kind: Literal["close_work"] = "close_work"
    work_id: UUID
    expected_revision: int = Field(ge=1)
    outcome: ClosedOutcome
    basis: str = Field(min_length=1, max_length=4096)
    premises: tuple[ArtifactRef, ...] = ()
    decision_premises: tuple[DecisionRef, ...] = ()

    @model_validator(mode="after")
    def premises_name_stale_only(self) -> CloseWorkRequest:
        named = self.premises + self.decision_premises
        if (self.outcome == "stale") != bool(named):
            raise ValueError("Only a stale outcome names its changed premises, and it must")
        if len(set(self.premises)) != len(self.premises) or len(set(self.decision_premises)) != len(
            self.decision_premises
        ):
            raise ValueError("Changed premises must be unique")
        return self


class DeleteWorkRequest(OperationRequest):
    kind: Literal["delete_work"] = "delete_work"
    work_id: UUID
    expected_revision: int = Field(ge=1)


class ResourceState(ContractModel):
    label: str = Field(min_length=1, max_length=200)
    root: Path
    mode: Literal["exclusive", "shared"] = "exclusive"
    limit_units: int = Field(ge=1)
    status: Literal["active", "revoked"] = "active"


class CreateResourceRequest(OperationRequest):
    kind: Literal["create_resource"] = "create_resource"
    resource_id: UUID
    work_id: UUID
    state: ResourceState


class ReviseResourceRequest(OperationRequest):
    kind: Literal["revise_resource"] = "revise_resource"
    resource_id: UUID
    work_id: UUID
    expected_revision: int = Field(ge=1)
    state: ResourceState


class StartAttemptRequest(OperationRequest):
    kind: Literal["start_attempt"] = "start_attempt"
    attempt_id: UUID
    work_id: UUID
    expected_work_revision: int = Field(ge=1)
    resource_id: UUID
    expected_resource_revision: int = Field(ge=1)
    session_id: UUID
    previous_attempt_id: UUID | None = None


class StopAttemptRequest(OperationRequest):
    kind: Literal["stop_attempt"] = "stop_attempt"
    attempt_id: UUID
    work_id: UUID
    session_id: UUID
    outcome: Literal["completed", "interrupted"]


class AssignAttemptRequest(OperationRequest):
    kind: Literal["assign_attempt"] = "assign_attempt"
    attempt_id: UUID
    work_id: UUID
    expected_work_revision: int = Field(ge=1)
    resource_id: UUID
    expected_resource_revision: int = Field(ge=1)
    session_id: UUID
    previous_attempt_id: UUID | None = None
    executor_version: str = Field(min_length=1, max_length=200)


class ClaimAttemptLaunchRequest(OperationRequest):
    kind: Literal["claim_attempt_launch"] = "claim_attempt_launch"
    attempt_id: UUID
    work_id: UUID
    session_id: UUID
    expected_assignment_revision: int = Field(ge=1)
    claim_nonce: UUID


class OpenWaitRequest(OperationRequest):
    kind: Literal["open_wait"] = "open_wait"
    wait_id: UUID
    attempt_id: UUID
    work_id: UUID
    session_id: UUID
    expected_assignment_revision: int = Field(ge=1)
    question: str = Field(min_length=1, max_length=8192)
    expected_actor: str = Field(min_length=1, max_length=200)
    remainder: str = Field(min_length=1, max_length=8192)
    partial_refs: tuple[ArtifactRef, ...] = ()


class AnswerWaitRequest(OperationRequest):
    kind: Literal["answer_wait"] = "answer_wait"
    wait_id: UUID
    attempt_id: UUID
    work_id: UUID
    session_id: UUID
    expected_wait_revision: int = Field(ge=1)
    answer: str = Field(min_length=1, max_length=8192)


class RequestAttemptStopRequest(OperationRequest):
    kind: Literal["request_attempt_stop"] = "request_attempt_stop"
    attempt_id: UUID
    work_id: UUID
    session_id: UUID
    expected_assignment_revision: int = Field(ge=1)
    reason: str = Field(min_length=1, max_length=4096)


class RecordAttemptStopRequest(OperationRequest):
    kind: Literal["record_attempt_stop"] = "record_attempt_stop"
    attempt_id: UUID
    work_id: UUID
    session_id: UUID
    expected_assignment_revision: int = Field(ge=1)
    outcome: Literal["stopped", "unknown"]


class PrepareInvocationRequest(OperationRequest):
    kind: Literal["prepare_invocation"] = "prepare_invocation"
    invocation_id: UUID
    attempt_id: UUID
    work_id: UUID
    session_id: UUID
    purpose: Literal["content", "compaction-summary", "overflow-retry", "other"]
    provider: str = Field(min_length=1, max_length=200)
    model: str = Field(min_length=1, max_length=200)
    transport: str = Field(min_length=1, max_length=80)
    request_sha256: str = Field(pattern=r"^[0-9a-fA-F]{64}$")
    request_bytes: int = Field(ge=1)
    reserve_units: int = Field(ge=1)


class AdmitInvocationRequest(OperationRequest):
    kind: Literal["admit_invocation"] = "admit_invocation"
    invocation_id: UUID
    attempt_id: UUID
    work_id: UUID
    session_id: UUID


class SendInvocationRequest(OperationRequest):
    kind: Literal["send_invocation"] = "send_invocation"
    invocation_id: UUID
    attempt_id: UUID
    work_id: UUID
    session_id: UUID


class FinishInvocationRequest(OperationRequest):
    kind: Literal["finish_invocation"] = "finish_invocation"
    invocation_id: UUID
    attempt_id: UUID
    work_id: UUID
    session_id: UUID
    outcome: Literal["answered", "unknown"]
    usage_units: int | None = Field(default=None, ge=0)
    http_status: int | None = Field(default=None, ge=100, le=599)

    @model_validator(mode="after")
    def usage_matches_outcome(self) -> FinishInvocationRequest:
        if (self.outcome == "answered") != (self.usage_units is not None):
            raise ValueError("Answered calls require usage; unknown calls retain reserve")
        return self


DomainRequest = Annotated[
    BootstrapRequest
    | RecoverRequest
    | CreateBindingVersionRequest
    | SetBindingStateRequest
    | FireBindingRequest
    | ResolveBindingOfferRequest
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
    | CreateMethodVersionRequest
    | DeleteMethodVersionRequest
    | CreateCompositeWorkRequest
    | ReviseWorkPlanRequest
    | IssueChildWorkRequest
    | ConfirmObligationRequest
    | ResolveObligationApplicabilityRequest
    | WaiveObligationRequest
    | RevalidateResultRequest
    | ReviseActivePlanRequest
    | LinkWorkOutputRequest
    | PublishAttemptOutputRequest
    | AcceptWorkRequest
    | CloseWorkRequest
    | DeleteWorkRequest
    | CreateResourceRequest
    | ReviseResourceRequest
    | StartAttemptRequest
    | StopAttemptRequest
    | AssignAttemptRequest
    | ClaimAttemptLaunchRequest
    | OpenWaitRequest
    | AnswerWaitRequest
    | RequestAttemptStopRequest
    | RecordAttemptStopRequest
    | PrepareInvocationRequest
    | AdmitInvocationRequest
    | SendInvocationRequest
    | FinishInvocationRequest,
    Field(discriminator="kind"),
]


class SpaceInfo(ContractModel):
    root: Path
    database: Path
    space_id: UUID
    created_at: AwareDatetime
    schema_version: Literal[1, 2, 3, 4, 5, 6, 7, 8, 9]
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


class DecisionRevision(ContractModel):
    """One exact Decision revision: an access rule, an addressed choice or exception."""

    decision_id: UUID
    revision: int = Field(ge=1)
    operation_id: UUID
    created_at: AwareDatetime
    actor: str
    state: DecisionBody


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


class ResourceRevision(ContractModel):
    resource_id: UUID
    work_id: UUID
    revision: int = Field(ge=1)
    state: ResourceState


class AttemptRecord(ContractModel):
    attempt_id: UUID
    revision: int = Field(ge=1)
    work_id: UUID
    work_revision: int = Field(ge=1)
    resource_id: UUID
    resource_revision: int = Field(ge=1)
    session_id: UUID
    previous_attempt_id: UUID | None
    execution_epoch: int = Field(ge=1)
    generation: int = Field(ge=1)
    input_refs: tuple[ArtifactRef, ...]
    status: Literal["active", "completed", "interrupted"]


class InvocationRecord(ContractModel):
    invocation_id: UUID
    revision: int = Field(ge=1)
    attempt_id: UUID
    purpose: str
    provider: str
    model: str
    transport: str
    request_sha256: str | None
    request_bytes: int = Field(ge=1)
    reserve_units: int = Field(ge=1)
    usage_units: int | None = Field(default=None, ge=0)
    status: Literal["prepared", "admitted", "sent", "answered", "unknown"]
    http_status: int | None = None


class AssignmentRecord(ContractModel):
    attempt_id: UUID
    work_id: UUID
    revision: int = Field(ge=1)
    executor_version: str
    status: Literal[
        "assigned", "waiting", "ready", "stop_requested", "stopped", "unknown", "interrupted"
    ]
    stop_reason: str | None = None


class WaitRecord(ContractModel):
    wait_id: UUID
    attempt_id: UUID
    work_id: UUID
    revision: int = Field(ge=1)
    status: Literal["open", "answered", "closed", "purged"]
    question: str | None
    expected_actor: str
    remainder: str | None
    partial_refs: tuple[ArtifactRef, ...]
    answer: str | None
    answer_source: str | None


class OutboxRecord(ContractModel):
    outbox_id: UUID
    attempt_id: UUID
    work_id: UUID
    wait_id: UUID | None
    execution_epoch: int = Field(ge=1)
    generation: int = Field(ge=1)
    kind: Literal["launch", "resume"]
    status: Literal["pending", "cancelled"]


type WorkLifecycle = Literal[
    "proposed",
    "ready",
    "running",
    "waiting",
    "blocked",
    "succeeded",
    "failed",
    "cancelled",
    "stale",
]


class StatusReason(ContractModel):
    """One addressed cause of a derived Work state; never a copy of Work content."""

    code: str = Field(min_length=1, max_length=80)
    role: str | None = None
    record_id: UUID | None = None
    revision: int | None = Field(default=None, ge=1)
    # Obligation key and choice name of an applicability reason; absent otherwise.
    key: str | None = Field(default=None, exclude_if=lambda value: value is None)
    name: str | None = Field(default=None, exclude_if=lambda value: value is None)
    # The held and current revision of a changed premise of an accepted child result.
    premise: PremiseChange | None = Field(default=None, exclude_if=lambda value: value is None)


class WorkStatus(ContractModel):
    """Current Work state derived from Core issue, plan, Attempt and wait records."""

    work_id: UUID
    status: WorkLifecycle
    reasons: tuple[StatusReason, ...] = ()
    attempt_id: UUID | None = None
    wait_id: UUID | None = None


class PlanPin(ContractModel):
    """Exact plan and Method address fixed when a child Attempt was assigned."""

    attempt_id: UUID
    work_id: UUID
    parent_work_id: UUID
    role: str
    plan_revision: int = Field(ge=1)
    method: MethodRef


class ParentPlanPin(ContractModel):
    attempt_id: UUID
    work_id: UUID
    plan_revision: int = Field(ge=1)
    method: MethodRef
    operation_id: UUID


class ParentOutputProof(ContractModel):
    work_id: UUID
    slot: str
    artifact: ArtifactRef
    attempt_id: UUID
    plan_revision: int = Field(ge=1)
    method: MethodRef
    operation_id: UUID


class ChildProgress(ContractModel):
    role: str
    work_id: UUID
    issued_plan_revision: int | None = None
    status: WorkStatus
    # Revision of the recheck that currently lets this accepted result integrate.
    revalidation: int | None = Field(default=None, exclude_if=lambda value: value is None)


class ObligationProgress(ContractModel):
    """Recorded execution with derived applicability and waiver.

    A resolution whose exact choice is no longer current reads ``applicability_stale``
    until it is resolved again; a waiver whose exact exception no longer holds reads
    ``waiver_stale`` until the obligation is confirmed or waived again.
    """

    key: str
    revision: int = Field(ge=1)
    role: str | None = Field(default=None, exclude_if=lambda value: value is None)
    applicability: Literal["active", "inactive", "unresolved", "applicability_stale"] = "active"
    status: Literal["open", "satisfied", "waived", "waiver_stale"]
    evidence: ArtifactRef | None = None
    choice: DecisionRef | None = Field(default=None, exclude_if=lambda value: value is None)
    exception: DecisionRef | None = Field(default=None, exclude_if=lambda value: value is None)
    reopened: Literal["node_replaced", "parent_attempt_replaced", "stale_plan"] | None = Field(
        default=None, exclude_if=lambda value: value is None
    )


class PlanTransfer(ContractModel):
    """Explicit transfer of one active child Attempt into a later plan revision.

    Recorded by the plan revision that kept its node, after the current rights, inputs,
    readiness and Method use were rechecked; the original pin is never rewritten.
    """

    attempt_id: UUID
    work_id: UUID
    parent_work_id: UUID
    role: str
    from_plan_revision: int = Field(ge=1)
    plan_revision: int = Field(ge=2)
    method: MethodRef
    operation_id: UUID


class PlanNode(ContractModel):
    """One recorded node decision of an active plan revision; addresses only.

    ``work_id`` fills the role in the new revision (keep, replace, add) or leaves the plan
    (cancel, stale, release); ``replaced_work_id`` is the Work a replacement took over from.
    ``closed_revision`` is the Work revision holding the outcome recorded for a node that
    left unfinished; its basis lives there.
    """

    role: str
    decision: NodeDecisionKind
    work_id: UUID
    replaced_work_id: UUID | None = None
    issue_carried: bool = False
    closed_revision: int | None = Field(default=None, ge=1)


class PlanNodes(ContractModel):
    """The explicit node mapping from one plan revision to the next."""

    parent_work_id: UUID
    plan_revision: int = Field(ge=2)
    operation_id: UUID
    nodes: tuple[PlanNode, ...]


class RoleFilling(ContractModel):
    """One Work filling a role over consecutive plan revisions."""

    role: str
    work_id: UUID
    first_plan_revision: int = Field(ge=1)
    # None while the Work still fills the role in the current revision.
    last_plan_revision: int | None = Field(default=None, ge=1)


class CompositionView(ContractModel):
    """Addresses and states of one composite Work; plan content stays in its revision.

    ``children`` are the nodes of the current plan revision; ``departed`` are Works that
    filled a role in an earlier revision and left the plan (replaced, cancelled, stale or
    released).
    """

    parent_work_id: UUID
    method: MethodRef
    plan_revision: int = Field(ge=1)
    plan_available: bool
    role: str | None = None
    issued_plan_revision: int | None = None
    pins: tuple[PlanPin, ...] = ()
    own_pins: tuple[ParentPlanPin, ...] = Field(default=(), exclude_if=lambda value: not value)
    children: tuple[ChildProgress, ...] = ()
    obligations: tuple[ObligationProgress, ...] = ()
    # Absent while empty, so reads of plans without active revisions stay unchanged.
    departed: tuple[ChildProgress, ...] = Field(default=(), exclude_if=lambda value: not value)
    transfers: tuple[PlanTransfer, ...] = Field(default=(), exclude_if=lambda value: not value)
    # Address-only decisions of the current revision. The plan text remains in its
    # separately authorized revision, even when the node is nested.
    nodes: tuple[PlanNode, ...] = Field(default=(), exclude_if=lambda value: not value)
    # A child can itself own a composite plan. Keep both its parent binding and its
    # own immediate children visible without recursively copying plan contents.
    nested: CompositionView | None = Field(default=None, exclude_if=lambda value: value is None)


class ExecutionSnapshot(ContractModel):
    space_id: UUID
    execution_epoch: int = Field(ge=1)
    activity: ActivityRevision
    work: WorkRevision
    inputs: tuple[ArtifactRevision, ...]
    outputs: tuple[ArtifactRevision, ...]
    resources: tuple[ResourceRevision, ...]
    attempts: tuple[AttemptRecord, ...]
    invocations: tuple[InvocationRecord, ...]
    assignments: tuple[AssignmentRecord, ...] = ()
    waits: tuple[WaitRecord, ...] = ()
    outbox: tuple[OutboxRecord, ...] = ()
    work_rights: tuple[Action, ...]
    limit_units: int | None = None
    committed_units: int = Field(ge=0)
    held_units: int = Field(ge=0)
    remaining_units: int | None = None
    status: WorkStatus | None = None
    composition: CompositionView | None = None


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


class TechnicalVersions(ContractModel):
    executor: str = Field(min_length=1)
    dbos: str = Field(min_length=1)
    pi: str = Field(min_length=1)
    bridge_protocol: int = Field(ge=1)


class BackupManifest(ContractModel):
    backup_id: UUID
    format_version: Literal[1, 2] = 1
    space_id: UUID
    schema_version: Literal[1, 2, 3, 4, 5, 6, 7, 8, 9]
    state_revision: int = Field(ge=0)
    execution_epoch: int = Field(ge=1)
    created_at: AwareDatetime
    database_file: Literal["core.sqlite3"] = "core.sqlite3"
    database_sha256: str = Field(pattern=r"^[0-9A-F]{64}$")
    sqlite_version: str | None = None
    core_version: str | None = None
    maintenance_boundary: Literal["exclusive-managed"] | None = None
    technical_versions: TechnicalVersions | None = None
    executor_sha256: str | None = Field(default=None, pattern=r"^[0-9A-F]{64}$")
    pi_rpc_home_files: dict[str, str] = Field(default_factory=dict)


class BackupInfo(ContractModel):
    manifest: BackupManifest
    package: Path


class DeletionStatus(ContractModel):
    pending_jobs: int = Field(ge=0)
    completed_jobs: int = Field(ge=0)
    purged_backups: int = Field(ge=0)
    live_store_sanitized: bool
    completed_at: datetime | None = None
    # Schemas 2-6: Works whose outcome basis an earlier deletion left in place. Only the
    # explicit upgrade named here can retire it; until then nothing is reported complete.
    retained_bases: tuple[UUID, ...] = ()
    upgrade_required: Literal[7] | None = None

    @model_validator(mode="after")
    def honest_completion(self) -> DeletionStatus:
        if self.retained_bases and (self.live_store_sanitized or self.upgrade_required is None):
            raise ValueError("Retained outcome bases need the explicit upgrade")
        if self.completed_at is not None and not self.live_store_sanitized:
            raise ValueError("Only a sanitized live store has a completion time")
        return self


__all__ = [
    "BindingInputRevision",
    "BindingChildTemplate",
    "BindingNewWork",
    "BindingOfferWork",
    "BindingDefinition",
    "BindingVersion",
    "BindingFiring",
    "BindingOffer",
    "CreateBindingVersionRequest",
    "SetBindingStateRequest",
    "FireBindingRequest",
    "ResolveBindingOfferRequest",
    "NodeClosure",
    "DescendantClosure",
    "NodeDecisionKind",
    "PlanNode",
    "PlanNodeDecision",
    "PlanNodes",
    "ObligationMapping",
    "MethodTransition",
    "PlanTransfer",
    "ReviseActivePlanRequest",
    "RoleFilling",
    "ExceptionState",
    "ObligationTarget",
    "PremiseChange",
    "ResultRevalidation",
    "RevalidateResultRequest",
    "WaivedObligation",
    "WaiveObligationRequest",
    "ChoiceApplicability",
    "ChoiceState",
    "DecisionBody",
    "DecisionRevision",
    "DecisionScope",
    "Identifier",
    "ResolveObligationApplicabilityRequest",
    "CLOSED_OUTCOMES",
    "ClosedOutcome",
    "CloseWorkRequest",
    "DecisionRef",
    "WorkClosure",
    "ChildProgress",
    "CompositionView",
    "ObligationProgress",
    "PlanPin",
    "StatusReason",
    "WorkLifecycle",
    "WorkStatus",
    "PlanOutputBinding",
    "CapabilityRequirement",
    "NamedInput",
    "WorkPlan",
    "ReviseWorkPlanRequest",
    "PlanRevision",
    "PlanCondition",
    "PlanChild",
    "ObligationRevision",
    "MethodVersion",
    "MethodRef",
    "MethodObligation",
    "MethodDefinition",
    "IssueChildWorkRequest",
    "DeleteMethodVersionRequest",
    "CreateMethodVersionRequest",
    "CreateCompositeWorkRequest",
    "ConfirmObligationRequest",
    "ALL_ACTIONS",
    "AcceptWorkRequest",
    "AnswerWaitRequest",
    "AdmitInvocationRequest",
    "AssignAttemptRequest",
    "ClaimAttemptLaunchRequest",
    "AssignmentRecord",
    "Action",
    "ActivityRevision",
    "ActivityState",
    "AttemptRecord",
    "AuditReference",
    "ArtifactRevision",
    "ArtifactRef",
    "BackupInfo",
    "BackupManifest",
    "TechnicalVersions",
    "BootstrapRequest",
    "CreateActivityRequest",
    "CreateArtifactRequest",
    "CreateDecisionRequest",
    "CreateGrantRequest",
    "CreateWorkRequest",
    "CreateResourceRequest",
    "DecisionState",
    "DeleteActivityRequest",
    "DeleteArtifactRequest",
    "DeleteWorkRequest",
    "DeletionStatus",
    "FinishInvocationRequest",
    "DomainRequest",
    "ExecutionSnapshot",
    "GrantState",
    "InvocationRecord",
    "OperationReceipt",
    "OpenWaitRequest",
    "OutboxRecord",
    "OperationAuditEntry",
    "PrepareInvocationRequest",
    "PublishAttemptOutputRequest",
    "OutputContract",
    "LinkedOutput",
    "ProvenanceRef",
    "RecordSummary",
    "RecoverRequest",
    "RecordAttemptStopRequest",
    "RequestAttemptStopRequest",
    "ResourceState",
    "ResourceRevision",
    "ReviseActivityRequest",
    "ReviseArtifactRequest",
    "ReviseDecisionRequest",
    "ReviseResourceRequest",
    "RevokeGrantRequest",
    "SpaceInfo",
    "SpaceInspection",
    "SendInvocationRequest",
    "StartAttemptRequest",
    "StopAttemptRequest",
    "WaitRecord",
    "WorkAcceptance",
    "WorkRevision",
    "WorkState",
    "LinkWorkOutputRequest",
]

"""Frozen contracts for the independent Core v0.1 domain foundation."""

from __future__ import annotations

from datetime import date, datetime
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

from .capabilities import ProcedureOperation

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
    "memory.transfer",
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
    "memory.transfer",
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


class ChangeDecisionState(ContractModel):
    """An addressed adoption decision, never an access rule or a Grant."""

    variant: Literal["change_adoption"] = "change_adoption"
    statement: str = Field(min_length=1, max_length=4096)
    candidate_id: UUID
    candidate_revision: int = Field(ge=1)
    mode: Literal["trial", "regular"]
    trial_use_limit: int | None = Field(default=None, ge=1, le=1000)
    use: Literal["permitted", "recommended", "required"]
    scope_activity_id: UUID | None = None
    scope_global: bool = False
    validation_result_ids: tuple[UUID, ...] = ()
    review_condition: str = Field(min_length=1, max_length=2048)
    status: Literal["active", "suspended", "revoked"] = "active"

    @model_validator(mode="after")
    def one_scope(self) -> ChangeDecisionState:
        if (self.scope_activity_id is not None) == self.scope_global:
            raise ValueError("Adoption has exactly one activity or global scope")
        if (self.mode == "trial") != (self.trial_use_limit is not None):
            raise ValueError("Trial admission needs a finite use limit")
        return self


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


class KnowledgeRef(ContractModel):
    """One exact revision; optional offsets refer to retained bytes."""

    record_id: UUID
    revision: int = Field(ge=1)
    start: int | None = Field(default=None, ge=0)
    end: int | None = Field(default=None, ge=1)

    @model_validator(mode="after")
    def valid_fragment(self) -> KnowledgeRef:
        if (self.start is None) != (self.end is None) or (
            self.start is not None and self.end is not None and self.end <= self.start
        ):
            raise ValueError("A fragment needs an ordered start and end")
        return self


MaterialRole = Literal["working", "basis", "intake", "execution", "representation"]


class DataFilter(ContractModel):
    field: Identifier
    operator: Literal["eq", "ne", "lt", "le", "gt", "ge", "missing", "unknown"] = "eq"
    value: JsonValue = None


class ActivityState(ContractModel):
    title: str = Field(min_length=1, max_length=200)
    goal: str = Field(min_length=1, max_length=4096)
    status: Literal["ongoing", "paused", "completed"] = "ongoing"


class OutputContract(ContractModel):
    slot: str = Field(min_length=1, max_length=80, pattern=r"^[a-z][a-z0-9_-]*$")
    media_type: str = Field(min_length=1, max_length=200)
    format_ref: KnowledgeRef | None = Field(default=None, exclude_if=lambda value: value is None)
    allow_empty: bool = Field(default=False, exclude_if=lambda value: not value)


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
    return str(variant) if variant in ("choice", "exception", "change_adoption") else "rule"


# An access rule keeps its earlier canonical form; only the other variants name themselves.
DecisionBody = Annotated[
    Annotated[DecisionState, Tag("rule")]
    | Annotated[ChoiceState, Tag("choice")]
    | Annotated[ExceptionState, Tag("exception")]
    | Annotated[ChangeDecisionState, Tag("change_adoption")],
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


class MemoryMetadata(ContractModel):
    """Agent-declared organization, separate from epistemic status and access."""

    title: str = Field(min_length=1, max_length=500)
    activity_id: UUID | None = None
    topics: tuple[Annotated[str, Field(min_length=1, max_length=200)], ...] = ()
    aliases: tuple[Annotated[str, Field(min_length=1, max_length=500)], ...] = ()
    context_role: Literal["reference", "required"] = "reference"
    material_role: MaterialRole | None = Field(default=None, exclude_if=lambda value: value is None)


class MemorySelector(ContractModel):
    """Union across selectors; filters within a selector are conjunctive."""

    empty: bool = Field(default=False, exclude_if=lambda value: not value)
    use_period: bool = Field(default=False, exclude_if=lambda value: not value)

    activity_ids: tuple[UUID, ...] = ()
    current_activity: bool = False
    common: bool = False
    record_ids: tuple[UUID, ...] = ()
    topics: tuple[str, ...] = ()
    query: str | None = None
    full: bool = False
    context_role: Literal["reference", "required", "legacy"] | None = None
    kinds: tuple[
        Literal[
            "source",
            "claim",
            "analysis",
            "link",
            "view",
            "handoff",
            "data_format",
            "data_entry",
            "activity_structure",
        ],
        ...,
    ] = Field(default=(), exclude_if=lambda value: not value)
    material_roles: tuple[MaterialRole, ...] = Field(default=(), exclude_if=lambda value: not value)
    format_refs: tuple[KnowledgeRef, ...] = Field(default=(), exclude_if=lambda value: not value)
    format_keys: tuple[Identifier, ...] = Field(default=(), exclude_if=lambda value: not value)
    data_filters: tuple[DataFilter, ...] = Field(default=(), exclude_if=lambda value: not value)
    date_from: date | None = Field(default=None, exclude_if=lambda value: value is None)
    date_until: date | None = Field(default=None, exclude_if=lambda value: value is None)
    time_from: AwareDatetime | None = Field(default=None, exclude_if=lambda value: value is None)
    time_until: AwareDatetime | None = Field(default=None, exclude_if=lambda value: value is None)
    data_statuses: tuple[str, ...] = Field(default=(), exclude_if=lambda value: not value)


class MemoryRequirement(ContractModel):
    selectors: tuple[MemorySelector, ...] = Field(min_length=1)
    required: bool = True


class MethodDefinition(ContractModel):
    instruction: str = Field(min_length=1, max_length=32768)
    applicability: Literal["always"] = "always"
    named_inputs: tuple[OutputContract, ...] = ()
    named_outputs: tuple[OutputContract, ...] = Field(min_length=1)
    obligations: tuple[MethodObligation, ...] = ()
    role_methods: tuple[tuple[str, MethodRef], ...] = ()
    required_capabilities: tuple[CapabilityRequirement, ...] = ()
    source_ref: str = Field(min_length=1, max_length=2048)
    memory_requirements: tuple[MemoryRequirement, ...] = Field(
        default=(), exclude_if=lambda value: not value
    )

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
        "validated_internal_output",
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
    validation_id: UUID | None = Field(default=None, exclude_if=lambda value: value is None)

    @model_validator(mode="after")
    def exact_shape(self) -> PlanCondition:
        if self.kind == "validated_internal_output":
            if (
                not self.role
                or not self.slot
                or not self.media_type
                or self.artifact is None
                or self.validation_id is None
                or self.members
                or self.decision_id is not None
                or self.decision_revision is not None
                or self.name is not None
                or self.value is not None
            ):
                raise ValueError(
                    "Internal output needs exact role, slot, type, Artifact and validation receipt"
                )
            return self
        if self.validation_id is not None:
            raise ValueError("Only internal output names a validation receipt")
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
    nested_plan: WorkPlan | None = Field(default=None, exclude_if=lambda v: v is None)


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
    structure: KnowledgeRef | None = Field(default=None, exclude_if=lambda value: value is None)

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


class ActivityCreation(ContractModel):
    activity_id: UUID
    state: ActivityState


class ActivityRevisionChange(ContractModel):
    activity_id: UUID
    expected_revision: int = Field(ge=1)
    state: ActivityState


class WorkActivityMove(ContractModel):
    work_id: UUID
    expected_revision: int = Field(ge=1)
    from_activity_id: UUID
    to_activity_id: UUID

    @model_validator(mode="after")
    def different_activities(self) -> WorkActivityMove:
        if self.from_activity_id == self.to_activity_id:
            raise ValueError("Work move needs a different destination Activity")
        return self


class ReorganizeActivitiesRequest(OperationRequest):
    """One exact split, merge or retirement of current Activity membership."""

    kind: Literal["reorganize_activities"] = "reorganize_activities"
    creations: tuple[ActivityCreation, ...] = ()
    revisions: tuple[ActivityRevisionChange, ...] = ()
    moves: tuple[WorkActivityMove, ...] = ()
    rationale: str = Field(min_length=1, max_length=4096)
    binding_disposition: str = Field(min_length=1, max_length=4096)
    decision_disposition: str = Field(min_length=1, max_length=4096)
    grant_disposition: str = Field(min_length=1, max_length=4096)
    event_boundary: str = Field(min_length=1, max_length=4096)

    @model_validator(mode="after")
    def unique_targets(self) -> ReorganizeActivitiesRequest:
        created = [item.activity_id for item in self.creations]
        revised = [item.activity_id for item in self.revisions]
        moved = [item.work_id for item in self.moves]
        if not (created or revised or moved):
            raise ValueError("Reorganization needs an actual change")
        if len(created) != len(set(created)) or len(revised) != len(set(revised)):
            raise ValueError("Activity addresses must be unique")
        if set(created) & set(revised) or len(moved) != len(set(moved)):
            raise ValueError("Reorganization targets overlap")
        return self


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
    content: bytes = Field(max_length=8 * 1024 * 1024)


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
    limit_units: int | None = Field(default=None, ge=1)
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


class SourceState(ContractModel):
    kind: Literal["source"] = "source"
    channel: Literal[
        "conversation_user",
        "conversation_assistant",
        "core_operation",
        "tool_result",
        "document",
        "external_report",
    ]
    connection: str = Field(min_length=1, max_length=160)
    profile_revision: int = Field(ge=1)
    source_event_id: str | None = Field(default=None, max_length=300)
    source_order: int | None = Field(default=None, ge=0)
    conversation_id: str | None = Field(default=None, max_length=300)
    scope_activity_id: UUID | None = None
    scope_work_id: UUID | None = None
    sender: str | None = Field(default=None, max_length=200)
    claimed_author: str | None = Field(default=None, max_length=200)
    event_at: AwareDatetime | None = None
    event_time_basis: str | None = Field(default=None, max_length=500)
    media_type: str = Field(min_length=1, max_length=200)
    capture: Literal["full", "fragment", "reference", "excluded"]
    content: bytes | None = Field(default=None, max_length=8 * 1024 * 1024)
    locator: str | None = Field(default=None, max_length=2048)
    limitations: tuple[str, ...] = ()
    derived_from: tuple[KnowledgeRef, ...] = ()
    memory: MemoryMetadata | None = Field(default=None, exclude_if=lambda value: value is None)

    @model_validator(mode="after")
    def capture_is_honest(self) -> SourceState:
        if (self.capture in ("full", "fragment")) != (self.content is not None):
            raise ValueError("Captured bytes and declared availability must agree")
        if self.capture == "reference" and not self.locator:
            raise ValueError("A reference-only source needs a locator")
        if self.event_at is not None and not self.event_time_basis:
            raise ValueError("Event time needs its source")
        return self


class ClaimState(ContractModel):
    kind: Literal["claim"] = "claim"
    proposition: str = Field(min_length=1, max_length=16384)
    epistemic_kind: Literal["observed", "reported", "derived", "hypothesis"]
    status: Literal["current", "contested", "superseded", "retracted", "unsupported"]
    scope_activity_id: UUID | None = None
    scope_method_id: UUID | None = None
    scope_global: bool = False
    evidence: tuple[KnowledgeRef, ...] = ()
    counter_evidence: tuple[KnowledgeRef, ...] = ()
    supersedes: KnowledgeRef | None = None
    interpretation_basis: str = Field(min_length=1, max_length=4096)
    valid_from: AwareDatetime | None = None
    valid_until: AwareDatetime | None = None
    memory: MemoryMetadata | None = Field(default=None, exclude_if=lambda value: value is None)

    @model_validator(mode="after")
    def explicit_scope_and_basis(self) -> ClaimState:
        if (
            sum(
                (
                    self.scope_activity_id is not None,
                    self.scope_method_id is not None,
                    self.scope_global,
                )
            )
            != 1
        ):
            raise ValueError("Claim needs exactly one declared scope")
        if self.status in ("current", "contested") and not self.evidence:
            raise ValueError("A current or contested Claim needs exact evidence")
        if self.status == "contested" and not self.counter_evidence:
            raise ValueError("A contested Claim needs counter-evidence")
        return self


class AnalysisState(ContractModel):
    kind: Literal["analysis"] = "analysis"
    task: str = Field(min_length=1, max_length=4096)
    inputs: tuple[KnowledgeRef, ...] = Field(min_length=1)
    executor: str = Field(min_length=1, max_length=200)
    status: Literal["pending", "started", "no_change", "result", "interrupted", "error", "blocked"]
    conclusion: str | None = Field(default=None, max_length=16384)
    effects: tuple[KnowledgeRef, ...] = ()
    remainder: str | None = Field(default=None, max_length=8192)
    memory: MemoryMetadata | None = Field(default=None, exclude_if=lambda value: value is None)

    @model_validator(mode="after")
    def progress_is_explicit(self) -> AnalysisState:
        if self.status in ("no_change", "result") and not self.conclusion:
            raise ValueError("Completed analysis needs a conclusion")
        if self.status in ("started", "interrupted", "error", "blocked") and not self.remainder:
            raise ValueError("Unfinished analysis needs a remainder")
        return self


class MemoryLinkState(ContractModel):
    kind: Literal["link"] = "link"
    source: KnowledgeRef
    target: KnowledgeRef
    target_mode: Literal["exact", "current"] = "exact"
    relation: str = Field(min_length=1, max_length=120)
    basis: tuple[KnowledgeRef, ...] = Field(min_length=1)
    explanation: str = Field(min_length=1, max_length=4096)
    status: Literal["active", "retired"] = "active"
    memory: MemoryMetadata | None = Field(default=None, exclude_if=lambda value: value is None)


class MemorySelectionBasis(ContractModel):
    selectors: tuple[MemorySelector, ...] = Field(min_length=1)
    fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    actor: str = Field(min_length=1, max_length=200)
    epoch: int = Field(ge=1)
    rule_version: int = Field(default=1, ge=1)
    parts: tuple[KnowledgeRef, ...] = ()
    members: tuple[KnowledgeRef, ...] = ()
    query_members: tuple[KnowledgeRef, ...] | None = Field(
        default=None, exclude_if=lambda value: value is None
    )
    total_bytes: int = Field(default=0, ge=0)
    cache: bool = False
    restricted: bool = False


class MemoryViewState(ContractModel):
    kind: Literal["view"] = "view"
    purpose: str = Field(min_length=1, max_length=500)
    scope: str = Field(min_length=1, max_length=500)
    scope_kind: Literal["space", "conversation", "activity", "work"]
    scope_id: str | None = Field(default=None, max_length=300)
    generation_method: str = Field(min_length=1, max_length=500)
    mode: Literal["historical", "current"]
    sources: tuple[KnowledgeRef, ...]
    text: str = Field(min_length=1, max_length=65536)
    coverage_state_revision: int = Field(ge=0)
    limitations: tuple[str, ...] = ()
    memory: MemoryMetadata | None = Field(default=None, exclude_if=lambda value: value is None)
    selection: MemorySelectionBasis | None = Field(
        default=None, exclude_if=lambda value: value is None
    )

    @model_validator(mode="after")
    def addressed_scope(self) -> MemoryViewState:
        if not self.sources and self.selection is None:
            raise ValueError("A regular view requires exact sources")
        if self.selection is not None and not set(
            self.selection.members + self.selection.parts
        ).issubset(set(self.sources)):
            raise ValueError("Selection members and parts require structural source links")
        if (self.scope_kind == "space") != (self.scope_id is None):
            raise ValueError("A scoped view needs its exact scope address")
        if self.scope_id is not None and not self.scope_id:
            raise ValueError("A scoped view needs a nonempty address")
        if self.scope_kind in ("activity", "work") and self.scope_id is not None:
            scoped_record = UUID(self.scope_id)
            if self.mode == "current" and scoped_record not in {
                ref.record_id for ref in self.sources
            }:
                raise ValueError("Current scoped view must include its Core original")
        return self


class ContextState(ContractModel):
    kind: Literal["context"] = "context"
    purpose: str = Field(min_length=1, max_length=4096)
    session_id: UUID
    work_id: UUID | None = None
    attempt_id: UUID | None = None
    method: MethodRef | None = None
    plan_revision: int | None = Field(default=None, ge=1)
    mandatory: tuple[KnowledgeRef, ...] = ()
    optional: tuple[KnowledgeRef, ...] = ()
    historical_memory: tuple[KnowledgeRef, ...] = Field(
        default=(), exclude_if=lambda value: not value
    )
    pinned_structure: KnowledgeRef | None = Field(
        default=None, exclude_if=lambda value: value is None
    )
    procedure_snapshot: KnowledgeRef | None = Field(
        default=None, exclude_if=lambda value: value is None
    )
    limits: tuple[str, ...] = ()
    max_bytes: int | None = Field(default=None, ge=1)


class HandoffState(ContractModel):
    kind: Literal["handoff"] = "handoff"
    subject: str = Field(min_length=1, max_length=4096)
    document: bytes = Field(min_length=1, max_length=8 * 1024 * 1024)
    media_type: str = Field(min_length=1, max_length=200)
    included: tuple[KnowledgeRef, ...] = ()
    expected_return: str = Field(min_length=1, max_length=2048)
    status: Literal["prepared", "reported_sent", "delivered", "returned", "matched"]
    transfer_source: KnowledgeRef | None = None
    return_source: KnowledgeRef | None = None
    match_basis: str | None = Field(default=None, max_length=4096)
    basis_state_revision: int = Field(ge=0)
    memory: MemoryMetadata | None = Field(default=None, exclude_if=lambda value: value is None)

    @model_validator(mode="after")
    def stages_need_separate_evidence(self) -> HandoffState:
        if self.status == "prepared" and (
            self.transfer_source is not None or self.return_source is not None or self.match_basis
        ):
            raise ValueError("Prepared document has no transfer or return evidence")
        if self.status != "prepared" and self.transfer_source is None:
            raise ValueError("Transfer needs an exact report or receipt")
        if self.status in ("returned", "matched") and self.return_source is None:
            raise ValueError("A returned document needs a separate source")
        if self.status == "matched" and not self.match_basis:
            raise ValueError("Matching needs an explicit basis")
        return self


class DataField(ContractModel):
    """Finite declarative field tree; never executable schema code."""

    key: Identifier
    meaning: str = Field(min_length=1, max_length=2048)
    type: Literal[
        "text", "boolean", "integer", "decimal", "date", "datetime", "enum", "ref", "object", "list"
    ]
    required: bool = True
    unknown_allowed: bool = False
    unit: str | None = None
    precision: int | None = Field(default=None, ge=0)
    minimum: str | None = None
    maximum: str | None = None
    choices: tuple[str, ...] = ()
    fields: tuple[DataField, ...] = ()
    item: DataField | None = None
    indexed: bool = False

    @model_validator(mode="after")
    def supported_shape(self) -> DataField:
        if (self.type == "object") != bool(self.fields):
            raise ValueError("Object fields require exactly their declared children")
        if (self.type == "list") != (self.item is not None):
            raise ValueError("List fields require exactly one item definition")
        if (self.type == "enum") != bool(self.choices):
            raise ValueError("Enums require explicit choices")
        if len({field.key for field in self.fields}) != len(self.fields):
            raise ValueError("Field keys must be unique")
        if self.indexed and self.type in ("object", "list"):
            raise ValueError("Only declared scalar fields can be indexed")
        if self.precision is not None and self.type != "decimal":
            raise ValueError("Precision is a decimal contract")
        return self


class DataFormatState(ContractModel):
    kind: Literal["data_format"] = "data_format"
    language_version: Literal[1] = 1
    title: str = Field(min_length=1, max_length=500)
    scope_activity_id: UUID | None = None
    role: Literal["object", "event", "plan", "document", "analysis"]
    fields: tuple[DataField, ...] = Field(min_length=1)
    statuses: tuple[str, ...] = ("recorded",)
    identity_fields: tuple[Identifier, ...] = ()
    time_field: Identifier | None = None
    memory: MemoryMetadata | None = Field(default=None, exclude_if=lambda value: value is None)

    @model_validator(mode="after")
    def addressable_fields(self) -> DataFormatState:
        keys = {field.key for field in self.fields}
        if len(keys) != len(self.fields):
            raise ValueError("Format keys must be unique")
        if not set(self.identity_fields).issubset(keys) or (
            self.time_field is not None and self.time_field not in keys
        ):
            raise ValueError("Identity/time fields must be declared")
        if self.time_field is not None and next(
            field.type for field in self.fields if field.key == self.time_field
        ) not in ("date", "datetime"):
            raise ValueError("Time field must be date or timezone-aware datetime")
        return self


class DataReference(ContractModel):
    record_id: UUID
    mode: Literal["exact", "current"] = "exact"
    revision: int | None = Field(default=None, ge=1)

    @model_validator(mode="after")
    def exact_has_revision(self) -> DataReference:
        if (self.mode == "exact") != (self.revision is not None):
            raise ValueError("An exact relation requires revision; current resolves at reading")
        return self


class DataEntryState(ContractModel):
    kind: Literal["data_entry"] = "data_entry"
    scope_activity_id: UUID | None = None
    format_ref: KnowledgeRef
    structure: KnowledgeRef | None = None
    role: Literal["object", "event", "plan", "document", "analysis"]
    values: dict[str, JsonValue]
    bases: tuple[KnowledgeRef, ...] = Field(min_length=1)
    event_date: date | None = None
    event_at: AwareDatetime | None = None
    period_from: date | None = None
    period_until: date | None = None
    timezone: str | None = None
    status: str = "recorded"
    external_namespace: str | None = None
    external_key: str | None = None
    complete: bool = True
    limitations: tuple[str, ...] = ()
    explanation: str | None = None
    work_id: UUID | None = None
    attempt_id: UUID | None = None
    session_id: UUID | None = None
    selection: KnowledgeRef | None = None
    memory: MemoryMetadata | None = Field(default=None, exclude_if=lambda value: value is None)

    @model_validator(mode="after")
    def honest_identity_and_period(self) -> DataEntryState:
        if (self.external_namespace is None) != (self.external_key is None):
            raise ValueError("External identity requires namespace and key together")
        if (self.period_from is None) != (self.period_until is None) or (
            self.period_from is not None
            and self.period_until is not None
            and self.period_from >= self.period_until
        ):
            raise ValueError("Period is ordered and end-exclusive")
        if self.attempt_id is not None and self.work_id is None:
            raise ValueError("Attempt effects require Work")
        if (self.attempt_id is None) != (self.session_id is None):
            raise ValueError("Attempt effect requires its session")
        if not self.complete and not self.limitations:
            raise ValueError("Incomplete data must explain what is unknown")
        return self


class ProcedureDefinition(ContractModel):
    key: Identifier
    purpose: str = Field(min_length=1, max_length=4096)
    parameters: tuple[DataField, ...] = ()
    inputs: tuple[MemorySelector, ...] = ()
    operations: tuple[str, ...] = ()
    goal: str = Field(min_length=1, max_length=4096)
    outputs: tuple[OutputContract, ...] = Field(min_length=1)
    method: MethodRef | None = None
    input_slot: Identifier | None = None
    plan: WorkPlan | None = None
    trigger: Literal["manual", "event", "period"] = "manual"
    period: Literal["day", "week", "month"] | None = None
    timezone: str | None = None
    autonomy: Literal["propose", "run"] = "propose"
    resource: Literal["workspace", "project"] = "workspace"
    project: str | None = None

    @model_validator(mode="after")
    def executable_contract(self) -> ProcedureDefinition:
        if (self.method is None) != (self.plan is None):
            raise ValueError("Method procedure requires its ordinary composite plan")
        if self.trigger == "period" and (self.period is None or self.timezone is None):
            raise ValueError("Period trigger requires calendar and timezone")
        if (self.resource == "project") != (self.project is not None):
            raise ValueError("Project resource requires a registered project name")
        if len({field.key for field in self.parameters}) != len(self.parameters):
            raise ValueError("Parameter keys must be unique")
        return self


class WorkingSet(ContractModel):
    key: Identifier
    purpose: str
    selectors: tuple[MemorySelector, ...] = Field(min_length=1)
    cardinality: Literal["one", "many"] = "many"


class ActivityStructureState(ContractModel):
    kind: Literal["activity_structure"] = "activity_structure"
    contract_version: Literal[1] = 1
    scope_activity_id: UUID
    title: str
    goal: str
    instructions: str
    first_action: str
    process: str
    workflows: tuple[WorkflowRef, ...] = Field(default=(), exclude_if=lambda v: not v)
    formats: dict[str, KnowledgeRef] = {}
    procedures: tuple[ProcedureDefinition, ...] = ()
    working_sets: tuple[WorkingSet, ...] = ()
    memory_requirements: tuple[MemoryRequirement, ...] = ()
    bases: tuple[KnowledgeRef, ...] = Field(min_length=1)
    extensions: tuple[str, ...] = ()
    deferred_questions: tuple[str, ...] = ()
    memory: MemoryMetadata | None = Field(default=None, exclude_if=lambda value: value is None)

    @model_validator(mode="after")
    def unique_components(self) -> ActivityStructureState:
        for items in (self.procedures, self.working_sets):
            if len({item.key for item in items}) != len(items):
                raise ValueError("Structure component keys must be unique")
        return self


class StructureChange(ContractModel):
    kind: Literal["structure"] = "structure"
    change_id: UUID
    activity_id: UUID
    expected_structure: KnowledgeRef | None = None
    manifest: ArtifactRef
    to_version: Literal[1] = 1


class DataOutputEnvelope(ContractModel):
    contract_version: Literal[1] = 1
    entries: tuple[KnowledgeRef, ...] = ()
    basis_snapshot: KnowledgeRef | None = None
    complete: bool
    limitations: tuple[str, ...] = ()
    result: str = Field(min_length=1)


class ResultValidationIssue(ContractModel):
    """An addressed new-result diagnostic without retaining rejected input values."""

    code: str = Field(min_length=1, max_length=100)
    path: tuple[str | int, ...] = ()
    message: str = Field(min_length=1, max_length=2048)
    allowed_values: tuple[str, ...] = ()


class DataMutation(ContractModel):
    record_id: UUID
    expected_revision: int | None = Field(default=None, ge=1)
    state: DataEntryState


class IntakeElement(ContractModel):
    key: str = Field(min_length=1, max_length=500)
    status: Literal["saved", "deferred", "rejected"]
    mutation: DataMutation | None = None
    reason: str | None = None

    @model_validator(mode="after")
    def explicit_outcome(self) -> IntakeElement:
        if (self.status == "saved") != (self.mutation is not None):
            raise ValueError("Saved intake element needs its mutation")
        if self.status != "saved" and not self.reason:
            raise ValueError("Unprocessed elements need a reason")
        return self


class IngestDataRequest(OperationRequest):
    kind: Literal["ingest_data"] = "ingest_data"
    source: KnowledgeRef
    delivery_key: str = Field(min_length=1, max_length=500)
    elements: tuple[IntakeElement, ...]
    complete: bool = False


class PrepareProcedureRequest(OperationRequest):
    kind: Literal["prepare_procedure"] = "prepare_procedure"
    activity_id: UUID
    procedure: Identifier
    request_key: str = Field(min_length=1, max_length=500)
    structure: KnowledgeRef
    parameters: dict[str, JsonValue] = {}
    request_basis: tuple[KnowledgeRef, ...] = ()
    rerun_of: UUID | None = None
    period_from: date | None = None
    period_until: date | None = None


class StartProcedureRequest(OperationRequest):
    kind: Literal["start_procedure"] = "start_procedure"
    activity_id: UUID
    procedure: Identifier
    request_key: str = Field(min_length=1, max_length=500)
    structure: KnowledgeRef
    parameters: dict[str, JsonValue] = {}
    request_basis: tuple[KnowledgeRef, ...] = ()
    rerun_of: UUID | None = None
    snapshot: KnowledgeRef
    period_from: date | None = None
    period_until: date | None = None


class SleepSelection(ContractModel):
    source: KnowledgeRef
    purpose: Literal["consolidation", "exploration"]
    analysis_id: UUID | None = None


class SleepDelivery(ContractModel):
    source: KnowledgeRef
    manifest: KnowledgeRef
    invocation_id: UUID
    stage: Literal["prepared", "sent", "answered", "unknown"]


class SleepEffect(ContractModel):
    operation_id: UUID
    result: KnowledgeRef


class SleepRemainder(ContractModel):
    kind: Literal["selected", "new_intake", "question", "stored_source"]
    description: str = Field(min_length=1, max_length=4096)
    source: KnowledgeRef | None = None
    return_condition: str | None = Field(default=None, max_length=2048)


class SleepState(ContractModel):
    """Saved analysis of one ordinary Work; Work owns execution state."""

    kind: Literal["sleep"] = "sleep"
    work_id: UUID
    method: MethodRef
    scope_activity_ids: tuple[UUID, ...]
    include_free_conversation: bool = True
    intake_cutoff_revision: int = Field(ge=0)
    enumeration_cursor_revision: int = Field(default=0, ge=0)
    enumeration_cursor_id: UUID | None = None
    exploration_cursor_revision: int = Field(default=0, ge=0)
    exploration_cursor_id: UUID | None = None
    selected: tuple[SleepSelection, ...] = ()
    deliveries: tuple[SleepDelivery, ...] = ()
    analyses: tuple[KnowledgeRef, ...] = ()
    effects: tuple[SleepEffect, ...] = ()
    remainder: tuple[SleepRemainder, ...] = ()
    resource_limit_units: int | None = Field(default=None, ge=1)
    reserved_units: int = Field(default=0, ge=0)
    spent_units: int = Field(default=0, ge=0)
    consolidation: Literal["pending", "partial", "complete", "no_material"] = "pending"
    exploration: Literal["pending", "partial", "complete", "no_material"] = "pending"
    conclusion: str | None = Field(default=None, max_length=8192)
    stop_reason: str | None = Field(default=None, max_length=2048)

    @model_validator(mode="after")
    def bounded_and_addressed(self) -> SleepState:
        if (
            self.resource_limit_units is not None
            and self.spent_units + self.reserved_units > self.resource_limit_units
        ):
            raise ValueError("Sleep consumption exceeds its fixed resource")
        if self.enumeration_cursor_revision > self.intake_cutoff_revision:
            raise ValueError("Enumeration cannot pass its intake boundary")
        if (
            self.consolidation in ("complete", "no_material")
            and self.exploration in ("complete", "no_material")
            and not self.conclusion
        ):
            raise ValueError("Finished Sleep analysis needs a conclusion")
        return self


class ValidationCriterion(ContractModel):
    key: Identifier
    question: str = Field(min_length=1, max_length=4096)
    pass_condition: str = Field(min_length=1, max_length=4096)
    basis: tuple[KnowledgeRef, ...] = ()


class ValidationPlanState(ContractModel):
    baseline: str = Field(min_length=1, max_length=4096)
    environment: str = Field(min_length=1, max_length=4096)
    criteria: tuple[ValidationCriterion, ...] = Field(min_length=1)
    cases: str = Field(min_length=1, max_length=8192)
    method: str = Field(min_length=1, max_length=4096)
    sufficiency: str = Field(min_length=1, max_length=4096)
    limits: str = Field(min_length=1, max_length=4096)
    stop_and_restore: str = Field(min_length=1, max_length=4096)
    decision_condition: str = Field(min_length=1, max_length=4096)
    follow_up: str = Field(min_length=1, max_length=4096)


class ValidationResultState(ContractModel):
    result_id: UUID
    criterion: Identifier
    outcome: Literal["met", "not_met", "undetermined"]
    evidence: tuple[KnowledgeRef, ...]
    actual_input: str = Field(min_length=1, max_length=4096)
    environment: str = Field(min_length=1, max_length=4096)
    limitations: str | None = Field(default=None, max_length=4096)
    manifest: KnowledgeRef | None = None
    trial_work_id: UUID | None = None

    @model_validator(mode="after")
    def observed_result_has_evidence(self) -> ValidationResultState:
        if self.outcome != "undetermined" and not self.evidence:
            raise ValueError("Observed validation needs saved evidence")
        return self


class WorkflowRef(ContractModel):
    workflow_id: UUID
    version: int = Field(ge=1)
    checksum: str = Field(pattern=r"^[0-9A-F]{64}$")


class WorkflowModel(ContractModel):
    provider: str = Field(min_length=1, max_length=100)
    model_id: str = Field(min_length=1, max_length=200)
    profile: str = Field(min_length=1, max_length=100)
    reasoning: str = Field(min_length=1, max_length=50)


class WorkflowNode(ContractModel):
    key: Identifier
    kind: Literal["model", "question", "external", "core", "nested"]
    instruction: str = Field(min_length=1, max_length=16384)
    method: MethodRef | None = None
    plan: WorkPlan | None = None
    input_slot: Identifier | None = None
    inputs: tuple[NamedInput, ...] = ()
    dependencies: tuple[Identifier, ...] = ()
    successors: tuple[Identifier, ...] = ()
    max_iterations: int = Field(default=1, ge=1, le=100)
    result_fields: tuple[DataField, ...] = ()
    operation: str | None = None
    operation_arguments: dict[str, JsonValue] = Field(default_factory=dict)
    workflow: WorkflowRef | None = None
    resource: Literal["workspace", "project"] = "workspace"
    project: str | None = None
    result_protocol: Literal["workflow_json", "setup_draft", "setup_review"] = "workflow_json"
    allowed_actions: tuple[
        Literal["core_read", "project_read", "project_write", "project_command"], ...
    ] = ("core_read",)

    @model_validator(mode="after")
    def executable_node(self) -> WorkflowNode:
        if (
            any(action != "core_read" for action in self.allowed_actions)
            and self.resource != "project"
        ):
            raise ValueError("Project actions require a selected project resource")
        if self.result_protocol != "workflow_json" and self.allowed_actions != ("core_read",):
            raise ValueError("Setup stages allow only their declared Core reads")
        if (self.method is None) != (self.plan is None):
            raise ValueError("A Method node requires its exact composite plan")
        if (self.kind == "core") != (self.operation is not None):
            raise ValueError("A core node names its registered operation")
        if (self.kind == "nested") != (self.workflow is not None):
            raise ValueError("A nested node names its exact workflow")
        if (self.resource == "project") != (self.project is not None):
            raise ValueError("Project nodes need a registered project")
        if len(set(self.dependencies)) != len(self.dependencies) or len(
            set(self.successors)
        ) != len(self.successors):
            raise ValueError("Workflow edges must be unique")
        return self


class WorkflowDefinition(ContractModel):
    contract_version: Literal[1] = 1
    title: str = Field(min_length=1, max_length=200)
    purpose: str = Field(min_length=1, max_length=4096)
    inputs: tuple[OutputContract, ...] = ()
    outputs: tuple[OutputContract, ...] = (
        OutputContract(slot="report", media_type="application/json"),
    )
    nodes: tuple[WorkflowNode, ...] = Field(min_length=1, max_length=100)
    entry_nodes: tuple[Identifier, ...] = Field(min_length=1)
    allowed_operations: tuple[str, ...] = ()
    allowed_action_classes: tuple[
        Literal["core_read", "project_read", "project_write", "project_command"], ...
    ] = ("core_read",)

    @model_validator(mode="after")
    def valid_graph_template(self) -> WorkflowDefinition:
        if (
            len(self.outputs) != 1
            or self.outputs[0].slot != "report"
            or self.outputs[0].media_type not in ("application/json", "text/plain")
            or self.outputs[0].format_ref is not None
        ):
            raise ValueError(
                "Workflow root declares one JSON or text report; typed data is a node effect"
            )
        keys = {node.key for node in self.nodes}
        if len(keys) != len(self.nodes) or not set(self.entry_nodes).issubset(keys):
            raise ValueError("Workflow nodes and entry addresses must be exact and unique")
        for node in self.nodes:
            if not set(node.allowed_actions).issubset(set(self.allowed_action_classes)):
                raise ValueError("Node actions exceed the workflow contract")
            if not set(node.dependencies + node.successors).issubset(keys):
                raise ValueError("Workflow edge names an absent node")
            if node.operation is not None and node.operation not in self.allowed_operations:
                raise ValueError("Core node operation is outside the definition")
        # Readiness is acyclic. Bounded successor loops materialize fresh Work iterations.
        visiting: set[str] = set()
        visited: set[str] = set()

        def visit(key: str) -> None:
            if key in visiting:
                raise ValueError("Workflow readiness cannot contain cycles")
            if key in visited:
                return
            visiting.add(key)
            for dependency in next(node for node in self.nodes if node.key == key).dependencies:
                visit(dependency)
            visiting.remove(key)
            visited.add(key)

        for key in keys:
            visit(key)
        return self


class WorkflowChange(ContractModel):
    kind: Literal["workflow"] = "workflow"
    workflow_id: UUID
    from_version: int | None = Field(default=None, ge=1)
    to_version: int = Field(ge=1)
    definition: WorkflowDefinition

    @model_validator(mode="after")
    def consecutive_version(self) -> WorkflowChange:
        if self.to_version != (self.from_version or 0) + 1:
            raise ValueError("Workflow versions must be consecutive")
        return self


class WorkflowNodeResult(ContractModel):
    outcome: Literal["result", "question", "external", "obstacle"]
    values: dict[str, JsonValue] = Field(default_factory=dict)
    question: str | None = None
    purpose: str | None = None
    next_nodes: tuple[Identifier, ...] = ()
    explanation: str | None = None

    @model_validator(mode="after")
    def honest_outcome(self) -> WorkflowNodeResult:
        if self.outcome in ("question", "external") and (not self.question or not self.purpose):
            raise ValueError("An interaction needs its exact question and purpose")
        if self.outcome == "obstacle" and not self.explanation:
            raise ValueError("An obstacle needs a concrete explanation")
        return self


class WorkflowWait(ContractModel):
    wait_id: UUID
    node_key: str
    work_id: UUID
    revision: int
    kind: Literal["question", "external"]
    question: str
    purpose: str
    expected_actor: str
    bases: tuple[KnowledgeRef, ...] = ()
    answer: KnowledgeRef | None = None
    root_work_id: UUID | None = Field(default=None, exclude_if=lambda v: v is None)
    native: bool = Field(default=False, exclude_if=lambda value: not value)
    attempt_id: UUID | None = Field(default=None, exclude_if=lambda value: value is None)
    session_id: UUID | None = Field(default=None, exclude_if=lambda value: value is None)


class WorkflowNodeView(ContractModel):
    key: str
    iteration: int
    role: str
    work_id: UUID
    packet: ArtifactRef
    model: WorkflowModel | None = None
    output: ArtifactRef | None = None
    validation_id: UUID | None = None
    issues: tuple[SetupValidationIssue, ...] = ()
    retired: bool = False


class WorkflowRunView(ContractModel):
    root_work_id: UUID
    revision: int
    workflow: WorkflowRef
    activity_id: UUID
    nodes: tuple[WorkflowNodeView, ...]
    waits: tuple[WorkflowWait, ...]
    ready_nodes: tuple[str, ...]
    next_action: Literal["run", "answer", "resume", "attention", "finish", "closed", "owner_action"]
    explanation: str
    control: Literal["running", "paused", "cancelled"]
    diagnostics: tuple[ArtifactRef, ...] = ()


class WorkflowRequest(OperationRequest):
    kind: Literal["workflow"] = "workflow"
    action: Literal[
        "create_definition",
        "start",
        "bind_node",
        "validate_output",
        "ask",
        "answer",
        "advance",
        "pause",
        "resume",
        "cancel",
        "migrate",
        "attention",
        "finish",
        "correct_answer",
        "retry",
    ]
    workflow: WorkflowRef | None = None
    workflow_id: UUID | None = None
    version: int = Field(default=1, ge=1)
    definition: WorkflowDefinition | None = None
    root_work_id: UUID | None = None
    activity_id: UUID | None = None
    expected_revision: int | None = Field(default=None, ge=1)
    node_key: str | None = None
    iteration: int | None = Field(default=None, ge=1)
    model: WorkflowModel | None = None
    source_refs: tuple[KnowledgeRef, ...] = ()
    inputs: tuple[NamedInput, ...] = ()
    output: ArtifactRef | None = None
    wait_id: UUID | None = None
    expected_wait_revision: int | None = Field(default=None, ge=1)
    question: str | None = None
    purpose: str | None = None
    interaction_kind: Literal["question", "external"] = "question"
    answer: KnowledgeRef | None = None
    next_nodes: tuple[str, ...] = ()
    node_mapping: dict[str, str] = Field(default_factory=dict)
    node_dispositions: dict[str, Literal["keep", "replace", "retire"]] = Field(default_factory=dict)
    text: str | None = None
    code: str | None = None


class SetupInteraction(ContractModel):
    interaction_id: UUID
    question: str
    input_version: int
    sources: tuple[KnowledgeRef, ...] = ()
    answer: KnowledgeRef | None = None


class MethodChange(ContractModel):
    kind: Literal["method"] = "method"
    method_id: UUID
    from_version: int | None = Field(default=None, ge=1)
    from_checksum: str | None = Field(default=None, pattern=r"^[0-9A-F]{64}$")
    to_version: int = Field(ge=1)
    definition: MethodDefinition

    @model_validator(mode="after")
    def exact_previous(self) -> MethodChange:
        if (self.from_version is None) != (self.from_checksum is None):
            raise ValueError("Previous Method needs version and checksum together")
        if self.to_version != (self.from_version or 0) + 1:
            raise ValueError("Method versions must be consecutive")
        return self


class BindingChange(ContractModel):
    kind: Literal["binding"] = "binding"
    binding_id: UUID
    from_version: int | None = Field(default=None, ge=1)
    from_checksum: str | None = Field(default=None, pattern=r"^[0-9A-F]{64}$")
    to_version: int = Field(ge=1)
    definition: BindingDefinition

    @model_validator(mode="after")
    def exact_previous(self) -> BindingChange:
        if (self.from_version is None) != (self.from_checksum is None):
            raise ValueError("Previous Binding needs version and checksum together")
        if self.to_version != (self.from_version or 0) + 1:
            raise ValueError("Binding versions must be consecutive")
        return self


class ProgramChange(ContractModel):
    """An exact managed build destined for one selected working resource file."""

    kind: Literal["program"] = "program"
    program_id: UUID
    resource_id: UUID
    resource_revision: int = Field(ge=1)
    relative_path: str = Field(min_length=1, max_length=1024)
    from_version: int | None = Field(default=None, ge=1)
    from_checksum: str | None = Field(default=None, pattern=r"^[0-9A-F]{64}$")
    from_build: ArtifactRef | None = None
    to_version: int = Field(ge=1)
    build: ArtifactRef
    build_sha256: str = Field(pattern=r"^[0-9A-F]{64}$")
    required_validation_keys: tuple[Identifier, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def exact_build_and_path(self) -> ProgramChange:
        from pathlib import PurePosixPath

        parts = PurePosixPath(self.relative_path).parts
        if (
            not parts
            or self.relative_path.startswith(("/", chr(92)))
            or chr(92) in self.relative_path
            or ":" in self.relative_path
            or any(part in (".", "..") for part in parts)
            or PurePosixPath(self.relative_path).as_posix() != self.relative_path
        ):
            raise ValueError("Program path must be relative and remain inside its resource")
        if (
            len({self.from_version is None, self.from_checksum is None, self.from_build is None})
            != 1
        ):
            raise ValueError("Previous program needs version, checksum and build together")
        if self.to_version != (self.from_version or 0) + 1:
            raise ValueError("Program versions must be consecutive")
        if self.from_checksum == self.build_sha256:
            raise ValueError("Program build must change exact bytes")
        if len(self.required_validation_keys) != len(set(self.required_validation_keys)):
            raise ValueError("Program prerequisites must be unique")
        return self


ChangePart = Annotated[MethodChange | BindingChange | ProgramChange, Field(discriminator="kind")]


class CompositeChange(ContractModel):
    """A single admission for multiple exact dependent changes."""

    kind: Literal["composite"] = "composite"
    package_id: UUID
    from_version: int | None = Field(default=None, ge=1)
    to_version: int = Field(ge=1)
    parts: tuple[ChangePart, ...] = Field(min_length=2)

    @model_validator(mode="after")
    def unique_parts(self) -> CompositeChange:
        if self.to_version != (self.from_version or 0) + 1:
            raise ValueError("Composite versions must be consecutive")
        keys = [
            (item.kind, item.method_id if isinstance(item, MethodChange) else item.binding_id)
            if not isinstance(item, ProgramChange)
            else (item.kind, item.program_id)
            for item in self.parts
        ]
        if len(keys) != len(set(keys)):
            raise ValueError("Composite targets must be unique")
        paths = [
            (item.resource_id, item.relative_path.casefold())
            for item in self.parts
            if isinstance(item, ProgramChange)
        ]
        if len(paths) != len(set(paths)):
            raise ValueError("Composite program paths must be unique")
        return self


class ActivityChange(ContractModel):
    """An exact, admitted reorganization of current Activity membership."""

    kind: Literal["activity"] = "activity"
    change_id: UUID
    from_version: int | None = None
    to_version: Literal[1] = 1
    creations: tuple[ActivityCreation, ...] = ()
    revisions: tuple[ActivityRevisionChange, ...] = ()
    moves: tuple[WorkActivityMove, ...] = ()
    rationale: str = Field(min_length=1, max_length=4096)
    binding_disposition: str = Field(min_length=1, max_length=4096)
    decision_disposition: str = Field(min_length=1, max_length=4096)
    grant_disposition: str = Field(min_length=1, max_length=4096)
    event_boundary: str = Field(min_length=1, max_length=4096)

    @model_validator(mode="after")
    def valid_reorganization(self) -> ActivityChange:
        if self.from_version is not None:
            raise ValueError("Each Activity reorganization has one exact version")
        created = [item.activity_id for item in self.creations]
        revised = [item.activity_id for item in self.revisions]
        moved = [item.work_id for item in self.moves]
        if not (created or revised or moved):
            raise ValueError("Activity change needs a real reorganization")
        if len(created) != len(set(created)) or len(revised) != len(set(revised)):
            raise ValueError("Activity addresses must be unique")
        if set(created) & set(revised) or len(moved) != len(set(moved)):
            raise ValueError("Activity change targets overlap")
        return self


ChangeTarget = Annotated[
    MethodChange
    | BindingChange
    | ProgramChange
    | CompositeChange
    | ActivityChange
    | StructureChange
    | WorkflowChange,
    Field(discriminator="kind"),
]


class ChangeCandidateState(ContractModel):
    kind: Literal["candidate"] = "candidate"
    target: ChangeTarget
    proposal: str = Field(min_length=1, max_length=8192)
    evidence: tuple[KnowledgeRef, ...] = ()
    counter_evidence: tuple[KnowledgeRef, ...] = ()
    expected_outcome: str = Field(min_length=1, max_length=4096)
    scope_activity_ids: tuple[UUID, ...] = ()
    scope_global: bool = False
    exclusions: str = Field(min_length=1, max_length=4096)
    impact: str = Field(min_length=1, max_length=8192)
    affected_work_ids: tuple[UUID, ...] = ()
    unknowns: str = Field(min_length=1, max_length=4096)
    validation_plan: ValidationPlanState | None = None
    results: tuple[ValidationResultState, ...] = ()
    restore_plan: str = Field(min_length=1, max_length=4096)
    irreversible_effects: str = Field(min_length=1, max_length=4096)
    status: Literal["open", "deferred", "closed"] = "open"
    return_condition: str | None = Field(default=None, max_length=2048)

    @model_validator(mode="after")
    def clear_scope_and_results(self) -> ChangeCandidateState:
        if self.scope_global == bool(self.scope_activity_ids):
            raise ValueError("Candidate needs one global or activity scope")
        criteria = self.validation_plan.criteria if self.validation_plan else ()
        keys = {item.key for item in criteria}
        if len(keys) != len(criteria):
            raise ValueError("Validation criteria must have unique keys")
        if any(item.criterion not in keys for item in self.results):
            raise ValueError("Results need a criterion in the saved plan")
        if len({item.result_id for item in self.results}) != len(self.results):
            raise ValueError("Validation result addresses must be unique")
        parts = self.target.parts if isinstance(self.target, CompositeChange) else (self.target,)
        required = {
            key
            for part in parts
            if isinstance(part, ProgramChange)
            for key in part.required_validation_keys
        }
        if self.validation_plan is not None and not required.issubset(keys):
            raise ValueError("Program prerequisites need criteria in the saved plan")
        return self


class CreateDevelopmentRequest(OperationRequest):
    kind: Literal["create_development"] = "create_development"
    record_id: UUID
    state: SleepState | ChangeCandidateState


class ReviseDevelopmentRequest(OperationRequest):
    kind: Literal["revise_development"] = "revise_development"
    record_id: UUID
    expected_revision: int = Field(ge=1)
    state: SleepState | ChangeCandidateState


class DeleteDevelopmentRequest(OperationRequest):
    kind: Literal["delete_development"] = "delete_development"
    record_id: UUID
    expected_revision: int = Field(ge=1)


class ApplyCandidateRequest(OperationRequest):
    kind: Literal["apply_candidate"] = "apply_candidate"
    candidate_id: UUID
    candidate_revision: int = Field(ge=1)
    decision_id: UUID
    decision_revision: int = Field(ge=1)
    mode: Literal["trial", "regular"]


class ConfirmProgramInstallRequest(OperationRequest):
    kind: Literal["confirm_program_install"] = "confirm_program_install"
    application_id: UUID
    expected_revision: int = Field(ge=1)


class StopCandidateRequest(OperationRequest):
    kind: Literal["stop_candidate"] = "stop_candidate"
    application_id: UUID
    expected_revision: int = Field(ge=1)
    reason: str = Field(min_length=1, max_length=4096)
    started_works: str = Field(min_length=1, max_length=4096)
    external_effects: str = Field(min_length=1, max_length=4096)


class RestoreCandidateRequest(OperationRequest):
    kind: Literal["restore_candidate"] = "restore_candidate"
    application_id: UUID
    expected_revision: int = Field(ge=1)
    reason: str = Field(min_length=1, max_length=4096)
    data_restoration: str = Field(min_length=1, max_length=4096)
    external_effects: str = Field(min_length=1, max_length=4096)


class RecordChangeOutcomeRequest(OperationRequest):
    kind: Literal["record_change_outcome"] = "record_change_outcome"
    application_id: UUID
    expected_revision: int = Field(ge=1)
    outcome: Literal["positive", "negative", "undetermined"]
    evidence: tuple[KnowledgeRef, ...] = ()
    observation: str = Field(min_length=1, max_length=8192)


KnowledgeBody = Annotated[
    SourceState
    | ClaimState
    | AnalysisState
    | MemoryLinkState
    | MemoryViewState
    | ContextState
    | HandoffState
    | DataFormatState
    | DataEntryState
    | ActivityStructureState,
    Field(discriminator="kind"),
]


class CreateKnowledgeRequest(OperationRequest):
    kind: Literal["create_knowledge"] = "create_knowledge"
    record_id: UUID
    state: KnowledgeBody


class ReviseKnowledgeRequest(OperationRequest):
    kind: Literal["revise_knowledge"] = "revise_knowledge"
    record_id: UUID
    expected_revision: int = Field(ge=1)
    state: KnowledgeBody


class DeleteKnowledgeRequest(OperationRequest):
    kind: Literal["delete_knowledge"] = "delete_knowledge"
    record_id: UUID
    expected_revision: int = Field(ge=1)


class RecordContextDeliveryRequest(OperationRequest):
    kind: Literal["record_context_delivery"] = "record_context_delivery"
    invocation_id: UUID
    manifest: KnowledgeRef
    stage: Literal["prepared", "sent", "answered", "unknown"]
    request_sha256: str | None = Field(default=None, pattern=r"^[0-9A-F]{64}$")
    request_bytes: int | None = Field(default=None, ge=0)
    free_call: bool = False
    reserve_units: int = Field(default=0, ge=0)
    usage_units: int | None = Field(default=None, ge=0)
    budget_limit_units: int | None = Field(default=None, ge=0)
    trial_total_send_limit: int | None = Field(default=None, ge=1)

    @model_validator(mode="after")
    def valid_accounting(self) -> RecordContextDeliveryRequest:
        if (
            self.stage == "prepared"
            and self.free_call
            and (
                self.reserve_units < 1
                or (
                    self.budget_limit_units is not None
                    and self.budget_limit_units < self.reserve_units
                )
            )
        ):
            raise ValueError("Free model calls need a bounded reserve")
        if (self.stage == "answered") != (self.usage_units is not None):
            raise ValueError("Only an answered call has confirmed usage")
        if self.stage == "sent" and (self.request_sha256 is None or self.request_bytes is None):
            raise ValueError("Sent request needs an observed body digest and size")
        return self


class KnowledgeRevision(ContractModel):
    record_id: UUID
    kind: Literal[
        "source",
        "claim",
        "analysis",
        "link",
        "view",
        "context",
        "handoff",
        "data_format",
        "data_entry",
        "activity_structure",
    ]
    revision: int = Field(ge=1)
    operation_id: UUID
    received_at: AwareDatetime
    created_at: AwareDatetime
    actor: str
    state: KnowledgeBody | None
    sha256: str | None
    availability: Literal["available", "unavailable", "deleted"]
    stale: bool = False


class DevelopmentRevision(ContractModel):
    record_id: UUID
    revision: int = Field(ge=1)
    operation_id: UUID
    actor: str
    created_at: AwareDatetime
    state: SleepState | ChangeCandidateState | None
    availability: Literal["available", "unavailable", "deleted"]


class ChangeApplication(ContractModel):
    application_id: UUID
    candidate_id: UUID
    candidate_revision: int = Field(ge=1)
    decision_id: UUID
    decision_revision: int = Field(ge=1)
    mode: Literal["trial", "regular"]
    target_kind: Literal[
        "method", "binding", "program", "composite", "activity", "structure", "workflow"
    ]
    target_id: UUID
    version: int = Field(ge=1)
    checksum: str = Field(pattern=r"^[0-9A-F]{64}$")
    status: Literal["prepared", "active", "stopped", "restored", "partial"]
    revision: int = Field(ge=1)
    created_at: AwareDatetime
    changed_at: AwareDatetime


SetupArea = Literal[
    "goal", "workflow", "history", "continuation", "extension", "capabilities", "consistency"
]


class SetupMethodTemplate(ContractModel):
    key: Identifier
    definition: MethodDefinition
    output_formats: dict[str, Identifier] = Field(
        default_factory=dict, exclude_if=lambda value: not value
    )


class SetupWorkTemplate(ContractModel):
    key: Identifier
    goal: str = Field(min_length=1, max_length=4096)
    method_key: Identifier | None = None
    expected_outputs: tuple[OutputContract, ...] = ()
    plan: WorkPlan | None = None
    output_formats: dict[str, Identifier] = Field(
        default_factory=dict, exclude_if=lambda value: not value
    )


class ActivitySetupDraft(ContractModel):
    title: str = Field(min_length=1, max_length=200)
    goal: str = Field(min_length=1, max_length=4096)
    instructions: str = Field(min_length=1, max_length=16384)
    methods: tuple[SetupMethodTemplate, ...] = ()
    works: tuple[SetupWorkTemplate, ...] = Field(min_length=1)
    memory: tuple[MemoryRequirement, ...] = ()
    extensions: tuple[str, ...] = ()
    open_questions: tuple[str, ...] = ()
    first_action: str = Field(min_length=1, max_length=4096)

    @model_validator(mode="after")
    def coherent_templates(self) -> ActivitySetupDraft:
        keys = [item.key for item in self.methods]
        if len(keys) != len(set(keys)) or len({item.key for item in self.works}) != len(self.works):
            raise ValueError("Setup template keys must be unique")
        for method in self.methods:
            if method.definition.required_capabilities or method.definition.role_methods:
                raise ValueError("Setup must use supported capabilities and self-contained Methods")
        for work in self.works:
            if work.method_key is not None and work.method_key not in keys:
                raise ValueError("Work template refers to a missing Method")
            if work.method_key is not None and work.plan is None:
                raise ValueError("Method Work requires its typed composite plan")
            if work.method_key is None and (work.plan is not None or not work.expected_outputs):
                raise ValueError("Plain Work requires outputs and cannot have a composite plan")
        return self


class SetupFinding(ContractModel):
    area: SetupArea
    problem: str = Field(min_length=1, max_length=4096)
    blocking: bool
    cause: str = Field(min_length=1, max_length=4096)


class SetupQuestion(ContractModel):
    text: str = Field(min_length=1, max_length=4096)
    blocking: bool
    scope: Literal["setup", "procedure", "none"] | None = Field(
        default=None, exclude_if=lambda v: v is None
    )
    procedure_key: Identifier | None = Field(default=None, exclude_if=lambda v: v is None)

    @model_validator(mode="after")
    def addressed_blocking_scope(self) -> SetupQuestion:
        if (self.scope == "procedure") != (self.procedure_key is not None):
            raise ValueError("A procedure-scoped question needs its procedure key")
        return self


class SetupFormatTemplate(ContractModel):
    key: Identifier
    definition: DataFormatState
    existing: KnowledgeRef | None = None


class SetupOutputTemplate(OutputContract):
    format_key: Identifier | None = None


class SetupProcedureTemplate(ContractModel):
    key: Identifier
    purpose: str = Field(min_length=1, max_length=4096)
    goal: str = Field(min_length=1, max_length=4096)
    parameters: tuple[DataField, ...] = ()
    inputs: tuple[MemorySelector, ...] = ()
    operations: tuple[ProcedureOperation, ...] = ()
    outputs: tuple[SetupOutputTemplate, ...] = Field(min_length=1)
    method_key: Identifier | None = None
    input_slot: Identifier | None = None
    plan: WorkPlan | None = None
    trigger: Literal["manual", "event", "period"] = "manual"
    period: Literal["day", "week", "month"] | None = None
    timezone: str | None = None
    autonomy: Literal["propose", "run"] = "propose"
    resource: Literal["workspace", "project"] = "workspace"
    project: str | None = None


class SetupDecisionBasis(ContractModel):
    subject: str = Field(min_length=1, max_length=4096)
    status: Literal["confirmed", "proposed", "unknown", "not_applicable"]
    explanation: str = Field(min_length=1, max_length=4096)
    sources: tuple[KnowledgeRef, ...] = ()


class ActivitySetupDraftV2(ContractModel):
    contract_version: Literal[2] = 2
    title: str = Field(min_length=1, max_length=200)
    goal: str = Field(min_length=1, max_length=4096)
    instructions: str = Field(min_length=1, max_length=16384)
    process: str = Field(min_length=1, max_length=16384)
    first_action: str = Field(min_length=1, max_length=4096)
    first_path: str = Field(min_length=1, max_length=8192)
    formats: tuple[SetupFormatTemplate, ...] = ()
    procedures: tuple[SetupProcedureTemplate, ...] = ()
    working_sets: tuple[WorkingSet, ...] = ()
    methods: tuple[SetupMethodTemplate, ...] = ()
    works: tuple[SetupWorkTemplate, ...] = ()
    memory: tuple[MemoryRequirement, ...] = ()
    decisions: tuple[SetupDecisionBasis, ...] = Field(min_length=1)
    extensions: tuple[str, ...] = ()
    questions: tuple[SetupQuestion, ...] = ()
    workflows: tuple[WorkflowDefinition, ...] = Field(default=(), exclude_if=lambda v: not v)

    @property
    def open_questions(self) -> tuple[str, ...]:
        return tuple(
            item.text
            for item in self.questions
            if item.blocking and item.scope not in ("procedure", "none")
        )

    @model_validator(mode="after")
    def coherent_package(self) -> ActivitySetupDraftV2:
        for components in (
            self.formats,
            self.procedures,
            self.methods,
            self.works,
            self.working_sets,
        ):
            keys = [item.key for item in components]
            if len(keys) != len(set(keys)):
                raise ValueError("Component keys must be unique")
        method_keys = {item.key for item in self.methods}
        format_keys = {item.key for item in self.formats}
        for procedure in self.procedures:
            if procedure.method_key is not None and procedure.method_key not in method_keys:
                raise ValueError("Procedure refers to an absent Method")
            if (procedure.method_key is None) != (procedure.plan is None):
                raise ValueError("Method procedure needs its exact composite plan")
            if any(
                output.format_key is not None and output.format_key not in format_keys
                for output in procedure.outputs
            ):
                raise ValueError("Procedure output refers to an absent format")
        for work in self.works:
            if work.method_key is not None and (
                work.method_key not in method_keys or work.plan is None
            ):
                raise ValueError("Work needs an existing Method key and exact plan")
            if work.method_key is None and (work.plan is not None or not work.expected_outputs):
                raise ValueError("Plain Work needs output contracts")
        return self


class SetupAreaEvidence(ContractModel):
    area: SetupArea
    explanation: str = Field(min_length=1, max_length=8192)
    components: tuple[str, ...] = Field(min_length=1)


class ActivitySetupReviewV2(ContractModel):
    contract_version: Literal[2] = 2
    draft: ArtifactRef
    manifest: ArtifactRef
    input_version: int = Field(ge=1)
    checked: tuple[SetupArea, ...]
    coverage: tuple[SetupAreaEvidence, ...]
    findings: tuple[SetupFinding, ...] = ()
    questions: tuple[SetupQuestion, ...] = ()
    conclusion: str = Field(min_length=1, max_length=4096)

    @property
    def unresolved(self) -> tuple[str, ...]:
        return tuple(
            item.text
            for item in self.questions
            if item.blocking and item.scope not in ("procedure", "none")
        )

    @model_validator(mode="after")
    def complete_review(self) -> ActivitySetupReviewV2:
        ActivitySetupReview(
            draft=self.draft,
            input_version=self.input_version,
            checked=self.checked,
            findings=self.findings,
            conclusion=self.conclusion,
        )
        if len(self.coverage) != 7 or {item.area for item in self.coverage} != set(self.checked):
            raise ValueError("Full review needs reasoned evidence for all seven areas")
        return self


class CompiledFormat(ContractModel):
    key: Identifier
    ref: KnowledgeRef
    definition: DataFormatState
    expected_revision: int | None = None
    create: bool = True


class ActivityActivationManifest(ContractModel):
    compiler_version: Literal[1] = 1
    setup_id: UUID
    activity_id: UUID
    draft: ArtifactRef
    input_version: int = Field(ge=1)
    previous_structure: KnowledgeRef | None = None
    previous_setup_id: UUID | None = None
    structure_expected_revision: int | None = Field(default=None, ge=1)
    formats: tuple[CompiledFormat, ...] = ()
    structure_ref: KnowledgeRef
    structure: ActivityStructureState
    method_definitions: dict[str, MethodDefinition] = Field(default_factory=dict)
    initial_works: tuple[SetupWorkTemplate, ...] = ()
    workflow_definitions: tuple[WorkflowDefinition, ...] = Field(
        default=(), exclude_if=lambda v: not v
    )


class ActivitySetupReview(ContractModel):
    draft: ArtifactRef
    input_version: int = Field(ge=1)
    checked: tuple[SetupArea, ...]
    findings: tuple[SetupFinding, ...] = ()
    unresolved: tuple[str, ...] = ()
    conclusion: str = Field(min_length=1, max_length=4096)

    @model_validator(mode="after")
    def complete_review(self) -> ActivitySetupReview:
        areas = {
            "goal",
            "workflow",
            "history",
            "continuation",
            "extension",
            "capabilities",
            "consistency",
        }
        if len(self.checked) != len(areas) or set(self.checked) != areas:
            raise ValueError("Review must cover every setup area exactly once")
        return self


class SetupValidationIssue(ContractModel):
    code: str = Field(min_length=1, max_length=100)
    path: tuple[str | int, ...] = ()
    message: str = Field(min_length=1, max_length=2048)
    allowed_values: tuple[str, ...] = ()


class SetupResultRejection(ContractModel):
    artifact: ArtifactRef
    issues: tuple[SetupValidationIssue, ...] = Field(min_length=1, max_length=16)
    fingerprint: str
    series_id: UUID


class SetupStage(ContractModel):
    work_id: UUID
    kind: Literal["draft", "correction", "review"]
    input_version: int = Field(ge=1)
    packet: ArtifactRef
    draft: ArtifactRef | None = None
    output: ArtifactRef | None = None
    review_pass: int = Field(default=0, ge=0)
    retired: bool = False
    result_protocol: Literal["setup_json"] | None = Field(
        default=None, exclude_if=lambda v: v is None
    )
    rejection: SetupResultRejection | None = Field(default=None, exclude_if=lambda v: v is None)
    repair_of: UUID | None = Field(default=None, exclude_if=lambda v: v is None)
    repair_series: UUID | None = Field(default=None, exclude_if=lambda v: v is None)
    repair_number: int = Field(default=0, ge=0, le=2, exclude_if=lambda v: v == 0)
    model: WorkflowModel | None = Field(default=None, exclude_if=lambda v: v is None)


class ActivitySetupState(ContractModel):
    activity_id: UUID
    owner: str
    authorization_scope: Literal["new_activity_setup", "activity_structure_change"] = (
        "new_activity_setup"
    )
    mode: Literal["create", "change_structure"] = Field(
        default="create", exclude_if=lambda v: v == "create"
    )
    contract_version: Literal[1, 2] = Field(default=1, exclude_if=lambda v: v == 1)
    previous_structure: KnowledgeRef | None = Field(default=None, exclude_if=lambda v: v is None)
    manifest: ArtifactRef | None = Field(default=None, exclude_if=lambda v: v is None)
    phase: Literal[
        "collecting",
        "drafting",
        "reviewing",
        "correcting",
        "needs_input",
        "paused",
        "needs_attention",
        "activating",
        "ready",
        "cancelled",
    ]
    sources: tuple[KnowledgeRef, ...] = Field(min_length=1)
    input_version: int = Field(default=1, ge=1)
    question: str | None = None
    draft: ArtifactRef | None = None
    review: ArtifactRef | None = None
    stages: tuple[SetupStage, ...] = ()
    reviews_started: int = Field(default=0, ge=0)
    reviews_completed: int = Field(default=0, ge=0)
    pass_boundary: int = Field(default=0, ge=0)
    auto_resume: bool = False
    repair_work: UUID | None = None
    result: str | None = None
    activated_works: tuple[UUID, ...] = ()
    activated_methods: tuple[MethodRef, ...] = ()
    recovery_boundary: int = Field(default=0, ge=0, exclude_if=lambda v: v == 0)
    workflow: WorkflowRef | None = Field(default=None, exclude_if=lambda v: v is None)
    root_work_id: UUID | None = Field(default=None, exclude_if=lambda v: v is None)
    interactions: tuple[SetupInteraction, ...] = Field(default=(), exclude_if=lambda v: not v)


class ActivitySetupRevision(ContractModel):
    setup_id: UUID
    revision: int = Field(ge=1)
    state: ActivitySetupState


class ActivitySetupRequest(OperationRequest):
    kind: Literal["activity_setup"] = "activity_setup"
    action: Literal[
        "begin",
        "answer",
        "question",
        "start_stage",
        "complete_stage",
        "pause",
        "resume",
        "cancel",
        "finish",
        "retry",
        "attention",
        "attach_sources",
        "migrate_workflow",
        "bind_model",
    ]
    setup_id: UUID
    activity_id: UUID
    expected_revision: int | None = Field(default=None, ge=1)
    title: str | None = Field(default=None, min_length=1, max_length=200)
    text: str | None = Field(default=None, min_length=1, max_length=32768)
    source_refs: tuple[KnowledgeRef, ...] = ()
    stage_kind: Literal["draft", "correction", "review"] | None = None
    stage_instruction: str | None = Field(default=None, min_length=1, max_length=4096)
    stage_model: WorkflowModel | None = Field(default=None, exclude_if=lambda v: v is None)
    auto_resume: bool = False
    output: ArtifactRef | None = None
    mode: Literal["create", "change_structure"] = Field(
        default="create", exclude_if=lambda v: v == "create"
    )
    contract_version: Literal[1, 2] = Field(default=1, exclude_if=lambda v: v == 1)


DomainRequest = Annotated[
    WorkflowRequest
    | IngestDataRequest
    | StartProcedureRequest
    | PrepareProcedureRequest
    | ActivitySetupRequest
    | BootstrapRequest
    | RecoverRequest
    | CreateBindingVersionRequest
    | SetBindingStateRequest
    | FireBindingRequest
    | ResolveBindingOfferRequest
    | CreateKnowledgeRequest
    | ReviseKnowledgeRequest
    | DeleteKnowledgeRequest
    | RecordContextDeliveryRequest
    | CreateDevelopmentRequest
    | ReviseDevelopmentRequest
    | DeleteDevelopmentRequest
    | ApplyCandidateRequest
    | ConfirmProgramInstallRequest
    | StopCandidateRequest
    | RestoreCandidateRequest
    | RecordChangeOutcomeRequest
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
    | ReorganizeActivitiesRequest
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
    schema_version: Literal[1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16]
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
    schema_version: Literal[1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16]
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
    "MemoryMetadata",
    "MemoryRequirement",
    "MemorySelector",
    "MemorySelectionBasis",
    "KnowledgeRef",
    "KnowledgeBody",
    "KnowledgeRevision",
    "SourceState",
    "ClaimState",
    "AnalysisState",
    "MemoryLinkState",
    "MemoryViewState",
    "ContextState",
    "HandoffState",
    "CreateKnowledgeRequest",
    "ReviseKnowledgeRequest",
    "DeleteKnowledgeRequest",
    "RecordContextDeliveryRequest",
    "BindingInputRevision",
    "BindingChildTemplate",
    "ActivitySetupRequest",
    "ActivitySetupRevision",
    "ActivitySetupState",
    "ActivitySetupDraft",
    "ActivitySetupReview",
    "SetupFinding",
    "SetupStage",
    "SetupWorkTemplate",
    "SetupMethodTemplate",
    "SetupArea",
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
    "ResultValidationIssue",
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

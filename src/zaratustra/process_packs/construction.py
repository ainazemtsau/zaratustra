"""Bounded immutable process definitions projected onto one focused Core Work."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Annotated, Literal, Self
from uuid import UUID

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    ValidationError,
    model_validator,
)

from zaratustra.core import InitialRecords, NextWork, PackReference, Work

from .lifecycle import PackRegistration

Text = Annotated[
    str, StringConstraints(strict=True, strip_whitespace=True, min_length=1, max_length=4096)
]
Key = Annotated[str, Field(strict=True, pattern="^[a-z][a-z0-9._-]{0,127}$")]

DEPENDENCIES = "zaratustra.graph.dependencies/v1"
PREDECESSOR_DATA = "zaratustra.graph.predecessor-data/v1"
OCCURRENCES = "zaratustra.graph.occurrences/v1"
SOURCE_REASONS = "zaratustra.graph.source-reasons/v1"
SUPPORTED_CAPABILITIES = frozenset((DEPENDENCIES, PREDECESSOR_DATA, OCCURRENCES, SOURCE_REASONS))
REQUIREMENT_KIND = "zaratustra.process-definition/v1"


class ConstructionError(ValueError):
    """A definition or snapshot cannot produce the claimed focused Work."""

    def __init__(self, code: str, detail: str) -> None:
        self.code = code
        super().__init__(f"{code}: {detail}")


class ConstructionModel(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", strict=True)


class SourceReference(ConstructionModel):
    source_id: Key
    kind: Literal["request", "research", "capability"]
    locator: Text


class Reason(ConstructionModel):
    text: Text
    source_ids: Annotated[tuple[Key, ...], Field(min_length=1)]

    @model_validator(mode="after")
    def unique_sources(self) -> Self:
        if len(set(self.source_ids)) != len(self.source_ids):
            raise ValueError("Reason source ids must be unique")
        return self


class Dependency(ConstructionModel):
    node_id: Key


class NodeDefinition(ConstructionModel):
    node_id: Key
    goal: Text
    expected_result: Text
    acceptance: Annotated[tuple[Text, ...], Field(min_length=1)]
    boundaries: Annotated[tuple[Text, ...], Field(min_length=1)]
    budget: Text
    artifact_title: Text
    output_keys: Annotated[tuple[Key, ...], Field(min_length=1)]
    dependencies: tuple[Dependency, ...] = ()
    recurring: bool = False
    reasons: Annotated[tuple[Reason, ...], Field(min_length=1)]

    @model_validator(mode="after")
    def unique_members(self) -> Self:
        if len(set(self.output_keys)) != len(self.output_keys):
            raise ValueError("Node output keys must be unique")
        dependency_ids = tuple(row.node_id for row in self.dependencies)
        if len(set(dependency_ids)) != len(dependency_ids):
            raise ValueError("Node dependencies must be unique")
        return self


class ProcessDefinition(ConstructionModel):
    definition_id: Key
    edition: Annotated[int, Field(strict=True, ge=1)]
    title: Text
    required_capabilities: Annotated[tuple[Text, ...], Field(min_length=1)]
    sources: Annotated[tuple[SourceReference, ...], Field(min_length=1)]
    nodes: Annotated[tuple[NodeDefinition, ...], Field(min_length=1)]

    @model_validator(mode="after")
    def coherent_graph(self) -> Self:
        if len(set(self.required_capabilities)) != len(self.required_capabilities):
            raise ValueError("Required capabilities must be unique")
        source_ids = tuple(row.source_id for row in self.sources)
        if len(set(source_ids)) != len(source_ids):
            raise ValueError("Definition source ids must be unique")
        node_ids = tuple(row.node_id for row in self.nodes)
        if len(set(node_ids)) != len(node_ids):
            raise ValueError("Definition node ids must be unique")
        known_sources = set(source_ids)
        known_nodes = set(node_ids)
        for node in self.nodes:
            dependencies = {row.node_id for row in node.dependencies}
            if node.node_id in dependencies:
                raise ValueError("Recurrence cannot be a dependency self-edge")
            if not dependencies <= known_nodes:
                raise ValueError("Dependency target is not a definition node")
            if any(not set(reason.source_ids) <= known_sources for reason in node.reasons):
                raise ValueError("Reason points outside definition sources")

        dependencies_by_node = {
            node.node_id: tuple(row.node_id for row in node.dependencies) for node in self.nodes
        }
        visiting: set[str] = set()
        visited: set[str] = set()

        def visit(node_id: str) -> None:
            if node_id in visiting:
                raise ValueError("Definition dependencies must be acyclic")
            if node_id in visited:
                return
            visiting.add(node_id)
            for predecessor in dependencies_by_node[node_id]:
                visit(predecessor)
            visiting.remove(node_id)
            visited.add(node_id)

        for node_id in node_ids:
            visit(node_id)
        return self


class DataValue(ConstructionModel):
    key: Key
    value: Text


class NodeResult(ConstructionModel):
    node_id: Key
    occurrence: Annotated[int, Field(strict=True, ge=1)]
    data: Annotated[tuple[DataValue, ...], Field(min_length=1)]


class ProcessSnapshot(ConstructionModel):
    definition: ProcessDefinition
    results: tuple[NodeResult, ...] = ()


class ResultGround(ConstructionModel):
    node_id: Key
    occurrence: Annotated[int, Field(strict=True, ge=1)]
    data: tuple[DataValue, ...]
    result_sha256: Annotated[str, Field(strict=True, pattern="^[0-9a-f]{64}$")]


class ReadyWork(ConstructionModel):
    node: NodeDefinition
    occurrence: Annotated[int, Field(strict=True, ge=1)]
    grounds: tuple[ResultGround, ...]


class BlockedWork(ConstructionModel):
    node: NodeDefinition
    occurrence: Literal[1] = 1
    missing_dependencies: Annotated[tuple[Key, ...], Field(min_length=1)]


class ConstructionView(ConstructionModel):
    definition_sha256: Annotated[str, Field(strict=True, pattern="^[0-9a-f]{64}$")]
    ready: tuple[ReadyWork, ...]
    blocked: tuple[BlockedWork, ...]
    selected: ReadyWork | None
    complete: bool


class DefinitionTransition(ConstructionModel):
    """One reviewed edition boundary, scoped to an exact not-yet-completed Work."""

    work_id: UUID
    from_snapshot_sha256: Annotated[str, Field(strict=True, pattern="^[0-9a-f]{64}$")]
    from_definition: ProcessDefinition
    to_definition: ProcessDefinition

    @model_validator(mode="after")
    def compatible_identity(self) -> Self:
        before, after = self.from_definition, self.to_definition
        if (
            after.definition_id != before.definition_id
            or after.title != before.title
            or after.required_capabilities != before.required_capabilities
            or after.sources != before.sources
        ):
            raise ValueError("An edition transition must preserve identity, title and sources")
        if after.edition != before.edition + 1:
            raise ValueError("An edition transition must advance exactly one edition")
        return self


def _wire(value: ConstructionModel) -> bytes:
    return (
        json.dumps(
            value.model_dump(mode="json"),
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
            allow_nan=False,
        )
        + chr(10)
    ).encode("utf-8")


def definition_sha256(definition: ProcessDefinition) -> str:
    definition = ProcessDefinition.model_validate(definition.model_dump())
    return hashlib.sha256(_wire(definition)).hexdigest()


def snapshot_bytes(snapshot: ProcessSnapshot) -> bytes:
    snapshot = ProcessSnapshot.model_validate(snapshot.model_dump())
    return _wire(snapshot)


def _result_ground(result: NodeResult) -> ResultGround:
    return ResultGround(
        node_id=result.node_id,
        occurrence=result.occurrence,
        data=result.data,
        result_sha256=hashlib.sha256(_wire(result)).hexdigest(),
    )


def _available(
    definition: ProcessDefinition,
    completed: dict[str, list[NodeResult]],
) -> tuple[tuple[ReadyWork, ...], tuple[BlockedWork, ...]]:
    incomplete = [node for node in definition.nodes if not completed[node.node_id]]
    ready: list[ReadyWork] = []
    blocked: list[BlockedWork] = []
    if incomplete:
        for node in incomplete:
            missing = tuple(
                edge.node_id for edge in node.dependencies if not completed[edge.node_id]
            )
            if missing:
                blocked.append(BlockedWork(node=node, missing_dependencies=missing))
                continue
            grounds = tuple(
                _result_ground(completed[edge.node_id][0]) for edge in node.dependencies
            )
            ready.append(ReadyWork(node=node, occurrence=1, grounds=grounds))
        return tuple(ready), tuple(blocked)

    for node in definition.nodes:
        if not node.recurring:
            continue
        prior = completed[node.node_id]
        recurrence_grounds = [
            _result_ground(completed[edge.node_id][0]) for edge in node.dependencies
        ]
        recurrence_grounds.append(_result_ground(prior[-1]))
        ready.append(
            ReadyWork(
                node=node,
                occurrence=len(prior) + 1,
                grounds=tuple(recurrence_grounds),
            )
        )
    return tuple(ready), ()


def _validate_data(node: NodeDefinition, result: NodeResult) -> None:
    keys = tuple(row.key for row in result.data)
    if keys != node.output_keys:
        raise ConstructionError(
            "incomplete_result",
            f"{node.node_id} data keys must exactly match its declared output keys",
        )


def evaluate_snapshot(snapshot: ProcessSnapshot) -> ConstructionView:
    """Validate complete ordered state and expose its deterministic ready/blocked view."""
    snapshot = ProcessSnapshot.model_validate(snapshot.model_dump())
    definition = snapshot.definition
    unsupported = tuple(
        capability
        for capability in definition.required_capabilities
        if capability not in SUPPORTED_CAPABILITIES
    )
    if unsupported:
        raise ConstructionError(
            "unsupported_capability",
            "Unsupported definition capabilities: " + ", ".join(unsupported),
        )
    nodes = {node.node_id: node for node in definition.nodes}
    completed: dict[str, list[NodeResult]] = {node_id: [] for node_id in nodes}
    for result in snapshot.results:
        node = nodes.get(result.node_id)
        if node is None:
            raise ConstructionError("invalid_result_node", "Result names no definition node")
        ready, _blocked = _available(definition, completed)
        selected = ready[0] if ready else None
        if selected is None or (result.node_id, result.occurrence) != (
            selected.node.node_id,
            selected.occurrence,
        ):
            raise ConstructionError(
                "invalid_result_order", "Result is not the selected eligible occurrence"
            )
        _validate_data(node, result)
        completed[result.node_id].append(result)

    ready, blocked = _available(definition, completed)
    selected = ready[0] if ready else None
    return ConstructionView(
        definition_sha256=definition_sha256(definition),
        ready=ready,
        blocked=blocked,
        selected=selected,
        complete=not ready and not blocked,
    )


def record_result(snapshot: ProcessSnapshot, data: tuple[DataValue, ...]) -> ProcessSnapshot:
    """Append exact data for the currently selected occurrence; no state is written."""
    view = evaluate_snapshot(snapshot)
    if view.selected is None:
        raise ConstructionError("process_complete", "Definition has no next domain occurrence")
    selected = view.selected
    result = NodeResult(
        node_id=selected.node.node_id,
        occurrence=selected.occurrence,
        data=data,
    )
    _validate_data(selected.node, result)
    return snapshot.model_copy(update=dict(results=(*snapshot.results, result)))


def _requirements(snapshot: ProcessSnapshot, selected: ReadyWork) -> tuple[str, ...]:
    definition = snapshot.definition
    return (
        REQUIREMENT_KIND,
        f"definition-sha256:{definition_sha256(definition)}",
        f"basis-snapshot-sha256:{hashlib.sha256(snapshot_bytes(snapshot)).hexdigest()}",
        f"node:{selected.node.node_id}",
        f"occurrence:{selected.occurrence}",
    )


def initial_requirements(definition: ProcessDefinition) -> tuple[str, ...]:
    snapshot = ProcessSnapshot(definition=definition)
    selected = evaluate_snapshot(snapshot).selected
    if selected is None:
        raise ConstructionError("missing_initial_work", "Definition has no initial eligible node")
    return _requirements(snapshot, selected)


def initial_records(definition: ProcessDefinition) -> InitialRecords:
    snapshot = ProcessSnapshot(definition=definition)
    selected = evaluate_snapshot(snapshot).selected
    if selected is None:
        raise ConstructionError("missing_initial_work", "Definition has no initial eligible node")
    node = selected.node
    return InitialRecords(
        process_title=definition.title,
        goal=node.goal,
        expected_result=node.expected_result,
        acceptance=node.acceptance,
        boundaries=node.boundaries,
        budget=node.budget,
        artifact_title=node.artifact_title,
    )


def edition_transition(
    work: Work,
    snapshot: ProcessSnapshot,
    to_definition: ProcessDefinition,
) -> DefinitionTransition:
    """Validate one future-only edition against the exact current Work and basis."""
    snapshot = ProcessSnapshot.model_validate(snapshot.model_dump())
    to_definition = ProcessDefinition.model_validate(to_definition.model_dump())
    transition = DefinitionTransition(
        work_id=work.id,
        from_snapshot_sha256=hashlib.sha256(snapshot_bytes(snapshot)).hexdigest(),
        from_definition=snapshot.definition,
        to_definition=to_definition,
    )
    current = evaluate_snapshot(snapshot).selected
    if current is None:
        raise ConstructionError("work_mismatch", "Snapshot has no current selected Work")
    if work.executor_requirements != _requirements(snapshot, current) or not _node_matches(
        work, current.node
    ):
        raise ConstructionError("work_mismatch", "Core Work is not this exact snapshot selection")
    if to_definition.nodes == snapshot.definition.nodes:
        raise ConstructionError(
            "no_change", "Advancing only the definition edition is not a process change"
        )
    touched = {row.node_id for row in snapshot.results} | {current.node.node_id}
    old_nodes = {row.node_id: row for row in snapshot.definition.nodes}
    new_nodes = {row.node_id: row for row in to_definition.nodes}
    if any(new_nodes.get(node_id) != old_nodes[node_id] for node_id in touched):
        raise ConstructionError(
            "started_work_changed", "Completed and current node definitions must remain exact"
        )
    transitioned = ProcessSnapshot(definition=to_definition, results=snapshot.results)
    changed_current = evaluate_snapshot(transitioned).selected
    if changed_current != current:
        raise ConstructionError(
            "current_work_changed", "The proposed edition changes current Work selection"
        )
    placeholder = tuple(
        DataValue(key=key, value="Pending exact accepted value") for key in current.node.output_keys
    )
    completed = record_result(snapshot, placeholder)
    changed_completed = ProcessSnapshot(
        definition=to_definition,
        results=completed.results,
    )
    if evaluate_snapshot(changed_completed).selected is None:
        raise ConstructionError(
            "no_future_work",
            "The proposed edition has no supported Work after the current Result",
        )
    return transition


def _node_matches(work: Work, node: NodeDefinition) -> bool:
    return (
        work.goal == node.goal
        and work.expected_result == node.expected_result
        and work.acceptance == node.acceptance
        and work.boundaries == node.boundaries
        and work.budget == node.budget
    )


def _apply_transition(
    transition: DefinitionTransition,
    work: Work,
    before: ProcessSnapshot,
    accepted: ProcessSnapshot,
) -> ProcessSnapshot:
    if (
        transition.work_id != work.id
        or transition.from_definition != before.definition
        or transition.from_snapshot_sha256 != hashlib.sha256(snapshot_bytes(before)).hexdigest()
    ):
        raise ConstructionError("transition_mismatch", "Edition transition source changed")
    # Repeat all compatibility checks at use time; retained journal data grants nothing.
    checked = edition_transition(work, before, transition.to_definition)
    if checked != transition:
        raise ConstructionError("transition_mismatch", "Edition transition changed")
    try:
        return ProcessSnapshot(definition=transition.to_definition, results=accepted.results)
    except ValidationError as error:
        raise ConstructionError(
            "transition_invalid", "Accepted history cannot enter the approved edition"
        ) from error


@dataclass(frozen=True)
class DefinitionRule:
    reference: PackReference
    definition: ProcessDefinition
    transition: DefinitionTransition | None = None

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "reference", PackReference.model_validate(self.reference.model_dump())
        )
        object.__setattr__(
            self, "definition", ProcessDefinition.model_validate(self.definition.model_dump())
        )
        if self.transition is not None:
            copied = DefinitionTransition.model_validate(self.transition.model_dump())
            if copied.from_definition != self.definition:
                raise ConstructionError(
                    "transition_mismatch", "Transition must begin at the registered definition"
                )
            object.__setattr__(self, "transition", copied)

    def next_work(
        self, work: Work, accepted_result: bytes, work_id: UUID, artifact_id: UUID
    ) -> NextWork:
        if work.pack_binding != self.reference:
            raise ConstructionError("binding_mismatch", "Work needs this exact Pack binding")
        try:
            snapshot = ProcessSnapshot.model_validate_json(accepted_result)
        except ValidationError as error:
            raise ConstructionError(
                "invalid_snapshot", "Accepted bytes are not a complete definition snapshot"
            ) from error
        if snapshot_bytes(snapshot) != accepted_result:
            raise ConstructionError("noncanonical_snapshot", "Accepted snapshot bytes changed form")
        allowed: tuple[ProcessDefinition, ...] = (self.definition,)
        if self.transition is not None:
            allowed = (*allowed, self.transition.to_definition)
        if snapshot.definition not in allowed:
            raise ConstructionError(
                "definition_mismatch", "Accepted snapshot is not a registered definition edition"
            )
        if not snapshot.results:
            raise ConstructionError("missing_result", "Accepted snapshot has no current result")
        before = snapshot.model_copy(update=dict(results=snapshot.results[:-1]))
        current = evaluate_snapshot(before).selected
        if current is None:
            raise ConstructionError(
                "work_mismatch", "Core Work does not name the snapshot's selected occurrence"
            )
        expected_requirements = _requirements(before, current)
        node_matches = _node_matches(work, current.node)
        if work.executor_requirements != expected_requirements or not node_matches:
            same_selection = (
                node_matches
                and len(work.executor_requirements) == len(expected_requirements)
                and work.executor_requirements[:2] == expected_requirements[:2]
                and work.executor_requirements[3:] == expected_requirements[3:]
            )
            if same_selection:
                raise ConstructionError(
                    "history_mismatch", "Prior accepted snapshot bytes have changed"
                )
            raise ConstructionError(
                "work_mismatch", "Core Work does not name the snapshot's selected occurrence"
            )
        result = snapshot.results[-1]
        if (result.node_id, result.occurrence) != (current.node.node_id, current.occurrence):
            raise ConstructionError("work_mismatch", "Snapshot result belongs to another Work")
        effective = snapshot
        if (
            self.transition is not None
            and snapshot.definition == self.transition.from_definition
            and work.id == self.transition.work_id
        ):
            effective = _apply_transition(self.transition, work, before, snapshot)
        following = evaluate_snapshot(effective).selected
        if following is None:
            raise ConstructionError("process_complete", "No further domain occurrence is ready")
        node = following.node
        return NextWork(
            work_id=work_id,
            artifact_id=artifact_id,
            goal=node.goal,
            expected_result=node.expected_result,
            acceptance=node.acceptance,
            boundaries=node.boundaries,
            budget=node.budget,
            executor_requirements=_requirements(effective, following),
            artifact_title=node.artifact_title,
            authority_scope="work_metadata",
        )


def registration(
    reference: PackReference,
    definition: ProcessDefinition,
    transition: DefinitionTransition | None = None,
) -> PackRegistration:
    """Register one exact definition under an already explicit immutable Pack identity."""
    rule = DefinitionRule(reference, definition, transition)
    return PackRegistration(rule.reference, rule)

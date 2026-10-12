"""Model-free compilation of an exact, reviewable Activity structure package."""

from __future__ import annotations

import sqlite3
from typing import Any
from uuid import UUID, uuid5

from .capabilities import ProcedureOperation
from .data_formats import validate_format
from .data_store import exact_state, head_ref
from .models import (
    ActivityActivationManifest,
    ActivitySetupDraft,
    ActivitySetupDraftV2,
    ActivitySetupReview,
    ActivitySetupReviewV2,
    ActivitySetupState,
    ActivityStructureState,
    ArtifactRef,
    CompiledFormat,
    DataFormatState,
    KnowledgeRef,
    MemoryMetadata,
    MethodRef,
    OutputContract,
    ProcedureDefinition,
    SetupValidationIssue,
    WorkPlan,
)
from .setup_validation import SetupResultError, validate_new_value
from .storage import FoundationError


def _typed_plan(plan: WorkPlan, outputs: tuple[OutputContract, ...]) -> WorkPlan:
    """A bound child produces the same exact format as the parent's declared output."""
    contracts = {item.slot: item for item in outputs}
    children = []
    for child in plan.children:
        bindings = {
            item.child_slot: contracts[item.parent_slot]
            for item in plan.output_bindings
            if item.role == child.role and item.parent_slot in contracts
        }
        updated = []
        for output in child.state.expected_outputs:
            parent = bindings.get(output.slot)
            if parent is not None:
                if output.format_ref is not None and output.format_ref != parent.format_ref:
                    raise FoundationError("invalid_plan", "Bound child output uses another format")
                output = output.model_copy(update={"format_ref": parent.format_ref})
            updated.append(output)
        children.append(
            child.model_copy(
                update={
                    "state": child.state.model_copy(update={"expected_outputs": tuple(updated)})
                }
            )
        )
    return plan.model_copy(update={"children": tuple(children)})


SUPPORTED_OPERATIONS = frozenset(ProcedureOperation)


def draft_from_bytes(raw: bytes, version: int) -> ActivitySetupDraft | ActivitySetupDraftV2:
    return (ActivitySetupDraftV2 if version == 2 else ActivitySetupDraft).model_validate_json(raw)


def review_from_bytes(raw: bytes, version: int) -> ActivitySetupReview | ActivitySetupReviewV2:
    return (ActivitySetupReviewV2 if version == 2 else ActivitySetupReview).model_validate_json(raw)


def compile_structure(
    connection: sqlite3.Connection,
    setup_id: UUID,
    state: ActivitySetupState,
    draft: ActivitySetupDraftV2,
    draft_ref: ArtifactRef,
    actor: str,
    epoch: int,
) -> ActivityActivationManifest:
    from .composition import method_checksum

    if head_ref(connection, state.activity_id) != state.previous_structure:
        raise FoundationError("stale_structure", "Activity structure changed during preparation")
    compiled: list[CompiledFormat] = []
    for template in draft.formats:
        definition = template.definition
        if template.existing is None and definition.scope_activity_id not in (
            None,
            state.activity_id,
        ):
            raise FoundationError("out_of_scope", "New formats belong to this Activity")
        if template.existing is not None:
            existing = exact_state(connection, template.existing, actor, epoch)
            if not isinstance(existing, DataFormatState) or existing != definition:
                raise FoundationError(
                    "stale_format", "Borrowed format must keep its exact definition"
                )
            compiled.append(
                CompiledFormat(
                    key=template.key, ref=template.existing, definition=definition, create=False
                )
            )
            continue
        definition = definition.model_copy(
            update={
                "scope_activity_id": state.activity_id,
                "memory": MemoryMetadata(
                    title=definition.title, activity_id=state.activity_id, material_role="working"
                ),
            }
        )
        validate_new_value(("formats", template.key, "definition"), validate_format, definition)
        identifier = uuid5(state.activity_id, "format:" + template.key)
        row = connection.execute(
            "SELECT current_revision FROM knowledge_records WHERE record_id=?", (str(identifier),)
        ).fetchone()
        old = int(row[0]) if row else None
        if old is not None:
            previous = exact_state(
                connection, KnowledgeRef(record_id=identifier, revision=old), actor, epoch
            )
            if not isinstance(previous, DataFormatState):
                raise FoundationError("wrong_kind", "Reserved format address has another kind")
            if previous == definition:
                compiled.append(
                    CompiledFormat(
                        key=template.key,
                        ref=KnowledgeRef(record_id=identifier, revision=old),
                        definition=definition,
                        create=False,
                    )
                )
                continue
        compiled.append(
            CompiledFormat(
                key=template.key,
                ref=KnowledgeRef(record_id=identifier, revision=(old or 0) + 1),
                definition=definition,
                expected_revision=old,
            )
        )
    formats = {item.key: item.ref for item in compiled}

    def selectors(values: Any) -> tuple[Any, ...]:
        result = []
        for value in values:
            if not set(value.format_keys).issubset(formats):
                raise SetupResultError(
                    "invalid_format",
                    "Selection names an absent local format",
                    ("selectors", "format_keys"),
                )
            result.append(
                value.model_copy(
                    update={
                        "format_keys": (),
                        "format_refs": value.format_refs
                        + tuple(formats[key] for key in value.format_keys),
                    }
                )
            )
        return tuple(result)

    definitions = {}
    for item in draft.methods:
        if item.definition.required_capabilities:
            raise SetupResultError(
                "unsupported_condition",
                "Method capabilities are not connected",
                ("methods", item.key, "definition", "required_capabilities"),
            )
        if not set(item.output_formats).issubset(
            {output.slot for output in item.definition.named_outputs}
        ):
            raise SetupResultError(
                "invalid_format",
                "Method output format names an absent slot",
                ("methods", item.key, "output_formats"),
            )
        if not set(item.output_formats.values()).issubset(formats):
            raise SetupResultError(
                "invalid_format",
                "Method output names an absent local format",
                ("methods", item.key, "output_formats"),
            )
        definitions[item.key] = item.definition.model_copy(
            update={
                "named_outputs": tuple(
                    output.model_copy(
                        update={"format_ref": formats[item.output_formats[output.slot]]}
                    )
                    if output.slot in item.output_formats
                    else output
                    for output in item.definition.named_outputs
                ),
                "memory_requirements": tuple(
                    requirement.model_copy(update={"selectors": selectors(requirement.selectors)})
                    for requirement in item.definition.memory_requirements
                ),
            }
        )
        from .composition import _method
        from .operations import _authorize

        for _, role_method in item.definition.role_methods:
            _method(connection, role_method)
            _authorize(
                connection,
                actor=actor,
                action="method.use",
                epoch=epoch,
                resource_type="method",
                resource_id=role_method.method_id,
            )
    methods = {
        item.key: MethodRef(
            method_id=uuid5(setup_id, "method:" + item.key),
            version=1,
            checksum=method_checksum(definitions[item.key]),
        )
        for item in draft.methods
    }
    procedures: list[ProcedureDefinition] = []
    for procedure_template in draft.procedures:
        if not set(procedure_template.operations).issubset(SUPPORTED_OPERATIONS):
            raise SetupResultError(
                "unsupported_operation", "Procedure names an unavailable operation"
            )
        outputs = tuple(
            OutputContract.model_validate(
                {
                    **output.model_dump(exclude={"format_key"}),
                    "format_ref": formats[output.format_key]
                    if output.format_key
                    else output.format_ref,
                }
            )
            for output in procedure_template.outputs
        )
        fields: dict[str, Any] = procedure_template.model_dump(exclude={"method_key", "outputs"})
        fields.update(outputs=outputs, method=methods.get(procedure_template.method_key or ""))
        fields["inputs"] = selectors(procedure_template.inputs)
        if procedure_template.plan is not None:
            fields["plan"] = validate_new_value(
                ("procedures", procedure_template.key, "plan"),
                _typed_plan,
                procedure_template.plan,
                outputs,
            )
        procedure = validate_new_value(
            ("procedures", procedure_template.key),
            ProcedureDefinition.model_validate,
            fields,
        )
        if procedure.parameters:
            validate_new_value(
                ("procedures", procedure_template.key, "parameters"),
                validate_format,
                DataFormatState(
                    title="Procedure parameters", role="object", fields=procedure.parameters
                ),
            )
        if procedure.timezone is not None:
            from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

            try:
                ZoneInfo(procedure.timezone)
            except (ZoneInfoNotFoundError, ValueError) as error:
                raise SetupResultError(
                    "invalid_timezone",
                    "Procedure needs an IANA timezone",
                    ("procedures", procedure_template.key, "timezone"),
                ) from error
        if procedure.method is not None:
            assert procedure_template.method_key is not None
            method_definition = definitions[procedure_template.method_key]
            if procedure.outputs != method_definition.named_outputs:
                raise SetupResultError(
                    "invalid_plan",
                    "Procedure outputs differ from its Method",
                    ("procedures", procedure_template.key, "outputs"),
                )
            if procedure.input_slot not in {
                value.slot
                for value in method_definition.named_inputs
                if value.media_type == "application/json"
            }:
                raise SetupResultError(
                    "invalid_plan",
                    "Composite procedure needs its JSON input slot",
                    ("procedures", procedure_template.key, "input_slot"),
                )
            from .composition import _validate_plan

            assert procedure.plan is not None
            if any(
                child.state.activity_id != state.activity_id for child in procedure.plan.children
            ):
                raise FoundationError("out_of_scope", "Procedure children belong to this Activity")
            validate_new_value(
                ("procedures", procedure_template.key, "plan"),
                _validate_plan,
                procedure.plan,
                method_definition,
                state.activity_id,
                schema=15,
                allow_nested=True,
            )
        procedures.append(procedure)
    identifier = uuid5(state.activity_id, "structure")
    current = connection.execute(
        "SELECT current_revision FROM knowledge_records WHERE record_id=?", (str(identifier),)
    ).fetchone()
    expected_revision = int(current[0]) if current else None
    previous_head = connection.execute(
        "SELECT setup_id FROM structure_heads WHERE activity_id=?", (str(state.activity_id),)
    ).fetchone()
    ref = KnowledgeRef(
        record_id=identifier,
        revision=(expected_revision or 0) + 1,
    )
    from .models import WorkflowRef
    from .workflows import WORKFLOW_CORE_OPERATIONS, workflow_checksum

    for ordinal, workflow_definition in enumerate(draft.workflows):
        for index, node in enumerate(workflow_definition.nodes):
            if node.kind == "core" and node.operation not in WORKFLOW_CORE_OPERATIONS:
                raise SetupResultError(
                    "unsupported_operation",
                    "Core workflow operation is not registered",
                    ("workflows", ordinal, "nodes", index, "operation"),
                )
    workflow_refs = tuple(
        WorkflowRef(
            workflow_id=uuid5(setup_id, f"workflow:{ordinal}"),
            version=1,
            checksum=workflow_checksum(definition),
        )
        for ordinal, definition in enumerate(draft.workflows)
    )
    structure = ActivityStructureState(
        scope_activity_id=state.activity_id,
        title=draft.title,
        goal=draft.goal,
        instructions=draft.instructions,
        first_action=draft.first_action,
        process=draft.process + "\n\nFirst path:\n" + draft.first_path,
        workflows=workflow_refs,
        formats=formats,
        procedures=tuple(procedures),
        working_sets=tuple(
            item.model_copy(update={"selectors": selectors(item.selectors)})
            for item in draft.working_sets
        ),
        memory_requirements=tuple(
            item.model_copy(update={"selectors": selectors(item.selectors)})
            for item in draft.memory
        ),
        bases=state.sources
        + (KnowledgeRef(record_id=draft_ref.artifact_id, revision=draft_ref.revision),),
        extensions=draft.extensions,
        deferred_questions=tuple(
            item.text
            for item in draft.questions
            if not item.blocking or item.scope in ("procedure", "none")
        ),
        memory=MemoryMetadata(
            title="Activity structure", activity_id=state.activity_id, material_role="working"
        ),
    )
    initial_works = []
    for work in draft.works:
        if not set(work.output_formats).issubset({item.slot for item in work.expected_outputs}):
            raise SetupResultError(
                "invalid_format",
                "Initial Work names an absent output slot",
                ("works", work.key, "output_formats"),
            )
        if not set(work.output_formats.values()).issubset(formats):
            raise SetupResultError(
                "invalid_format",
                "Initial Work names an absent local format",
                ("works", work.key, "output_formats"),
            )
        outputs = tuple(
            item.model_copy(update={"format_ref": formats[work.output_formats[item.slot]]})
            if item.slot in work.output_formats
            else item
            for item in work.expected_outputs
        )
        if work.method_key is not None:
            from .composition import _validate_plan

            assert work.plan is not None
            work = work.model_copy(
                update={
                    "plan": validate_new_value(
                        ("works", work.key, "plan"), _typed_plan, work.plan, outputs
                    )
                }
            )
            assert work.plan is not None
            assert work.method_key is not None
            if any(child.state.activity_id != state.activity_id for child in work.plan.children):
                raise FoundationError("out_of_scope", "Initial children belong to this Activity")
            validate_new_value(
                ("works", work.key, "plan"),
                _validate_plan,
                work.plan,
                definitions[work.method_key],
                state.activity_id,
                schema=15,
                allow_nested=True,
            )
        initial_works.append(
            work.model_copy(update={"expected_outputs": outputs, "output_formats": {}})
        )
    return ActivityActivationManifest(
        setup_id=setup_id,
        activity_id=state.activity_id,
        draft=draft_ref,
        input_version=state.input_version,
        previous_structure=state.previous_structure,
        previous_setup_id=UUID(previous_head[0]) if previous_head else None,
        structure_expected_revision=expected_revision,
        formats=tuple(compiled),
        structure_ref=ref,
        structure=structure,
        method_definitions=definitions,
        initial_works=tuple(initial_works),
        workflow_definitions=draft.workflows,
    )


def review_component_catalog(manifest: ActivityActivationManifest) -> tuple[str, ...]:
    """Exact review addresses; retained root aliases keep older reports readable."""
    allowed = {
        "title",
        "goal",
        "instructions",
        "process",
        "first_action",
        "first_path",
        "sources",
        "decisions",
        "memory",
        "extensions",
        "questions",
        "working_sets",
        "initial_works",
        "formats",
        "procedures",
        "methods",
        "works",
        "workflows",
    }
    allowed.update("formats." + item.key for item in manifest.formats)
    allowed.update("procedures." + item.key for item in manifest.structure.procedures)
    allowed.update("methods." + key for key in manifest.method_definitions)
    allowed.update("working_sets." + item.key for item in manifest.structure.working_sets)
    for item in manifest.initial_works:
        allowed.update(("works." + item.key, "initial_works." + item.key))
    allowed.update("workflows." + str(index) for index in range(len(manifest.workflow_definitions)))
    allowed.update("workflows." + str(item.workflow_id) for item in manifest.structure.workflows)
    return tuple(sorted(allowed))


def review_result_schema(manifest: ActivityActivationManifest) -> dict[str, Any]:
    """Constrain only a newly prepared review packet, not persisted model contracts."""
    schema = ActivitySetupReviewV2.model_json_schema()
    schema["$defs"]["SetupAreaEvidence"]["properties"]["components"]["items"] = {
        "type": "string",
        "enum": list(review_component_catalog(manifest)),
    }
    return schema


def validate_review_components(
    report: ActivitySetupReviewV2, manifest: ActivityActivationManifest
) -> None:
    allowed = review_component_catalog(manifest)
    issues = tuple(
        SetupValidationIssue(
            code="unsupported_review_component",
            message="Use an exact component address from review_components",
            path=("coverage", coverage_index, "components", component_index),
            allowed_values=allowed,
        )
        for coverage_index, coverage in enumerate(report.coverage)
        for component_index, component in enumerate(coverage.components)
        if component not in allowed
    )[:16]
    if issues:
        error = SetupResultError(
            issues[0].code,
            issues[0].message,
            issues[0].path,
        )
        error.issues = issues
        raise error


__all__ = ["compile_structure", "draft_from_bytes", "review_from_bytes"]

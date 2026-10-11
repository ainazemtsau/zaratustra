"""Model-free compilation of an exact, reviewable Activity structure package."""

from __future__ import annotations

import sqlite3
from typing import Any
from uuid import UUID, uuid5

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
    WorkPlan,
)
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


SUPPORTED_OPERATIONS = frozenset(
    {
        "describe_structure",
        "list_formats",
        "read_format",
        "create_entry",
        "correct_entry",
        "ingest_batch",
        "read_entry",
        "history",
        "query_entries",
        "aggregate_entries",
        "start_procedure",
        "procedure_status",
        "due_procedures",
        "catalog",
        "read_batch",
        "prepare_cache",
        "open_selection",
        "retain",
        "prepare",
        "publish",
        "request_input",
    }
)


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
        validate_format(definition)
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
                raise FoundationError("invalid_format", "Selection names an absent local format")
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
            raise FoundationError("unsupported_condition", "Method capabilities are not connected")
        if not set(item.output_formats).issubset(
            {output.slot for output in item.definition.named_outputs}
        ):
            raise FoundationError("invalid_format", "Method output format names an absent slot")
        if not set(item.output_formats.values()).issubset(formats):
            raise FoundationError("invalid_format", "Method output names an absent local format")
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
            raise FoundationError(
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
            fields["plan"] = _typed_plan(procedure_template.plan, outputs)
        procedure = ProcedureDefinition.model_validate(fields)
        if procedure.parameters:
            validate_format(
                DataFormatState(
                    title="Procedure parameters", role="object", fields=procedure.parameters
                )
            )
        if procedure.timezone is not None:
            from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

            try:
                ZoneInfo(procedure.timezone)
            except (ZoneInfoNotFoundError, ValueError) as error:
                raise FoundationError(
                    "invalid_timezone", "Procedure needs an IANA timezone"
                ) from error
        if procedure.method is not None:
            assert procedure_template.method_key is not None
            method_definition = definitions[procedure_template.method_key]
            if procedure.outputs != method_definition.named_outputs:
                raise FoundationError("invalid_plan", "Procedure outputs differ from its Method")
            if procedure.input_slot not in {
                value.slot
                for value in method_definition.named_inputs
                if value.media_type == "application/json"
            }:
                raise FoundationError(
                    "invalid_plan", "Composite procedure needs its JSON input slot"
                )
            from .composition import _validate_plan

            assert procedure.plan is not None
            _validate_plan(
                procedure.plan, method_definition, state.activity_id, schema=15, allow_nested=True
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
    structure = ActivityStructureState(
        scope_activity_id=state.activity_id,
        title=draft.title,
        goal=draft.goal,
        instructions=draft.instructions,
        first_action=draft.first_action,
        process=draft.process + "\n\nFirst path:\n" + draft.first_path,
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
        deferred_questions=tuple(item.text for item in draft.questions if not item.blocking),
        memory=MemoryMetadata(
            title="Activity structure", activity_id=state.activity_id, material_role="working"
        ),
    )
    initial_works = []
    for work in draft.works:
        if not set(work.output_formats).issubset({item.slot for item in work.expected_outputs}):
            raise FoundationError("invalid_format", "Initial Work names an absent output slot")
        if not set(work.output_formats.values()).issubset(formats):
            raise FoundationError("invalid_format", "Initial Work names an absent local format")
        outputs = tuple(
            item.model_copy(update={"format_ref": formats[work.output_formats[item.slot]]})
            if item.slot in work.output_formats
            else item
            for item in work.expected_outputs
        )
        if work.method_key is not None:
            from .composition import _validate_plan

            assert work.plan is not None
            work = work.model_copy(update={"plan": _typed_plan(work.plan, outputs)})
            assert work.plan is not None
            assert work.method_key is not None
            _validate_plan(
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
    )


def validate_review_components(
    report: ActivitySetupReviewV2, manifest: ActivityActivationManifest
) -> None:
    allowed = {
        "goal",
        "instructions",
        "process",
        "first_path",
        "sources",
        "decisions",
        "memory",
        "extensions",
        "questions",
        "working_sets",
        "initial_works",
    }
    allowed.update("formats." + item.key for item in manifest.formats)
    allowed.update("procedures." + item.key for item in manifest.structure.procedures)
    allowed.update("methods." + key for key in manifest.method_definitions)
    for coverage in report.coverage:
        if not set(coverage.components).issubset(allowed):
            raise FoundationError(
                "invalid_setup_result", "Review addresses an absent manifest component"
            )


__all__ = ["compile_structure", "draft_from_bytes", "review_from_bytes"]

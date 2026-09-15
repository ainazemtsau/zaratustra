"""Host-independent entry for explicit owner-requested Process operations."""

from __future__ import annotations

import argparse
import hashlib
import hmac
import json
import sys
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from zaratustra.core import (
    WorkspaceError,
    authorize_local,
    prepare_authorization,
    read_records,
    read_workspace,
)
from zaratustra.entry import EntryError, resolve_entry
from zaratustra.onboarding import (
    OnboardingError,
    ProseClarification,
    creation_status_text,
    onboarding_status_text,
    prepare_onboarding_read,
    read_onboarding,
    save_prose_creation_draft,
)
from zaratustra.process_creation import (
    ProcessCreationError,
    authorize_process_activation,
    execute_process_activation,
    inspect_process_creation,
    prepare_process_activation,
)


def _required(value: str, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"Explicit {label} is required")
    return value


def _catalog_file(catalog: Path) -> Path:
    selected = catalog.expanduser().resolve()
    if selected.is_dir():
        raise ValueError("Explicit catalog must be a file path, not a directory")
    return selected


def _selects_catalog_entry(catalog: Path, designation: str) -> bool:
    if not catalog.exists():
        return False
    try:
        resolve_entry(catalog, designation)
    except EntryError as error:
        if error.code == "not_found":
            return False
        raise
    return True


def read_selected(
    catalog: Path,
    designation: str,
    *,
    actor: str,
    source_ref: str,
) -> str:
    """Read one explicit catalog selection under the trusted local owner request."""
    catalog = _catalog_file(catalog)
    designation = _required(designation, "designation")
    actor = _required(actor, "local-agent actor")
    source_ref = _required(source_ref, "owner-instruction source")
    try:
        creation = inspect_process_creation(catalog, designation)
    except ProcessCreationError as error:
        if error.code != "creation_not_found":
            raise
        creation = None
    if (
        creation is not None
        and creation.stage != "activated"
        and _selects_catalog_entry(catalog, designation)
    ):
        raise OnboardingError(
            "selection_conflict",
            "Designation matches both an unfinished creation and a cataloged Process",
        )
    prepared = prepare_onboarding_read(catalog, designation)
    caller = None
    if prepared.process_read is not None:
        prompt = prepare_authorization(
            prepared.process_read.workspace,
            prepared.process_read.query,
        )
        caller = authorize_local(
            prompt,
            channel="local-chat",
            actor=actor,
            source_ref=source_ref,
        )
    return onboarding_status_text(read_onboarding(prepared, caller))


def save_prose_draft(
    catalog: Path,
    designation: str,
    *,
    process_title: str,
    need: str,
    desired_outcomes: tuple[str, ...],
    constraints: tuple[str, ...],
    created_by: str,
    clarifications: tuple[ProseClarification, ...] = (),
) -> str:
    """Save one owner-requested prose draft through the existing creation journal."""
    catalog = _catalog_file(catalog)
    designation = _required(designation, "designation")
    if _selects_catalog_entry(catalog, designation):
        raise OnboardingError(
            "designation_conflict",
            "A cataloged Process already has this designation or alias",
        )
    status = save_prose_creation_draft(
        catalog,
        designation,
        process_title=process_title,
        need=need,
        desired_outcomes=desired_outcomes,
        constraints=constraints,
        created_by=created_by,
        clarifications=clarifications,
    )
    return creation_status_text(status)


def _activation_target_observation(
    selected: Path,
    *,
    retained_workspace_id: object | None,
) -> dict[str, object]:
    if not selected.exists():
        if retained_workspace_id is not None:
            raise ProcessCreationError(
                "workspace_collision", "Reserved activation workspace is missing"
            )
        return {"state": "new_directory", "workspace_id": None, "schema_version": None}
    if not selected.is_dir():
        raise ProcessCreationError(
            "workspace_collision", "Selected activation target is not a directory"
        )
    if not (selected / ".zara").exists():
        if retained_workspace_id is not None:
            raise ProcessCreationError(
                "workspace_collision", "Reserved activation workspace identity changed"
            )
        if any(selected.iterdir()):
            raise ProcessCreationError(
                "workspace_collision", "Selected activation target is not empty"
            )
        return {"state": "empty_directory", "workspace_id": None, "schema_version": None}
    try:
        info = read_workspace(selected)
        records = read_records(selected) if info.schema_version >= 2 else None
    except (WorkspaceError, OSError) as error:
        raise ProcessCreationError(
            "workspace_collision", "Selected activation target has invalid managed state"
        ) from error
    if retained_workspace_id is not None:
        if info.workspace_id != retained_workspace_id:
            raise ProcessCreationError(
                "workspace_collision", "Activated workspace identity changed"
            )
        state = "activated_workspace"
    elif records is not None and (records.state_revision != 0 or records.records):
        raise ProcessCreationError(
            "workspace_collision", "Selected activation target already has managed state"
        )
    else:
        state = "initialized_empty_workspace"
    return {
        "state": state,
        "workspace_id": str(info.workspace_id),
        "schema_version": info.schema_version,
    }


def _activation_intent(
    catalog: Path,
    designation: str,
    workspace: Path,
    aliases: tuple[str, ...],
) -> tuple[str, str]:
    catalog = _catalog_file(catalog)
    designation = _required(designation, "designation")
    selected = workspace.expanduser().resolve()
    status = inspect_process_creation(catalog, designation)
    if status.proposal is None:
        raise ProcessCreationError(
            "proposal_missing", "Activation needs a saved supported proposal"
        )
    target_path = selected.as_posix()
    normalized_aliases = tuple(_required(alias, "alias") for alias in aliases)
    if len(set(normalized_aliases)) != len(normalized_aliases):
        raise ProcessCreationError("invalid_request", "Activation aliases must be distinct")
    retained_workspace_id: object | None = None
    if status.activation_target is not None:
        if (
            status.activation_target.workspace_path != target_path
            or status.activation_target.aliases != normalized_aliases
        ):
            raise ProcessCreationError(
                "activation_collision", "Activation target or aliases changed"
            )
        retained_workspace_id = status.workspace_id or status.bootstrap_workspace_id
    observed = _activation_target_observation(selected, retained_workspace_id=retained_workspace_id)
    payload: dict[str, Any] = {
        "version": 1,
        "action": "activate_saved_process_proposal",
        "catalog": catalog.as_posix(),
        "creation_id": str(status.creation_id),
        "designation": status.designation,
        "draft_sha256": status.draft_sha256,
        "draft": status.draft.model_dump(mode="json"),
        "proposal": status.proposal.model_dump(mode="json"),
        "target": {
            "workspace_path": target_path,
            "aliases": normalized_aliases,
            **observed,
        },
    }
    canonical = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")
    digest = hashlib.sha256(canonical).hexdigest()
    draft = status.draft
    definition = status.proposal.definition
    lines = [
        "Proposed Zaratustra Process activation",
        f"Process: {status.designation}",
        f"Title: {draft.process_title}",
        "Need:",
        draft.need,
        "Desired outcomes:",
        *(f"- {row}" for row in draft.desired_outcomes),
        "Constraints:",
        *(f"- {row}" for row in draft.constraints),
        (
            f"Definition: {definition.title} "
            f"({definition.definition_id}, edition {definition.edition})"
        ),
        "Required capabilities:",
        *(f"- {row}" for row in definition.required_capabilities),
        "Proposal sources:",
        *(
            f"- {source.source_id}: {source.kind} | {source.locator}"
            for source in definition.sources
        ),
        "Proposed Works:",
    ]
    for node in definition.nodes:
        lines.extend(
            (
                f"- {node.node_id}: {node.goal}",
                f"  Expected result: {node.expected_result}",
                f"  Acceptance: {'; '.join(node.acceptance)}",
                f"  Boundaries: {'; '.join(node.boundaries)}",
                f"  Budget: {node.budget}",
                f"  Artifact: {node.artifact_title}",
                f"  Output keys: {', '.join(node.output_keys)}",
                "  Depends on: " + (", ".join(row.node_id for row in node.dependencies) or "none"),
                f"  Repeats: {'yes' if node.recurring else 'no'}",
                "  Why:",
                *(
                    f"    - {reason.text} [sources: {', '.join(reason.source_ids)}]"
                    for reason in node.reasons
                ),
            )
        )
    lines.extend(
        (
            f"Target workspace: {target_path}",
            f"Target state: {observed['state']}",
            f"Target workspace identity: {observed['workspace_id'] or 'not initialized'}",
            f"Aliases: {', '.join(normalized_aliases) if normalized_aliases else 'none'}",
            "This preview is read-only; it created no Process records.",
            f"Assistant freshness SHA-256: {digest}",
            "Ask the owner whether to create this exact Process at this exact location. "
            "Keep the digest as tool metadata; do not ask the owner to repeat it.",
        )
    )
    return "\n".join(lines) + "\n", digest


def preview_process_activation(
    catalog: Path,
    designation: str,
    workspace: Path,
    *,
    aliases: tuple[str, ...] = (),
) -> str:
    """Render one exact saved proposal and selected target without bootstrapping it."""
    text, _digest = _activation_intent(catalog, designation, workspace, aliases)
    return text


def confirm_process_activation(
    catalog: Path,
    designation: str,
    workspace: Path,
    *,
    aliases: tuple[str, ...] = (),
    expected_sha256: str,
    actor: str,
    source_ref: str,
) -> str:
    """Activate only the freshly matching intent after the owner agreed in conversation."""
    actor = _required(actor, "local-agent actor")
    source_ref = _required(source_ref, "owner-confirmation source")
    _text, actual_sha256 = _activation_intent(catalog, designation, workspace, aliases)
    if not hmac.compare_digest(expected_sha256, actual_sha256):
        raise ProcessCreationError(
            "stale_activation",
            "Displayed proposal, target, aliases, or workspace identity changed",
        )
    prepared = prepare_process_activation(catalog, designation, workspace, aliases=aliases)
    authorization = authorize_process_activation(
        prepared,
        channel="local-chat",
        actor=actor,
        source_ref=source_ref,
    )
    receipt = execute_process_activation(prepared, authorization)
    creation = receipt.creation
    lines = [
        creation_status_text(creation).rstrip(),
        f"Workspace ID: {creation.workspace_id}",
        f"Process ID: {creation.process_id}",
        f"First Work: {creation.first_work_id}",
        f"Completed activation operations: {', '.join(creation.completed_operations)}",
    ]
    if receipt.warnings:
        lines.extend(("Warnings:", *(f"- {row}" for row in receipt.warnings)))
    return "\n".join(lines) + "\n"


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="zara-agent",
        description="Trusted local-agent entry for explicit selected Process operations.",
    )
    commands = parser.add_subparsers(dest="command", required=True)
    read = commands.add_parser("read", help="Read one explicitly selected Process or draft.")
    read.add_argument("catalog", type=Path)
    read.add_argument("designation")
    read.add_argument("--actor", required=True)
    read.add_argument("--source-ref", required=True)
    draft = commands.add_parser("draft", help="Save an explicitly requested prose draft.")
    draft.add_argument("catalog", type=Path)
    draft.add_argument("designation")
    draft.add_argument("need")
    draft.add_argument("--title", required=True)
    draft.add_argument("--outcome", action="append", required=True)
    draft.add_argument("--constraint", action="append", required=True)
    draft.add_argument("--created-by", required=True)
    draft.add_argument("--clarification", action="append", default=[])
    draft.add_argument("--clarification-reason", action="append", default=[])
    draft.add_argument("--clarification-answer", action="append", default=[])
    preview = commands.add_parser(
        "activation-preview", help="Show a saved proposal and target without creating records."
    )
    preview.add_argument("catalog", type=Path)
    preview.add_argument("designation")
    preview.add_argument("workspace", type=Path)
    preview.add_argument("--alias", action="append", default=[])
    confirm = commands.add_parser(
        "activation-confirm",
        help="Activate the unchanged proposal after its conversational confirmation.",
    )
    confirm.add_argument("catalog", type=Path)
    confirm.add_argument("designation")
    confirm.add_argument("workspace", type=Path)
    confirm.add_argument("--alias", action="append", default=[])
    confirm.add_argument("--expected-sha256", required=True)
    confirm.add_argument("--actor", required=True)
    confirm.add_argument("--source-ref", required=True)
    return parser


def _use_utf8_stdio() -> None:
    """Keep prose exact under Windows isolated mode, which may default to cp1252."""
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is not None:
            reconfigure(encoding="utf-8", errors="strict")


def main(argv: list[str] | None = None) -> int:
    """Run one closed, typed local-agent operation without a host-specific form."""
    _use_utf8_stdio()
    parser = _parser()
    args = parser.parse_args(argv)
    try:
        if args.command == "read":
            output = read_selected(
                args.catalog,
                args.designation,
                actor=args.actor,
                source_ref=args.source_ref,
            )
        elif args.command == "draft":
            lengths = {
                len(args.clarification),
                len(args.clarification_reason),
                len(args.clarification_answer),
            }
            if len(lengths) != 1:
                raise OnboardingError(
                    "invalid_prose",
                    "Every clarification needs one reason and one answer",
                )
            output = save_prose_draft(
                args.catalog,
                args.designation,
                process_title=args.title,
                need=args.need,
                desired_outcomes=tuple(args.outcome),
                constraints=tuple(args.constraint),
                created_by=args.created_by,
                clarifications=tuple(
                    ProseClarification(question=question, why_needed=reason, answer=answer)
                    for question, reason, answer in zip(
                        args.clarification,
                        args.clarification_reason,
                        args.clarification_answer,
                        strict=True,
                    )
                ),
            )
        elif args.command == "activation-preview":
            output = preview_process_activation(
                args.catalog,
                args.designation,
                args.workspace,
                aliases=tuple(args.alias),
            )
        else:
            output = confirm_process_activation(
                args.catalog,
                args.designation,
                args.workspace,
                aliases=tuple(args.alias),
                expected_sha256=args.expected_sha256,
                actor=args.actor,
                source_ref=args.source_ref,
            )
    except (
        EntryError,
        ProcessCreationError,
        OnboardingError,
        WorkspaceError,
        ValidationError,
        OSError,
        ValueError,
    ) as error:
        code = getattr(error, "code", "invalid_request")
        print(f"zara-agent: [{code}] {error}", file=sys.stderr)
        return 1
    sys.stdout.write(output)
    sys.stdout.flush()
    return 0


__all__ = [
    "confirm_process_activation",
    "main",
    "preview_process_activation",
    "read_selected",
    "save_prose_draft",
]


if __name__ == "__main__":
    raise SystemExit(main())

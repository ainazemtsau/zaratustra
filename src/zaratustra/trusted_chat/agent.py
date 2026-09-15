"""Host-independent entry for explicit owner-requested reads and prose drafts."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from pydantic import ValidationError

from zaratustra.core import WorkspaceError, authorize_local, prepare_authorization
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
from zaratustra.process_creation import ProcessCreationError, inspect_process_creation


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


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="zara-agent",
        description="Trusted local-agent entry for explicit selected reads and prose drafts.",
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
        else:
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


__all__ = ["main", "read_selected", "save_prose_draft"]


if __name__ == "__main__":
    raise SystemExit(main())
